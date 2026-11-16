from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "local"
    database_url: str = "postgresql+psycopg://wallbit:wallbit@localhost:5432/wallbit"
    rabbitmq_url: str = "amqp://wallbit:wallbit@localhost:5672//"
    # Business timezone: Beat starts the close on day 1, Argentina time.
    business_timezone: str = "America/Argentina/Buenos_Aires"


@lru_cache
def get_settings() -> Settings:
    return Settings()
