"""
Basic tests for the deploy-agent.

Run with: python -m pytest tests/ -v
"""

import pytest


def test_settings_load():
    """Settings should load without crashing (even with missing .env)."""
    from src.config.settings import Settings

    s = Settings(gemini_api_key="test-key")
    assert s.llm_model == "gemini-1.5-pro"
    assert s.ssh_default_user == "root"
    assert s.ssh_timeout == 30


def test_state_schema():
    """State schema should be importable and have correct fields."""
    from src.graph.state import AgentState

    # Verify the state has expected keys
    annotations = AgentState.__annotations__
    assert "intent" in annotations
    assert "target_servers" in annotations
    assert "tool_results" in annotations
    assert "error" in annotations


def test_tools_importable():
    """All tools should be importable and be valid LangChain tools."""
    from src.tools import ALL_TOOLS

    assert len(ALL_TOOLS) == 3

    tool_names = {t.name for t in ALL_TOOLS}
    assert "ssh_execute" in tool_names
    assert "get_server_info" in tool_names
    assert "list_all_servers" in tool_names


def test_graph_builds():
    """Graph should compile without errors."""
    from src.graph.graph import build_graph

    # Need a valid API key format to build (LLM init)
    import os
    os.environ["GEMINI_API_KEY"] = "sk-test-key-for-build-only"

    graph = build_graph()
    assert graph is not None
