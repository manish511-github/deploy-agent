"""
Tools package — LangChain tools the agent can invoke.

Each tool is a thin adapter: it receives arguments from the LLM,
delegates to the infrastructure layer, and formats the result as
a human-readable string.
"""

from src.tools.ssh import ssh_execute
from src.tools.database import get_server_info, list_all_servers

ALL_TOOLS = [ssh_execute, get_server_info, list_all_servers]

__all__ = ["ALL_TOOLS", "ssh_execute", "get_server_info", "list_all_servers"]
