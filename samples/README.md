# 样例数据

这些 CSV 用来核对 V1.0 的统计口径。期望数字来自导入完成后的任务行：`total_records` / `success_records` / `failed_records`。文件级失败时三个数都是 0，错误只出现在 `sync_errors` 和 `last_error_code`。

表头固定为 `external_id,name,amount,record_date`。`ok.csv` 与规格示例一致，字段前后的空格会在入库前去掉，`external_id` 以大写保存。

| 文件 | 终态 | total | success | failed | 预期错误 |
| --- | --- | --- | --- | --- | --- |
| `ok.csv` | SUCCESS | 2 | 2 | 0 | 无 |
| `bom.csv` | SUCCESS | 2 | 2 | 0 | 无。文件以 UTF-8 BOM 开头，读入时去掉 |
| `row-errors.csv` | PARTIAL_SUCCESS | 8 | 1 | 7 | 见下表。`last_error_code` 为空，错误在 `sync_errors` |
| `bad-header.csv` | FAILED | 0 | 0 | 0 | `CSV_HEADER_INVALID`，`row_number` 为空 |
| `empty.csv` | FAILED | 0 | 0 | 0 | `FILE_EMPTY`，`row_number` 为空 |

`ok.csv` 入库后的两行是 `S001 / 商品 A / 19.90 / 2026-01-01` 和 `S002 / 商品 B / 29.50 / 2026-01-02`。

`row-errors.csv` 第 1 行是表头。第 2 行合法。后面每一行只产生一条错误：

| 文件行号 | error_code | field_name |
| --- | --- | --- |
| 3 | FIELD_REQUIRED | external_id |
| 4 | EXTERNAL_ID_INVALID | external_id |
| 5 | EXTERNAL_ID_DUPLICATE | external_id |
| 6 | NAME_TOO_LONG | name |
| 7 | AMOUNT_INVALID | amount |
| 8 | DATE_INVALID | record_date |
| 9 | ROW_COLUMN_COUNT_MISMATCH | 空 |

页面上文件级错误的行号显示为 `-`。自动化核对在 `backend/tests/test_samples.py`。用法见仓库根目录 README 的「用样例做一次导入」。
