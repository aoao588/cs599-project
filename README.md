# EnterpriseDocAgent

## 项目简介
面向企业内部文档（研发规范 / HR 制度 / 财务表）的 **Agentic RAG 智能问答系统**：通过 LangGraph 状态机驱动「意图路由 → Query 改写 → 工具检索 → 结果评估 → 反思重检 → 带引用作答」的多步推理闭环，解决传统 RAG「一次检索定胜负、答非所问、无引用」的痛点。

## 方向
方向一：Agentic AI 原生开发

## 技术栈
- **AI IDE**：Trae CN
- **LLM**：DeepSeek（`deepseek-chat`，OpenAI 兼容协议）
- **Embedding**：通义千问 `text-embedding-v3`（DashScope OpenAI 兼容端点）
- **Agent 框架**：LangGraph + LangChain
- **向量库**：Chroma（本地持久化）
- **评估**：Ragas（LLM-as-judge）+ 自定义 OOD 拒答率
- **前端**：Streamlit Web UI / CLI
- **可观测性**：节点级耗时观测；可选 LangSmith Tracing（环境变量开关）

> 规划中（详见报告第六章与 API Spec，当前版本尚未实现）：MCP Server 化、Docker 容器化、DuckDB 结构化查询、云端部署。

## 目录结构
```
cs599-project/
├── docs/
│   ├── CS599_大作业报告.pdf          # 最终提交报告（PDF，带书签）
│   ├── CS599_大作业报告.docx         # 报告源文件
│   ├── architecture.md             # 架构图（Mermaid）
│   ├── evaluation.md               # 评估方法与结果
│   ├── diagrams/                   # 架构图 PNG
│   └── specs/                      # SDD 三件套（product/architecture/api spec）
├── src/
│   ├── config.py                   # 配置（pydantic-settings，读 .env）
│   ├── llm.py                      # DeepSeek 客户端封装
│   ├── embeddings.py               # 通义 Embedding 封装
│   ├── vectorstore.py              # Chroma 初始化
│   ├── ingest.py                   # 语料切分 + 入库脚本
│   ├── main.py                     # CLI 入口
│   ├── baseline.py                 # 朴素 RAG（对照实验）
│   ├── evaluate.py                 # Ragas 评估脚本
│   └── graph/                      # LangGraph 状态机（state / nodes / build）
├── data/
│   ├── corpus/                     # 模拟企业文档（dev / hr / finance / it，25 篇）
│   ├── eval/                       # Golden QA + 评估结果
│   └── chroma/                     # Chroma 持久化目录（gitignore）
├── scripts/                        # 架构图绘制 + 报告生成脚本
├── app.py                          # Streamlit Web UI
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
- [x] MVP（v0.1 完整闭环，CLI 可用）
- [x] Final（完整代码 + Web UI + Ragas 评估 + 朴素/Agentic 对照实验 + 报告，2026-06-22）

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

## 开源依赖与引用
本项目基于以下开源项目构建（遵循各自许可证），在此致谢：
- [LangGraph](https://github.com/langchain-ai/langgraph) / [LangChain](https://github.com/langchain-ai/langchain) —— Agent 状态机编排
- [Chroma](https://github.com/chroma-core/chroma) —— 向量数据库
- [Ragas](https://github.com/explodinggradients/ragas) —— RAG 评估框架
- [Streamlit](https://github.com/streamlit/streamlit) —— Web UI
- LLM 与 Embedding 服务：DeepSeek API、阿里云通义千问 DashScope

语料文档为自行构造的模拟企业制度，不涉及任何真实企业数据。

## License
MIT

