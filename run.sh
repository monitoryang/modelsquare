docker run -d --name modelsquare-triton --gpus all \
  -p 8003:8000 -p 8001:8001 -p 8002:8002 \
  -v /mnt/14TB/yangwen/code/AIcoder/ModelSquare/models:/models:rw \
  nvcr.io/nvidia/tritonserver:25.04-py3 \
  tritonserver --model-repository=/models \
  --model-control-mode=poll \
  --repository-poll-secs=5