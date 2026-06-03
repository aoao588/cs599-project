"""Shared state object flowing through the LangGraph nodes."""
from __future__ import annotations

from typing import Literal, TypedDict

from langchain_core.documents import Document

Route = Literal["rag_qa", "chitchat"]
Grade = Literal["relevant", "partial", "irrelevant"]


class Citation(TypedDict):
    id: int
    source: str
    snippet: str


class AgentState(TypedDict, total=False):
    # --- input ---
    question: str

    # --- router ---
    route: Route

    # --- retrieval loop ---
    rewritten_query: str
    subqueries: list[str]
    docs: list[Document]
    grade: Grade
    rewrite_count: int   # 总共调用 rewrite 的次数，统一上限控制
    reflect_count: int   # 仅 reflect 节点判定失败的次数（用于调试展示）

    # --- output ---
    answer: str
    citations: list[Citation]

    # --- debug ---
    trace: list[str]
