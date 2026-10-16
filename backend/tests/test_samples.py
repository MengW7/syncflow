"""用 samples/ 里的发布样例走创建和导入，核对统计与错误码。"""

from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

from app.core.config import settings
from app.core.error_codes import ERROR_MEANINGS, SyncErrorCode
from app.services.import_service import ImportService

SAMPLES = Path(__file__).resolve().parents[2] / "samples"
HEADER = "external_id,name,amount,record_date\n"


def create_from_bytes(client, content: bytes, name: str, filename: str = "items.csv") -> str:
    response = client.post(
        "/api/v1/jobs",
        data={"name": name},
        files={"file": (filename, content, "text/csv")},
    )
    assert response.status_code == 201, response.text
    assert response.json()["data"]["status"] == "PENDING"
    return response.json()["data"]["id"]


def job_row(conn, job_id: str) -> dict:
    row = conn.execute(
        text("SELECT * FROM sync_jobs WHERE id = :id"),
        {"id": job_id},
    ).mappings().one()
    return dict(row)


def error_rows(conn, job_id: str) -> list[dict]:
    rows = conn.execute(
        text(
            """
            SELECT `row_number`, field_name, error_code
            FROM sync_errors
            WHERE job_id = :id
            ORDER BY id
            """
        ),
        {"id": job_id},
    ).mappings().all()
    return [dict(row) for row in rows]


def test_release_samples_match_expected_stats(api):
    client, test_engine, _upload_dir = api
    service = ImportService(test_engine)

    ok_id = create_from_bytes(client, (SAMPLES / "ok.csv").read_bytes(), "pytest-sample-ok", "ok.csv")
    ok = service.import_job(ok_id)
    assert ok.status == "SUCCESS"
    assert (ok.total_records, ok.success_records, ok.failed_records) == (2, 2, 0)
    with test_engine.connect() as conn:
        saved = conn.execute(
            text(
                """
                SELECT external_id, name, amount, record_date
                FROM sync_records
                WHERE job_id = :id
                ORDER BY external_id
                """
            ),
            {"id": ok_id},
        ).mappings().all()
        assert [(row["external_id"], row["name"], row["amount"], row["record_date"]) for row in saved] == [
            ("S001", "商品 A", Decimal("19.90"), date(2026, 1, 1)),
            ("S002", "商品 B", Decimal("29.50"), date(2026, 1, 2)),
        ]
        assert job_row(conn, ok_id)["last_error_code"] is None
        assert error_rows(conn, ok_id) == []

    bom_id = create_from_bytes(client, (SAMPLES / "bom.csv").read_bytes(), "pytest-sample-bom", "bom.csv")
    bom = service.import_job(bom_id)
    assert bom.status == "SUCCESS"
    assert (bom.total_records, bom.success_records, bom.failed_records) == (2, 2, 0)
    with test_engine.connect() as conn:
        assert error_rows(conn, bom_id) == []

    row_id = create_from_bytes(
        client,
        (SAMPLES / "row-errors.csv").read_bytes(),
        "pytest-sample-rows",
        "row-errors.csv",
    )
    rows = service.import_job(row_id)
    assert rows.status == "PARTIAL_SUCCESS"
    assert (rows.total_records, rows.success_records, rows.failed_records) == (8, 1, 7)
    with test_engine.connect() as conn:
        assert job_row(conn, row_id)["last_error_code"] is None
        found = error_rows(conn, row_id)
    assert [(item["row_number"], item["field_name"], item["error_code"]) for item in found] == [
        (3, "external_id", "FIELD_REQUIRED"),
        (4, "external_id", "EXTERNAL_ID_INVALID"),
        (5, "external_id", "EXTERNAL_ID_DUPLICATE"),
        (6, "name", "NAME_TOO_LONG"),
        (7, "amount", "AMOUNT_INVALID"),
        (8, "record_date", "DATE_INVALID"),
        (9, None, "ROW_COLUMN_COUNT_MISMATCH"),
    ]

    header_id = create_from_bytes(
        client,
        (SAMPLES / "bad-header.csv").read_bytes(),
        "pytest-sample-header",
        "bad-header.csv",
    )
    header = service.import_job(header_id)
    assert header.status == "FAILED"
    assert (header.total_records, header.success_records, header.failed_records) == (0, 0, 0)
    _assert_file_error(test_engine, header_id, SyncErrorCode.CSV_HEADER_INVALID)

    empty_id = create_from_bytes(
        client,
        (SAMPLES / "empty.csv").read_bytes(),
        "pytest-sample-empty",
        "empty.csv",
    )
    empty = service.import_job(empty_id)
    assert empty.status == "FAILED"
    assert (empty.total_records, empty.success_records, empty.failed_records) == (0, 0, 0)
    _assert_file_error(test_engine, empty_id, SyncErrorCode.FILE_EMPTY)


def test_import_rejects_non_utf8_and_too_many_rows(api):
    client, test_engine, _upload_dir = api
    assert settings.max_records_per_job == 10000
    service = ImportService(test_engine)

    gbk = "external_id,name,amount,record_date\nS001,商品,19.90,2026-01-01\n".encode("gbk")
    encoding_id = create_from_bytes(client, gbk, "pytest-sample-gbk")
    encoding = service.import_job(encoding_id)
    assert encoding.status == "FAILED"
    assert (encoding.total_records, encoding.success_records, encoding.failed_records) == (0, 0, 0)
    _assert_file_error(test_engine, encoding_id, SyncErrorCode.FILE_ENCODING_INVALID)

    limit = settings.max_records_per_job
    body = HEADER + "".join(f"S{i:05d},商品,19.90,2026-01-01\n" for i in range(limit + 1))
    over_id = create_from_bytes(client, body.encode("utf-8"), "pytest-sample-too-many")
    over = service.import_job(over_id)
    assert over.status == "FAILED"
    assert (over.total_records, over.success_records, over.failed_records) == (0, 0, 0)
    _assert_file_error(test_engine, over_id, SyncErrorCode.FILE_TOO_MANY_ROWS)
    with test_engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM sync_records WHERE job_id = :id"),
            {"id": over_id},
        ).scalar()
    assert count == 0


def _assert_file_error(engine, job_id: str, code: SyncErrorCode) -> None:
    with engine.connect() as conn:
        job = job_row(conn, job_id)
        found = error_rows(conn, job_id)
    assert job["last_error_code"] == code.value
    assert job["last_error_message"] == ERROR_MEANINGS[code]
    assert found == [{"row_number": None, "field_name": None, "error_code": code.value}]
