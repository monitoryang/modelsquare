# ModelSquare - 实时交互式模型广场平台

实时交互式 AI 模型推理与展示平台，支持模型上传、图像/视频推理、万物检测和实时流媒体处理。

## 功能特性

- **模型管理** - 上传、编辑、删除模型，支持 ONNX/TensorRT 格式
- **图片推理** - 上传图片进行目标检测，Canvas 实时渲染结果
- **视频推理** - 上传视频文件进行逐帧检测，生成带检测框的结果视频
- **万物检测** - 基于 VLM 的自然语言目标检测，支持中英文描述
- **实时推流** - RTMP 推流 + 实时检测，视频与检测框叠加渲染
- **GPU 监控** - 实时监控多卡 GPU 利用率、显存、温度
- **API Key 管理** - 创建和管理 API 访问密钥
- **用户权限** - 超级用户/普通用户权限分离

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 19 + TypeScript + Ant Design Pro + Vite |
| 后端 | FastAPI + SQLAlchemy + Pydantic |
| 数据库 | PostgreSQL 15 + Redis 7 |
| 存储 | MinIO (S3 兼容) |
| 推理 | NVIDIA Triton Inference Server |
| 流媒体 | SRS (RTMP/HLS/WebRTC) + FFmpeg |
| 容器化 | Docker + Docker Compose |

## 前置条件

- Docker >= 24.0
- Docker Compose >= 2.20
- Node.js >= 18 (本地开发)
- Python >= 3.11 (本地开发)
- NVIDIA GPU + CUDA (可选，用于 Triton 推理)

## 快速启动

### 1. 克隆项目并配置环境

项目提供了两套预设环境配置文件，根据使用场景选择：

| 配置文件 | 适用场景 | 访问地址 |
|----------|----------|----------|
| `.env.local` | 本地开发/测试 | `http://localhost:3010` |
| `.env.production` | 公网部署 | `http://182.150.116.35:3010` |

```bash
git clone git@github.com:Monitoryang/ModelSquare.git
cd ModelSquare

# 本地开发环境
cp .env.local .env

# 或公网生产环境（先修改 SECRET_KEY！）
cp .env.production .env
```

> **注意**：`VITE_API_URL` 等前端变量在 Docker **构建阶段**烧入静态文件，切换环境后必须重新构建前端镜像：
> ```bash
> docker compose build --no-cache web
> ```

### 2. 一键启动所有服务

```bash
# 启动所有服务（包括 GPU 推理和 vLLM VL 模型）
docker compose --profile gpu --profile vllm-vl up -d

# 查看服务状态
docker compose --profile gpu --profile vllm-vl ps
```

### 3. 分步启动（可选）

如果不需要 GPU 推理或 vLLM 服务，可以分步启动：

```bash
# 仅启动基础服务：PostgreSQL、Redis、MinIO、SRS、API、Web
docker compose up -d

# 额外启动 Triton GPU 推理服务
docker compose --profile gpu up -d

# 启动 Qwen3-VL-32B 模型（推荐，万物检测功能）
docker compose --profile gpu --profile vllm-vl up -d

# 启动 Qwen3-Omni-30B 模型（需要完整模型文件）
docker compose --profile gpu --profile vllm-omni up -d
```

**注意**：vllm-vl 和 vllm-omni 两个服务互斥，只能启动其中一个。

### 4. 本地开发模式

**后端开发**

```bash
cd backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt

# 启动开发服务器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8020
```

**前端开发**

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

## 服务访问地址

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端 | http://localhost:3010 (Docker) / http://localhost:5173 (开发) | Web 界面 |
| 后端 API | http://localhost:8020 | RESTful API |
| API 文档 | http://localhost:8020/docs | Swagger UI |
| MinIO 控制台 | http://localhost:9011 | 对象存储管理 |
| MinIO API | http://localhost:9010 | S3 兼容接口 |
| SRS 控制台 | http://localhost:1995 | 流媒体服务 |
| SRS HTTP | http://localhost:8090 | HLS/WebRTC |
| Triton gRPC | http://localhost:8021 | 推理服务 gRPC |
| Triton HTTP | http://localhost:8022 | 推理服务 HTTP |
| vLLM | http://localhost:8110 (vl) / 8111 (omni) | 大模型多模态推理 |

## 测试

### 后端测试

```bash
cd backend
source venv/bin/activate
pytest tests/ -v
```

### 前端测试

```bash
cd frontend
npm run test
```

## 项目结构

```
ModelSquare/
├── frontend/              # React 前端
│   ├── src/
│   │   ├── pages/         # 页面组件
│   │   ├── layouts/       # 布局组件
│   │   ├── services/      # API 服务
│   │   └── types/         # TypeScript 类型
│   └── package.json
├── backend/               # FastAPI 后端
│   ├── app/
│   │   ├── api/v1/        # API 路由
│   │   ├── core/          # 核心配置
│   │   ├── models/        # 数据库模型
│   │   └── schemas/       # Pydantic 模式
│   ├── tests/             # 测试用例
│   └── requirements.txt
├── docker/                # Docker 配置
│   ├── srs/               # SRS 流媒体配置
│   └── ffmpeg/            # FFmpeg Worker（帧提取服务）
├── docs/                  # 项目文档
├── llm_models/            # VLM 模型存储目录
├── models/                # Triton 模型仓库
├── docker-compose.yml     # Docker Compose 配置
└── .env.example           # 环境变量模板
```

## 常见问题

### 1. 数据库连接失败

```
sqlalchemy.exc.OperationalError: could not connect to server
```

**解决方案**：确保 PostgreSQL 容器正在运行

```bash
docker compose ps postgres
docker compose up -d postgres
```

### 2. Redis 连接失败

```
redis.exceptions.ConnectionError: Error connecting to Redis
```

**解决方案**：确保 Redis 容器正在运行

```bash
docker compose ps redis
docker compose up -d redis
```

### 3. 端口被占用

```
Error: listen EADDRINUSE :::8020
```

**解决方案**：检查并释放端口

```bash
# Linux/Mac
lsof -i :8020
kill -9 <PID>

# 或修改 docker-compose.yml 中的端口映射
```

### 4. Triton 启动失败（无 GPU）

如果没有 NVIDIA GPU，不要启动 Triton 服务：

```bash
# 仅启动基础服务，不包含 GPU profile
docker compose up -d
```

### 5. vLLM 启动失败或模型加载慢

vLLM 加载大模型需要较长时间（约 3-5 分钟），可查看日志确认状态：

```bash
# 查看 Qwen3-VL 启动日志
docker logs -f modelsquare-vllm

# 查看 Qwen3-Omni 启动日志
docker logs -f modelsquare-vllm-omni

# 检查 vLLM 健康状态
curl http://localhost:8110/health  # VL 模型
curl http://localhost:8111/health  # Omni 模型
```

**注意**：如果 Qwen3-Omni 模型文件不完整（vocab.json 等文件仅为 Git LFS 指针），需要重新下载完整模型：

```bash
cd llm_models/Qwen3-Omni-30B-A3B-Instruct
# 检查文件大小，vocab.json 应该大于 1MB
ls -lh vocab.json

# 如果文件很小（如 132 字节），需要重新下载
python ../../scripts/download_qwen_omni.sh
```

### 6. 前端 API 请求 CORS 错误

确保后端 `CORS_ORIGINS` 配置包含前端地址：

```env
CORS_ORIGINS=["http://localhost:5173","http://localhost:3010"]
```

### 7. 实时推流功能使用

实时推流检测功能需要启动 FFmpeg Worker 服务：

```bash
# 启动包含 workers 的完整服务
docker compose --profile gpu --profile vllm-vl --profile workers up -d

# 查看 FFmpeg Worker 日志
docker logs -f modelsquare-ffmpeg-worker
```

**推流步骤：**

1. 在模型详情页面点击"在线测试" -> "实时推流"
2. 创建推流会话，获取推流地址（如 `rtmp://localhost:1945/live/<session_id>`）
3. 使用 FFmpeg/OBS 开始推流：
   ```bash
   # 推送本地视频文件
   ffmpeg -re -i input.mp4 -c:v libx264 -f flv rtmp://localhost:1945/live/<session_id>
   
   # 推送摄像头
   ffmpeg -f v4l2 -i /dev/video0 -c:v libx264 -f flv rtmp://localhost:1945/live/<session_id>
   ```
4. 点击"开始推理"激活实时检测
5. 页面会显示视频播放和检测框叠加

**注意：** 视频播放通过 flv.js 实现，检测框基于服务端推理结果实时更新。

## 开发命令

```bash
# 查看所有服务日志
docker compose --profile gpu --profile vllm-vl logs -f

# 查看特定服务日志
docker compose logs -f api
docker compose logs -f vllm-vl  # 或 vllm-omni



# 停止并重启所有服务（保留数据）
docker compose --profile gpu --profile vllm-vl --profile workers down
docker compose --profile gpu --profile vllm-vl --profile workers up -d

# 或者使用 restart 命令（更快，但不会应用配置更改）
docker compose --profile gpu --profile vllm-vl --profile workers restart

# 如果需要强制重建镜像再启动
docker compose --profile gpu --profile vllm-vl --profile workers up -d --build --force-recreate

```

## 开发进度

| 里程碑 | 功能 | 状态 |
|--------|------|------|
| MVP 1 | 模型管理 + 图片推理 + 用户权限 + Triton 自动部署 | **已完成** |
| MVP 2 | 视频推理 + 万物检测(VLM) + GPU监控 + API Key管理 | **已完成** |
| MVP 3 | RTMP推流 + SRS流媒体 + 实时视频检测渲染 | **已完成** |

## License

MIT
