#!/bin/bash

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 获取脚本所在目录的绝对路径
PROJECT_ROOT=$(pwd)

# PID 文件路径
PID_FILE="$PROJECT_ROOT/.server_pids"

stop_services() {
    if [ -f "$PID_FILE" ]; then
        echo -e "${RED}Stopping existing services...${NC}"
        # 读取并杀死进程
        while read -r pid; do
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid"
                echo "Killed PID: $pid"
            fi
        done < "$PID_FILE"
        rm "$PID_FILE"
        echo -e "${GREEN}Services stopped.${NC}"
        # 给一点时间让端口释放
        sleep 2
    else
        echo "No running services found."
    fi
}

start_services() {
    echo -e "${BLUE}=== Starting Enterprise RAG System ===${NC}"
    
    # 1. 启动 AI Server
    echo -e "${GREEN}[1/3] Starting AI Server (Port 8001)...${NC}"
    cd "$PROJECT_ROOT/ai_server"
    mkdir -p logs
    nohup uv run main.py > logs/ai_server.log 2>&1 &
    AI_PID=$!
    echo "$AI_PID" >> "$PID_FILE"
    echo "AI Server PID: $AI_PID"

    # 2. 启动 Business Server
    echo -e "${GREEN}[2/3] Starting Business Server (Port 8000)...${NC}"
    cd "$PROJECT_ROOT/business_server"
    mkdir -p logs
    nohup uv run main.py > logs/business_server.log 2>&1 &
    BIZ_PID=$!
    echo "$BIZ_PID" >> "$PID_FILE"
    echo "Business Server PID: $BIZ_PID"

    # 3. 启动 Frontend
    echo -e "${GREEN}[3/3] Starting Frontend (Port 5173)...${NC}"
    cd "$PROJECT_ROOT/frontend"
    nohup npm run dev > ../frontend_server.log 2>&1 &
    FRONT_PID=$!
    echo "$FRONT_PID" >> "$PID_FILE"
    echo "Frontend PID: $FRONT_PID"

    echo -e "${BLUE}=== All Services Started ===${NC}"
    echo -e "Frontend:  http://localhost:5173"
    echo -e "Business:  http://localhost:8000/docs"
    echo -e "AI Server: http://localhost:8001/docs"
    echo -e "${BLUE}============================${NC}"
    echo "Logs are being written to ai_server/logs, business_server/logs and frontend_server.log"
}

# 命令行参数处理
case "$1" in
    start)
        start_services
        echo "Press Ctrl+C to stop all services..."
        trap "stop_services; exit" INT
        wait
        ;;
    stop)
        stop_services
        ;;
    restart)
        stop_services
        start_services
        echo "Press Ctrl+C to stop all services..."
        trap "stop_services; exit" INT
        wait
        ;;
    *)
        echo "Usage: $0 {start|stop|restart}"
        # 默认行为：如果是直接运行不带参数，则执行 start 逻辑
        start_services
        echo "Press Ctrl+C to stop all services..."
        trap "stop_services; exit" INT
        wait
        ;;
esac
