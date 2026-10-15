from pathlib import Path

from sqlalchemy import text

from app.core.config import Settings
from app.repositories.job_repo import JobRepository
from app.services.import_service import ImportService
from app.worker import process_job, reclaim_stale_jobs

HEADER = "external_id,name,amount,record_date\n"


def post_csv(client, content: str, name: str):
    return client.post(
        "/api/v1/jobs",
        data={"name": name},
        files={"file": ("items.csv", content.encode(), "text/csv")},
    )


def create_job(client, content: str, name: str) -> str:
    response = post_csv(client, content, name)
    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["status"] == "PENDING"
    return body["id"]


def job_row(conn, job_id: str) -> dict:
    row = conn.execute(
        text("SELECT * FROM sync_jobs WHERE id = :id"),
        {"id": job_id},
    ).mappings().one()
    return dict(row)


def test_job_timeout_seconds_reads_env(monkeypatch):
    monkeypatch.setenv("JOB_TIMEOUT_SECONDS", "45")
    assert Settings().job_timeout_seconds == 45


def test_worker_reaches_success_partial_and_failed(api):
    client, test_engine, _upload_dir = api
    importer = ImportService(test_engine)
    success_id = create_job(
        client,
        HEADER + "S001,商品A,19.90,2026-01-01\n",
        "pytest-worker-success",
    )
    partial_id = create_job(
        client,
        HEADER + "S001,商品A,19.90,2026-01-01\nS002,商品B,-1,2026-01-02\n",
        "pytest-worker-partial",
    )
    failed_id = create_job(
        client,
        "name,external_id,amount,record_date\nS001,商品A,19.90,2026-01-01\n",
        "pytest-worker-failed",
    )

    process_job(importer, success_id)
    process_job(importer, partial_id)
    process_job(importer, failed_id)

    with test_engine.connect() as conn:
        assert job_row(conn, success_id)["status"] == "SUCCESS"
        assert job_row(conn, partial_id)["status"] == "PARTIAL_SUCCESS"
        failed = job_row(conn, failed_id)
    assert failed["status"] == "FAILED"
    assert failed["last_error_code"] == "CSV_HEADER_INVALID"
    assert "Traceback" not in (failed["last_error_message"] or "")


def test_worker_marks_missing_file_unreadable(api):
    client, test_engine, _upload_dir = api
    job_id = create_job(
        client,
        HEADER + "S001,商品A,19.90,2026-01-01\n",
        "pytest-worker-missing",
    )
    with test_engine.connect() as conn:
        stored = job_row(conn, job_id)["stored_file_path"]
    Path(stored).unlink()

    process_job(ImportService(test_engine), job_id)

    with test_engine.connect() as conn:
        job = job_row(conn, job_id)
    assert job["status"] == "FAILED"
    assert job["last_error_code"] == "FILE_UNREADABLE"
    assert job["total_records"] == 0
    assert job["failed_records"] == 0


def test_worker_unexpected_error_does_not_stay_running(api):
    client, test_engine, _upload_dir = api
    job_id = create_job(
        client,
        HEADER + "S001,商品A,19.90,2026-01-01\n",
        "pytest-worker-boom",
    )
    importer = ImportService(test_engine)

    def explode(_job_id: str):
        importer.jobs.mark_running(_job_id)
        raise RuntimeError("Traceback (most recent call last): secret")

    importer.import_job = explode
    process_job(importer, job_id)

    with test_engine.connect() as conn:
        job = job_row(conn, job_id)
    assert job["status"] == "FAILED"
    assert job["last_error_code"] == "INTERNAL_ERROR"
    assert job["last_error_message"] == "Worker 处理失败"
    assert "Traceback" not in job["last_error_message"]
    assert "secret" not in job["last_error_message"]


def test_worker_second_delivery_does_not_write_again(api):
    client, test_engine, _upload_dir = api
    job_id = create_job(
        client,
        HEADER + "S001,商品A,19.90,2026-01-01\n",
        "pytest-worker-twice",
    )
    importer = ImportService(test_engine)
    process_job(importer, job_id)
    process_job(importer, job_id)

    with test_engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM sync_records WHERE job_id = :id"),
            {"id": job_id},
        ).scalar()
        job = job_row(conn, job_id)
    assert job["status"] == "SUCCESS"
    assert count == 1


def test_mark_failed_does_not_overwrite_terminal_jobs(api):
    """PENDING 和 RUNNING 可以标失败；已成功的任务保持原状态、统计和记录。"""
    client, test_engine, _upload_dir = api
    pending_id = create_job(
        client,
        HEADER + "S001,商品A,19.90,2026-01-01\n",
        "pytest-worker-mark-pending",
    )
    running_id = create_job(
        client,
        HEADER + "S002,商品B,19.90,2026-01-01\n",
        "pytest-worker-mark-running",
    )
    done_id = create_job(
        client,
        HEADER + "S003,商品C,19.90,2026-01-01\n",
        "pytest-worker-mark-done",
    )
    repo = JobRepository(test_engine)
    assert repo.mark_running(running_id) is True
    process_job(ImportService(test_engine), done_id)

    assert repo.mark_failed(pending_id, "QUEUE_ENQUEUE_FAILED", "任务已创建但加入队列失败") is True
    assert repo.mark_failed(running_id, "INTERNAL_ERROR", "Worker 处理失败") is True
    assert repo.mark_failed(done_id, "INTERNAL_ERROR", "不应覆盖") is False
    assert repo.mark_failed(pending_id, "INTERNAL_ERROR", "不应覆盖") is False

    with test_engine.connect() as conn:
        pending = job_row(conn, pending_id)
        running = job_row(conn, running_id)
        done = job_row(conn, done_id)
        done_records = conn.execute(
            text("SELECT COUNT(*) FROM sync_records WHERE job_id = :id"),
            {"id": done_id},
        ).scalar()
    assert pending["status"] == "FAILED"
    assert pending["last_error_code"] == "QUEUE_ENQUEUE_FAILED"
    assert pending["last_error_message"] == "任务已创建但加入队列失败"
    assert running["status"] == "FAILED"
    assert running["last_error_message"] == "Worker 处理失败"
    assert done["status"] == "SUCCESS"
    assert done["success_records"] == 1
    assert done["last_error_message"] is None
    assert done_records == 1


def test_reclaim_stale_running_leaves_fresh_jobs(api):
    client, test_engine, _upload_dir = api
    stale_id = create_job(client, HEADER + "S001,商品A,19.90,2026-01-01\n", "pytest-worker-stale")
    fresh_id = create_job(client, HEADER + "S002,商品B,19.90,2026-01-01\n", "pytest-worker-fresh")
    with test_engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE sync_jobs
                SET status = 'RUNNING',
                    started_at = DATE_SUB(UTC_TIMESTAMP(3), INTERVAL 301 SECOND)
                WHERE id = :id
            """),
            {"id": stale_id},
        )
        conn.execute(
            text("""
                UPDATE sync_jobs
                SET status = 'RUNNING', started_at = UTC_TIMESTAMP(3)
                WHERE id = :id
            """),
            {"id": fresh_id},
        )

    reclaimed = reclaim_stale_jobs(ImportService(test_engine), 300)

    assert stale_id in reclaimed
    assert fresh_id not in reclaimed
    with test_engine.connect() as conn:
        stale = job_row(conn, stale_id)
        fresh = job_row(conn, fresh_id)
    assert stale["status"] == "FAILED"
    assert stale["last_error_code"] == "INTERNAL_ERROR"
    assert stale["last_error_message"] == "任务处理超时"
    assert fresh["status"] == "RUNNING"
