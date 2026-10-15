"""读取本地 CSV，并做文件级的表头与行数检查。

read_csv 只把文件读成表头和数据行，并区分读不了、编码不对、空文件。
表头内容和行数上限由 validate_header、validate_row_count 判定。
单元格规则在 row_validator。
"""

import csv
import io
from dataclasses import dataclass
from pathlib import Path

from app.core.error_codes import ERROR_MEANINGS, SyncErrorCode


@dataclass(frozen=True)
class CsvDataRow:
    """一条计入总数的数据行。

    row_number 是这条记录在文件里的起始行号，从 1 开始，表头也占行号。
    被忽略的空行不占记录，但后面的行号仍按文件原行计算。
    """

    row_number: int
    cells: tuple[str, ...]


@dataclass(frozen=True)
class CsvTable:
    """读成功的结果。rows 不含表头，也不含被忽略的空行。"""

    header: tuple[str, ...]
    header_row_number: int
    rows: tuple[CsvDataRow, ...]

    @property
    def record_count(self) -> int:
        return len(self.rows)


# 表头必须且只能是这四列，顺序固定。比较时不去掉空格，也不忽略大小写。
EXPECTED_HEADER: tuple[str, ...] = ("external_id", "name", "amount", "record_date")


@dataclass(frozen=True)
class CsvReadError:
    """文件级失败。任务不再做行级校验。"""

    code: SyncErrorCode
    message: str


def read_csv(path: str | Path) -> CsvTable | CsvReadError:
    """按 UTF-8（兼容 BOM）和逗号分隔读取 CSV。"""
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return _failure(SyncErrorCode.FILE_UNREADABLE)

    try:
        # utf-8-sig 会去掉文件开头的 BOM，避免表头第一个字段带上 \ufeff。
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return _failure(SyncErrorCode.FILE_ENCODING_INVALID)

    return _parse(text)


def validate_header(table: CsvTable) -> CsvReadError | None:
    """表头缺列、重复、顺序错或有多余列时，返回文件级 CSV_HEADER_INVALID。"""
    if table.header != EXPECTED_HEADER:
        return _failure(SyncErrorCode.CSV_HEADER_INVALID)
    return None


def validate_row_count(table: CsvTable, max_records: int) -> CsvReadError | None:
    """忽略空行后的数据行数超过上限时，返回文件级 FILE_TOO_MANY_ROWS。

    等于上限可以通过。这里数的是非空行，还没做单元格校验。
    """
    if table.record_count > max_records:
        return _failure(SyncErrorCode.FILE_TOO_MANY_ROWS)
    return None


def _failure(code: SyncErrorCode) -> CsvReadError:
    return CsvReadError(code=code, message=ERROR_MEANINGS[code])


def _is_ignored_blank(cells: list[str]) -> bool:
    """空行不计入总数。

    完全空白，以及没有逗号、只有空白的一行，都视为空行。
    ``,`` 或 ``,,,`` 这类带分隔符的行是空字段，留给行级校验，这里保留。
    """
    if not cells:
        return True
    return len(cells) == 1 and cells[0].strip() == ""


def _parse(text: str) -> CsvTable | CsvReadError:
    # strict=True：引号不闭合等结构损坏算读不了，而不是把后续内容吞进一个字段。
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    header: tuple[str, ...] | None = None
    header_row_number = 0
    rows: list[CsvDataRow] = []
    previous_line = 0

    try:
        for cells in reader:
            start_line = previous_line + 1
            previous_line = reader.line_num
            if _is_ignored_blank(cells):
                continue
            values = tuple(cells)
            if header is None:
                header = values
                header_row_number = start_line
                continue
            rows.append(CsvDataRow(row_number=start_line, cells=values))
    except csv.Error:
        return _failure(SyncErrorCode.FILE_UNREADABLE)

    # 没有数据行时，不论表头写得对不对，都先算「空文件或只有表头」。
    if header is None or not rows:
        return _failure(SyncErrorCode.FILE_EMPTY)

    return CsvTable(header=header, header_row_number=header_row_number, rows=tuple(rows))
