"""朴素 RAG baseline：单轮 retrieve → generate。

与 Agentic RAG 的差异（对照实验的核心）：
- 无 router       ：不判断意图
- 无 rewrite      ：用原始 question 单次检索（不做多 query 改写/HyDE）
- 无 grade        ：不评估检索质量、不重检
- 无 reflect      ：不反思答案、不重试
即经典的「一次检索 + 一次生成」流水线。
"""
from __future__ import annotations

from langchain_core.documents import Document

from .config import get_settings
from .llm import get_llm

_NAIVE_SYS = """你是企业知识助手。请根据下面提供的检索片段回答用户问题。
- 只能使用检索片段中的信息；片段中没有相关信息时，回答"未在知识库中找到相关依据"。
- 在引用到的事实点末尾用 [n] 标注对应片段编号。
输出 JSON：{"answer": "带 [n] 角标的回答"}"""


def _format_docs(docs: list[Document]) -> str:
    lines = []
    for i, d in enumerate(docs, 1):
        src = d.metadata.get("source", "?")
        snippet = d.page_content.replace("\n", " ")[:240]
        lines.append(f"[{i}] ({src}) {snippet}")
    return "\n".join(lines) if lines else "(无)"


def naive_rag(question: str) -> tuple[str, list[str]]:
    """单轮朴素 RAG，返回 (答案, 检索到的 context 文本列表)。"""
    # 延迟导入，避免与评估脚本顶部的 vertexai stub 顺序耦合
    from .vectorstore import get_vectorstore

    vs = get_vectorstore()
    top_k = get_settings().retrieve_top_k
    docs = vs.similarity_search(question, k=top_k)

    out = get_llm().chat_json(
        [
            {"role": "system", "content": _NAIVE_SYS},
            {
                "role": "user",
                "content": f"问题：{question}\n\n检索片段：\n{_format_docs(docs)}",
            },
        ]
    )
    answer = out.get("answer", "") or ""
    contexts = [d.page_content for d in docs]
    return answer, contexts
