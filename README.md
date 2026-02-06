# LangChain 项目落地实战学习路线图 (基于 LangChain-Chatchat)

source .venv/bin/activate

这份指南旨在帮助你从“懂语法”进阶到“能落地”，以 LangChain-Chatchat 为核心案例，通过**“拆解-复刻-进阶”**三个阶段，掌握大模型应用开发的全部技能。

## 阶段一：架构拆解与源码阅读 (Week 1)
**目标**：理解成熟的 RAG 系统是如何组织的，不再局限于单文件脚本。

### 1.1 项目全貌认知
- [ ] **目录结构分析**：
    - `configs/`: 为什么要将模型配置、服务配置分离？
    - `server/`: 核心后端逻辑。
    - `chains/`: 自定义的 Chain 是怎么写的。
- [ ] **启动流程追踪**：
    - 阅读 `startup.py`，理解如何同时启动 API 服务、WebUI 和 Model Worker。

### 1.2 核心模块深挖 (重点)
- [ ] **Knowledge Base (知识库)**：
    - 找到 `server/knowledge_base/kb_service/base.py`，看它是如何定义抽象类的。
    - 学习 `faiss_kb_service.py` 或 `milvus_kb_service.py`，看它如何实现具体的增删改查。
- [ ] **Chat 接口**：
    - 阅读 `server/chat/chat.py` 和 `knowledge_base_chat.py`。
    - **关键点**：学习 FastAPI 的 `StreamingResponse` 是如何结合 LangChain 的 `CallbackHandler` 实现流式输出的。

---

## 阶段二：最小化复刻 "Mini-Chatchat" (Week 2)
**目标**：脱离源码，自己动手实现一个精简版核心链路，拒绝“只会跑 Demo”。

### 2.1 搭建后端 API (FastAPI)
- [ ] 初始化一个标准的 FastAPI 项目结构。
- [ ] 实现 `/upload` 接口：接收文件并保存到临时目录。
- [ ] 实现 `/chat` 接口：接收用户 Prompt，调用 OpenAI/本地模型返回结果。

### 2.2 实现核心 RAG 引擎
- [ ] **Loader 封装**：编写一个函数，根据文件后缀自动选择 Loader (PDF/TXT/MD)。
- [ ] **Vector Store 封装**：不使用 LangChain 的默认类，而是封装一个 `KBService` 类，管理向量库的加载与保存。
- [ ] **Chain 组装**：使用 LCEL (LangChain Expression Language) 编写 RAG 链：
  ```python
  chain = (
      {"context": retriever, "question": RunnablePassthrough()} 
      | prompt 
      | llm 
      | StrOutputParser()
  )
  ```

### 2.3 对接简易前端
- [ ] 使用 Streamlit 快速搭建界面，调用自己写的 FastAPI 接口（模拟前后端分离）。

---

## 阶段三：企业级进阶与优化 (Week 3)
**目标**：解决“不好用”的问题，增加高级特性。

### 3.1 检索效果优化 (Advanced RAG)
- [ ] **混合检索**：引入 BM25 关键词检索，与向量检索加权融合。
- [ ] **重排序 (Rerank)**：在检索后引入 BGE-Reranker 模型，对前 50 个结果进行精排。
目前的纯向量检索（Dense Retrieval）有一个缺点： 对专有名词或精确匹配不敏感 。
比如用户搜“Trae v1.2.3 更新了什么？”，向量检索可能会找“版本更新”相关的内容，但不一定能精准匹配到 "v1.2.3" 这个具体的关键词。

解决方案是 混合检索 (Hybrid Search) ：

- 向量检索 (Chroma) : 擅长理解语义（“苹果”和“水果”）。
- 关键词检索 (BM25) : 擅长精确匹配（“v1.2.3”）。
- 加权融合 (Ensemble) : 将两者的结果结合起来，取长补短。

### 3.2 长期记忆与会话管理
- [ ] 引入 Redis 或 SQL 数据库存储 `SessionID` 和对应的历史消息。
- [ ] 实现 `HistoryAwareRetriever`，将“它的价格是多少？”重写为“iPhone 15 的价格是多少？”。

### 3.3 工具调用 (Agent)
- [ ] 为系统增加“联网搜索”或“查询天气”的 Tool。
- [ ] 改造 Chat 接口，使其能够根据意图自动判断是查知识库还是查工具。

---

## 阶段四：工程化与部署 (Week 4)
**目标**：符合公司生产环境标准。

### 4.1 容器化交付
- [ ] 编写 `Dockerfile`，将环境打包。
- [ ] 编写 `docker-compose.yml`，编排 API 服务、向量库(Milvus) 和 数据库(MySQL)。

### 4.2 监控与评估
- [ ] 接入 **LangSmith** 或 **LangFuse**，监控 Token 消耗和 Trace。
- [ ] 使用 **RAGAS** 框架建立一套自动化测试集，评估问答准确率。

---

## 学习资源推荐
1. **官方文档**: LangChain Python Docs (紧跟最新版本)
2. **源码**: LangChain-Chatchat (反复阅读)
3. **工具**: LangSmith (调试神器)
