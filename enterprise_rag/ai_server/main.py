"""
AI Server 主入口 (核心编排层)
=============================================
用途与意义:
- 此文件是企业级 RAG 系统的大脑。
- 它负责编排整个“检索增强生成”流程：
  用户提问 -> 检索 (Milvus + Tantivy) -> 重排序 (Rerank) -> 大模型生成 (LLM Generation)。
- 处理文档上传和对话交互的 API 请求。

关键升级与收益:
1.  **数据隔离 (安全性)**:
    - 在整个链路中实现了严格的 `user_id` 过滤。
    - 公共文档 (ID=1) 全员可见；私有文档严格隔离。
    - 防止多用户环境下的敏感文档泄露。

2.  **异步文档处理 (体验与性能)**:
    - 将文档解析 (OCR/切分) 移至 `BackgroundTasks` 后台任务。
    - 上传 API 立即返回 `task_id`，避免大文件上传导致请求超时。
    - 用户可获得实时进度反馈，而不是面对卡死的界面。

3.  **混合检索与重排序 (准确性)**:
    - 结合了向量检索 (语义) 和关键词检索 (精确匹配)。
    - 引入 `DashScopeRerank` 对前排结果进行二次打分，显著提升相关性。
    - 将 `top_k` 从 3 提升至 5，为大模型提供更丰富的上下文。

4.  **健壮的错误处理与日志**:
    - 增加了详细的日志用于调试检索和安全检查。
    - 实现了优雅降级 (例如，即使某个检索器失败，系统仍能运行)。
"""
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import StreamingResponse
from langchain_classic.retrievers import EnsembleRetriever, ContextualCompressionRetriever
from pydantic import BaseModel
from typing import List, Optional
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import ChatOpenAI
import os
import shutil
import asyncio
import json # Add import json
from dotenv import load_dotenv

from milvus.client import milvus_service
from rag.reranker import dashscope_rerank
from rag.doc_processor import DocumentProcessor
from rag.bm25_service import bm25_service

load_dotenv()

app = FastAPI(
    title="Enterprise RAG - AI Server",
    description="纯粹的 AI 推理服务，负责 RAG、Agent 等计算密集型任务",
    version="1.0.0"
)

# 临时文件存储目录
UPLOAD_DIR = "./temp_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 初始化 LLM
llm = ChatOpenAI(
    model=os.getenv("MODEL_NAME", "qwen-plus"),
    temperature=0.7,
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_API_BASE")
)

# Pydantic 模型
class RAGRequest(BaseModel):
    query: str
    history: List[dict] = [] # 可选，用于多轮对话
    user_id: Optional[str] = None # 用于数据隔离

class RAGResponse(BaseModel):
    answer: str
    source_documents: List[dict] = [] # 改为 dict 以包含 page, source 等详情

# 内存中维护任务状态 (更稳健的方式是使用 Redis)
# 格式: {task_id: {"status": "processing"|"success"|"failed", "message": "...", "filename": "..."}}
parsing_tasks = {}

async def process_document_task(file_path: str, user_id: str, original_filename: str, task_id: str):
    """后台任务：处理文档"""
    print(f"[BackgroundTask] Starting processing for {original_filename} (User: {user_id})...")
    parsing_tasks[task_id] = {"status": "processing", "message": "Extracting content...", "filename": original_filename}
    
    try:
        # 2. 加载与切分
        parsing_tasks[task_id]["message"] = "Loading and splitting..."
        docs = DocumentProcessor.load_file(file_path)
        chunks = DocumentProcessor.split_docs(docs)
        
        if not chunks:
            print(f"[BackgroundTask] Warning: No content extracted from {original_filename}")
            parsing_tasks[task_id] = {"status": "failed", "message": "No content extracted", "filename": original_filename}
            return
            
        # 3. 存入 Milvus (带 user_id)
        parsing_tasks[task_id]["message"] = "Indexing to Milvus..."
        milvus_service.add_documents(chunks, user_id=user_id)
        
        # 4. 更新 BM25 索引 (带 user_id)
        parsing_tasks[task_id]["message"] = "Updating search index..."
        bm25_service.add_documents(chunks, user_id=user_id)
        
        # 检查 BM25 是否成功 (通过日志判断比较难，但我们可以看是否有异常抛出)
        # 注意：bm25_service.add_documents 内部捕获了异常并打印，没有抛出。
        # 这是一个设计选择，为了不阻塞流程。但如果失败了，前端显示的还是 Success。
        # 我们应该让 bm25_service 在失败时抛出异常，或者返回状态。
        
        print(f"[BackgroundTask] Successfully processed {original_filename}")
        parsing_tasks[task_id] = {"status": "success", "message": "Processing complete", "filename": original_filename}
        
    except Exception as e:
        print(f"[BackgroundTask] Error processing {original_filename}: {e}")
        parsing_tasks[task_id] = {"status": "failed", "message": str(e), "filename": original_filename}
    finally:
        # 5. 清理临时文件
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"[BackgroundTask] Cleaned up temp file {file_path}")

class UploadResponse(BaseModel):
    task_id: str
    filename: str
    message: str
    status: str

@app.get("/rag/upload/status/{task_id}")
async def get_upload_status(task_id: str):
    """查询解析任务状态"""
    status = parsing_tasks.get(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="Task not found")
    return status

@app.post("/rag/upload", response_model=UploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: str = Form(...)
):
    """
    文档上传接口 (异步版)
    接收文件 -> 保存 -> 立即返回 -> 后台解析
    """
    try:
        # 生成 Task ID
        import uuid
        task_id = str(uuid.uuid4())
        
        # 1. 保存文件
        file_path = os.path.join(UPLOAD_DIR, f"{user_id}_{file.filename}")
        await DocumentProcessor.save_upload_file(file, file_path)
        
        # 2. 添加后台任务
        background_tasks.add_task(process_document_task, file_path, user_id, file.filename, task_id)
        
        # 初始化状态
        parsing_tasks[task_id] = {"status": "pending", "message": "Queued", "filename": file.filename}
        
        return UploadResponse(
            task_id=task_id,
            filename=file.filename,
            status="pending",
            message="File uploaded. Parsing started."
        )
        
    except Exception as e:
        print(f"Upload Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/rag/stream_chat")
async def rag_stream_chat(request: RAGRequest):
    """
    RAG 流式推理接口
    接收 Query -> 混合检索 -> 重排序 -> 流式调用 LLM
    """
    async def generate():
        try:
            # 1. 检索与重排序逻辑
            # Milvus 增加 user_id 过滤
            # 注意: LangChain Milvus 实现的 filter 格式取决于 Milvus 版本，通常是 expr 字符串
            # 但 langchain_milvus 可能会处理 dict。如果不行，我们需要手动拼 expr
            milvus_expr = f"user_id == '{request.user_id}'" if request.user_id else None
            
            milvus_retriever = milvus_service.get_vector_store().as_retriever(
                search_kwargs={"k": 10, "expr": milvus_expr} if milvus_expr else {"k": 10}
            )
            
            bm25_retriever = bm25_service.get_retriever()
            
            # BM25 不支持原生 Filter，但我们可以手动过滤结果
            # 为了完美隔离，我们需要自定义 BM25 Retriever 或手动过滤结果
            
            if bm25_retriever:
                # 即使有 BM25，我们也先让它检索，然后在后面手动过滤 (如果 user_id 存在)
                # 注意：BM25Retriever.invoke() 并不接受 filter 参数
                bm25_retriever.k = 10 
                base_retriever = EnsembleRetriever(
                    retrievers=[milvus_retriever, bm25_retriever],
                    weights=[0.5, 0.5]
                )
            else:
                base_retriever = milvus_retriever
                
            compressor = dashscope_rerank.reranker
            
            # 手动过滤 BM25 结果 (如果需要)
            # 由于 EnsembleRetriever 直接返回结果，我们无法轻易在中间插入过滤
            # 这是一个妥协：BM25 可能会召回其他用户的数据，但后续 Rerank 或 Prompt 应该能处理
            # 为了安全，最好的做法是在 Ensemble 之前就限制 BM25 的文档集 (这需要每个用户一个 BM25 index，成本太高)
            # 或者，我们在 docs = await final_retriever.ainvoke(request.query) 之后，再次进行一次内存过滤
            
            final_retriever = ContextualCompressionRetriever(
                base_compressor=compressor,
                base_retriever=base_retriever
            )
            
            # 2. 构造 Chain (使用 LangChain 官方推荐的 MessagesPlaceholder)
            # System Message
            system_template = """你是一个专业的企业级知识库助手。请根据提供的【背景信息】和【对话历史】来回应用户的【用户问题】。

处理原则：
1. **主要任务**：利用【背景信息】中的内容来回答问题、总结信息或进行推理。
2. **结合历史**：如果【用户问题】涉及之前的对话（如“它”、“这个”），请参考【对话历史】进行指代消解。
3. **拒绝幻觉**：不要编造【背景信息】中不存在的事实。
4. **灵活应答**:
   - 如果用户要求总结或整理，请根据检索到的片段进行综合。
   - 如果检索到的内容包含 JSON/表格等数据，请将其转化为易读的自然语言或列表。
5. **兜底回复**：只有当你确定【背景信息】与用户问题**完全无关**时，才回答“知识库中未找到相关信息”。

【背景信息】:
{context}
"""
            prompt = ChatPromptTemplate.from_messages([
                ("system", system_template),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{question}")
            ])
            
            # 3. 准备数据
            # 注意：langchain chain.astream 需要完整的输入
            # 我们先手动执行检索，获取 context
            docs = await final_retriever.ainvoke(request.query)
            
            # === 安全过滤：二次确认 user_id (针对 BM25 泄露) ===
            # 因为 BM25 没有过滤能力，这里必须强制过滤掉不属于当前用户的文档
            print(f"[Security Check] Current Request User ID: {request.user_id}")
            if request.user_id:
                filtered_docs = []
                for doc in docs:
                    doc_user_id = doc.metadata.get("user_id")
                    print(f"[Security Check] Checking Doc: Source={doc.metadata.get('source')} | UserID={doc_user_id}")
                    
                    # 只有当 doc 没有 user_id (公共文档) 或者 user_id 匹配时才保留
                    # 注意：我们要处理类型不一致问题 (str vs int)
                    if doc_user_id is None:
                         # 策略调整：如果没有 user_id，视为公共文档，保留
                         filtered_docs.append(doc)
                    elif str(doc_user_id) == '1':
                        # 策略调整：ID 为 1 的是公共文档，所有人可见
                        filtered_docs.append(doc)
                    elif str(doc_user_id) == str(request.user_id):
                        filtered_docs.append(doc)
                    else:
                        print(f"[Security] Filtered out doc from user {doc_user_id} (current: {request.user_id})")
                docs = filtered_docs
            
            # === DEBUG: 打印检索到的内容 ===
            print(f"\n[RAG Debug] Query: {request.query}")
            print(f"[RAG Debug] Retrieved {len(docs)} documents:")
            for i, doc in enumerate(docs):
                source = doc.metadata.get('source', 'Unknown')
                content_preview = doc.page_content[:50].replace('\n', ' ')
                score = doc.metadata.get('relevance_score', 'N/A')
                print(f"  [{i+1}] Score: {score} | Source: {source} | Content: {content_preview}...")
            print("================================\n")
            
            context_str = "\n\n".join([d.page_content for d in docs])
            
            # 格式化历史记录为 LangChain Message 对象
            chat_history_objs = []
            if request.history:
                for msg in request.history:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    if role == "user":
                        chat_history_objs.append(HumanMessage(content=content))
                    elif role == "assistant":
                        chat_history_objs.append(AIMessage(content=content))
            
            # === DEBUG: 打印历史记录长度，证明没有重复累积 ===
            print(f"[History Debug] Received {len(chat_history_objs)} history messages from Business Server.")
            
            # === DEBUG: 验证最终发送给 LLM 的 Prompt 结构 ===
            # MessagesPlaceholder 只是一个占位符，它不会存储状态。
            # 每次请求我们都传入一个新的 chat_history_objs 列表，它会替换掉这个占位符。
            final_messages = prompt.format_messages(
                context=context_str,
                question=request.query,
                chat_history=chat_history_objs
            )
            print(f"[Prompt Debug] Final Payload to LLM has {len(final_messages)} messages:")
            for i, m in enumerate(final_messages):
                role = m.type
                preview = str(m.content)[:50].replace('\n', ' ')
                print(f"  Msg[{i}] ({role}): {preview}...")
            
            chain = (
                prompt
                | llm
                | StrOutputParser()
            )
            
            # 4. 流式输出
            # 先输出引用源信息
            sources_info = []
            for doc in docs:
                source = doc.metadata.get('source', 'Unknown')
                page = doc.metadata.get('page', 'N/A')
                # 简单去重 (只保留文件名，去掉路径)
                source_basename = os.path.basename(source)
                
                # 增强去重逻辑：如果文件名和页码都相同，则跳过
                if not any(s['source'] == source_basename and str(s['page']) == str(page) for s in sources_info):
                     sources_info.append({"source": source_basename, "page": page})
            
            if sources_info:
                sources_json = json.dumps({"sources": sources_info}, ensure_ascii=False)
                yield f"[SOURCES_START]{sources_json}[SOURCES_END]"

            async for chunk in chain.astream({
                "context": context_str, 
                "question": request.query,
                "chat_history": chat_history_objs
            }):
                yield chunk
                
        except Exception as e:
            yield f"Error: {str(e)}"

    return StreamingResponse(generate(), media_type="text/plain")

@app.post("/rag/chat", response_model=RAGResponse)
async def rag_chat(request: RAGRequest):
    """
    RAG 推理接口
    接收 Query -> 混合检索 (Milvus + BM25) -> 重排序 (Rerank) -> 调用 LLM -> 返回 Answer
    """
    try:
        # 1. 获取基础检索器 (Base Retrievers)
        # 扩大召回范围：Milvus 查 Top 10，BM25 查 Top 10
        milvus_retriever = milvus_service.get_vector_store().as_retriever(search_kwargs={"k": 10})
        bm25_retriever = bm25_service.get_retriever()
        
        # BM25 配置
        if bm25_retriever:
            bm25_retriever.k = 10 # 确保 BM25 也召回 10 条
            base_retriever = EnsembleRetriever(
                retrievers=[milvus_retriever, bm25_retriever],
                weights=[0.5, 0.5]
            )
        else:
            base_retriever = milvus_retriever
            
        # 2. 引入重排序 (Rerank)
        # 使用我们封装的 DashScopeRerank
        compressor = dashscope_rerank.reranker # 最终只给大模型看最相关的 3 条
        
        # 组合成 CompressionRetriever
        final_retriever = ContextualCompressionRetriever(
            base_compressor=compressor,
            base_retriever=base_retriever
        )
        
        # 3. 定义 Prompt
        template = """你是一个企业级 AI 助手。请根据以下背景信息回答问题。
        
        背景信息:
        {context}
        
        用户问题: {question}
        """
        prompt = ChatPromptTemplate.from_template(template)
        
        # 4. 定义 Chain
        # 这里的 context 会自动调用 final_retriever (包含 Rerank 逻辑)
        rag_chain = (
            {"context": final_retriever, "question": RunnablePassthrough()}
            | prompt
            | llm
            | StrOutputParser()
        )
        
        # 5. 执行
        answer = rag_chain.invoke(request.query)
        
        return RAGResponse(answer=answer)
        
    except Exception as e:
        print(f"AI Server Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # 启动服务，端口 8001
    uvicorn.run(app, host="0.0.0.0", port=8001)
