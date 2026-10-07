from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.core.config import settings


def create_mysql_engine(database: str | None = None) -> Engine:
    """按配置建立连接池。database 为空时用 MYSQL_DATABASE，测试可传入 MYSQL_TEST_DATABASE。"""
    return create_engine(
        settings.mysql_dsn_for(database),
        pool_pre_ping=True,
        pool_recycle=3600,
        connect_args={"connect_timeout": 10},
    )


engine = create_mysql_engine()


def get_engine() -> Engine:
    return engine
