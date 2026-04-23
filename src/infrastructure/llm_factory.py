"""
LLM factory — create LLM instances based on configuration.

Centralizes LLM provider selection and configuration. Follows the
Factory Method pattern so callers don't depend on concrete LLM classes.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from src.core.config import Settings, get_settings


def create_llm(
    settings: Settings | None = None,
    bind_tools: list | None = None,
    temperature: float | None = None,
) -> BaseChatModel:
    """Create and configure an LLM instance.

    Args:
        settings: Application settings (uses singleton if not provided).
        bind_tools: Optional list of tools to bind to the LLM.
        temperature: Override the configured temperature.

    Returns:
        A configured LangChain chat model instance.
    """
    cfg = settings or get_settings()
    temp = temperature if temperature is not None else cfg.llm_temperature
    provider = cfg.resolved_llm_provider

    llm: BaseChatModel

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        llm = ChatOllama(
            model=cfg.llm_model,
            base_url=cfg.ollama_base_url,
            temperature=temp,
        )
    elif provider == "openrouter":
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=cfg.openrouter_api_key,
            model=cfg.llm_model,
            temperature=temp,
        )
    else:  # gemini (default)
        from langchain_google_genai import ChatGoogleGenerativeAI

        llm = ChatGoogleGenerativeAI(
            model=cfg.llm_model,
            temperature=temp,
            google_api_key=cfg.gemini_api_key,
        )

    if bind_tools:
        return llm.bind_tools(bind_tools)

    return llm
