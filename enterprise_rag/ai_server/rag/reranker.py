import os
import json

from langchain_community.document_compressors import DashScopeRerank
from langchain_core.documents import BaseDocumentCompressor


class DashScopeRerankSever:
   def __init__(self, top_n=5):
      self.top_n = top_n
      self.reranker = DashScopeRerank(
        model=os.getenv("RERANKER_MODEL_NAME"),
        dashscope_api_key=os.getenv("OPENAI_API_KEY"),
        top_n=self.top_n  # 重排后返回最相关的前3个
    )


dashscope_rerank = DashScopeRerankSever(top_n=5)
