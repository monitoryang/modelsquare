# ModelSquare - 实时交互式模型广场平台

实时交互式 AI 模型推理与展示平台，支持模型上传、图像/视频推理和实时流媒体处理。

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

```bash
git clone git@github.com:Monitoryang/ModelSquare.git
cd ModelSquare

# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，修改必要配置（特别是 SECRET_KEY）
```

### 2. 启动基础服务 (Docker)

```bash
# 启动核心服务：PostgreSQL、Redis、MinIO、SRS
docker compose up -d postgres redis minio srs

# 查看服务状态
docker compose ps
```

### 3. 启动后端 API

**方式一：Docker 部署**

```bash
docker compose up -d api
```

**方式二：本地开发**

```bash
cd backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt

# 启动开发服务器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. 启动前端

**方式一：Docker 部署**

```bash
docker compose up -d web
```

**方式二：本地开发**

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

### 5. 启动 GPU 推理服务（可选）

```bash
# 需要 NVIDIA GPU 和 nvidia-docker
docker compose --profile gpu up -d triton
```

### 6. 启动 FFmpeg Worker（可选）

```bash
docker compose --profile workers up -d ffmpeg-worker
```

## 服务访问地址

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端 | http://localhost:3000 (Docker) / http://localhost:5173 (开发) | Web 界面 |
| 后端 API | http://localhost:8000 | RESTful API |
| API 文档 | http://localhost:8000/docs | Swagger UI |
| MinIO 控制台 | http://localhost:9001 | 对象存储管理 |
| SRS 控制台 | http://localhost:1985 | 流媒体服务 |
| Triton HTTP | http://localhost:8002 | 推理服务 |

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
│   └── ffmpeg/            # FFmpeg Worker
├── docs/                  # 项目文档
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
Error: listen EADDRINUSE :::8000
```

**解决方案**：检查并释放端口

```bash
# Linux/Mac
lsof -i :8000
kill -9 <PID>

# 或修改 .env 中的端口配置
```

### 4. Triton 启动失败（无 GPU）

如果没有 NVIDIA GPU，不要启动 Triton 服务：

```bash
# 仅启动基础服务，不包含 GPU profile
docker compose up -d
```

### 5. 前端 API 请求 CORS 错误

确保后端 `CORS_ORIGINS` 配置包含前端地址：

```env
CORS_ORIGINS=["http://localhost:5173","http://localhost:3000"]
```

## 开发命令

```bash
# 查看所有服务日志
docker compose logs -f

# 查看特定服务日志
docker compose logs -f api

# 重启服务
docker compose restart api

# 停止所有服务
docker compose down

# 停止并清除数据卷
docker compose down -v

# 重新构建镜像
docker compose build --no-cache
```

## License

MIT
