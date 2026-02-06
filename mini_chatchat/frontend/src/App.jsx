import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Send, Upload, FileText, Loader2, Bot, User } from 'lucide-react';

const API_BASE_URL = 'http://localhost:8000';

// 生成简单的随机 Session ID
const generateSessionId = () => {
  return 'sess_' + Math.random().toString(36).substring(2, 15);
};

function App() {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: '你好！我是 Mini-Chatchat。请上传文档，然后问我关于文档的问题。' }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState(null);
  const [sessionId, setSessionId] = useState('');

  // 初始化 Session ID
  useEffect(() => {
    let sid = localStorage.getItem('chat_session_id');
    if (!sid) {
      sid = generateSessionId();
      localStorage.setItem('chat_session_id', sid);
    }
    setSessionId(sid);
    console.log('Current Session ID:', sid);
  }, []);

  const handleUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setUploading(true);
    setUploadStatus(null);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await axios.post(`${API_BASE_URL}/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      if (res.data.status === 'success') {
        setUploadStatus({ type: 'success', msg: `上传成功！已切分 ${res.data.chunks_count} 个片段。` });
      } else {
        setUploadStatus({ type: 'warning', msg: res.data.message });
      }
    } catch (err) {
      setUploadStatus({ type: 'error', msg: '上传失败: ' + (err.response?.data?.detail || err.message) });
    } finally {
      setUploading(false);
    }
  };

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMsg = { role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      // 这里的 history 不再需要传递，后端会自动管理
      // const history = messages.filter(m => m.role !== 'system').slice(-6);
      
      const res = await axios.post(`${API_BASE_URL}/chat`, {
        query: userMsg.content,
        session_id: sessionId // 传递 Session ID
      });

      const aiMsg = { role: 'assistant', content: res.data.answer };
      setMessages(prev => [...prev, aiMsg]);
    } catch (err) {
      const errMsg = { role: 'assistant', content: '❌ 请求出错: ' + (err.response?.data?.detail || err.message) };
      setMessages(prev => [...prev, errMsg]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-screen bg-gray-100">
      {/* Sidebar */}
      <div className="w-80 bg-white border-r border-gray-200 p-6 flex flex-col">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
            <Bot className="text-white w-6 h-6" />
          </div>
          <h1 className="text-xl font-bold text-gray-800">Mini Chatchat</h1>
        </div>

        <div className="flex-1">
          <label className="block mb-4">
            <span className="text-sm font-medium text-gray-700 mb-2 block">上传知识库文档</span>
            <div className={`
              border-2 border-dashed rounded-xl p-6 flex flex-col items-center justify-center text-center cursor-pointer transition-colors
              ${uploading ? 'bg-gray-50 border-gray-300' : 'hover:bg-blue-50 hover:border-blue-400 border-gray-300'}
            `}>
              <input type="file" className="hidden" onChange={handleUpload} disabled={uploading} accept=".pdf,.txt,.md,.csv,.json" />
              {uploading ? (
                <Loader2 className="w-8 h-8 text-blue-500 animate-spin mb-2" />
              ) : (
                <Upload className="w-8 h-8 text-gray-400 mb-2" />
              )}
              <span className="text-sm text-gray-500">
                {uploading ? '正在处理...' : '点击上传 PDF/TXT'}
              </span>
            </div>
          </label>

          {uploadStatus && (
            <div className={`p-3 rounded-lg text-sm ${
              uploadStatus.type === 'success' ? 'bg-green-50 text-green-700' :
              uploadStatus.type === 'warning' ? 'bg-yellow-50 text-yellow-700' :
              'bg-red-50 text-red-700'
            }`}>
              {uploadStatus.msg}
            </div>
          )}
        </div>

        <div className="text-xs text-gray-400 mt-auto text-center">
          Powered by LangChain & React
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {messages.map((msg, idx) => (
            <div key={idx} className={`flex gap-4 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
              <div className={`
                w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0
                ${msg.role === 'assistant' ? 'bg-blue-100' : 'bg-gray-200'}
              `}>
                {msg.role === 'assistant' ? <Bot className="w-6 h-6 text-blue-600" /> : <User className="w-6 h-6 text-gray-600" />}
              </div>
              <div className={`
                max-w-[80%] p-4 rounded-2xl text-sm leading-relaxed shadow-sm
                ${msg.role === 'assistant' ? 'bg-white text-gray-800 rounded-tl-none' : 'bg-blue-600 text-white rounded-tr-none'}
              `}>
                {msg.content}
              </div>
            </div>
          ))}
          {loading && (
             <div className="flex gap-4">
               <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center flex-shrink-0">
                 <Bot className="w-6 h-6 text-blue-600" />
               </div>
               <div className="bg-white p-4 rounded-2xl rounded-tl-none shadow-sm flex items-center">
                 <div className="flex space-x-1">
                   <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                   <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                   <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                 </div>
               </div>
             </div>
          )}
        </div>

        {/* Input Area */}
        <div className="p-6 bg-white border-t border-gray-200">
          <div className="max-w-4xl mx-auto relative">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              placeholder="输入你的问题..."
              disabled={loading}
              className="w-full pl-6 pr-14 py-4 bg-gray-100 rounded-full focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition-all shadow-inner"
            />
            <button
              onClick={handleSend}
              disabled={loading || !input.trim()}
              className="absolute right-2 top-2 p-2 bg-blue-600 text-white rounded-full hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <Send className="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
