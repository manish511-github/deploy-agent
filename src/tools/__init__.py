"""
Tools package — LangChain tools the agent can invoke.

Each tool is a thin adapter: it receives arguments from the LLM,
delegates to the infrastructure layer, and formats the result as
a human-readable string.
"""

from src.tools.agent_task import send_agent_task, execute_dynamic_script
from src.tools.database import get_server_info, list_all_servers
from src.tools.k8s_deploy import (
    create_project,
    create_environment,
    deploy_image_app,
    list_deployments,
    get_app_status,
    scale_app,
    delete_app,
    delete_k8s_app,
    set_env_var,
    set_resource_limits,
)

ALL_TOOLS = [
    # ── Server management ──────────────────────
    send_agent_task,            # Structured tasks (system.info, device.restart, k8s.*)
    execute_dynamic_script,     # AI-generated scripts (unlimited capability)
    get_server_info,            # DB lookups
    list_all_servers,           # DB lookups
    # ── Kubernetes deployment ──────────────────
    create_project,
    create_environment,
    deploy_image_app,
    list_deployments,           # List all pods/deployments across namespaces
    get_app_status,
    scale_app,
    delete_app,                 # Delete DB-tracked app
    delete_k8s_app,             # Delete any k8s app by name+namespace (no DB required)
    set_env_var,
    set_resource_limits,
]

__all__ = [
    "ALL_TOOLS",
    "send_agent_task", "execute_dynamic_script",
    "get_server_info", "list_all_servers",
    "create_project", "create_environment",
    "deploy_image_app", "list_deployments",
    "get_app_status", "scale_app",
    "delete_app", "delete_k8s_app",
    "set_env_var", "set_resource_limits",
]
