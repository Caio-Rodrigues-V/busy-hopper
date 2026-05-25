import pytest
import os
import sys
import json
from unittest.mock import AsyncMock, patch

# Set pythonpath
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select
from app.core.database import Base, engine, SessionLocal
from app.models.user import User
from app.models.company import Company
from app.models.agent import Agent
from app.api.agents import import_openclaw_agent

@pytest.fixture(autouse=True, scope="function")
async def setup_db():
    """Fixture to automatically create and drop tables for each test function."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

async def create_test_setup(db):
    """Utility to seed basic user and company."""
    user = User(email="openclaw_tester@user.com", password_hash="dummy_hash")
    db.add(user)
    await db.commit()
    await db.refresh(user)

    company = Company(
        user_id=user.id,
        name="Claw Company",
        mission="Test OpenClaw Imports",
        monthly_budget_usd=100.0,
        markup_pct=0.0
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return user, company

@pytest.mark.asyncio
async def test_import_openclaw_agent_direct_root():
    async with SessionLocal() as db:
        user, company = await create_test_setup(db)
        
        # Payload with direct root config
        payload = {
            "name": "Social Media Manager",
            "role": "Marketing Assistant",
            "system_prompt": "Craft and schedule engaging social media posts",
            "model": "gpt-4o-mini",
            "temperature": 0.5,
            "monthly_budget_usd": 30.0,
            "allowed_tools": ["web", "image", "file"]
        }
        
        # Mock WebSocket broadcast
        with patch("app.services.websocket_manager.manager.broadcast_to_company", new_callable=AsyncMock) as mock_broadcast:
            agent = await import_openclaw_agent(
                payload=payload,
                db=db,
                company=company,
                current_user=user
            )
            
            assert agent.name == "Social Media Manager"
            assert agent.title == "Marketing Assistant"
            assert agent.role_prompt == "Craft and schedule engaging social media posts"
            assert agent.model == "gpt-4o-mini"
            assert agent.temperature == 0.5
            assert agent.monthly_budget_usd == 30.0
            
            # Tools mapping checks:
            # "web" -> "web_search"
            # "image" -> "generate_image_asset"
            # "file" -> "read_write_file"
            # Plus default safety tools: "delegate_task", "request_approval"
            assert "web_search" in agent.tools
            assert "generate_image_asset" in agent.tools
            assert "read_write_file" in agent.tools
            assert "delegate_task" in agent.tools
            assert "request_approval" in agent.tools
            assert len(agent.tools) == 5
            
            mock_broadcast.assert_called_once_with(company.id, {"type": "org_updated"})

@pytest.mark.asyncio
async def test_import_openclaw_agent_nested_gateway():
    async with SessionLocal() as db:
        user, company = await create_test_setup(db)
        
        # Payload with nested "gateway" key
        payload = {
            "openclaw_config": {
                "gateway": {
                    "name": "SysAdmin Agent",
                    "system_prompt": "Run server maintenance tasks.",
                    "model": "claude-3-5-sonnet-20241022",
                    "allowed_tools": ["shell"]
                }
            }
        }
        
        with patch("app.services.websocket_manager.manager.broadcast_to_company", new_callable=AsyncMock) as mock_broadcast:
            agent = await import_openclaw_agent(
                payload=payload,
                db=db,
                company=company,
                current_user=user
            )
            
            assert agent.name == "SysAdmin Agent"
            assert agent.title == "OpenClaw Assistant" # falls back to default title
            assert agent.role_prompt == "Run server maintenance tasks."
            assert agent.model == "claude-3-5-sonnet-20241022"
            assert "run_bash_command" in agent.tools # shell -> run_bash_command
            assert "delegate_task" in agent.tools
            assert "request_approval" in agent.tools
            assert len(agent.tools) == 3
            
            mock_broadcast.assert_called_once_with(company.id, {"type": "org_updated"})
