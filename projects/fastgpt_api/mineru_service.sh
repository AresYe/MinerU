#!/bin/bash

# ================================
# 配置区域 - 可根据需要修改
# ================================

# 指定具体python解释器路径
PYTHON_PATH="/home/smart/anaconda3/envs/mineru/bin/python3"
SCRIPT_PATH="$(dirname "$0")/main.py"
DEFAULT_OUTPUT_DIR="$(dirname "$0")/output"
DEFAULT_HOST="0.0.0.0"
DEFAULT_PORT="8888"
LOG_DIR="$(dirname "$0")/logs"
LOG_FILE="$LOG_DIR/mineru_service.log"

# 设置环境变量
export MinerU_OUTPUT_DIR="$DEFAULT_OUTPUT_DIR"
export PROCESSES_PER_GPU="1"
export MINERU_MODEL_SOURCE="local"

# 创建日志目录
mkdir -p "$LOG_DIR"

# 记录脚本启动日志
echo "[$(date)] ===执行脚本命令: $0 $*" >> "$LOG_FILE"

# 检查参数
if [ $# -eq 0 ]; then
    echo "用法: $0 [start|stop]"
    echo "[$(date)] 错误: 缺少参数" >> "$LOG_FILE"
    exit 1
fi

start_service() {
    echo "[$(date)] 开始启动服务" >> "$LOG_FILE"

    # 创建输出目录
    if [ ! -d "$MinerU_OUTPUT_DIR" ]; then
        mkdir -p "$MinerU_OUTPUT_DIR"
        echo "创建输出目录: $MinerU_OUTPUT_DIR"
        echo "[$(date)] 创建输出目录: $MinerU_OUTPUT_DIR" >> "$LOG_FILE"
    fi

    echo "启动服务..."
    echo "[$(date)] 启动服务" >> "$LOG_FILE"
    echo "主机: $DEFAULT_HOST"
    echo "端口: $DEFAULT_PORT"
    echo "输出目录: $MinerU_OUTPUT_DIR"

    echo "[$(date)] 主机: $DEFAULT_HOST" >> "$LOG_FILE"
    echo "[$(date)] 端口: $DEFAULT_PORT" >> "$LOG_FILE"
    echo "[$(date)] 输出目录: $MinerU_OUTPUT_DIR" >> "$LOG_FILE"

    # 启动服务并将输出重定向到日志文件
    echo "[$(date)] 启动FastAPI服务进程" >> "$LOG_FILE"

    # 生成带时间戳的日志文件名
    timestamp=$(date +"%Y%m%d_%H%M")
    FASTAPI_LOG_FILE="$LOG_DIR/fastapi_stdout_$timestamp.log"

    # 在后台启动服务
    nohup "$PYTHON_PATH" "$SCRIPT_PATH" > "$FASTAPI_LOG_FILE" 2>&1 &

    # 等待15秒后再检查服务启动是否完成
    sleep 15

    # 查找占用指定端口的进程PID
    USE_PID=$(lsof -ti :$DEFAULT_PORT)
    echo "$DEFAULT_PORT 端口正在使用的进程PID: $USE_PID"

    if [ -n "$USE_PID" ]; then
        echo "[$(date)] 启动FastAPI服务进程成功" >> "$LOG_FILE"
        echo "服务启动成功 (PID: $USE_PID)。请查看日志文件确认服务是否正常启动。"
        echo "[$(date)] 服务启动成功 (PID: $USE_PID), 日志文件: $FASTAPI_LOG_FILE" >> "$LOG_FILE"
    else
        echo "未找到监听端口 $DEFAULT_PORT 的进程，启动失败。"
        echo "[$(date)] 未找到监听端口 $DEFAULT_PORT 的进程，启动失败。" >> "$LOG_FILE"
        exit 1
    fi

    sleep 3
}

stop_service() {
    echo "[$(date)] 开始停止服务。" >> "$LOG_FILE"
    echo "停止服务..."

    # 直接通过端口号查找并终止进程
    # echo "[$(date)] 查找端口 $DEFAULT_PORT 上的进程。" >> "$LOG_FILE"

    # 查找占用指定端口的进程PID
    FOUND_PID=$(lsof -ti :$DEFAULT_PORT)
    # echo "正在使用的进程PID: $FOUND_PID"

    # 如果找到了PID，，则先发送SIGTERM信号，等待一段时间后再强制终止
    if [ -n "$FOUND_PID" ]; then
        echo "[$(date)] 尝试优雅终止进程 (PID: $FOUND_PID)。" >> "$LOG_FILE"

        kill -15 $FOUND_PID 2>/dev/null

        # 等待最多30秒让应用优雅关闭
        timeout=30
        while [ $timeout -gt 0 ] && kill -0 $FOUND_PID 2>/dev/null; do
            sleep 1
            timeout=$((timeout - 1))
        done

        # 如果进程仍然存在，则强制终止
        if kill -0 $FOUND_PID 2>/dev/null; then
            echo "[$(date)] 进程未在30秒内关闭，强制终止 (PID: $FOUND_PID)。" >> "$LOG_FILE"
            kill -9 $FOUND_PID 2>/dev/null
        else
            echo "[$(date)] 进程已优雅关闭 (PID: $FOUND_PID)。" >> "$LOG_FILE"
        fi

        echo "服务已停止。"
        echo "[$(date)] 服务已停止。" >> "$LOG_FILE"
    else
        echo "未找到监听端口 $DEFAULT_PORT 的进程。"
        echo "[$(date)] 未找到监听端口 $DEFAULT_PORT 的进程。" >> "$LOG_FILE"
    fi

    sleep 2

}


case "$1" in
    start)
        stop_service
        start_service
        ;;
    stop)
        stop_service
        ;;
    *)
        echo "错误: 无效参数 $1。请使用 start 或 stop"
        echo "[$(date)] 错误: 无效参数 $1" >> "$LOG_FILE"
        exit 1
        ;;
esac

echo "[$(date)] 脚本执行完成" >> "$LOG_FILE"