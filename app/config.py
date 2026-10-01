from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    gemini_api_key: str
    gemini_model: str = "gemini-2.5-flash-lite"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()