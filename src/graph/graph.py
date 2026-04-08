"""
Main LangGraph — The deployment agent state machine.

Phase 1 graph structure (simple):
    START → ReAct Agent (with tools) → END

The ReAct agent handles the full Think → Act → Observe loop internally
via LangGraph's create_react_agent, which:
1. Sends messages to LLM
2. If LLM returns tool calls → executes them → adds results → loops back
3. If LLM returns a final text response → ends

Phase 2 will break this into separate Planner → Executor → Reviewer nodes.
"""

from __future__ import annotations

from langgraph.prebuilt import create_react_agent  # noqa: deprecation

from src.graph.nodes.agent import get_llm, SYSTEM_PROMPT
from src.tools import ALL_TOOLS
from src.config import settings


def build_graph():
    """
    Build and compile the LangGraph state machine.
    
    Returns a compiled graph that can be invoked with:
        graph.invoke({"messages": [("user", "check status of my server")]})
    
    The create_react_agent utility builds a graph that:
    1. Takes user messages
    2. Sends to LLM with tools bound
    3. If LLM wants to call tools → executes them → feeds results back
    4. Repeats until LLM gives a final text answer
    """
    llm = get_llm()

    from langgraph.checkpoint.memory import MemorySaver
    
    memory = MemorySaver()
    # create_react_agent builds the full ReAct loop:
    #   START → agent (LLM call) → should_continue?
    #                                 ├─ tool_calls → tool_executor → agent (loop)
    #                                 └─ no tool_calls → END
    graph = create_react_agent(
        model=llm,
        tools=ALL_TOOLS,
        prompt=SYSTEM_PROMPT,
        checkpointer=memory,
        interrupt_before=["tools"],
    )

    return graph
