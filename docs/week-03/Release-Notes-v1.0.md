# SyncFlow V1.0

发布日期：2026-10-16。Git 标签：`v1.0.0`（V1.0 发布提交）。

## 版本概述

用户在 React 页面选择 CSV 并创建任务。创建接口把任务 ID 放进 Redis 后立即返回，不等待整份文件处理完。Worker 读取 UTF-8 CSV（兼容 BOM），校验表头和每一行，把合法记录写入 MySQL `sync_records`，把失败写入 `sync_errors`，并在同一个事务里更新总数、成功数、失败数和终态。

终态有三种：`SUCCESS`、`PARTIAL_SUCCESS`、`FAILED`。详情页在任务还没结束时每 3 秒刷新，结束后停止。失败数大于 0，或者状态已经是 `FAILED`，都可以打开错误明细。文件级错误没有行号，页面显示 `-`。

## 安装说明

按仓库根目录 `README.md` 第 6 节，从 `.env.example` 开始安装依赖、启动 MySQL 和 Redis、迁移两套数据库、再启动 API、Worker 和前端。然后按第 7 节上传 `samples/ok.csv`。创建响应里的状态是 `PENDING`；Worker 完成后详情是 `SUCCESS`，统计为 2 / 2 / 0。

其它样例的期望统计在 `samples/README.md`。测试命令和 65 个用例的结果在 `docs/week-03/测试报告.md`。接口示例在 `docs/api.md`。

## 规范

- 表头只有 `external_id,name,amount,record_date`。金额用 `Decimal`，不用 float。
- 文件级失败的 `total_records`、`success_records`、`failed_records` 都是 0。
- 批量写入失败复用 `INTERNAL_ERROR`，消息里带批号。原始数据库报错只写日志。
- 错误明细排序是 `row_number ASC, id ASC`。空行号排在前面。错误码表见api.md.
- Worker 只在启动时回收超时的 `RUNNING` 任务，消息是「任务处理超时」。意外失败的消息是「Worker 处理失败」。已经结束的任务不会被再次标成失败。

## 不包含

幂等键、失败自动重试、取消任务、导出错误文件。`.env` 里的 `MAX_JOB_ATTEMPTS`、`RETRY_BACKOFF_SECONDS`、`IDEMPOTENCY_KEY_TTL_HOURS` 保留但未接入。这些留在 V1.1 的议题里，不在这个标签上改主线行为。

## 使用注意

不要同时运行宿主机 Worker 和 Compose Worker。两边的上传目录路径不同。改 `MAX_RECORDS_PER_JOB` 后要重启 Worker，演示结束后改回 `10000`。Windows 若不能绑定 8000，按 README 换端口，不要改 Compose 的端口映射。

## 测试环境
项目只在一下环境测试过：
| 系统环境 | 版本 |
| --- | --- |
| Python | 3.13.2 |
| MySQL | 8.0.46 |
| Redis | 7.4.11 |
| 操作系统 | Windows11Pro 26H2 |
| pytest | 9.1.1 |
| Docker | 29.8.1 |
| Docker Compose | v5.5.1 |

## 相关文档索引

下面按用途分组。路径都以仓库根目录为基准，链接相对本文件。

### 发布与验收

| 文档 | 仓库路径 | 内容 |
| --- | --- | --- |
| [V1.0 测试报告](./测试报告.md) | `docs/week-03/测试报告.md` | 测试环境、执行命令、`65 passed` 结果和逐条用例清单 |
| [AI Code Review 记录](./AI-Code-Review.md) | `docs/week-03/AI-Code-Review.md` | 对照任务书与任务计划，检查已合并主线和发布提交 |
| [三分钟演示脚本](./演示脚本.md) | `docs/week-03/演示脚本.md` | 演示前的启动步骤与逐段时间线 |
| [V1.0 复盘初稿](./复盘初稿.md) | `docs/week-03/复盘初稿.md` | 本期完成范围、遗留议题与 V1.1 输入 |

### 接口与设计

| 文档 | 仓库路径 | 内容 |
| --- | --- | --- |
| [API 文档](../api.md) | `docs/api.md` | 已实现的 HTTP 接口、请求响应示例与错误码表 |
| [API 设计（第 1 周）](../week-01/05-API设计.md) | `docs/week-01/05-API设计.md` | 接口清单与字段设计的源头规格 |
| [数据库设计](../week-01/06-数据库设计.md) | `docs/week-01/06-数据库设计.md` | `jobs` / `sync_records` / `sync_errors` 表结构与索引 |
| [任务状态机](../week-01/07-任务状态机.md) | `docs/week-01/07-任务状态机.md` | `PENDING` / `RUNNING` 与三种终态的迁移规则 |
| [Web 页面设计](../week-01/08-Web页面设计.md) | `docs/week-01/08-Web页面设计.md` | 创建、详情刷新、错误明细三个页面 |
| [业务名词表](../week-01/02-业务名词表.md) | `docs/week-01/02-业务名词表.md` | 术语口径，避免统计与错误命名歧义 |
| [需求疑问清单](../week-01/01-需求疑问清单.md) | `docs/week-01/01-需求疑问清单.md` | 第 1 周澄清记录 |
| [测试计划（第 1 周）](../week-01/09-测试计划.md) | `docs/week-01/09-测试计划.md` | 异常场景、边界值与期望结果 |
| [系统边界图](../week-01/03-系统边界图.png) | `docs/week-01/03-系统边界图.png` | 系统边界示意 |
| [核心流程图](../week-01/04-核心流程图.png) | `docs/week-01/04-核心流程图.png` | CSV 同步主链路 |

### 需求来源

| 文档 | 仓库路径 | 内容 |
| --- | --- | --- |
| [产品需求文档](../PRD/product-requirements.pdf) | `docs/PRD/product-requirements.pdf` | PRD 原文 |
| [第 1 周任务书](../tasks/week-01.pdf) | `docs/tasks/week-01.pdf` | 需求与设计周任务 |
| [第 2 周任务书](../tasks/week-02.pdf) | `docs/tasks/week-02.pdf` | 骨架搭建周任务 |
| [第 3 周任务书](../tasks/week-03.pdf) | `docs/tasks/week-03.pdf` | CSV 同步闭环与 V1.0 发布周任务 |

在线文档：服务启动后 `http://127.0.0.1:8000/docs` 是交互式 API 文档，`http://127.0.0.1:8000/openapi.json` 是机器可读规格。

