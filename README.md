# EnterpriseDocAgent

## 项目简介
面向企业内部文档（研发规范 / HR 制度 / 财务表）的 **Agentic RAG 智能问答系统**：通过 LangGraph 状态机驱动「意图路由 → Query 改写 → 工具检索 → 结果评估 → 反思重检 → 带引用作答」的多步推理闭环，解决传统 RAG「一次检索定胜负、答非所问、无引用」的痛点。

## 方向
方向一：Agentic AI 原生开发

## 技术栈
- **AI IDE**：Trae CN
- **LLM**：DeepSeek-V3（OpenAI 兼容协议）
- **Embedding**：通义千问 `text-embedding-v3`（DashScope OpenAI 兼容端点）
- **Agent 框架**：LangGraph + LangChain
- **向量库**：Chroma（本地持久化）
- **结构化数据**：DuckDB（HR / 财务模拟表）
- **协议**：MCP（自研 Server 暴露 vector_search / sql_query）
- **可观测性**：LangSmith Tracing + Ragas 评估
- **容器**：Docker + Docker Compose
- **前端**：Streamlit

## 目录结构
```
cs599-project/
├── docs/
│   └── specs/                      # SDD 三件套
│       ├── product_spec.md         # 产品规格
│       ├── architecture_spec.md    # 架构规格
│       └── api_spec.md             # 接口规格
├── src/
│   ├── config.py                   # 配置（pydantic-settings，读 .env）
│   ├── llm.py                      # DeepSeek 客户端封装
│   ├── embeddings.py               # 通义 Embedding 封装
│   ├── vectorstore.py              # Chroma 初始化
│   ├── ingest.py                   # 语料切分 + 入库脚本
│   ├── main.py                     # CLI 入口
│   └── graph/                      # LangGraph 状态机
│       ├── state.py                # 全局 State 定义
│       ├── nodes.py                # Router / Retrieve / Grade / Generate / Reflect 节点
│       └── build.py                # 图编译
├── data/
│   ├── corpus/                     # 模拟企业文档
│   │   ├── dev/                    # 研发规范
│   │   └── hr/                     # HR 制度
│   └── chroma/                     # Chroma 持久化目录（gitignore）
├── tests/                          # 单元测试
├── .env.example                    # 环境变量模板
├── requirements.txt
└── LICENSE
```

## 环境搭建
1. **依赖安装**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate    # Windows PowerShell
   pip install -r requirements.txt
   ```
2. **环境变量配置**（⚠️ 不硬编码 API Key）
   ```bash
   cp .env.example .env
   # 编辑 .env 填入：
   #   DEEPSEEK_API_KEY=sk-...
   #   DASHSCOPE_API_KEY=sk-...
   ```
3. **构建向量库**（首次运行）
   ```bash
   python -m src.ingest
   ```
4. **提问**
   - CLI 单次提问：
     ```bash
     python -m src.main "公司年假怎么算？" --trace
     ```
   - 交互模式：
     ```bash
     python -m src.main --interactive
     ```
   - Web UI（Streamlit，含节点级实时进度可视化）：
     ```bash
     streamlit run app.py
     # 浏览器访问 http://localhost:8501
     ```

## 项目状态
- [x] Proposal（架构设计 + Spec 初稿）
- [x] MVP（v0.1 完整闭环，CLI 可用，2026-06-03 完成）
- [ ] Final（含 MCP / 云部署 / Ragas 评估，目标 2026-06-22）

### v0.1 已验证能力
- ✅ 多步检索：router → rewrite → retrieve → grade → generate → reflect 状态机闭环
- ✅ 组合推理：跨多条文档片段聚合作答（如"代码评审门禁"组合 [2][4]）
- ✅ 计算查表：识别可计算条件并应用文档中的折算公式（如年假折算）
- ✅ 带引用作答：每个事实点标注 [n] 角标 + 来源文件
- ✅ 拒绝幻觉：知识库外问题（OOD）早退并明确告知"未找到依据"
- ✅ 生产级：API 超时控制、tenacity 重试、流式节点耗时观测、密钥环境变量化

### Ragas 评估结果（知识库 25 篇/44 chunks，10 条 Golden QA，详见 [docs/evaluation.md](docs/evaluation.md)）
| faithfulness | answer_relevancy | context_precision | OOD 拒答率 |
|:---:|:---:|:---:|:---:|
| 0.824 | 0.887 | 0.938 | 100% |

**对照实验（朴素 RAG vs Agentic RAG）**：在"需定位深层条款"的问题上，朴素 RAG 直接漏检失败，
Agentic RAG 凭 rewrite 多查询改写 + grade 重检仍能正确作答（见 evaluation.md §4 案例分析）。

```bash
python -m src.evaluate                    # 全量评估（Agentic）
python -m src.evaluate --mode baseline    # 朴素 RAG 对照
python -m src.evaluate --reuse-agent      # 复用运行结果，仅重跑评分（更快）
```

## License
MIT
