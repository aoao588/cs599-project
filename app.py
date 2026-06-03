"""Streamlit Web UI for EnterpriseDocAgent.

运行：
    streamlit run app.py
"""
from __future__ import annotations

import os
import time

import streamlit as st

from src.config import get_settings
from src.graph.build import build_graph
from src.graph.state import AgentState

# ---------------------------------------------------------------------------
# 页面配置
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="EnterpriseDocAgent",
    page_icon="📚",
    layout="centered",
)

NODE_LABELS = {
    "router": "🧭 意图路由",
    "rewrite": "✍️ Query 改写",
    "retrieve": "🔍 向量检索",
    "grade": "⚖️ 检索评估",
    "generate": "🪄 生成答案",
    "reflect": "🔁 答案反思",
    "chitchat": "💬 闲聊回复",
}


def _enable_langsmith_if_configured() -> None:
    s = get_settings()
    if not s.langsmith_tracing or not s.langsmith_api_key:
        return
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = s.langsmith_api_key.get_secret_value()
    os.environ["LANGSMITH_PROJECT"] = s.langsmith_project


@st.cache_resource(show_spinner=False)
def get_graph():
    _enable_langsmith_if_configured()
    return build_graph()


# ---------------------------------------------------------------------------
# 侧边栏
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ 系统信息")
    s = get_settings()
    st.markdown(
        f"""
- **LLM**：`{s.deepseek_model}`
- **Embedding**：`{s.dashscope_embed_model}`
- **向量库**：Chroma（`{s.chroma_collection}`）
- **检索 top-k**：{s.retrieve_top_k}
- **最大反思轮数**：{s.max_reflect_rounds}
"""
    )
    st.divider()
    st.subheader("💡 试试这些问题")
    examples = [
        "入职 8 个月、累计工作 3 年的员工今年能休几天年假？",
        "代码评审有哪些必过门禁？",
        "出差住宿费报销标准是多少？",
        "hotfix 分支怎么处理？",
        "公司食堂几点开门？（知识库外，应拒答）",
    ]
    for ex in examples:
        if st.button(ex, use_container_width=True, key=f"ex_{ex}"):
            st.session_state["pending_question"] = ex

    st.divider()
    st.caption("方向一：Agentic AI 原生开发 · Agentic RAG")


# ---------------------------------------------------------------------------
# 主区
# ---------------------------------------------------------------------------
st.title("📚 EnterpriseDocAgent")
st.caption("企业知识库 Agentic RAG 问答 · 多步检索 · 带引用 · 拒绝幻觉")

# 初始化历史
if "history" not in st.session_state:
    st.session_state["history"] = []

# 渲染历史消息
for msg in st.session_state["history"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("citations"):
            with st.expander(f"📎 引用来源（{len(msg['citations'])}）"):
                for c in msg["citations"]:
                    st.markdown(f"**[{c['id']}] `{c['source']}`**")
                    st.caption(c["snippet"])
        if msg.get("trace"):
            with st.expander("🧩 执行轨迹"):
                for step in msg["trace"]:
                    st.text(f"• {step}")


def run_agent(question: str) -> None:
    """执行 Agent 并流式展示节点进度。"""
    # 用户消息
    st.session_state["history"].append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    graph = get_graph()
    init: AgentState = {
        "question": question,
        "rewrite_count": 0,
        "reflect_count": 0,
        "trace": [],
    }

    with st.chat_message("assistant"):
        status = st.status("🤖 Agent 正在思考…", expanded=True)
        final: AgentState = {}  # type: ignore[assignment]
        t0 = time.time()
        last = t0
        with status:
            for chunk in graph.stream(
                init, config={"recursion_limit": 15}, stream_mode="updates"
            ):
                for node_name, delta in chunk.items():
                    now = time.time()
                    label = NODE_LABELS.get(node_name, node_name)
                    st.write(f"{label} · {now - last:.2f}s")
                    last = now
                    if isinstance(delta, dict):
                        final.update(delta)  # type: ignore[arg-type]
        elapsed = time.time() - t0
        status.update(label=f"✅ 完成 · 耗时 {elapsed:.2f}s", state="complete", expanded=False)

        answer = final.get("answer") or "(无答案)"
        st.markdown(answer)

        citations = final.get("citations") or []
        if citations:
            with st.expander(f"📎 引用来源（{len(citations)}）"):
                for c in citations:
                    st.markdown(f"**[{c['id']}] `{c['source']}`**")
                    st.caption(c["snippet"])

        trace = final.get("trace") or []
        if trace:
            with st.expander("🧩 执行轨迹"):
                for step in trace:
                    st.text(f"• {step}")

    st.session_state["history"].append(
        {
            "role": "assistant",
            "content": answer,
            "citations": citations,
            "trace": trace,
        }
    )


# 处理来自示例按钮的待回答问题
pending = st.session_state.pop("pending_question", None)

# 聊天输入
typed = st.chat_input("输入你的问题，例如：年假怎么算？")

question = typed or pending
if question:
    try:
        run_agent(question)
    except Exception as e:  # noqa: BLE001
        st.error(f"出错了：{type(e).__name__}: {e}")
