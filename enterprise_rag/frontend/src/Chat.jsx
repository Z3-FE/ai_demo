import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { Send, Upload, Bot, User, Plus, MessageSquare, LogOut, Loader2, FileText, Trash2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { fetchEventSource } from '@microsoft/fetch-event-source';

const API_BASE_URL = '/api'; // Use proxy path

function Chat() {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [historyList, setHistoryList] = useState([]);
  const [sessionId, setSessionId] = useState('');
  const messagesEndRef = useRef(null);

  // 解析引用源的辅助函数
  const parseSources = (content) => {
    // 使用全局匹配标志 'g' 来移除所有重复的 sources 块
    const sourceRegexGlobal = /\[SOURCES_START\](.*?)\[SOURCES_END\]/gs;
    const sourceRegex = /\[SOURCES_START\](.*?)\[SOURCES_END\]/s;
    
    // 提取第一个有效的 sources (假设它们都是一样的)
    const match = content.match(sourceRegex);
    if (match) {
      try {
        const sources = JSON.parse(match[1]).sources;
        // 移除所有匹配项
        const cleanContent = content.replace(sourceRegexGlobal, '');
        return { cleanContent, sources };
      } catch (e) {
        console.error("Failed to parse sources", e);
      }
    }
    return { cleanContent: content, sources: null };
  };

  // 初始化：检查登录状态 & 生成 Session ID
  useEffect(() => {
    const token = localStorage.getItem('token');
    const userData = localStorage.getItem('user');
    
    if (!token || !userData) {
      navigate('/login');
      return;
    }
    
    setUser(JSON.parse(userData));
    loadHistory().then(() => {
        // 如果没有历史记录，创建一个新的
        startNewChat();
    });
  }, []);

  // 滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const startNewChat = () => {
    const newSid = 'sess_' + Math.random().toString(36).substring(2, 15);
    setSessionId(newSid);
    setMessages([{ role: 'assistant', content: '你好！我是你的企业级 AI 助手。请上传文档，或者直接问我问题。' }]);
    // 强制刷新历史列表（虽然还没保存，但为了清空选中状态）
    // setHistoryList 保持不变，只是 sessionId 变了
  };

  const switchSession = async (sid) => {
      if (sid === sessionId) return;
      
      try {
        setLoading(true);
        const token = localStorage.getItem('token');
        // 使用新的 API 获取指定会话详情
        const res = await axios.get(`${API_BASE_URL}/history?session_id=${sid}`, {
            headers: { Authorization: `Bearer ${token}` }
        });
        
        const formattedMsgs = res.data.map(msg => {
            let content = msg.content;
            let sources = null;
            
            // 1. 尝试使用后端返回的独立 sources 字段 (新数据)
            if (msg.sources) {
                try {
                    // 后端存的是 JSON 字符串 '{"sources": [...]}'
                    const parsed = JSON.parse(msg.sources);
                    sources = parsed.sources || parsed; 
                } catch(e) {
                    console.error("Failed to parse msg.sources", e);
                }
            }
            
            // 2. 尝试从 content 中解析 (旧数据兼容)
            // 如果 sources 还没找到，或者 content 里可能还残留有标记
            const parsedContent = parseSources(content);
            if (parsedContent.sources) {
                content = parsedContent.cleanContent;
                // 如果后端没给 sources，就用从 content 解析出来的
                if (!sources) {
                    sources = parsedContent.sources;
                }
            }
            
            return {
                role: msg.role,
                content: content,
                sources: sources
            };
        });
        
        setSessionId(sid);
        setMessages(formattedMsgs.length > 0 ? formattedMsgs : [{ role: 'assistant', content: '你好！这是之前的会话记录。' }]);
      } catch (err) {
        console.error('Switch session failed:', err);
      } finally {
        setLoading(false);
      }
  };

  const deleteSession = async (sid, e) => {
      e.stopPropagation(); // 阻止冒泡，避免触发切换
      if (!window.confirm('Are you sure you want to delete this chat?')) return;
      
      try {
          const token = localStorage.getItem('token');
          await axios.delete(`${API_BASE_URL}/history/${sid}`, {
              headers: { Authorization: `Bearer ${token}` }
          });
          
          // 前端移除
          setHistoryList(prev => prev.filter(item => item.session_id !== sid));
          
          // 如果删除的是当前会话，则开启新会话
          if (sid === sessionId) {
              startNewChat();
          }
      } catch (err) {
          console.error('Delete session failed:', err);
          alert('Failed to delete session');
      }
  };

  const loadHistory = async () => {
    try {
      const token = localStorage.getItem('token');
      // 获取所有历史记录 (Limit 1000)
      const res = await axios.get(`${API_BASE_URL}/history`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      // 前端分组处理
      const sessions = {};
      const sessionOrder = []; // 保持时间顺序
      
      res.data.forEach(item => {
        if (!sessions[item.session_id]) {
            sessions[item.session_id] = [];
            sessionOrder.push(item.session_id);
        }
        sessions[item.session_id].unshift(item); // 假设后端是倒序返回的，unshift 恢复正序
      });

      // 生成侧边栏列表 (取每个会话的第一条用户消息作为标题，或者直接用 session_id)
      const list = sessionOrder.map(sid => {
          const msgs = sessions[sid];
          const firstUserMsg = msgs.find(m => m.role === 'user');
          return {
              session_id: sid,
              title: firstUserMsg ? firstUserMsg.content.slice(0, 30) : 'New Chat',
              created_at: msgs[0]?.created_at
          };
      });
      
      setHistoryList(list);
    } catch (err) {
      console.error('Load history failed:', err);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    navigate('/login');
  };

  const handleUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);
    const token = localStorage.getItem('token');

    try {
      // 1. 发起上传
      const res = await axios.post(`${API_BASE_URL}/upload`, formData, {
        headers: { 
          'Content-Type': 'multipart/form-data',
          'Authorization': `Bearer ${token}`
        }
      });
      
      const taskId = res.data.task_id;
      
      // 添加一条初始状态消息
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: `📤 文件 **${res.data.filename}** 已上传，正在后台解析中...` 
      }]);

      // 2. 开始轮询状态
      const pollInterval = setInterval(async () => {
        try {
            const statusRes = await axios.get(`${API_BASE_URL}/upload/status/${taskId}`, {
                headers: { Authorization: `Bearer ${token}` }
            });
            
            const { status, message } = statusRes.data;
            
            if (status === 'success') {
                clearInterval(pollInterval);
                setMessages(prev => [...prev, { 
                    role: 'assistant', 
                    content: `✅ 解析完成！\n文件 **${res.data.filename}** 已存入知识库，您可以开始提问了。` 
                }]);
                setUploading(false);
            } else if (status === 'failed') {
                clearInterval(pollInterval);
                setMessages(prev => [...prev, { 
                    role: 'assistant', 
                    content: `❌ 解析失败: ${message}` 
                }]);
                setUploading(false);
            } else {
                // 更新进度提示 (可选，避免刷屏)
                console.log(`Parsing status: ${status} - ${message}`);
            }
        } catch (err) {
            console.error("Poll error:", err);
            clearInterval(pollInterval);
            setUploading(false);
        }
      }, 2000); // 每2秒轮询一次

    } catch (err) {
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: `❌ 上传失败: ${err.response?.data?.detail || err.message}` 
      }]);
      setUploading(false);
    }
  };

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMsg = { role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    const token = localStorage.getItem('token');
    // let aiContent = ''; // 移除未使用的变量
    let rawContentBuffer = ''; // 用于累积原始内容，以便提取 sources

    // 添加一个空的 AI 消息占位
    setMessages(prev => [...prev, { role: 'assistant', content: '', sources: null }]);

    try {
      // 使用 fetchEventSource 处理 SSE
      await fetchEventSource(`${API_BASE_URL}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          query: userMsg.content,
          session_id: sessionId
        }),
        onmessage(msg) {
          if (msg.data === '[DONE]') {
            return;
          }
          try {
            const data = JSON.parse(msg.data);
            if (data.content) {
              rawContentBuffer += data.content;
              const { cleanContent, sources } = parseSources(rawContentBuffer);
              
              setMessages(prev => {
                const newMsgs = [...prev];
                // 如果解析出了 sources，更新 sources 字段，内容只显示 cleanContent
                // 如果还没有 sources，说明还在接收或者没有引用，暂时显示 rawContentBuffer (或者根据需要处理)
                // 实际上，SOURCES 标记通常在最前面或最后面。
                // 我们的后端是在最前面 yield [SOURCES_START]...
                
                // 优化：实时更新
                newMsgs[newMsgs.length - 1] = { 
                    role: 'assistant', 
                    content: cleanContent, // 只显示正文
                    sources: sources || newMsgs[newMsgs.length - 1].sources 
                };
                return newMsgs;
              });
            } else if (data.error) {
               // Error handling
            }
          } catch (e) {
            console.error('Parse SSE error:', e);
          }
        },
        onerror(err) {
            console.error("SSE Error:", err);
            throw err; 
        }
      });
      
      // 发送完成后刷新历史列表
      loadHistory();
      
    } catch (err) {
      setMessages(prev => {
        const newMsgs = [...prev];
        newMsgs[newMsgs.length - 1] = { role: 'assistant', content: rawContentBuffer + `\n❌ 网络错误: ${err.message}` };
        return newMsgs;
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-screen bg-gray-900 text-gray-100 font-sans">
      {/* ... (Sidebar omitted for brevity) ... */}
      <div className="w-[260px] bg-black flex flex-col border-r border-gray-800 hidden md:flex">
         {/* Sidebar content same as before */}
        <div className="p-3">
          <button 
            onClick={startNewChat}
            className="w-full flex items-center gap-3 px-3 py-3 rounded-md border border-gray-700 hover:bg-gray-900 transition-colors text-sm text-white"
          >
            <Plus className="w-4 h-4" />
            New chat
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-2">
          <div className="text-xs font-medium text-gray-500 mb-2 px-2">History</div>
          {historyList.map((item, idx) => (
            <div 
              key={idx}
              onClick={() => switchSession(item.session_id)}
              className={`w-full flex items-center gap-3 px-3 py-3 rounded-md transition-colors text-sm truncate text-left group cursor-pointer ${
                item.session_id === sessionId ? 'bg-gray-800 text-white' : 'hover:bg-gray-900 text-gray-300'
              }`}
            >
              <MessageSquare className="w-4 h-4 text-gray-500 group-hover:text-white flex-shrink-0" />
              <span className="truncate flex-1">{item.title || 'New Chat'}</span>
              <button 
                onClick={(e) => deleteSession(item.session_id, e)}
                className="opacity-0 group-hover:opacity-100 p-1 hover:bg-red-500/20 rounded text-gray-500 hover:text-red-400 transition-all"
                title="Delete chat"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>

        <div className="p-3 border-t border-gray-800">
          <div className="flex items-center gap-3 px-3 py-3 rounded-md hover:bg-gray-900 cursor-pointer transition-colors">
            <div className="w-8 h-8 bg-green-600 rounded-sm flex items-center justify-center text-sm font-bold">
              {user?.username?.[0]?.toUpperCase()}
            </div>
            <div className="flex-1 text-sm font-medium truncate">
              {user?.username}
            </div>
            <button onClick={handleLogout} className="text-gray-500 hover:text-white">
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Main Area */}
      <div className="flex-1 flex flex-col bg-gray-800 relative">
        {/* Mobile Header */}
        <div className="md:hidden h-12 bg-gray-900 border-b border-gray-700 flex items-center justify-center text-sm font-medium">
          Enterprise RAG
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto scroll-smooth">
          <div className="flex flex-col items-center pb-32 pt-10">
            {messages.map((msg, idx) => (
              <div 
                key={idx} 
                className={`w-full px-4 py-8 border-b border-black/10 dark:border-gray-900/50 ${
                  msg.role === 'assistant' ? 'bg-gray-800' : 'bg-gray-800'
                }`}
              >
                <div className="max-w-3xl mx-auto flex gap-4 md:gap-6">
                  <div className="flex-shrink-0 flex flex-col relative items-end">
                    <div className={`w-8 h-8 rounded-sm flex items-center justify-center ${
                      msg.role === 'assistant' ? 'bg-green-500' : 'bg-gray-600'
                    }`}>
                      {msg.role === 'assistant' ? <Bot className="w-5 h-5 text-white" /> : <User className="w-5 h-5 text-white" />}
                    </div>
                  </div>
                  <div className="relative flex-1 overflow-hidden">
                    <div className="prose prose-invert prose-p:leading-relaxed prose-pre:bg-black/50 max-w-none">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {msg.content}
                      </ReactMarkdown>
                    </div>
                    {/* 显示引用来源 */}
                    {msg.sources && msg.sources.length > 0 && (
                        <div className="mt-4 pt-3 border-t border-gray-700">
                            <div className="text-xs text-gray-400 font-semibold mb-2 flex items-center gap-1">
                                <FileText className="w-3 h-3" /> Sources:
                            </div>
                            <div className="flex flex-wrap gap-2">
                                {msg.sources.map((src, i) => (
                                    <span key={i} className="inline-flex items-center gap-1 px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs text-blue-300 cursor-pointer transition-colors" title={`Page ${src.page}`}>
                                        {src.source} <span className="text-gray-500">p.{src.page}</span>
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input Area */}
        <div className="absolute bottom-0 left-0 w-full bg-gradient-to-t from-gray-800 via-gray-800 to-transparent pt-10 pb-6 px-4">
          <div className="max-w-3xl mx-auto">
             {/* Upload Status/Button */}
             <div className="mb-2 flex items-center gap-2">
                <label className="cursor-pointer flex items-center gap-2 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded-md text-xs text-gray-300 transition-colors border border-gray-600">
                  {uploading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Upload className="w-3 h-3" />}
                  {uploading ? 'Processing...' : 'Upload Document'}
                  <input type="file" className="hidden" onChange={handleUpload} disabled={uploading} accept=".pdf,.txt,.md,.csv,.json,.docx" />
                </label>
             </div>

            <div className="relative flex items-end w-full p-3 bg-[#40414F] rounded-xl border border-black/10 dark:border-gray-900/50 shadow-md overflow-hidden ring-offset-2 focus-within:ring-2 ring-blue-500/50">
              <textarea
                className="w-full max-h-[200px] py-[10px] pr-10 md:py-3 md:pr-12 bg-transparent border-none text-white placeholder-gray-400 focus:ring-0 resize-none outline-none overflow-y-auto m-0"
                rows={1}
                placeholder="Send a message..."
                value={input}
                onChange={(e) => {
                  setInput(e.target.value);
                  e.target.style.height = 'auto';
                  e.target.style.height = `${e.target.scrollHeight}px`;
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
              />
              <button
                onClick={handleSend}
                disabled={loading || !input.trim()}
                className="absolute right-3 bottom-3 p-1 rounded-md text-gray-400 hover:bg-black/50 disabled:hover:bg-transparent disabled:opacity-40 transition-colors"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
            <div className="text-center text-xs text-gray-500 mt-2">
              Enterprise RAG can make mistakes. Consider checking important information.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Chat;
