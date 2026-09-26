import threading
import time
from datetime import datetime, timezone

import pymysql
import redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings

_CHECK_TIMEOUT_SECONDS = 2

app = FastAPI(title="SyncFlow API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _mysql_status() -> str:
    try:
        conn = pymysql.connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_database,
            connect_timeout=_CHECK_TIMEOUT_SECONDS,
            read_timeout=_CHECK_TIMEOUT_SECONDS,
            write_timeout=_CHECK_TIMEOUT_SECONDS,
        )
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
        finally:
            conn.close()
        return "ok"
    except Exception:
        return "unavailable"


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
    probes = {"mysql": _mysql_status, "redis": _redis_status}
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