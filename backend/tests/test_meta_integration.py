import pytest
import os
import sys
import json
import tempfile
import shutil
from datetime import datetime

# Set pythonpath
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.security import encrypt_key, decrypt_key
from app.models.api_credential import ApiCredential

def test_meta_config_json_encryption():
    # Simulate the frontend sending multiple fields
    config_payload = {
        "access_token": "EAAGb-token-123-xyz",
        "ad_account_id": "1029384756",
        "page_id": "9876543210",
        "pixel_id": "5432109876"
      }
    
    # Serialize to JSON
    serialized = json.dumps(config_payload)
    
    # Encrypt
    encrypted = encrypt_key(serialized)
    assert encrypted != serialized
    assert len(encrypted) > 0
    
    # Decrypt and parse
    decrypted = decrypt_key(encrypted)
    parsed = json.loads(decrypted)
    
    assert parsed["access_token"] == "EAAGb-token-123-xyz"
    assert parsed["ad_account_id"] == "1029384756"
    assert parsed["page_id"] == "9876543210"
    assert parsed["pixel_id"] == "5432109876"

def test_simulated_meta_campaign_file_creation():
    # Setup temporary workspace
    temp_dir = tempfile.mkdtemp()
    try:
        campaign_name = "Black Friday Traffic Burst"
        objective = "CONVERSIONS"
        budget = 50.0
        ad_account_id = "12345"
        page_id = "67890"
        
        filename = f"manual_meta_campaign_test.json"
        target_path = os.path.join(temp_dir, filename)
        
        campaign_data = {
            "campaign_name": campaign_name,
            "objective": objective,
            "daily_budget_usd": budget,
            "status": "ACTIVE",
            "facebook_campaign_id": f"act_{ad_account_id}/camp_test",
            "deployed_at": datetime.utcnow().isoformat(),
            "ad_account_id": ad_account_id,
            "page_id": page_id,
            "mode": "MANUAL_DEPLOY"
        }
        
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(campaign_data, f, indent=2)
            
        # Verify file exists and holds correct data
        assert os.path.exists(target_path)
        with open(target_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            assert loaded["campaign_name"] == campaign_name
            assert loaded["objective"] == objective
            assert loaded["daily_budget_usd"] == budget
            assert loaded["facebook_campaign_id"] == f"act_{ad_account_id}/camp_test"
            
    finally:
        shutil.rmtree(temp_dir)

def test_svg_image_banner_generation():
    # Test SVG generator template syntax
    prompt = "Ad creative image prompt for conversion sales"
    filename = "creative_banner.svg"
    
    selected_gradient = '<linearGradient id="gradient-bg" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#4F46E5"/><stop offset="100%" stop-color="#EC4899"/></linearGradient>'
    
    svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 500" width="100%" height="100%">
  <defs>
    {selected_gradient}
    <filter id="glass-blur" x="-10%" y="-10%" width="120%" height="120%">
      <feDropShadow dx="0" dy="12" stdDeviation="8" flood-color="#000" flood-opacity="0.35"/>
    </filter>
  </defs>
  <rect width="800" height="500" rx="16" fill="url(#gradient-bg)"/>
  <circle cx="150" cy="120" r="180" fill="#ffffff" fill-opacity="0.08"/>
  <circle cx="680" cy="380" r="220" fill="#ffffff" fill-opacity="0.06"/>
  <rect x="120" y="100" width="560" height="300" rx="20" fill="#ffffff" fill-opacity="0.12" stroke="#ffffff" stroke-width="1" stroke-opacity="0.25"/>
  <text x="400" y="210" font-family="sans-serif" font-size="28" fill="#ffffff" text-anchor="middle">HIGH-CONVERTING AD BANNER</text>
  <text x="400" y="255" font-family="sans-serif" font-size="13" fill="#E2E8F0" text-anchor="middle">"{prompt[:70]}"</text>
</svg>"""
    
    assert "<svg" in svg_content
    assert "</svg>" in svg_content
    assert prompt in svg_content
    assert filename not in svg_content

@pytest.mark.asyncio
async def test_real_campaign_listing_and_parsing():
    from app.api.meta import list_meta_campaigns
    from unittest.mock import AsyncMock, MagicMock, patch
    
    # Mock company object
    mock_company = MagicMock()
    mock_company.id = 1
    
    # Mock db session
    mock_db = AsyncMock()
    mock_result = MagicMock()
    
    # Mock credential record
    mock_cred = MagicMock()
    from app.core.security import encrypt_key
    mock_cred.encrypted_key = encrypt_key(json.dumps({
        "access_token": "EAA_test_token",
        "ad_account_id": "123456"
    }))
    
    mock_result.scalars.return_value.first.return_value = mock_cred
    mock_db.execute.return_value = mock_result
    
    # Mock HTTP response
    mock_response_data = {
        "data": [
            {
                "id": "120202020",
                "name": "Conversion Ad Set Test",
                "objective": "OUTCOMES",
                "daily_budget": "5000",
                "status": "ACTIVE",
                "created_time": "2026-05-25T12:00:00+0000",
                "insights": {
                    "data": [
                        {
                            "spend": "45.50",
                            "impressions": "15000",
                            "clicks": "450",
                            "ctr": "3.0",
                            "conversions": "15",
                            "actions": [
                                {
                                    "action_type": "omni_purchase",
                                    "value": "150.0"
                                }
                            ]
                        }
                    ]
                }
            }
        ]
    }
    
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: mock_response_data
        )
        
        campaigns = await list_meta_campaigns(db=mock_db, company=mock_company)
        
        assert len(campaigns) == 1
        campaign = campaigns[0]
        assert campaign["campaign_name"] == "Conversion Ad Set Test"
        assert campaign["objective"] == "OUTCOMES"
        assert campaign["daily_budget_usd"] == 50.0
        assert campaign["total_spent"] == 45.50
        assert campaign["impressions"] == 15000
        assert campaign["clicks"] == 450
        assert campaign["ctr"] == 3.0
        assert campaign["conversions"] == 15
        assert abs(campaign["roas"] - (150.0 / 45.50)) < 0.001
        assert campaign["health"] == "Excellent"
        assert campaign["status"] == "ACTIVE"

