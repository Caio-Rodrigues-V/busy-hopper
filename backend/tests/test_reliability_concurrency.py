import pytest
import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

# Set pythonpath
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import Base, engine, SessionLocal
from app.models.user import User
from app.models.company import Company
from app.models.agent import Agent
from app.models.task import Task
from app.models.run import Run, RunStep
from app.models.approval import Approval
from app.models.api_credential import ApiCredential
from app.services.agent_executor import AgentExecutor
from app.core.config import settings
from fastapi import HTTPException

@pytest.fixture(autouse=True, scope="function")
async def setup_db():
    """Fixture to automatically create and drop tables for each test function."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

async def create_test_setup(db):
    """Utility to seed basic user, company, and agents."""
    user = User(email="test@user.com", password_hash="dummy_hash")
    db.add(user)
    await db.commit()
    await db.refresh(user)

    company = Company(
        user_id=user.id,
        name="Test Corp",
        mission="Test corporate mission",
        monthly_budget_usd=100.0,
        markup_pct=0.0
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)

    # Main Agent
    agent = Agent(
        company_id=company.id,
        name=" Sophia",
        title="CEO",
        role_prompt="Role prompt",
        adapter_type="claude",
        model="claude-3-5-sonnet-20241022",
        temperature=0.0,
        tools=["delegate_task", "request_approval"],
        monthly_budget_usd=50.0,
        status="active"
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)

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

    return user, company, agent

# 1. Checkout Concurrency and Active Run Locking
@pytest.mark.asyncio
async def test_concurrency_execution_locks():
    async with SessionLocal() as db:
        user, company, agent = await create_test_setup(db)
        
        # Create a single task
        task = Task(
            company_id=company.id,
            title="Clean the Workspace",
            description="Sweep the floor and organize archives.",
            assignee_agent_id=agent.id,
            status="todo"
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)

    # Run 5 concurrent execution requests for the exact same task
    # Note: they will use separate db sessions to simulate concurrent threads/workers
    async def run_executor_task(worker_id):
        async with SessionLocal() as worker_db:
            # We mock the LLM response to exit early
            with patch("app.services.agent_executor.AgentExecutor._get_anthropic_key", return_value="mock_key"):
                executor = AgentExecutor(worker_db, company.id, agent.id, task.id)
                res = await executor.execute_run()
                return worker_id, res

    results = await asyncio.gather(*(run_executor_task(i) for i in range(5)))
    
    # We expect exactly one successful start (which continues into the mock loop or finishes)
    # and the remaining 4 to return "Task already running" or "Task already claimed"
    success_runs = []
    skipped_runs = []
    for wid, res in results:
        if "already running" in res.lower() or "already claimed" in res.lower():
            skipped_runs.append((wid, res))
        else:
            success_runs.append((wid, res))

    assert len(success_runs) == 1
    assert len(skipped_runs) == 4

# 2. Budget Lock Check In-Loop
@pytest.mark.asyncio
async def test_budget_lock_mid_loop():
    async with SessionLocal() as db:
        user, company, agent = await create_test_setup(db)
        # Set agent budget very low
        agent.monthly_budget_usd = 0.05
        db.add(agent)
        
        task = Task(
            company_id=company.id,
            title="Budget Test Task",
            description="Exceed budget limits.",
            assignee_agent_id=agent.id,
            status="todo"
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)

    # We mock the API key check to succeed
    # We mock _messages_create to return a message with high token count/cost exceeding 0.05
    from anthropic.types import Message, Usage, TextBlock
    mock_msg = Message(
        id="mock_id",
        content=[TextBlock(text="We are working on this.", type="text")],
        model="claude-3-5-sonnet-20241022",
        role="assistant",
        stop_reason="end_turn",
        type="message",
        usage=Usage(input_tokens=10000, output_tokens=5000) # Cost: 10000*3/1M + 5000*15/1M = 0.03 + 0.075 = 0.105 (exceeds 0.05)
    )

    async with SessionLocal() as db:
        with patch("app.services.agent_executor.AgentExecutor._get_anthropic_key", return_value="mock_key"), \
             patch("app.services.agent_executor.AgentExecutor._messages_create", return_value=mock_msg):
            executor = AgentExecutor(db, company.id, agent.id, task.id)
            res = await executor.execute_run()

            # The loop should halt immediately on iteration step 1 and return a budget exceed message
            assert "monthly budget limit exceeded" in res.lower()
            
            # Verify that the task status is set to "paused"
            task = await db.get(Task, task.id)
            agent = await db.get(Agent, agent.id)
            assert task.status == "paused"
            assert task.locked_at is None
            assert agent.status == "exhausted"

# 3. Multi-tenant Isolation Check
@pytest.mark.asyncio
async def test_multi_tenant_isolation():
    async with SessionLocal() as db:
        # Create Company A
        user_a = User(email="usera@test.com", password_hash="hash")
        db.add(user_a)
        await db.commit()
        await db.refresh(user_a)
        company_a = Company(user_id=user_a.id, name="Company A", mission="Mission A")
        db.add(company_a)
        await db.commit()
        await db.refresh(company_a)
        agent_a = Agent(company_id=company_a.id, name="Sophia A", title="CEO", role_prompt="CEO A", adapter_type="claude")
        db.add(agent_a)
        await db.commit()
        await db.refresh(agent_a)

        # Create Company B
        user_b = User(email="userb@test.com", password_hash="hash")
        db.add(user_b)
        await db.commit()
        await db.refresh(user_b)
        company_b = Company(user_id=user_b.id, name="Company B", mission="Mission B")
        db.add(company_b)
        await db.commit()
        await db.refresh(company_b)
        agent_b = Agent(company_id=company_b.id, name="Sophia B", title="CEO", role_prompt="CEO B", adapter_type="claude")
        db.add(agent_b)
        await db.commit()
        await db.refresh(agent_b)

    # Import routes
    from app.api.agents import get_agent, create_agent
    from app.schemas.agent import AgentCreate

    # Test 3a: User B tries to view Agent A -> should fail with 404
    with pytest.raises(HTTPException) as exc_info:
        async with SessionLocal() as db:
            await get_agent(agent_id=agent_a.id, db=db, company=company_b)
    assert exc_info.value.status_code == 404

    # Test 3b: User B tries to create an agent reporting to Agent A (boss in Company A) -> should fail
    agent_in = AgentCreate(
        name="Marcus B",
        title="EM",
        role_prompt="Manager",
        boss_agent_id=agent_a.id,
        adapter_type="claude",
        model="claude-3-5-sonnet-20241022",
        temperature=0.0,
        tools=[],
        monthly_budget_usd=50.0
    )
    with pytest.raises(HTTPException) as exc_info:
        async with SessionLocal() as db:
            await create_agent(agent_in=agent_in, db=db, company=company_b, current_user=user_b)
    assert exc_info.value.status_code == 400

# 4. Anthropic API Resiliency (Mock Timeout and Retry)
@pytest.mark.asyncio
async def test_anthropic_api_retry_resiliency():
    from anthropic import RateLimitError, InternalServerError
    from anthropic.types import Message, Usage, TextBlock

    # Setup a mock client
    mock_client = AsyncMock()
    mock_msg = Message(
        id="mock_success_id",
        content=[TextBlock(text="Task completed successfully.", type="text")],
        model="claude-3-5-sonnet-20241022",
        role="assistant",
        stop_reason="end_turn",
        type="message",
        usage=Usage(input_tokens=10, output_tokens=5)
    )

    # Configure mock messages.create call to:
    # 1. Raise RateLimitError (429)
    # 2. Raise InternalServerError (500)
    # 3. Succeed with mock_msg
    import httpx
    dummy_request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    dummy_response_429 = httpx.Response(status_code=429, request=dummy_request)
    dummy_response_500 = httpx.Response(status_code=500, request=dummy_request)

    mock_response = [
        RateLimitError(message="Rate limited!", response=dummy_response_429, body=None),
        InternalServerError(message="Internal Server error!", response=dummy_response_500, body=None),
        mock_msg
    ]
    mock_client.messages.create.side_effect = mock_response

    async with SessionLocal() as db:
        user, company, agent = await create_test_setup(db)
        task = Task(company_id=company.id, title="Test retry", description="Retry task", assignee_agent_id=agent.id, status="todo")
        db.add(task)
        await db.commit()
        await db.refresh(task)

        executor = AgentExecutor(db, company.id, agent.id, task.id)
        
        # Patch sleep to speed up test execution
        with patch("asyncio.sleep", return_value=None) as mock_sleep:
            res = await executor._messages_create(
                mock_client,
                {"messages": []},
                "real_api_key_placeholder",
                agent,
                task,
                []
            )
            # Verify it succeeded eventually
            assert res.id == "mock_success_id"
            # Verify sleep was called twice (once for 429, once for 500)
            assert mock_sleep.call_count == 2

# 5. Circular Delegation and Depth Validation
@pytest.mark.asyncio
async def test_circular_delegation_and_max_depth():
    async with SessionLocal() as db:
        user, company, agent = await create_test_setup(db)
        
        # Create second agent
        agent_marcus = Agent(
            company_id=company.id,
            name="Marcus",
            title="EM",
            role_prompt="Manager",
            boss_agent_id=agent.id,
            adapter_type="claude",
            monthly_budget_usd=50.0
        )
        db.add(agent_marcus)
        await db.commit()
        await db.refresh(agent_marcus)

        # Create third agent
        agent_devbot = Agent(
            company_id=company.id,
            name="DevBot",
            title="Developer",
            role_prompt="Dev",
            boss_agent_id=agent_marcus.id,
            adapter_type="claude",
            monthly_budget_usd=50.0
        )
        db.add(agent_devbot)
        await db.commit()
        await db.refresh(agent_devbot)

        # Sophia's task
        task_sophia = Task(company_id=company.id, title="Root task", description="CEO Task", assignee_agent_id=agent.id, status="in_progress")
        db.add(task_sophia)
        await db.commit()
        await db.refresh(task_sophia)

        # Marcus's task (delegated by Sophia)
        task_marcus = Task(company_id=company.id, title="Sub task 1", description="EM Task", assignee_agent_id=agent_marcus.id, parent_task_id=task_sophia.id, status="in_progress")
        db.add(task_marcus)
        await db.commit()
        await db.refresh(task_marcus)

        # DevBot's task (delegated by Marcus)
        task_devbot = Task(company_id=company.id, title="Sub task 2", description="Dev Task", assignee_agent_id=agent_devbot.id, parent_task_id=task_marcus.id, status="in_progress")
        db.add(task_devbot)
        await db.commit()
        await db.refresh(task_devbot)

        # Executor for DevBot
        executor = AgentExecutor(db, company.id, agent_devbot.id, task_devbot.id)

        # Test 5a: Self-delegation check
        res_self = await executor._tool_delegate_task({"title": "Self task", "description": "Delegating to myself", "assignee_agent_id": agent_devbot.id})
        assert "Circular delegation detected. An agent cannot delegate a task to themselves" in res_self

        # Test 5b: Circular delegation walk checking (DevBot -> Marcus or DevBot -> Sophia)
        res_cycle = await executor._tool_delegate_task({"title": " EM Help", "description": "Delegating back up to EM", "assignee_agent_id": agent_marcus.id})
        assert "Circular delegation detected. Agent" in res_cycle

        res_cycle_ceo = await executor._tool_delegate_task({"title": "CEO Help", "description": "Delegating back up to CEO", "assignee_agent_id": agent.id})
        assert "Circular delegation detected. Agent" in res_cycle_ceo

        # Test 5c: Delegation depth limit
        # Chain of 5 deep tasks (Sophia task is depth 1, Marcus is 2, DevBot is 3)
        task_depth_4 = Task(company_id=company.id, title="Depth 4", description="D4", assignee_agent_id=agent.id, parent_task_id=task_devbot.id, status="in_progress")
        db.add(task_depth_4)
        await db.commit()
        await db.refresh(task_depth_4)

        task_depth_5 = Task(company_id=company.id, title="Depth 5", description="D5", assignee_agent_id=agent_marcus.id, parent_task_id=task_depth_4.id, status="in_progress")
        db.add(task_depth_5)
        await db.commit()
        await db.refresh(task_depth_5)

        # Now, trying to delegate from depth 5 would result in a child of depth 6
        executor_depth_5 = AgentExecutor(db, company.id, agent_marcus.id, task_depth_5.id)
        # Create a new non-cyclic agent just for depth test
        new_agent = Agent(company_id=company.id, name="External Bot", title="Ext", role_prompt="Ext", adapter_type="claude", monthly_budget_usd=50.0)
        db.add(new_agent)
        await db.commit()
        await db.refresh(new_agent)

        res_depth = await executor_depth_5._tool_delegate_task({"title": "Depth 6 Task", "description": "Should fail", "assignee_agent_id": new_agent.id})
        assert "Maximum delegation depth" in res_depth
