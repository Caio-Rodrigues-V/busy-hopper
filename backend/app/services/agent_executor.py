import logging
import os
import subprocess
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from anthropic import AsyncAnthropic

from app.models.agent import Agent
from app.models.company import Company
from app.models.task import Task
from app.models.run import Run, RunStep
from app.models.approval import Approval
from app.models.audit import AuditLog
from app.models.api_credential import ApiCredential
from app.core.security import decrypt_key
from app.core.config import settings
from app.services.websocket_manager import manager

logger = logging.getLogger(__name__)

# Constants
MAX_ITERATIONS = 10

def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculates Claude token usage costs based on rates."""
    rates = {
        "claude-3-5-sonnet-20241022": {"input": 3.0 / 1_000_000, "output": 15.0 / 1_000_000},
        "claude-3-5-sonnet-latest": {"input": 3.0 / 1_000_000, "output": 15.0 / 1_000_000},
        "claude-3-opus-20240229": {"input": 15.0 / 1_000_000, "output": 75.0 / 1_000_000},
        "claude-3-haiku-20240307": {"input": 0.25 / 1_000_000, "output": 1.25 / 1_000_000},
    }
    model_key = model if model in rates else "claude-3-5-sonnet-20241022"
    rate = rates[model_key]
    return (input_tokens * rate["input"]) + (output_tokens * rate["output"])

async def calculate_monthly_spend(db: AsyncSession, company_id: int, agent_id: int) -> Tuple[float, float]:
    """Calculates month-to-date spending for the agent and company."""
    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)

    # Agent total spend this month
    agent_spend_query = select(func.coalesce(func.sum(RunStep.cost_usd), 0.0)).join(Run).filter(
        Run.agent_id == agent_id,
        RunStep.created_at >= month_start
    )
    agent_spend = (await db.execute(agent_spend_query)).scalar_one()

    # Company total spend this month
    company_spend_query = select(func.coalesce(func.sum(RunStep.cost_usd), 0.0)).join(Run).join(Agent).filter(
        Agent.company_id == company_id,
        RunStep.created_at >= month_start
    )
    company_spend = (await db.execute(company_spend_query)).scalar_one()

    return agent_spend, company_spend

async def create_audit_entry(db: AsyncSession, company_id: int, actor: str, action: str, payload: Optional[Dict] = None):
    """Utility to create an append-only audit log entry."""
    log = AuditLog(
        company_id=company_id,
        actor=actor,
        action=action,
        payload=payload
    )
    db.add(log)
    await db.commit()

class AgentExecutor:
    def __init__(self, db: AsyncSession, company_id: int, agent_id: int, task_id: int):
        self.db = db
        self.company_id = company_id
        self.agent_id = agent_id
        self.task_id = task_id
        
        # Paths for sandboxed file read/write
        self.workspace_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "workspace", f"company_{company_id}")
        )
        os.makedirs(self.workspace_dir, exist_ok=True)

    async def execute_run(self) -> str:
        """Main execution engine loop."""
        # 1. Fetch models
        agent = await self.db.get(Agent, self.agent_id)
        company = await self.db.get(Company, self.company_id)
        task = await self.db.get(Task, self.task_id)

        if not agent or not company or not task:
            raise ValueError("Invalid agent, company, or task ID.")

        if agent.status != "active":
            return f"Agent {agent.name} is not active (status: {agent.status})."

        # 2. Budget verification
        agent_spend, company_spend = await calculate_monthly_spend(self.db, self.company_id, self.agent_id)
        if agent_spend >= agent.monthly_budget_usd:
            agent.status = "exhausted"
            await self.db.commit()
            await create_audit_entry(
                self.db, self.company_id, f"agent_{agent.id}",
                "PAUSED_BUDGET_EXHAUSTED", {"agent_spend": agent_spend, "limit": agent.monthly_budget_usd}
            )
            await manager.broadcast_to_company(self.company_id, {"type": "budget_alert", "agent_id": agent.id, "reason": "agent_limit"})
            return "Agent monthly budget limit exceeded."

        if company_spend >= company.monthly_budget_usd:
            # Pause agent execution (company scope)
            await create_audit_entry(
                self.db, self.company_id, "system",
                "COMPANY_BUDGET_EXHAUSTED", {"company_spend": company_spend, "limit": company.monthly_budget_usd}
            )
            await manager.broadcast_to_company(self.company_id, {"type": "budget_alert", "reason": "company_limit"})
            return "Company monthly budget limit exceeded."

        # 3. Retrieve API Key
        api_key = await self._get_anthropic_key()
        if not api_key:
            return "Anthropic Claude API Key not configured."

        # 4. Atomic Checkout (locking task)
        task.status = "in_progress"
        task.locked_at = datetime.utcnow()
        await self.db.commit()

        # Create execution Run
        run = Run(
            task_id=self.task_id,
            agent_id=self.agent_id,
            status="running",
            started_at=datetime.utcnow()
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)

        await manager.broadcast_to_company(self.company_id, {
            "type": "run_status", "run_id": run.id, "task_id": self.task_id, "status": "running"
        })

        client = AsyncAnthropic(api_key=api_key)
        iteration = 0
        messages = []
        final_answer = ""
        paused_for_approval = False

        system_prompt = (
            f"You are {agent.name}, holding the title '{agent.title}'.\n"
            f"Your role prompt details are:\n{agent.role_prompt}\n\n"
            f"You belong to company '{company.name}', whose main MISSION is:\n{company.mission}\n\n"
            f"CRITICAL: You are currently working on task: '{task.title}' ({task.description}).\n"
            f"You must use tools at your disposal to complete the task. Call tools as needed. "
            f"When done, write a final clear message to complete the task."
        )

        # Build tools list for API call
        claude_tools = self._build_claude_tools(agent.tools)

        user_message = f"Please proceed with the task: '{task.title}'."
        messages.append({"role": "user", "content": user_message})

        try:
            while iteration < MAX_ITERATIONS:
                iteration += 1
                logger.info(f"Agent {agent.name} loop step {iteration}")

                start_time = time.time()
                
                # LLM Call
                api_params = {
                    "model": agent.model,
                    "max_tokens": 4000,
                    "temperature": agent.temperature,
                    "system": system_prompt,
                    "messages": messages,
                }
                if claude_tools:
                    api_params["tools"] = claude_tools

                response = await self._messages_create(client, api_params, api_key, agent, task, messages)
                latency = int((time.time() - start_time) * 1000)

                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens
                cost = estimate_cost(agent.model, input_tokens, output_tokens)

                # Record run stats
                run.total_tokens += (input_tokens + output_tokens)
                run.total_cost_usd += cost
                await self.db.commit()

                # Add RunStep (LLM CALL)
                input_payload = {"messages": messages[-1:]}
                output_payload = {
                    "content": [c.model_dump() for c in response.content],
                    "stop_reason": response.stop_reason
                }
                step = RunStep(
                    run_id=run.id,
                    kind="llm_call",
                    input=input_payload,
                    output=output_payload,
                    tokens=(input_tokens + output_tokens),
                    cost_usd=cost,
                    latency_ms=latency
                )
                self.db.add(step)
                await self.db.commit()

                await manager.broadcast_to_company(self.company_id, {
                    "type": "run_step", "run_id": run.id, "kind": "llm_call", "cost": cost, "latency": latency
                })

                # Check content for tool use
                tool_calls = [c for c in response.content if c.type == "tool_use"]
                text_content = " ".join([c.text for c in response.content if c.type == "text"])

                # Save response for history
                assistant_message_content = []
                for c in response.content:
                    if c.type == "text":
                        assistant_message_content.append({"type": "text", "text": c.text})
                    elif c.type == "tool_use":
                        assistant_message_content.append({
                            "type": "tool_use",
                            "id": c.id,
                            "name": c.name,
                            "input": c.input
                        })
                messages.append({"role": "assistant", "content": assistant_message_content})

                if not tool_calls:
                    # No tool calls; check if this is the final answer
                    final_answer = text_content
                    break

                # Process Tool Calls
                tool_responses = []
                for tool in tool_calls:
                    tool_name = tool.name
                    tool_input = tool.input
                    tool_call_id = tool.id

                    # Security verification (least privilege check)
                    if tool_name not in agent.tools:
                        result = f"Error: You are not authorized to use tool '{tool_name}'."
                        tool_responses.append({
                            "type": "tool_result",
                            "tool_use_id": tool_call_id,
                            "content": result
                        })
                        continue

                    # Executing tools
                    logger.info(f"Agent {agent.name} executing tool '{tool_name}'")
                    
                    step_start = time.time()
                    
                    if tool_name == "delegate_task":
                        tool_result = await self._tool_delegate_task(tool_input)
                    elif tool_name == "request_approval":
                        tool_result = await self._tool_request_approval(tool_input, run)
                        paused_for_approval = True
                    elif tool_name == "web_search":
                        tool_result = await self._tool_web_search(tool_input)
                    elif tool_name == "read_write_file":
                        tool_result = await self._tool_read_write_file(tool_input)
                    elif tool_name == "run_bash_command":
                        # Run bash automatically requires human approval gate
                        tool_result = await self._tool_request_approval(
                            {"action_type": "run_bash_command", "payload": tool_input}, run
                        )
                        paused_for_approval = True
                    elif tool_name == "publish_meta_campaign":
                        # Meta Ads requires human approval gate
                        tool_result = await self._tool_request_approval(
                            {"action_type": "publish_meta_campaign", "payload": tool_input}, run
                        )
                        paused_for_approval = True
                    elif tool_name == "generate_image_asset":
                        tool_result = await self._tool_generate_image_asset(tool_input)
                    else:
                        tool_result = f"Unknown tool '{tool_name}'."

                    step_latency = int((time.time() - step_start) * 1000)

                    # Log tool run step
                    tool_step = RunStep(
                        run_id=run.id,
                        kind="tool_call",
                        input={"tool_name": tool_name, "input": tool_input},
                        output={"result": tool_result},
                        tokens=0,
                        cost_usd=0.0,
                        latency_ms=step_latency
                    )
                    self.db.add(tool_step)
                    await self.db.commit()

                    await manager.broadcast_to_company(self.company_id, {
                        "type": "run_step", "run_id": run.id, "kind": "tool_call", "latency": step_latency
                    })

                    tool_responses.append({
                        "type": "tool_result",
                        "tool_use_id": tool_call_id,
                        "content": tool_result
                    })

                messages.append({"role": "user", "content": tool_responses})

                if paused_for_approval:
                    # Halt loop execution and wait for human decision
                    run.status = "paused"
                    task.status = "paused"
                    await self.db.commit()
                    await manager.broadcast_to_company(self.company_id, {
                        "type": "run_status", "run_id": run.id, "task_id": self.task_id, "status": "paused"
                    })
                    return "Execution paused for board approval."

            if iteration >= MAX_ITERATIONS:
                run.status = "failed"
                task.status = "failed"
                await create_audit_entry(
                    self.db, self.company_id, f"agent_{agent.id}",
                    "RUN_FAILED_LOOP", {"task_id": self.task_id, "iterations": iteration}
                )
                final_answer = "Task failed: exceeded maximum iteration runaway limit."
            else:
                run.status = "success"
                task.status = "done"
                await create_audit_entry(
                    self.db, self.company_id, f"agent_{agent.id}",
                    "TASK_COMPLETED", {"task_id": self.task_id, "answer": final_answer}
                )

            run.finished_at = datetime.utcnow()
            task.locked_at = None
            await self.db.commit()

            await manager.broadcast_to_company(self.company_id, {
                "type": "run_status", "run_id": run.id, "task_id": self.task_id, "status": run.status
            })

            return final_answer

        except Exception as e:
            logger.error(f"Error executing agent loop: {e}", exc_info=True)
            run.status = "failed"
            task.status = "failed"
            task.locked_at = None
            run.finished_at = datetime.utcnow()
            await self.db.commit()
            
            await manager.broadcast_to_company(self.company_id, {
                "type": "run_status", "run_id": run.id, "task_id": self.task_id, "status": "failed"
            })
            return f"Execution error: {str(e)}"

    async def resume_run(self, approval_id: int) -> str:
        """Resumes a paused run once the board approval decision is registered."""
        # Find the paused run
        run_query = select(Run).filter(Run.task_id == self.task_id, Run.status == "paused")
        run = (await self.db.execute(run_query)).scalars().first()
        if not run:
            return "No paused run found for this task."

        approval = await self.db.get(Approval, approval_id)
        if not approval:
            return "Approval record not found."

        # Fetch models
        agent = await self.db.get(Agent, self.agent_id)
        task = await self.db.get(Task, self.task_id)

        # Set task & run back to running
        run.status = "running"
        task.status = "in_progress"
        await self.db.commit()

        await manager.broadcast_to_company(self.company_id, {
            "type": "run_status", "run_id": run.id, "task_id": self.task_id, "status": "running"
        })

        # Fetch credentials and client
        api_key = await self._get_anthropic_key()
        client = AsyncAnthropic(api_key=api_key)

        # Read past run steps to rebuild messages history
        # (This avoids memory state loss since FastAPI is stateless)
        # We query the run steps of kind llm_call to reconstruct message chain
        steps_query = select(RunStep).filter(RunStep.run_id == run.id).order_by(RunStep.created_at.asc())
        steps = (await self.db.execute(steps_query)).scalars().all()

        messages = []
        for step in steps:
            if step.kind == "llm_call":
                # input is {"messages": [...]}, output is {"content": [...]}
                # Add input messages
                for msg in step.input.get("messages", []):
                    messages.append(msg)
                # Add assistant response
                assistant_content = []
                for c in step.output.get("content", []):
                    if c["type"] == "text":
                        assistant_content.append({"type": "text", "text": c["text"]})
                    elif c["type"] == "tool_use":
                        assistant_content.append({
                            "type": "tool_use",
                            "id": c["id"],
                            "name": c["name"],
                            "input": c["input"]
                        })
                messages.append({"role": "assistant", "content": assistant_content})

        # Re-inject the tool result from the approval
        outcome = f"Board decision on approval: {approval.status}."
        if approval.status == "approved":
            if approval.action_type == "run_bash_command":
                # Execute bash command safely
                command = approval.payload.get("command")
                outcome = await self._execute_bash_safely(command)
            elif approval.action_type == "publish_meta_campaign":
                # Deploy Meta Ads campaign
                outcome = await self._tool_execute_meta_campaign(approval.payload)

        # We need to find the last assistant message and its tool_use id to associate the result
        last_assistant_msg = messages[-1]
        tool_call_id = "paused_tool_id"
        for c in last_assistant_msg["content"]:
            if c["type"] == "tool_use":
                tool_call_id = c["id"]

        messages.append({
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": tool_call_id,
                "content": outcome
            }]
        })

        # Record tool outcome step
        tool_step = RunStep(
            run_id=run.id,
            kind="approval",
            input={"approval_id": approval_id, "action": approval.action_type},
            output={"result": outcome},
            tokens=0,
            cost_usd=0.0,
            latency_ms=0
        )
        self.db.add(tool_step)
        await self.db.commit()

        # Re-enter the loop starting at current iteration
        iteration = len(steps)
        paused_for_approval = False
        final_answer = ""

        system_prompt = (
            f"You are {agent.name}, holding the title '{agent.title}'.\n"
            f"Your role prompt details are:\n{agent.role_prompt}\n\n"
            f"You belong to company, whose main MISSION is:\n"
            f"CRITICAL: You are currently working on task: '{task.title}' ({task.description}).\n"
            f"Resume your execution after receiving the board's decision."
        )
        claude_tools = self._build_claude_tools(agent.tools)

        try:
            while iteration < MAX_ITERATIONS:
                iteration += 1
                logger.info(f"Resuming Agent {agent.name} loop step {iteration}")

                start_time = time.time()
                
                api_params = {
                    "model": agent.model,
                    "max_tokens": 4000,
                    "temperature": agent.temperature,
                    "system": system_prompt,
                    "messages": messages,
                }
                if claude_tools:
                    api_params["tools"] = claude_tools

                response = await self._messages_create(client, api_params, api_key, agent, task, messages)
                latency = int((time.time() - start_time) * 1000)

                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens
                cost = estimate_cost(agent.model, input_tokens, output_tokens)

                run.total_tokens += (input_tokens + output_tokens)
                run.total_cost_usd += cost
                await self.db.commit()

                # Add RunStep (LLM CALL)
                input_payload = {"messages": messages[-1:]}
                output_payload = {
                    "content": [c.model_dump() for c in response.content],
                    "stop_reason": response.stop_reason
                }
                step = RunStep(
                    run_id=run.id,
                    kind="llm_call",
                    input=input_payload,
                    output=output_payload,
                    tokens=(input_tokens + output_tokens),
                    cost_usd=cost,
                    latency_ms=latency
                )
                self.db.add(step)
                await self.db.commit()

                await manager.broadcast_to_company(self.company_id, {
                    "type": "run_step", "run_id": run.id, "kind": "llm_call", "cost": cost, "latency": latency
                })

                tool_calls = [c for c in response.content if c.type == "tool_use"]
                text_content = " ".join([c.text for c in response.content if c.type == "text"])

                assistant_message_content = []
                for c in response.content:
                    if c.type == "text":
                        assistant_message_content.append({"type": "text", "text": c.text})
                    elif c.type == "tool_use":
                        assistant_message_content.append({
                            "type": "tool_use",
                            "id": c.id,
                            "name": c.name,
                            "input": c.input
                        })
                messages.append({"role": "assistant", "content": assistant_message_content})

                if not tool_calls:
                    final_answer = text_content
                    break

                tool_responses = []
                for tool in tool_calls:
                    tool_name = tool.name
                    tool_input = tool.input
                    tool_call_id = tool.id

                    if tool_name not in agent.tools:
                        result = f"Error: You are not authorized to use tool '{tool_name}'."
                        tool_responses.append({
                            "type": "tool_result",
                            "tool_use_id": tool_call_id,
                            "content": result
                        })
                        continue

                    step_start = time.time()
                    
                    if tool_name == "delegate_task":
                        tool_result = await self._tool_delegate_task(tool_input)
                    elif tool_name == "request_approval":
                        tool_result = await self._tool_request_approval(tool_input, run)
                        paused_for_approval = True
                    elif tool_name == "web_search":
                        tool_result = await self._tool_web_search(tool_input)
                    elif tool_name == "read_write_file":
                        tool_result = await self._tool_read_write_file(tool_input)
                    elif tool_name == "run_bash_command":
                        tool_result = await self._tool_request_approval(
                            {"action_type": "run_bash_command", "payload": tool_input}, run
                        )
                        paused_for_approval = True
                    elif tool_name == "publish_meta_campaign":
                        tool_result = await self._tool_request_approval(
                            {"action_type": "publish_meta_campaign", "payload": tool_input}, run
                        )
                        paused_for_approval = True
                    elif tool_name == "generate_image_asset":
                        tool_result = await self._tool_generate_image_asset(tool_input)
                    else:
                        tool_result = f"Unknown tool '{tool_name}'."

                    step_latency = int((time.time() - step_start) * 1000)

                    tool_step = RunStep(
                        run_id=run.id,
                        kind="tool_call",
                        input={"tool_name": tool_name, "input": tool_input},
                        output={"result": tool_result},
                        tokens=0,
                        cost_usd=0.0,
                        latency_ms=step_latency
                    )
                    self.db.add(tool_step)
                    await self.db.commit()

                    await manager.broadcast_to_company(self.company_id, {
                        "type": "run_step", "run_id": run.id, "kind": "tool_call", "latency": step_latency
                    })

                    tool_responses.append({
                        "type": "tool_result",
                        "tool_use_id": tool_call_id,
                        "content": tool_result
                    })

                messages.append({"role": "user", "content": tool_responses})

                if paused_for_approval:
                    run.status = "paused"
                    task.status = "paused"
                    await self.db.commit()
                    await manager.broadcast_to_company(self.company_id, {
                        "type": "run_status", "run_id": run.id, "task_id": self.task_id, "status": "paused"
                    })
                    return "Execution paused for board approval."

            if iteration >= MAX_ITERATIONS:
                run.status = "failed"
                task.status = "failed"
                await create_audit_entry(
                    self.db, self.company_id, f"agent_{agent.id}",
                    "RUN_FAILED_LOOP", {"task_id": self.task_id, "iterations": iteration}
                )
                final_answer = "Task failed: exceeded maximum iteration runaway limit."
            else:
                run.status = "success"
                task.status = "done"
                await create_audit_entry(
                    self.db, self.company_id, f"agent_{agent.id}",
                    "TASK_COMPLETED", {"task_id": self.task_id, "answer": final_answer}
                )

            run.finished_at = datetime.utcnow()
            task.locked_at = None
            await self.db.commit()

            await manager.broadcast_to_company(self.company_id, {
                "type": "run_status", "run_id": run.id, "task_id": self.task_id, "status": run.status
            })

            return final_answer

        except Exception as e:
            logger.error(f"Error resuming agent loop: {e}", exc_info=True)
            run.status = "failed"
            task.status = "failed"
            task.locked_at = None
            run.finished_at = datetime.utcnow()
            await self.db.commit()
            
            await manager.broadcast_to_company(self.company_id, {
                "type": "run_status", "run_id": run.id, "task_id": self.task_id, "status": "failed"
            })
            return f"Execution error: {str(e)}"

    async def _messages_create(self, client, api_params, api_key, agent, task, messages) -> Any:
        """Calls the Anthropic API, or returns a mock message response if using a mock key."""
        if api_key == "your_anthropic_api_key_here" or api_key.lower().startswith("mock"):
            return await self._get_mock_llm_response(agent, task, messages)
        else:
            return await client.messages.create(**api_params)

    async def _get_mock_llm_response(self, agent, task, messages) -> Any:
        """Simulates agent decisions and tool invocations step-by-step for local testing without APIs."""
        class MockTextBlock:
            def __init__(self, text: str):
                self.type = "text"
                self.text = text
            def model_dump(self):
                return {"type": "text", "text": self.text}

        class MockToolUseBlock:
            def __init__(self, tool_id: str, name: str, tool_input: dict):
                self.type = "tool_use"
                self.id = tool_id
                self.name = name
                self.input = tool_input
            def model_dump(self):
                return {"type": "tool_use", "id": self.id, "name": self.name, "input": self.input}

        class MockUsage:
            def __init__(self, input_tokens=150, output_tokens=100):
                self.input_tokens = input_tokens
                self.output_tokens = output_tokens

        class MockMessage:
            def __init__(self, content: list, stop_reason="end_turn", usage=None):
                self.content = content
                self.stop_reason = stop_reason
                self.usage = usage or MockUsage()

        tool_use_id = f"toolu_mock_{int(time.time())}"
        assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
        step_number = len(assistant_msgs) + 1

        if agent.name == "Sophia":
            if step_number == 1:
                marcus_query = select(Agent).filter(Agent.company_id == self.company_id, Agent.name == "Marcus")
                marcus = (await self.db.execute(marcus_query)).scalars().first()
                marcus_id = marcus.id if marcus else 2
                
                content = [
                    MockTextBlock("Como CEO da Autonomous Corp, analisei a missão da empresa e o objetivo solicitado. Irei delegar o planejamento e coordenação técnica do desenvolvimento para Marcus (Engineering Manager)."),
                    MockToolUseBlock(
                        tool_id=tool_use_id,
                        name="delegate_task",
                        tool_input={
                            "title": f"Coordenação e Planejamento: {task.title}",
                            "description": f"Elaborar os requisitos técnicos e gerenciar a implementação da tarefa: {task.description}",
                            "assignee_agent_id": marcus_id
                        }
                    )
                ]
                return MockMessage(content=content, stop_reason="tool_use")
            else:
                content = [
                    MockTextBlock(f"Perfeito. O gerente Marcus relatou a conclusão bem-sucedida do desenvolvimento técnico. Revisei os relatórios e declaro a tarefa '{task.title}' concluída com sucesso pela diretoria!")
                ]
                return MockMessage(content=content, stop_reason="end_turn")

        elif agent.name == "Marcus":
            if step_number == 1:
                devbot_query = select(Agent).filter(Agent.company_id == self.company_id, Agent.name == "DevBot")
                devbot = (await self.db.execute(devbot_query)).scalars().first()
                devbot_id = devbot.id if devbot else 3
                
                content = [
                    MockTextBlock("Como Gerente de Engenharia, recebi a incumbência da CEO Sophia. Irei delegar a implementação prática e testes unitários para o DevBot (Senior Developer)."),
                    MockToolUseBlock(
                        tool_id=tool_use_id,
                        name="delegate_task",
                        tool_input={
                            "title": f"Desenvolvimento de Código e Criativo: {task.title}",
                            "description": f"Escrever arquivos de código correspondentes, testar comandos de terminal e gerar criativo visual para: {task.description}",
                            "assignee_agent_id": devbot_id
                        }
                    )
                ]
                return MockMessage(content=content, stop_reason="tool_use")
            else:
                content = [
                    MockTextBlock(f"Recebi a confirmação de que o DevBot concluiu com sucesso a escrita de código e a geração do criativo visual. Todos os arquivos foram validados. Reportando conclusão para a CEO Sophia.")
                ]
                return MockMessage(content=content, stop_reason="end_turn")

        else:
            if "read_write_file" in agent.tools and step_number == 1:
                content = [
                    MockTextBlock("Vou iniciar escrevendo o arquivo de código principal para a implementação solicitada no workspace da empresa."),
                    MockToolUseBlock(
                        tool_id=tool_use_id,
                        name="read_write_file",
                        tool_input={
                            "action": "write",
                            "filename": "principal.py",
                            "content": f"# Codigo gerado pelo desenvolvedor para {task.title}\n\ndef rodar():\n    print('Executando {task.description}')\n\nif __name__ == '__main__':\n    rodar()\n"
                        }
                    )
                ]
                return MockMessage(content=content, stop_reason="tool_use")
                
            elif "run_bash_command" in agent.tools and (step_number == 2 or (step_number == 1 and "read_write_file" not in agent.tools)):
                content = [
                    MockTextBlock("Código gravado. Agora executarei testes automatizados e validações de compilação via console Bash para garantir que o script roda corretamente e não contém erros."),
                    MockToolUseBlock(
                        tool_id=tool_use_id,
                        name="run_bash_command",
                        tool_input={
                            "command": "python principal.py"
                        }
                    )
                ]
                return MockMessage(content=content, stop_reason="tool_use")
                
            elif "generate_image_asset" in agent.tools and (step_number == 3 or (step_number == 2 and "run_bash_command" not in agent.tools) or (step_number == 1 and "read_write_file" not in agent.tools and "run_bash_command" not in agent.tools)):
                content = [
                    MockTextBlock("Testes rodados e aprovados. Prosseguirei agora gerando o banner visual de publicidade SVG para a campanha."),
                    MockToolUseBlock(
                        tool_id=tool_use_id,
                        name="generate_image_asset",
                        tool_input={
                            "prompt": f"Campanha colorida com gradientes modernos para: {task.title}",
                            "filename": "criativo_conversao.svg"
                        }
                    )
                ]
                return MockMessage(content=content, stop_reason="tool_use")
            
            elif "publish_meta_campaign" in agent.tools and (step_number == 4 or step_number == 3):
                content = [
                    MockTextBlock("Com o criativo SVG e o copy prontos no workspace, solicitarei o disparo da campanha publicitária simulada na API de Meta Ads."),
                    MockToolUseBlock(
                        tool_id=tool_use_id,
                        name="publish_meta_campaign",
                        tool_input={
                            "campaign_name": f"Campanha Auto: {task.title}",
                            "objective": "CONVERSIONS",
                            "daily_budget_usd": 35.0,
                            "creative_filename": "criativo_conversao.svg"
                        }
                    )
                ]
                return MockMessage(content=content, stop_reason="tool_use")

            else:
                content = [
                    MockTextBlock(f"Processo finalizado com sucesso! Todos os requisitos da tarefa '{task.title}' foram concluídos e os arquivos necessários foram salvos com sucesso.")
                ]
                return MockMessage(content=content, stop_reason="end_turn")

    # Private Helpers & Tool Actions
    async def _get_anthropic_key(self) -> Optional[str]:
        """Loads the decrypted key from database, falling back to environment settings."""
        query = select(ApiCredential).filter(
            ApiCredential.company_id == self.company_id,
            ApiCredential.provider == "anthropic"
        )
        cred = (await self.db.execute(query)).scalars().first()
        if cred:
            try:
                return decrypt_key(cred.encrypted_key)
            except Exception as e:
                logger.error(f"Decryption of API key failed: {e}")
        return settings.ANTHROPIC_API_KEY

    def _build_claude_tools(self, allowed_tools: List[str]) -> List[Dict]:
        """Builds schemas for only the tools explicitly configured for the agent."""
        all_schemas = {
            "delegate_task": {
                "name": "delegate_task",
                "description": "Delegate a subtask to another agent in the organization.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Title of the task"},
                        "description": {"type": "string", "description": "Detailed task description"},
                        "assignee_agent_id": {"type": "integer", "description": "ID of the agent to assign the task to"}
                    },
                    "required": ["title", "description", "assignee_agent_id"]
                }
            },
            "request_approval": {
                "name": "request_approval",
                "description": "Request a decision from the board (human) for a sensitive action or high spend.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "action_type": {"type": "string", "description": "The category of action needing approval"},
                        "payload": {"type": "object", "description": "Key-value details of the action context"}
                    },
                    "required": ["action_type", "payload"]
                }
            },
            "web_search": {
                "name": "web_search",
                "description": "Search the web for information.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Web search query terms"}
                    },
                    "required": ["query"]
                }
            },
            "read_write_file": {
                "name": "read_write_file",
                "description": "Read or write a text file safely in the workspace.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["read", "write"], "description": "Read or write mode"},
                        "filename": {"type": "string", "description": "Target file name (do not include paths)"},
                        "content": {"type": "string", "description": "Text content to write (only required for write action)"}
                    },
                    "required": ["action", "filename"]
                }
            },
            "run_bash_command": {
                "name": "run_bash_command",
                "description": "Execute a bash shell command in the environment.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "The command string to execute"}
                    },
                    "required": ["command"]
                }
            },
            "publish_meta_campaign": {
                "name": "publish_meta_campaign",
                "description": "Publish a paid traffic campaign to Meta Ads (Facebook/Instagram). This is a governed high-spend action requiring board approval.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "campaign_name": {"type": "string", "description": "The name of the ad campaign"},
                        "objective": {"type": "string", "description": "Campaign objective (e.g. CONVERSIONS, LEAD_GENERATION, REACH)"},
                        "daily_budget_usd": {"type": "number", "description": "Daily budget in USD to spend on ads"}
                    },
                    "required": ["campaign_name", "objective", "daily_budget_usd"]
                }
            },
            "generate_image_asset": {
                "name": "generate_image_asset",
                "description": "Generate a simulated visual image asset (e.g. ad banners, social media posts) using AI image generator.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "Detailed description of the image to generate"},
                        "filename": {"type": "string", "description": "Target filename (e.g. ad_banner.svg or copy_creatives.svg)"}
                    },
                    "required": ["prompt", "filename"]
                }
            }
        }
        return [all_schemas[t] for t in allowed_tools if t in all_schemas]

    # Individual Tool Executors
    async def _tool_delegate_task(self, inputs: Dict[str, Any]) -> str:
        """Executes delegate_task tool."""
        title = inputs.get("title")
        description = inputs.get("description")
        assignee_agent_id = inputs.get("assignee_agent_id")

        if not title or not description or not assignee_agent_id:
            return "Error: Missing delegation arguments."

        # Create child task
        child_task = Task(
            company_id=self.company_id,
            title=title,
            description=description,
            assignee_agent_id=assignee_agent_id,
            parent_task_id=self.task_id,
            status="todo",
            traces_to_goal=True
        )
        self.db.add(child_task)
        await self.db.commit()
        await self.db.refresh(child_task)

        await create_audit_entry(
            self.db, self.company_id, f"agent_{self.agent_id}",
            "DELEGATED_TASK", {"child_task_id": child_task.id, "assignee_id": assignee_agent_id}
        )
        await manager.broadcast_to_company(self.company_id, {
            "type": "task_created", "task_id": child_task.id, "parent_task_id": self.task_id
        })

        return f"Task delegated successfully. New task ID is {child_task.id}. It has been placed in the assignee's queue."

    async def _tool_request_approval(self, inputs: Dict[str, Any], run: Run) -> str:
        """Saves a pending approval request."""
        action_type = inputs.get("action_type", "custom")
        payload = inputs.get("payload", {})
        
        # Enrich payload with routing information for easy resumes
        enriched_payload = dict(payload)
        enriched_payload["task_id"] = self.task_id
        enriched_payload["agent_id"] = self.agent_id
        enriched_payload["run_id"] = run.id

        approval = Approval(
            company_id=self.company_id,
            action_type=action_type,
            payload=enriched_payload,
            status="pending"
        )
        self.db.add(approval)
        await self.db.commit()
        await self.db.refresh(approval)

        await create_audit_entry(
            self.db, self.company_id, f"agent_{self.agent_id}",
            "APPROVAL_REQUESTED", {"approval_id": approval.id, "action_type": action_type}
        )
        
        await manager.broadcast_to_company(self.company_id, {
            "type": "approval_requested", "approval_id": approval.id, "action_type": action_type
        })

        return f"Approval request {approval.id} submitted to the board. Execution is paused until verified."

    async def _tool_web_search(self, inputs: Dict[str, Any]) -> str:
        """Simulates web search results."""
        query = inputs.get("query", "")
        # Standard mockup search response
        return (
            f"Search results for query: '{query}':\n"
            f"1. Control Plane Architecture: Re-designed systems for multi-agent systems are scaling, enabling autonomous task routing.\n"
            f"2. Budget controls: Implementing hard stops prevents unexpected token cost spikes.\n"
            f"3. Human-in-the-loop: Governance gates are essential for sandboxed operations."
        )

    async def _tool_read_write_file(self, inputs: Dict[str, Any]) -> str:
        """Safe directory-constrained read/write operation."""
        action = inputs.get("action")
        filename = inputs.get("filename", "").strip()
        content = inputs.get("content", "")

        # Directory traversal prevention
        clean_filename = os.path.basename(filename)
        target_path = os.path.abspath(os.path.join(self.workspace_dir, clean_filename))
        
        if not target_path.startswith(self.workspace_dir):
            return "Error: Access denied. Cannot write outside the authorized workspace."

        if action == "read":
            if not os.path.exists(target_path):
                return f"Error: File '{clean_filename}' does not exist."
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                return f"Error reading file: {str(e)}"
        elif action == "write":
            try:
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(content)
                return f"File '{clean_filename}' written successfully."
            except Exception as e:
                return f"Error writing file: {str(e)}"
        return "Error: Invalid file action."

    async def _execute_bash_safely(self, command: str) -> str:
        """Executes a terminal command inside the company sandbox."""
        if not command:
            return "Error: Empty command."
        
        logger.info(f"Executing approved bash command: {command}")
        try:
            # Execute command with a timeout
            process = subprocess.run(
                command,
                shell=True,
                cwd=self.workspace_dir,
                capture_output=True,
                text=True,
                timeout=15
            )
            return (
                f"Command completed.\n"
                f"Stdout: {process.stdout}\n"
                f"Stderr: {process.stderr}\n"
                f"Exit Code: {process.returncode}"
            )
        except subprocess.TimeoutExpired:
            return "Error: Command timed out after 15 seconds."
        except Exception as e:
            return f"Error executing command: {str(e)}"

    async def _tool_execute_meta_campaign(self, payload: Dict[str, Any]) -> str:
        """Simulates deploying a campaign via Meta Ads Graph API using actual configured credentials."""
        campaign_name = payload.get("campaign_name", "Meta Ads Campaign")
        objective = payload.get("objective", "LEAD_GENERATION")
        budget = payload.get("daily_budget_usd", 10.0)
        
        # Try loading Meta Ads config
        ad_account_id = "983749823"
        page_id = "unknown_page"
        
        query = select(ApiCredential).filter(
            ApiCredential.company_id == self.company_id,
            ApiCredential.provider == "meta_ads"
        )
        cred = (await self.db.execute(query)).scalars().first()
        if cred:
            try:
                decrypted = decrypt_key(cred.encrypted_key)
                config_data = json.loads(decrypted)
                ad_account_id = config_data.get("ad_account_id", ad_account_id)
                page_id = config_data.get("page_id", page_id)
            except Exception:
                # Fallback if key was not stored as JSON
                pass

        # Write campaign metadata inside workspace directory
        import json
        filename = f"meta_campaign_{int(time.time())}.json"
        clean_filename = os.path.basename(filename)
        target_path = os.path.abspath(os.path.join(self.workspace_dir, clean_filename))
        
        campaign_data = {
            "campaign_name": campaign_name,
            "objective": objective,
            "daily_budget_usd": budget,
            "status": "ACTIVE",
            "facebook_campaign_id": f"act_{ad_account_id}/camp_{int(time.time())}",
            "deployed_at": datetime.utcnow().isoformat(),
            "ad_account_id": ad_account_id,
            "page_id": page_id,
            "mode": "AGENT_DEPLOY"
        }
        
        try:
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(campaign_data, f, indent=2)
            
            return (
                f"SUCCESS: Campaign '{campaign_name}' deployed to Meta Ads Server.\n"
                f"Ad Account ID: act_{ad_account_id}\n"
                f"Facebook Campaign ID: {campaign_data['facebook_campaign_id']}\n"
                f"Status: ACTIVE\n"
                f"Daily Budget: ${budget} USD\n"
                f"Local Trace Saved to Workspace: {clean_filename}"
            )
        except Exception as e:
            return f"Error registering Meta campaign deployment: {str(e)}"

    async def _tool_generate_image_asset(self, inputs: Dict[str, Any]) -> str:
        """Simulates generating a creative image asset and saves it as a stylized SVG in the workspace."""
        prompt = inputs.get("prompt", "Creative Ad Banner")
        filename = inputs.get("filename", "ad_banner.svg").strip()
        
        # Enforce .svg extension for direct frontend vector rendering
        if not filename.lower().endswith(".svg"):
            filename = os.path.splitext(filename)[0] + ".svg"
            
        clean_filename = os.path.basename(filename)
        target_path = os.path.abspath(os.path.join(self.workspace_dir, clean_filename))
        
        # Check traversal
        if not target_path.startswith(self.workspace_dir):
            return "Error: Access denied. Cannot write outside the authorized workspace."
            
        import random
        # Choose a modern vivid gradient palette
        gradients = [
            '<linearGradient id="gradient-bg" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#4F46E5"/><stop offset="100%" stop-color="#EC4899"/></linearGradient>',
            '<linearGradient id="gradient-bg" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#06B6D4"/><stop offset="100%" stop-color="#10B981"/></linearGradient>',
            '<linearGradient id="gradient-bg" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#F59E0B"/><stop offset="100%" stop-color="#EF4444"/></linearGradient>',
            '<linearGradient id="gradient-bg" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#8B5CF6"/><stop offset="100%" stop-color="#6366F1"/></linearGradient>'
        ]
        selected_gradient = random.choice(gradients)
        
        svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 500" width="100%" height="100%">
  <defs>
    {selected_gradient}
    <filter id="glass-blur" x="-10%" y="-10%" width="120%" height="120%">
      <feDropShadow dx="0" dy="12" stdDeviation="8" flood-color="#000" flood-opacity="0.35"/>
    </filter>
  </defs>
  
  <!-- Gradient Background -->
  <rect width="800" height="500" rx="16" fill="url(#gradient-bg)"/>
  
  <!-- Abstract Decorative Overlays -->
  <circle cx="150" cy="120" r="180" fill="#ffffff" fill-opacity="0.08"/>
  <circle cx="680" cy="380" r="220" fill="#ffffff" fill-opacity="0.06"/>
  <path d="M 0,350 Q 200,280 400,380 T 800,320 L 800,500 L 0,500 Z" fill="#ffffff" fill-opacity="0.04"/>
  
  <!-- Outer Border Frame -->
  <rect x="40" y="40" width="720" height="420" rx="12" fill="none" stroke="#ffffff" stroke-width="1.5" stroke-opacity="0.2"/>
  
  <!-- Central Glassmorphism Card -->
  <rect x="120" y="100" width="560" height="300" rx="20" fill="#ffffff" fill-opacity="0.12" stroke="#ffffff" stroke-width="1" stroke-opacity="0.25" filter="url(#glass-blur)"/>
  
  <!-- Top Integration Tag -->
  <rect x="310" y="130" width="180" height="28" rx="14" fill="#0F172A" fill-opacity="0.75"/>
  <circle cx="330" cy="144" r="5" fill="#10B981"/>
  <text x="410" y="148" font-family="system-ui, -apple-system, sans-serif" font-size="10" font-weight="bold" fill="#38BDF8" text-anchor="middle" letter-spacing="1">AI CREATIVE ENGINE</text>
  
  <!-- Main Prompt Title -->
  <text x="400" y="210" font-family="system-ui, -apple-system, sans-serif" font-size="28" font-weight="900" fill="#ffffff" text-anchor="middle" letter-spacing="0.5">HIGH-CONVERTING AD BANNER</text>
  
  <!-- Truncated user prompt context -->
  <text x="400" y="255" font-family="system-ui, -apple-system, sans-serif" font-size="13" font-style="italic" fill="#E2E8F0" text-anchor="middle">
    "{prompt[:70] + ('...' if len(prompt) > 70 else '')}"
  </text>
  
  <!-- CTA Button -->
  <rect x="300" y="300" width="200" height="45" rx="12" fill="#10B981"/>
  <text x="400" y="327" font-family="system-ui, -apple-system, sans-serif" font-size="14" font-weight="bold" fill="#FFFFFF" text-anchor="middle">SHOP NOW</text>
  
  <!-- Suffix stats tag -->
  <text x="740" y="445" font-family="monospace" font-size="9" fill="#ffffff" fill-opacity="0.5" text-anchor="end">Asset ID: {clean_filename}</text>
</svg>"""
        
        try:
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(svg_content)
            return f"SUCCESS: Styled creative vector image generated and saved to workspace as '{clean_filename}'."
        except Exception as e:
            return f"Error registering image asset generation: {str(e)}"
