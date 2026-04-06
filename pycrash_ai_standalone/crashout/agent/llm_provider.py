"""LLM provider abstraction - supports Claude (Anthropic) and OpenAI.

Usage:
    provider = get_provider()  # auto-detects from env vars
    result = await provider.extract(text, tools)

Set one of these env vars:
    ANTHROPIC_API_KEY=sk-ant-...   -> uses Claude
    OPENAI_API_KEY=sk-...          -> uses OpenAI
"""
from __future__ import annotations

import os
import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    """Represents a tool call from the LLM."""
    name: str
    input: Dict[str, Any]
    id: str = ""


@dataclass
class LLMResponse:
    """Normalized response from any LLM provider."""
    tool_calls: List[ToolCall] = field(default_factory=list)
    text: str = ""
    model: str = ""
    usage: Dict[str, int] = field(default_factory=dict)


class LLMProvider(ABC):
    """Abstract base for LLM providers."""

    @abstractmethod
    async def complete(
        self,
        system: str,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...


class AnthropicProvider(LLMProvider):
    """Claude via Anthropic API."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key
        self.model = model

    @property
    def name(self) -> str:
        return f"anthropic/{self.model}"

    async def complete(
        self,
        system: str,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key)

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        message = client.messages.create(**kwargs)

        tool_calls = []
        text_parts = []

        for block in message.content:
            if block.type == "tool_use":
                tool_calls.append(ToolCall(
                    name=block.name,
                    input=block.input,
                    id=block.id,
                ))
            elif block.type == "text":
                text_parts.append(block.text)

        return LLMResponse(
            tool_calls=tool_calls,
            text="\n".join(text_parts),
            model=message.model,
            usage={
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens,
            },
        )


class OpenAIProvider(LLMProvider):
    """GPT via OpenAI API."""

    def __init__(self, api_key: str, model: str = "gpt-4o",
                 base_url: Optional[str] = None):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    @property
    def name(self) -> str:
        return f"openai/{self.model}"

    def _convert_tools_to_openai(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert Anthropic-style tool defs to OpenAI function calling format."""
        openai_tools = []
        for tool in tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {}),
                },
            })
        return openai_tools

    async def complete(
        self,
        system: str,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        import openai

        client_kwargs: Dict[str, Any] = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url

        client = openai.OpenAI(**client_kwargs)

        oai_messages = [{"role": "system", "content": system}]
        for msg in messages:
            oai_messages.append(msg)

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": oai_messages,
        }
        if tools:
            kwargs["tools"] = self._convert_tools_to_openai(tools)

        response = client.chat.completions.create(**kwargs)
        choice = response.choices[0]

        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(ToolCall(
                    name=tc.function.name,
                    input=json.loads(tc.function.arguments),
                    id=tc.id,
                ))

        return LLMResponse(
            tool_calls=tool_calls,
            text=choice.message.content or "",
            model=response.model,
            usage={
                "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                "output_tokens": response.usage.completion_tokens if response.usage else 0,
            },
        )


class MockProvider(LLMProvider):
    """Mock provider for testing without API keys."""

    @property
    def name(self) -> str:
        return "mock"

    async def complete(
        self,
        system: str,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        return LLMResponse(
            tool_calls=[],
            text="[Mock LLM - set ANTHROPIC_API_KEY or OPENAI_API_KEY]",
            model="mock",
        )


def get_provider(
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> LLMProvider:
    """Get LLM provider from args or environment.

    Priority:
    1. Explicit provider/api_key args
    2. ANTHROPIC_API_KEY env var -> Claude
    3. OPENAI_API_KEY env var -> GPT
    4. MockProvider (no API key)
    """
    if provider == "anthropic" or (not provider and api_key and api_key.startswith("sk-ant")):
        return AnthropicProvider(
            api_key=api_key or os.getenv("ANTHROPIC_API_KEY", ""),
            model=model or "claude-sonnet-4-20250514",
        )

    if provider == "openai" or (not provider and api_key and not api_key.startswith("sk-ant")):
        return OpenAIProvider(
            api_key=api_key or os.getenv("OPENAI_API_KEY", ""),
            model=model or "gpt-4o",
            base_url=base_url,
        )

    # Auto-detect from env
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        return AnthropicProvider(
            api_key=anthropic_key,
            model=model or "claude-sonnet-4-20250514",
        )

    openai_key = os.getenv("OPENAI_API_KEY", "")
    if openai_key:
        return OpenAIProvider(
            api_key=openai_key,
            model=model or "gpt-4o",
            base_url=base_url or os.getenv("OPENAI_BASE_URL"),
        )

    return MockProvider()
