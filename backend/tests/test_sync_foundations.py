from sqlalchemy import text

from app.core.config import Settings
from app.core.error_codes import (
    ERROR_FIELD_NAMES,
    ERROR_MEANINGS,
    FILE_LEVEL_ERROR_CODES,
    ROW_LEVEL_ERROR_CODES,
    SyncErrorCode,
)
from tests.conftest import delete_pytest_jobs


def test_max_records_per_job_reads_env(monkeypatch):
    assert Settings.model_fields["max_records_per_job"].default == 10000

    monkeypatch.setenv("MAX_RECORDS_PER_JOB", "42")
    assert Settings().max_records_per_job == 42

    monkeypatch.setenv("MAX_RECORDS_PER_JOB", "10000")
    assert Settings().max_records_per_job == 10000


def test_sync_error_codes_match_week3_spec():
    assert [code.value for code in FILE_LEVEL_ERROR_CODES] == [
        "FILE_UNREADABLE",
        "FILE_ENCODING_INVALID",
        "FILE_EMPTY",
        "CSV_HEADER_INVALID",
        "FILE_TOO_MANY_ROWS",
    ]
    assert [code.value for code in ROW_LEVEL_ERROR_CODES] == [
        "ROW_COLUMN_COUNT_MISMATCH",
        "FIELD_REQUIRED",
        "EXTERNAL_ID_INVALID",
        "EXTERNAL_ID_DUPLICATE",
        "NAME_TOO_LONG",
        "AMOUNT_INVALID",
        "DATE_INVALID",
    ]
    assert set(FILE_LEVEL_ERROR_CODES).isdisjoint(ROW_LEVEL_ERROR_CODES)
    assert set(FILE_LEVEL_ERROR_CODES) | set(ROW_LEVEL_ERROR_CODES) == set(SyncErrorCode)
    assert set(ERROR_FIELD_NAMES) == set(SyncErrorCode)
    assert set(ERROR_MEANINGS) == set(SyncErrorCode)
    assert ERROR_FIELD_NAMES[SyncErrorCode.AMOUNT_INVALID] == "amount"
    assert ERROR_FIELD_NAMES[SyncErrorCode.FIELD_REQUIRED] is None
    assert ERROR_FIELD_NAMES[SyncErrorCode.FILE_EMPTY] is None


def test_cleanup_removes_records_and_errors(api):
    client, test_engine, _upload_dir = api
    response = client.post(
        "/api/v1/jobs",
        data={"name": "pytest-cleanup"},
        files={"file": ("items.csv", b"a,b\n1,2\n", "text/csv")},
    )
    assert response.status_code == 201
    job_id = response.json()["data"]["id"]

    with test_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO sync_records (
                    job_id, external_id, name, amount, record_date, created_at, updated_at
                ) VALUES (
                    :job_id, 'S001', '商品A', 19.90, '2026-01-01', UTC_TIMESTAMP(3), UTC_TIMESTAMP(3)
                )
                """
            ),
            {"job_id": job_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO sync_errors (
                    job_id, `row_number`, field_name, error_code, error_message, raw_row, created_at
                ) VALUES (
                    :job_id, NULL, NULL, 'FILE_EMPTY', '文件为空', NULL, UTC_TIMESTAMP(3)
                )
                """
            ),
            {"job_id": job_id},
        )
        delete_pytest_jobs(conn)
        left_jobs = conn.execute(
            text("SELECT COUNT(*) FROM sync_jobs WHERE id = :job_id"),
            {"job_id": job_id},
        ).scalar()
        left_records = conn.execute(
            text("SELECT COUNT(*) FROM sync_records WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).scalar()
        left_errors = conn.execute(
            text("SELECT COUNT(*) FROM sync_errors WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).scalar()

    assert left_jobs == 0
    assert left_records == 0
    assert left_errors == 0
