"""
    启动： uv run api.py
"""

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import shutil
import os
from typing import List, Optional
from dotenv import load_dotenv
from operator import itemgetter

# 导入自定义 RAG 模块
from server.rag.doc_processor import DocumentProcessor
from server.kb_service.vector_store import VectorStoreService
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough, RunnableWithMessageHistory, RunnableParallel
from langchain_community.chat_message_histories import SQLChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory

# 导入数据库模块
from server.db import init_db, DB_PATH

# 加载环境变量
load_dotenv()

# 初始化数据库表
init_db()

# 初始化全局服务
kb_service = VectorStoreService()  # 向量库服务
llm = ChatOpenAI(
    model=os.getenv("MODEL_NAME", "qwen-plus"),
    temperature=0.7,
    openai_api_key=os.getenv("OPENAI_API_KEY"),
    openai_api_base=os.getenv("OPENAI_API_BASE")
)

# 帮助函数：获取历史记录对象
def get_session_history(session_id: str) -> BaseChatMessageHistory:
    # 这里的参数名必须叫 session_id 或者和 config 里的 key 对应
    return SQLChatMessageHistory(
        session_id=session_id,
        connection_string=DB_PATH
    )

# 初始化 FastAPI 应用
app = FastAPI(
    title="Mini-Chatchat API",
    description="A minimal implementation of LangChain-Chatchat backend",
    version="0.1.0"
)

# 允许跨域请求 (方便后续对接前端)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 基础数据模型
class ChatRequest(BaseModel):
    query: str
    session_id: str = "default_user"  # 新增 session_id，默认为 default_user
    # history 字段不再需要前端传递，后端自动从数据库取

class ChatResponse(BaseModel):
    answer: str
    session_id: str

# 临时文件存储目录
UPLOAD_DIR = "../temp_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.get("/")
async def root():
    """健康检查接口"""
    return {"message": "Mini-Chatchat API is running!"}

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    文件上传接口 -> 自动向量化
    功能: 接收用户上传的文件 -> 保存 -> 加载 -> 切分 -> 存入向量库
    """
    try:
        # 1. 保存文件到临时目录
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 2. 调用文档处理器加载并切分
        print(f"Processing file: {file.filename}...")
        docs = DocumentProcessor.load_file(file_path)
        chunks = DocumentProcessor.split_docs(docs)
        print(f"Split into {len(chunks)} chunks.")
        
        # 3. 存入向量库
        if not chunks:
            return {
                "filename": file.filename,
                "status": "warning",
                "message": "No valid text content found in file."
            }
            
        kb_service.add_documents(chunks)
        
        return {
            "filename": file.filename,
            "status": "success",
            "chunks_count": len(chunks),
            "message": "File processed and indexed successfully."
        }
    except Exception as e:
        print(f"Error processing file: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    RAG 对话接口 (支持持久化历史记录)
    功能: 接收问题 -> 检索向量库 -> 组装 Prompt (含历史) -> 调用 LLM 回答 -> 存入数据库
    """
    try:
        query = request.query
        session_id = request.session_id
        
        # 1. 定义 Prompt 模板 (增加 history 占位符)
        template = """你是一个智能助手。请根据以下已知信息回答用户的问题。如果无法从已知信息中找到答案，请诚实地说不知道。
 
        已知信息:
        {context}

        历史对话:
        {history}

        用户问题: {question}
        """
        prompt = ChatPromptTemplate.from_template(template)

        # 2. 获取 Retriever
        retriever = kb_service.as_retriever()
        
        # 帮助函数：格式化文档
        def format_docs(docs):
            if not docs:
                return "没有找到相关的已知信息。"
            return "\n\n".join(doc.page_content for doc in docs)

        # 3. 构建 RAG Chain (LCEL)
        # 使用 RunnableParallel 并行处理输入
        # 注意: 这里的 itemgetter 是从 operator 模块导入的，用于从字典中提取特定的键值
        """
        itemgetter("name") 等价于 data["name"]
        attrgetter("page_content") 等价于 doc.page_content
        """
        rag_chain = (
            RunnableParallel({
                "context": itemgetter("question") | retriever | format_docs,  # 1.显式提取 question 2. 传给 retriever 3. 格式化结果
                "question": itemgetter("question"),
                "history": itemgetter("history") # 这个 history 由 RunnableWithMessageHistory 注入
            })
            | prompt
            | llm
            | StrOutputParser()
        )
        
        # 4. 包装链，加入历史记录管理能力
        chain_with_history = RunnableWithMessageHistory(
            rag_chain, # 传入 RAG 链
            get_session_history, # 调用数据库获取历史记录函数
            input_messages_key="question",
            history_messages_key="history",
        )
        
        # 5. 执行链 (传入 session_id)
        print(f"Invoking RAG chain for query: {query}, session_id: {session_id}")
        
        # invoke 的参数结构发生变化，需要传入 config 指定 session_id
        answer = chain_with_history.invoke(
            {"question": query},
            config={"configurable": {"session_id": session_id}}
        )
        
        return ChatResponse(answer=answer, session_id=session_id)
        
    except Exception as e:
        print(f"Error in chat: {e}")
        # 出错时也要返回 session_id 以保持前端一致性
        return ChatResponse(answer=f"Sorry, something went wrong: {str(e)}", session_id=request.session_id)

if __name__ == "__main__":
    import uvicorn
    # 启动服务: host="0.0.0.0" 表示允许局域网访问
    uvicorn.run(app, host="0.0.0.0", port=8000)
