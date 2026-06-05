<!--
报告源文件。导出 PDF（带书签/导航）方法：
- VS Code + Markdown Preview Enhanced：右键 → Chrome (Puppeteer) → PDF（标题自动成书签）
- 或 Typora → 导出 → PDF
- 或 Pandoc：pandoc report.md -o report.pdf --toc --pdf-engine=xelatex -V CJKmainfont="SimSun"
最终文件须命名为 docs/CS599_大作业报告.pdf
标注 [✍️待填] 处需作者补充。
-->

# 企业级应用软件设计与开发 — 期末大作业报告

| 字段 | 内容 |
|---|---|
| 课程名称 | 企业级应用软件设计与开发 |
| 项目名称 | EnterpriseDocAgent —— 企业知识库 Agentic RAG 智能问答系统 |
| 方向 | 方向一：Agentic AI 原生开发 |
| 学号 | ✍️待填 |
| 姓名 | ✍️待填 |
| 专业 | 计算机技术 / 软件工程（✍️择一） |
| 指导教师 | 戚欣 |
| 提交日期 | 2026 年 6 月 22 日 |

> 代码仓库：https://github.com/aoao588/cs599-project

---

## 一、选题背景与设计思想

### 1.1 问题定义
中型企业内部知识高度碎片化：研发规范、HR 制度、财务流程分散在 Wiki / PDF / 数据库中。
员工高频咨询（请假、报销、规范）占用大量 HR/资深工程师时间，新员工上手慢。

### 1.2 现有方案的不足
| 方案 | 痛点 |
|---|---|
| 关键词全文搜索 | 不懂语义；返回文档列表而非答案 |
| 朴素 RAG（单轮检索+生成） | 一次检索定胜负；遇到口语化/跨库/需计算的问题答非所问；无引用、无法核对；易幻觉 |

### 1.3 项目价值
构建一个**会规划、会反思、带引用、拒绝幻觉**的 Agentic RAG 问答系统，把"检索"从一次性动作
升级为 LLM 驱动的多步决策过程。详见对照实验（§五），证明该设计在复杂问题上显著优于朴素 RAG。

### 1.4 技术路线
LangGraph 状态机编排 → DeepSeek(LLM) + 通义(Embedding) 全 OpenAI 兼容协议 → Chroma 本地向量库
→ Ragas 量化评估。核心技术要素覆盖：SDD、工具使用、状态管理与多步推理、记忆机制、可观测性与评估。

---

## 二、Specs 规格文档（SDD 核心）

本项目采用规格驱动开发（SDD），先写规格再实现。三份规格文档：

| 规格 | 文件 | 内容 |
|---|---|---|
| Product Spec | [specs/product_spec.md](specs/product_spec.md) | 用户故事 US-01~05、验收标准、成功指标 |
| Architecture Spec | [specs/architecture_spec.md](specs/architecture_spec.md) | 模块划分、状态机、数据流、关键决策 |
| API Spec | [specs/api_spec.md](specs/api_spec.md) | 内部模块接口契约、未来 HTTP/MCP 接口 |

> 报告中可摘录各 Spec 的关键片段（如 US-03「检索不足自动重检」的验收标准），
> 体现"规格 → 实现 → 验证"的闭环。[✍️可补 1-2 段摘录]

---

## 三、系统架构与设计

> 本章图文并茂，核心图见 [architecture.md](architecture.md)，报告中嵌入导出的 PNG。

### 3.1 总体分层架构
四层解耦：接入层（CLI/Web）→ Agent 编排层（LangGraph）→ 服务层（LLM/Embedding/向量库）→ 外部 API。
（嵌入 architecture.md 图 1）

### 3.2 Agent 交互流程（LangGraph 状态机）
router → rewrite → retrieve → grade →（不足则回 rewrite）→ generate → reflect →（不通过则回 rewrite）。
循环由 `rewrite_count` 预算 + `recursion_limit` 双重兜底。（嵌入 architecture.md 图 2）

### 3.3 数据流设计
离线 ingest（切分→向量化→入库）与在线 query（多步检索推理）。（嵌入 architecture.md 图 3、3.2）

### 3.4 关键设计决策
| 决策 | 选择 | 理由 |
|---|---|---|
| 编排框架 | LangGraph | 显式状态 + 条件边 + 反思循环，天然契合 Agentic RAG |
| Embedding | 通义 text-embedding-v3 | DeepSeek 无 embedding；通义中文强、成本低 |
| 向量库 | Chroma | 零运维、本地持久化 |
| 结构化输出 | DeepSeek JSON mode | grade/reflect 节点稳定解析 |

---

## 四、关键实现与代码展示

### 4.1 Agent 核心循环
LangGraph `StateGraph` 编译，6 个节点 + 4 条条件边。代码见 `src/graph/build.py`、`src/graph/nodes.py`。
[✍️贴 build.py 的图编译片段 + 一个节点实现片段]

### 4.2 工具与节点定义
- `node_rewrite`：多 query 改写（HyDE/子问题分解）
- `node_grade`：结构化输出评估检索质量（relevant/partial/irrelevant）
- `node_reflect`：答案反思，不通过则重检

### 4.3 配置与安全
`src/config.py` 用 pydantic-settings 读 `.env`，API Key 全程环境变量化，绝不硬编码。
[✍️贴 .env.example 截图 / config.py 片段]

### 4.4 生产级工程实践
API 超时控制、tenacity 指数退避重试、流式节点耗时观测、JSON 解析失败自动修复重试。

### 4.5 AI IDE 使用
[✍️插入 Trae CN 使用截图：如用 AI 生成节点骨架、调试状态机等]

---

## 五、测试与评估

> 详见 [evaluation.md](evaluation.md)。

### 5.1 评估方法
知识库 25 篇/44 chunks（含 21 篇干扰文档）；Golden QA 10 条（8 in_domain + 2 OOD）；
工具 Ragas（LLM-as-judge）。

### 5.2 量化结果
| faithfulness | answer_relevancy | context_precision | OOD 拒答率 |
|:---:|:---:|:---:|:---:|
| 0.824 | 0.887 | 0.938 | 100% |

### 5.3 对照实验：朴素 RAG vs Agentic RAG
核心案例 qa02「首年折算」：朴素 RAG 漏检失败（答"未找到"），Agentic RAG 正确作答。
证明 rewrite+grade+reflect 架构在复杂问题上的价值。（嵌入 architecture.md 图 4）

### 5.4 Demo 截图/录屏
[✍️插入 Web UI 问答截图 + 节点进度截图；录屏存 docs/]

---

## 六、系统升级与扩展

### 6.1 可扩展架构
全 OpenAI 兼容协议，换 LLM/Embedding 厂商只改 `.env`；节点松耦合，易增删。

### 6.2 下一阶段计划
- **MCP 化**：将 vector_search / sql_query 抽为独立 MCP Server，跨项目复用
- **多智能体**：grade 拆为独立 Critic Agent，supervisor 模式编排
- **检索增强**：引入 BGE-reranker 重排、MarkdownHeader 感知切分
- **结构化数据**：接入 DuckDB，支持自然语言查表（sql_query 工具）

### 6.3 AI 能力演进路径
单 Agent → 多 Agent 协作 → 长期记忆（跨会话）→ 云端部署 + 流式输出（SSE）。

---

## 七、课程总结

> [✍️本章须作者本人撰写，以下为提纲提示]

- **个人收获**：从写代码到"编排智能体"的思维转变；SDD 先写规格的工程价值；
  调试 Agent（死循环、过度重试、OOD 处理）的经验。
- **工程思维转变**：[✍️结合 grade 死循环 bug、ragas×langchain 兼容、成本约束等真实经历展开]
- **对课程的建议**：[✍️待填]

---

## 附录

- 代码仓库：https://github.com/aoao588/cs599-project （tag v0.1）
- 目录结构与运行方式见 [README](../README.md)
- 评估明细：`data/eval/results/`
