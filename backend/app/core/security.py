import logging
from datetime import datetime, timedelta
from typing import Any, Union
from cryptography.fernet import Fernet
from jose import jwt
import bcrypt
from app.core.config import settings

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Fernet setup for symmetric encryption of API keys
try:
    fernet = Fernet(settings.ENCRYPTION_KEY.encode())
except Exception as e:
    logger.error(f"Failed to load ENCRYPTION_KEY. Generating a temporary one. Credentials will not persist across restarts: {e}")
    temp_key = Fernet.generate_key()
    fernet = Fernet(temp_key)

ALGORITHM = "HS256"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')

def create_access_token(subject: Union[str, Any], expires_delta: timedelta = None) -> str:
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def encrypt_key(plain_key: str) -> str:
    """Encrypts an API key using Fernet."""
    if not plain_key:
        return ""
    return fernet.encrypt(plain_key.encode()).decode()

def decrypt_key(encrypted_key: str) -> str:
    """Decrypts an API key back to plain text."""
    if not encrypted_key:
        return ""
    try:
        return fernet.decrypt(encrypted_key.encode()).decode()
    except Exception as e:
        logger.error(f"Failed to decrypt key: {e}")
        raise ValueError("Decryption failed. Invalid encryption key or corrupted data.")
