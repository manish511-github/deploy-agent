# DeployAI Agent

An autonomous, AI-powered system administrator built on LangGraph. DeployAI is designed to abstract away the toil of infrastructure management, server monitoring, and continuous deployment through dynamic, context-aware agentic workflows.

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

## 🚀 Multi-Agent Future

The current implementation lays the groundwork for a broader **Multi-Agent Architecture** (detailed in `multi_agent_plan.md`):
- **Specialized Sub-agents**: Future updates will introduce discrete agents specialized for networking, database management, and cloud orchestration.
- **Supervisor-Worker Paradigms**: Utilizing LangGraph's multi-actor graph capabilities to route complex objectives among the appropriate highly-specialized workers.

## 📂 Project Structure

```text
├── src/
│   ├── graph/          # LangGraph definitions, nodes, state, and routing edges
│   ├── tools/          # Agent-callable functions (ssh, database queries)
│   ├── memory/         # Persistent graph state and prompt histories
│   └── mcp_server/     # MCP (Model Context Protocol) integrations
├── multi_agent_plan.md # Roadmap for the multi-agent expansion 
├── tests/              # Unit testing for graph state transitions and tools
├── docker-compose.yml  # Local testing orchestrator and test-server instances
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
