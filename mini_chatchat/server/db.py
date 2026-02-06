import os
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime

# 数据库配置
DB_PATH = "sqlite:///../chat_history.db"  # 数据库文件路径
engine = create_engine(DB_PATH, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class ChatMessageModel(Base):
    """
    聊天记录表模型
    """
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True)  # 会话 ID
    role = Column(String)  # user / assistant
    content = Column(Text)  # 消息内容
    created_at = Column(DateTime, default=datetime.utcnow)

def init_db():
    """初始化数据库表"""
    Base.metadata.create_all(bind=engine)

def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
