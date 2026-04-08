"""
Agent Node — The ReAct reasoning agent.

This is the core intelligence node. It uses an LLM with bound tools
to follow the ReAct pattern: Think → Act (call tool) → Observe → Think.

The LLM decides which tools to call based on the user's request and
the system prompt that defines the agent's capabilities.
"""

from __future__ import annotations

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage

from src.config import settings
from src.tools import ALL_TOOLS

# System prompt that defines the agent's personality and capabilities
SYSTEM_PROMPT = """You are DeployAI, an intelligent Linux server management assistant.

You help users manage their Linux servers by executing commands, checking status,
and providing insights. You have access to the following capabilities:

TOOLS AVAILABLE:
1. **list_all_servers** — List all enrolled servers from the database
2. **get_server_info** — Look up a specific server by hostname, ID, or IP
3. **ssh_execute** — Execute shell commands on remote servers via SSH

WORKFLOW:
- When a user mentions a server, ALWAYS look it up first with get_server_info 
  to find its IP address before SSH-ing.
- If the user says "all servers" or doesn't specify, use list_all_servers first.
- For status checks, run multiple diagnostic commands:
  • uptime (server uptime and load)
  • free -h (memory usage)
  • df -h (disk usage) 
  • docker ps --format "table {{{{.Names}}}}\\t{{{{.Status}}}}\\t{{{{.Ports}}}}" (running containers)
  • systemctl list-units --state=failed --no-pager (failed services)

GUIDELINES:
- Always explain what you're doing and why.
- Present results in a clean, structured format.
- If a command fails, explain the error and suggest fixes.
- Be proactive — if you notice high disk usage or failed services, flag it.
- NEVER run destructive commands (rm -rf, mkfs, dd) without explicit user confirmation.
- For commands you're unsure about, explain what the command does first.

PERSONALITY:
- Professional but friendly
- Concise but thorough
- Proactive about potential issues
"""


def get_llm():
    """Create the LLM instance with tools bound.
    
    Auto-detects provider: uses Ollama if OLLAMA_BASE_URL is set,
    otherwise falls back to Gemini.
    """
    if settings.ollama_base_url:
        from langchain_ollama import ChatOllama
        llm = ChatOllama(
            model=settings.llm_model,
            base_url=settings.ollama_base_url,
            temperature=settings.llm_temperature,
        )
    else:
        llm = ChatGoogleGenerativeAI(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            google_api_key=settings.gemini_api_key,
        )
    return llm.bind_tools(ALL_TOOLS)


def get_system_message() -> SystemMessage:
    """Return the system message for the agent."""
    return SystemMessage(content=SYSTEM_PROMPT)
