from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# ==========================================
# 数据库配置
# ==========================================
# 如果使用 MySQL，连接字符串格式如下：
# SQLALCHEMY_DATABASE_URL = "mysql+pymysql://user:password@host:port/database_name"
# 例如: "mysql+pymysql://root:123456@localhost:3306/enterprise_rag"

# 优先从环境变量读取 DATABASE_URL，如果没有则使用 SQLite 作为兜底
# 生产环境示例: DATABASE_URL="mysql+pymysql://root:password@localhost:3306/enterprise_rag"
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "sqlite:///./business.db"
)

# 创建数据库引擎
# connect_args={"check_same_thread": False} 仅用于 SQLite
connect_args = {"check_same_thread": False} if "sqlite" in SQLALCHEMY_DATABASE_URL else {}

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args=connect_args
)

# 创建会话工厂
# autocommit=False: 禁止自动提交，需要手动 commit，保证事务安全性
# autoflush=False: 禁止自动刷新，需要手动 flush
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建 ORM 基类，所有数据模型都继承自它
Base = declarative_base()

# ==========================================
# 依赖注入 (Dependency Injection)
# ==========================================
def get_db():
    """
    获取数据库会话的依赖函数。
    FastAPI 会在每个请求开始时调用此函数获取 db 会话，
    并在请求结束时自动关闭会话。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
