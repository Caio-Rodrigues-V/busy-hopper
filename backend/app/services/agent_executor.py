import logging
import os
import subprocess
import time
import json
import asyncio
from datetime import datetime, timezone
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
from app.core.logging_config import execution_context

logger = logging.getLogger(__name__)

def get_provider_for_model(model: str) -> str:
    m = model.lower()
    if m.startswith("gemini-"):
        return "gemini"
    elif m.startswith("gpt-") or m.startswith("o1-") or m.startswith("o3-"):
        return "openai"
    elif m.startswith("openrouter/"):
        return "openrouter"
    elif m.startswith("bedrock/") or m.startswith("anthropic.claude") or m.startswith("meta.llama") or m.startswith("cohere.command") or m.startswith("amazon.titan") or m.startswith("us.") or m.startswith("eu."):
        return "aws_bedrock"
    else:
        return "anthropic"

class AdapterResponseBlock:
    def __init__(self, block_type: str, text: str = None, tool_use_id: str = None, name: str = None, tool_input: dict = None):
        self.type = block_type
        self.text = text
        self.id = tool_use_id
        self.name = name
        self.input = tool_input

    def model_dump(self):
        d = {"type": self.type}
        if self.text is not None:
            d["text"] = self.text
        if self.id is not None:
            d["id"] = self.id
            d["name"] = self.name
            d["input"] = self.input
        return d

class AdapterUsage:
    def __init__(self, input_tokens: int, output_tokens: int):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

class AdapterResponse:
    def __init__(self, content: list, stop_reason: str, usage: AdapterUsage):
        self.content = content
        self.stop_reason = stop_reason
        self.usage = usage

def translate_messages_to_openai(system_prompt: str, messages: List[Dict]) -> List[Dict]:
    openai_msgs = []
    if system_prompt:
        openai_msgs.append({"role": "system", "content": system_prompt})
        
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        
        if role == "user":
            if isinstance(content, list):
                tool_results = [c for c in content if isinstance(c, dict) and c.get("type") == "tool_result"]
                if tool_results:
                    for tr in tool_results:
                        openai_msgs.append({
                            "role": "tool",
                            "tool_call_id": tr.get("tool_use_id"),
                            "content": str(tr.get("content", ""))
                        })
                else:
                    text_parts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
                    openai_msgs.append({"role": "user", "content": " ".join(text_parts)})
            else:
                openai_msgs.append({"role": "user", "content": content})
                
        elif role == "assistant":
            if isinstance(content, list):
                text_content = " ".join([c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"])
                tool_uses = [c for c in content if isinstance(c, dict) and c.get("type") == "tool_use"]
                
                openai_msg = {"role": "assistant"}
                if text_content:
                    openai_msg["content"] = text_content
                else:
                    openai_msg["content"] = None
                    
                if tool_uses:
                    openai_msg["tool_calls"] = [
                        {
                            "id": tu.get("id"),
                            "type": "function",
                            "function": {
                                "name": tu.get("name"),
                                "arguments": json.dumps(tu.get("input", {}))
                            }
                        } for tu in tool_uses
                    ]
                openai_msgs.append(openai_msg)
            else:
                openai_msgs.append({"role": "assistant", "content": content})
                
    return openai_msgs

def translate_tools_to_openai(claude_tools: List[Dict]) -> List[Dict]:
    if not claude_tools:
        return None
    openai_tools = []
    for tool in claude_tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"]
            }
        })
    return openai_tools

def parse_openai_response(resp_json) -> AdapterResponse:
    choice = resp_json["choices"][0]
    message = choice["message"]
    finish_reason = choice.get("finish_reason")
    
    stop_reason = "tool_use" if finish_reason == "tool_calls" else "end_turn"
    
    content_blocks = []
    if message.get("content"):
        content_blocks.append(AdapterResponseBlock(block_type="text", text=message["content"]))
        
    if message.get("tool_calls"):
        for tc in message["tool_calls"]:
            try:
                args = json.loads(tc["function"]["arguments"])
            except Exception:
                args = {}
            content_blocks.append(AdapterResponseBlock(
                block_type="tool_use",
                tool_use_id=tc["id"],
                name=tc["function"]["name"],
                tool_input=args
            ))
            
    usage_data = resp_json.get("usage", {})
    usage = AdapterUsage(
        input_tokens=usage_data.get("prompt_tokens", 100),
        output_tokens=usage_data.get("completion_tokens", 100)
    )
    
    return AdapterResponse(content=content_blocks, stop_reason=stop_reason, usage=usage)

def translate_messages_to_bedrock(system_prompt: str, messages: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    bedrock_system = [{"text": system_prompt}] if system_prompt else []
    bedrock_msgs = []
    
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        
        if role == "user":
            bedrock_content = []
            if isinstance(content, list):
                tool_results = [c for c in content if isinstance(c, dict) and c.get("type") == "tool_result"]
                if tool_results:
                    for tr in tool_results:
                        bedrock_content.append({
                            "toolResult": {
                                "toolUseId": tr.get("tool_use_id"),
                                "status": "success",
                                "content": [{"text": str(tr.get("content", ""))}]
                            }
                        })
                else:
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "text":
                            bedrock_content.append({"text": c.get("text", "")})
            else:
                bedrock_content.append({"text": content})
            bedrock_msgs.append({"role": "user", "content": bedrock_content})
            
        elif role == "assistant":
            bedrock_content = []
            if isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "text":
                        bedrock_content.append({"text": c.get("text", "")})
                    elif isinstance(c, dict) and c.get("type") == "tool_use":
                        bedrock_content.append({
                            "toolUse": {
                                "toolUseId": c.get("id"),
                                "name": c.get("name"),
                                "input": c.get("input", {})
                            }
                        })
            else:
                bedrock_content.append({"text": content})
            bedrock_msgs.append({"role": "assistant", "content": bedrock_content})
            
    return bedrock_system, bedrock_msgs

def translate_tools_to_bedrock(claude_tools: List[Dict]) -> Dict:
    if not claude_tools:
        return None
    tools_list = []
    for tool in claude_tools:
        tools_list.append({
            "toolSpec": {
                "name": tool["name"],
                "description": tool["description"],
                "inputSchema": {
                    "json": tool["input_schema"]
                }
            }
        })
    return {"tools": tools_list}

def parse_bedrock_response(response) -> AdapterResponse:
    output_message = response["output"]["message"]
    stop_reason = response.get("stopReason", "end_turn")
    mapped_stop_reason = "tool_use" if stop_reason == "tool_use" else "end_turn"
        
    content_blocks = []
    for block in output_message.get("content", []):
        if "text" in block:
            content_blocks.append(AdapterResponseBlock(block_type="text", text=block["text"]))
        elif "toolUse" in block:
            tu = block["toolUse"]
            content_blocks.append(AdapterResponseBlock(
                block_type="tool_use",
                tool_use_id=tu["toolUseId"],
                name=tu["name"],
                tool_input=tu["input"]
            ))
            
    usage_data = response.get("usage", {})
    usage = AdapterUsage(
        input_tokens=usage_data.get("inputTokens", 100),
        output_tokens=usage_data.get("outputTokens", 100)
    )
    
    return AdapterResponse(content=content_blocks, stop_reason=mapped_stop_reason, usage=usage)

# Constants
MAX_ITERATIONS = 10

_checkout_lock = asyncio.Lock()
_active_tasks = set()

def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculates Claude token usage costs based on rates."""
    rates = settings.LLM_RATES
    model_key = model if model in rates else "claude-3-5-sonnet-20241022"
    rate = rates[model_key]
    return (input_tokens * (rate["input"] / 1_000_000)) + (output_tokens * (rate["output"] / 1_000_000))

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

        if agent.company_id != company.id or task.company_id != company.id:
            raise ValueError("Cross-tenant execution attempt detected!")

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
        provider = get_provider_for_model(agent.model)
        if provider == "anthropic":
            api_key = await self._get_anthropic_key()
        else:
            api_key = await self._get_provider_key(provider)
            if not api_key:
                if provider == "openai":
                    api_key = os.getenv("OPENAI_API_KEY")
                elif provider == "gemini":
                    api_key = os.getenv("GEMINI_API_KEY")
                elif provider == "openrouter":
                    api_key = os.getenv("OPENROUTER_API_KEY")
                
        if not api_key and provider != "aws_bedrock" and provider != "mock":
            return f"{provider.capitalize()} API Key not configured."

        # 4. Atomic Checkout (locking task)
        async with _checkout_lock:
            if self.task_id in _active_tasks:
                return "Task already running."

            # Reset transaction snapshot to read latest committed data
            await self.db.rollback()

            stmt = select(Task).filter(Task.id == self.task_id)
            if "postgresql" in settings.DATABASE_URL:
                stmt = stmt.with_for_update()

            result = await self.db.execute(stmt)
            task_to_claim = result.scalars().first()
            if not task_to_claim:
                return "Task not found."

            if task_to_claim.status in ["done", "failed", "paused"]:
                return f"Task is already {task_to_claim.status}."

            # Check if there is an active run for this task
            active_run_stmt = select(Run).filter(Run.task_id == self.task_id, Run.status == "running")
            active_run_result = await self.db.execute(active_run_stmt)
            active_run = active_run_result.scalars().first()
            if active_run:
                logger.info(f"Task {self.task_id} already has a running execution (Run ID {active_run.id}). Skipping.")
                return "Task already running."

            # Mark as in_progress if it was todo
            if task_to_claim.status == "todo":
                task_to_claim.status = "in_progress"
                task_to_claim.locked_at = datetime.now(timezone.utc)
                self.db.add(task_to_claim)

            task = task_to_claim

            # Re-fetch agent and company to ensure they are loaded in this transaction session without lazy loading
            agent = await self.db.get(Agent, self.agent_id)
            company = await self.db.get(Company, self.company_id)

            # Create execution Run
            run = Run(
                task_id=self.task_id,
                agent_id=self.agent_id,
                status="running",
                started_at=datetime.now(timezone.utc)
            )
            self.db.add(run)
            await self.db.commit()
            await self.db.refresh(run)

            # Add to active tasks set
            _active_tasks.add(self.task_id)

        token = None
        try:
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

            token = execution_context.set({
                "run_id": run.id,
                "company_id": self.company_id,
                "agent_id": self.agent_id
            })
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

                # Check budget limits in-loop
                budget_status = await self._check_budget_in_loop(agent, company, run, task)
                if budget_status:
                    return budget_status

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
                    elif tool_name == "hire_agent":
                        # Hiring a new agent requires human approval gate
                        tool_result = await self._tool_request_approval(
                            {"action_type": "hire_agent", "payload": tool_input}, run
                        )
                        paused_for_approval = True
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
        finally:
            if token:
                execution_context.reset(token)
            _active_tasks.discard(self.task_id)

    async def _check_budget_in_loop(self, agent, company, run, task) -> Optional[str]:
        """Checks monthly spend during the execution loop and pauses execution if budget is exceeded."""
        agent_spend, company_spend = await calculate_monthly_spend(self.db, self.company_id, self.agent_id)
        if agent_spend >= agent.monthly_budget_usd or company_spend >= company.monthly_budget_usd:
            run.status = "paused"
            task.status = "paused"
            task.locked_at = None
            
            if agent_spend >= agent.monthly_budget_usd:
                agent.status = "exhausted"
                audit_action = "PAUSED_BUDGET_EXHAUSTED"
                audit_payload = {"agent_spend": agent_spend, "limit": agent.monthly_budget_usd}
                alert_payload = {"type": "budget_alert", "agent_id": agent.id, "reason": "agent_limit"}
                ret_msg = "Agent monthly budget limit exceeded."
            else:
                audit_action = "COMPANY_BUDGET_EXHAUSTED"
                audit_payload = {"company_spend": company_spend, "limit": company.monthly_budget_usd}
                alert_payload = {"type": "budget_alert", "reason": "company_limit"}
                ret_msg = "Company monthly budget limit exceeded."
                
            await self.db.commit()
            await create_audit_entry(self.db, self.company_id, "system", audit_action, audit_payload)
            await manager.broadcast_to_company(self.company_id, alert_payload)
            await manager.broadcast_to_company(self.company_id, {
                "type": "run_status", "run_id": run.id, "task_id": self.task_id, "status": "paused"
            })
            return ret_msg
        return None

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
        company = await self.db.get(Company, self.company_id)

        if not agent or not company or not task:
            raise ValueError("Invalid agent, company, or task ID.")

        if agent.company_id != company.id or task.company_id != company.id or approval.company_id != company.id:
            raise ValueError("Cross-tenant execution attempt detected!")

        # Set task & run back to running
        run.status = "running"
        task.status = "in_progress"
        await self.db.commit()

        await manager.broadcast_to_company(self.company_id, {
            "type": "run_status", "run_id": run.id, "task_id": self.task_id, "status": "running"
        })

        # Fetch credentials and client
        provider = get_provider_for_model(agent.model)
        if provider == "anthropic":
            api_key = await self._get_anthropic_key()
        else:
            api_key = await self._get_provider_key(provider)
            if not api_key:
                if provider == "openai":
                    api_key = os.getenv("OPENAI_API_KEY")
                elif provider == "gemini":
                    api_key = os.getenv("GEMINI_API_KEY")
                elif provider == "openrouter":
                    api_key = os.getenv("OPENROUTER_API_KEY")
        client = None

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
            elif approval.action_type == "hire_agent":
                # Create the agent in database
                outcome = await self._tool_execute_hire_agent(approval.payload)

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
            f"You belong to company '{company.name}', whose main MISSION is:\n{company.mission}\n\n"
            f"CRITICAL: You are currently working on task: '{task.title}' ({task.description}).\n"
            f"Resume your execution after receiving the board's decision."
        )
        claude_tools = self._build_claude_tools(agent.tools)

        token = execution_context.set({
            "run_id": run.id,
            "company_id": self.company_id,
            "agent_id": self.agent_id
        })
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

                # Check budget limits in-loop
                budget_status = await self._check_budget_in_loop(agent, company, run, task)
                if budget_status:
                    return budget_status

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
                    elif tool_name == "hire_agent":
                        # Hiring a new agent requires human approval gate
                        tool_result = await self._tool_request_approval(
                            {"action_type": "hire_agent", "payload": tool_input}, run
                        )
                        paused_for_approval = True
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
        finally:
            execution_context.reset(token)

    async def _messages_create(self, client, api_params, api_key, agent, task, messages) -> Any:
        """Calls the Anthropic, OpenAI, Gemini, OpenRouter, or AWS Bedrock API dynamically based on agent model.
        Includes timeout, retry and exponential backoff for transient errors.
        """
        if not api_key or api_key == "your_anthropic_api_key_here" or api_key.lower().startswith("mock") or api_key.lower().startswith("your_"):
            return await self._get_mock_llm_response(agent, task, messages)

        provider = get_provider_for_model(agent.model)

        import asyncio
        import random
        max_retries = 5
        initial_delay = 1.0
        factor = 2.0

        for attempt in range(max_retries + 1):
            try:
                if provider == "anthropic":
                    from anthropic import AsyncAnthropic
                    anthropic_client = client or AsyncAnthropic(api_key=api_key)
                    return await asyncio.wait_for(
                        anthropic_client.messages.create(**api_params),
                        timeout=30.0
                    )
                elif provider in ("openai", "gemini", "openrouter"):
                    import httpx
                    if provider == "openai":
                        url = "https://api.openai.com/v1/chat/completions"
                        headers = {"Authorization": f"Bearer {api_key}"}
                        model_name = agent.model if agent.model else "gpt-4o"
                    elif provider == "gemini":
                        url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
                        headers = {"Authorization": f"Bearer {api_key}"}
                        model_name = agent.model if agent.model else "gemini-1.5-flash"
                    else: # openrouter
                        url = "https://openrouter.ai/api/v1/chat/completions"
                        headers = {
                            "Authorization": f"Bearer {api_key}",
                            "HTTP-Referer": "https://happy-heart-production-79f4.up.railway.app",
                            "X-Title": "Busy Hopper Orchestrator"
                        }
                        model_name = agent.model.replace("openrouter/", "") if agent.model.startswith("openrouter/") else agent.model

                    openai_msgs = translate_messages_to_openai(api_params.get("system", ""), messages)
                    openai_tools = translate_tools_to_openai(self._build_claude_tools(agent.tools))
                    
                    payload = {
                        "model": model_name,
                        "messages": openai_msgs,
                        "temperature": api_params.get("temperature", 0.0),
                    }
                    if openai_tools:
                        payload["tools"] = openai_tools

                    async with httpx.AsyncClient() as http_client:
                        resp = await http_client.post(url, headers=headers, json=payload, timeout=30.0)
                        if resp.status_code != 200:
                            raise Exception(f"{provider.upper()} API error ({resp.status_code}): {resp.text}")
                        resp_json = resp.json()
                        return parse_openai_response(resp_json)

                elif provider == "aws_bedrock":
                    import json
                    import boto3
                    
                    try:
                        config = json.loads(api_key)
                        aws_access_key_id = config.get("aws_access_key_id")
                        aws_secret_access_key = config.get("aws_secret_access_key")
                        aws_region = config.get("aws_region", "us-east-1")
                    except Exception:
                        aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
                        aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
                        aws_region = os.getenv("AWS_REGION", "us-east-1")

                    bedrock_model = agent.model.replace("bedrock/", "") if agent.model.startswith("bedrock/") else agent.model
                    
                    if bedrock_model == "" or bedrock_model == "aws_bedrock":
                        bedrock_model = "anthropic.claude-3-haiku-20240307-v1:0"

                    bedrock_system, bedrock_msgs = translate_messages_to_bedrock(api_params.get("system", ""), messages)
                    bedrock_tools = translate_tools_to_bedrock(self._build_claude_tools(agent.tools))

                    def invoke():
                        session = boto3.Session(
                            aws_access_key_id=aws_access_key_id,
                            aws_secret_access_key=aws_secret_access_key,
                            region_name=aws_region
                        )
                        client_bedrock = session.client('bedrock-runtime')
                        
                        converse_params = {
                            "modelId": bedrock_model,
                            "messages": bedrock_msgs,
                            "inferenceConfig": {"temperature": api_params.get("temperature", 0.0)}
                        }
                        if bedrock_system:
                            converse_params["system"] = bedrock_system
                        if bedrock_tools:
                            converse_params["toolConfig"] = bedrock_tools
                            
                        return client_bedrock.converse(**converse_params)

                    response = await asyncio.to_thread(invoke)
                    return parse_bedrock_response(response)

            except Exception as e:
                if attempt == max_retries:
                    logger.error(f"LLM API call failed after {max_retries} retries: {e}")
                    raise
                delay = initial_delay * (factor ** attempt) + random.uniform(0.1, 1.0)
                logger.warning(f"LLM API transient error on {provider}: {e}. Retrying in {delay:.2f}s...")
                await asyncio.sleep(delay)

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
    async def _get_provider_key(self, provider: str) -> Optional[str]:
        """Loads the decrypted key from database for a specific provider."""
        query = select(ApiCredential).filter(
            ApiCredential.company_id == self.company_id,
            ApiCredential.provider == provider
        )
        cred = (await self.db.execute(query)).scalars().first()
        if cred:
            try:
                return decrypt_key(cred.encrypted_key)
            except Exception as e:
                logger.error(f"Decryption of API key failed for {provider}: {e}")
        return None

    async def _get_anthropic_key(self) -> Optional[str]:
        """Loads the decrypted key from database, falling back to environment settings."""
        key = await self._get_provider_key("anthropic")
        return key if key else settings.ANTHROPIC_API_KEY

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
            },
            "hire_agent": {
                "name": "hire_agent",
                "description": "Hire a new subordinate agent under your hierarchy to manage or execute specific tasks.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "The name of the new agent"},
                        "title": {"type": "string", "description": "The title/role of the new agent (e.g. Traffic Manager, Copywriter)"},
                        "role_prompt": {"type": "string", "description": "System instructions / system prompt for the new agent's behavior and boundaries"},
                        "model": {"type": "string", "description": "LLM model identifier to use (e.g. claude-3-5-sonnet-20241022, gpt-4o-mini, gemini-1.5-flash)"},
                        "temperature": {"type": "number", "description": "Sampling temperature, e.g. 0.0 to 1.0 (default 0.0)"},
                        "monthly_budget_usd": {"type": "number", "description": "Maximum USD monthly budget allocation for this agent"},
                        "tools": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of tool names allowed for this agent. Choose from: delegate_task, request_approval, web_search, read_write_file, run_bash_command, publish_meta_campaign, generate_image_asset"
                        }
                    },
                    "required": ["name", "title", "role_prompt", "model", "monthly_budget_usd", "tools"]
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

        try:
            assignee_agent_id = int(assignee_agent_id)
        except (ValueError, TypeError):
            return "Error: Invalid assignee_agent_id."

        # Cycle check: self-delegation
        if assignee_agent_id == self.agent_id:
            return "Error: Circular delegation detected. An agent cannot delegate a task to themselves."

        # Verify delegation depth and cycles by walking up the task hierarchy
        current_depth = 1
        parent_id = self.task_id
        while parent_id is not None:
            stmt = select(Task).filter(Task.id == parent_id)
            res = await self.db.execute(stmt)
            parent_task = res.scalars().first()
            if not parent_task:
                break
            
            current_depth += 1
            if current_depth > settings.MAX_DELEGATION_DEPTH:
                return f"Error: Maximum delegation depth of {settings.MAX_DELEGATION_DEPTH} exceeded."

            if parent_task.assignee_agent_id:
                if int(parent_task.assignee_agent_id) == assignee_agent_id:
                    return f"Error: Circular delegation detected. Agent {assignee_agent_id} is already in the parent delegation chain."
            
            parent_id = parent_task.parent_task_id

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
        
        # Prevent command injection/path traversal outside the sandbox
        if ".." in command:
            return "Error: Command execution blocked. Path traversal ('..') detected."
            
        # Prevent command chaining or subshell execution
        for token in [";", "&&", "||", "|", "`", "$("]:
            if token in command:
                return f"Error: Command execution blocked. Command chaining or injection token '{token}' is forbidden."
        
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
        """Deploys a campaign via Meta Ads Graph API using configured credentials."""
        import httpx
        campaign_name = payload.get("campaign_name", "Meta Ads Campaign")
        objective = payload.get("objective", "LEAD_GENERATION")
        budget = float(payload.get("daily_budget_usd", 10.0))
        
        query = select(ApiCredential).filter(
            ApiCredential.company_id == self.company_id,
            ApiCredential.provider == "meta_ads"
        )
        cred = (await self.db.execute(query)).scalars().first()
        if not cred:
            return "Error: Meta Ads credentials are not configured. Please set up the access token and ad account ID first."
            
        try:
            decrypted = decrypt_key(cred.encrypted_key)
            config_data = json.loads(decrypted)
            access_token = config_data.get("access_token")
            ad_account_id = config_data.get("ad_account_id")
            page_id = config_data.get("page_id", "")
        except Exception:
            return "Error: Failed to decrypt or parse Meta Ads credentials."
            
        if not access_token or not ad_account_id:
            return "Error: Meta Access Token or Ad Account ID is missing in configuration."

        # Call Meta Graph API to actually create the campaign
        url = f"https://graph.facebook.com/v20.0/act_{ad_account_id}/campaigns"
        
        # Map objectives. Meta simplified objectives (v15+):
        # OUTCOMES, SALES, LEADS, TRAFFIC, AWARENESS, ENGAGEMENT, APP_PROMOTION
        objective_map = {
            "CONVERSIONS": "OUTCOMES",
            "LEAD_GENERATION": "OUTCOMES",
            "TRAFFIC": "TRAFFIC",
            "REACH": "AWARENESS"
        }
        meta_objective = objective_map.get(objective, objective)
        
        # Budget in cents
        budget_cents = int(budget * 100)
        
        payload_data = {
            "name": campaign_name,
            "objective": meta_objective,
            "status": "PAUSED", # Create as paused so they can activate it in Meta Ads Manager
            "daily_budget": budget_cents,
            "special_ad_categories": "[]", # Required field for Meta API
            "access_token": access_token
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, data=payload_data, timeout=15.0)
                if response.status_code != 200:
                    try:
                        err_data = response.json()
                        err_msg = err_data.get("error", {}).get("message", "Unknown Meta API error")
                    except Exception:
                        err_msg = response.text
                    return f"Error: Meta Ads API returned status code {response.status_code}. Detail: {err_msg}"
                
                res_data = response.json()
                campaign_id = res_data.get("id")
                
                campaign_data = {
                    "campaign_name": campaign_name,
                    "objective": objective,
                    "daily_budget_usd": budget,
                    "status": "PAUSED",
                    "facebook_campaign_id": campaign_id,
                    "deployed_at": datetime.utcnow().isoformat(),
                    "ad_account_id": ad_account_id,
                    "page_id": page_id,
                    "mode": "AGENT_DEPLOY"
                }
                
                # Write campaign metadata inside workspace directory
                filename = f"meta_campaign_{int(time.time())}.json"
                clean_filename = os.path.basename(filename)
                target_path = os.path.abspath(os.path.join(self.workspace_dir, clean_filename))
                
                with open(target_path, "w", encoding="utf-8") as f:
                    json.dump(campaign_data, f, indent=2)
                
                return (
                    f"SUCCESS: Campaign '{campaign_name}' deployed to Meta Ads Server.\n"
                    f"Ad Account ID: act_{ad_account_id}\n"
                    f"Facebook Campaign ID: {campaign_id}\n"
                    f"Status: PAUSED\n"
                    f"Daily Budget: ${budget} USD\n"
                    f"Local Trace Saved to Workspace: {clean_filename}"
                )
            except Exception as e:
                return f"Error connecting to Meta Ads API: {str(e)}"

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

    async def _tool_execute_hire_agent(self, payload: Dict[str, Any]) -> str:
        """Creates the hired subordinate agent in database after board approval."""
        try:
            name = payload.get("name")
            title = payload.get("title")
            role_prompt = payload.get("role_prompt")
            model = payload.get("model", "gpt-4o-mini")
            temp = float(payload.get("temperature", 0.0))
            budget = float(payload.get("monthly_budget_usd", 50.0))
            tools = payload.get("tools", [])

            # Resolve provider key
            adapter_type = get_provider_for_model(model)

            new_agent = Agent(
                company_id=self.company_id,
                name=name,
                title=title,
                role_prompt=role_prompt,
                boss_agent_id=self.agent_id, # Hired under the hierarchy of current agent
                adapter_type=adapter_type,
                model=model,
                temperature=temp,
                monthly_budget_usd=budget,
                tools=tools,
                status="active"
            )
            self.db.add(new_agent)
            await self.db.commit()
            await self.db.refresh(new_agent)

            await create_audit_entry(
                self.db, self.company_id, f"agent_{self.agent_id}",
                "AGENT_HIRED", {"new_agent_id": new_agent.id, "name": name, "title": title}
            )

            # Broadcast WebSocket updates to make the Org Chart re-render in real-time
            await manager.broadcast_to_company(self.company_id, {"type": "org_updated"})

            return f"Success: New agent '{name}' ({title}) hired successfully with ID #{new_agent.id} reporting to you."
        except Exception as e:
            return f"Error hiring agent: {str(e)}"
