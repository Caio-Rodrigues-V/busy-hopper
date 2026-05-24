import os
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Agent Orchestrator"
    API_V1_STR: str = "/api/v1"
    
    # JWT Settings
    SECRET_KEY: str = "super_secret_jwt_key_for_local_dev_change_me_in_production_12345"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # Encryption Key (Must be 32 URL-safe base64-encoded bytes)
    # Default is a pre-generated valid key for development.
    ENCRYPTION_KEY: str = "8lqWc_wA-p5HcrgC5lV4TfV3r4f7h9L3t9u3j2m1G4c="
    
    # Database URL. If using supabase, should be postgresql+asyncpg://...
    DATABASE_URL: str = "sqlite+aiosqlite:///./orchestrator.db"
    
    # LLM API keys
    ANTHROPIC_API_KEY: Optional[str] = None
    
    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"]

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

    def model_post_init(self, __context):
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
