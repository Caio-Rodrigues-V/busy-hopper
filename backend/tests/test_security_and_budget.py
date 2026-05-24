import pytest
import os
import sys
from datetime import datetime

# Set pythonpath
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.security import get_password_hash, verify_password, encrypt_key, decrypt_key, create_access_token
from app.services.agent_executor import estimate_cost

def test_password_hashing():
    pwd = "my_secure_board_password_123"
    hashed = get_password_hash(pwd)
    
    assert hashed != pwd
    assert verify_password(pwd, hashed) is True
    assert verify_password("wrong_password", hashed) is False

def test_key_encryption_decryption():
    secret_api_key = "sk-ant-api03-samplekey1234567890abcdef"
    encrypted = encrypt_key(secret_api_key)
    
    assert encrypted != secret_api_key
    assert len(encrypted) > 0
    
    decrypted = decrypt_key(encrypted)
    assert decrypted == secret_api_key

def test_jwt_token_flow():
    user_id = 42
    token = create_access_token(subject=user_id)
    
    assert token is not None
    assert isinstance(token, str)

def test_cost_estimation_rates():
    # Sonnet rate check
    sonnet_cost = estimate_cost("claude-3-5-sonnet-20241022", 1000, 500)
    # Rate: 3.0 / million input, 15.0 / million output
    # Input cost: 1000 * 0.000003 = 0.003
    # Output cost: 500 * 0.000015 = 0.0075
    # Total: 0.0105
    assert abs(sonnet_cost - 0.0105) < 1e-6
    
    # Opus rate check
    opus_cost = estimate_cost("claude-3-opus-20240229", 1000, 500)
    # Rate: 15.0 / million input, 75.0 / million output
    # Input cost: 1000 * 0.000015 = 0.015
    # Output cost: 500 * 0.000075 = 0.0375
    # Total: 0.0525
    assert abs(opus_cost - 0.0525) < 1e-6
