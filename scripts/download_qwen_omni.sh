#!/bin/bash
# 下载 Qwen3-Omni-30B-A3B-Instruct 模型到本地

set -e

MODEL_DIR="/mnt/14TB/yangwen/code/AIcoder/ModelSquare/llm_models/Qwen3-Omni-30B-A3B-Instruct"

echo "开始下载 Qwen3-Omni-30B-A3B-Instruct 模型..."

# 检查目录是否存在
if [ -d "$MODEL_DIR" ]; then
    echo "模型目录已存在: $MODEL_DIR"
    read -p "是否覆盖下载? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "取消下载"
        exit 0
    fi
fi

# 创建目录
mkdir -p "$MODEL_DIR"

# 使用 Python + ModelScope SDK 下载
python3 << 'EOF'
from modelscope import snapshot_download

model_dir = snapshot_download(
    'Qwen/Qwen3-Omni-30B-A3B-Instruct',
    cache_dir='/mnt/14TB/yangwen/code/AIcoder/ModelSquare/llm_models',
    revision='master'
)

print(f"\n模型下载完成: {model_dir}")
EOF

echo "下载完成！"
ls -lh "$MODEL_DIR"
