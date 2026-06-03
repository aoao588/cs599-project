"""LangGraph nodes: router / rewrite / retrieve / grade / generate / reflect."""
from __future__ import annotations

from langchain_core.documents import Document

from ..config import get_settings
from ..llm import get_llm
from ..vectorstore import get_vectorstore
from .state import AgentState, Citation


def _append_trace(state: AgentState, step: str) -> list[str]:
    return [*state.get("trace", []), step]


# ---------------------------------------------------------------------------
# 1. Router — classify intent
# ---------------------------------------------------------------------------
_ROUTER_SYS = """你是企业知识 Agent 的意图分类器。
仅在以下两类中选一个，输出 JSON：
- "rag_qa"   : 涉及企业研发规范、HR 制度、财务/项目数据等需要查知识库的问题
- "chitchat" : 闲聊、问候、与企业知识无关

输出格式：{"route": "rag_qa" | "chitchat"}
"""


def node_router(state: AgentState) -> dict:
    llm = get_llm()
    out = llm.chat_json(
        [
            {"role": "system", "content": _ROUTER_SYS},
            {"role": "user", "content": state["question"]},
        ]
    )
    route = out.get("route", "rag_qa")
    if route not in {"rag_qa", "chitchat"}:
        route = "rag_qa"
    return {"route": route, "trace": _append_trace(state, f"router→{route}")}


# ---------------------------------------------------------------------------
# 2. Rewrite — HyDE-ish query expansion + sub-question decomposition
# ---------------------------------------------------------------------------
_REWRITE_SYS = """你是检索助手，需要把用户问题改写为更适合向量检索的若干查询。

要求：
- 生成 1~3 条改写 query，覆盖不同角度（同义改写、子问题、关键术语展开）
- 每条 query 自包含、不超过 60 字
- 输出 JSON：{"subqueries": ["...", "..."]}
"""


def node_rewrite(state: AgentState) -> dict:
    llm = get_llm()
    rewrite_count = int(state.get("rewrite_count", 0)) + 1
    user = state["question"]
    if rewrite_count > 1:
        user = (
            f"原问题：{state['question']}\n"
            f"上一轮检索质量不足，请换一个角度生成新的检索 query。"
        )
    out = llm.chat_json(
        [
            {"role": "system", "content": _REWRITE_SYS},
            {"role": "user", "content": user},
        ]
    )
    subs = out.get("subqueries") or [state["question"]]
    subs = [s.strip() for s in subs if isinstance(s, str) and s.strip()]
    if not subs:
        subs = [state["question"]]
    return {
        "subqueries": subs[:3],
        "rewritten_query": subs[0],
        "rewrite_count": rewrite_count,
        "trace": _append_trace(state, f"rewrite#{rewrite_count}→{len(subs)} queries"),
    }


# ---------------------------------------------------------------------------
# 3. Retrieve — multi-query retrieval, dedup by (source, content_prefix)
# ---------------------------------------------------------------------------
def node_retrieve(state: AgentState) -> dict:
    vs = get_vectorstore()
    top_k = get_settings().retrieve_top_k
    seen: set[tuple[str, str]] = set()
    merged: list[Document] = []
    for q in state.get("subqueries") or [state["question"]]:
        for doc in vs.similarity_search(q, k=top_k):
            key = (doc.metadata.get("source", ""), doc.page_content[:80])
            if key in seen:
                continue
            seen.add(key)
            merged.append(doc)
    # Cap to a manageable context window
    merged = merged[: top_k * 2]
    return {
        "docs": merged,
        "trace": _append_trace(state, f"retrieve→{len(merged)} docs"),
    }


# ---------------------------------------------------------------------------
# 4. Grade — judge retrieval sufficiency
# ---------------------------------------------------------------------------
_GRADE_SYS = """你是检索质量评估员。判断检索片段是否**包含回答问题所需的原料**。
重要：你不需要片段里直接出现最终答案——只要片段包含相关规则、公式、定义、表格，就算 relevant。
推理与计算是下游 generate 节点的工作，不是 grade 的职责。

输出 JSON：{"grade": "relevant" | "partial" | "irrelevant", "reason": "一句话"}

判定标准：
- relevant   : 片段中存在能用于推导/计算/查表得到答案的关键条款、公式或数据
- partial    : 只覆盖问题的一部分子主题，缺关键条款（例如问"年假怎么算"但只找到入职流程）
- irrelevant : 主题完全不对（例如问年假却只找到代码评审规范）

注意：宁可宽松判 relevant，让 generate 去推理；不要因为"答案没直接写出来"就判 partial。
"""


def _format_docs_for_grade(docs: list[Document], limit: int = 8) -> str:
    lines = []
    for i, d in enumerate(docs[:limit], 1):
        src = d.metadata.get("source", "?")
        snippet = d.page_content.replace("\n", " ")[:240]
        lines.append(f"[{i}] ({src}) {snippet}")
    return "\n".join(lines) if lines else "(无)"


def node_grade(state: AgentState) -> dict:
    llm = get_llm()
    out = llm.chat_json(
        [
            {"role": "system", "content": _GRADE_SYS},
            {
                "role": "user",
                "content": (
                    f"问题：{state['question']}\n\n"
                    f"检索片段：\n{_format_docs_for_grade(state.get('docs', []))}"
                ),
            },
        ]
    )
    grade = out.get("grade", "partial")
    if grade not in {"relevant", "partial", "irrelevant"}:
        grade = "partial"
    reason = str(out.get("reason", "")).strip()[:80]
    label = f"grade→{grade}" + (f" ({reason})" if reason else "")
    return {"grade": grade, "trace": _append_trace(state, label)}


# ---------------------------------------------------------------------------
# 5. Generate — produce final answer with inline citations
# ---------------------------------------------------------------------------
_GENERATE_SYS = """你是企业知识助手。基于「检索片段」回答用户问题。

强约束：
1. 只能使用给定片段中的信息；片段中没有的，直接说"未在知识库中找到相关依据"。
2. **如果用户问题包含可计算的条件（如时长、金额、人数），而片段中有相关公式/表格/折算规则，必须显式应用它进行推算，不要只抄一条表格行就结束。**
3. **如果片段中存在多条可联立适用的条款，要把它们组合起来回答**（例如先查表得标准值，再用折算公式调整）。
4. 在每个事实点末尾用 [n] 标注引用编号，对应片段编号。
5. 如果推算需要用户未提供的变量（例如具体入职月份），明确指出该变量并给出"以 X 月入职为例"的示例计算。
6. 回答简洁、结构清晰；必要时分点。
7. 输出 JSON：{"answer": "带 [n] 角标的回答", "used_ids": [1,3]}
"""


def node_generate(state: AgentState) -> dict:
    docs = state.get("docs", [])

    # 知识库不覆盖该主题：直接给标准化"未找到"答案，省一次 LLM 调用，
    # 且不附任何引用（避免出现"未找到 + 一堆无关引用"的矛盾）。
    if state.get("grade") == "irrelevant":
        return {
            "answer": "未在知识库中找到与该问题相关的依据。",
            "citations": [],
            "trace": _append_trace(state, "generate→no_answer"),
        }

    llm = get_llm()
    out = llm.chat_json(
        [
            {"role": "system", "content": _GENERATE_SYS},
            {
                "role": "user",
                "content": (
                    f"问题：{state['question']}\n\n"
                    f"检索片段：\n{_format_docs_for_grade(docs, limit=10)}"
                ),
            },
        ]
    )
    answer = out.get("answer", "")
    # 不再兜底"列出全部 docs"——LLM 没标注引用时就返回空，避免无关引用。
    used_ids = out.get("used_ids") or []

    citations: list[Citation] = []
    for cid in used_ids:
        idx = int(cid) - 1
        if 0 <= idx < len(docs):
            d = docs[idx]
            citations.append(
                {
                    "id": int(cid),
                    "source": d.metadata.get("source", "?"),
                    "snippet": d.page_content.replace("\n", " ")[:200],
                }
            )
    return {
        "answer": answer,
        "citations": citations,
        "trace": _append_trace(state, "generate"),
    }


# ---------------------------------------------------------------------------
# 6. Reflect — does the answer actually address the question?
# ---------------------------------------------------------------------------
_REFLECT_SYS = """你是答案质量审查员。判断答案是否真正回答了用户问题、是否忠于检索片段。
输出 JSON：{"pass": true | false, "reason": "一句话"}

判定不通过的典型情况：
- 答非所问
- 出现片段中没有的关键事实（疑似幻觉）
- 关键信息缺失，回答过于笼统
"""


def node_reflect(state: AgentState) -> dict:
    llm = get_llm()
    out = llm.chat_json(
        [
            {"role": "system", "content": _REFLECT_SYS},
            {
                "role": "user",
                "content": (
                    f"问题：{state['question']}\n\n"
                    f"答案：{state.get('answer', '')}\n\n"
                    f"检索片段：\n{_format_docs_for_grade(state.get('docs', []))}"
                ),
            },
        ]
    )
    passed = bool(out.get("pass", True))
    reflect_count = int(state.get("reflect_count", 0)) + (0 if passed else 1)
    # If failed, downgrade the grade so the conditional edge re-routes to rewrite.
    new_grade = state.get("grade", "relevant") if passed else "partial"
    return {
        "reflect_count": reflect_count,
        "grade": new_grade,
        "trace": _append_trace(state, f"reflect→{'pass' if passed else 'retry'}"),
    }


# ---------------------------------------------------------------------------
# Chitchat — short, polite, non-knowledge-base reply
# ---------------------------------------------------------------------------
_CHITCHAT_SYS = """你是企业知识助手。当前是闲聊场景，请简短礼貌回应，
并提醒用户：你的主要能力是回答企业研发规范、HR 制度、财务数据等知识库问题。
直接输出文本，不要 JSON。"""


def node_chitchat(state: AgentState) -> dict:
    llm = get_llm()
    answer = llm.chat(
        [
            {"role": "system", "content": _CHITCHAT_SYS},
            {"role": "user", "content": state["question"]},
        ]
    )
    return {
        "answer": answer,
        "citations": [],
        "trace": _append_trace(state, "chitchat"),
    }
