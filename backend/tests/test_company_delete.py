import pytest
import os
import sys

# Set pythonpath
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select
from app.core.database import Base, engine, SessionLocal
from app.models.user import User
from app.models.company import Company
from app.models.agent import Agent
from app.models.task import Task
from app.models.api_credential import ApiCredential
from app.api.companies import delete_company

@pytest.fixture(autouse=True, scope="function")
async def setup_db():
    """Fixture to automatically create and drop tables for each test function."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.mark.asyncio
async def test_delete_company_cascades():
    async with SessionLocal() as db:
        # 1. Create a user
        user = User(email="company_deleter@user.com", password_hash="dummy_hash")
        db.add(user)
        await db.commit()
        await db.refresh(user)

        # 2. Create a company
        company = Company(
            user_id=user.id,
            name="Deletable Company LLC",
            mission="To be deleted",
            monthly_budget_usd=100.0,
            markup_pct=20.0
        )
        db.add(company)
        await db.commit()
        await db.refresh(company)

        # 3. Create an agent, a task, and a credential under this company
        agent = Agent(
            company_id=company.id,
            name="Assistant Agent",
            title="Helper",
            role_prompt="Help out",
            adapter_type="openai",
            model="gpt-4o",
            tools=["web_search"]
        )
        task = Task(
            company_id=company.id,
            assignee_agent_id=None,
            title="Clean Up Task",
            description="Clear files",
            status="pending"
        )
        cred = ApiCredential(
            company_id=company.id,
            provider="openai",
            encrypted_key="dummy_encrypted",
            last4="1234"
        )
        db.add_all([agent, task, cred])
        await db.commit()

        # Update task's agent id to be correct
        await db.refresh(agent)
        task.assignee_agent_id = agent.id
        await db.commit()
        await db.refresh(task)
        await db.refresh(cred)

        # 4. Verify they exist in the DB
        agent_res = await db.execute(select(Agent).filter(Agent.company_id == company.id))
        assert len(agent_res.scalars().all()) == 1

        task_res = await db.execute(select(Task).filter(Task.company_id == company.id))
        assert len(task_res.scalars().all()) == 1

        cred_res = await db.execute(select(ApiCredential).filter(ApiCredential.company_id == company.id))
        assert len(cred_res.scalars().all()) == 1

        # 5. Call the delete company handler (or endpoint directly)
        res = await delete_company(
            company_id=company.id,
            db=db,
            current_user=user
        )
        assert res["status"] == "success"

        # 6. Verify the company itself is deleted
        comp_res = await db.execute(select(Company).filter(Company.id == company.id))
        assert comp_res.scalars().first() is None

        # 7. Verify all cascading relations are deleted
        agent_res_after = await db.execute(select(Agent).filter(Agent.company_id == company.id))
        assert len(agent_res_after.scalars().all()) == 0

        task_res_after = await db.execute(select(Task).filter(Task.company_id == company.id))
        assert len(task_res_after.scalars().all()) == 0

        cred_res_after = await db.execute(select(ApiCredential).filter(ApiCredential.company_id == company.id))
        assert len(cred_res_after.scalars().all()) == 0
