# SyncFlow

SyncFlow 提供一个可追踪的数据导入闭环：用户通过 React 页面提交 CSV，接口立刻创建任务并返回，Worker 从 Redis 取出任务，校验每一行，把合法数据写入 MySQL，并保存状态、统计和错误明细。


## 1. 技术栈

| 层级 | 选型 |
|------|------|
| 后端 / Worker | Python 3.13 + FastAPI + Uvicorn |
| Web | React 19 + TypeScript + Vite + React Router |
| 数据库 | MySQL 8.0（镜像 `mysql:8.0`） |
| 队列 | Redis 7（镜像 `redis:7-alpine`） |
| 编排 | Docker Compose |
| 配置 | `.env` / `.env.example` |

## 2. 环境要求

- Python 3.13。创建虚拟环境用 `py -3.13`，不要用其它版本。
- Node.js 20+
- Git
- Docker Desktop。Windows 上先启用 WSL2，并确认 Docker 状态是 Running。

## 3. 仓库结构

```text
syncflow/
├── backend/                  # FastAPI 与 Worker（python -m app.worker）
├── frontend/                 # React + Vite
├── docs/                     # API 说明、周任务、发布记录
├── samples/                  # 可复现的 CSV 样例和期望统计
├── scripts/                  # 迁移脚本
├── uploads/                  # 上传目录，文件不提交
├── docker-compose.yml
├── .env.example
└── README.md
```

字段规则和 curl 示例在 [docs/api.md](docs/api.md)。样例期望统计在 [samples/README.md](samples/README.md)。

## 4. CSV 契约

文件必须是 `.csv`，UTF-8（允许 BOM），逗号分隔，第一行是表头。空行忽略，不计入总数。默认最大 10MB，对应 `MAX_UPLOAD_FILE_SIZE_MB`。单个任务默认最多 10000 条有效数据行，对应 `MAX_RECORDS_PER_JOB`。正好等于上限可以通过，多 1 字节或多 1 行会被拒绝。

表头必须且只能是下面四列，顺序固定：

```text
external_id,name,amount,record_date
```

| 字段 | 类型 | 必填 | 校验 | 存储 |
| --- | --- | --- | --- | --- |
| external_id | string | 是 | 去掉首尾空格后长度 1–64，只允许字母、数字、下划线和短横线；同一任务内大小写不敏感地唯一 | 大写 |
| name | string | 是 | 去掉首尾空格后长度 1–128 | 去掉首尾空格 |
| amount | decimal(12,2) | 是 | 非负，最多两位小数，不用科学计数法。`19`、`19.9`、`19.90` 都合法 | `DECIMAL(12,2)` |
| record_date | date | 是 | 严格 `YYYY-MM-DD`，且是真实日期 | `DATE` |

终态：全部成功是 `SUCCESS`；有成功也有行级失败是 `PARTIAL_SUCCESS`；文件级失败或全部行失败是 `FAILED`。`total_records = success_records + failed_records`。文件级失败时三个数都是 0。12 个 CSV 错误码见 [docs/api.md](docs/api.md)。

## 5. 配置

```powershell
Copy-Item .env.example .env
```

Linux 或 macOS：

```bash
cp .env.example .env
```

在宿主机跑 API 和 Worker 时，把 `.env` 改成：

```text
MYSQL_HOST=127.0.0.1
REDIS_ADDR=127.0.0.1:6379
```

Compose 里的 API 和 Worker 会自己覆盖这两项，`.env` 保持 `mysql` 和 `redis:6379` 即可。

`MAX_RECORDS_PER_JOB` 默认 `10000`，Worker 进程启动时读取。`MAX_UPLOAD_FILE_SIZE_MB` 默认 `10`。`JOB_TIMEOUT_SECONDS` 默认 `300`，Worker 只在启动时回收超时的 `RUNNING` 任务。

`MAX_JOB_ATTEMPTS`、`RETRY_BACKOFF_SECONDS`、`IDEMPOTENCY_KEY_TTL_HOURS` 先留在 `.env` 里，V1.0 不使用。

上传目录不要写进 `.env`。Compose 把 `./uploads` 挂到容器内的 `/data/uploads`。宿主机进程必须在自己的终端里设置 `UPLOAD_DIR`，见下一节。不要同时跑宿主机 Worker 和 Compose Worker：两边看到的文件路径不一样，后启动的那个会把任务标成 `FILE_UNREADABLE`。

## 6. 本地启动

在仓库根目录执行。

### 6.1 后端虚拟环境

```powershell
py -3.13 -m venv backend\.venv
backend\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

### 6.2 MySQL 和 Redis

```powershell
docker compose up -d mysql redis
```

等 `docker compose ps` 里 mysql、redis 都是 healthy，再迁移：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\migrate.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\migrate.ps1 -Test
```

两条命令应分别打印 `migrated: syncflow` 和 `migrated: syncflow_test`。

### 6.3 API

新开一个终端，位于仓库根目录：

```powershell
$env:UPLOAD_DIR = (Resolve-Path .\uploads).Path
backend\.venv\Scripts\Activate.ps1
Set-Location backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

如果 Windows 把 8000 划进了排除端口，API 会绑不上。换一个端口，例如 18000，并在前端终端设置 `$env:API_PROXY_TARGET = "http://127.0.0.1:18000"`。不要为了绕过它去改已经提交的 `docker-compose.yml` 端口。

### 6.4 Worker

再开一个终端，同样在仓库根目录。必须和 API 使用同一个 `UPLOAD_DIR`：

```powershell
$env:UPLOAD_DIR = (Resolve-Path .\uploads).Path
backend\.venv\Scripts\Activate.ps1
Set-Location backend
python -m app.worker
```

没有这个进程时，任务会停在 `PENDING`。

### 6.5 前端

```powershell
Set-Location frontend
npm install
npm run dev
```

浏览器打开 http://127.0.0.1:5173 。创建任务的页面是 http://127.0.0.1:5173/jobs/new 。

### 6.6 只用 Compose

镜像可用、并且宿主机能绑定 8000 时，可以在根目录执行：

```powershell
docker compose up -d --build
```

这种方式不要再另开宿主机 Worker。Web 容器通过 `API_PROXY_TARGET=http://api:8000` 访问 API。

## 7. 用样例做一次导入

先确认第 6 节的 API 和 Worker 都在运行，然后回到仓库根目录：

```powershell
$created = curl.exe -s -X POST "http://127.0.0.1:8000/api/v1/jobs" -F "name=样例-正常" -F "file=@samples/ok.csv;type=text/csv" | ConvertFrom-Json
$id = $created.data.id
Start-Sleep -Seconds 2
curl.exe -s "http://127.0.0.1:8000/api/v1/jobs/$id"
```

创建请求应马上返回，`data.status` 为 `PENDING`。Worker 跑完后详情里是 `SUCCESS`，`total_records`、`success_records`、`failed_records` 分别是 2、2、0。页面上也可以看到同样的数字。

其余样例的期望统计在 [samples/README.md](samples/README.md)。把上面的文件名换成 `samples/row-errors.csv`、`samples/bad-header.csv`、`samples/bom.csv` 或 `samples/empty.csv` 即可。

## 8. 停止

在 API、Worker 和前端所在的终端按 Ctrl+C。数据库和队列：

```powershell
docker compose down
```

## 9. 数据库迁移

业务表不由 MySQL 镜像自动创建。`scripts/init_db.sql` 通过迁移脚本应用到已经启动的库。脚本可以重复执行。

Linux：

```bash
docker compose up -d mysql
chmod +x scripts/migrate.sh
./scripts/migrate.sh
./scripts/migrate.sh --test
```

不传参数时使用 `syncflow`。`--test` 使用 `syncflow_test`，避免测试数据进开发库。

Windows 命令见 6.2。查看库和表之前，先把 `.env` 读进当前终端：

```powershell
Get-Content .env | ForEach-Object {
  if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
  $name, $value = $_.Split('=', 2)
  Set-Item -Path "Env:$name" -Value $value
}
docker compose exec -T mysql mysql --user=$env:MYSQL_USER --password=$env:MYSQL_PASSWORD --host=127.0.0.1 -e "SHOW DATABASES;"
docker compose exec -T mysql mysql --user=$env:MYSQL_USER --password=$env:MYSQL_PASSWORD --host=127.0.0.1 -e "SHOW TABLES FROM $env:MYSQL_DATABASE; SHOW TABLES FROM $env:MYSQL_TEST_DATABASE;"
```

每个库都应有且只有 `sync_jobs`、`sync_records`、`sync_errors`。

```powershell
docker compose exec -T mysql mysql --user=$env:MYSQL_USER --password=$env:MYSQL_PASSWORD --host=127.0.0.1 $env:MYSQL_DATABASE -e "SHOW CREATE TABLE sync_jobs\G; SHOW CREATE TABLE sync_records\G; SHOW CREATE TABLE sync_errors\G;"
```

| 对象 | 应该看到 |
| --- | --- |
| `sync_jobs` | 主键 `id`；索引 `(status, created_at)`、`(created_at)` |
| `sync_records` | `amount` 为 `decimal(12,2)`；`UNIQUE (job_id, external_id)` |
| `sync_errors` | 索引 `(job_id, row_number)`；`raw_row` 为 `json` |
| 字符集 | `DEFAULT CHARSET=utf8mb4` |

账号权限使用 `.env` 里的 root 密码：

```powershell
docker compose exec -T mysql mysql --user=root --password=$env:MYSQL_ROOT_PASSWORD --host=127.0.0.1 -e "SHOW GRANTS FOR '$($env:MYSQL_USER)'@'%';"
```

里面应有对 `syncflow` 和 `syncflow_test` 的授权。再执行一次 6.2 的两条迁移命令，仍应打印 `migrated:`，表还是这三张。

## 10. 前端构建

```powershell
Set-Location frontend
npm install
npm run build
```

构建产物在 `frontend/dist`。本地开发用 `npm run dev`，不用先构建。

## 11. 测试

后端测试写入 `syncflow_test`，不写开发库 `syncflow`。在 `backend` 目录执行：

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest
```

前端没有 `npm test`。检查用：

```powershell
Set-Location frontend
npm run lint
npm run build
```

探活：

```powershell
curl.exe -s http://127.0.0.1:8000/healthz
curl.exe -s http://127.0.0.1:8000/readyz
```

## 12. 查看日志

Compose 服务：

```powershell
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f mysql
docker compose logs -f redis
docker compose logs -f web
```

按第 6 节在宿主机启动时，日志就在对应终端里。导入日志的 logger 名是 `syncflow.import`。

## 13. 清理数据

下面的命令会删掉 MySQL 数据卷和 Redis 容器数据：

```powershell
docker compose down -v
```

清完后需要重新执行 6.2 的迁移。上传文件在 `uploads/`，按文件名手工删除即可，不要删 `uploads/.gitkeep`。

## 14. 已知限制

- 幂等键、自动重试和导出接口不属于 V1.0。
- 批量写入失败使用 `INTERNAL_ERROR`，不另建错误码。
- 错误明细里空的 `row_number` 会排在有行号的记录前面。
- 超时回收只在 Worker 启动时做一次。
- 本机若不能绑定 8000，用 6.3 的备用端口，不要改 Compose 文件。
