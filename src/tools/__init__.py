"""
Tools package — LangChain tools the agent can invoke.

Each tool is a thin adapter: it receives arguments from the LLM,
delegates to the infrastructure layer, and formats the result as
a human-readable string.
"""

from src.tools.agent_task import send_agent_task, execute_dynamic_script
from src.tools.database import get_server_info, list_all_servers
# from src.tools.ssh import ssh_execute             # DEPRECATED

ALL_TOOLS = [
    send_agent_task,            # Structured tasks (system.info, device.restart)
    execute_dynamic_script,     # AI-generated scripts (unlimited capability)
    get_server_info,            # DB lookups
    list_all_servers,           # DB lookups
]

__all__ = ["ALL_TOOLS", "send_agent_task", "execute_dynamic_script", "get_server_info", "list_all_servers"]
