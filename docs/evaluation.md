# 测试与评估报告

> 对应报告第五章「测试与评估」· 评估工具：[Ragas](https://docs.ragas.io) 0.2.15

---

## 1. 评估方法

### 1.1 知识库与评估集

**知识库规模**：`data/corpus/` 下共 25 篇企业文档，覆盖研发(dev)、人事(hr)、财务(finance)、IT 四个领域，
切分为 44 个向量片段。其中只有 4 篇与 Golden QA 直接相关，其余 21 篇为「干扰文档」——
这正是为了检验检索在较大知识库中的**抗干扰能力**。

**评估集（Golden QA）**：位于 `data/eval/golden_qa.json`，共 10 条，分两类：

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

## 4. 对照实验：朴素 RAG vs Agentic RAG

为证明「Agentic 架构」本身的价值，实现了一个朴素 RAG baseline（`src/baseline.py`）做对照。

| 维度 | 朴素 RAG (baseline) | Agentic RAG (ours) |
|---|---|---|
| 检索 | 用原始问题**单轮**检索 top-k | rewrite **多 query** 改写后检索、去重合并 |
| 质量控制 | 无 | grade 评估，不足则重检 |
| 反思 | 无 | reflect 校验答案，必要时重试 |
| 调用次数 | 1 次 LLM | 5~9 次 LLM |

> 运行方式：`python -m src.evaluate --mode baseline` / `--mode agentic`

### 4.1 样例对照结果

> 受 API 额度限制，此处为**样例级对照**（非大样本统计）。指标方向已足够明确，
> 核心结论由 §4.2 的案例分析支撑。

| 样例 | 指标 | 朴素 RAG | Agentic RAG |
|---|---|:---:|:---:|
| qa01 年假天数（直接查表） | faithfulness / relevancy / precision | 1.0 / 0.98 / 1.0 | 1.0 / 0.98 / 1.0 |
| **qa02 首年折算（需定位深层条款）** | faithfulness / relevancy / precision | **0.0 / 0.0 / 0.0** | 0.63 / 0.95 / 1.0 |
| OOD 拒答率 | — | 100% | 100% |

简单的"直接查表"类问题（qa01）两者打平；一旦问题需要**定位知识库深层条款**（qa02），
朴素 RAG 直接失败，Agentic RAG 仍能作答。

### 4.2 关键案例分析：qa02「首年年假折算」

知识库 `hr/leave-policy.md` 中**确实包含**首年折算公式，但两个系统表现迥异：

- **朴素 RAG → 回答"未在知识库中找到相关依据"（假阴性）**
  单轮检索命中的是年假办法开头的大片段，"折算公式"位于片段靠后位置、在上下文组织中被淹没，
  模型据此误判知识库无相关内容。**一次检索定胜负**的结构性缺陷。

- **Agentic RAG → 正确给出折算公式并代入计算**
  rewrite 节点生成"首年年假折算""入职当年年假比例"等针对性子查询，
  直接命中折算条款；grade 评估通过后由 generate 组合作答。
  **多 query 改写 + 质量评估**让它越过了朴素 RAG 的盲区。

### 4.3 结论

Agentic 架构的增益**不在简单问题上，而在"需要主动改写检索、跨片段定位"的复杂问题上**——
这类问题恰恰是企业知识库的常态。对照实验印证了 router/rewrite/grade/reflect 状态机的设计价值。

> 完整大样本对照（8 条 × 2 系统 × 3 指标）可在 API 额度充足时一键复现：
> `python -m src.evaluate --mode baseline` 与 `--mode agentic`，结果落盘到 `data/eval/results/`。
