from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class User(Base):
    """
    用户表
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, comment="用户名")
    # 真实项目中应该存储哈希后的密码，而不是明文
    hashed_password = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关联聊天记录
    chats = relationship("ChatHistory", back_populates="owner")

class ChatHistory(Base):
    """
    聊天记录表
    存储所有的问答对
    """
    __tablename__ = "chat_histories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    session_id = Column(String(50), index=True, comment="会话ID，用于区分不同的对话窗口")
    
    role = Column(String(20), comment="角色: user 或 assistant")
    content = Column(Text, comment="聊天内容")
    sources = Column(Text, nullable=True, comment="引用来源(JSON)")
    
    created_at = Column(DateTime, default=datetime.utcnow)

    # 反向关联
    owner = relationship("User", back_populates="chats")
