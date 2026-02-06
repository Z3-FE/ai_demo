# Mini-Chatchat 实现指南：会话持久化与 RAG 链式调用

本文档详细记录了在 `Mini-Chatchat` 项目中实现 RAG（检索增强生成）与会话持久化（Session Persistence）的核心逻辑、实现步骤及关键函数解析。

## 1. 核心思路

我们的目标是打造一个既能“查文档”又能“记上下文”的智能助手。为此，我们采用了以下架构：

1.  **数据隔离**：通过 `session_id` 区分不同用户的会话。
2.  **持久化存储**：使用 SQLite 数据库 (`SQLChatMessageHistory`) 存储用户的历史对话记录。
3.  **链式调用 (LCEL)**：利用 LangChain 强大的表达式语言，将 检索 -> 历史回填 -> Prompt -> LLM 串联成一个流水线。

---

## 2. 实现步骤

### 第一步：数据库层 (DB Layer)
创建 `server/db.py`，使用 SQLAlchemy 初始化 SQLite 数据库，用于存储聊天记录。

*   **表结构**：`chat_history` 表，包含 `session_id`, `role`, `content` 等字段。
*   **工具**：`SQLAlchemy` (ORM 框架)。

### 第二步：API 层 (FastAPI)
修改 `server/api.py`，这是系统的核心枢纽。

1.  **引入历史管理**：使用 `SQLChatMessageHistory` 类，它能自动对接 SQLite。
2.  **定义 RAG 链**：
    *   **并行处理 (`RunnableParallel`)**：同时做三件事：
        1.  拿问题去向量库查资料 (`retriever`)。
        2.  拿问题直接传给 Prompt (`question`)。
        3.  拿 `session_id` 去数据库查历史记录 (`history`)。
    *   **Prompt 组装**：把查到的资料、历史记录、当前问题填入模板。
    *   **LLM 生成**：调用通义千问生成回答。
3.  **自动管理历史 (`RunnableWithMessageHistory`)**：
    *   这是一个“包装器”，它把上面的 RAG 链包起来。
    *   **前置操作**：链执行前，自动根据 `session_id` 从数据库拉取历史，填入 `history` 字段。
    *   **后置操作**：链执行完，自动把用户的 `question` 和 AI 的 `answer` 存回数据库。

### 第三步：前端层 (React)
修改 `frontend/src/App.jsx`。

1.  **生成 ID**：用户首次访问时，生成一个随机 `session_id` 并存入 `localStorage`。
2.  **传递 ID**：每次发请求给 `/chat` 接口时，带上这个 `session_id`。
3.  **展示优化**：前端不再自己维护发给后端的 `history` 列表，只负责展示。

---

## 3. 关键函数与对象解析 (核心中的核心)

### 3.1 `RunnableParallel` (并行运行)
*   **作用**：同时执行多个任务，并把结果组合成一个字典。
*   **代码位置**：[api.py](file:///Users/z523/Desktop/zizhi/ai_Python/ai_dome/mini_chatchat/server/api.py#L154-L160)
*   **逻辑**：
    ```python
    RunnableParallel({
        # 任务 1: 查资料
        # itemgetter("question") -> 取出问题字符串
        # | retriever -> 查向量库 -> 返回 Document 列表
        # | format_docs -> 把 Document 列表拼成一个长字符串
        "context": itemgetter("question") | retriever | format_docs,

        # 任务 2: 传递问题
        "question": itemgetter("question"),

        # 任务 3: 占位 (由外层包装器填充)
        "history": itemgetter("history") 
    })
    ```

### 3.2 `RunnableWithMessageHistory` (历史记录包装器)
*   **作用**：给普通的链“挂载”上记忆能力。
*   **代码位置**：[api.py](file:///Users/z523/Desktop/zizhi/ai_Python/ai_dome/mini_chatchat/server/api.py#L167-L172)
*   **参数详解**：
    *   `runnable`: 被包装的核心链 (`rag_chain`)。
    *   `get_session_history`: 一个回调函数，告诉 LangChain 去哪里取历史记录（这里是去 SQLite）。
    *   `input_messages_key="question"`: 告诉它，用户的输入是字典里的哪个字段。
    *   `history_messages_key="history"`: 告诉它，取出来的历史记录要塞到 Prompt 的哪个变量里。

### 3.3 `itemgetter` (数据提取器)
*   **作用**：从字典中精准提取某个 Key 的值。
*   **为什么用它**：比 `lambda x: x["key"]` 更高效，且支持 LangChain 的序列化。
*   **场景**：
    *   `itemgetter("question")`：从输入 `{"question": "你好", "session_id": "..."}` 中只把 "你好" 取出来传给 Retriever。

---

## 4. 数据流转图 (Data Flow)

```mermaid
graph TD
    A[用户输入: "你好"] -->|前端| B(API: /chat)
    B -->|session_id| C{RunnableWithMessageHistory}
    
    C -->|1. 拉取历史| D[(SQLite 数据库)]
    D -->|历史记录| C
    
    C -->|输入: question + history| E[RunnableParallel]
    
    E -->|2. 并行: 查向量库| F[Retriever]
    F -->|Document 列表| G[format_docs]
    G -->|Context 字符串| H[Prompt Template]
    
    E -->|3. 并行: 传递历史| H
    E -->|4. 并行: 传递问题| H
    
    H -->|完整 Prompt| I[LLM (通义千问)]
    I -->|Answer| J[输出解析器]
    
    J -->|最终回答| C
    C -->|5. 自动保存对话| D
    C -->|返回结果| A
```
