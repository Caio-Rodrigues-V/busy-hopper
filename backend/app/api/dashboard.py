from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from datetime import datetime, timedelta, time
from typing import Dict, Any, List

from app.core.deps import get_db, get_current_company
from app.models.company import Company
from app.models.run import Run, RunStep
from app.models.agent import Agent

router = APIRouter()

@router.get("/metrics")
async def get_dashboard_metrics(
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company)
):
    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)
    today_start = datetime.combine(now.date(), time.min)

    # 1. Total real cost (actual dollars spent on providers)
    cost_query = select(func.coalesce(func.sum(RunStep.cost_usd), 0.0)).join(Run).join(Agent).filter(
        Agent.company_id == company.id,
        RunStep.created_at >= month_start
    )
    total_real_cost = (await db.execute(cost_query)).scalar_one()

    # 2. Markup price
    markup_factor = 1.0 + (company.markup_pct / 100.0)
    total_markup_cost = total_real_cost * markup_factor

    # 3. Budget consumed percent
    budget_pct = (total_real_cost / company.monthly_budget_usd * 100.0) if company.monthly_budget_usd > 0 else 0.0

    # 4. Runs today
    runs_today_query = select(func.count(Run.id)).join(Agent).filter(
        Agent.company_id == company.id,
        Run.started_at >= today_start
    )
    runs_today = (await db.execute(runs_today_query)).scalar_one()

    # 5. Success rate
    success_runs_query = select(func.count(Run.id)).join(Agent).filter(
        Agent.company_id == company.id,
        Run.status == "success"
    )
    success_runs = (await db.execute(success_runs_query)).scalar_one()

    total_finished_runs_query = select(func.count(Run.id)).join(Agent).filter(
        Agent.company_id == company.id,
        Run.status.in_(["success", "failed"])
    )
    total_finished_runs = (await db.execute(total_finished_runs_query)).scalar_one()
    success_rate = (success_runs / total_finished_runs * 100.0) if total_finished_runs > 0 else 100.0

    # 6. Cost over time (last 30 days)
    time_series_query = select(RunStep.created_at, RunStep.cost_usd).join(Run).join(Agent).filter(
        Agent.company_id == company.id,
        RunStep.created_at >= now - timedelta(days=30)
    )
    steps_data = (await db.execute(time_series_query)).all()

    daily_costs = {}
    for i in range(30):
        d = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        daily_costs[d] = 0.0

    for row in steps_data:
        d_str = row.created_at.strftime("%Y-%m-%d")
        if d_str in daily_costs:
            daily_costs[d_str] += row.cost_usd

    cost_over_time = [
        {
            "date": k,
            "cost": round(v, 4),
            "markup_cost": round(v * markup_factor, 4)
        } for k, v in sorted(daily_costs.items())
    ]

    # 7. Metrics per Agent
    agents_query = select(Agent).filter(Agent.company_id == company.id)
    agents = (await db.execute(agents_query)).scalars().all()

    agent_metrics = []
    for agent in agents:
        # Agent total spend and tokens this month
        agent_spend_query = select(
            func.coalesce(func.sum(RunStep.cost_usd), 0.0),
            func.coalesce(func.sum(RunStep.tokens), 0)
        ).join(Run).filter(
            Run.agent_id == agent.id,
            RunStep.created_at >= month_start
        )
        spend, tokens = (await db.execute(agent_spend_query)).first()

        # Agent average latency (avg latency of llm_calls)
        latency_query = select(func.coalesce(func.avg(RunStep.latency_ms), 0.0)).join(Run).filter(
            Run.agent_id == agent.id,
            RunStep.kind == "llm_call"
        )
        avg_latency = (await db.execute(latency_query)).scalar_one()

        # Success / Failed runs count
        success_count = (await db.execute(
            select(func.count(Run.id)).filter(Run.agent_id == agent.id, Run.status == "success")
        )).scalar_one()
        
        failed_count = (await db.execute(
            select(func.count(Run.id)).filter(Run.agent_id == agent.id, Run.status == "failed")
        )).scalar_one()
        
        total_runs = success_count + failed_count

        # Health Classification
        health = "green"
        if total_runs > 0:
            agent_success_rate = (success_count / total_runs) * 100.0
            if agent_success_rate < 50.0:
                health = "red"
            elif agent_success_rate < 80.0:
                health = "yellow"

        # Hard budget status overrides health to red
        if spend >= agent.monthly_budget_usd:
            health = "red"
        elif agent.status == "paused":
            health = "yellow"

        agent_metrics.append({
            "agent_id": agent.id,
            "name": agent.name,
            "title": agent.title,
            "cost": round(spend, 4),
            "markup_cost": round(spend * markup_factor, 4),
            "tokens": tokens,
            "latency": round(avg_latency, 0),
            "success": success_count,
            "failed": failed_count,
            "health": health,
            "status": agent.status,
            "monthly_budget": agent.monthly_budget_usd
        })

    return {
        "company_name": company.name,
        "mission": company.mission,
        "monthly_budget": company.monthly_budget_usd,
        "markup_pct": company.markup_pct,
        "kpis": {
            "monthly_cost": round(total_real_cost, 4),
            "markup_cost": round(total_markup_cost, 4),
            "budget_pct": round(budget_pct, 1),
            "runs_today": runs_today,
            "success_rate": round(success_rate, 1)
        },
        "cost_over_time": cost_over_time,
        "agent_metrics": agent_metrics
    }
