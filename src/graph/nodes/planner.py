"""
Planner node — analyzes user requests and generates execution plans.

Single Responsibility: read the conversation, produce a structured plan.
Does NOT execute commands or interact with tools.
"""

from __future__ import annotations

import json
import logging

from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field

from src.graph.state import AgentState
from src.graph.nodes.agent import get_llm_without_tools

logger = logging.getLogger("deployai.planner")

PLANNER_SYSTEM_PROMPT = """You are DeployAI, an intelligent deployment and server management agent.

## YOUR CAPABILITIES

### Built-in Tools (structured, reliable):
- send_agent_task("server", "system.info") → Full system health (CPU, RAM, disk, OS, uptime)
- send_agent_task("server", "device.lock/shutdown/restart") → Device control
- get_server_info("server") → Look up server details from database
- list_all_servers() → List all managed servers

### Dynamic Execution (unlimited):
- execute_dynamic_script("server", script, description, risk_level)
- You can execute ANY bash script on the target server
- Use this for tasks that don't have a dedicated tool
- Examples: install packages, configure services, manage files,
  set up cron jobs, modify firewall rules, deploy containers,
  debug applications, analyze logs, manage users

## PLANNING RULES

1. **Prefer built-in tools** when they exist (system.info > exec.run "uname -a")
2. **Break complex tasks** into small, verifiable steps
3. **Classify risk** for each step:
   - LOW: read-only commands (ls, cat, ps, df, uptime)
   - MEDIUM: config changes, service restarts
   - HIGH: package installs, data deletion, firewall changes
4. **Verify after each write** — always add a check step after modifications
5. **For novel/complex tasks**, explain your approach before executing
6. **If unsure**, ask the user for clarification instead of guessing

## OUTPUT FORMAT

Return a numbered list of steps. Each step must specify:
- The tool and arguments to use
- Risk level: [LOW], [MEDIUM], or [HIGH]
- What success looks like
"""


class DeploymentPlan(BaseModel):
    """Structured output schema for the Planner LLM."""

    plan: list[str] = Field(
        description=(
            "A sequential list of actionable steps or shell commands "
            "required to fulfill the user's request. Make sure steps "
            "are self-contained. E.g., ['apt-get update', 'apt-get install nginx -y']"
        )
    )


def _extract_plan_from_text(text: str) -> list[str]:
    """Fallback parser: extract numbered list items from plain text."""
    lines = text.strip().split("\n")
    steps = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Remove common list prefixes like "1. " or "- "
        import re
        cleaned = re.sub(r"^(\d+[.):\-]\s*|[\-\*]\s*)", "", line)
        if cleaned:
            steps.append(cleaned)
    return steps if steps else [text.strip()]


def planner_node(state: AgentState) -> dict:
    """Analyze the request and generate an execution plan.

    Returns:
        State update with the plan, reset step counter, and pending status.
    """
    llm = get_llm_without_tools()
    messages = state.get("messages", [])
    prompt = [SystemMessage(content=PLANNER_SYSTEM_PROMPT)] + messages

    # Try structured output first; fall back to plain text if the model
    # doesn't support JSON mode (common with OpenRouter free-tier models).
    try:
        structured_llm = llm.with_structured_output(DeploymentPlan)
        response = structured_llm.invoke(prompt)
        plan = response.plan
    except Exception:
        logger.warning("Structured output failed, falling back to plain text")
        response = llm.invoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)
        # Try to parse as JSON first
        try:
            data = json.loads(text)
            plan = data.get("plan", [])
        except json.JSONDecodeError:
            plan = _extract_plan_from_text(text)

    return {
        "plan": plan,
        "current_step": 0,
        "review_status": "pending",
    }
