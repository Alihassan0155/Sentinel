from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    gemini_api_key: str
    gemini_model: str = "gemini-2.5-flash-lite"
    embedding_model: str = "gemini-embedding-001"
    investigation_threshold: int = Field(default=70, ge=0, le=100)

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
