import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.core.config import settings
from app.core.error_codes import ERROR_MEANINGS, SyncErrorCode
from app.services.csv_reader import CsvTable, read_csv
from app.services.row_validator import ParsedCsv, parse_csv

HEADER = "external_id,name,amount,record_date\n"


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_bytes(text.encode())
    return path


def _parse(tmp_path: Path, text: str, **kwargs) -> ParsedCsv:
    return parse_csv(_write(tmp_path, "items.csv", text), **kwargs)


def _file_codes(result: ParsedCsv) -> list[str]:
    if result.file_error is None:
        return []
    return [result.file_error.code.value]


def _row_codes(result: ParsedCsv) -> list[str]:
    return [error.code.value for error in result.errors]


def test_file_unreadable(tmp_path: Path):
    missing = parse_csv(tmp_path / "missing.csv")
    assert _file_codes(missing) == ["FILE_UNREADABLE"]
    assert missing.file_error is not None
    assert missing.file_error.message == ERROR_MEANINGS[SyncErrorCode.FILE_UNREADABLE]
    assert missing.accepted == ()
    assert missing.errors == ()

    broken = _parse(tmp_path, 'external_id,name,amount,record_date\n"hello,world\n')
    assert _file_codes(broken) == ["FILE_UNREADABLE"]


def test_file_encoding_invalid(tmp_path: Path):
    path = tmp_path / "gbk.csv"
    path.write_bytes("商品,名称\n".encode("gbk"))

    result = parse_csv(path)

    assert _file_codes(result) == ["FILE_ENCODING_INVALID"]
    assert result.file_error is not None
    assert result.file_error.message == ERROR_MEANINGS[SyncErrorCode.FILE_ENCODING_INVALID]


def test_file_empty(tmp_path: Path):
    empty = parse_csv(_write(tmp_path, "empty.csv", ""))
    header_only = _parse(tmp_path, HEADER + "\n   \n")
    wrong_header_only = _parse(tmp_path, "sku,name\n")

    assert _file_codes(empty) == ["FILE_EMPTY"]
    assert _file_codes(header_only) == ["FILE_EMPTY"]
    assert _file_codes(wrong_header_only) == ["FILE_EMPTY"]
    assert empty.file_error is not None
    assert empty.file_error.message == ERROR_MEANINGS[SyncErrorCode.FILE_EMPTY]


def test_csv_header_invalid_missing_duplicate_order_and_extra(tmp_path: Path):
    data = "S001,商品A,19.90,2026-01-01\n"
    cases = {
        "missing.csv": "external_id,name,amount\n" + data,
        "duplicate.csv": "external_id,name,name,record_date\n" + data,
        "order.csv": "name,external_id,amount,record_date\n" + data,
        "extra.csv": "external_id,name,amount,record_date,extra\n" + data,
        "case.csv": "External_Id,name,amount,record_date\n" + data,
        "space.csv": "external_id,name,amount,record_date \n" + data,
    }
    for name, text in cases.items():
        result = parse_csv(_write(tmp_path, name, text))
        assert _file_codes(result) == ["CSV_HEADER_INVALID"], name
        assert result.errors == ()
        assert result.file_error is not None
        assert result.file_error.message == ERROR_MEANINGS[SyncErrorCode.CSV_HEADER_INVALID]


def test_csv_header_invalid_wins_over_row_limit(tmp_path: Path):
    text = "name,external_id,amount,record_date\n" + "S001,商品A,19.90,2026-01-01\n" * 2

    result = _parse(tmp_path, text, max_records=1)

    assert _file_codes(result) == ["CSV_HEADER_INVALID"]


def test_read_csv_still_returns_table_for_bad_header(tmp_path: Path):
    path = _write(tmp_path, "bad-header.csv", "h1,h2\nS001,商品A\n")

    loaded = read_csv(path)

    assert isinstance(loaded, CsvTable)
    assert loaded.header == ("h1", "h2")


def test_file_too_many_rows(tmp_path: Path):
    over = _parse(
        tmp_path,
        HEADER + "\n".join(f"S{i:05d},商品,19.90,2026-01-01" for i in range(10001)) + "\n",
        max_records=10000,
    )
    assert _file_codes(over) == ["FILE_TOO_MANY_ROWS"]
    assert over.accepted == ()
    assert over.file_error is not None
    assert over.file_error.message == ERROR_MEANINGS[SyncErrorCode.FILE_TOO_MANY_ROWS]

    within = _parse(
        tmp_path,
        HEADER + "\n".join(f"S{i:05d},商品,19.90,2026-01-01" for i in range(10000)) + "\n",
        max_records=10000,
    )
    assert within.file_error is None
    assert len(within.accepted) == 10000
    assert within.errors == ()


def test_file_too_many_rows_uses_settings(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "max_records_per_job", 1)
    text = HEADER + "\nS001,商品A,19.90,2026-01-01\n\nS002,商品B,19.90,2026-01-02\n"

    result = _parse(tmp_path, text)

    assert _file_codes(result) == ["FILE_TOO_MANY_ROWS"]


def test_blank_lines_do_not_count_toward_limit(tmp_path: Path):
    text = HEADER + "\n   \nS001,商品A,19.90,2026-01-01\n\n"

    result = _parse(tmp_path, text, max_records=1)

    assert result.file_error is None
    assert len(result.accepted) == 1
    assert result.accepted[0].row_number == 4


def test_row_column_count_mismatch(tmp_path: Path):
    text = HEADER + "S001,商品A,19.90\nS002,商品B,19.90,2026-01-02,extra\n"

    result = _parse(tmp_path, text)

    assert _row_codes(result) == ["ROW_COLUMN_COUNT_MISMATCH", "ROW_COLUMN_COUNT_MISMATCH"]
    assert result.accepted == ()
    assert [error.field_name for error in result.errors] == [None, None]
    assert result.errors[0].raw_row == {"cells": ["S001", "商品A", "19.90"]}
    assert "期望 4 列，实际 3 列" in result.errors[0].message


def test_field_required(tmp_path: Path):
    text = HEADER + " , , , \nS002,,19.90,2026-01-02\n"

    result = _parse(tmp_path, text)

    assert _row_codes(result) == [
        "FIELD_REQUIRED",
        "FIELD_REQUIRED",
        "FIELD_REQUIRED",
        "FIELD_REQUIRED",
        "FIELD_REQUIRED",
    ]
    assert [error.field_name for error in result.errors] == [
        "external_id",
        "name",
        "amount",
        "record_date",
        "name",
    ]
    assert result.errors[0].row_number == 2
    assert result.errors[0].message == "external_id 不能为空"
    assert result.errors[0].raw_row == {
        "external_id": " ",
        "name": " ",
        "amount": " ",
        "record_date": " ",
    }
    assert result.accepted == ()


def test_external_id_invalid(tmp_path: Path):
    too_long = "A" * 65
    text = (
        HEADER
        + "bad id,商品A,19.90,2026-01-01\n"
        + "中文,商品B,19.90,2026-01-02\n"
        + f"{too_long},商品C,19.90,2026-01-03\n"
        + "ok_id-1,商品D,19.90,2026-01-04\n"
    )

    result = _parse(tmp_path, text)

    assert _row_codes(result) == [
        "EXTERNAL_ID_INVALID",
        "EXTERNAL_ID_INVALID",
        "EXTERNAL_ID_INVALID",
    ]
    assert result.errors[0].field_name == "external_id"
    assert result.errors[0].message == "external_id 只允许字母、数字、下划线和短横线"
    assert result.errors[2].message == "external_id 长度不能超过 64"
    assert result.accepted[0].external_id == "OK_ID-1"


def test_external_id_duplicate_is_case_insensitive(tmp_path: Path):
    text = (
        HEADER
        + "  s001  ,商品A,19,2026-01-01\n"
        + "S001,商品B,19.9,2026-01-02\n"
        + "s002,商品C,19.90,2026-01-03\n"
        + "S001,坏金额,abc,2026-01-04\n"
    )

    result = _parse(tmp_path, text)

    assert [row.external_id for row in result.accepted] == ["S001", "S002"]
    assert result.accepted[0].name == "商品A"
    assert [error.code.value for error in result.errors if error.row_number == 3] == [
        "EXTERNAL_ID_DUPLICATE"
    ]
    assert result.errors[0].message == "external_id 在同一任务内重复"
    assert _row_codes(result)[-2:] == ["EXTERNAL_ID_DUPLICATE", "AMOUNT_INVALID"]


def test_duplicate_id_is_taken_when_other_fields_fail(tmp_path: Path):
    text = HEADER + "s001,商品A,-1,2026-01-01\nS001,商品B,19.90,2026-01-02\n"

    result = _parse(tmp_path, text)

    assert _row_codes(result) == ["AMOUNT_INVALID", "EXTERNAL_ID_DUPLICATE"]
    assert result.accepted == ()


def test_name_too_long(tmp_path: Path):
    text = HEADER + f"S001,{'测' * 128},19.90,2026-01-01\nS002,{'测' * 129},19.90,2026-01-02\n"

    result = _parse(tmp_path, text)

    assert len(result.accepted) == 1
    assert len(result.accepted[0].name) == 128
    assert _row_codes(result) == ["NAME_TOO_LONG"]
    assert result.errors[0].field_name == "name"
    assert result.errors[0].message == "name 长度不能超过 128"


def test_amount_invalid(tmp_path: Path):
    text = (
        HEADER
        + "S001,商品A,-1,2026-01-01\n"
        + "S002,商品B,19.901,2026-01-02\n"
        + "S003,商品C,1e2,2026-01-03\n"
        + "S004,商品D,1.5E+1,2026-01-04\n"
        + "S005,商品E,10000000000.00,2026-01-05\n"
        + "S006,商品F,abc,2026-01-06\n"
    )

    result = _parse(tmp_path, text)

    assert _row_codes(result) == ["AMOUNT_INVALID"] * 6
    assert result.accepted == ()
    assert [error.field_name for error in result.errors] == ["amount"] * 6
    assert result.errors[0].message == "amount 不能为负数"
    assert result.errors[1].message == "amount 最多两位小数"
    assert result.errors[2].message == "amount 不能使用科学计数法"
    assert result.errors[3].message == "amount 不能使用科学计数法"
    assert result.errors[4].message == "amount 超出范围"
    assert result.errors[5].message == "amount 格式不正确"


def test_amount_normalizes_without_float(tmp_path: Path):
    text = (
        HEADER
        + "S001,商品A,19,2026-01-01\n"
        + "S002,商品B,19.9,2026-01-02\n"
        + "S003,商品C,19.90,2026-01-03\n"
        + "S004,商品D,9999999999.99,2026-01-04\n"
    )

    result = _parse(tmp_path, text)

    assert result.errors == ()
    amounts = [row.amount for row in result.accepted]
    assert amounts == [
        Decimal("19.00"),
        Decimal("19.90"),
        Decimal("19.90"),
        Decimal("9999999999.99"),
    ]
    assert all(isinstance(amount, Decimal) and amount.as_tuple().exponent == -2 for amount in amounts)


def test_date_invalid(tmp_path: Path):
    text = (
        HEADER
        + "S001,商品A,19.90,2026/01/01\n"
        + "S002,商品B,19.90,01-01-2026\n"
        + "S003,商品C,19.90,2026-02-30\n"
        + "S004,商品D,19.90,2026-02-29\n"
        + "S005,商品E,19.90,2026-01-01 00:00:00\n"
        + "S006,商品F,19.90,2026-1-01\n"
        + "S007,商品G,19.90,2024-02-29\n"
    )

    result = _parse(tmp_path, text)

    assert _row_codes(result) == ["DATE_INVALID"] * 6
    assert [error.field_name for error in result.errors] == ["record_date"] * 6
    assert result.errors[0].message == "record_date 必须是 YYYY-MM-DD"
    assert result.errors[2].message == "record_date 不是有效日期"
    assert result.accepted == (
        result.accepted[0],
    )
    assert result.accepted[0].external_id == "S007"
    assert result.accepted[0].record_date == date(2024, 2, 29)


def test_valid_row_keeps_trimmed_name_and_raw_summary(tmp_path: Path):
    text = HEADER + "s001,  商品 A  ,19.90,2026-01-01\nS002,商品B,19.90,2026-13-01\n"

    result = _parse(tmp_path, text)

    assert result.file_error is None
    assert result.accepted[0].name == "商品 A"
    assert result.accepted[0].record_date == date(2026, 1, 1)
    assert result.errors[0].code is SyncErrorCode.DATE_INVALID
    assert result.errors[0].raw_row["record_date"] == "2026-13-01"
    json.dumps(result.errors[0].raw_row, ensure_ascii=False)


def test_one_row_reports_fields_in_header_order(tmp_path: Path):
    text = HEADER + "bad id,,-1,2026/01/01\n"

    result = _parse(tmp_path, text)

    assert [(error.field_name, error.code.value) for error in result.errors] == [
        ("external_id", "EXTERNAL_ID_INVALID"),
        ("name", "FIELD_REQUIRED"),
        ("amount", "AMOUNT_INVALID"),
        ("record_date", "DATE_INVALID"),
    ]
    assert result.errors[0].row_number == 2
