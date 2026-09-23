import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Force load .env into os.environ so LangChain can see GEMINI_API_KEY
load_dotenv()

class Settings(BaseSettings):
    PROJECT_NAME: str = "Fin Mind"
    API_V1_STR: str = "/api/v1"
    
    # Database
    DATABASE_URL: str = "sqlite:///./finmind.db"
    
    # Auth & JWT
    SECRET_KEY: str = "temporary-dev-jwt-secret-key-change-in-prod"  # For JWT signing
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # AES-256-GCM Master Key (MUST be exactly 32 bytes for AES-256, base64 encoded)
    # Default is for dev only. Production MUST inject via env.
    FINMIND_MASTER_KEY: str = os.getenv("FINMIND_MASTER_KEY", "MTIzNDU2Nzg5MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTI=")

    # External APIs
    GEMINI_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    FRED_API_KEY: str | None = None

    # Tiered Rate Limiting Configuration
    RATE_LIMIT_AUTH: str = os.getenv("RATE_LIMIT_AUTH", "5/minute")
    RATE_LIMIT_PUBLIC: str = os.getenv("RATE_LIMIT_PUBLIC", "30/minute")
    RATE_LIMIT_AUTHENTICATED: str = os.getenv("RATE_LIMIT_AUTHENTICATED", "60/minute")
    RATE_LIMIT_CHAT: str = os.getenv("RATE_LIMIT_CHAT", "20/minute")
    
    # Auth Exponential Backoff Settings
    AUTH_EXPONENTIAL_BACKOFF_BASE_SECONDS: int = int(os.getenv("AUTH_EXPONENTIAL_BACKOFF_BASE_SECONDS", "2"))
    AUTH_MAX_FAILURES_BEFORE_BACKOFF: int = int(os.getenv("AUTH_MAX_FAILURES_BEFORE_BACKOFF", "5"))
    AUTH_MAX_BACKOFF_SECONDS: int = int(os.getenv("AUTH_MAX_BACKOFF_SECONDS", "60"))


    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
