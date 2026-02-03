#!/bin/bash
# Download Qwen3-VL-32B-Instruct model from ModelScope
# This script downloads the model to the llm_models directory for use with vLLM v0.13.0

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
MODEL_DIR="$PROJECT_ROOT/llm_models"
MODEL_NAME="Qwen3-VL-32B-Instruct"
MODEL_PATH="$MODEL_DIR/$MODEL_NAME"

echo "=========================================="
echo "Qwen3-VL Model Downloader"
echo "=========================================="
echo ""
echo "Model: $MODEL_NAME"
echo "Target directory: $MODEL_PATH"
echo ""

# Check if model already exists
if [ -d "$MODEL_PATH" ] && [ "$(ls -A $MODEL_PATH 2>/dev/null)" ]; then
    echo "Model directory already exists and is not empty."
    read -p "Do you want to re-download? (y/N): " confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        echo "Skipping download."
        exit 0
    fi
fi

# Create model directory
mkdir -p "$MODEL_PATH"

# Check if modelscope is installed
if ! python3 -c "import modelscope" 2>/dev/null; then
    echo "Installing modelscope..."
    pip install modelscope -U -i https://pypi.tuna.tsinghua.edu.cn/simple
fi

echo ""
echo "Downloading model from ModelScope..."
echo "This may take a while depending on your network speed."
echo ""

# Download using modelscope
python3 << EOF
from modelscope import snapshot_download

model_dir = snapshot_download(
    'Qwen/Qwen3-VL-32B-Instruct',
    cache_dir='$MODEL_DIR',
    local_dir='$MODEL_PATH',
)

print(f"Model downloaded to: {model_dir}")
EOF

echo ""
echo "=========================================="
echo "Download complete!"
echo "=========================================="
echo ""
echo "Model location: $MODEL_PATH"
echo ""
echo "To start the vLLM service, run:"
echo "  docker compose --profile vllm up -d"
echo ""
echo "Or to run vLLM manually (requires 2x GPU with tensor-parallel):"
echo "  docker run -d --name vllm --gpus all \\"
echo "    -v $MODEL_DIR:/models:ro \\"
echo "    -p 8100:8000 \\"
echo "    --ipc=host \\"
echo "    -e VLLM_USE_MODELSCOPE=True \\"
echo "    modelsquare-vllm:v0.13.0 \\"
echo "    /models/$MODEL_NAME \\"
echo "    --served-model-name qwen3-vl \\"
echo "    --tensor-parallel-size 2 \\"
echo "    --gpu-memory-utilization 0.85 \\"
echo "    --max-model-len 32768 \\"
echo "    --trust-remote-code \\"
echo "    --dtype bfloat16 \\"
echo "    --limit-mm-per-prompt '{\"image\": 4}'"
echo ""
