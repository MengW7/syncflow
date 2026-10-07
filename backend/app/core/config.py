from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ROOT_ENV if _ROOT_ENV.is_file() else None,
        extra="ignore",
    )

    mysql_host: str = "mysql"
    mysql_port: int = 3306
    mysql_database: str = "syncflow"
    mysql_user: str = "syncflow"
    mysql_password: str = "syncflow123"
    mysql_test_database: str = "syncflow_test"

    redis_addr: str = "redis:6379"

    # 创建任务
    max_upload_file_size_mb: int = 10
    # 受控目录
    upload_dir: str = "/data/uploads"
    # Redis list
    job_queue_key: str = "syncflow:jobs"

    def mysql_dsn_for(self, database: str | None = None) -> str:
        user = quote_plus(self.mysql_user)
        password = quote_plus(self.mysql_password)
        name = quote_plus(database or self.mysql_database)
        return (
            f"mysql+pymysql://{user}:{password}"
            f"@{self.mysql_host}:{self.mysql_port}/{name}?charset=utf8mb4"
        )

    @property
    def mysql_dsn(self) -> str:
        return self.mysql_dsn_for()


settings = Settings()