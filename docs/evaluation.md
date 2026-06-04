# 测试与评估报告

> 对应报告第五章「测试与评估」· 评估工具：[Ragas](https://docs.ragas.io) 0.2.15

---

## 1. 评估方法

### 1.1 评估集（Golden QA）
位于 `data/eval/golden_qa.json`，共 10 条，分两类：

| 类型 | 数量 | 说明 |
|---|---|---|
| `in_domain` | 8 | 知识库可回答，覆盖年假/报销/代码评审/分支策略四个主题 |
| `ood` | 2 | 知识库外问题（食堂、班车），用于检验「拒绝幻觉」能力 |

每条含 `question`、`ground_truth`（人工核对原文得出的参考答案）、`source`（依据文件）。

### 1.2 评估指标

采用 Ragas 的「LLM-as-judge」无参考指标（评判用 DeepSeek，向量相似度用通义 embedding）：

| 指标 | 含义 | 越高越好 |
|---|---|:---:|
| **faithfulness** | 答案中的每个论断是否都能由检索片段支撑（衡量幻觉） | ✅ |
| **answer_relevancy** | 答案与问题的语义相关度（是否答非所问） | ✅ |
| **context_precision** | 检索到的片段中，与回答真正相关的占比（检索精度） | ✅ |
| **ood_refusal_rate** | OOD 问题被正确拒答的比例（自定义指标） | ✅ |

> 选这三个 Ragas 指标 + 一个自定义拒答率，正好对应 Product Spec 第 5 节设定的成功指标。

### 1.3 评估流程

```
golden_qa.json
     │
     ├─ in_domain ─→ 逐条跑 Agent ─→ 收集 (question, answer, retrieved_contexts)
     │                                        │
     │                                        ▼
     │                            Ragas evaluate（DeepSeek 评判）
     │                                        │
     │                                        ▼
     │                         faithfulness / answer_relevancy / context_precision
     │
     └─ ood ───────→ 逐条跑 Agent ─→ 判断答案是否包含「未找到」标记 ─→ 拒答率
```

复现命令：
```bash
python -m src.evaluate            # 全量
python -m src.evaluate --limit 2  # 快速验证管道
```

结果落盘到 `data/eval/results/`（逐条 CSV + 汇总 JSON）。

---

## 2. 评估结果

> 数据由 `python -m src.evaluate` 全量运行生成（8 条 in_domain + 2 条 OOD）。
> 运行时间 2026-06-04 · 评判模型 DeepSeek · 明细见 `data/eval/results/`。

| 指标 | 得分 | Product Spec 目标 | 是否达标 |
|---|:---:|:---:|:---:|
| faithfulness | **0.824** | ≥ 0.85 | 接近（见 §3 分析） |
| answer_relevancy | **0.887** | ≥ 0.85 | ✅ 达标 |
| context_precision | **0.938** | ≥ 0.90 | ✅ 达标 |
| ood_refusal_rate | **1.000** (2/2) | 100% | ✅ 达标 |

**耗时构成**（全量约 8 分钟）：Agent 运行 8 条约 76s（最慢 13s，含一轮反思重检）；
Ragas 评分阶段约 7 分钟——LLM-as-judge 需对每条答案逐句验证忠实度、反向生成相关性问题，
是评估的固有成本。脚本提供 `--reuse-agent` 复用 Agent 结果、`--workers` 调并发以加速重复评估。

---

## 3. 结果分析（要点）

- **检索精度（context_precision）高** → 说明 rewrite 多 query 改写 + 去重合并的检索策略有效。
- **拒答率（ood_refusal_rate）** → 验证了 grade 节点判 `irrelevant` 后早退、generate 输出标准「未找到」的设计。
- **faithfulness 的扣分点** → 当 Agent 为说明计算规则而**自行举例推算**（如年假折算的具体数字）时，这些数字不在原文，会被 Ragas 判为部分不忠实。这反映了「**推理能力 vs 严格忠实**」的固有张力：让模型计算就难免产出原文没有的中间数值。
  - 改进方向：在 generate 提示中要求「示例计算需显式标注为‘示例推算，非原文’」，或仅复述公式不代入具体数字。

---

## 4. 对照实验设想（升级方向）

为证明「Agentic RAG > 朴素 RAG」，可加一组对照：
- **Baseline**：单轮 `retrieve → generate`（关闭 rewrite/grade/reflect）
- **Ours**：完整状态机
- 在同一 Golden QA 上对比四项指标，预期 Ours 在 faithfulness 与 context_precision 上显著更优。
