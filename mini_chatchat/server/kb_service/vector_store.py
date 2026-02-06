import os
from typing import List
from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

class VectorStoreService:
    """
    向量库服务 (基于 Chroma + OpenAI 兼容接口)
    """
    
    def __init__(self, collection_name="mini_kb"):
        # 从环境变量读取 Key
        api_key = os.getenv("OPENAI_API_KEY")
        # 强制使用 DashScope 的 OpenAI 兼容端点
        base_url = os.getenv("OPENAI_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        embedding_model = os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-v3")
        
        # 初始化 Embedding 模型 (使用 OpenAIEmbeddings 但指向 DashScope)
        self.embeddings = OpenAIEmbeddings(
            api_key=api_key,
            base_url=base_url,
            model=embedding_model,
            check_embedding_ctx_length=False # 禁用上下文长度检查，避免不必要的报错
        )
        
        # 持久化目录
        self.persist_directory = "./chroma_db"
        
        # 初始化向量库
        self.vector_store = Chroma(
            collection_name=collection_name,
            embedding_function=self.embeddings,
            persist_directory=self.persist_directory
        )
    
    def add_documents(self, docs: List[Document]):
        """将文档向量化并存入库"""
        if not docs:
            return
            
        # 再次强制清洗：确保 page_content 绝对是字符串，且不为空
        valid_docs = []
        for doc in docs:
            # 判断doc.page_content是否有值，是否是字符串类型，是否为空字符串
            if doc.page_content and isinstance(doc.page_content, str) and doc.page_content.strip():
                # DashScope 对空字符串非常敏感，双重检查
                valid_docs.append(doc)
                
        if not valid_docs:
            print("Warning: 重新验证后没有可添加的有效文件.")
            return

        try:
            # 批量添加，如果一次性太大可能也会报错，可以考虑分批，这里先直接添加
            self.vector_store.add_documents(valid_docs)
            print(f"Successfully added {len(valid_docs)} documents to Chroma.")
        except Exception as e:
            print(f"Error adding documents to Chroma: {e}")
            raise e

    def search(self, query: str, top_k=3):
        """相似度检索"""
        return self.vector_store.similarity_search(query, k=top_k)

    def as_retriever(self):
        """返回 LangChain 标准 Retriever 对象"""
        return self.vector_store.as_retriever(
            search_type="similarity",
            search_kwargs={"k": 3}
        )
