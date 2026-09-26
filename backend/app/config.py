from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"


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
    redis_addr: str = "redis:6379"


settings = Settings()