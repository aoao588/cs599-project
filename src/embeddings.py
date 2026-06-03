"""通义千问 (DashScope) embedding client, OpenAI-compatible endpoint."""
from __future__ import annotations

from functools import lru_cache

from langchain_core.embeddings import Embeddings
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import get_settings

# DashScope OpenAI-compatible embeddings: max 10 inputs per call.
_BATCH_SIZE = 10


class DashScopeEmbeddings(Embeddings):
    def __init__(self) -> None:
        s = get_settings()
        self._client = OpenAI(
            api_key=s.dashscope_api_key.get_secret_value(),
            base_url=s.dashscope_base_url,
            timeout=s.request_timeout,
            max_retries=0,
        )
        self._model = s.dashscope_embed_model

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.embeddings.create(model=self._model, input=texts)
        # OpenAI SDK guarantees data order matches input order.
        return [item.embedding for item in resp.data]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), _BATCH_SIZE):
            out.extend(self._embed_batch(texts[i : i + _BATCH_SIZE]))
        return out

    def embed_query(self, text: str) -> list[float]:
        return self._embed_batch([text])[0]


@lru_cache(maxsize=1)
def get_embeddings() -> DashScopeEmbeddings:
    return DashScopeEmbeddings()
