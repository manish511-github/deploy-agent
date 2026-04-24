# DeployAI Agent

An autonomous, AI-powered system administrator built on LangGraph. DeployAI is designed to abstract away the toil of infrastructure management, server monitoring, and continuous deployment through dynamic, context-aware agentic workflows.

https://github.com/user-attachments/assets/6a6be621-5f77-455d-befc-9252a135ee59

## 🧠 Agentic Architecture

At the core of DeployAI is a State Graph (via **LangGraph**), which gives the agent persistent memory, sequential reasoning paths, and strict operational boundaries.

### State & Memory Management
- **State Preservation**: The agent utilizes persistent memory mechanisms (such as `MemorySaver`) to remember the context of its infrastructure interactions across sessions.
- **Workflow State**: Maintains explicit knowledge of its current objectives, previously executed tools, and current progress toward server deployment goals.

### Human-in-the-Loop (HITL) Execution
The agent operates with bounded autonomy. While it can freely investigate and plan, it requires authorization for execution:
- **Breakpoint Pauses**: Uses LangGraph's dynamic `interrupt_before=["tools"]` breakpoints mechanism.
- **Safeguarded Commands**: If the agent decides to execute a potentially destructive system command via SSH, graph execution halts until the user reviews and confirms the proposed command tool-call.

### Specialized Agentic Tools
The agent acts upon the world via a suite of narrowly scoped, explicitly defined tools (`src/tools/`):
- **SSH Tooling**: Allows the agent to open secure shells into target nodes, authenticate, execute diagnostics (`df -h`, `top`, etc.), and change file permissions autonomously—strictly adhering to its HITL permissions.
- **Database Tooling**: Capable of querying internal state, deployment histories, and configurations from the database.

## 🔌 MCP Server (Model Context Protocol)

DeployAI exposes its infrastructure tools as an **MCP Server**, allowing any MCP-compatible client (Claude Desktop, Cursor, Windsurf, VS Code Copilot) to use them directly.

### Available MCP Tools
| Tool | Description |
|------|-------------|
| `ssh_execute` | Execute shell commands on remote Linux servers via SSH |
| `get_server_info` | Look up a server by hostname, ID, or IP address |
| `list_all_servers` | List all enrolled servers with status |

### Available Resources
- `deployai://config/status` — Current agent configuration summary

### Available Prompts
- `server_health_check` — Full diagnostic prompt for a server
- `deploy_service` — Deployment workflow prompt

### Running the MCP Server

**Docker (SSE transport — recommended for remote access):**
```bash
docker-compose up -d mcp-server
# Server available at http://localhost:8811/sse
```

**Local (stdio transport — for Claude Desktop / Cursor):**
```bash
deploy-ai mcp                    # stdio mode (default)
deploy-ai mcp --transport sse    # SSE mode
```

### Client Configuration

**Claude Desktop** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "deploy-ai": {
      "command": "deploy-ai",
      "args": ["mcp"]
    }
  }
}
```

**Claude Desktop (Docker/SSE):**
```json
{
  "mcpServers": {
    "deploy-ai": {
      "transport": "sse",
      "url": "http://localhost:8811/sse"
    }
  }
}
```

## 🚀 Multi-Agent Architecture

The current implementation uses a **Multi-Agent Architecture** (detailed in `multi_agent_plan.md`):
- **Planner**: Analyzes targets, writes sequential game plans
- **Executor**: Reads exact steps, runs SSH commands via tools
- **Reviewer**: Reads tool outputs, approves or routes back to Planner

Future updates will introduce specialized sub-agents for networking, database management, and cloud orchestration.

## 📂 Project Structure

```text
├── src/
│   ├── graph/          # LangGraph definitions, nodes, state, and routing edges
│   ├── tools/          # Agent-callable functions (ssh, database queries)
│   ├── memory/         # Persistent graph state and prompt histories
│   ├── mcp_server/     # MCP Server — exposes tools via Model Context Protocol
│   │   └── server.py   # FastMCP server with tools, resources, and prompts
│   └── cli/            # Typer CLI (chat, run, mcp, status commands)
├── multi_agent_plan.md # Roadmap for the multi-agent expansion 
├── tests/              # Unit testing for graph state transitions and tools
├── Dockerfile          # Agent container
├── Dockerfile.mcp      # MCP server container (SSE transport)
├── docker-compose.yml  # Full stack orchestrator
└── pyproject.toml      # Configuration and dependencies
```

## 🛠 Getting Started

### 1. Environment Configuration
Copy the example environment parameters:
```bash
cp .env.example .env
```
Ensure your API keys (e.g., Anthropic/OpenAI) and agent variables are set.

### 2. Local Testing with Dummy Server
To safely test the agent's SSH capabilities without putting production machines at risk, use the included Docker test environment:
```bash
docker-compose up -d --build
```
This deploys the agent alongside a hardened dummy server that the agent can connect to securely.

### 3. Running the Agent Local Tests
```bash
pip install -e .[test]
pytest
```

