import os
from dotenv import load_dotenv
from milvus.client import milvus_service
from rag.bm25_service import bm25_service

# 加载环境变量
load_dotenv()

def check_milvus():
    print("\n=== Checking Milvus Vector Store ===")
    try:
        vector_store = milvus_service.get_vector_store()
        # 尝试检索 "Milvus" 相关内容
        results = vector_store.similarity_search("Milvus", k=5)
        
        if not results:
            print("No documents found in Milvus.")
        else:
            print(f"Found {len(results)} relevant documents:")
            for i, doc in enumerate(results):
                content_preview = doc.page_content[:100].replace("\n", " ")
                print(f"[{i+1}] {content_preview}...")
                print(f"    Source: {doc.metadata.get('source', 'Unknown')}")
    except Exception as e:
        print(f"Milvus Error: {e}")

def check_bm25():
    print("\n=== Checking BM25 Keyword Index ===")
    try:
        # BM25 是纯内存 + Pickle 持久化的，直接看 bm25_service.documents 长度
        doc_count = len(bm25_service.documents)
        print(f"Total documents in BM25 index: {doc_count}")
        
        if doc_count > 0:
            # 尝试检索
            retriever = bm25_service.get_retriever()
            results = retriever.invoke("Milvus")
            print(f"BM25 Search 'Milvus' results: {len(results)}")
            for i, doc in enumerate(results[:3]):
                print(f"[{i+1}] {doc.page_content[:50]}...")
    except Exception as e:
        print(f"BM25 Error: {e}")

if __name__ == "__main__":
    check_milvus()
    check_bm25()
