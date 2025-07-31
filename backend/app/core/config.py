from pydantic_settings import BaseSettings
from pydantic import computed_field

class Settings(BaseSettings):
    POSTGRES_SERVER: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str

    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}/{self.POSTGRES_DB}"

    REDIS_HOST: str
    REDIS_PORT: int = 6379

    OLLAMA_HOST: str

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'

settings = Settings()