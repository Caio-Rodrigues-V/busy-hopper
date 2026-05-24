import os
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Agent Orchestrator"
    API_V1_STR: str = "/api/v1"
    
    # JWT Settings
    SECRET_KEY: Optional[str] = None
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # Encryption Key (Must be 32 URL-safe base64-encoded bytes)
    ENCRYPTION_KEY: Optional[str] = None
    
    # Database URL. Defaults to PostgreSQL (using pooler port or local postgres)
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/postgres"
    
    # LLM API keys
    ANTHROPIC_API_KEY: Optional[str] = None
    
    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"]

    # LLM pricing rates (per 1,000,000 tokens)
    LLM_RATES: dict = {
        "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
        "claude-3-5-sonnet-latest": {"input": 3.0, "output": 15.0},
        "claude-3-opus-20240229": {"input": 15.0, "output": 75.0},
        "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    }

    # Delegation limit and cycle settings
    MAX_DELEGATION_DEPTH: int = 5

    # Reaper and orphan run timeout
    ORPHAN_RUN_TIMEOUT_MINUTES: int = 10

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

    def model_post_init(self, __context):
        import sys
        is_test = "pytest" in sys.modules or os.getenv("ENV") == "test"

        if is_test:
            if not self.SECRET_KEY:
                self.SECRET_KEY = "test_secret_key_jwt_dev_only_not_secure_12345"
            if not self.ENCRYPTION_KEY:
                self.ENCRYPTION_KEY = "8lqWc_wA-p5HcrgC5lV4TfV3r4f7h9L3t9u3j2m1G4c="
            self.DATABASE_URL = "sqlite+aiosqlite:///./test_temp.db"
        else:
            if not self.SECRET_KEY:
                raise ValueError("CRITICAL SECURITY ERROR: SECRET_KEY must be configured in environment!")
            if not self.ENCRYPTION_KEY:
                raise ValueError("CRITICAL SECURITY ERROR: ENCRYPTION_KEY must be configured in environment!")
            if self.SECRET_KEY == "super_secret_jwt_key_for_local_dev_change_me_in_production_12345":
                # Warn or raise on weak key if in production
                is_production = os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("ENV") == "production"
                if is_production:
                    raise ValueError("CRITICAL SECURITY ERROR: SECRET_KEY must be overridden in production!")
            if self.ENCRYPTION_KEY == "8lqWc_wA-p5HcrgC5lV4TfV3r4f7h9L3t9u3j2m1G4c=":
                is_production = os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("ENV") == "production"
                if is_production:
                    raise ValueError("CRITICAL SECURITY ERROR: ENCRYPTION_KEY must be overridden in production!")

        # Resolve relative SQLite path to absolute path relative to the backend root directory
        if self.DATABASE_URL.startswith("sqlite+aiosqlite:///./"):
            backend_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            db_name = self.DATABASE_URL.replace("sqlite+aiosqlite:///./", "")
            db_path = os.path.abspath(os.path.join(backend_root, db_name))
            self.DATABASE_URL = f"sqlite+aiosqlite:///{db_path.replace('\\', '/')}"
        elif self.DATABASE_URL.startswith("postgresql://"):
            self.DATABASE_URL = self.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif self.DATABASE_URL.startswith("postgres://"):
            self.DATABASE_URL = self.DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

settings = Settings()
