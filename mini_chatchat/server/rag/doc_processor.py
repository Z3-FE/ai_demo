import os
from typing import List
from langchain_community.document_loaders import (
    UnstructuredFileLoader,
    TextLoader,
    JSONLoader,
    CSVLoader
)
from langchain_community.document_loaders.pdf import PyPDFLoader
from langchain_community.document_loaders.markdown import UnstructuredMarkdownLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

class DocumentProcessor:
    """
    文档处理核心类
    功能: 自动识别文件类型加载 -> 文本清洗 -> 切分 (Split)
    """
    
    # 支持的文件扩展名映射
    LOADER_MAPPING = {
        ".txt": TextLoader,
        ".pdf": PyPDFLoader,
        ".md": UnstructuredMarkdownLoader,
        ".csv": CSVLoader,
        ".json": JSONLoader,
    }

    @staticmethod
    def load_file(file_path: str) -> List[Document]:
        """加载单个文件"""
        ext = os.path.splitext(file_path)[-1].lower()
        
        if ext not in DocumentProcessor.LOADER_MAPPING:
            # 默认尝试用 Unstructured 加载未知格式
            loader = UnstructuredFileLoader(file_path)
        else:
            loader_class = DocumentProcessor.LOADER_MAPPING[ext]
            # 针对不同 Loader 的特殊参数处理
            if loader_class == TextLoader:
                loader = loader_class(file_path, encoding="utf-8", autodetect_encoding=True)
            else:
                loader = loader_class(file_path)
                
        return loader.load()

    @staticmethod
    def split_docs(docs: List[Document], chunk_size=500, chunk_overlap=50) -> List[Document]:
        """
        文本切分
        :param chunk_size: 每个片段的最大字符数
        :param chunk_overlap: 上下文重叠字符数 (防止语义切断)
        """
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "。", "！", "？", " ", ""]
        )
        chunks = text_splitter.split_documents(docs)
        
        # 过滤掉空文档，确保 page_content 是非空字符串
        filtered_chunks = [
            doc for doc in chunks 
            if doc.page_content and isinstance(doc.page_content, str) and doc.page_content.strip()
        ]
        
        print(f"Original chunks: {len(chunks)}, Filtered chunks: {len(filtered_chunks)}")
        return filtered_chunks

if __name__ == "__main__":
    # 简单测试代码
    print("DocumentProcessor ready.")
