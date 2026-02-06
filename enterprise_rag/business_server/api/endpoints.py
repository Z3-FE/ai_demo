from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import List, Optional
import httpx
import os
import json
import asyncio
import re

from db.database import get_db, SessionLocal
from db.models import ChatHistory, User
from api.auth import create_access_token, get_current_user, get_password_hash, verify_password, ACCESS_TOKEN_EXPIRE_MINUTES
from datetime import timedelta

router = APIRouter()

# AI Server 的地址
AI_SERVER_URL = os.getenv("AI_SERVER_URL", "http://localhost:8001")

# ==========================================
# Pydantic 模型
# ==========================================
class UserCreate(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: int
    username: str

class ChatRequest(BaseModel):
    session_id: str
    query: str
    # user_id 从 Token 获取，不再需要前端传

class UploadResponse(BaseModel):
    task_id: Optional[str] = None
    filename: str
    chunks_count: int
    status: str
    message: str

# ==========================================
# 认证接口 (Auth)
# ==========================================

@router.post("/auth/register", response_model=Token)
def register(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed_password = get_password_hash(user.password)
    new_user = User(username=user.username, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # 注册成功直接登录
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": new_user.username}, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "user_id": new_user.id,
        "username": new_user.username
    }

@router.post("/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "user_id": user.id,
        "username": user.username
    }

# ==========================================
# 业务接口 (Chat & Upload)
# ==========================================

@router.get("/history", response_model=List[dict])
def get_history(
    session_id: Optional[str] = None,
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """
    获取当前用户的历史会话。
    - 如果提供了 session_id，则返回该会话的所有消息。
    - 如果没有提供 session_id，则返回所有历史记录 (Limit 1000)。
    """
    query = db.query(ChatHistory).filter(ChatHistory.user_id == current_user.id)
    
    if session_id:
        query = query.filter(ChatHistory.session_id == session_id)
        # 会话详情按时间正序
        histories = query.order_by(ChatHistory.created_at.asc()).all()
    else:
        # 所有记录按时间倒序 (Limit 1000)
        histories = query.order_by(ChatHistory.created_at.desc()).limit(1000).all()
    
    return [
        {
            "session_id": h.session_id,
            "role": h.role,
            "content": h.content,
            "sources": h.sources,
            "created_at": h.created_at
        }
        for h in histories
    ]

@router.delete("/history/{session_id}")
def delete_history(
    session_id: str,
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """删除指定会话的所有记录"""
    deleted_count = db.query(ChatHistory).filter(
        ChatHistory.session_id == session_id,
        ChatHistory.user_id == current_user.id
    ).delete(synchronize_session=False)
    
    db.commit()
    
    if deleted_count == 0:
        return {"message": "Session not found or already deleted", "count": 0}
        
    return {"message": "Session deleted successfully", "count": deleted_count}

@router.post("/upload", response_model=UploadResponse)
async def upload_proxy(
    file: UploadFile = File(...), 
    current_user: User = Depends(get_current_user)
):
    try:
        async with httpx.AsyncClient() as client:
            files = {'file': (file.filename, file.file, file.content_type)}
            data = {'user_id': str(current_user.id)} # 传递 user_id
            # 转发给 AI Server
            response = await client.post(f"{AI_SERVER_URL}/rag/upload", files=files, data=data, timeout=120.0)
            
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
                
            data = response.json()
            return UploadResponse(
                task_id=data.get('task_id'), # 透传 task_id
                filename=data['filename'],
                chunks_count=0,
                status=data['status'],
                message=data['message']
            )
    except Exception as e:
        print(f"Proxy Upload Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/upload/status/{task_id}")
async def get_upload_status(task_id: str):
    """查询解析任务状态 (透传)"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{AI_SERVER_URL}/rag/upload/status/{task_id}", timeout=10.0)
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/chat")
async def chat_endpoint(
    request: ChatRequest, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    流式对话接口 (SSE)
    """
    # 0. 获取最近的历史记录
    recent_history_objs = db.query(ChatHistory).filter(
        ChatHistory.session_id == request.session_id,
        ChatHistory.user_id == current_user.id
    ).order_by(ChatHistory.created_at.desc()).limit(10).all()
    
    history_payload = [
        {"role": h.role, "content": h.content} 
        for h in reversed(recent_history_objs)
    ]

    # 1. 保存用户提问
    user_msg = ChatHistory(
        user_id=current_user.id,
        session_id=request.session_id,
        role="user",
        content=request.query
    )
    db.add(user_msg)
    db.commit()

    # 2. 定义流式生成器
    async def event_generator():
        full_answer = ""
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST", 
                    f"{AI_SERVER_URL}/rag/stream_chat", 
                    json={
                        "query": request.query, 
                        "history": history_payload,
                        "user_id": str(current_user.id) # 传递 user_id
                    },
                    timeout=60.0
                ) as response:
                    async for chunk in response.aiter_text():
                        if chunk:
                            full_answer += chunk
                            yield f"data: {json.dumps({'content': chunk})}\n\n"
            
            # 3. 生成结束后，保存 AI 回答 (使用新的 SessionLocal)
            # Parse sources from full_answer
            sources_json = None
            clean_answer = full_answer
            
            # Regex to find [SOURCES_START]...[SOURCES_END]
            sources_pattern = r"\[SOURCES_START\](.*?)\[SOURCES_END\]"
            matches = re.findall(sources_pattern, full_answer, re.DOTALL)
            if matches:
                try:
                    # Use the last match if multiple (should be unique now)
                    sources_data = json.loads(matches[-1])
                    sources_json = json.dumps(sources_data)
                except:
                    pass
                # Remove ALL source blocks from content to be clean
                clean_answer = re.sub(sources_pattern, "", full_answer, flags=re.DOTALL)

            with SessionLocal() as session:
                ai_msg = ChatHistory(
                    user_id=current_user.id,
                    session_id=request.session_id,
                    role="assistant",
                    content=clean_answer,
                    sources=sources_json
                )
                session.add(ai_msg)
                session.commit()
            
        except Exception as e:
            print(f"Streaming Error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
