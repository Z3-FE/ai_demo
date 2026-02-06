# LangChain 调试与可观测性工具指南

在开发 LangChain 应用（尤其是 RAG 系统）时，因为涉及多步链路（检索、Prompt 组装、LLM 调用、解析），调试往往比较困难。

以下是整理的一份从**轻量级**到**企业级**的调试工具清单。

---

## 1. 原生轻量级调试 (开发阶段首选)

无需安装额外复杂的依赖，直接利用 LangChain 内置功能。

### 1.1 全局 Debug 模式
最简单粗暴的方法，会打印出每一个 Step 的输入输出。

```python
from langchain.globals import set_debug

# 开启全局调试模式，控制台会输出大量详细日志
set_debug(True)

# 运行你的 Chain
chain.invoke("query")

# 关闭
set_debug(False)
```

### 1.2 StdOutCallbackHandler
如果你只想看 Chain 的执行过程，而不是所有底层细节。

```python
from langchain_core.tracers import ConsoleCallbackHandler

# 在 invoke 时传入 config
chain.invoke(
    "query",
    config={'callbacks': [ConsoleCallbackHandler()]}
)
```

**输出效果**：会清晰地显示 `Chains` -> `LLM` -> `Tool` 的嵌套调用结构。

---

## 2. 可视化追踪工具 (Trace & Observability)

当链路变复杂（Agent、多路检索）时，看控制台日志已经不够用了。

### 2.1 LangSmith (官方推荐)
LangChain 官方出品，功能最强，但需要注册账号（有免费额度）。

*   **优点**：
    *   **可视化追踪**：能看到完整的 Token 消耗、延迟、输入输出。
    *   **Prompt 游乐场**：可以在网页上直接修改 Prompt 重跑某一次失败的请求。
    *   **数据集评估**：可以建立测试集进行回归测试。

*   **配置**：
    ```bash
    export LANGCHAIN_TRACING_V2=true
    export LANGCHAIN_API_KEY="your-api-key"
    export LANGCHAIN_PROJECT="my-rag-project"
    ```

### 2.2 Arize Phoenix (本地化神器)
如果你不想把数据传到云端，Phoenix 是目前最好的**本地化**开源替代品，尤其擅长 **RAG 检索评估**。

*   **特点**：
    *   **Embedding 可视化**：能把你的文档向量和 Query 向量画在 3D 空间里，一眼看出为什么检索偏了。
    *   **本地 Dashboard**：`pip install arize-phoenix` 启动后，本地浏览器访问。

*   **集成**：
    ```python
    from phoenix.trace.langchain import LangChainInstrumentor
    LangChainInstrumentor().instrument()
    ```

---

## 3. RAG 专项评估工具

针对 RAG 系统“查得准不准”、“答得对不对”的专项评估。

### 3.1 Ragas
目前最流行的 RAG 评估框架。它利用 LLM 来评估 LLM（LLM-as-a-Judge）。

*   **核心指标**：
    *   **Faithfulness (忠实度)**：回答是否忠实于检索到的上下文（防幻觉）。
    *   **Answer Relevance (回答相关性)**：回答是否解决了用户问题。
    *   **Context Precision (上下文精度)**：检索到的文档里有多少是有用的。

*   **用法**：
    ```python
    from ragas import evaluate
    from ragas.metrics import faithfulness, answer_relevance
    
    results = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevance]
    )
    ```

### 3.2 DeepEval
类似 Ragas，但提供了更接近 PyTest 的体验，适合集成到 CI/CD 流水线中。

---

## 4. 推荐组合

*   **日常开发 (MVP)**: `set_debug(True)` 或 `ConsoleCallbackHandler`。
*   **复杂链路调试**: **LangSmith** (如果有 Key) 或 **Phoenix** (本地)。
*   **上线前质量验收**: **Ragas** (批量跑测试集，确保准确率达标)。
