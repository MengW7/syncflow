import json
from datetime import date
from decimal import Decimal

from sqlalchemy import text

from app.core.config import settings
from app.db.session import create_mysql_engine
from app.services.import_service import ImportService
from app.services.row_validator import ValidRow

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
    return response.json()["data"]["id"]


def job_row(conn, job_id: str) -> dict:
    row = conn.execute(
        text("SELECT * FROM sync_jobs WHERE id = :id"),
        {"id": job_id},
    ).mappings().one()
    return dict(row)


def records(conn, job_id: str) -> list[dict]:
    rows = conn.execute(
        text("""
            SELECT external_id, name, amount, record_date
            FROM sync_records
            WHERE job_id = :id
            ORDER BY external_id
        """),
        {"id": job_id},
    ).mappings().all()
    return [dict(row) for row in rows]


def errors(conn, job_id: str) -> list[dict]:
    rows = conn.execute(
        text("""
            SELECT `row_number`, field_name, error_code, error_message, raw_row
            FROM sync_errors
            WHERE job_id = :id
            ORDER BY id
        """),
        {"id": job_id},
    ).mappings().all()
    loaded = []
    for row in rows:
        item = dict(row)
        item["raw_row"] = _json_or_none(item["raw_row"])
        loaded.append(item)
    return loaded


def test_success_import_writes_records_and_terminal_stats(api):
    client, test_engine, _upload_dir = api
    job_id = create_job(
        client,
        HEADER + "s001,商品A,19,2026-01-01\nS002,商品B,19.9,2026-01-02\n",
        "pytest-import-success",
    )

    result = ImportService(test_engine).import_job(job_id)

    assert result.skipped is False
    assert result.status == "SUCCESS"
    assert (result.total_records, result.success_records, result.failed_records) == (2, 2, 0)
    with test_engine.connect() as conn:
        job = job_row(conn, job_id)
        saved = records(conn, job_id)
        assert job["status"] == "SUCCESS"
        assert job["finished_at"] is not None
        assert (job["total_records"], job["success_records"], job["failed_records"]) == (2, 2, 0)
        assert job["total_records"] == job["success_records"] + job["failed_records"]
        assert job["last_error_code"] is None
        assert errors(conn, job_id) == []
    assert [(row["external_id"], row["amount"], row["record_date"]) for row in saved] == [
        ("S001", Decimal("19.00"), date(2026, 1, 1)),
        ("S002", Decimal("19.90"), date(2026, 1, 2)),
    ]
    _assert_dev_database_has_no_job(job_id)


def test_partial_success_keeps_good_rows_and_row_errors(api):
    client, test_engine, _upload_dir = api
    job_id = create_job(
        client,
        HEADER + "S001,商品A,19.90,2026-01-01\nS002,商品B,-1,2026-01-02\n",
        "pytest-import-partial",
    )

    result = ImportService(test_engine).import_job(job_id)

    assert result.status == "PARTIAL_SUCCESS"
    assert (result.total_records, result.success_records, result.failed_records) == (2, 1, 1)
    with test_engine.connect() as conn:
        job = job_row(conn, job_id)
        saved = records(conn, job_id)
        found = errors(conn, job_id)
        assert job["status"] == "PARTIAL_SUCCESS"
        assert job["finished_at"] is not None
        assert job["total_records"] == job["success_records"] + job["failed_records"]
    assert [row["external_id"] for row in saved] == ["S001"]
    assert len(found) == 1
    assert found[0]["row_number"] == 3
    assert found[0]["field_name"] == "amount"
    assert found[0]["error_code"] == "AMOUNT_INVALID"
    assert found[0]["raw_row"]["amount"] == "-1"


def test_all_rows_invalid_finishes_failed(api):
    client, test_engine, _upload_dir = api
    job_id = create_job(
        client,
        HEADER + ",商品A,19.90,2026-01-01\nS002,商品B,-1,2026-01-02\n",
        "pytest-import-all-failed",
    )

    result = ImportService(test_engine).import_job(job_id)

    assert result.status == "FAILED"
    assert (result.total_records, result.success_records, result.failed_records) == (2, 0, 2)
    with test_engine.connect() as conn:
        job = job_row(conn, job_id)
        assert job["status"] == "FAILED"
        assert job["finished_at"] is not None
        assert records(conn, job_id) == []
        assert len(errors(conn, job_id)) == 2


def test_header_invalid_is_file_level_failure(api):
    client, test_engine, _upload_dir = api
    job_id = create_job(
        client,
        "name,external_id,amount,record_date\nS001,商品A,19.90,2026-01-01\n",
        "pytest-import-header",
    )

    result = ImportService(test_engine).import_job(job_id)

    assert result.status == "FAILED"
    assert (result.total_records, result.success_records, result.failed_records) == (0, 0, 0)
    with test_engine.connect() as conn:
        job = job_row(conn, job_id)
        found = errors(conn, job_id)
        assert job["status"] == "FAILED"
        assert job["last_error_code"] == "CSV_HEADER_INVALID"
        assert job["finished_at"] is not None
        assert records(conn, job_id) == []
    assert len(found) == 1
    assert found[0]["row_number"] is None
    assert found[0]["field_name"] is None
    assert found[0]["error_code"] == "CSV_HEADER_INVALID"
    assert found[0]["raw_row"] is None


def test_empty_file_is_file_level_failure(api):
    client, test_engine, _upload_dir = api
    job_id = create_job(client, HEADER, "pytest-import-empty")

    result = ImportService(test_engine).import_job(job_id)

    assert result.status == "FAILED"
    assert (result.total_records, result.success_records, result.failed_records) == (0, 0, 0)
    with test_engine.connect() as conn:
        job = job_row(conn, job_id)
        found = errors(conn, job_id)
        assert job["last_error_code"] == "FILE_EMPTY"
        assert records(conn, job_id) == []
    assert len(found) == 1
    assert found[0]["row_number"] is None
    assert found[0]["field_name"] is None
    assert found[0]["error_code"] == "FILE_EMPTY"


def test_ten_thousand_rows_can_be_written(api):
    client, test_engine, _upload_dir = api
    body = HEADER + "".join(
        f"S{i:05d},商品,19.90,2026-01-01\n" for i in range(10000)
    )
    job_id = create_job(client, body, "pytest-import-10000")

    result = ImportService(test_engine).import_job(job_id)

    assert result.status == "SUCCESS"
    assert (result.total_records, result.success_records, result.failed_records) == (10000, 10000, 0)
    with test_engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM sync_records WHERE job_id = :id"),
            {"id": job_id},
        ).scalar()
        error_count = conn.execute(
            text("SELECT COUNT(*) FROM sync_errors WHERE job_id = :id"),
            {"id": job_id},
        ).scalar()
    assert count == 10000
    assert error_count == 0


def test_failed_batch_does_not_roll_back_other_batches(api):
    client, test_engine, _upload_dir = api
    body = HEADER + "".join(
        f"S{i:03d},商品,19.90,2026-01-01\n" for i in range(1, 5)
    )
    job_id = create_job(client, body, "pytest-import-batch")
    _insert_conflict(test_engine, job_id, "S003")

    result = ImportService(test_engine).import_job(job_id, batch_size=2)

    assert result.status == "PARTIAL_SUCCESS"
    assert (result.total_records, result.success_records, result.failed_records) == (4, 2, 2)
    with test_engine.connect() as conn:
        job = job_row(conn, job_id)
        saved = {row["external_id"] for row in records(conn, job_id)}
        found = errors(conn, job_id)
        assert job["last_error_code"] == "INTERNAL_ERROR"
        assert job["finished_at"] is not None
        assert job["last_error_message"] == "第 2 批写入失败（唯一约束冲突）"
        _assert_no_database_detail(job["last_error_message"])
    assert saved == {"S001", "S002", "S003"}
    assert "S004" not in saved
    assert len(found) == 1
    assert found[0]["error_code"] == "INTERNAL_ERROR"
    assert found[0]["error_message"] == "第 2 批写入失败（唯一约束冲突）"
    assert found[0]["row_number"] is None
    assert found[0]["raw_row"] == {"batch_number": 2, "row_count": 2}
    _assert_no_database_detail(found[0]["error_message"])


def test_multiple_batch_failures_summarize_batch_numbers(api):
    client, test_engine, _upload_dir = api
    body = HEADER + "".join(
        f"S{i:03d},商品,19.90,2026-01-01\n" for i in range(1, 5)
    )
    job_id = create_job(client, body, "pytest-import-batches")
    _insert_conflict(test_engine, job_id, "S001")
    _insert_conflict(test_engine, job_id, "S003")

    result = ImportService(test_engine).import_job(job_id, batch_size=2)

    assert result.status == "FAILED"
    assert (result.total_records, result.success_records, result.failed_records) == (4, 0, 4)
    with test_engine.connect() as conn:
        job = job_row(conn, job_id)
        found = errors(conn, job_id)
    assert job["last_error_message"] == "第 1、2 批写入失败，共 2 批"
    _assert_no_database_detail(job["last_error_message"])
    assert [item["error_message"] for item in found] == [
        "第 1 批写入失败（唯一约束冲突）",
        "第 2 批写入失败（唯一约束冲突）",
    ]


def test_repeat_import_does_not_write_again(api):
    client, test_engine, _upload_dir = api
    job_id = create_job(
        client,
        HEADER + "S001,商品A,19.90,2026-01-01\n",
        "pytest-import-repeat",
    )
    service = ImportService(test_engine)
    first = service.import_job(job_id)
    second = service.import_job(job_id)

    assert first.status == "SUCCESS"
    assert second.skipped is True
    assert second.status == "SUCCESS"
    with test_engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM sync_records WHERE job_id = :id"),
            {"id": job_id},
        ).scalar()
    assert count == 1


def _insert_conflict(engine, job_id: str, external_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO sync_records (
                    job_id, external_id, name, amount, record_date, created_at, updated_at
                ) VALUES (
                    :job_id, :external_id, '已存在', 1.00, '2026-01-01', UTC_TIMESTAMP(3), UTC_TIMESTAMP(3)
                )
            """),
            {"job_id": job_id, "external_id": external_id},
        )


def _assert_dev_database_has_no_job(job_id: str) -> None:
    dev_engine = create_mysql_engine(settings.mysql_database)
    try:
        with dev_engine.connect() as conn:
            database = conn.execute(text("SELECT DATABASE()")).scalar()
            assert database == settings.mysql_database
            assert database != settings.mysql_test_database
            counts = {
                "sync_jobs": conn.execute(
                    text("SELECT COUNT(*) FROM sync_jobs WHERE id = :id"),
                    {"id": job_id},
                ).scalar(),
                "sync_records": conn.execute(
                    text("SELECT COUNT(*) FROM sync_records WHERE job_id = :id"),
                    {"id": job_id},
                ).scalar(),
                "sync_errors": conn.execute(
                    text("SELECT COUNT(*) FROM sync_errors WHERE job_id = :id"),
                    {"id": job_id},
                ).scalar(),
            }
            assert counts == {"sync_jobs": 0, "sync_records": 0, "sync_errors": 0}
    finally:
        dev_engine.dispose()


def _assert_no_database_detail(message: str) -> None:
    assert "Duplicate entry" not in message
    assert "uk_sync_records" not in message
    assert "sync_records" not in message


def _json_or_none(value):
    if value is None or isinstance(value, dict):
        return value
    return json.loads(value)


def test_record_repository_keeps_earlier_batches_when_a_later_batch_conflicts(api):
    """直接造一批重复键，确认仓库层只回滚冲突的那一批。"""
    _client, test_engine, _upload_dir = api
    job_id = create_job(
        _client,
        HEADER + "S001,商品A,19.90,2026-01-01\n",
        "pytest-import-repo-batch",
    )
    rows = [
        _valid("S001"),
        _valid("S002"),
        _valid("S001"),
        _valid("S003"),
    ]

    result = ImportService(test_engine).records.insert_in_batches(job_id, rows, batch_size=2)

    assert result.inserted_count == 2
    assert len(result.failures) == 1
    assert result.failures[0].batch_number == 2
    assert result.failures[0].row_count == 2
    assert result.failures[0].reason == "unique"
    with test_engine.connect() as conn:
        saved = {row["external_id"] for row in records(conn, job_id)}
    assert saved == {"S001", "S002"}


def _valid(external_id: str) -> ValidRow:
    return ValidRow(
        row_number=2,
        external_id=external_id,
        name="商品",
        amount=Decimal("19.90"),
        record_date=date(2026, 1, 1),
    )
