from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    GEOAPIFY_API_KEY: str

    class Config:
        # Load .env file if present
        env_file = '.env'
        env_file_encoding = 'utf-8'

# Use lru_cache to load settings only once
@lru_cache()
def get_settings():
    return Settings()
