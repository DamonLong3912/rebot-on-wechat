#!/bin/bash
# 后台运行 Chat_on_webchat 执行脚本

cd `dirname $0`/..
export BASE_DIR=`pwd`
echo $BASE_DIR

# 检查 nohup.out 日志输出文件
if [ ! -f "${BASE_DIR}/nohup.out" ]; then
  touch "${BASE_DIR}/nohup.out"
  echo "create file ${BASE_DIR}/nohup.out"
fi

# 启动 Python 程序
nohup python3 "${BASE_DIR}/app.py" > "${BASE_DIR}/nohup.out" 2>&1 &

# 打印提示信息
echo "Chat_on_webchat is starting, you can check the ${BASE_DIR}/nohup.out"

# 在后台跟踪日志文件
#tail -f "${BASE_DIR}/nohup.out"