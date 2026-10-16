# SyncFlow V1.0

发布日期：2026-10-16。Git 标签：`v1.0.0`，指向包含本文件的发布提交。

## 这个版本能做什么

用户在 React 页面选择 CSV 并创建任务。创建接口把任务 ID 放进 Redis 后立即返回，不等待整份文件处理完。Worker 读取 UTF-8 CSV（兼容 BOM），校验表头和每一行，把合法记录写入 MySQL `sync_records`，把失败写入 `sync_errors`，并在同一个事务里更新总数、成功数、失败数和终态。

终态有三种：`SUCCESS`、`PARTIAL_SUCCESS`、`FAILED`。详情页在任务还没结束时每 3 秒刷新，结束后停止。失败数大于 0，或者状态已经是 `FAILED`，都可以打开错误明细。文件级错误没有行号，页面显示 `-`。

## 怎样在空环境复现

按仓库根目录 `README.md` 第 6 节，从 `.env.example` 开始安装依赖、启动 MySQL 和 Redis、迁移两套库、再启动 API、Worker 和前端。然后按第 7 节上传 `samples/ok.csv`。创建响应里的状态是 `PENDING`；Worker 完成后详情是 `SUCCESS`，统计为 2 / 2 / 0。

其它样例的期望统计在 `samples/README.md`。测试命令和 65 个用例的结果在 `docs/week-03/测试报告.md`。接口示例在 `docs/api.md`。

## 规格里已经定下来的口径

- 表头只有 `external_id,name,amount,record_date`。金额用 `Decimal`，不用 float。
- 文件级失败的 `total_records`、`success_records`、`failed_records` 都是 0。
- 批量写入失败复用 `INTERNAL_ERROR`，消息里带批号。原始数据库报错只写日志。
- 错误明细排序是 `row_number ASC, id ASC`。空行号排在前面。
- Worker 只在启动时回收超时的 `RUNNING` 任务，消息是「任务处理超时」。意外失败的消息是「Worker 处理失败」。已经结束的任务不会被再次标成失败。

## 不包含

幂等键、失败自动重试、取消任务、导出错误文件。`.env` 里的 `MAX_JOB_ATTEMPTS`、`RETRY_BACKOFF_SECONDS`、`IDEMPOTENCY_KEY_TTL_HOURS` 保留但未接入。这些留在 V1.1 的议题里，不在这个标签上改主线行为。

## 使用时注意

不要同时运行宿主机 Worker 和 Compose Worker。两边的上传目录路径不同。改 `MAX_RECORDS_PER_JOB` 后要重启 Worker，演示结束后改回 `10000`。Windows 若不能绑定 8000，按 README 换端口，不要改 Compose 的端口映射。
