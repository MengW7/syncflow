import uuid

from sqlalchemy import text

from app.api.deps import get_job_service
from app.core.config import settings
from app.db.session import get_engine
from app.main import app
from app.repositories.job_repo import JobRepository
from app.services.job_service import JobService
from app.services.queue import queue_service
from tests.conftest import TEST_QUEUE_KEY


def post_csv(client, filename="items.csv", content=b"a,b\n1,2\n", name="pytest-create"):
    data = {} if name is None else {"name": name}
    return client.post(
        "/api/v1/jobs",
        data=data,
        files={"file": (filename, content, "text/csv")},
    )


def test_create_job_success(api):
    client, test_engine, upload_dir = api
    dev_queue_before = queue_service.client.llen("syncflow:jobs")

    response = post_csv(client, filename="../../secret.csv", name="pytest-create")

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"data", "meta"}
    job = body["data"]
    assert set(job) == {"id", "name", "status", "created_at"}
    assert job["name"] == "pytest-create"
    assert job["status"] == "PENDING"
    assert str(job["created_at"]).endswith("Z")
    assert "stored_file_path" not in response.text
    assert settings.mysql_password not in response.text

    stored = upload_dir / f"{job['id']}.csv"
    assert stored.is_file()
    assert stored.read_bytes() == b"a,b\n1,2\n"
    with test_engine.connect() as conn:
        row = conn.execute(
            text("SELECT status, source_file_name, CHAR_LENGTH(file_sha256) AS sha_len, stored_file_path FROM sync_jobs WHERE id = :id"),
            {"id": job["id"]},
        ).mappings().one()
    assert row["status"] == "PENDING"
    assert row["source_file_name"] == "secret.csv"
    assert row["sha_len"] == 64
    assert row["stored_file_path"].endswith(f"{job['id']}.csv")
    assert job["id"] in queue_service.client.lrange(TEST_QUEUE_KEY, 0, -1)
    assert queue_service.client.llen("syncflow:jobs") == dev_queue_before

    with get_engine().connect() as conn:
        leaked = conn.execute(
            text("SELECT COUNT(*) FROM sync_jobs WHERE id = :id"),
            {"id": job["id"]},
        ).scalar()
    assert leaked == 0


def test_create_rejects_invalid_parameters(api):
    client, test_engine, upload_dir = api

    missing = client.post("/api/v1/jobs", data={"name": "pytest-missing"})
    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "INVALID_REQUEST"

    text_file = post_csv(client, filename="notes.txt", content=b"hello", name="pytest-text")
    assert text_file.status_code == 400
    assert text_file.json()["error"]["code"] == "INVALID_FILE_EXTENSION"
    assert "Traceback" not in text_file.text

    long_name = post_csv(client, name="测" * 129)
    assert long_name.status_code == 400
    assert long_name.json()["error"]["code"] == "INVALID_REQUEST"
    assert list(upload_dir.glob("*.csv")) == []

    bad_status = client.get("/api/v1/jobs", params={"status": "NOPE"})
    assert bad_status.status_code == 400
    assert bad_status.json()["error"]["code"] == "INVALID_REQUEST"
    assert set(bad_status.json()["error"]) == {"code", "message", "details"}

    with test_engine.connect() as conn:
        leftover = conn.execute(text("SELECT COUNT(*) FROM sync_jobs WHERE name LIKE 'pytest-%'")).scalar()
    assert leftover == 0


def test_create_rejects_oversize_file(api, monkeypatch):
    client, _engine, upload_dir = api
    monkeypatch.setattr(settings, "max_upload_file_size_mb", 0)

    response = post_csv(client, content=b"x", name="pytest-big")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert "Traceback" not in response.text
    assert list(upload_dir.glob("*.csv")) == []


def test_database_error_is_hidden(api):
    client, test_engine, upload_dir = api

    class ExplodingRepository(JobRepository):
        def create(self, job_data):
            raise RuntimeError("mysql+pymysql://syncflow:secret-password@127.0.0.1/syncflow")

    app.dependency_overrides[get_job_service] = lambda: JobService(ExplodingRepository(test_engine))
    response = post_csv(client, name="pytest-db-error")

    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "INTERNAL_ERROR"
    assert "secret-password" not in response.text
    assert "Traceback" not in response.text
    assert "mysql+pymysql" not in response.text
    assert list(upload_dir.glob("*.csv")) == []
    with test_engine.connect() as conn:
        leftover = conn.execute(text("SELECT COUNT(*) FROM sync_jobs WHERE name = 'pytest-db-error'")).scalar()
    assert leftover == 0


def test_list_pagination_boundaries(api):
    client, test_engine, _upload_dir = api
    ids = {
        "a": "00000000-0000-4000-8000-000000000001",
        "b": "00000000-0000-4000-8000-000000000002",
        "c": "00000000-0000-4000-8000-000000000003",
    }
    stamps = {
        "a": "2099-01-02 00:00:00.000",
        "b": "2099-01-02 00:00:00.000",
        "c": "2099-01-03 00:00:00.000",
    }
    with test_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM sync_jobs WHERE id IN (:a, :b, :c) OR name LIKE 'pytest-page-%'"),
            {"a": ids["a"], "b": ids["b"], "c": ids["c"]},
        )
        for key, job_id in ids.items():
            conn.execute(
                text(
                    """
                    INSERT INTO sync_jobs (
                        id, name, status, source_file_name, stored_file_path, file_sha256,
                        total_records, success_records, failed_records, retry_count,
                        created_at, updated_at
                    ) VALUES (
                        :id, :name, 'PENDING', 'items.csv', '', :sha,
                        0, 0, 0, 0, :created_at, :created_at
                    )
                    """
                ),
                {
                    "id": job_id,
                    "name": f"pytest-page-{key}",
                    "sha": "ab" * 32,
                    "created_at": stamps[key],
                },
            )

    first = client.get("/api/v1/jobs", params={"page": 1, "page_size": 1})
    assert first.status_code == 200
    assert first.json()["meta"] == {"page": 1, "page_size": 1, "total": first.json()["meta"]["total"]}
    assert first.json()["data"][0]["id"] == ids["c"]
    assert len(first.json()["data"]) == 1

    second = client.get("/api/v1/jobs", params={"page": 2, "page_size": 1})
    third = client.get("/api/v1/jobs", params={"page": 3, "page_size": 1})
    assert second.json()["data"][0]["id"] == ids["b"]
    assert third.json()["data"][0]["id"] == ids["a"]

    total = first.json()["meta"]["total"]
    beyond = client.get("/api/v1/jobs", params={"page": total + 1, "page_size": 1})
    assert beyond.status_code == 200
    assert beyond.json()["data"] == []
    assert beyond.json()["meta"]["total"] == total

    defaults = client.get("/api/v1/jobs")
    assert defaults.status_code == 200
    assert defaults.json()["meta"]["page"] == 1
    assert defaults.json()["meta"]["page_size"] == 20

    wide = client.get("/api/v1/jobs", params={"page_size": 100})
    assert wide.status_code == 200
    assert wide.json()["meta"]["page_size"] == 100

    with test_engine.begin() as conn:
        conn.execute(text("UPDATE sync_jobs SET status = 'SUCCESS' WHERE id = :id"), {"id": ids["c"]})
    filtered = client.get("/api/v1/jobs", params={"status": "SUCCESS", "page_size": 100})
    filtered_ids = [item["id"] for item in filtered.json()["data"]]
    assert ids["c"] in filtered_ids
    assert ids["a"] not in filtered_ids

    assert client.get("/api/v1/jobs", params={"page": 0}).status_code == 400
    assert client.get("/api/v1/jobs", params={"page_size": 101}).status_code == 400

    detail = client.get(f"/api/v1/jobs/{ids['c']}")
    assert detail.status_code == 200
    assert detail.json()["data"]["status"] == "SUCCESS"
    assert "stored_file_path" not in detail.text

    missing = client.get(f"/api/v1/jobs/{uuid.uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "JOB_NOT_FOUND"
    assert "Traceback" not in missing.text


def test_openapi_lists_job_routes(api):
    client, _engine, _upload_dir = api
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "post" in paths["/api/v1/jobs"]
    assert "get" in paths["/api/v1/jobs"]
    assert "get" in paths["/api/v1/jobs/{job_id}"]
