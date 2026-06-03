# API Spec — EnterpriseDocAgent

> **版本**：v0.1 · **日期**：2026-06-02
> 本文档定义两层接口：(1) 模块内部 Python 接口契约；(2) 未来对外 HTTP/MCP 接口。

---

## 1. 内部模块接口

### 1.1 `src/config.py`

```python
class Settings(BaseSettings):
    deepseek_api_key: SecretStr
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    dashscope_api_key: SecretStr
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_embed_model: str = "text-embedding-v3"

    chroma_persist_dir: str = "./data/chroma"
    chroma_collection: str = "enterprise_docs"

    retrieve_top_k: int = 5
    max_reflect_rounds: int = 2

settings = Settings()   # 单例
```

### 1.2 `src/llm.py`

```python
class LLMClient:
    def chat(self, messages: list[dict], *, temperature: float = 0.2) -> str: ...
    def chat_json(self, messages: list[dict], *, schema_hint: str | None = None) -> dict: ...

def get_llm() -> LLMClient: ...   # 单例工厂
```

- `chat` 返回纯文本
- `chat_json` 强制 `response_format={"type":"json_object"}`，并解析为 dict；解析失败触发一次重试

### 1.3 `src/embeddings.py`

```python
class EmbeddingClient(Embeddings):
    """实现 LangChain Embeddings 接口，Chroma 可直接吃。"""
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...

def get_embeddings() -> EmbeddingClient: ...
```

- 批量大小 25（DashScope 单批上限）
- 失败重试 3 次（tenacity）

### 1.4 `src/vectorstore.py`

```python
def get_vectorstore() -> Chroma: ...           # 返回 LangChain Chroma 实例
def reset_collection() -> None: ...            # 删除并重建集合（ingest 用）
```

### 1.5 `src/graph/state.py`

```python
class AgentState(TypedDict, total=False):
    question: str
    route: Literal["rag_qa", "chitchat"]
    rewritten_query: str
    subqueries: list[str]
    docs: list[Document]
    grade: Literal["relevant", "partial", "irrelevant"]
    reflect_count: int
    answer: str
    citations: list[Citation]
    trace: list[str]

class Citation(TypedDict):
    id: int
    source: str        # 文件相对路径
    snippet: str       # 引用段落（截断 200 字）
```

### 1.6 `src/graph/nodes.py`

每个节点签名一致：

```python
def node_xxx(state: AgentState) -> dict: ...
```

返回**只包含本节点修改字段**的 dict，由 LangGraph 合并到 State。

| 节点 | 输入字段 | 输出字段 |
|---|---|---|
| `node_router` | `question` | `route` |
| `node_rewrite` | `question` | `rewritten_query`, `subqueries` |
| `node_retrieve` | `subqueries` | `docs` |
| `node_grade` | `question`, `docs` | `grade` |
| `node_generate` | `question`, `docs` | `answer`, `citations` |
| `node_reflect` | `question`, `answer`, `docs` | `reflect_count`, `grade`（可能改写） |

### 1.7 `src/graph/build.py`

```python
def build_graph() -> CompiledStateGraph: ...
```

---

## 2. CLI 接口

```bash
python -m src.ingest                              # 全量重建索引
python -m src.ingest --path data/corpus/dev       # 增量入库某子目录
python -m src.main "公司年假怎么算？"               # 单次提问
python -m src.main --interactive                  # 交互模式
python -m src.main --trace "..."                  # 打印节点轨迹
```

---

## 3. 未来对外接口（Final 阶段，预留设计）

### 3.1 HTTP API

```
POST /api/v1/ask
Content-Type: application/json

{
  "question": "string",
  "session_id": "string (optional)",
  "stream": false
}
```

**Response 200**：
```json
{
  "answer": "string",
  "citations": [
    {"id": 1, "source": "hr/leave-policy.md", "snippet": "..."}
  ],
  "trace": ["router→rag_qa", "rewrite→...", "retrieve→5 docs", "grade→relevant", "generate", "reflect→pass"],
  "latency_ms": 4231,
  "tokens": {"prompt": 1820, "completion": 312}
}
```

**Response 4xx/5xx**：
```json
{"error": "string", "code": "INVALID_QUESTION | UPSTREAM_TIMEOUT | INTERNAL"}
```

### 3.2 MCP Server（加分项，预留）

暴露三个工具：

| Tool | 参数 | 返回 |
|---|---|---|
| `vector_search` | `{query: str, top_k: int = 5}` | `[{source, snippet, score}]` |
| `sql_query` | `{sql: str}` | `{columns: [...], rows: [...]}` |
| `web_search` | `{query: str}` | `[{title, url, snippet}]` |

协议遵循 MCP 1.0，stdio 传输；LangGraph 节点通过 `mcp-client` 调用。

---

## 4. 外部 API 调用契约

### 4.1 DeepSeek Chat（已通过 OpenAI SDK）
- Endpoint：`POST {DEEPSEEK_BASE_URL}/chat/completions`
- Model：`deepseek-chat`
- 关键参数：`response_format={"type":"json_object"}` 用于结构化节点
- 重试：429 / 5xx → tenacity 指数退避，最多 3 次

### 4.2 通义 Embedding（DashScope OpenAI 兼容端点）
- Endpoint：`POST {DASHSCOPE_BASE_URL}/embeddings`
- Model：`text-embedding-v3`
- 单批上限：25 条 / 8192 tokens
- 向量维度：1024（v3 默认）

---

## 5. 配置变更兼容性

- 所有外部 URL/模型名走环境变量 → 切到 SiliconFlow、智谱、OpenAI 等只需改 `.env`
- 新增字段必须给默认值，老 `.env` 仍可启动
