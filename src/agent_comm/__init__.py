"""
Agent Communication Package — re-exports from src.task for backward compatibility.
Import from src.task directly in new code.
"""

from src.task.service import TaskService as AgentService, AgentTask  # noqa: F401
from src.task.mqtt import MQTTPublisher  # noqa: F401
from src.task.models import CheckinRequest, TaskResponse  # noqa: F401
