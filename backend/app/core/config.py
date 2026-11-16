from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "local"
    database_url: str = "postgresql+psycopg://cierre:cierre@localhost:5432/cierre"
    rabbitmq_url: str = "amqp://cierre:cierre@localhost:5672//"
    # Zona horaria del negocio: Beat dispara el cierre el día 1 en hora argentina.
    business_timezone: str = "America/Argentina/Buenos_Aires"


@lru_cache
def get_settings() -> Settings:
    return Settings()
