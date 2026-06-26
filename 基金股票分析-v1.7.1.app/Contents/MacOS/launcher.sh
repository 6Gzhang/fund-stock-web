#!/bin/bash
APP_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
BACKEND_DIR="$APP_DIR/Contents/Resources/backend"
WEBVIEW_BIN="$APP_DIR/Contents/MacOS/FundStockWebView"
PORT=8080
LOG_FILE="$HOME/Library/Logs/FundStockApp.log"
PID_FILE="$HOME/Library/Logs/FundStockApp_server.pid"
WEBVIEW_PID_FILE="$HOME/Library/Logs/FundStockApp_webview.pid"

mkdir -p "$HOME/Library/Logs"

echo "" >> "$LOG_FILE"
echo "=== 基金股票分析软件启动 $(date) ===" >> "$LOG_FILE"
echo "APP_DIR: $APP_DIR" >> "$LOG_FILE"

cleanup() {
    echo "清理进程..." >> "$LOG_FILE"
    if [ -f "$PID_FILE" ]; then
        SERVER_PID=$(cat "$PID_FILE")
        if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
            kill "$SERVER_PID" 2>/dev/null
            sleep 0.5
            kill -9 "$SERVER_PID" 2>/dev/null
        fi
        rm -f "$PID_FILE"
    fi
    # 清理所有 python3 main.py 进程
    pkill -f "python3.*main.py" 2>/dev/null
    sleep 0.3
}

trap cleanup EXIT

# 第一步：强力清理所有旧进程和占用端口的进程
echo "清理旧进程..." >> "$LOG_FILE"

# 清理旧的 Python 后端
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        kill "$OLD_PID" 2>/dev/null
        sleep 0.5
        kill -9 "$OLD_PID" 2>/dev/null
    fi
    rm -f "$PID_FILE"
fi

# 清理所有相关 python 进程
pkill -f "python3.*main.py" 2>/dev/null
pkill -f "FundStockApp.*python" 2>/dev/null
sleep 0.5

# 清理占用端口的进程
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    OLD_PIDS=$(lsof -Pi :$PORT -sTCP:LISTEN -t 2>/dev/null)
    if [ -n "$OLD_PIDS" ]; then
        echo "端口 $PORT 被占用，强制清理: $OLD_PIDS" >> "$LOG_FILE"
        kill -9 $OLD_PIDS 2>/dev/null
        sleep 1
    fi
fi

# 再确认一次端口
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "警告：端口 $PORT 仍被占用，尝试继续启动..." >> "$LOG_FILE"
fi

# 启动后端
cd "$BACKEND_DIR"
echo "启动后端服务..." >> "$LOG_FILE"
/usr/bin/python3 main.py >> "$LOG_FILE" 2>&1 &
SERVER_PID=$!
echo $SERVER_PID > "$PID_FILE"
echo "后端 PID: $SERVER_PID" >> "$LOG_FILE"

# 等待后端就绪（最多等 60 秒）
READY=0
for i in $(seq 1 120); do
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "后端进程已退出（等待 ${i} 次后）" >> "$LOG_FILE"
        break
    fi
    if curl -s --connect-timeout 1 "http://localhost:$PORT/api/version" > /dev/null 2>&1; then
        READY=1
        echo "后端就绪（等待 ${i} 次，约 $((i/2)) 秒）" >> "$LOG_FILE"
        break
    fi
    sleep 0.5
done

if [ "$READY" -ne 1 ]; then
    echo "后端启动失败" >> "$LOG_FILE"
    tail -20 "$LOG_FILE" >> "$LOG_FILE" 2>/dev/null
    osascript -e "display dialog \"后端服务启动失败！\n\n请查看日志文件：\n~/Library/Logs/FundStockApp.log\" buttons {\"确定\"} default button 1 with icon stop" 2>/dev/null
    exit 1
fi

# 启动 WebView
echo "启动 WebView..." >> "$LOG_FILE"
if [ -f "$WEBVIEW_BIN" ]; then
    "$WEBVIEW_BIN" &
    WEBVIEW_PID=$!
    echo $WEBVIEW_PID > "$WEBVIEW_PID_FILE"
    echo "WebView PID: $WEBVIEW_PID" >> "$LOG_FILE"
    
    # 2秒后确保窗口前置
    sleep 2
    osascript -e 'tell application "System Events" to set frontmost of every process whose unix id is '"$WEBVIEW_PID"' to true' 2>/dev/null
    
    wait $WEBVIEW_PID
    echo "WebView 退出" >> "$LOG_FILE"
else
    echo "WebView 二进制不存在，用浏览器打开" >> "$LOG_FILE"
    open "http://localhost:$PORT"
    if kill -0 "$SERVER_PID" 2>/dev/null; then
        wait $SERVER_PID
    fi
fi

exit 0
