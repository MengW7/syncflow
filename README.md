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

