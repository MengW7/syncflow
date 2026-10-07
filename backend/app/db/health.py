from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.core.config import settings

# 探针不用 session.engine。卡住的连接不能占业务池；
# Windows 对不可达主机名的 DNS 还会忽略驱动超时，调用方用线程截止时间兜底。


def mysql_status(timeout_seconds: float = 2) -> str:
    timeout = int(timeout_seconds)
    probe = create_engine(
        settings.mysql_dsn,
        poolclass=NullPool,
        connect_args={
            "connect_timeout": timeout,
            "read_timeout": timeout,
            "write_timeout": timeout,
        },
    )
    try:
        with probe.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "unavailable"
    finally:
        probe.dispose()
