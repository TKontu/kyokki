import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    POSTGRES_SERVER: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    DATABASE_URL: str

    REDIS_HOST: str
    REDIS_PORT: int

    OLLAMA_HOST: str

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'

settings = Settings()
