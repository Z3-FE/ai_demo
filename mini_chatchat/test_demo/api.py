import os
import sqlite3
from typing import Dict, TypedDict, Annotated, List
import operator

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import create_react_agent

# 引入向量库服务
from server.kb_service.vector_store import VectorStoreService

# 加载环境变量
load_dotenv()

# 初始化向量库服务 (复用之前的逻辑)
kb_service = VectorStoreService()

# 1. 定义工具 (Tools)
@tool
def retrieve_knowledge(query: str) -> str:
    """
    当用户询问关于具体的知识、文档内容、事实性问题时，必须调用此工具。
    输入用户的具体问题，返回从知识库中检索到的相关片段。
    """
    print(f"🛠️ [Agent] 正在调用检索工具: {query}")
    docs = kb_service.search(query, top_k=3)
    if not docs:
        return "未找到相关信息。"
    # 将文档内容拼接成字符串返回
    return "\n\n".join([f"片段 {i+1}: {doc.page_content}" for i, doc in enumerate(docs)])

@tool
def get_weather(city: str) -> str:
    """
    查询天气的工具。输入城市名称，返回当前天气。
    """
    print(f"🛠️ [Agent] 正在查询天气: {city}")
    return f"{city} 今天晴空万里，气温 25℃，适合写代码！"

# 工具列表
tools = [retrieve_knowledge, get_weather]

# 2. 初始化 LLM
llm = ChatOpenAI(
    model=os.getenv("MODEL_NAME", "qwen-plus"),
    temperature=0.5, # Agent 场景建议调低 temperature 以提高工具调用稳定性
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_API_BASE")
)

# 3. 初始化持久化 Checkpointer
conn = sqlite3.connect("agent_checkpoints.db", check_same_thread=False)
memory = SqliteSaver(conn)

# 4. 创建 Agent
# 注入了 tools，LLM 就会自动识别是否需要调用
agent = create_agent(
    llm,
    tools=tools, 
    checkpointer=memory,
    system_prompt="你是一个全能助手。对于用户的问题，优先查阅知识库。如果是闲聊，则直接回答。"
)

# 5. 调用测试
config = {"configurable": {"thread_id": "session_z523_rag_001"}}

print("\n--- Round 1: 闲聊测试 ---")
res1 = agent.invoke(
    {"messages": [("user", "你好，我是钟凯强")]}, 
    config=config
)
print(f"AI: {res1['messages'][-1].content}")

print("\n--- Round 2: 知识库检索测试 ---")
# 这里假设你的向量库里已经存了一些东西 (比如之前的 pdf)
# 如果没有存，它会返回"未找到相关信息"，然后 AI 会告诉你没找到
res2 = agent.invoke(
    {"messages": [("user", "我的知识库里有什么内容？或者帮我找找关于 Trae 的介绍")]}, 
    config=config
)
print(f"AI: {res2['messages'][-1].content}")

print("\n--- Round 3: 天气工具测试 ---")
res3 = agent.invoke(
    {"messages": [("user", "北京天气怎么样？")]}, 
    config=config
)
print(f"AI: {res3['messages'][-1].content}")


