from pathlib import Path

from app.core.error_codes import ERROR_MEANINGS, SyncErrorCode
from app.services.csv_reader import CsvReadError, CsvTable, read_csv

HEADER = "external_id,name,amount,record_date\n"


def _write(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path


def test_utf8_keeps_text_and_skips_blank_lines(tmp_path: Path):
    path = _write(
        tmp_path / "items.csv",
        (
            HEADER
            + "\n"
            + "S001,商品A,19.90,2026-01-01\n"
            + "   \n"
            + "S002,商品B,29.50,2026-01-02\n"
        ).encode(),
    )

    table = read_csv(path)

    assert isinstance(table, CsvTable)
    assert table.header == ("external_id", "name", "amount", "record_date")
    assert table.header_row_number == 1
    assert table.record_count == 2
    assert [(row.row_number, row.cells[1]) for row in table.rows] == [
        (3, "商品A"),
        (5, "商品B"),
    ]


def test_utf8_bom_does_not_prefix_header(tmp_path: Path):
    path = _write(
        tmp_path / "bom.csv",
        (HEADER + "S001,商品A,19.90,2026-01-01\n").encode("utf-8-sig"),
    )

    table = read_csv(path)

    assert isinstance(table, CsvTable)
    assert table.header[0] == "external_id"
    assert table.rows[0].cells[1] == "商品A"
    assert "\ufeff" not in table.header[0]


def test_crlf_and_quoted_newline(tmp_path: Path):
    path = _write(
        tmp_path / "crlf.csv",
        ("h1,h2\r\n\r\n\"hello\r\nworld\",b\r\n").encode(),
    )

    table = read_csv(path)

    assert isinstance(table, CsvTable)
    assert table.record_count == 1
    assert table.rows[0].row_number == 3
    assert table.rows[0].cells == ("hello\r\nworld", "b")


def test_comma_only_row_is_kept(tmp_path: Path):
    path = _write(tmp_path / "commas.csv", b"h1,h2\n,\nS001,x\n")

    table = read_csv(path)

    assert isinstance(table, CsvTable)
    assert table.record_count == 2
    assert table.rows[0].row_number == 2
    assert table.rows[0].cells == ("", "")


def test_empty_file_is_file_empty(tmp_path: Path):
    result = read_csv(_write(tmp_path / "empty.csv", b""))
    _assert_error(result, SyncErrorCode.FILE_EMPTY)


def test_bom_only_is_file_empty(tmp_path: Path):
    result = read_csv(_write(tmp_path / "bom-only.csv", b"\xef\xbb\xbf"))
    _assert_error(result, SyncErrorCode.FILE_EMPTY)


def test_header_only_is_file_empty(tmp_path: Path):
    result = read_csv(_write(tmp_path / "header.csv", (HEADER + "\n   \n").encode()))
    _assert_error(result, SyncErrorCode.FILE_EMPTY)


def test_missing_file_is_unreadable(tmp_path: Path):
    result = read_csv(tmp_path / "missing.csv")
    _assert_error(result, SyncErrorCode.FILE_UNREADABLE)


def test_directory_is_unreadable(tmp_path: Path):
    result = read_csv(tmp_path)
    _assert_error(result, SyncErrorCode.FILE_UNREADABLE)


def test_unclosed_quote_is_unreadable(tmp_path: Path):
    result = read_csv(_write(tmp_path / "broken.csv", b'a,b\n"hello,world\n'))
    _assert_error(result, SyncErrorCode.FILE_UNREADABLE)


def test_invalid_utf8_is_encoding_invalid(tmp_path: Path):
    result = read_csv(_write(tmp_path / "bad.csv", b"\xff\xfeh1,h2\n"))
    _assert_error(result, SyncErrorCode.FILE_ENCODING_INVALID)


def test_gbk_text_is_encoding_invalid(tmp_path: Path):
    result = read_csv(_write(tmp_path / "gbk.csv", "商品,名称\n".encode("gbk")))
    _assert_error(result, SyncErrorCode.FILE_ENCODING_INVALID)


def _assert_error(result: CsvTable | CsvReadError, code: SyncErrorCode) -> None:
    assert isinstance(result, CsvReadError)
    assert result.code is code
    assert result.message == ERROR_MEANINGS[code]
