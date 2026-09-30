# SyncFlow

SyncFlow 提供一个可追踪的数据导入闭环：用户通过 React Web 页面提交 CSV 文件，系统创建任务并异步处理，校验每条记录，将合法数据写入 MySQL，并保存任务状态、处理统计、错误记录和执行日志。


## 技术栈

| 层级 | 选型 |
|------|------|
| 后端 / Worker | Python 3.13 + FastAPI + Uvicorn |
| Web | React 18 + TypeScript + Vite + React Router |
| 数据库 | MySQL 8.4 |
| 队列 / 缓存 | Redis 7.4.11 |
| 编排 | Docker Compose |
| 配置 | `.env` / `.env.example`，从环境变量读取 |

## 环境要求
- Node.js 20+
- Git
- Docker Desktop(Windows启用WSL2)

## 仓库结构
```text
syncflow/
├── backend/                  # FastAPI + Worker
│   └── app/
│       ├── main.py           # /healthz 接口
│       └── worker.py
├── frontend/                 # React + Vite
├── docs/                     # PRD、周任务、设计文档
├── uploads/                  # 受控上传目录（不提交文件）
├── docker-compose.yml
├── .env.example
└── README.md
```

## 快速启动
### 1. 初始化
在根目录中打开终端运行：
```copy .env.example .env```
编辑.env文件中的MYSQL_HOST和REDIS_ADDR字段:
```
MYSQL_HOST=127.0.0.1
REDIS_ADDR=127.0.0.1:6379
```
进入backend文件夹，终端中运行：
```
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. 启动Docker
在根目录下打开终端运行：
```docker compose up -d mysql redis```

### 3. 启动后端
- 激活虚拟环境，进入后端backend文件夹，打开终端运行：
```.venv\Scripts\activate```
- 启动Fast API，打开终端运行：
```uvicorn app.main:app --reload --host 127.0.0.1 --port 8000```

### 4. 启动前端
在另一个终端运行：
```
npm install   
npm run dev
```

### 5. 调试
打开浏览输入：http://localhost:5173

### 6. 停止
终端中输入：
```docker compose down```
在进程对应终端中Ctrl+C

### 7. 数据库迁移
#### Linux
- 启动MYSQL：
```
docker compose up -d mysql
chmod +x scripts/migrate.sh
```
- 开发库迁移：
```
./scripts/migrate.sh
```
为脚本赋予可执行权限后直接运行。不传参数时会自动使用默认库名 syncflow，将 scripts/init_db.sql 应用到本地开发库。
- 测试库迁移：
```
./scripts/migrate.sh --test
```
跑自动化测试或集成测试时，避免脏数据污染日常开发库。
- 需要迁移到其他库名时显示传参：
```
./scripts/migrate.sh other_db–
```
#### Windows
- 迁移主库，根目录下运行：
```
# 迁移主库 syncflow
powershell -ExecutionPolicy Bypass -File .\scripts\migrate.ps1
```
建测试库：
```
# 建测试库 syncflow_test 并灌表
powershell -ExecutionPolicy Bypass -File .\scripts\migrate.ps1 -Test
```
#### 查看库是否正确创建
- 两个库是否在：
```
docker compose exec -T mysql mysql `
  --user=$env:MYSQL_USER `
  --password=$env:MYSQL_PASSWORD `
  --host=127.0.0.1 `
  -e "SHOW DATABASES;"
```
列表里应有 syncflow 和 syncflow_test。
- 库中表是否对齐：
```
docker compose exec -T mysql mysql `
  --user=$env:MYSQL_USER `
  --password=$env:MYSQL_PASSWORD `
  --host=127.0.0.1 `
  -e "SHOW TABLES FROM $env:MYSQL_DATABASE; SHOW TABLES FROM $env:MYSQL_TEST_DATABASE;"
```
每个库都应有且只有：sync_jobs、sync_records、sync_errors
- 表结构和约束：
```
docker compose exec -T mysql mysql `
  --user=$env:MYSQL_USER `
  --password=$env:MYSQL_PASSWORD `
  --host=127.0.0.1 `
  $env:MYSQL_DATABASE `
  -e "SHOW CREATE TABLE sync_jobs\G; SHOW CREATE TABLE sync_records\G; SHOW CREATE TABLE sync_errors\G;"
```
对照检查：
| 对象 | 应该看到 |
| :--- | :--- |
| `sync_jobs` | 主键 `id`；索引 `(status, created_at)`、`(created_at)` |
| `sync_records` | `amount` 为 `decimal(12,2)`；`UNIQUE (job_id, external_id)` |
| `sync_errors` | 索引 `(job_id, row_number)`；`raw_row` 为 `json` |
| 字符集 | `DEFAULT CHARSET=utf8mb4` |
- 账号权限：
```
docker compose exec -T mysql mysql `
  --user=root `
  --password=$env:MYSQL_ROOT_PASSWORD `
  --host=127.0.0.1 `
  -e "SHOW GRANTS FOR '$($env:MYSQL_USER)'@'%';"
```
里面应有对 syncflow 和 `syncflow_test` 的授权。
- 迁移是否可重复，再运行一次：
```
powershell -ExecutionPolicy Bypass -File .\scripts\migrate.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\migrate.ps1 -Test
# Linux运行下面的命令
# ./scripts/migrate.sh
# ./scripts/migrate.sh --test
两次都应打印 migrated: syncflow / migrated: syncflow_test。然后再执行第 2 步，表还是那三张，没有多出奇怪的表。

### 8. 前端构建
终端中运行：
```
npm install
npm run build
npm run dev
```

### 7. 测试
终端中运行：
```
# API 探活
curl.exe http://127.0.0.1:8000/healthz
# 后端
cd backend
.\.venv\Scripts\Activate.ps1
pytest

# 前端
cd frontend
npm test
```

### 8. 查看日志
终端中运行：
```
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f mysql
docker compose logs -f redis
docker compose logs -f web
```

### 9. 清理数据
清楚Docker容器和数据卷，终端中运行：
```docker compose down -v```

