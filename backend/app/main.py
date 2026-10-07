import logging
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import redis
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.responses import fail
from app.api.router import api_router
from app.core.config import settings
from app.core.errors import AppError
from app.db.health import mysql_status
from app.db.session import engine

logger = logging.getLogger(__name__)

_CHECK_TIMEOUT_SECONDS = 2


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    yield
    engine.dispose()


app = FastAPI(title="SyncFlow API", version="0.1.0", lifespan=_lifespan)
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 捕获自定义领域异常 AppError
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.http_status,
        content=fail(code=exc.code, message=exc.message, details=exc.details),
    )


# 捕获请求验证错误
@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content=fail(
            code="INVALID_REQUEST",
            message="请求参数验证失败",
            details=exc.errors(),
        ),
    )


# 捕获未处理的异常
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled server error: %s", exc)
    return JSONResponse(
        status_code=500,
        content=fail(
            code="INTERNAL_ERROR",
            message="服务器内部错误",
        ),
    )


def _redis_status() -> str:
    try:
        addr = settings.redis_addr.strip()
        host, sep, port_text = addr.rpartition(":")
        if not sep:
            host = addr
            port = 6379
        else:
            port = int(port_text)
        client = redis.Redis(
            host=host,
            port=port,
            socket_connect_timeout=_CHECK_TIMEOUT_SECONDS,
            socket_timeout=_CHECK_TIMEOUT_SECONDS,
        )
        try:
            if not client.ping():
                return "unavailable"
        finally:
            client.close()
        return "ok"
    except Exception:
        return "unavailable"


@app.get("/healthz")
def healthz():
    return {
        "data": {
            "status": "ok",
            "service": "api",
            "time": datetime.now(timezone.utc).isoformat(),
        },
        "meta": {},
    }


def _dependency_checks() -> dict[str, str]:
    probes = {
        "mysql": lambda: mysql_status(_CHECK_TIMEOUT_SECONDS),
        "redis": _redis_status,
    }
    results: dict[str, str | None] = {name: None for name in probes}

    def run(name: str, probe) -> None:
        results[name] = probe()

    threads = []
    for name, probe in probes.items():
        thread = threading.Thread(target=run, args=(name, probe), daemon=True)
        thread.start()
        threads.append(thread)
    deadline = time.monotonic() + _CHECK_TIMEOUT_SECONDS
    for thread in threads:
        remaining = deadline - time.monotonic()
        if remaining > 0:
            thread.join(remaining)
    return {name: status or "unavailable" for name, status in results.items()}


@app.get("/readyz")
def readyz():
    checks = _dependency_checks()
    if all(status == "ok" for status in checks.values()):
        return {
            "data": {
                "status": "ok",
                "service": "api",
                "checks": checks,
            },
            "meta": {},
        }
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "NOT_READY",
                "message": "依赖不可用",
                "details": checks,
            }
        },
    )