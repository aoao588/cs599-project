# Architecture Spec — EnterpriseDocAgent

> **版本**：v0.1 · **日期**：2026-06-02

---

## 1. 总体架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            EnterpriseDocAgent                           │
│                                                                         │
│   ┌─────────┐    ┌──────────────────────────────────────┐               │
│   │  CLI    │───▶│        LangGraph StateGraph          │               │
│   │  / UI   │    │                                      │               │
│   └─────────┘    │  router ─▶ retrieve ─▶ grade ─┬──▶ generate ─▶ end   │
│                  │                ▲              │                      │
│                  │                │  (rewrite)   │ (reflect→retry)      │
│                  │                └──────────────┘                      │
│                  └────────┬─────────────────┬───────────────────────────┘
│                           │                 │
│                ┌──────────▼──────┐   ┌──────▼────────┐                  │
│                │  LLM Client     │   │ Vector Store  │                  │
│                │  (DeepSeek)     │   │  (Chroma)     │                  │
│                └──────────┬──────┘   └──────┬────────┘                  │
│                           │                 │                           │
│                           │           ┌─────▼──────────┐                │
│                           │           │  Embedding     │                │
│                           │           │  (通义 v3)      │                │
│                           │           └────────────────┘                │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                              ┌─────▼──────┐
                              │ DeepSeek   │
                              │  API       │
                              └────────────┘
                              ┌────────────┐
                              │ DashScope  │
                              │  API       │
                              └────────────┘
```

---

## 2. 模块划分

| 模块 | 文件 | 职责 |
|---|---|---|
| **配置** | `src/config.py` | 用 pydantic-settings 读 `.env`；所有密钥/URL/参数集中管理 |
| **LLM 客户端** | `src/llm.py` | 封装 DeepSeek（OpenAI 兼容协议）；提供 `chat(messages)` 与 `chat_json(...)` 两种入口 |
| **Embedding 客户端** | `src/embeddings.py` | 封装通义 `text-embedding-v3`（DashScope OpenAI 兼容端点） |
| **向量库** | `src/vectorstore.py` | Chroma PersistentClient + LangChain `Chroma` 封装；提供 `get_vectorstore()` / `as_retriever()` |
| **入库脚本** | `src/ingest.py` | 扫描 `data/corpus/`、Markdown 切分、批量向量化入库；幂等 |
| **状态机** | `src/graph/state.py` | 定义 `AgentState`（TypedDict）：question, rewritten_query, docs, grade, answer, reflect_count |
| **节点** | `src/graph/nodes.py` | 6 个节点：router / rewrite / retrieve / grade / generate / reflect |
| **图编译** | `src/graph/build.py` | StateGraph 连接 + 条件边 + 编译 |
| **CLI 入口** | `src/main.py` | argparse + 调用图 + 流式打印 |

---

## 3. LangGraph 状态机详图

```
              ┌────────────┐
   START ───▶ │  router    │  分类：rag_qa / sql_qa(预留) / chitchat
              └─────┬──────┘
                    │
            ┌───────┴────────┐
   chitchat │                │ rag_qa
            ▼                ▼
       (直接 generate)   ┌────────────┐
            │            │  rewrite   │ HyDE / 子问题分解
            │            └─────┬──────┘
            │                  ▼
            │            ┌────────────┐
            │            │  retrieve  │ Chroma top-k
            │            └─────┬──────┘
            │                  ▼
            │            ┌────────────┐
            │            │   grade    │ LLM 评分：相关 / 部分 / 不相关
            │            └─────┬──────┘
            │                  │
            │       ┌──────────┼──────────┐
            │  不相关│   部分    │   相关   │
            │       ▼          ▼          ▼
            │   (回 rewrite，   ┌────────────┐
            │    reflect_count++)│  generate  │
            │                   └─────┬──────┘
            │                         ▼
            │                   ┌────────────┐
            │                   │  reflect   │ 答案是否真的回答了问题？
            │                   └─────┬──────┘
            │                         │
            │             不通过      │  通过
            │        ┌────────────────┼──────────┐
            │        ▼ (reflect_count             ▼
            └───────────────────────< MAX ?)    END
                 (回 rewrite)
```

**循环控制**：`reflect_count` 计数器 + `MAX_REFLECT_ROUNDS=2`，超过则强制走 generate 并标注「信息不完整」。

---

## 4. State 设计

```python
class AgentState(TypedDict):
    # 输入
    question: str

    # 路由结果
    route: Literal["rag_qa", "chitchat"]

    # 检索循环
    rewritten_query: str
    docs: list[Document]
    grade: Literal["relevant", "partial", "irrelevant"]
    reflect_count: int

    # 输出
    answer: str
    citations: list[dict]   # [{"id": 1, "source": "hr/leave-policy.md", "snippet": "..."}]

    # 调试
    trace: list[str]        # 节点执行轨迹
```

---

## 5. 数据流

### 5.1 入库时（一次性，可重跑）
```
data/corpus/**/*.md
        ▼
RecursiveCharacterTextSplitter (chunk=500, overlap=80)
        ▼
通义 text-embedding-v3（批量，每批 ≤ 25 条）
        ▼
Chroma PersistentClient → data/chroma/
```

### 5.2 查询时
```
用户 Query
   ▼
router (1 次 LLM)
   ▼
rewrite (1 次 LLM，生成 1~3 个改写 Query)
   ▼
retrieve (并发 embed + 检索，结果去重合并)
   ▼
grade (1 次 LLM，结构化输出)
   ▼ relevant
generate (1 次 LLM，带引用)
   ▼
reflect (1 次 LLM)
   ▼ pass
答案 + 引用
```

**LLM 调用次数**：理想路径 5 次；最坏路径（2 轮反思）约 9 次。

---

## 6. 关键设计决策

| 决策 | 选择 | 理由 |
|---|---|---|
| Embedding 服务 | 通义 `text-embedding-v3` | DeepSeek 暂无 embedding API；通义中文表现强、价格低 |
| 向量库 | Chroma 本地持久化 | 零运维、SQLite 后端、几千文档完全够用 |
| 状态机 | LangGraph 而非 LangChain Chain | 显式状态 + 条件边 + 反思循环天然契合 Agentic RAG |
| 结构化输出 | DeepSeek 的 `response_format={"type":"json_object"}` | 比 prompt 约束稳定，grade/reflect 节点必用 |
| 切分策略 | RecursiveCharacterTextSplitter | Markdown 友好；后续可换 `MarkdownHeaderTextSplitter` |
| 检索增强 | HyDE + 子问题分解 | rewrite 节点同时输出多个改写 query，合并去重 |

---

## 7. 错误处理与重试

- 所有外部 API 调用通过 `tenacity` 装饰器：指数退避，最多 3 次
- LLM 返回非法 JSON → 触发一次「修复重试」（追加 "请严格输出合法 JSON" 系统消息）
- Embedding 服务超时 → 单条降级为顺序调用
- 全部捕获后写入 `state.trace`，最终在 reflect 节点统一暴露

---

## 8. 可观测性

- **结构化日志**：每个节点入/出打印 JSON 日志（含 latency_ms）
- **LangSmith Tracing**（可选开关）：`LANGSMITH_TRACING=true` 即接入
- **Token 计量**：在 LLM 客户端层累计 prompt/completion tokens，CLI 结束时打印

---

## 9. 未来演进（架构预留点）

1. **MCP 化**：把 `retrieve` / `sql_query` 抽出为独立 MCP Server，nodes 通过 MCP Client 调用 → 工具复用、跨项目可用
2. **多 Agent**：把 `grade` 拆出独立 Critic Agent，与 Retriever Agent 用 supervisor 模式编排
3. **流式输出**：generate 节点改 `astream`，通过 SSE 推到前端
4. **重排（Rerank）**：在 retrieve 之后接 BGE-reranker（可选）
