"""Compile the LangGraph StateGraph for EnterpriseDocAgent."""
from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from ..config import get_settings
from .nodes import (
    node_chitchat,
    node_generate,
    node_grade,
    node_reflect,
    node_retrieve,
    node_rewrite,
    node_router,
)
from .state import AgentState


def _route_after_router(state: AgentState) -> str:
    return "chitchat" if state.get("route") == "chitchat" else "rewrite"


def _route_after_grade(state: AgentState) -> str:
    """relevant → generate; partial → rewrite（多轮重试）; irrelevant → 早退到 generate。

    设计意图：
    - relevant：检索到原料，直接生成答案
    - partial：相关但缺细节，值得改写 query 再查（共享 rewrite_count 预算）
    - irrelevant：主题完全不在知识库里，再多改写也无意义。允许 1 次改写
      容错（防止首轮 query 烂导致的误判），第 2 次仍 irrelevant 就早退到 generate，
      generate 会输出"未在知识库中找到相关依据"。
    """
    grade = state.get("grade", "relevant")
    count = int(state.get("rewrite_count", 0))

    if grade == "relevant":
        return "generate"
    if grade == "irrelevant" and count >= 1:
        return "generate"   # 早退：知识库不覆盖此主题
    if count >= 1 + get_settings().max_reflect_rounds:
        return "generate"   # partial 预算耗尽，best-effort 作答
    return "rewrite"


def _route_after_generate(state: AgentState) -> str:
    """irrelevant（"未找到"答案）无需反思，直接结束；正常答案才走 reflect。"""
    if state.get("grade") == "irrelevant":
        return END
    return "reflect"


def _route_after_reflect(state: AgentState) -> str:
    """reflect 最多触发 1 次重试，避免和 grade 重试叠加导致放大循环。"""
    # 答案已通过 reflect（pass=True 时 node_reflect 不改 grade）
    if state.get("grade") == "relevant":
        return END
    # 任何已经做过 1 次 reflect 失败的情况，直接结束（best-effort 已给）
    if int(state.get("reflect_count", 0)) >= 1:
        return END
    # 总预算上限
    if int(state.get("rewrite_count", 0)) >= 1 + get_settings().max_reflect_rounds:
        return END
    return "rewrite"


@lru_cache(maxsize=1)
def build_graph():
    g: StateGraph = StateGraph(AgentState)

    g.add_node("router", node_router)
    g.add_node("rewrite", node_rewrite)
    g.add_node("retrieve", node_retrieve)
    g.add_node("grade", node_grade)
    g.add_node("generate", node_generate)
    g.add_node("reflect", node_reflect)
    g.add_node("chitchat", node_chitchat)

    g.add_edge(START, "router")
    g.add_conditional_edges(
        "router",
        _route_after_router,
        {"rewrite": "rewrite", "chitchat": "chitchat"},
    )
    g.add_edge("rewrite", "retrieve")
    g.add_edge("retrieve", "grade")
    g.add_conditional_edges(
        "grade",
        _route_after_grade,
        {"generate": "generate", "rewrite": "rewrite"},
    )
    g.add_conditional_edges(
        "generate",
        _route_after_generate,
        {"reflect": "reflect", END: END},
    )
    g.add_conditional_edges(
        "reflect",
        _route_after_reflect,
        {"rewrite": "rewrite", END: END},
    )
    g.add_edge("chitchat", END)

    return g.compile()
