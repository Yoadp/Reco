from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://reco:reco@localhost:5432/reco"
    redis_url: str = "redis://localhost:6379"
    secret_key: str = "change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 days

    google_places_api_key: str = ""
    yelp_api_key: str = ""
    gemini_api_key: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
