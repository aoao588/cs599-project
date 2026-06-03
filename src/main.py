"""CLI entry: ask a question through the Agentic RAG graph."""
from __future__ import annotations

import argparse
import os
import sys
import time

from .config import get_settings
from .graph.build import build_graph
from .graph.state import AgentState


def _enable_langsmith_if_configured() -> None:
    s = get_settings()
    if not s.langsmith_tracing or not s.langsmith_api_key:
        return
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = s.langsmith_api_key.get_secret_value()
    os.environ["LANGSMITH_PROJECT"] = s.langsmith_project


def run_once(question: str, show_trace: bool = False) -> None:
    graph = build_graph()
    init: AgentState = {
        "question": question,
        "rewrite_count": 0,
        "reflect_count": 0,
        "trace": [],
    }
    t0 = time.time()
    last = t0
    final: AgentState = {}  # type: ignore[assignment]
    # 流式执行：每个节点完成就打印耗时，便于实时观察进度 / 定位慢节点。
    # recursion_limit 是 LangGraph 兜底，避免任何剩余循环 bug 烧 token。
    for chunk in graph.stream(
        init, config={"recursion_limit": 15}, stream_mode="updates"
    ):
        for node_name, delta in chunk.items():
            now = time.time()
            print(f"  · {node_name:<10} {now - last:5.2f}s", file=sys.stderr, flush=True)
            last = now
            if isinstance(delta, dict):
                final.update(delta)  # type: ignore[arg-type]
    elapsed = time.time() - t0

    print("\n=== 答案 ===")
    print(final.get("answer") or "(空)")

    cits = final.get("citations") or []
    if cits:
        print("\n=== 引用 ===")
        for c in cits:
            print(f"[{c['id']}] {c['source']}")
            print(f"    {c['snippet']}")

    if show_trace:
        print("\n=== 轨迹 ===")
        for step in final.get("trace") or []:
            print(f"  - {step}")

    print(f"\n[耗时 {elapsed:.2f}s]")


def interactive() -> None:
    print("EnterpriseDocAgent — 输入问题，回车提问；输入 :q 退出。")
    while True:
        try:
            q = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if q in {":q", "quit", "exit"}:
            return
        if not q:
            continue
        try:
            run_once(q, show_trace=True)
        except Exception as e:
            print(f"[error] {type(e).__name__}: {e}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="EnterpriseDocAgent CLI")
    parser.add_argument("question", nargs="?", help="一次性提问；省略则进入交互模式")
    parser.add_argument("--trace", action="store_true", help="打印节点执行轨迹")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互模式")
    args = parser.parse_args()

    _enable_langsmith_if_configured()

    if args.interactive or not args.question:
        interactive()
    else:
        run_once(args.question, show_trace=args.trace)


if __name__ == "__main__":
    main()
