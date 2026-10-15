from enum import Enum


class SyncErrorCode(str, Enum):
    """CSV 同步错误码。文件级 5 个，行级 7 个。前后端和导出文件共用这一套。"""

    FILE_UNREADABLE = "FILE_UNREADABLE"
    FILE_ENCODING_INVALID = "FILE_ENCODING_INVALID"
    FILE_EMPTY = "FILE_EMPTY"
    CSV_HEADER_INVALID = "CSV_HEADER_INVALID"
    FILE_TOO_MANY_ROWS = "FILE_TOO_MANY_ROWS"

    ROW_COLUMN_COUNT_MISMATCH = "ROW_COLUMN_COUNT_MISMATCH"
    FIELD_REQUIRED = "FIELD_REQUIRED"
    EXTERNAL_ID_INVALID = "EXTERNAL_ID_INVALID"
    EXTERNAL_ID_DUPLICATE = "EXTERNAL_ID_DUPLICATE"
    NAME_TOO_LONG = "NAME_TOO_LONG"
    AMOUNT_INVALID = "AMOUNT_INVALID"
    DATE_INVALID = "DATE_INVALID"


# 文件级：写入 sync_errors 时 row_number 为空。
FILE_LEVEL_ERROR_CODES: tuple[SyncErrorCode, ...] = (
    SyncErrorCode.FILE_UNREADABLE,
    SyncErrorCode.FILE_ENCODING_INVALID,
    SyncErrorCode.FILE_EMPTY,
    SyncErrorCode.CSV_HEADER_INVALID,
    SyncErrorCode.FILE_TOO_MANY_ROWS,
)

# 行级：写入 sync_errors 时 row_number 有值。
ROW_LEVEL_ERROR_CODES: tuple[SyncErrorCode, ...] = (
    SyncErrorCode.ROW_COLUMN_COUNT_MISMATCH,
    SyncErrorCode.FIELD_REQUIRED,
    SyncErrorCode.EXTERNAL_ID_INVALID,
    SyncErrorCode.EXTERNAL_ID_DUPLICATE,
    SyncErrorCode.NAME_TOO_LONG,
    SyncErrorCode.AMOUNT_INVALID,
    SyncErrorCode.DATE_INVALID,
)

# 规格表里的固定 field_name。None 表示留空。
# FIELD_REQUIRED 的字段名不固定，写入时填实际缺值的列。
ERROR_FIELD_NAMES: dict[SyncErrorCode, str | None] = {
    SyncErrorCode.FILE_UNREADABLE: None,
    SyncErrorCode.FILE_ENCODING_INVALID: None,
    SyncErrorCode.FILE_EMPTY: None,
    SyncErrorCode.CSV_HEADER_INVALID: None,
    SyncErrorCode.FILE_TOO_MANY_ROWS: None,
    SyncErrorCode.ROW_COLUMN_COUNT_MISMATCH: None,
    SyncErrorCode.FIELD_REQUIRED: None,
    SyncErrorCode.EXTERNAL_ID_INVALID: "external_id",
    SyncErrorCode.EXTERNAL_ID_DUPLICATE: "external_id",
    SyncErrorCode.NAME_TOO_LONG: "name",
    SyncErrorCode.AMOUNT_INVALID: "amount",
    SyncErrorCode.DATE_INVALID: "record_date",
}

ERROR_MEANINGS: dict[SyncErrorCode, str] = {
    SyncErrorCode.FILE_UNREADABLE: "文件无法读取",
    SyncErrorCode.FILE_ENCODING_INVALID: "编码无法识别或非 UTF-8",
    SyncErrorCode.FILE_EMPTY: "文件为空或只有表头",
    SyncErrorCode.CSV_HEADER_INVALID: "表头缺失、重复、顺序错误或包含额外字段",
    SyncErrorCode.FILE_TOO_MANY_ROWS: "有效数据行超过配置上限",
    SyncErrorCode.ROW_COLUMN_COUNT_MISMATCH: "列数不正确",
    SyncErrorCode.FIELD_REQUIRED: "必填字段为空",
    SyncErrorCode.EXTERNAL_ID_INVALID: "格式不符合规则",
    SyncErrorCode.EXTERNAL_ID_DUPLICATE: "同一任务内重复",
    SyncErrorCode.NAME_TOO_LONG: "超过长度限制",
    SyncErrorCode.AMOUNT_INVALID: "非法、为负数或小数位超过两位",
    SyncErrorCode.DATE_INVALID: "格式错误或日期不存在",
}
