import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


class Settings:
    APP_NAME: str = os.getenv("APP_NAME", "NexusAI: Smart Inventory Engine")
    APP_VERSION: str = os.getenv("APP_VERSION", "2.1.0")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

    ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "admin@nexusai.com")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "SecureAdminTest2026!")
    ADMIN_FULL_NAME: str = os.getenv("ADMIN_FULL_NAME", "Senior Administrator")

    MANAGER_EMAIL: str = os.getenv("MANAGER_EMAIL", "manager@nexusai.com")
    MANAGER_PASSWORD: str = os.getenv("MANAGER_PASSWORD", "manager123")
    MANAGER_FULL_NAME: str = os.getenv("MANAGER_FULL_NAME", "Inventory Manager")

    GUEST_EMAIL: str = os.getenv("GUEST_EMAIL", "guest@nexusai.com")
    GUEST_PASSWORD: str = os.getenv("GUEST_PASSWORD", "guestpassword")
    GUEST_FULL_NAME: str = os.getenv("GUEST_FULL_NAME", "Premium Guest")

    LOW_STOCK_THRESHOLD: int = int(os.getenv("LOW_STOCK_THRESHOLD", "15"))
    SEED_PRODUCT_COUNT: int = int(os.getenv("SEED_PRODUCT_COUNT", "100"))
    PRODUCTS_PER_PAGE: int = int(os.getenv("PRODUCTS_PER_PAGE", "12"))

    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "300"))

    MAX_LOGIN_ATTEMPTS: int = int(os.getenv("MAX_LOGIN_ATTEMPTS", "5"))
    LOCKOUT_MINUTES: int = int(os.getenv("LOCKOUT_MINUTES", "15"))

    RATE_LIMIT_LOGIN: str = os.getenv("RATE_LIMIT_LOGIN", "10/minute")
    RATE_LIMIT_SIGNUP: str = os.getenv("RATE_LIMIT_SIGNUP", "5/minute")

    PASSWORD_RESET_EXPIRE_MINUTES: int = int(os.getenv("PASSWORD_RESET_EXPIRE_MINUTES", "30"))

    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama3-8b-8192")
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3")


    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "noreply@nexusai.com")
    SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    APP_BASE_URL: str = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000")

    def validate_required(self) -> None:
        missing: list[str] = []
        if not self.JWT_SECRET_KEY or len(self.JWT_SECRET_KEY) < 32:
            missing.append("JWT_SECRET_KEY (min 32 characters)")
        if missing:
            raise RuntimeError(
                "Missing required environment variables: "
                + ", ".join(missing)
                + ". Copy .env.example to .env and configure values."
            )

@lru_cache
def get_settings() -> Settings:
    return Settings()
