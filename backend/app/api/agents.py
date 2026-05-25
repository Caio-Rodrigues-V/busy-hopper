from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List

from app.core.deps import get_db, get_current_user, get_current_company
from app.models.user import User
from app.models.company import Company
from app.models.agent import Agent
from app.models.run import Run, RunStep
from app.schemas.agent import AgentCreate, AgentResponse, AgentUpdate
from app.services.agent_executor import create_audit_entry
from fastapi.responses import FileResponse
from datetime import datetime
import os

router = APIRouter()

@router.get("/", response_model=List[AgentResponse])
async def list_agents(
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company)
):
    result = await db.execute(select(Agent).filter(Agent.company_id == company.id))
    return result.scalars().all()

@router.post("/", response_model=AgentResponse)
async def create_agent(
    agent_in: AgentCreate,
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company),
    current_user: User = Depends(get_current_user)
):
    # Verify boss reporting line validity
    if agent_in.boss_agent_id:
        boss_res = await db.execute(select(Agent).filter(Agent.id == agent_in.boss_agent_id, Agent.company_id == company.id))
        boss = boss_res.scalars().first()
        if not boss:
            raise HTTPException(status_code=400, detail="Invalid boss agent (must belong to the same company).")

    new_agent = Agent(
        company_id=company.id,
        name=agent_in.name,
        title=agent_in.title,
        role_prompt=agent_in.role_prompt,
        boss_agent_id=agent_in.boss_agent_id,
        adapter_type=agent_in.adapter_type,
        model=agent_in.model,
        temperature=agent_in.temperature,
        tools=agent_in.tools,
        monthly_budget_usd=agent_in.monthly_budget_usd,
        status=agent_in.status,
        heartbeat_cron=agent_in.heartbeat_cron
    )
    db.add(new_agent)
    await db.commit()
    await db.refresh(new_agent)
    
    await create_audit_entry(
        db, company.id, f"user_{current_user.id}",
        "CREATE_AGENT", {"name": new_agent.name, "title": new_agent.title}
    )
    return new_agent

@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company)
):
    res = await db.execute(select(Agent).filter(Agent.id == agent_id, Agent.company_id == company.id))
    agent = res.scalars().first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found.")
    return agent

@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: int,
    agent_in: AgentUpdate,
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company),
    current_user: User = Depends(get_current_user)
):
    res = await db.execute(select(Agent).filter(Agent.id == agent_id, Agent.company_id == company.id))
    agent = res.scalars().first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found.")
        
    # Verify hierarchies
    if agent_in.boss_agent_id:
        if agent_in.boss_agent_id == agent.id:
            raise HTTPException(status_code=400, detail="An agent cannot report to themselves.")
        boss_res = await db.execute(select(Agent).filter(Agent.id == agent_in.boss_agent_id, Agent.company_id == company.id))
        boss = boss_res.scalars().first()
        if not boss:
            raise HTTPException(status_code=400, detail="Invalid boss agent ID.")

    for field, val in agent_in.model_dump(exclude_unset=True).items():
        setattr(agent, field, val)
        
    await db.commit()
    await db.refresh(agent)
    
    await create_audit_entry(
        db, company.id, f"user_{current_user.id}",
        "UPDATE_AGENT", {"name": agent.name, "updates": agent_in.model_dump(exclude_unset=True)}
    )
    return agent

@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company),
    current_user: User = Depends(get_current_user)
):
    res = await db.execute(select(Agent).filter(Agent.id == agent_id, Agent.company_id == company.id))
    agent = res.scalars().first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found.")
        
    await db.delete(agent)
    await db.commit()
    
    await create_audit_entry(
        db, company.id, f"user_{current_user.id}",
        "DELETE_AGENT", {"name": agent.name}
    )
    return

@router.get("/{agent_id}/artifacts")
async def list_agent_artifacts(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company)
):
    # 1. Verify agent ownership
    res = await db.execute(select(Agent).filter(Agent.id == agent_id, Agent.company_id == company.id))
    agent = res.scalars().first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found.")
        
    # 2. Get all run IDs of this agent
    runs_result = await db.execute(select(Run.id).filter(Run.agent_id == agent_id))
    run_ids = runs_result.scalars().all()
    
    if not run_ids:
        return []
        
    # 3. Get all run steps for these runs
    steps_result = await db.execute(
        select(RunStep).filter(RunStep.run_id.in_(run_ids))
    )
    steps = steps_result.scalars().all()
    
    # 4. Filter steps for artifact creation
    artifacts_map = {}
    workspace_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "workspace", f"company_{company.id}")
    )
    
    for step in steps:
        if step.kind == "tool_call" and step.input:
            tool_name = step.input.get("tool_name")
            tool_input = step.input.get("input", {})
            
            filename = None
            tool_type = None
            
            if tool_name == "read_write_file" and tool_input.get("action") == "write":
                filename = tool_input.get("filename")
                tool_type = "document"
            elif tool_name == "generate_image_asset":
                filename = tool_input.get("filename")
                if filename and not filename.lower().endswith(".svg"):
                    filename = os.path.splitext(filename)[0] + ".svg"
                tool_type = "image"
                
            if filename:
                clean_filename = os.path.basename(filename)
                fpath = os.path.join(workspace_dir, clean_filename)
                
                if os.path.exists(fpath):
                    stats = os.stat(fpath)
                    artifacts_map[clean_filename] = {
                        "filename": clean_filename,
                        "type": tool_type,
                        "size_bytes": stats.st_size,
                        "created_at": datetime.fromtimestamp(stats.st_mtime).isoformat(),
                        "prompt": tool_input.get("prompt", "")
                    }
                    
    # Sort by created_at descending
    sorted_artifacts = sorted(
        artifacts_map.values(),
        key=lambda x: x["created_at"],
        reverse=True
    )
    return sorted_artifacts

@router.get("/{agent_id}/artifacts/{filename}")
async def get_agent_artifact(
    agent_id: int,
    filename: str,
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company)
):
    # 1. Verify agent ownership
    res = await db.execute(select(Agent).filter(Agent.id == agent_id, Agent.company_id == company.id))
    agent = res.scalars().first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found.")
        
    # 2. Prevent directory traversal
    clean_filename = os.path.basename(filename)
    workspace_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "workspace", f"company_{company.id}")
    )
    target_path = os.path.abspath(os.path.join(workspace_dir, clean_filename))
    
    if not target_path.startswith(workspace_dir):
        raise HTTPException(status_code=403, detail="Access denied. Outside of authorized directory.")
        
    if not os.path.exists(target_path):
        raise HTTPException(status_code=404, detail="Artifact file not found.")
        
    # 3. Detect media type
    media_type = "application/octet-stream"
    if clean_filename.lower().endswith(".svg"):
        media_type = "image/svg+xml"
    elif clean_filename.lower().endswith(".txt") or clean_filename.lower().endswith(".md"):
        media_type = "text/plain; charset=utf-8"
    elif clean_filename.lower().endswith(".json"):
        media_type = "application/json"
        
    return FileResponse(target_path, media_type=media_type)

@router.post("/import-openclaw", response_model=AgentResponse)
async def import_openclaw_agent(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company),
    current_user: User = Depends(get_current_user)
):
    # Retrieve config object
    config = payload.get("openclaw_config") or payload
    if not config:
        raise HTTPException(status_code=400, detail="Invalid import payload. 'openclaw_config' or direct configuration required.")

    # Resolve gateway or agent nested structure
    if "gateway" in config and isinstance(config["gateway"], dict):
        agent_data = config["gateway"]
    elif "agent" in config and isinstance(config["agent"], dict):
        agent_data = config["agent"]
    else:
        agent_data = config

    # Extract fields
    name = agent_data.get("name") or agent_data.get("agent_name") or "Imported OpenClaw Agent"
    title = agent_data.get("title") or agent_data.get("role") or "OpenClaw Assistant"
    
    role_prompt = (
        agent_data.get("system_prompt") or 
        agent_data.get("instructions") or 
        agent_data.get("role_prompt") or 
        agent_data.get("system") or
        "You are an imported OpenClaw assistant."
    )
    
    raw_model = agent_data.get("model") or "gpt-4o-mini"
    from app.services.agent_executor import get_provider_for_model
    adapter_type = get_provider_for_model(raw_model)
    
    # Temperature
    temp = 0.0
    if "temperature" in agent_data:
        try:
            temp = float(agent_data["temperature"])
        except (ValueError, TypeError):
            pass

    # Budget
    budget = 50.0
    if "monthly_budget_usd" in agent_data:
        try:
            budget = float(agent_data["monthly_budget_usd"])
        except (ValueError, TypeError):
            pass
            
    # Tools mapping
    raw_tools = agent_data.get("allowed_tools") or agent_data.get("tools") or agent_data.get("skills") or []
    if isinstance(raw_tools, str):
        raw_tools = [t.strip() for t in raw_tools.split(",") if t.strip()]

    mapped_tools = []
    tool_mappings = {
        "shell": "run_bash_command",
        "bash": "run_bash_command",
        "cmd": "run_bash_command",
        "run_bash_command": "run_bash_command",
        "file": "read_write_file",
        "file_management": "read_write_file",
        "read_write_file": "read_write_file",
        "web": "web_search",
        "web_search": "web_search",
        "search": "web_search",
        "delegate": "delegate_task",
        "delegate_task": "delegate_task",
        "approval": "request_approval",
        "request_approval": "request_approval",
        "meta": "publish_meta_campaign",
        "publish_meta_campaign": "publish_meta_campaign",
        "image": "generate_image_asset",
        "generate_image_asset": "generate_image_asset",
        "hiring": "hire_agent",
        "hire_agent": "hire_agent"
    }

    for t in raw_tools:
        clean_t = str(t).lower().strip()
        if clean_t in tool_mappings:
            mapped_t = tool_mappings[clean_t]
            if mapped_t not in mapped_tools:
                mapped_tools.append(mapped_t)

    # Add default safety tools
    if "delegate_task" not in mapped_tools:
        mapped_tools.append("delegate_task")
    if "request_approval" not in mapped_tools:
        mapped_tools.append("request_approval")

    # Reporting line boss agent validation
    boss_agent_id = payload.get("boss_agent_id")
    if boss_agent_id:
        try:
            boss_agent_id = int(boss_agent_id)
            boss_res = await db.execute(select(Agent).filter(Agent.id == boss_agent_id, Agent.company_id == company.id))
            boss = boss_res.scalars().first()
            if not boss:
                boss_agent_id = None
        except (ValueError, TypeError):
            boss_agent_id = None

    # Save to database
    new_agent = Agent(
        company_id=company.id,
        name=name,
        title=title,
        role_prompt=role_prompt,
        boss_agent_id=boss_agent_id,
        adapter_type=adapter_type,
        model=raw_model,
        temperature=temp,
        tools=mapped_tools,
        monthly_budget_usd=budget,
        status="active"
    )
    db.add(new_agent)
    await db.commit()
    await db.refresh(new_agent)

    await create_audit_entry(
        db, company.id, f"user_{current_user.id}",
        "IMPORT_OPENCLAW_AGENT", {"agent_id": new_agent.id, "name": name, "title": title}
    )
    
    # WebSocket broadcast
    from app.services.websocket_manager import manager
    await manager.broadcast_to_company(company.id, {"type": "org_updated"})

    return new_agent
