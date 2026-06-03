"""Chroma persistent vector store, wired with 通义 embeddings."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import chromadb
from langchain_chroma import Chroma

from .config import get_settings
from .embeddings import get_embeddings


def _persist_path() -> Path:
    p = Path(get_settings().chroma_persist_dir).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


@lru_cache(maxsize=1)
def get_vectorstore() -> Chroma:
    s = get_settings()
    client = chromadb.PersistentClient(path=str(_persist_path()))
    return Chroma(
        client=client,
        collection_name=s.chroma_collection,
        embedding_function=get_embeddings(),
    )


def reset_collection() -> None:
    """Drop and recreate the collection. Used by full re-ingest."""
    s = get_settings()
    client = chromadb.PersistentClient(path=str(_persist_path()))
    try:
        client.delete_collection(s.chroma_collection)
    except Exception:
        pass
    get_vectorstore.cache_clear()
