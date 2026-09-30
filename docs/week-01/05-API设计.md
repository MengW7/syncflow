## 1. 接口清单
| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| GET | `/healthz` | 进程存活 |
| GET | `/readyz` | MySQL + Redis 可连通 |
| POST | `/api/v1/jobs` | 上传 CSV 创建任务 |
| GET | `/api/v1/jobs` | 任务列表，分页 + 状态筛选 |
| GET | `/api/v1/jobs/{job_id}` | 任务详情与统计 |
| GET | `/api/v1/jobs/{job_id}/errors` | 错误明细分页 |
| GET | `/api/v1/jobs/{job_id}/records` | 成功记录分页 |
| POST | `/api/v1/jobs/{job_id}/cancel` | 取消分页 |
| GET | `/api/v1/jobs/{job_id}/export` | 导出成功或错误 |

## 2. 错误码
| code | 错误码 | 含义 |
| :--- | :--- | :--- |
| `VALIDATION_ERROR` | 400 | 参数或表单不合法 |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | 不是 text/csv 或未上传文件 |
| `FILE_TOO_LARGE` | 413 | 超过 MAX_UPLOAD_FILE_SIZE_MB |
| `INVALID_CSV_HEADER` | 400 或任务内失败 | 创建期可拦类型；表头内容由 Worker 判定 |
| `JOB_NOT_FOUND` | 404 | job_id 不存在 |
| `JOB_NOT_CANCELLABLE` | 409 | 当前状态不允许取消 |
| `IDEMPOTENCY_CONFLICT` | 409 | 同一 key 对应不同文件摘要 |
| `NOT_READY` | 503 | MySQL 或 Redis 不可用，仅 `/readyz` |
| `INTERNAL_ERROR` | 500 | 未预期错误，消息对用户脱敏 |

## 3. 导入任务接口
### POST /api/v1/jobs

处理：校验大小与扩展名 → 规范化文件名写入 uploads/ → pending → 立即返回 201。

**201**
```json
{
  "data": {
    "job_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "pending",
    "original_filename": "products.csv",
    "created_at": "2026-09-24T15:00:00.000Z"
  },
  "meta": {}
}
```
### GET /api/v1/jobs
Query：page、page_size。

200
```
{
  "data": {
    "items": [
      {
        "job_id": "550e8400-e29b-41d4-a716-446655440000",
        "status": "partial_succeeded",
        "original_filename": "products.csv",
        "total_rows": 100,
        "success_count": 90,
        "failure_count": 10,
        "created_at": "2026-09-24T15:00:00.000Z",
        "finished_at": "2026-09-24T15:00:08.120Z"
      }
    ]
  },
  "meta": { "page": 1, "page_size": 20, "total": 1 }
}
```

### GET /api/v1/jobs/{job_id}
200
```
{
  "data": {
    "job_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "running",
    "original_filename": "products.csv",
    "file_size_bytes": 20480,
    "total_rows": 1000,
    "success_count": 400,
    "failure_count": 12,
    "attempt_count": 1,
    "error_code": null,
    "error_message": null,
    "created_at": "2026-09-24T15:00:00.000Z",
    "started_at": "2026-09-24T15:00:01.010Z",
    "finished_at": null
  },
  "meta": {}
}
```

## 4. 任务结果接口
### GET /api/v1/jobs/{job_id}/errors
错误码：MISSING_SKU、DUPLICATE_SKU、INVALID_PRICE、INVALID_QUANTITY、MISSING_NAME、
ROW_PARSE_ERROR

### GET /api/v1/jobs/{job_id}/records
成功记录分页，字段：row_number、sku、name、price、quantity。

## 5. 健康检查

两个接口都使用统一响应信封。`/healthz` 只表示 API 进程存活，不检查 MySQL 和 Redis。`/readyz` 检查这两项依赖。

### GET /healthz

进程能响应即返回 200。

```json
{
  "data": {
    "status": "ok",
    "service": "api",
    "time": "2026-09-26T08:00:00.000000+00:00"
  },
  "meta": {}
}
```

`time` 为 UTC 的 ISO 8601 时间。

### GET /readyz

MySQL 与 Redis 都可连通时返回 200。

```json
{
  "data": {
    "status": "ok",
    "service": "api",
    "checks": { "mysql": "ok", "redis": "ok" }
  },
  "meta": {}
}
```

任一依赖失败、超时或无法连接时返回 503。`details` 里每一项只取 `ok` 或 `unavailable`，不包含主机、密码、DSN 和异常堆栈。

```json
{
  "error": {
    "code": "NOT_READY",
    "message": "依赖不可用",
    "details": { "mysql": "ok", "redis": "unavailable" }
  }
}
```
