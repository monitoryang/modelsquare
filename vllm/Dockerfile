# 1. 基于官方 vLLM OpenAI 兼容镜像
#    该镜像版本 v0.8.5 默认不包含 ModelScope SDK，
#    仅提供 vLLM 核心及 Hugging Face 相关依赖。
# 确认与 Docker Hub 标签一致 :contentReference[oaicite:4]{index=4}

FROM vllm/vllm-openai:v0.13.0
# 2. 安装 ModelScope SDK
#    通过 PyPI 安装最新版本的 modelscope，
#    以支持从 ModelScope 平台拉取与管理模型。
 # 安装 ModelScope 包 :contentReference[oaicite:5]{index=5}
RUN pip install --no-cache-dir modelscope -i https://pypi.tuna.tsinghua.edu.cn/simple

# 3. （可选）安装其他可选依赖
#    如果你还需要使用 vLLM 的音频等可选功能，可按需解注释以下行：
# RUN pip install --no-cache-dir "vllm[audio]==0.8.5"  # 参考官方文档说明 :contentReference[oaicite:6]{index=6}

# 4. 设置环境变量
#    指示 vLLM 在启动时优先从 ModelScope 获取模型，而非仅仅依赖 Hugging Face。
# 启用 ModelScope 支持 :contentReference[oaicite:7]{index=7}
ENV VLLM_USE_MODELSCOPE=True  


# 5. （可选）配置 ModelScope 认证
#    如果访问私有模型，需要将 SDK Token 注入容器环境：
# ENV MODELSCOPE_SDK_TOKEN=<your_modelscope_token>  # 详见 ModelScope 文档 :contentReference[oaicite:8]{index=8}

# 6. 容器启动入口保持与官方一致
#    不要更改 ENTRYPOINT 或 CMD，以保证兼容 vLLM 的 CLI 接口。
#    启动后可通过 --model 参数指定 ModelScope 上的模型 ID（例如 Qwen/Qwen2.5-7B-Instruct）。

