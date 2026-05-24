import asyncio
import sys
import os
from sqlalchemy.future import select

# Set pythonpath
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User
from app.models.company import Company
from app.models.agent import Agent

async def main():
    async with SessionLocal() as db:
        # Check if running in production
        is_production = os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("ENV") == "production"
        admin_email = os.getenv("ADMIN_EMAIL", "admin@autonomous.corp")
        admin_password = os.getenv("ADMIN_PASSWORD")
        
        # If in production, require a custom strong password
        if is_production:
            if not admin_password or admin_password == "password123":
                print("[Warning] Skipping database seeding: ADMIN_PASSWORD is not set or is set to weak default ('password123') in production.")
                return

        password = admin_password or "password123"

        # 1. Create Default User
        result = await db.execute(select(User).filter(User.email == admin_email))
        user = result.scalars().first()
        if not user:
            user = User(
                email=admin_email,
                password_hash=get_password_hash(password)
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            print(f"Created default user: {admin_email} (password: {'[SECURED]' if is_production else password})")
        else:
            print("Default user already exists.")
            
        # 2. Create Default Company
        result = await db.execute(select(Company).filter(Company.name == "Autonomous Corp"))
        company = result.scalars().first()
        if not company:
            company = Company(
                user_id=user.id,
                name="Autonomous Corp",
                mission="Build, optimize and execute software development lifecycle tasks autonomously, reporting metrics to the board.",
                monthly_budget_usd=500.0,
                markup_pct=25.0 # 25% markup
            )
            db.add(company)
            await db.commit()
            await db.refresh(company)
            print("Created default company: Autonomous Corp")
        else:
            print("Default company already exists.")
            
        # 3. Create Default Org Chart Agents
        result = await db.execute(select(Agent).filter(Agent.company_id == company.id))
        agents = result.scalars().all()
        if not agents:
            # Create CEO Agent
            ceo = Agent(
                company_id=company.id,
                name="Sophia",
                title="Chief Executive Officer",
                role_prompt="You are Sophia, the CEO of Autonomous Corp. You receive high-level directives from the board (user). You analyze the mission and goals, break them down, and delegate task items to your subordinates. Do not execute technical code yourself. You must delegate tasks to Marcus (Engineering Manager) or ask the board for approvals.",
                boss_agent_id=None,
                adapter_type="claude",
                model="claude-3-5-sonnet-20241022",
                temperature=0.2,
                tools=["delegate_task", "request_approval"],
                monthly_budget_usd=200.0,
                status="active"
            )
            db.add(ceo)
            await db.commit()
            await db.refresh(ceo)
            
            # Create Engineering Manager Agent
            manager = Agent(
                company_id=company.id,
                name="Marcus",
                title="Engineering Manager",
                role_prompt="You are Marcus, the Engineering Manager. You report directly to Sophia (CEO). You receive tasks from the CEO, formulate concrete technical steps, write reports, and delegate execution tasks to DevBot (Senior Developer). You can read/write files and check progress.",
                boss_agent_id=ceo.id,
                adapter_type="claude",
                model="claude-3-5-sonnet-20241022",
                temperature=0.1,
                tools=["delegate_task", "request_approval", "read_write_file"],
                monthly_budget_usd=150.0,
                status="active"
            )
            db.add(manager)
            await db.commit()
            await db.refresh(manager)
            
            # Create Senior Developer Agent
            worker = Agent(
                company_id=company.id,
                name="DevBot",
                title="Senior Developer",
                role_prompt="You are DevBot, a Senior Developer reporting to Marcus. You write code, scripts, and execute command instructions to fulfill engineering tasks. For any complex or risky command, request approval.",
                boss_agent_id=manager.id,
                adapter_type="claude",
                model="claude-3-5-sonnet-20241022",
                temperature=0.0,
                tools=["read_write_file", "web_search", "run_bash_command"],
                monthly_budget_usd=100.0,
                status="active"
            )
            db.add(worker)
            await db.commit()
            
            print("Prepopulated organizational structure: Sophia (CEO) -> Marcus (EM) -> DevBot (Senior Developer)")
        else:
            print("Agents already exist in this company.")

if __name__ == "__main__":
    asyncio.run(main())
