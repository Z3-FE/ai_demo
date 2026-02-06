from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from db.database import engine, Base
from api import endpoints

# ==========================================
# 初始化数据库表
# ==========================================
# 在应用启动时，自动创建所有定义的表结构
# 生产环境中通常使用 Alembic 进行版本迁移，而不是直接 create_all
Base.metadata.create_all(bind=engine)

# 自动迁移：检查并添加 sources 列 (Dev Only Hack)
try:
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE chat_histories ADD COLUMN sources TEXT"))
        conn.commit()
        print("Migrated: Added 'sources' column to chat_histories.")
except Exception as e:
    # Column likely already exists
    pass

app = FastAPI(
    title="Enterprise RAG - Business Server",
    description="负责用户管理、鉴权和历史记录存储的业务后端",
    version="1.0.0"
)

# ==========================================
# 跨域配置 (CORS)
# ==========================================
# 允许前端 (React) 访问此后端
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 生产环境建议指定具体的域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 注册路由
# ==========================================
app.include_router(endpoints.router, prefix="/api")

@app.get("/")
def root():
    return {"message": "Business Server is running..."}

if __name__ == "__main__":
    import uvicorn
    # 启动服务，端口 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)
