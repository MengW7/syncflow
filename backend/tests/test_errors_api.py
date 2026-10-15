import json
import uuid

from sqlalchemy import text

HEADER = "external_id,name,amount,record_date\n"
ERROR_FIELDS = [
    "job_id",
    "row_number",
    "field_name",
    "error_code",
    "error_message",
    "raw_row",
    "created_at",
]


def post_csv(client, content: str, name: str):
    return client.post(
        "/api/v1/jobs",
        data={"name": name},
        files={"file": ("items.csv", content.encode(), "text/csv")},
    )


def create_job(client, name: str) -> str:
    response = post_csv(client, HEADER + "S001,商品A,19.90,2026-01-01\n", name)
    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["status"] == "PENDING"
    return body["id"]


def insert_error(conn, job_id: str, *, row_number, field_name, error_code, raw_row=None):
    conn.execute(
        text("""
            INSERT INTO sync_errors (
                job_id, `row_number`, field_name, error_code, error_message, raw_row, created_at
            ) VALUES (
                :job_id, :row_number, :field_name, :error_code, :error_message,
                CAST(:raw_row AS JSON), UTC_TIMESTAMP(3)
            )
        """),
        {
            "job_id": job_id,
            "row_number": row_number,
            "field_name": field_name,
            "error_code": error_code,
            "error_message": f"{error_code} 说明",
            "raw_row": None if raw_row is None else json.dumps(raw_row, ensure_ascii=False),
        },
    )


def test_error_list_paginates_in_row_then_id_order(api):
    client, test_engine, _upload_dir = api
    job_id = create_job(client, "pytest-errors-page")
    with test_engine.begin() as conn:
        insert_error(
            conn, job_id,
            row_number=5, field_name="amount", error_code="AMOUNT_INVALID",
            raw_row={"amount": "-1"},
        )
        insert_error(
            conn, job_id,
            row_number=5, field_name="name", error_code="FIELD_REQUIRED",
            raw_row={"name": ""},
        )
        insert_error(
            conn, job_id,
            row_number=2, field_name="external_id", error_code="FIELD_REQUIRED",
            raw_row={"external_id": ""},
        )
        insert_error(
            conn, job_id,
            row_number=None, field_name=None, error_code="CSV_HEADER_INVALID",
        )

    defaults = client.get(f"/api/v1/jobs/{job_id}/errors")
    assert defaults.status_code == 200
    body = defaults.json()
    assert body["meta"] == {"page": 1, "page_size": 20, "total": 4}
    assert [item["error_code"] for item in body["data"]] == [
        "CSV_HEADER_INVALID",
        "FIELD_REQUIRED",
        "AMOUNT_INVALID",
        "FIELD_REQUIRED",
    ]
    assert [item["field_name"] for item in body["data"]] == [
        None,
        "external_id",
        "amount",
        "name",
    ]
    file_error = body["data"][0]
    assert list(file_error.keys()) == ERROR_FIELDS
    assert file_error["job_id"] == job_id
    assert file_error["row_number"] is None
    assert file_error["raw_row"] is None
    assert file_error["created_at"].endswith("Z")
    assert body["data"][2]["raw_row"] == {"amount": "-1"}
    assert "id" not in file_error

    first = client.get(f"/api/v1/jobs/{job_id}/errors", params={"page": 1, "page_size": 2})
    second = client.get(f"/api/v1/jobs/{job_id}/errors", params={"page": 2, "page_size": 2})
    assert first.json()["meta"]["total"] == 4
    assert [item["field_name"] for item in first.json()["data"]] == [None, "external_id"]
    assert [item["field_name"] for item in second.json()["data"]] == ["amount", "name"]

    beyond = client.get(f"/api/v1/jobs/{job_id}/errors", params={"page": 3, "page_size": 2})
    assert beyond.status_code == 200
    assert beyond.json()["data"] == []
    assert beyond.json()["meta"] == {"page": 3, "page_size": 2, "total": 4}


def test_error_list_rejects_bad_pages_and_missing_or_empty_jobs(api):
    client, _engine, _upload_dir = api
    job_id = create_job(client, "pytest-errors-empty")

    empty = client.get(f"/api/v1/jobs/{job_id}/errors")
    assert empty.status_code == 200
    assert empty.json()["data"] == []
    assert empty.json()["meta"] == {"page": 1, "page_size": 20, "total": 0}
    assert "Traceback" not in empty.text

    missing = client.get(f"/api/v1/jobs/{uuid.uuid4()}/errors")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "JOB_NOT_FOUND"
    assert "Traceback" not in missing.text
    assert "sync_errors" not in missing.text

    zero = client.get(f"/api/v1/jobs/{job_id}/errors", params={"page": 0})
    huge = client.get(f"/api/v1/jobs/{job_id}/errors", params={"page_size": 101})
    assert zero.status_code == 400
    assert huge.status_code == 400
    assert zero.json()["error"]["code"] == "INVALID_REQUEST"
    assert huge.json()["error"]["code"] == "INVALID_REQUEST"
    assert "Traceback" not in zero.text
    assert "Traceback" not in huge.text


def test_openapi_lists_error_route(api):
    client, _engine, _upload_dir = api
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "get" in response.json()["paths"]["/api/v1/jobs/{job_id}/errors"]
