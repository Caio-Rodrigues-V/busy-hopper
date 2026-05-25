from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from typing import List

from app.core.deps import get_db, get_current_user, get_current_company
from app.models.user import User
from app.models.company import Company
from app.models.task import Task
from app.models.run import Run
from app.schemas.task import TaskCreate, TaskResponse, TaskUpdate
from app.schemas.run import RunResponse
from app.services.agent_executor import create_audit_entry
from app.services.scheduler import run_agent_task

router = APIRouter()

@router.get("/debug-db")
async def debug_db(db: AsyncSession = Depends(get_db)):
    from app.models.company import Company
    from app.models.agent import Agent
    from app.models.task import Task
    from app.models.run import Run, RunStep
    from app.models.user import User
    from sqlalchemy.future import select
    
    companies = (await db.execute(select(Company))).scalars().all()
    agents = (await db.execute(select(Agent))).scalars().all()
    tasks = (await db.execute(select(Task))).scalars().all()
    runs = (await db.execute(select(Run))).scalars().all()
    users = (await db.execute(select(User))).scalars().all()
    
    from app.models.api_credential import ApiCredential
    credentials = (await db.execute(select(ApiCredential))).scalars().all()
    
    from app.models.audit import AuditLog
    audit_logs = (await db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(30))).scalars().all()
    
    # Let's get run steps in detail
    run_steps = {}
    for r in runs:
        steps_res = await db.execute(select(RunStep).filter(RunStep.run_id == r.id).order_by(RunStep.created_at.asc()))
        steps = steps_res.scalars().all()
        run_steps[r.id] = [{
            "id": s.id,
            "kind": s.kind,
            "input": s.input,
            "output": s.output,
            "latency": s.latency_ms,
            "cost": s.cost_usd
        } for s in steps]
    
    return {
        "users": [{"id": u.id, "email": u.email} for u in users],
        "companies": [{"id": c.id, "name": c.name, "user_id": c.user_id} for c in companies],
        "agents": [{"id": a.id, "name": a.name, "model": a.model, "company_id": a.company_id, "status": a.status, "tools": a.tools} for a in agents],
        "tasks": [{"id": t.id, "title": t.title, "status": t.status, "company_id": t.company_id, "assignee": t.assignee_agent_id} for t in tasks],
        "runs": [{"id": r.id, "task_id": r.task_id, "status": r.status, "steps": run_steps.get(r.id, [])} for r in runs],
        "audit_logs": [{"id": l.id, "actor": l.actor, "action": l.action, "payload": l.payload} for l in audit_logs],
        "credentials": [{"id": cr.id, "provider": cr.provider, "company_id": cr.company_id} for cr in credentials]
    }

@router.get("/debug-workspace")
async def debug_workspace():
    import os
    workspace_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "workspace", "company_6")
    )
    if not os.path.exists(workspace_dir):
        return {"error": f"Workspace dir does not exist: {workspace_dir}"}
        
    files = os.listdir(workspace_dir)
    contents = {}
    for f in files:
        if f.endswith(".txt") or f.endswith(".json") or f.endswith(".svg"):
            try:
                with open(os.path.join(workspace_dir, f), "r", encoding="utf-8") as file_obj:
                    contents[f] = file_obj.read()
            except Exception as e:
                contents[f] = f"Error: {e}"
                
    return {"workspace_dir": workspace_dir, "files": files, "contents": contents}

@router.get("/debug-setup-run-campaign")
async def debug_setup_run_campaign(db: AsyncSession = Depends(get_db)):
    import os
    from app.models.task import Task
    from app.services.agent_executor import AgentExecutor
    
    # 1. Ensure workspace directory exists
    workspace_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "workspace", "company_6")
    )
    os.makedirs(workspace_dir, exist_ok=True)
    
    # 2. Write briefing_campanha.txt
    briefing_content = (
        "Briefing da Campanha de Tráfego Pago:\n\n"
        "Objetivo: Gerar leads qualificados para o nosso serviço de \"TIME DE TRAFEGO PAGO\".\n"
        "Público-alvo: Empresas e empreendedores que buscam otimizar suas campanhas de tráfego pago e aumentar o ROI.\n"
        "Dores do público: Baixo ROI em campanhas atuais, dificuldade em escalar, falta de tempo para gerenciar, complexidade das plataformas de anúncios.\n"
        "Desejos do público: Campanhas de alta conversão, aumento de vendas, otimização de custos, equipe especializada para gerenciar o tráfego.\n"
        "Oferta: Serviço de gestão de tráfego pago com foco em ROI positivo, utilizando inteligência artificial e um time de especialistas.\n"
        "Chamada para Ação (CTA): \"Agende uma Consultoria Gratuita\", \"Saiba Mais\", \"Comece Agora\".\n"
        "Gatilhos mentais a serem explorados: Escassez (vagas limitadas para consultoria), Autoridade (time de especialistas), Prova Social (cases de sucesso - a serem adicionados posteriormente).\n"
    )
    
    with open(os.path.join(workspace_dir, "briefing_campanha.txt"), "w", encoding="utf-8") as f:
        f.write(briefing_content)
        
    # 3. Reset Task 7 status to todo
    task = await db.get(Task, 7)
    if not task:
        return {"error": "Task 7 not found"}
    task.status = "todo"
    task.locked_at = None
    await db.commit()
    
    # 4. Run Task 7
    try:
        executor = AgentExecutor(db, company_id=6, agent_id=9, task_id=7)
        result = await executor.execute_run()
        
        # List files in workspace after execution
        files = os.listdir(workspace_dir)
        return {
            "status": "completed",
            "result": result,
            "workspace_files": files
        }
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        return {"status": "failed", "error": str(e), "traceback": tb}

@router.get("/debug-run-7")
async def debug_run_7(db: AsyncSession = Depends(get_db)):
    import traceback
    from app.models.task import Task
    from app.services.agent_executor import AgentExecutor
    from sqlalchemy.future import select
    
    # Fetch task 7
    task = await db.get(Task, 7)
    if not task:
        return {"error": "Task 7 not found"}
        
    # Reset task status to todo so it can be run
    task.status = "todo"
    task.locked_at = None
    await db.commit()
    
    try:
        executor = AgentExecutor(db, company_id=6, agent_id=9, task_id=7)
        result = await executor.execute_run()
        return {"status": "completed", "result": result}
    except Exception as e:
        tb = traceback.format_exc()
        return {"status": "failed", "error": str(e), "traceback": tb}

@router.get("/debug-gemini")
async def debug_gemini(db: AsyncSession = Depends(get_db)):
    from app.models.api_credential import ApiCredential
    from app.core.security import decrypt_key
    from sqlalchemy.future import select
    import httpx
    
    query = select(ApiCredential).filter(
        ApiCredential.company_id == 6,
        ApiCredential.provider == "gemini"
    )
    cred = (await db.execute(query)).scalars().first()
    if not cred:
        return {"error": "No Gemini credentials found for Company 6"}
        
    try:
        api_key = decrypt_key(cred.encrypted_key)
    except Exception as e:
        return {"error": f"Failed to decrypt key: {e}"}
        
    results = {}
    
    # Test 1: OpenAI compatible URL with Authorization header
    url1 = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    headers1 = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": "gemini-2.5-flash",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5
    }
    try:
        async with httpx.AsyncClient() as client:
            resp1 = await client.post(url1, headers=headers1, json=payload, timeout=10.0)
            results["bearer_status"] = resp1.status_code
            results["bearer_response"] = resp1.text[:500]
    except Exception as e:
        results["bearer_error"] = str(e)

    # Test 2: OpenAI compatible URL with query parameter key
    url2 = f"https://generativelanguage.googleapis.com/v1beta/openai/chat/completions?key={api_key}"
    try:
        async with httpx.AsyncClient() as client:
            resp2 = await client.post(url2, json=payload, timeout=10.0)
            results["query_status"] = resp2.status_code
            results["query_response"] = resp2.text[:500]
    except Exception as e:
        results["query_error"] = str(e)
        
    return results

@router.get("/", response_model=List[TaskResponse])
async def list_tasks(
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company)
):
    result = await db.execute(select(Task).filter(Task.company_id == company.id))
    return result.scalars().all()

@router.post("/", response_model=TaskResponse)
async def create_task(
    task_in: TaskCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company),
    current_user: User = Depends(get_current_user)
):
    new_task = Task(
        company_id=company.id,
        title=task_in.title,
        description=task_in.description,
        status="todo",
        assignee_agent_id=task_in.assignee_agent_id,
        parent_task_id=task_in.parent_task_id,
        traces_to_goal=task_in.traces_to_goal
    )
    db.add(new_task)
    await db.commit()
    await db.refresh(new_task)
    
    await create_audit_entry(
        db, company.id, f"user_{current_user.id}",
        "CREATE_TASK", {"title": new_task.title, "assignee_id": new_task.assignee_agent_id}
    )
    
    # If task has an assignee, trigger execution loop immediately in backend task
    if new_task.assignee_agent_id:
        background_tasks.add_task(run_agent_task, company.id, new_task.assignee_agent_id, new_task.id)
        
    return new_task

@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company)
):
    res = await db.execute(select(Task).filter(Task.id == task_id, Task.company_id == company.id))
    task = res.scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task

@router.get("/{task_id}/runs", response_model=List[RunResponse])
async def list_task_runs(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(get_current_company)
):
    res = await db.execute(select(Task).filter(Task.id == task_id, Task.company_id == company.id))
    task = res.scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
        
    # Query task runs with preloaded step elements
    query = select(Run).filter(Run.task_id == task_id).options(selectinload(Run.steps)).order_by(Run.started_at.desc())
    result = await db.execute(query)
    return result.scalars().all()
