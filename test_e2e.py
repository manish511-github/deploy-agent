import asyncio
from src.tools.agent_task import execute_dynamic_script, send_agent_task

async def run_test():
    print("Testing send_agent_task (system.info)...")
    result = await send_agent_task.ainvoke(
        input={
            "server_name": "test-server",
            "task_type": "system.info",
            "wait_timeout": 10
        }
    )
    print("Result:")
    print(result)

    print("\nTesting execute_dynamic_script (echo Hello)...")
    result2 = await execute_dynamic_script.ainvoke(
        input={
            "server_name": "test-server",
            "script": "echo 'Hello from DeployAI E2E Test!'",
            "description": "Test echo command",
            "risk_level": "low"
        }
    )
    print("Result:")
    print(result2)

if __name__ == "__main__":
    asyncio.run(run_test())
