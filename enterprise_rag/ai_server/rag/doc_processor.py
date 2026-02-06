"""
文档处理流水线 (ETL)
==================================
用途与意义:
- 负责用户文档的提取 (Extract)、转换 (Transform) 和加载 (Load)。
- 支持 PDF, DOCX, TXT, JSON, CSV 等多种格式。
- 执行文本切分 (Chunking)，为 Embedding 准备数据。

关键升级与收益:
1.  **优化的切分策略 (上下文保留)**:
    - 将 `chunk_size` 从 500 增加到 1000 字符。
    - **收益**: 每个分片保留更多语义上下文 (例如，保持“姓名”和“经历”在一起)。
    - **收益**: 减少了关键信息被切断导致的“迷失在中间”现象。

2.  **元数据增强**:
    - 自动提取并注入元数据 (来源 source, 页码 page, 用户 user_id)。
    - **收益**: 实现精确的引用溯源 ("参见 Resume.pdf 第 5 页")。
    - **收益**: 是数据隔离安全层的基石。
"""
import os
import shutil
from typing import List, Optional
from langchain_community.document_loaders import (
    TextLoader,
    JSONLoader,
    CSVLoader,
    Docx2txtLoader,
    PDFPlumberLoader
)
# from langchain_community.document_loaders.pdf import PyPDFLoader
from langchain_community.document_loaders.markdown import UnstructuredMarkdownLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from fastapi import UploadFile

# 自定义 OCR Loader (避免依赖 LangChain 版本问题)
class CustomRapidOCRPDFLoader:
    def __init__(self, file_path: str):
        self.file_path = file_path

    def load(self) -> List[Document]:
        try:
            from rapidocr_pdf import RapidOCRPDF
        except ImportError:
            raise ImportError("rapidocr-pdf is not installed. Please install it with `pip install rapidocr-pdf`.")

        loader = RapidOCRPDF()
        texts = loader(self.file_path)
        
        docs = []
        if not texts:
            return []
            
        for page_data in texts:
            # page_data format: [page_num, text, confidence]
            if isinstance(page_data, list) and len(page_data) >= 2:
                content = page_data[1]
                page_num = page_data[0]
            else:
                continue
                
            if content and content.strip():
                docs.append(Document(
                    page_content=content,
                    metadata={"source": self.file_path, "page": page_num}
                ))
        return docs

class DocumentProcessor:
    """
    文档处理核心类 (优化版)
    移除 heavy dependencies (unstructured), 使用更轻量的方案
    """
    
    @staticmethod
    async def save_upload_file(upload_file: UploadFile, destination: str) -> str:
        """保存上传的文件到临时目录"""
        try:
            with open(destination, "wb") as buffer:
                shutil.copyfileobj(upload_file.file, buffer)
            return destination
        finally:
            upload_file.file.close()

    @staticmethod
    def load_file(file_path: str) -> List[Document]:
        """加载单个文件"""
        ext = os.path.splitext(file_path)[-1].lower()
        print(f"[DocProcessor] Loading file: {file_path} (Type: {ext})")
        
        try:
            loader = None
            if ext == ".txt" or ext == ".md":
                loader = TextLoader(file_path, encoding="utf-8")
            elif ext == ".pdf":
                # 优先尝试 PDFPlumberLoader (表格/排版更好)
                loader = PDFPlumberLoader(file_path)
            elif ext == ".json":
                # 改用 TextLoader 读取 JSON，确保所有内容都被当作文本处理
                # JSONLoader 需要 jq schema，比较麻烦且容易漏字段
                loader = TextLoader(file_path, encoding="utf-8")
            elif ext == ".csv":
                loader = CSVLoader(file_path)
            elif ext == ".docx":
                loader = Docx2txtLoader(file_path)
            else:
                # 不支持的格式
                print(f"[DocProcessor] Unsupported file type: {ext}")
                raise ValueError(f"Unsupported file type: {ext}")
                
            docs = loader.load()
            print(f"[DocProcessor] Loaded {docs} non-empty documents.]")
            print(f"[DocProcessor] Loaded {len(docs)} raw documents.")
            
            # 检查空内容
            non_empty_docs = [d for d in docs if d.page_content and d.page_content.strip()]
            print(f"[DocProcessor] Found {non_empty_docs} non-empty documents.")
            
            # 如果 PDFPlumber 提取为空，尝试 OCR
            if not non_empty_docs and ext == ".pdf":
                print(f"[DocProcessor] Warning: Standard PDF extraction failed. Attempting OCR...")
                try:
                    # 使用自定义 OCR Loader
                    ocr_loader = CustomRapidOCRPDFLoader(file_path)
                    docs = ocr_loader.load()
                    print(f"[DocProcessor] OCR loaded {len(docs)} documents.")
                    non_empty_docs = [d for d in docs if d.page_content and d.page_content.strip()]
                except ImportError as e:
                    print(f"[DocProcessor] OCR failed: {e}")
                    raise ValueError("Scanned PDF detected but OCR dependencies missing. Please install rapidocr-pdf.")
                except Exception as e:
                    print(f"[DocProcessor] OCR processing error: {e}")
                    # 不抛出异常，继续下面的空检查，统一报错
                    pass
            
            if not non_empty_docs:
                print(f"[DocProcessor] Warning: Loader returned empty content for {file_path}")
                if ext == ".pdf":
                    raise ValueError("PDF content is empty even after OCR. The file might be corrupted or the image quality is too low.")
                return []
            
            return non_empty_docs
            
        except Exception as e:
            print(f"[DocProcessor] Error loading file {file_path}: {e}")
            # 重新抛出异常，以便上层捕获并知道具体原因
            raise e

    @staticmethod
    def split_docs(docs: List[Document], chunk_size=1000, chunk_overlap=100) -> List[Document]:
        """文本切分"""
        print(f"[DocProcessor] Splitting {len(docs)} docs...")
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "。", "！", "？", " ", ""]
        )
        chunks = text_splitter.split_documents(docs)
        
        # 过滤掉空文档
        filtered_chunks = [
            doc for doc in chunks 
            if doc.page_content and isinstance(doc.page_content, str) and doc.page_content.strip()
        ]
        
        print(f"[DocProcessor] Created {len(filtered_chunks)} chunks (filtered from {len(chunks)}).")
        return filtered_chunks
