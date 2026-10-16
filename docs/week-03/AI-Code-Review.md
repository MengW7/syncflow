# AI Code Review 记录

日期：2026-10-16。对照 `docs/tasks/week-03.pdf` 和 `docs/week-03/任务计划.md`，检查已经合并的主线和这次发布提交。这是阅读实现、样例和测试后的记录，不是另一次远端 Review 评论。

## 已有的可审阅 PR

发布标准要求代码至少经过一次 PR 和一次 AI Code Review。下面五次合并已经在主线上：

| PR | 合并提交 | 内容 |
| --- | --- | --- |
| #1 | `73d7c39` | CSV 解析和行校验 |
| #2 | `2b2b4ef` | 批量写入、错误记录和任务统计 |
| #3 | `c990425` | Worker 消费 |
| #4 | `292d35c` | 错误明细查询 API |
| #5 | `9229157` | 创建页、详情轮询和错误明细页 |

这次发布在 `chore/week3/v1-release`，标签 `v1.0.0` 指向本提交。远端 AI Review 不由本文件代替，要在发布 PR 上由仓库所有者发送 `/review`，走 `.github/workflows/deepseek-review.yml`。

## 核对过的行为

- 创建接口保存文件并入队后返回 201，导入在 Worker 或 `ImportService.import_job` 里进行。
- 五份样例的终态和 `total/success/failed` 与 `samples/README.md` 一致，由 `tests/test_samples.py` 锁住。
- 正好 10MB 可以创建，多 1 字节返回 `FILE_TOO_LARGE` 并删除半截文件。10000 行可以写入，10001 行是文件级 `FILE_TOO_MANY_ROWS`，计数为 0。
- 文件级 5 码和行级 7 码都有断言。错误明细的路径在 `/openapi.json` 里。
- 详情轮询在终态停止。文件级失败即使 `failed_records` 为 0 也有错误明细入口。
- `mark_failed` 只更新 `PENDING` 或 `RUNNING`。公开错误信息不带 SQL、路径和堆栈。

## 结论

实现和周规格、任务计划里已经采纳的口径一致，可以带标签 `v1.0.0`。下面几项是已知限制，不在这个发布提交里改：

- 批量写入失败继续用 `INTERNAL_ERROR`，不新增 `DB_WRITE_FAILED`。
- 空 `row_number` 按 MySQL 默认排在有行号的记录前面。
- 超时回收只在 Worker 启动时执行，不删除已经写入的 `sync_records`，也不重算计数。
- 不同时运行宿主机 Worker 和 Compose Worker。
- 前端没有自动化测试。页面上的 10MB 和 128 字限制没有从后端配置注入。

对应的后续写法在 `docs/week-03/复盘初稿.md`。
