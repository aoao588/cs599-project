"""Ragas 评估脚本：量化 Agentic RAG 的检索与生成质量。

指标（均无需人工参考答案，LLM-as-judge）：
- faithfulness        ：答案是否忠于检索片段（衡量幻觉）
- answer_relevancy    ：答案与问题的相关度
- context_precision   ：检索片段对回答的有用程度

OOD（知识库外）问题单独统计「拒答正确率」。

用法：
    python -m src.evaluate                 # 全量评估（in_domain 全部 + OOD 拒答率）
    python -m src.evaluate --limit 2       # 只评估前 2 条 in_domain（先验证管道）
    python -m src.evaluate --workers 2     # 控制 Ragas 并发（默认 2，降低限流/控制成本节奏）
"""
from __future__ import annotations

import sys
import types

# --- 必须在 import ragas 之前执行的兼容性 shim ---------------------------------
# ragas 硬 import `langchain_community.chat_models.vertexai`，
# 而 langchain-community 1.x 已移除该路径。注入空 stub 绕过（本项目不使用 vertexai）。
_vx = types.ModuleType("langchain_community.chat_models.vertexai")
_vx.ChatVertexAI = type("ChatVertexAI", (), {})
sys.modules.setdefault("langchain_community.chat_models.vertexai", _vx)
# -----------------------------------------------------------------------------

# Windows GBK 控制台无法打印部分字符，强制 stdout/stderr 走 utf-8。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from langchain_openai import ChatOpenAI
from ragas import EvaluationDataset, evaluate
from ragas.dataset_schema import SingleTurnSample
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import (
    Faithfulness,
    LLMContextPrecisionWithoutReference,
    ResponseRelevancy,
)
from ragas.run_config import RunConfig

from .config import get_settings
from .embeddings import get_embeddings
from .graph.build import build_graph
from .graph.state import AgentState

GOLDEN_PATH = Path("data/eval/golden_qa.json")
RESULTS_DIR = Path("data/eval/results")
REFUSAL_MARKERS = ("未在知识库", "未找到", "没有找到", "无法找到")


def load_golden(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _cache_path(mode: str) -> Path:
    return RESULTS_DIR / f"runs_cache_{mode}.json"


def load_run_cache(mode: str) -> dict:
    p = _cache_path(mode)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def save_run_cache(mode: str, cache: dict) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(mode).write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def run_agent(graph, question: str) -> tuple[str, list[str]]:
    """跑一次 Agent，返回 (答案, 检索到的 context 文本列表)。"""
    init: AgentState = {
        "question": question,
        "rewrite_count": 0,
        "reflect_count": 0,
        "trace": [],
    }
    final: AgentState = graph.invoke(init, config={"recursion_limit": 15})  # type: ignore[assignment]
    answer = final.get("answer", "") or ""
    docs = final.get("docs", []) or []
    contexts = [d.page_content for d in docs]
    return answer, contexts


def is_refusal(answer: str) -> bool:
    return any(m in answer for m in REFUSAL_MARKERS)


def build_ragas_llm_and_embeddings():
    s = get_settings()
    chat = ChatOpenAI(
        model=s.deepseek_model,
        base_url=s.deepseek_base_url,
        api_key=s.deepseek_api_key.get_secret_value(),
        temperature=0.0,
        timeout=s.request_timeout,
        max_retries=2,
    )
    llm = LangchainLLMWrapper(chat)
    emb = LangchainEmbeddingsWrapper(get_embeddings())
    return llm, emb


def main() -> None:
    parser = argparse.ArgumentParser(description="Ragas 评估 EnterpriseDocAgent")
    parser.add_argument(
        "--mode",
        choices=["agentic", "baseline"],
        default="agentic",
        help="agentic=完整状态机；baseline=朴素 RAG（单轮 retrieve→generate）",
    )
    parser.add_argument("--limit", type=int, default=0, help="只评估前 N 条 in_domain（0=全部）")
    parser.add_argument("--workers", type=int, default=4, help="Ragas 并发数（越高越快，但更易触发限流）")
    parser.add_argument("--golden", default=str(GOLDEN_PATH), help="Golden QA 文件路径")
    parser.add_argument(
        "--reuse-agent",
        action="store_true",
        help="复用上次缓存的运行结果，跳过重跑（仅重做 Ragas 评分，省时省钱）",
    )
    args = parser.parse_args()
    mode = args.mode

    cache = load_run_cache(mode) if args.reuse_agent else {}

    # 根据 mode 选择被评估系统
    if mode == "agentic":
        graph = build_graph()

        def runner(q: str) -> tuple[str, list[str]]:
            return run_agent(graph, q)
    else:
        from .baseline import naive_rag

        def runner(q: str) -> tuple[str, list[str]]:
            return naive_rag(q)

    golden = load_golden(Path(args.golden))
    in_domain = [g for g in golden if g.get("type") == "in_domain"]
    ood = [g for g in golden if g.get("type") == "ood"]
    if args.limit > 0:
        in_domain = in_domain[: args.limit]

    print(f"[eval] mode={mode} · in_domain={len(in_domain)} 条, ood={len(ood)} 条")
    print(f"[eval] 预计 DeepSeek 调用 ≈ {len(in_domain) * 12 + len(ood) * 6} 次（系统运行 + 评估）\n")

    # ---- 1. 跑被评估系统收集 in_domain 样本 ----
    samples: list[SingleTurnSample] = []
    print(f"=== 运行系统（mode={mode}, in_domain）===")
    for g in in_domain:
        q = g["question"]
        if q in cache:
            answer, contexts = cache[q]["answer"], cache[q]["contexts"]
            print(f"  [{g['id']}] {g['topic']} · (缓存) · {len(contexts)} contexts")
        else:
            t0 = time.time()
            answer, contexts = runner(q)
            cache[q] = {"answer": answer, "contexts": contexts}
            print(f"  [{g['id']}] {g['topic']} · {time.time() - t0:.1f}s · {len(contexts)} contexts")
        samples.append(
            SingleTurnSample(
                user_input=g["question"],
                response=answer,
                retrieved_contexts=contexts or ["(无检索结果)"],
                reference=g.get("ground_truth"),
            )
        )

    # ---- 2. OOD 拒答率 ----
    print("\n=== OOD 拒答检测 ===")
    refusal_hits = 0
    ood_detail = []
    for g in ood:
        q = g["question"]
        if q in cache:
            answer = cache[q]["answer"]
        else:
            answer, ctx = runner(q)
            cache[q] = {"answer": answer, "contexts": ctx}
        ok = is_refusal(answer)
        refusal_hits += int(ok)
        mark = "[OK] 正确拒答" if ok else "[NG] 未拒答"
        print(f"  [{g['id']}] {g['topic']} · {mark}")
        ood_detail.append({"id": g["id"], "question": g["question"], "answer": answer, "refused": ok})
    refusal_rate = refusal_hits / len(ood) if ood else None

    # 缓存运行结果，下次可用 --reuse-agent 跳过重跑（省时省钱）
    save_run_cache(mode, cache)

    # ---- 3. Ragas 评估 in_domain ----
    print("\n=== Ragas 评分中（LLM-as-judge，请耐心等待）===")
    llm, emb = build_ragas_llm_and_embeddings()
    metrics = [
        Faithfulness(),
        ResponseRelevancy(),
        LLMContextPrecisionWithoutReference(),
    ]
    dataset = EvaluationDataset(samples=samples)
    run_config = RunConfig(max_workers=args.workers, timeout=get_settings().request_timeout)
    result = evaluate(
        dataset=dataset,
        metrics=metrics,
        llm=llm,
        embeddings=emb,
        run_config=run_config,
        show_progress=True,
    )

    # ---- 4. 输出 + 保存 ----
    df = result.to_pandas()
    print("\n=== 逐条得分 ===")
    print(df.to_string(index=False))

    print("\n=== 汇总（均值）===")
    summary = {}
    for col in df.columns:
        if df[col].dtype.kind in "fi":
            summary[col] = round(float(df[col].mean()), 4)
            print(f"  {col:28s}: {summary[col]}")
    if refusal_rate is not None:
        print(f"  {'ood_refusal_rate':28s}: {round(refusal_rate, 4)}  ({refusal_hits}/{len(ood)})")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = RESULTS_DIR / f"ragas_{mode}_{ts}.csv"
    json_path = RESULTS_DIR / f"summary_{mode}_{ts}.json"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    json_path.write_text(
        json.dumps(
            {
                "mode": mode,
                "timestamp": ts,
                "in_domain_count": len(in_domain),
                "metrics_mean": summary,
                "ood_refusal_rate": refusal_rate,
                "ood_detail": ood_detail,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n[eval] 明细已保存：{csv_path}")
    print(f"[eval] 汇总已保存：{json_path}")


if __name__ == "__main__":
    main()
