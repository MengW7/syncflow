"""把已读入的 CSV 做行级校验，并提供从文件到校验结果的入口。

文件级错误先返回，不再产生行级错误。行级错误留在原行，其余行继续校验。
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.core.config import settings
from app.core.error_codes import SyncErrorCode
from app.services.csv_reader import (
    CsvDataRow,
    CsvReadError,
    CsvTable,
    EXPECTED_HEADER,
    read_csv,
    validate_header,
    validate_row_count,
)

# DECIMAL(12,2) 最多 10 位整数加 2 位小数。
_MAX_AMOUNT = Decimal("9999999999.99")
_CENT = Decimal("0.01")
_AMOUNT = re.compile(r"^\d+(?:\.(\d+))?$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_EXTERNAL_ID = re.compile(r"^[A-Za-z0-9_-]+\Z")
_RAW_CELL_LIMIT = 200


@dataclass(frozen=True)
class ValidRow:
    """一行校验通过后的规范化结果。amount 是两位小数的 Decimal，不是 float。"""

    row_number: int
    external_id: str
    name: str
    amount: Decimal
    record_date: date


@dataclass(frozen=True)
class RowError:
    """一行里的一个错误。同一行可以有多条，字段顺序与表头一致。"""

    row_number: int
    field_name: str | None
    code: SyncErrorCode
    message: str
    raw_row: dict[str, object]


@dataclass(frozen=True)
class ParsedCsv:
    """parse_csv 的结果。file_error 有值时，accepted 和 errors 都为空。"""

    file_error: CsvReadError | None = None
    accepted: tuple[ValidRow, ...] = ()
    errors: tuple[RowError, ...] = ()


def parse_csv(path: str | Path, *, max_records: int | None = None) -> ParsedCsv:
    """读取、表头校验、行数上限、行级校验。上限默认取 MAX_RECORDS_PER_JOB。"""
    loaded = read_csv(path)
    if isinstance(loaded, CsvReadError):
        return ParsedCsv(file_error=loaded)

    # 表头先于行数。表头不对时，即使行数也超了，也只报 CSV_HEADER_INVALID。
    header_error = validate_header(loaded)
    if header_error is not None:
        return ParsedCsv(file_error=header_error)

    limit = settings.max_records_per_job if max_records is None else max_records
    limit_error = validate_row_count(loaded, limit)
    if limit_error is not None:
        return ParsedCsv(file_error=limit_error)

    accepted, errors = validate_rows(loaded)
    return ParsedCsv(accepted=accepted, errors=errors)


def validate_rows(table: CsvTable) -> tuple[tuple[ValidRow, ...], tuple[RowError, ...]]:
    """校验数据行。格式合法的 external_id 会占住唯一性，即使这一行别的字段失败。"""
    seen: set[str] = set()
    accepted: list[ValidRow] = []
    errors: list[RowError] = []
    for row in table.rows:
        row_errors, valid = _validate_row(row, seen)
        errors.extend(row_errors)
        if valid is not None:
            accepted.append(valid)
    return tuple(accepted), tuple(errors)


def _validate_row(
    row: CsvDataRow,
    seen: set[str],
) -> tuple[list[RowError], ValidRow | None]:
    raw_row = _raw_row(row.cells)
    if len(row.cells) != len(EXPECTED_HEADER):
        return [
            _error(
                row,
                None,
                SyncErrorCode.ROW_COLUMN_COUNT_MISMATCH,
                f"列数不正确，期望 {len(EXPECTED_HEADER)} 列，实际 {len(row.cells)} 列",
                raw_row,
            )
        ], None

    external_id, name, amount_text, record_text = (cell.strip() for cell in row.cells)
    found: list[RowError] = []

    normalized_id: str | None = None
    if external_id == "":
        found.append(_required(row, "external_id", raw_row))
    else:
        id_message = _external_id_message(external_id)
        if id_message is not None:
            found.append(_error(row, "external_id", SyncErrorCode.EXTERNAL_ID_INVALID, id_message, raw_row))
        else:
            normalized_id = external_id.upper()
            if normalized_id in seen:
                found.append(
                    _error(
                        row,
                        "external_id",
                        SyncErrorCode.EXTERNAL_ID_DUPLICATE,
                        "external_id 在同一任务内重复",
                        raw_row,
                    )
                )
            else:
                seen.add(normalized_id)

    normalized_name: str | None = None
    if name == "":
        found.append(_required(row, "name", raw_row))
    elif len(name) > 128:
        found.append(_error(row, "name", SyncErrorCode.NAME_TOO_LONG, "name 长度不能超过 128", raw_row))
    else:
        normalized_name = name

    amount: Decimal | None = None
    if amount_text == "":
        found.append(_required(row, "amount", raw_row))
    else:
        amount, amount_message = _parse_amount(amount_text)
        if amount_message is not None:
            found.append(_error(row, "amount", SyncErrorCode.AMOUNT_INVALID, amount_message, raw_row))

    parsed_date: date | None = None
    if record_text == "":
        found.append(_required(row, "record_date", raw_row))
    else:
        parsed_date, date_message = _parse_date(record_text)
        if date_message is not None:
            found.append(_error(row, "record_date", SyncErrorCode.DATE_INVALID, date_message, raw_row))

    if (
        found
        or normalized_id is None
        or normalized_name is None
        or amount is None
        or parsed_date is None
    ):
        return found, None

    return [], ValidRow(
        row_number=row.row_number,
        external_id=normalized_id,
        name=normalized_name,
        amount=amount,
        record_date=parsed_date,
    )


def _external_id_message(text: str) -> str | None:
    if len(text) > 64:
        return "external_id 长度不能超过 64"
    if _EXTERNAL_ID.fullmatch(text) is None:
        return "external_id 只允许字母、数字、下划线和短横线"
    return None


def _parse_amount(text: str) -> tuple[Decimal | None, str | None]:
    """用 Decimal 解析金额。不经过 float，超过两位小数的写法直接拒绝，不四舍五入。"""
    if re.search(r"[eE]", text):
        return None, "amount 不能使用科学计数法"
    if text.startswith("-"):
        return None, "amount 不能为负数"
    matched = _AMOUNT.fullmatch(text)
    if matched is None:
        return None, "amount 格式不正确"
    fraction = matched.group(1) or ""
    if len(fraction) > 2:
        return None, "amount 最多两位小数"
    integer_part = text.split(".", 1)[0].lstrip("0") or "0"
    if len(integer_part) > 10:
        return None, "amount 超出范围"
    amount = Decimal(text).quantize(_CENT)
    if amount > _MAX_AMOUNT:
        return None, "amount 超出范围"
    return amount, None


def _parse_date(text: str) -> tuple[date | None, str | None]:
    if _DATE.fullmatch(text) is None:
        return None, "record_date 必须是 YYYY-MM-DD"
    try:
        return date.fromisoformat(text), None
    except ValueError:
        return None, "record_date 不是有效日期"


def _required(row: CsvDataRow, field_name: str, raw_row: dict[str, object]) -> RowError:
    return _error(row, field_name, SyncErrorCode.FIELD_REQUIRED, f"{field_name} 不能为空", raw_row)


def _error(
    row: CsvDataRow,
    field_name: str | None,
    code: SyncErrorCode,
    message: str,
    raw_row: dict[str, object],
) -> RowError:
    return RowError(
        row_number=row.row_number,
        field_name=field_name,
        code=code,
        message=message,
        raw_row=raw_row,
    )


def _raw_row(cells: tuple[str, ...]) -> dict[str, object]:
    """原始单元格摘要。保留未规范化的文本，过长的单元格截断。"""
    clipped = [_clip(cell) for cell in cells]
    if len(clipped) == len(EXPECTED_HEADER):
        return {
            "external_id": clipped[0],
            "name": clipped[1],
            "amount": clipped[2],
            "record_date": clipped[3],
        }
    return {"cells": clipped}


def _clip(value: str) -> str:
    if len(value) <= _RAW_CELL_LIMIT:
        return value
    return value[:_RAW_CELL_LIMIT] + "…"
