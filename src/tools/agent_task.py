import json
import asyncio
from typing import Dict, Any, Optional

from langchain_core.tools import tool

from src.fleet.repository import PostgresServerRepository
from src.task.service import TaskService
from src.task.mqtt import MQTTPublisher

async def _send_task_impl(
    server_name: str,
    task_type: str,
    payload: Optional[Dict[str, Any]] = None,
    wait_timeout: int = 30
) -> str:
    repo = PostgresServerRepository()
    server = repo.get_by_identifier(server_name)
    if not server:
        return f"Server '{server_name}' not found."
    
    service = TaskService()
    
    # 1. Create task in queue
    task = service.create_task(
        device_id=server.server_id,
        task_type=task_type,
        payload=payload or {},
        created_by="ai_agent"
    )
    if not task:
        return "Failed to create task in the database."
    
    # 2. Wake agent via MQTT
    mqtt = MQTTPublisher()
    mqtt_topic = getattr(server, "mqtt_topic", None)
    if not mqtt_topic:
        return f"Server '{server_name}' does not have an MQTT topic configured."
        
    mqtt.wake_device(mqtt_topic)
    
    # 3. Wait for result (poll DB)
    poll_interval = 1.0
    elapsed = 0.0
    while elapsed < wait_timeout:
        result = service.get_task_result(task.task_id)
        if result:
            return json.dumps(result, indent=2)
            
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
        
    return f"Agent did not respond within {wait_timeout} seconds timeout."

@tool
async def send_agent_task(
    server_name: str,
    task_type: str,
    payload: Optional[Dict[str, Any]] = None,
    wait_timeout: int = 30
) -> str:
    """Send a task to a server's Go agent and wait for the result.
    
    This replaces SSH! Instead of SSHing in and running commands,
    we queue a task, wake the agent via MQTT, and wait for it to
    report back.
    
    Args:
        server_name: Server hostname or name from the database.
        task_type: One of: system.info, exec.run, device.lock, etc.
        payload: Task-specific data (e.g., {"script": "uptime"} for exec.run).
        wait_timeout: Seconds to wait for the agent to respond.
    
    Returns:
        JSON result from the agent, or error message.
    """
    return await _send_task_impl(server_name, task_type, payload, wait_timeout)

@tool
async def execute_dynamic_script(
    server_name: str,
    script: str,
    description: str,
    risk_level: str = "medium",
) -> str:
    """Execute a dynamically generated bash script on a server.

    Use this when NO specific tool exists for the user's request.
    You generate the script yourself based on the problem analysis.

    IMPORTANT: Always explain what the script does before executing.
    For destructive operations, the system will pause for user approval.

    Args:
        server_name: Target server hostname or name.
        script: The full bash script to execute.
        description: Human-readable explanation of what this script does.
        risk_level: "low" (read-only), "medium" (config changes), "high" (installs/deletes).

    Returns:
        stdout/stderr output from the script execution.
    """
    return await _send_task_impl(
        server_name=server_name,
        task_type="exec.run",
        payload={
            "script": script,
            "timeout": 120,
            "metadata": {
                "description": description,
                "risk_level": risk_level,
                "generated_by": "ai_agent",
            }
        },
        wait_timeout=120
    )
