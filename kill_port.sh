#!/bin/bash

if [ $# -eq 0 ]; then
  read -p "请输入要清理的端口号: " PORT
else
  PORT=$1
fi

if ! [[ "$PORT" =~ ^[0-9]+$ ]]; then
  echo "错误：请输入有效的端口号（数字）"
  exit 1
fi

PORT_PIDS=$(lsof -i :29003 -t)

if [ -z "$PORT_PIDS" ]; then
  echo "未发现占用${PORT}端口的进程"
  exit 0
fi

for PID in $PORT_PIDS; do
  if ps -p $PID -o comm= | grep -q "python"; then
    PROCESS_NAME=$(ps -p $PID -o comm=)
    COMMAND=$(ps -p $PID -o args=)

    echo "找到占用29003端口的Python进程:"
    echo "  PID: $PID"
    echo "  程序: $PROCESS_NAME"
    echo "  命令: $COMMAND"

    echo "正在终止进程 $PID..."
    kill -9 $PID
  fi
done

if lsof -i :29003 > /dev/null; then
  echo "警告：${PORT}端口仍被占用，请检查其他非Python进程"
else
  echo "${PORT}端口已成功释放"
fi

echo "清理操作完成"