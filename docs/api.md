# SyncFlow API

V1.0 已实现的 HTTP 接口。交互文档在服务起来后打开 `http://127.0.0.1:8000/docs`，机器可读规格是 `http://127.0.0.1:8000/openapi.json`。OpenAPI 里包含 `POST /api/v1/jobs`、`GET /api/v1/jobs`、`GET /api/v1/jobs/{job_id}` 和 `GET /api/v1/jobs/{job_id}/errors`。

任务 ID 是 UUID 36 位字符串。时间是 UTC，序列化后以 `Z` 结尾。成功响应包在 `{ "data", "meta" }` 里。失败响应是：

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "请求参数验证失败",
    "details": []
  }
}
```

创建任务只把 ID 放进 Redis 队列 `syncflow:jobs`，然后立刻返回。CSV 解析、写入和终态由 Worker 完成。下面的示例假定 API 在 `http://127.0.0.1:8000`，并且 Worker 已经在跑。命令在仓库根目录的 PowerShell 里执行。

## 状态

列表筛选和详情只使用这五个值。其它 `status` 返回 400 `INVALID_REQUEST`。

| status | 含义 |
| --- | --- |
| PENDING | 已创建，还没开始处理 |
| RUNNING | Worker 正在处理 |
| SUCCESS | 有效数据行全部写入成功 |
| PARTIAL_SUCCESS | 至少一行成功，并且至少一行行级失败 |
| FAILED | 文件级失败，或所有有效行都失败，或处理过程失败 |

计数规则：`total_records = success_records + failed_records`。文件级失败时三个数都是 0，原因在 `last_error_code` 和 `sync_errors`。行级失败时 `last_error_code` 可以为空，逐行原因在错误明细里。

## 创建任务

`POST /api/v1/jobs`

表单字段：`file`（必填，扩展名 `.csv`，大小默认不超过 10MB）、`name`（选填，去掉首尾空格后最长 128）。成功返回 201，`data` 只有 `id`、`name`、`status`、`created_at`。此时 `status` 一般是 `PENDING`。Redis 入队失败时仍返回 201，但 `status` 为 `FAILED`，`last_error_code` 为 `QUEUE_ENQUEUE_FAILED`。

```powershell
curl.exe -s -X POST "http://127.0.0.1:8000/api/v1/jobs" -F "name=样例-正常" -F "file=@samples/ok.csv;type=text/csv"
```

缺文件、名称超长、分页参数非法都是 400 `INVALID_REQUEST`。扩展名不是 `.csv` 是 400 `INVALID_FILE_EXTENSION`。超过大小上限是 400 `FILE_TOO_LARGE`。数据库异常返回 500 `INTERNAL_ERROR`，响应里没有 SQL、路径或堆栈。

## 任务列表

`GET /api/v1/jobs?page=1&page_size=20&status=PARTIAL_SUCCESS`

`page` 默认 1，最小 1。`page_size` 默认 20，最大 100。`status` 可省略。超过最后一页返回 200 和空数组，`meta.total` 不变。`data` 是数组，不是 `data.items`。

```powershell
curl.exe -s "http://127.0.0.1:8000/api/v1/jobs?page=1&page_size=20&status=PARTIAL_SUCCESS"
```

## 任务详情

`GET /api/v1/jobs/{job_id}`

不存在返回 404 `JOB_NOT_FOUND`。响应不包含 `stored_file_path` 和 `file_sha256`。

```powershell
curl.exe -s "http://127.0.0.1:8000/api/v1/jobs/00000000-0000-4000-8000-000000000000"
```

把上一节创建结果里的 `data.id` 换进去，可以看到样例跑完后的 `SUCCESS`、`total_records=2`、`success_records=2`、`failed_records=0`。

## 错误明细

`GET /api/v1/jobs/{job_id}/errors?page=1&page_size=20`

分页规则与任务列表相同。任务不存在返回 404 `JOB_NOT_FOUND`。任务存在但没有错误时返回 200，`data` 为 `[]`，`meta.total` 为 0。

每条记录只有这 7 个字段：`job_id`、`row_number`、`field_name`、`error_code`、`error_message`、`raw_row`、`created_at`。`raw_row` 是对象或 `null`。内部自增 `id` 不返回，只参与排序。

排序是 `row_number ASC, id ASC`。MySQL 把空的 `row_number` 排在有行号的记录前面。同一行号按写入顺序。

```powershell
curl.exe -s "http://127.0.0.1:8000/api/v1/jobs/00000000-0000-4000-8000-000000000000/errors?page=1&page_size=20"
```

用 `samples/row-errors.csv` 创建并等 Worker 跑完后，第一页应看到 7 条行级错误，行号从 3 到 9。用 `samples/bad-header.csv` 时只有一条，`row_number` 为 `null`，`error_code` 为 `CSV_HEADER_INVALID`。

## CSV 错误码

这 12 个码写入 `sync_errors.error_code`。文件级错误的 `row_number` 和 `field_name` 都为空。

| error_code | 级别 | field_name | 含义 |
| --- | --- | --- | --- |
| FILE_UNREADABLE | 文件 | 空 | 文件无法读取 |
| FILE_ENCODING_INVALID | 文件 | 空 | 编码无法识别或非 UTF-8 |
| FILE_EMPTY | 文件 | 空 | 文件为空或只有表头 |
| CSV_HEADER_INVALID | 文件 | 空 | 表头缺失、重复、顺序错误或包含额外字段 |
| FILE_TOO_MANY_ROWS | 文件 | 空 | 有效数据行超过 `MAX_RECORDS_PER_JOB` |
| ROW_COLUMN_COUNT_MISMATCH | 行 | 空 | 列数不正确 |
| FIELD_REQUIRED | 行 | 实际缺值的列 | 必填字段为空 |
| EXTERNAL_ID_INVALID | 行 | external_id | 格式不符合规则 |
| EXTERNAL_ID_DUPLICATE | 行 | external_id | 同一任务内重复 |
| NAME_TOO_LONG | 行 | name | 超过长度限制 |
| AMOUNT_INVALID | 行 | amount | 非法、为负数或小数位超过两位 |
| DATE_INVALID | 行 | record_date | 格式错误或日期不存在 |

批量写入失败不新增错误码，复用接口错误码 `INTERNAL_ERROR`。`error_message` 说明是哪一批，以及是唯一约束冲突还是写入失败。原始数据库报错只留在日志 `syncflow.import`。

## 其它 HTTP 错误码

| code | HTTP | 何时出现 |
| --- | --- | --- |
| INVALID_REQUEST | 400 | 缺文件、名称超长、页码或 `page_size` 或 `status` 非法 |
| INVALID_FILE_EXTENSION | 400 | 扩展名不是 `.csv` |
| FILE_TOO_LARGE | 400 | 文件大于 `MAX_UPLOAD_FILE_SIZE_MB` |
| JOB_NOT_FOUND | 404 | 详情或错误明细的任务不存在 |
| INTERNAL_ERROR | 500 | 未处理异常。响应消息是「服务器内部错误」 |
| NOT_READY | 503 | `GET /readyz` 发现 MySQL 或 Redis 不可用 |

## 探活

```powershell
curl.exe -s http://127.0.0.1:8000/healthz
curl.exe -s http://127.0.0.1:8000/readyz
```

`/healthz` 只说明 API 进程在。`/readyz` 同时检查 MySQL 和 Redis，检查值只有 `ok` 或 `unavailable`。
