"""LLM provider abstraction for agent runtime."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.services.agent.models import LLMProviderConfig

logger = logging.getLogger(__name__)


class LLMRouter:
    """OpenAI-compatible router with light provider abstraction."""

    def __init__(self, default_config: Optional[LLMProviderConfig] = None, retries: int = 2):
        self.default_config = default_config or LLMProviderConfig()
        self.retries = retries

    def count_tokens(self, text: str, model: Optional[str] = None) -> int:
        try:
            import tiktoken  # type: ignore

            encoding = tiktoken.encoding_for_model(model or self.default_config.model)
            return len(encoding.encode(text or ""))
        except Exception:
            return max(1, len(text or "") // 4)

    async def complete(
        self,
        messages: List[Dict[str, Any]],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        config: Optional[LLMProviderConfig] = None,
    ) -> Dict[str, Any]:
        router_config = config or self.default_config
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                return await self._complete_once(messages, tools=tools, config=router_config)
            except Exception as exc:
                last_error = exc
                logger.warning("LLM call failed on attempt %s: %s", attempt + 1, exc)
                if attempt >= self.retries:
                    break
                await asyncio.sleep(min(2 ** attempt, 3))
        raise RuntimeError(f"LLM request failed: {last_error}") from last_error

    async def stream_complete(
        self,
        messages: List[Dict[str, Any]],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        config: Optional[LLMProviderConfig] = None,
    ) -> AsyncGenerator[str, None]:
        response = await self.complete(messages, tools=tools, config=config)
        text = response.get("content", "")
        if not text:
            return
        chunk_size = 120
        for index in range(0, len(text), chunk_size):
            yield text[index:index + chunk_size]

    async def _complete_once(
        self,
        messages: List[Dict[str, Any]],
        *,
        tools: Optional[List[Dict[str, Any]]],
        config: LLMProviderConfig,
    ) -> Dict[str, Any]:
        try:
            from openai import AsyncOpenAI  # type: ignore
        except Exception as exc:
            raise RuntimeError("openai package is required for LLM routing") from exc

        # Auto-detect base_url for known providers
        base_url = config.base_url
        if not base_url:
            if config.provider == "ollama":
                base_url = "http://host.docker.internal:11434/v1"
            elif config.provider == "ollama-local":
                base_url = "http://localhost:11434/v1"

        client = AsyncOpenAI(
            api_key=config.api_key or "ollama",
            base_url=base_url,
        )
        payload: Dict[str, Any] = {
            "model": config.model,
            "messages": messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        response = await client.chat.completions.create(**payload)
        choice = response.choices[0]
        message = choice.message
        tool_calls = []
        for tool_call in getattr(message, "tool_calls", []) or []:
            tool_calls.append(
                {
                    "id": tool_call.id,
                    "type": getattr(tool_call, "type", "function"),
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
            )
        return {
            "content": message.content or "",
            "tool_calls": tool_calls,
            "finish_reason": choice.finish_reason,
            "usage": {
                "prompt_tokens": getattr(response.usage, "prompt_tokens", 0) if getattr(response, "usage", None) else 0,
                "completion_tokens": getattr(response.usage, "completion_tokens", 0) if getattr(response, "usage", None) else 0,
            },
        }
