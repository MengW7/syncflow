from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mysql_host: str = "mysql"
    mysql_port: int = 3306
    mysql_database: str = "syncflow"
    mysql_user: str = "syncflow"
    mysql_password: str = "syncflow123"
    redis_addr: str = "redis:6379"


settings = Settings()