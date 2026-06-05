# 系统架构图

> 对应报告第三章「系统架构与设计」。所有图使用 Mermaid 绘制，GitHub 可直接渲染；
> 导出 PNG 可用 VS Code「Markdown Preview Enhanced」右键导出，或 mermaid.live 在线导出。

---

## 1. 总体分层架构

```mermaid
flowchart TB
    subgraph L1["接入层 (Interface)"]
        CLI["CLI<br/>src/main.py"]
        UI["Streamlit Web UI<br/>app.py"]
    end

    subgraph L2["Agent 编排层 (LangGraph StateGraph)"]
        direction LR
        RT["router"] --> RW["rewrite"] --> RE["retrieve"]
        RE --> GR["grade"] --> GE["generate"] --> RF["reflect"]
    end

    subgraph L3["服务层 (Services)"]
        LLM["LLM Client<br/>src/llm.py"]
        EMB["Embedding Client<br/>src/embeddings.py"]
        VS[("Chroma 向量库<br/>src/vectorstore.py")]
    end

    subgraph L4["外部 API (OpenAI 兼容协议)"]
        DS["DeepSeek API<br/>deepseek-chat"]
        DASH["DashScope API<br/>text-embedding-v3"]
    end

    CLI --> L2
    UI --> L2
    L2 --> LLM
    L2 --> VS
    VS --> EMB
    LLM --> DS
    EMB --> DASH
```

**设计要点**：四层解耦。接入层（CLI / Web）只负责输入输出；Agent 编排层是核心，用 LangGraph 状态机驱动多步推理；服务层封装 LLM、Embedding、向量库；外部 API 全部走 OpenAI 兼容协议，更换厂商只需改 `.env`。

---

## 2. LangGraph 状态机（核心）

```mermaid
flowchart TD
    START((START)) --> router{router<br/>意图分类}
    router -->|chitchat| chitchat["chitchat<br/>闲聊回复"]
    router -->|rag_qa| rewrite["rewrite<br/>多 query 改写"]

    rewrite --> retrieve["retrieve<br/>向量检索+去重合并"]
    retrieve --> grade{grade<br/>检索质量评估}

    grade -->|relevant| generate
    grade -->|partial / 未超预算| rewrite
    grade -->|irrelevant / 已重试| generate

    generate["generate<br/>带引用作答"] -->|irrelevant 未找到| EXIT((END))
    generate -->|正常答案| reflect{reflect<br/>答案反思}

    reflect -->|pass| EXIT
    reflect -->|fail / 有预算| rewrite
    chitchat --> EXIT

    classDef decision fill:#fff3cd,stroke:#d39e00;
    classDef action fill:#d1ecf1,stroke:#0c5460;
    class router,grade,reflect decision;
    class rewrite,retrieve,generate,chitchat action;
```

**循环控制**：`rewrite_count` 作为统一重试预算（`MAX_REFLECT_ROUNDS=2`，即最多重写 3 次）；
`irrelevant` 早退避免在知识库外问题上空转；LangGraph `recursion_limit=15` 作为硬兜底。

---

## 3. 数据流

### 3.1 离线入库（ingest，一次性）

```mermaid
flowchart LR
    MD["data/corpus/<br/>25 篇 Markdown"] --> SP["RecursiveCharacterTextSplitter<br/>chunk=500 / overlap=80"]
    SP --> CH["44 个文本片段"]
    CH --> EM["通义 text-embedding-v3<br/>批量(≤10/批)"]
    EM --> VEC["1024 维向量"]
    VEC --> DB[("Chroma<br/>data/chroma/")]
```

### 3.2 在线问答（query）

```mermaid
sequenceDiagram
    participant U as 用户
    participant G as LangGraph
    participant L as DeepSeek
    participant V as Chroma
    participant E as 通义 Embedding

    U->>G: 提问
    G->>L: router 意图分类
    G->>L: rewrite 生成子查询
    loop 每个子查询
        G->>E: 向量化
        G->>V: 相似检索 top-k
        V-->>G: 候选片段
    end
    G->>L: grade 评估检索质量
    alt 检索充分
        G->>L: generate 带引用作答
        G->>L: reflect 校验答案
    else 不充分且有预算
        G->>G: 回到 rewrite 重检
    end
    G-->>U: 答案 + 引用 + 轨迹
```

---

## 4. 朴素 RAG vs Agentic RAG（对照实验示意）

```mermaid
flowchart LR
    subgraph A["朴素 RAG（baseline）"]
        direction LR
        Q1["Query"] --> R1["Retrieve"] --> G1["Generate"] --> O1["Answer"]
    end

    subgraph B["Agentic RAG（ours）"]
        direction TB
        Q2["Query"] --> P2["rewrite<br/>多查询改写"]
        P2 --> R2["retrieve"]
        R2 --> D2{"grade"}
        D2 -->|不足| P2
        D2 -->|充分| G2["generate"]
        G2 --> F2{"reflect"}
        F2 -->|不通过| P2
        F2 -->|通过| O2["Answer"]
    end
```

**对比结论**：朴素 RAG 是一条直线（一次检索定胜负）；Agentic RAG 引入「改写—评估—反思」反馈环，
在需要定位深层条款的复杂问题上显著更稳健（详见 [evaluation.md](evaluation.md) §4）。
