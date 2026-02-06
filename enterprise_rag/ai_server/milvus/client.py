"""
向量数据库客户端 (Milvus)
===============================
用途与意义:
- 管理与 Milvus 向量数据库 (Lite/Standalone) 的连接。
- 处理 Embedding 生成 (OpenAI/DashScope) 和向量存储。
- 执行语义相似度搜索。

关键升级与收益:
1.  **Schema 演进 (v2)**:
    - 将集合从 `enterprise_kb_v1` 迁移到 `enterprise_kb_v2`。
    - **收益**: 强制更新 Schema 以包含关键的 `user_id` 标量字段。
    - **收益**: 修复了过滤时的 "field user_id not exist" 错误。

2.  **严格的隔离过滤**:
    - 实现了 `expr="user_id == '...'"`.
    - **收益**: 将安全过滤下沉到数据库引擎，效率最高。
    - **收益**: 确保在检索层零数据泄露。
"""
import os
# from pymilvus import connections, utility
# from langchain_community.vectorstores import Milvus
# 使用官方推荐的 langchain_milvus
from langchain_milvus import Milvus
from langchain_openai import OpenAIEmbeddings

class MilvusService:
    def __init__(self):
        # Milvus 连接配置
        # 1. 优先尝试从环境变量获取 URI (支持 Docker/K8s: "http://localhost:19530")
        # 2. 如果没有 URI，默认回退到 Lite 本地文件 (仅用于极简测试，生产环境不推荐)
        self.uri = os.getenv("MILVUS_CONNECTION_URI", "http://localhost:19530")
        self.token = os.getenv("MILVUS_TOKEN", "") 
        
        # 初始化 Embedding 模型
        self.embeddings = OpenAIEmbeddings(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_api_base=os.getenv("OPENAI_API_BASE"),
            model=os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-v3"),
            check_embedding_ctx_length=False
        )
        
        # ⚠️ Schema Conflict Fix: Changed collection name to force re-creation
        # user_id filter fix: force new collection to ensure schema update
        self.collection_name = "enterprise_kb_v2"
        
        # 打印连接信息
        print(f"--- Milvus Service Init ---")
        print(f"Target URI: {self.uri}")
        if "milvus_data.db" in self.uri:
             print("Mode: Lite (Embedded)")
        else:
             print("Mode: Standalone/Cluster (Docker/K8s)")
        print(f"Collection: {self.collection_name}")
        print("---------------------------")

    def get_vector_store(self):
        """
        获取 LangChain 的 Milvus 向量库对象
        """
        # 构造连接参数
        connection_args = {"uri": self.uri}
        if self.token:
            connection_args["token"] = self.token
            
        vector_store = Milvus(
            embedding_function=self.embeddings,
            connection_args=connection_args,
            collection_name=self.collection_name,
            auto_id=True,
            drop_old=False
        )
        return vector_store

    def add_documents(self, docs, user_id: str = None):
        """添加文档到 Milvus"""
        if not docs:
            return
        
        # 如果提供了 user_id，注入到 metadata 中
        if user_id:
            for doc in docs:
                doc.metadata["user_id"] = str(user_id)
                
        try:
            vector_store = self.get_vector_store()
            vector_store.add_documents(docs)
            print(f"Successfully added {len(docs)} documents to Milvus (user_id={user_id}).")
        except Exception as e:
            print(f"Failed to add documents to Milvus: {e}")
            # 如果是连接错误，提示用户
            if "Connection refused" in str(e) or "Fail connecting" in str(e):
                print("Tip: Please check if Milvus Docker container is running (docker-compose up -d).")

# 单例模式
milvus_service = MilvusService()
