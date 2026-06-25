import os
from pathlib import Path
from pydantic import BaseSettings, Field, validator

class Settings(BaseSettings):
    # Core settings
    PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
    
    # Database
    DATABASE_URL: str = Field(..., env="DATABASE_URL")
    
    # JWT
    JWT_SECRET_KEY: str = Field("default_jwt_secret_change_me_please!", env="JWT_SECRET_KEY")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(60, env="ACCESS_TOKEN_EXPIRE_MINUTES")
    
    # Admin password (plain for demo; in production hash & store securely)
    ADMIN_PASSWORD: str = Field("SecureAdminTest2026!", env="ADMIN_PASSWORD")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# Singleton settings instance
settings = Settings()
