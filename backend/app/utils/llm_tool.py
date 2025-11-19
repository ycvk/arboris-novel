"""OpenAI 兼容型 LLM 工具封装，保持与旧项目一致的接口体验。."""

import os
from collections.abc import AsyncGenerator
from dataclasses import asdict, dataclass

from openai import AsyncOpenAI


@dataclass
class ChatMessage:
    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class LLMClient:
    """异步流式调用封装，兼容 OpenAI SDK。."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError("缺少 OPENAI_API_KEY 配置，请在数据库或环境变量中补全。")

        self._client = AsyncOpenAI(
            api_key=key, base_url=base_url or os.environ.get("OPENAI_API_BASE")
        )

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        response_format: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
        timeout: int = 120,
        **kwargs,
    ) -> AsyncGenerator[dict[str, str], None]:
        import logging

        logger = logging.getLogger(__name__)

        payload = {
            "model": model or os.environ.get("MODEL", "gpt-3.5-turbo"),
            "messages": [msg.to_dict() for msg in messages],
            "stream": True,
            "timeout": timeout,
            **kwargs,
        }
        if response_format:
            payload["response_format"] = {"type": response_format}
            logger.info(f"Using response_format: {payload['response_format']}")
        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        stream = await self._client.chat.completions.create(**payload)
        async for chunk in stream:
            # 兼容增量块中可能缺失 choices 或 delta 的情况
            choices = getattr(chunk, "choices", None)
            if not choices:
                continue
            choice = choices[0]
            delta = getattr(choice, "delta", None)
            content_piece = (
                getattr(delta, "content", None) if delta is not None else None
            )
            finish_reason = getattr(choice, "finish_reason", None)
            yield {
                "content": content_piece,
                "finish_reason": finish_reason,
            }
