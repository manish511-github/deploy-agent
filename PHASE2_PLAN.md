# Deploy-Agent Phase 2 Plan
## Server-First + Streaming Architecture

**Status:** Draft — Based on deep source-code analysis of Claude Code (`query.ts`, `Tool.ts`) and OpenCode (`session/llm.ts`, `session/processor.ts`, `permission/index.ts`, `agent/agent.ts`).

**Goal:** Separate the engine from the CLI, add live streaming via SSE, make sessions resumable, and replace hardcoded HITL with a declarative permission ruleset.

**Time Estimate:** 2 weeks

---

## 0. What We Learned from the Source Code

### Claude Code (`claude-code-main/src/`)

**`query.ts` (1,730 lines)** — The streaming engine is a hand-rolled async generator loop:

1. **Pre-emptive compaction** runs BEFORE every API call (4 strategies in sequence):
   - **Snip**: Drops old tool results from message tail
   - **Microcompact**: Collapses adjacent assistant+tool pairs into summaries
   - **Autocompact**: LLM-generated summary of the entire conversation
   - **Reactive compact**: Triggered by API errors (`prompt_too_long`, `max_output_tokens`)

2. **Streaming API call** via `for await (const message of deps.callModel(...))`:
   - Yields text deltas to UI in real-time
   - Accumulates assistant messages and `tool_use` blocks
   - `StreamingToolExecutor` can start tools BEFORE all args arrive

3. **Tool execution** via `runTools()`:
   - Parallelizes tools where `isConcurrencySafe === true`
   - Each tool goes through: `validateInput` → `checkPermissions` → `call()`
   - Results fed back as user messages with `tool_result` blocks

4. **Loop continuation**: If `tool_use` blocks were emitted, feed results back and call API again.

**Key insight:** The entire loop state is a mutable `State` object carried between iterations. Compaction is defensive — it happens before every call, not after failure.

**`Tool.ts` (794 lines)** — The Tool interface bundles everything:
- **Execution**: `call()`, `validateInput()`, `checkPermissions()`
- **Rendering**: `renderToolUseMessage()`, `renderToolResultMessage()`, `renderToolUseProgressMessage()`
- **Safety**: `isConcurrencySafe()`, `isReadOnly()`, `isDestructive()`
- **Budget**: `maxResultSizeChars` (spills to disk when exceeded)
- **Deferred loading**: `shouldDefer`, `alwaysLoad` for trimming system prompt

`buildTool()` fills in fail-closed defaults: `isConcurrencySafe: false`, `isReadOnly: false`.

### OpenCode (`opencode-dev/packages/opencode/src/`)

**`session/llm.ts` (320 lines)** — Uses Vercel AI SDK `streamText()`:

```typescript
return streamText({
  model: wrapLanguageModel({ model: language, middleware: [...] }),
  tools,
  activeTools: Object.keys(tools).filter(x => x !== "invalid"),
  experimental_repairToolCall: async (failed) => { /* auto-fix casing */ },
  experimental_telemetry: { isEnabled: cfg.experimental?.openTelemetry },
})
```

No hand-rolled loop. The `streamText()` call returns a `StreamTextResult` that the processor consumes. Multi-provider support (Anthropic, OpenAI, Google, OpenRouter, Copilot, Ollama) comes for free.

**`session/processor.ts` (430 lines)** — The stream consumer updates the database on EVERY event:

```typescript
for await (const value of stream.fullStream) {
  switch (value.type) {
    case "text-delta":
      await Session.updatePartDelta({ field: "text", delta: value.text })
      break
    case "tool-call":
      await Session.updatePart({ state: { status: "running", input: value.input } })
      // DOOM LOOP DETECTION: same tool+input called 3x → ask permission
      break
    case "tool-result":
      await Session.updatePart({ state: { status: "completed", output: value.output } })
      break
    case "finish-step":
      if (SessionCompaction.isOverflow({ tokens: usage.tokens })) needsCompaction = true
      break
  }
}
```

**Key insight:** The DB is the source of truth for UI state. Any client can query the DB and see current state. Events (Bus) are just notifications that something changed.

**`permission/index.ts` (322 lines)** — Uses Effect `Deferred` to block tool execution:

```typescript
async function ask(input) {
  for (const pattern of request.patterns) {
    const rule = evaluate(request.permission, pattern, ruleset, approved)
    if (rule.action === "deny") throw new DeniedError({ ruleset })
    if (rule.action === "allow") continue
    needsAsk = true
  }
  if (!needsAsk) return

  const deferred = Deferred.make<void, RejectedError | CorrectedError>()
  pending.set(id, { info, deferred })
  Bus.publish(Event.Asked, info)
  return Deferred.await(deferred) // BLOCKS until reply()
}
```

When user clicks "always":
1. Adds rule to session's `approved` ruleset
2. Re-evaluates ALL pending requests in that session
3. Auto-unblocks any that now match

**`agent/agent.ts` (418 lines)** — Agents are pure data (rulesets):

```typescript
const agents = {
  build: {
    permission: Permission.merge(defaults, Permission.fromConfig({
      question: "allow", plan_enter: "allow"
    }), user),
    mode: "primary",
  },
  plan: {
    permission: Permission.merge(defaults, Permission.fromConfig({
      edit: { "*": "deny" }, plan_exit: "allow"
    }), user),
    mode: "primary",
  },
  explore: {
    permission: Permission.merge(defaults, Permission.fromConfig({
      "*": "deny", grep: "allow", glob: "allow", bash: "allow", read: "allow"
    }), user),
    mode: "subagent",
  },
  compaction: {
    permission: Permission.merge(defaults, Permission.fromConfig({ "*": "deny" }), user),
    mode: "primary", hidden: true,
  },
}
```

An agent IS its ruleset. No separate code paths. `plan` mode is just `edit: {*: deny}`.

---

## 1. Architecture Decision: What to Adopt from Each

### From Claude Code
- **Streaming generator pattern**: Token-by-token yield to the client
- **Pre-emptive context management**: Check token budget before API call, compact if needed
- **Tool contract richness**: `isReadOnly`, `isDestructive`, `isConcurrencySafe` as booleans on each tool
- **Result budget**: Spill large tool outputs to disk, feed preview to LLM
- **Slash commands**: Three shapes (local / local_jsx / prompt)

### From OpenCode
- **Server-first**: Engine behind HTTP, CLI as client, SSE streaming
- **Permission as wildcard ruleset**: Declarative safety, agents defined by rules
- **Bus + SSE**: Postgres LISTEN/NOTIFY for event distribution (we adapt this from their in-memory PubSub)
- **Tool interface stays lean**: No rendering inside the tool; rendering happens in the client
- **DB as source of truth**: Update messages table on every stream event
- **Doom loop detection**: Same tool+input called N times → auto-ask

### What We Skip (for now)
- **Effect-TS** (OpenCode): Python equivalent is overkill. Use plain async + dependency injection.
- **React + Ink** (Claude Code): Rich Live is the Python answer.
- **Vercel AI SDK** (OpenCode): LangChain already gives us provider abstraction.
- **4-layer compaction** (Claude Code): Start with simple post-step overflow check.
- **MCP client** (both): Server-only is fine for now.

---

## 2. Target Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  CLI (Typer + Rich Live)                                        │
│  deploy-ai chat                                                 │
│     POST /sessions/:id/messages  →  202 Accepted                │
│     GET  /sessions/:id/events    ←  SSE stream                  │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP
┌──────────────────────────▼──────────────────────────────────────┐
│  FastAPI Server (src/server/main.py)                            │
│     ├─ POST /sessions                → create session           │
│     ├─ POST /sessions/:id/messages   → submit prompt            │
│     ├─ GET  /sessions/:id/events     → SSE event stream         │
│     ├─ POST /permissions/:id/reply   → approve/deny             │
│     └─ POST /agent/v1/server/:id     → Go agent check-ins       │
└──────────────────────────┬──────────────────────────────────────┘
                           │ spawns asyncio task
┌──────────────────────────▼──────────────────────────────────────┐
│  Session Engine (src/session/engine.py)                         │
│     async generator: stream(session_id, message) → events       │
│     ├─ loads checkpoint from Postgres (PostgresSaver)           │
│     ├─ runs LangGraph via astream_events()                      │
│     ├─ translates state updates → events                        │
│     ├─ permission gate inside tool wrapper                      │
│     └─ publishes events via Bus (Postgres LISTEN/NOTIFY)        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌──────────┐    ┌──────────┐    ┌──────────┐
    │ Postgres │    │ Bus      │    │ LLM API  │
    │ (state)  │    │ (events) │    │ (stream) │
    └──────────┘    └──────────┘    └──────────┘
```

---

## 3. New Dependencies

Add to `pyproject.toml`:

```toml
dependencies = [
    # ... existing ...
    "asyncpg>=0.30",                         # Async Postgres driver
    "langgraph-checkpoint-postgres>=2.0",    # Official Postgres checkpointer
    "sse-starlette>=2.0",                    # SSE endpoint support
]
```

`asyncpg` — for the Bus (LISTEN/NOTIFY) and SessionStore.

`langgraph-checkpoint-postgres` — replaces `MemorySaver` with durable checkpoints.

`sse-starlette` — Server-Sent Events for the `/sessions/:id/events` endpoint.

---

## 4. File-by-File Implementation Plan

### 4.1 `src/bus/events.py` + `src/bus/publisher.py` (NEW)

**`events.py`** — Pydantic schemas for every event:

```python
class EventType(str, Enum):
    TEXT_DELTA = "text_delta"
    TOOL_START = "tool_start"
    TOOL_RESULT = "tool_result"
    TOOL_ERROR = "tool_error"
    PERMISSION_ASKED = "permission_asked"
    PERMISSION_REPLIED = "permission_replied"
    STEP_START = "step_start"
    STEP_FINISH = "step_finish"
    DONE = "done"
    ERROR = "error"
    COMPACT = "compact"

class Event(BaseModel):
    event_id: UUID
    event_type: EventType
    session_id: UUID
    occurred_at: datetime
    payload: dict
```

**`publisher.py`** — Postgres LISTEN/NOTIFY wrapper:

```python
class Bus:
    async def publish(self, channel: str, payload: dict) -> None:
        """NOTIFY a channel with JSON payload."""
        async with self._pool.acquire() as conn:
            await conn.execute(f"NOTIFY {channel}, '{json.dumps(payload)}'")

    async def subscribe(self, channel: str) -> AsyncIterator[Event]:
        """LISTEN on a channel and yield events as they arrive."""
        async with self._pool.acquire() as conn:
            await conn.execute(f"LISTEN {channel}")
            async for notification in conn.notifications():
                yield Event.parse(notification.payload)
```

Why Postgres LISTEN/NOTIFY instead of Redis (like OpenCode uses): we already have Postgres. Zero additional infra. Latency is sub-millisecond for same-host connections.

### 4.2 `src/session/store.py` (NEW)

Session and message CRUD using `asyncpg`:

```python
class SessionStore:
    async def create(self, agent: str, model: str) -> Session:
        """INSERT INTO sessions, RETURNING id."""

    async def get(self, session_id: UUID) -> Session | None:
        """SELECT * FROM sessions WHERE id = $1."""

    async def add_message(self, session_id: UUID, role: str, parts: list[dict]) -> Message:
        """INSERT INTO messages, RETURNING id."""

    async def list_messages(self, session_id: UUID) -> list[Message]:
        """SELECT * FROM messages WHERE session_id = $1 ORDER BY created_at."""

    async def update_usage(self, session_id: UUID, tokens_in: int, tokens_out: int, cost_usd: float) -> None:
        """UPDATE sessions SET total_tokens_in = ..., total_cost_usd = ..."""

    async def get_checkpoint(self, session_id: UUID) -> dict | None:
        """Load LangGraph checkpoint from Postgres."""
```

Messages stored as structured JSONB `parts` (not raw LangChain objects). Makes them queryable and version-agnostic:

```json
[
  { "type": "text", "text": "I'll check the servers..." },
  { "type": "tool_call", "tool": "send_agent_task", "call_id": "call_123", "input": {...} },
  { "type": "tool_result", "call_id": "call_123", "output": {...} }
]
```

### 4.3 `src/permission/ruleset.py` (NEW)

Port OpenCode's `evaluate.ts` to Python:

```python
@dataclass(frozen=True)
class Rule:
    permission: str    # "exec_script", "send_agent_task", "fleet_target"
    pattern: str       # "rm -rf *", "device.shutdown", "count>10"
    action: Literal["allow", "deny", "ask"]

Ruleset = list[Rule]

def evaluate(permission: str, pattern: str, *rulesets: Ruleset) -> Rule:
    """Last-match-wins across all rulesets."""
    matched: Rule | None = None
    for rule in chain(*rulesets):
        if wildcard_match(permission, rule.permission) and wildcard_match(pattern, rule.pattern):
            matched = rule
    return matched if matched else Rule(permission="*", pattern="*", action="deny")
```

Wildcard matching using `fnmatch` (stdlib):

```python
import fnmatch

def wildcard_match(value: str, pattern: str) -> bool:
    return fnmatch.fnmatch(value, pattern)
```

### 4.4 `src/permission/service.py` (NEW)

`asyncio.Event`-based permission gate (Python equivalent of OpenCode's Effect `Deferred`):

```python
class PermissionService:
    def __init__(self, bus: Bus, store: SessionStore):
        self.bus = bus
        self.store = store
        self._pending: dict[UUID, asyncio.Event] = {}
        self._approved: Ruleset = []  # session-scoped approvals

    async def ask(
        self,
        session_id: UUID,
        permission: str,
        patterns: list[str],
        ruleset: Ruleset,
    ) -> Literal["approved", "rejected"]:
        for pattern in patterns:
            rule = evaluate(permission, pattern, ruleset, self._approved)
            if rule.action == "deny":
                raise DeniedError(f"Rule denies {permission}({pattern})")
            if rule.action == "allow":
                continue
            # Needs ask
            request_id = await self._create_request(session_id, permission, patterns)
            await self.bus.publish(f"session:{session_id}", {
                "type": "permission_asked",
                "request_id": str(request_id),
                "permission": permission,
                "patterns": patterns,
            })
            # Block until reply
            ev = asyncio.Event()
            self._pending[request_id] = ev
            await ev.wait()
            reply = await self._get_reply(request_id)
            if reply == "rejected":
                raise RejectedError()
            return "approved"
        return "approved"

    async def reply(self, request_id: UUID, reply: Literal["once", "always", "reject"]) -> None:
        await self._update_request(request_id, reply)
        if request_id in self._pending:
            self._pending[request_id].set()
        if reply == "always":
            # Add to session-scoped approved ruleset
            request = await self._get_request(request_id)
            for pattern in request.patterns:
                self._approved.append(Rule(
                    permission=request.permission,
                    pattern=pattern,
                    action="allow"
                ))
            # Re-evaluate other pending requests in same session
            for rid, ev in list(self._pending.items()):
                if rid == request_id:
                    continue
                other = await self._get_request(rid)
                if other.session_id == request.session_id:
                    ok = all(
                        evaluate(other.permission, p, self._approved).action == "allow"
                        for p in other.patterns
                    )
                    if ok:
                        await self._update_request(rid, "always")
                        ev.set()
```

### 4.5 `src/session/engine.py` (NEW)

The core streaming engine. **This is the hardest file.**

```python
async def stream_session(
    session_id: UUID,
    user_message: str,
    bus: Bus,
    store: SessionStore,
    checkpointer: PostgresSaver,
) -> None:
    """Run a session turn and publish events to the Bus.

    Steps:
      1. Load checkpoint from Postgres (resumes if session exists).
      2. Append user message to messages table.
      3. Build graph with checkpointer + permission-wrapped tools.
      4. Stream via graph.astream_events({"messages": [user_msg]}, config).
      5. For each event:
         - on_chat_model_stream → TEXT_DELTA event
         - on_tool_start → TOOL_START event
         - on_tool_end → TOOL_RESULT event
         - on_chain_end → DONE event
      6. On permission needed inside tool wrapper:
         → PERMISSION_ASKED event → blocks on asyncio.Event
         → resumes when reply() is called
      7. On finish → DONE event, update usage stats.
      8. On error → ERROR event.
    """
```

Key design: permission gate moves from graph `interrupt_before` to **tool wrapper**:

```python
class PermissionToolWrapper:
    def __init__(self, tool: BaseTool, ruleset: Ruleset, permission: PermissionService):
        self.tool = tool
        self.ruleset = ruleset
        self.permission = permission

    def invoke(self, args: dict) -> str:
        # Permission check blocks here until resolved
        result = asyncio.run(self.permission.ask(
            session_id=self.session_id,
            permission=self.tool.name,
            patterns=self._extract_patterns(args),
            ruleset=self.ruleset,
        ))
        if result == "rejected":
            return f"Permission denied: {self.tool.name}"
        return self.tool.invoke(args)
```

This means the graph **does not use `interrupt_before`** anymore. It flows continuously. The only blocking point is inside the tool wrapper, which is fine because `astream_events` can handle tool execution time.

### 4.6 `src/graph/graph.py` (MODIFY)

Changes:
1. Remove `interrupt_before=["tools"]` — permission is now inside the tool wrapper.
2. Accept `checkpointer` as an argument instead of hardcoding `MemorySaver()`.
3. Accept a `tools` list (wrapped by PermissionToolWrapper).

```python
def build_graph(checkpointer, tools):
    workflow = StateGraph(AgentState)
    workflow.add_node("planner", planner_node)
    workflow.add_node("executor", executor_node)
    workflow.add_node("reviewer", reviewer_node)
    workflow.add_node("tools", ToolNode(tools))
    # ... same edges, NO interrupt_before
    return workflow.compile(checkpointer=checkpointer)
```

### 4.7 `src/server/routes/sessions.py` (NEW)

```python
router = APIRouter(prefix="/sessions", tags=["sessions"])

@router.post("")
async def create_session(req: CreateSessionRequest) -> SessionResponse:
    """POST /sessions — create a new session. Returns {id, agent, created_at}."""

@router.post("/{session_id}/messages")
async def post_message(session_id: UUID, req: PostMessageRequest) -> MessageResponse:
    """POST /sessions/:id/messages — submit a user message.
    
    Returns 202 immediately. Spawns an asyncio task to run the engine.
    The engine publishes events to the Bus. Clients read them via SSE.
    """
    await store.add_message(session_id, role="user", parts=[{"type": "text", "text": req.content}])
    asyncio.create_task(engine.stream_session(session_id, req.content, bus, store, checkpointer))
    return { "message_id": ..., "status": "accepted" }

@router.get("/{session_id}/events")
async def get_events(session_id: UUID, request: Request) -> EventSourceResponse:
    """GET /sessions/:id/events — SSE stream of session events.
    
    Uses sse-starlette to stream Server-Sent Events.
    Subscribes to the Bus channel 'session:<session_id>'.
    """
    async def event_generator():
        async for event in bus.subscribe(f"session:{session_id}"):
            if await request.is_disconnected():
                break
            yield { "data": event.model_dump_json() }
    return EventSourceResponse(event_generator())

@router.post("/{session_id}/resume")
async def resume_session(session_id: UUID) -> None:
    """Resume a paused session (e.g., after server restart).
    
    Loads the latest checkpoint and re-runs the engine from where it left off.
    """
```

### 4.8 `src/server/routes/permissions.py` (NEW)

```python
router = APIRouter(prefix="/permissions", tags=["permissions"])

@router.post("/{request_id}/reply")
async def reply_to_permission(request_id: UUID, req: PermissionReplyRequest) -> None:
    """User approves or denies a permission request.
    
    Updates the permission_requests table and triggers the awaiting asyncio.Event.
    Also handles 'always' by adding a session-scoped rule.
    """
    await permission_service.reply(request_id, req.reply)
```

### 4.9 `src/server/main.py` (MODIFY)

Merge existing agent check-in routes with new session routes:

```python
from fastapi import FastAPI
from src.server.routes.sessions import router as sessions_router
from src.server.routes.permissions import router as permissions_router
from src.task.router import router as agent_router

app = FastAPI(title="DeployAI")
app.include_router(sessions_router)
app.include_router(permissions_router)
app.include_router(agent_router)
```

### 4.10 `src/cli/stream.py` (NEW)

SSE consumer that renders events with Rich Live:

```python
async def consume_session_stream(session_id: UUID, base_url: str, console: Console):
    """Connect to SSE endpoint and render events live.

    Event handlers:
      - text_delta    → append to current text buffer, re-render with Live
      - tool_start    → show "Running <tool_name>..." status line
      - tool_result   → show result in a Panel
      - permission_asked → show Rich Panel with typer.confirm()
      - done          → finalize and return
      - error         → show error panel
    """
    async with httpx.AsyncClient() as client:
        async with client.stream("GET", f"{base_url}/sessions/{session_id}/events") as response:
            async for line in response.aiter_lines():
                event = Event.parse(line)
                match event.event_type:
                    case EventType.TEXT_DELTA:
                        text_buffer += event.payload["text"]
                        live.update(Markdown(text_buffer))
                    case EventType.PERMISSION_ASKED:
                        # Pause live, show panel, get user input
                        reply = typer.confirm(f"Allow {event.payload['permission']}?")
                        await client.post(f"{base_url}/permissions/{event.payload['request_id']}/reply",
                                          json={"reply": "always" if reply else "reject"})
                    case EventType.DONE:
                        return
```

### 4.11 `src/cli/app.py` (MODIFY)

Replace direct graph invocation with HTTP calls:

```python
# OLD (direct import — tight coupling):
graph = build_graph()
response = invoke_agent(graph, user_input, thread_id="chat_session")

# NEW (server-first):
session = await http.post("/sessions", json={"agent": "build"})
await http.post(f"/sessions/{session.id}/messages", json={"content": user_input})
async for event in consume_session_stream(session.id, base_url, console):
    pass  # Rendering happens inside the consumer
```

The `chat` command becomes:
1. Create session (POST /sessions)
2. POST message
3. Open SSE stream (GET /sessions/:id/events)
4. Render events until DONE

Keep a `--direct` flag for debugging without the server (falls back to old `invoke_agent()`).

---

## 5. Data Flow (End-to-End)

### Scenario A — Simple read-only query

```
User: "list all servers"

CLI        Server        Engine        LangGraph      DB/Bus
 |           |             |              |              |
 |──POST /sessions/:id/messages─────────────>           |
 |<─202 Accepted─────────────────────────────|            |
 |           |             |              |              |
 |──GET /sessions/:id/events (SSE)──────────>           |
 |           |             |              |              |
 |           |──spawn stream_session()─────>|            |
 |           |             |──astream_events()──>|       |
 |           |             |              |              |
 |           |             |<─text chunk──|            |
 |           |             |              |              |
 |           |<─Event(text_delta)──────────|            |
 |<─SSE: text_delta────────────────────────|            |
 |           |             |              |              |
 |           |             |<─tool call───|            |
 |           |             |──list_all_servers()───────>|
 |           |             |              |              |
 |           |             |<─result────────────────────|
 |           |             |              |              |
 |           |<─Event(tool_result)─────────|            |
 |<─SSE: tool_result───────────────────────|            |
 |           |             |              |              |
 |           |             |<─final text──|            |
 |           |             |              |              |
 |           |<─Event(done)────────────────|            |
 |<─SSE: done──────────────────────────────|            |
 |           |             |              |              |
```

### Scenario B — Permission request (destructive operation)

```
User: "restart nginx on prod-web-01"

Engine runs astream_events() → tool call: send_agent_task("prod-web-01", "device.restart")

PermissionToolWrapper.invoke():
  evaluate("send_agent_task", "device.restart", ruleset)
  → rule matches: action="ask"
  → INSERT permission_requests (...status='pending')
  → NOTIFY 'session:abc-123' → PERMISSION_ASKED event
  → await asyncio.Event()  ← BLOCKS HERE

SSE sends PERMISSION_ASKED to CLI → Rich panel renders

User clicks "approve once":
  CLI POST /permissions/:id/reply {reply: "once"}
  Server UPDATE permission_requests status='once'
  Server triggers asyncio.Event.set()
  PermissionToolWrapper resumes
  Tool executes → INSERT task_queue → MQTT wake → Go agent runs

SSE sends TOOL_RESULT → CLI shows result
```

### Scenario C — Server restart mid-session

```
Engine is running stream_session() in an asyncio task
User kills the FastAPI process

Go agent completes task, POSTs result to /agent/v1/server/:id
Server is down → Go agent retries with backoff

User restarts FastAPI:
  CLI reconnects: GET /sessions/:id/events?since=<last_event_id>
  Server replays missed events from messages table
  CLI POST /sessions/:id/resume
  Server spawns new stream_session() task
  PostgresSaver loads checkpoint → resumes from last node
  If the tool was already completed (in task_history), engine reads it directly
  Session continues seamlessly
```

---

## 6. Migration Steps (In Order)

### Step 1: Database Migration
Apply `scripts/migrate_001_sessions.sql` (from Phase 1) to create:
- `sessions`
- `messages`
- `permission_rules`
- `permission_requests`

LangGraph PostgresSaver creates its own `checkpoints` table automatically.

### Step 2: Install Dependencies
```bash
pip install asyncpg langgraph-checkpoint-postgres sse-starlette
```

### Step 3: Build Bus + Store
Create `bus/events.py`, `bus/publisher.py`, `session/store.py`.
Write unit tests for store CRUD and bus publish/subscribe.

### Step 4: Build Permission System (Minimal)
Create `permission/ruleset.py` with a minimal evaluator.
Create `permission/service.py` with `ask()` and `reply()` using `asyncio.Event`.

Hardcode 3 rules for Phase 2:
```yaml
- permission: exec_script
  pattern: "rm -rf /*"
  action: deny
- permission: send_agent_task
  pattern: "device.restart"
  action: ask
- permission: "*"
  pattern: "*"
  action: allow
```

No `fleet_target` yet (Phase 3).

### Step 5: Build Engine
Create `session/engine.py`.

Start with a simple version:
- No subagents
- No compaction
- Permission system hardcoded (just the 3 rules)
- Stream events via Bus

Test it standalone: `python -m session.engine` with a mock bus.

### Step 6: Build Server Routes
Create `server/routes/sessions.py`, `server/routes/permissions.py`.
Mount them in `server/main.py`.

Test with curl:
```bash
curl -X POST http://localhost:8800/sessions -d '{"agent":"build"}'
curl -X POST http://localhost:8800/sessions/:id/messages -d '{"content":"list servers"}'
curl -N http://localhost:8800/sessions/:id/events
```

### Step 7: Build CLI Stream Consumer
Create `cli/stream.py`.
Test it against the running server.

### Step 8: Wire CLI
Modify `cli/app.py` to use HTTP instead of direct imports.
Keep backward compatibility: add a `--direct` flag that falls back to the old mode.

### Step 9: Switch Checkpointer
Modify `graph/graph.py` to accept checkpointer arg.
Modify `session/engine.py` to pass `PostgresSaver`.

Verify: start a session, restart server, session resumes.

### Step 10: Remove interrupt_before
Once permission gate works inside tools, remove `interrupt_before=["tools"]` from graph compilation.
Delete `runner.py` (no longer needed — engine replaces it).

---

## 7. Interfaces (Contracts Between Layers)

### Bus → SSE
```python
class Bus(Protocol):
    async def publish(self, channel: str, payload: dict) -> None: ...
    async def subscribe(self, channel: str) -> AsyncIterator[Event]: ...
```

### Engine → Bus
```python
Event = {"event_type": str, "session_id": UUID, "payload": dict}
```

### Server → Engine
```python
async def stream_session(
    session_id: UUID,
    user_message: str,
    bus: Bus,
    store: SessionStore,
    checkpointer: PostgresSaver,
) -> None:
    """Side effect: publishes events to Bus. Does not return data."""
```

### CLI → Server
```python
POST /sessions           → {id: UUID, agent: str, created_at: str}
POST /sessions/:id/msg   → {message_id: UUID, status: str}
GET  /sessions/:id/events → SSE stream
POST /permissions/:id/reply → 200 OK
```

### Permission → Tool Wrapper
```python
class PermissionGate(Protocol):
    async def ask(self, tool_name: str, args: dict, ruleset: Ruleset) -> None:
        """Throws DeniedError or RejectedError if not allowed."""
    async def reply(self, request_id: UUID, reply: Literal["once", "always", "reject"]) -> None: ...
```

---

## 8. Testing Strategy

| Component | Test Approach |
|-----------|---------------|
| **Bus** | Unit test with temp Postgres in Docker. Verify NOTIFY/LISTEN roundtrip. |
| **Store** | Unit test CRUD. Verify message ordering and JSONB parts storage. |
| **Permission evaluator** | Pure function tests. 20 cases: allow/deny/ask with wildcards. |
| **Engine** | Integration test with mock LLM (canned responses). Verify event sequence is: text_delta → tool_start → tool_result → done. |
| **Server routes** | HTTP-level tests with `httpx.AsyncClient` + `TestServer`. |
| **CLI stream** | Mock SSE stream, verify Rich output parsing. |
| **End-to-end** | `docker-compose up`, run `deploy-ai run "list servers"`, verify streamed output. |

---

## 9. Rollback Plan

If anything breaks:

1. **`cli/app.py` keeps `--direct` flag** that bypasses the server and uses the old `invoke_agent()` path.
2. **`graph.py` accepts `checkpointer=None`** → falls back to `MemorySaver()`.
3. **Old `agent_comm/` files remain untouched** (already moved to `task/` in Phase 1).

---

## 10. What We're NOT Building in Phase 2

| Feature | Why Deferred | Seam Left in Place |
|---------|-------------|-------------------|
| Auto-compaction | Sessions aren't long enough yet | `compaction.py` module reserved |
| Subagents (task tool) | Need stable engine first | `parent_id` column in sessions table |
| Fleet target rules | Phase 3 | `permission_rules.pattern` accepts any string |
| Web dashboard | No frontend capacity yet | SSE is the API surface |
| Slack bot | Same | Same SSE consumer pattern |
| Plugin system | 1 user (you) | Tool registry is injectable |
| Cost tracking | Nice to have | `total_cost_usd` column exists |
| Multi-tenancy | 1 org | `project_id` reserved in schema |
| Worker tier (arq/Celery) | FastAPI process handles it for now | Engine is a generator function — easy to move later |

---

## 11. Design Decisions Explained

### Why Postgres LISTEN/NOTIFY instead of Redis?
We already have Postgres. `LISTEN`/`NOTIFY` is built-in, zero additional infrastructure. Latency is sub-millisecond for same-host connections. OpenCode uses in-memory PubSub because it's a desktop app; we're a server.

### Why `asyncio.Event` instead of graph `interrupt_before`?
`interrupt_before=["tools"]` pauses the entire LangGraph between nodes. The streaming stops, the state machine is frozen, and resuming requires complex state management. Moving permission inside the tool wrapper means the graph flows continuously — the tool execution simply blocks until the user replies. This is how OpenCode does it (Effect `Deferred`), and it's simpler to reason about.

### Why update the DB on every stream event?
Because the DB becomes the source of truth. If the CLI disconnects and reconnects, it queries the DB and sees the current state. If the server restarts, the new process reads checkpoints and resumes. Multiple clients (CLI + web + Slack) all see the same state by reading the same DB.

### Why lean tool interface (no rendering)?
Claude Code puts rendering inside each tool (`renderToolUseMessage`, `renderToolResultMessage`). This makes tools heavy (~40 lines of interface per tool). OpenCode keeps tools at ~20 lines — rendering happens in the TUI/web client based on event types. For a server-first architecture, the client renders; the engine emits events. Lean tools are the right choice.

---

## 12. Deliverables Checklist

### Core Infrastructure
- [ ] `src/bus/events.py` — event schemas
- [ ] `src/bus/publisher.py` — Postgres LISTEN/NOTIFY bus
- [ ] `src/session/store.py` — async session/message CRUD
- [ ] `src/core/db.py` — asyncpg pool (from Phase 1, extend)

### Permission System
- [ ] `src/permission/ruleset.py` — wildcard rule evaluator
- [ ] `src/permission/service.py` — ask/reply with asyncio.Event

### Engine
- [ ] `src/session/engine.py` — streaming engine (async generator)
- [ ] `src/session/compaction.py` — placeholder (Phase 4)

### Server
- [ ] `src/server/routes/sessions.py` — REST + SSE routes
- [ ] `src/server/routes/permissions.py` — permission reply route
- [ ] `src/server/main.py` — merged FastAPI app

### CLI
- [ ] `src/cli/stream.py` — Rich Live SSE consumer
- [ ] `src/cli/app.py` — updated to use HTTP API

### Graph Changes
- [ ] `src/graph/graph.py` — accepts checkpointer, no interrupt_before
- [ ] `src/graph/runner.py` — DELETE (replaced by engine)

### Config
- [ ] `pyproject.toml` — add asyncpg, langgraph-checkpoint-postgres, sse-starlette
- [ ] `scripts/migrate_001_sessions.sql` — create tables

### Tests
- [ ] Tests for Bus
- [ ] Tests for Store
- [ ] Tests for Permission evaluator
- [ ] Integration test for Engine (mock LLM)

---

*Next step: review this plan, then begin implementation starting with Bus + Store (Step 3).*
