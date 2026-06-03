"""DeepSeek LLM client (OpenAI-compatible) with JSON-mode helper."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import get_settings


class LLMClient:
    def __init__(self) -> None:
        s = get_settings()
        self._client = OpenAI(
            api_key=s.deepseek_api_key.get_secret_value(),
            base_url=s.deepseek_base_url,
            timeout=s.request_timeout,
            max_retries=0,  # 重试统一交给 tenacity，避免 SDK 内置重试叠加
        )
        self._model = s.deepseek_model

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.2) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
        )
        return resp.choices[0].message.content or ""

    def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Force JSON output. Retries once with a stricter system nudge on parse failure."""
        try:
            return self._call_json(messages, temperature)
        except json.JSONDecodeError:
            patched = [
                {
                    "role": "system",
                    "content": "你的上一次输出不是合法 JSON。本次必须严格输出可被 json.loads 解析的 JSON 对象，不要任何额外文字。",
                },
                *messages,
            ]
            return self._call_json(patched, temperature)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _call_json(self, messages: list[dict[str, str]], temperature: float) -> dict[str, Any]:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        return json.loads(raw)


@lru_cache(maxsize=1)
def get_llm() -> LLMClient:
    return LLMClient()
