"""
    启动： streamlit run webui.py
"""

import streamlit as st
import requests
import os

# 后端 API 地址
API_BASE_URL = "http://localhost:8000"

st.set_page_config(page_title="Mini-Chatchat", page_icon="🤖", layout="wide")

st.title("🤖 Mini-Chatchat (RAG 演示版)")

# 初始化 Session State
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- 侧边栏：文件上传 ---
with st.sidebar:
    st.header("📚 知识库管理")
    uploaded_file = st.file_uploader("上传文档 (PDF/TXT/MD)", type=["txt", "pdf", "md", "csv", "json"])
    
    if uploaded_file is not None:
        if st.button("开始向量化"):
            with st.spinner("正在处理文档..."):
                try:
                    files = {"file": (uploaded_file.name, uploaded_file, uploaded_file.type)}
                    response = requests.post(f"{API_BASE_URL}/upload", files=files)
                    
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("status") == "success":
                            st.success(f"成功！已切分为 {data.get('chunks_count')} 个片段并存入向量库。")
                        else:
                            st.warning(f"警告: {data.get('message')}")
                    else:
                        st.error(f"上传失败: {response.text}")
                except Exception as e:
                    st.error(f"请求错误: {str(e)}")

    st.divider()
    st.markdown("### 使用说明")
    st.markdown("1. 在此处上传文档")
    st.markdown("2. 点击“开始向量化”")
    st.markdown("3. 在右侧对话框提问")

# --- 主界面：聊天窗口 ---
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 处理用户输入
if prompt := st.chat_input("请输入你的问题..."):
    # 1. 显示用户问题
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. 调用后端 API
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        
        try:
            with st.spinner("思考中..."):
                response = requests.post(
                    f"{API_BASE_URL}/chat",
                    json={"query": prompt, "history": st.session_state.messages[:-1]}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    full_response = data.get("answer", "No answer received.")
                    message_placeholder.markdown(full_response)
                else:
                    full_response = f"Error: {response.status_code} - {response.text}"
                    message_placeholder.error(full_response)
        except Exception as e:
            full_response = f"Connection Error: {str(e)}"
            message_placeholder.error(full_response)
            
    # 3. 保存 AI 回复
    st.session_state.messages.append({"role": "assistant", "content": full_response})
