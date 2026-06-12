"""生成报告用架构图 PNG（matplotlib，中文）。
运行：python scripts/draw_diagrams.py  → 输出到 docs/diagrams/
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

OUT = Path("docs/diagrams")
OUT.mkdir(parents=True, exist_ok=True)

BLUE = "#d1ecf1"
YELLOW = "#fff3cd"
GREEN = "#d4edda"
GRAY = "#e9ecef"
ORANGE = "#ffe5d0"


def box(ax, x, y, w, h, text, fc=BLUE, ec="#34495e", fs=11, bold=False):
    p = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        fc=fc, ec=ec, lw=1.4, zorder=2,
    )
    ax.add_patch(p)
    ax.text(
        x + w / 2, y + h / 2, text, ha="center", va="center",
        fontsize=fs, zorder=3, fontweight="bold" if bold else "normal",
    )


def arrow(ax, p1, p2, text="", color="#34495e", rad=0.0, fs=9):
    a = FancyArrowPatch(
        p1, p2, arrowstyle="-|>", mutation_scale=14, color=color, lw=1.4,
        connectionstyle=f"arc3,rad={rad}", zorder=1,
    )
    ax.add_patch(a)
    if text:
        mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
        ax.text(mx, my, text, fontsize=fs, color=color, ha="center", va="center",
                bbox=dict(fc="white", ec="none", pad=0.5), zorder=4)


def band(ax, x, y, w, h, label, fc):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.01,rounding_size=0.05",
                                fc=fc, ec="#adb5bd", lw=1.0, alpha=0.35, zorder=0))
    ax.text(x + 0.15, y + h - 0.25, label, fontsize=10, color="#555", ha="left", va="top",
            style="italic", zorder=1)


# ---------------------------------------------------------------------------
# 图 1：总体分层架构
# ---------------------------------------------------------------------------
def fig_layered():
    fig, ax = plt.subplots(figsize=(11, 8))
    ax.set_xlim(0, 16); ax.set_ylim(0, 12); ax.axis("off")

    band(ax, 0.3, 9.6, 15.4, 1.9, "接入层 Interface", BLUE)
    box(ax, 3.5, 9.9, 3.2, 1.1, "CLI\nsrc/main.py", "#ffffff", fs=11)
    box(ax, 9.3, 9.9, 3.2, 1.1, "Streamlit Web UI\napp.py", "#ffffff", fs=11)

    band(ax, 0.3, 6.2, 15.4, 2.9, "Agent 编排层  LangGraph StateGraph", YELLOW)
    nodes = ["router", "rewrite", "retrieve", "grade", "generate", "reflect"]
    nx = 0.7
    centers = []
    for n in nodes:
        box(ax, nx, 7.2, 2.25, 1.0, n, "#ffffff", fs=10, bold=True)
        centers.append(nx + 1.125)
        nx += 2.5
    for i in range(len(centers) - 1):
        arrow(ax, (centers[i] + 0.0, 7.7), (centers[i] + 1.25, 7.7))
    # 反馈环（grade/reflect 回 rewrite）
    arrow(ax, (centers[3], 7.2), (centers[1], 7.2), "不足则重检", color="#c0392b", rad=-0.35, fs=8)

    band(ax, 0.3, 3.0, 15.4, 2.7, "服务层 Services", GREEN)
    box(ax, 1.2, 3.7, 3.6, 1.2, "LLM Client\nsrc/llm.py", "#ffffff", fs=10)
    box(ax, 6.2, 3.7, 3.6, 1.2, "Embedding Client\nsrc/embeddings.py", "#ffffff", fs=10)
    box(ax, 11.2, 3.7, 3.6, 1.2, "Chroma 向量库\nsrc/vectorstore.py", "#ffffff", fs=10)

    band(ax, 0.3, 0.3, 15.4, 2.1, "外部 API（OpenAI 兼容协议）", GRAY)
    box(ax, 1.2, 0.7, 3.6, 1.1, "DeepSeek API\ndeepseek-chat", ORANGE, fs=10)
    box(ax, 11.2, 0.7, 3.6, 1.1, "DashScope API\ntext-embedding-v3", ORANGE, fs=10)

    # 跨层箭头
    arrow(ax, (5.1, 9.9), (5.1, 8.25))   # CLI -> agent
    arrow(ax, (10.9, 9.9), (10.9, 8.25)) # UI -> agent
    arrow(ax, (3.0, 7.2), (3.0, 4.9))    # agent -> LLM
    arrow(ax, (13.0, 7.2), (13.0, 4.9))  # agent -> Chroma
    arrow(ax, (11.2, 4.3), (9.8, 4.3))   # Chroma -> Embedding
    arrow(ax, (3.0, 3.7), (3.0, 1.8))    # LLM -> DeepSeek
    arrow(ax, (13.0, 3.7), (13.0, 1.8))  # Embedding/Chroma -> DashScope

    plt.tight_layout()
    fig.savefig(OUT / "fig1_layered.png", dpi=170, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# 图 2：LangGraph 状态机
# ---------------------------------------------------------------------------
def fig_statemachine():
    fig, ax = plt.subplots(figsize=(9, 11))
    ax.set_xlim(0, 12); ax.set_ylim(0, 16); ax.axis("off")

    def n(x, y, t, fc=BLUE, w=3.0, h=0.95, **k):
        box(ax, x, y, w, h, t, fc, **k); return (x + w / 2, y, x + w / 2, y + h)

    # 主链（竖直）
    box(ax, 4.5, 14.7, 3.0, 0.8, "START", GRAY, bold=True)
    n(4.0, 13.2, "router\n意图分类", YELLOW, w=4.0)
    n(4.0, 11.5, "rewrite\n多 query 改写", w=4.0)
    n(4.0, 9.9, "retrieve\n向量检索 + 去重", w=4.0)
    n(4.0, 8.3, "grade\n检索质量评估", YELLOW, w=4.0)
    n(4.0, 6.5, "generate\n带引用作答", w=4.0)
    n(4.0, 4.8, "reflect\n答案反思", YELLOW, w=4.0)
    box(ax, 4.5, 3.1, 3.0, 0.8, "END", GRAY, bold=True)
    n(0.2, 13.2, "chitchat\n闲聊回复", GREEN, w=3.0, fs=10)

    cx = 6.0  # 主链中心 x
    arrow(ax, (cx, 14.7), (cx, 14.15))               # start->router
    arrow(ax, (cx, 13.2), (cx, 12.45), "rag_qa")     # router->rewrite
    arrow(ax, (4.0, 13.6), (3.2, 13.6), "chitchat")  # router->chitchat
    arrow(ax, (cx, 11.5), (cx, 10.85))               # rewrite->retrieve
    arrow(ax, (cx, 9.9), (cx, 9.25))                 # retrieve->grade
    arrow(ax, (cx, 8.3), (cx, 7.45), "relevant")     # grade->generate
    arrow(ax, (cx, 6.5), (cx, 5.75), "正常")          # generate->reflect
    arrow(ax, (cx, 4.8), (cx, 3.9), "pass")          # reflect->END
    arrow(ax, (1.7, 13.2), (1.7, 3.5))               # chitchat->END (left rail)
    arrow(ax, (1.7, 3.5), (4.5, 3.5))

    # 反馈环：grade(partial)->rewrite, reflect(fail)->rewrite
    arrow(ax, (8.0, 8.75), (8.0, 11.95), "partial\n重检", color="#c0392b", rad=-0.3, fs=9)
    arrow(ax, (8.0, 5.25), (8.0, 11.95), "fail\n重试", color="#c0392b", rad=-0.45, fs=9)
    # grade irrelevant -> generate (早退)
    arrow(ax, (4.0, 8.5), (4.0, 7.45), "irrelevant\n早退", color="#7f8c8d", rad=0.3, fs=8)
    # generate 未找到 -> END
    arrow(ax, (4.0, 6.6), (4.0, 3.9), "未找到", color="#7f8c8d", rad=0.4, fs=8)

    ax.text(6, 15.7, "LangGraph 状态机：黄=决策节点，蓝/绿=执行节点，红=反馈环",
            ha="center", fontsize=10, color="#555")
    plt.tight_layout()
    fig.savefig(OUT / "fig2_statemachine.png", dpi=170, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# 图 3：朴素 RAG vs Agentic RAG
# ---------------------------------------------------------------------------
def fig_compare():
    fig, ax = plt.subplots(figsize=(12, 6.5))
    ax.set_xlim(0, 16); ax.set_ylim(0, 9); ax.axis("off")

    band(ax, 0.3, 0.4, 6.0, 8.2, "朴素 RAG (baseline)", GRAY)
    seq = ["Query", "Retrieve", "Generate", "Answer"]
    y = 7.0
    cyc = []
    for i, t in enumerate(seq):
        fc = ORANGE if t in ("Query", "Answer") else "#ffffff"
        box(ax, 1.7, y, 3.2, 0.9, t, fc, fs=11, bold=True)
        cyc.append(y)
        y -= 2.0
    for i in range(len(cyc) - 1):
        arrow(ax, (3.3, cyc[i]), (3.3, cyc[i + 1] + 0.9))
    ax.text(3.3, 0.7, "一次检索定胜负\n→ 复杂条款易漏检", ha="center", fontsize=9, color="#c0392b")

    band(ax, 7.0, 0.4, 8.7, 8.2, "Agentic RAG (ours)", YELLOW)
    box(ax, 8.2, 7.4, 2.6, 0.85, "Query", ORANGE, fs=11, bold=True)
    box(ax, 8.2, 5.9, 2.6, 0.85, "rewrite\n多查询改写", "#ffffff", fs=10)
    box(ax, 8.2, 4.4, 2.6, 0.85, "retrieve", "#ffffff", fs=10)
    box(ax, 8.2, 2.9, 2.6, 0.85, "grade", YELLOW, fs=10)
    box(ax, 12.2, 4.4, 2.6, 0.85, "generate", "#ffffff", fs=10)
    box(ax, 12.2, 2.9, 2.6, 0.85, "reflect", YELLOW, fs=10)
    box(ax, 12.2, 1.2, 2.6, 0.85, "Answer", ORANGE, fs=11, bold=True)

    arrow(ax, (9.5, 7.4), (9.5, 6.75))
    arrow(ax, (9.5, 5.9), (9.5, 5.25))
    arrow(ax, (9.5, 4.4), (9.5, 3.75))
    arrow(ax, (10.8, 3.3), (12.2, 4.6), "充分")
    arrow(ax, (10.8, 3.1), (10.8, 6.05), "不足", color="#c0392b", rad=-0.6, fs=9)
    arrow(ax, (13.5, 4.4), (13.5, 3.75))
    arrow(ax, (13.5, 2.9), (13.5, 2.05), "pass")
    arrow(ax, (12.2, 3.3), (10.8, 6.0), "不通过", color="#c0392b", rad=0.3, fs=9)
    ax.text(11.3, 0.7, "改写—评估—反思反馈环 → 复杂问题更稳健", ha="center", fontsize=9, color="#1e7e34")

    plt.tight_layout()
    fig.savefig(OUT / "fig3_compare.png", dpi=170, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    fig_layered()
    fig_statemachine()
    fig_compare()
    print("已生成:", *[p.name for p in sorted(OUT.glob("*.png"))])
