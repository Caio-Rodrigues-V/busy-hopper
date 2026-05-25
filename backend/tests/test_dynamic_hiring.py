import pytest
import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

# Set pythonpath
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select
from app.core.database import Base, engine, SessionLocal
from app.models.user import User
from app.models.company import Company
from app.models.agent import Agent
from app.models.task import Task
from app.models.run import Run, RunStep
from app.models.approval import Approval
from app.models.api_credential import ApiCredential
from app.services.agent_executor import AgentExecutor

@pytest.fixture(autouse=True, scope="function")
async def setup_db():
    """Fixture to automatically create and drop tables for each test function."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

async def create_test_setup(db):
    """Utility to seed basic user, company, and CEO agent."""
    user = User(email="ceo_tester@user.com", password_hash="dummy_hash")
    db.add(user)
    await db.commit()
    await db.refresh(user)

    company = Company(
        user_id=user.id,
        name="CEO Enterprise Inc",
        mission="Automate and grow business",
        monthly_budget_usd=100.0,
        markup_pct=0.0
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)

    # CEO Agent with hire_agent permission
    ceo = Agent(
        company_id=company.id,
        name="Sophia CEO",
        title="CEO",
        role_prompt="You manage operations.",
        adapter_type="claude",
        model="claude-3-5-sonnet-20241022",
        temperature=0.0,
        tools=["hire_agent", "request_approval"],
        monthly_budget_usd=50.0,
        status="active"
    )
    db.add(ceo)
    await db.commit()
    await db.refresh(ceo)

    # API Credential
    cred = ApiCredential(
        company_id=company.id,
        provider="anthropic",
        encrypted_key="mock_key_encrypted",
        last4="mock"
    )
    db.add(cred)
    await db.commit()
    await db.refresh(cred)

    return user, company, ceo

@pytest.mark.asyncio
async def test_dynamic_hiring_flow():
    async with SessionLocal() as db:
        user, company, ceo = await create_test_setup(db)

        # Create CEO task
        task = Task(
            company_id=company.id,
            title="Expand Content Team",
            description="Hire a copywriter to draft the ads",
            assignee_agent_id=ceo.id,
            status="todo"
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)

    # Mock the LLM to output a tool call to hire an agent
    from app.services.agent_executor import AdapterResponse, AdapterResponseBlock, AdapterUsage
    
    mock_tool_use = AdapterResponseBlock(
        block_type="tool_use",
        tool_use_id="toolu_hire_001",
        name="hire_agent",
        tool_input={
            "name": "CopywriterBot",
            "title": "Copywriter Manager",
            "role_prompt": "You write ads copy.",
            "model": "gpt-4o-mini",
            "temperature": 0.2,
            "monthly_budget_usd": 20.0,
            "tools": ["read_write_file"]
        }
    )
    
    mock_llm_response = AdapterResponse(
        content=[
            AdapterResponseBlock(block_type="text", text="I will hire a CopywriterBot to help write copies."),
            mock_tool_use
        ],
        stop_reason="tool_use",
        usage=AdapterUsage(input_tokens=100, output_tokens=50)
    )

    async with SessionLocal() as db:
        # Patch the LLM messages create call
        with patch("app.services.agent_executor.AgentExecutor._get_anthropic_key", return_value="mock_key"), \
             patch("app.services.agent_executor.AgentExecutor._messages_create", return_value=mock_llm_response):
            
            executor = AgentExecutor(db, company.id, ceo.id, task.id)
            res = await executor.execute_run()

            # 1. Verify loop paused for approval
            assert "paused for board approval" in res.lower()

            # 2. Check task status and active runs
            task = await db.get(Task, task.id)
            assert task.status == "paused"

            # 3. Verify approval ticket was created
            approvals_query = select(Approval).filter(Approval.company_id == company.id)
            approvals = (await db.execute(approvals_query)).scalars().all()
            assert len(approvals) == 1
            
            approval = approvals[0]
            assert approval.action_type == "hire_agent"
            assert approval.status == "pending"
            assert approval.payload["name"] == "CopywriterBot"
            assert approval.payload["tools"] == ["read_write_file"]

            # 4. Approve the ticket
            approval.status = "approved"
            db.add(approval)
            await db.commit()

            # 5. Mock the LLM follow-up response after approval completion
            mock_followup = AdapterResponse(
                content=[AdapterResponseBlock(block_type="text", text="The CopywriterBot has been successfully hired. I will now conclude the task.")],
                stop_reason="end_turn",
                usage=AdapterUsage(input_tokens=200, output_tokens=30)
            )

            with patch("app.services.agent_executor.AgentExecutor._messages_create", return_value=mock_followup):
                # Resume execution
                res_resume = await executor.resume_run(approval.id)
                assert "conclude the task" in res_resume.lower()

                # 6. Check that the CopywriterBot agent was successfully inserted in the database
                agent_query = select(Agent).filter(Agent.company_id == company.id, Agent.name == "CopywriterBot")
                new_agent = (await db.execute(agent_query)).scalars().first()
                
                assert new_agent is not None
                assert new_agent.name == "CopywriterBot"
                assert new_agent.title == "Copywriter Manager"
                assert new_agent.boss_agent_id == ceo.id
                assert new_agent.adapter_type == "openai" # Derived from model gpt-4o-mini
                assert new_agent.model == "gpt-4o-mini"
                assert new_agent.monthly_budget_usd == 20.0
                assert new_agent.tools == ["read_write_file"]
                assert new_agent.status == "active"
