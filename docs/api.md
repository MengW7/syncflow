## API 设计
1. ID 格式：全项目统一一种。建议 ULID 26 位字符串，API 里原样返回，不要有的地方加 job_ 前缀、有的地方不加。
2. 时间格式：库里 UTC datetime(3)，接口一律 ISO 8601，例如 2026-01-01T10:00:00.000Z。
3. 本周状态：只允许 PENDING | RUNNING | SUCCESS | FAILED。列表筛到别的值直接 400 INVALID_REQUEST。

### 目标结构
```
backend/
  app/
    main.py                 # FastAPI app 组装
    core/
      config.py             # 环境变量
      logging.py
      errors.py             # 领域错误 + 错误码
    db/
      session.py            # MySQL 连接
      health.py
    models/
      job.py                # Pydantic / 枚举
    repositories/
      job_repo.py
    services/
      job_service.py
      storage.py            # 受控目录存文件
      queue.py              # Redis 入队
    api/
      deps.py               # 依赖注入
      responses.py          # 统一包装
      router.py
      routes/
        health.py
        jobs.py
    worker/
      main.py               # 独立进程，先可空着
  tests/
    conftest.py
    test_jobs_api.py
  alembic/ 或 sql/          # 你已完成
  requirements.txt
```

