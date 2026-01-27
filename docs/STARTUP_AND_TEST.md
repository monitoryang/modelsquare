# ModelSquare 启动与测试指南

## 一、环境要求

| 依赖 | 版本要求 |
|------|----------|
| Node.js | >= 18.x |
| Python | >= 3.10 |
| Docker | >= 20.x |
| Docker Compose | >= 2.x |

## 二、快速启动

### 2.1 初始化配置

```bash
# 克隆项目后，复制环境变量模板
cp .env.example .env

# 根据需要修改 .env 中的配置
```

### 2.2 启动基础设施服务

```bash
# 启动 PostgreSQL、Redis、MinIO、SRS
docker compose up -d postgres redis minio srs

# 查看服务状态
docker compose ps

# 等待服务健康检查通过（约10秒）
```

### 2.3 启动后端 API

```bash
cd backend

# 创建虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 运行数据库迁移（首次启动）
# alembic upgrade head

# 启动开发服务器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2.4 启动前端

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

### 2.5 一键启动脚本

```bash
# 使用提供的启动脚本
./scripts/dev-start.sh
```

## 三、服务地址一览

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端应用 | http://localhost:5173 | React 开发服务器 |
| API 文档 (Swagger) | http://localhost:8000/api/v1/docs | FastAPI 自动生成 |
| API 文档 (ReDoc) | http://localhost:8000/api/v1/redoc | FastAPI 自动生成 |
| PostgreSQL | localhost:5432 | 数据库 |
| Redis | localhost:6379 | 缓存/消息队列 |
| MinIO Console | http://localhost:9001 | 对象存储管理界面 |
| MinIO API | http://localhost:9000 | S3 兼容 API |
| SRS HTTP | http://localhost:8080 | 流媒体 HTTP 服务 |
| SRS RTMP | rtmp://localhost:1935/live | RTMP 推流地址 |

## 四、测试流程

### 4.1 后端 API 测试

#### 4.1.1 健康检查

```bash
# 基础健康检查
curl http://localhost:8000/api/v1/health

# 预期响应
# {"status":"healthy","service":"modelsquare-api"}

# 数据库连接检查
curl http://localhost:8000/api/v1/health/db

# Redis 连接检查
curl http://localhost:8000/api/v1/health/redis
```

#### 4.1.2 用户注册与登录

```bash
# 注册新用户
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "username": "testuser",
    "password": "password123"
  }'

# 登录获取 Token
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=test@example.com&password=password123"

# 保存返回的 access_token 用于后续请求
# 响应格式: {"access_token":"xxx","refresh_token":"xxx","token_type":"bearer"}
```

#### 4.1.3 模型管理 API

```bash
# 设置 Token (替换为实际获取的 token)
TOKEN="your_access_token_here"

# 创建模型
curl -X POST http://localhost:8000/api/v1/models \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "name": "YOLOv8 Detection",
    "description": "目标检测模型",
    "task_type": "detection",
    "framework": "onnx",
    "is_public": true,
    "tags": ["detection", "yolo"]
  }'

# 获取模型列表
curl http://localhost:8000/api/v1/models

# 获取单个模型详情 (替换 {model_id})
curl http://localhost:8000/api/v1/models/{model_id}

# 更新模型
curl -X PATCH http://localhost:8000/api/v1/models/{model_id} \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"description": "更新后的描述"}'

# 删除模型
curl -X DELETE http://localhost:8000/api/v1/models/{model_id} \
  -H "Authorization: Bearer $TOKEN"
```

#### 4.1.4 推理接口测试

```bash
# 图片推理 (需要模型已配置)
curl -X POST http://localhost:8000/api/v1/models/{model_id}/infer/image \
  -H "Authorization: Bearer $TOKEN" \
  -F "image=@/path/to/test_image.jpg"

# 视频推理
curl -X POST http://localhost:8000/api/v1/models/{model_id}/infer/video \
  -H "Authorization: Bearer $TOKEN" \
  -F "video=@/path/to/test_video.mp4"
```

#### 4.1.5 流媒体会话测试

```bash
# 创建推流会话
curl -X POST http://localhost:8000/api/v1/stream/start \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "model_id": "{model_id}",
    "stream_type": "rtmp"
  }'

# 获取推流状态
curl http://localhost:8000/api/v1/stream/{session_id}/status \
  -H "Authorization: Bearer $TOKEN"

# 停止推流会话
curl -X POST http://localhost:8000/api/v1/stream/{session_id}/stop \
  -H "Authorization: Bearer $TOKEN"
```

### 4.2 前端功能测试

#### 4.2.1 页面访问测试

| 页面 | 路径 | 验证内容 |
|------|------|----------|
| 首页 | / | 模型列表、搜索框、任务类型筛选 |
| 模型广场 | /models | 同首页 |
| 模型详情 | /models/:id | 模型信息、测试区域（图片/视频/推流标签页）|
| 登录页 | /login | 登录表单、注册链接 |
| 注册页 | /register | 注册表单 |
| 个人中心 | /profile | 用户信息、我的模型、API Key 管理 |

#### 4.2.2 功能测试清单

- [ ] 用户注册流程
- [ ] 用户登录/登出
- [ ] 模型列表加载与展示
- [ ] 模型搜索与筛选
- [ ] 模型详情查看
- [ ] 图片上传推理测试
- [ ] Canvas 结果渲染
- [ ] 个人中心访问（需登录）
- [ ] 响应式布局检查

### 4.3 Docker 服务测试

```bash
# 检查所有服务状态
docker compose ps

# 查看服务日志
docker compose logs -f postgres
docker compose logs -f redis
docker compose logs -f minio
docker compose logs -f srs

# MinIO 初始化 Bucket（首次）
docker compose exec minio mc alias set local http://localhost:9000 minioadmin minioadmin
docker compose exec minio mc mb local/models
docker compose exec minio mc mb local/temp

# 测试 RTMP 推流（需要安装 FFmpeg）
ffmpeg -re -i test_video.mp4 -c:v libx264 -f flv rtmp://localhost:1935/live/test

# 访问 HLS 播放
# http://localhost:8080/live/test.m3u8
```

### 4.4 单元测试

```bash
# 后端测试
cd backend
pytest tests/ -v --cov=app

# 前端测试
cd frontend
npm run test  # 如果配置了 vitest
```

## 五、常见问题排查

### 5.1 数据库连接失败

```bash
# 检查 PostgreSQL 容器状态
docker compose logs postgres

# 手动连接测试
docker compose exec postgres psql -U postgres -d modelsquare
```

### 5.2 Redis 连接失败

```bash
# 检查 Redis 容器状态
docker compose logs redis

# 手动连接测试
docker compose exec redis redis-cli ping
```

### 5.3 前端 API 请求失败

1. 检查后端服务是否运行在 8000 端口
2. 检查 CORS 配置是否包含前端地址
3. 检查 `.env` 中的 `VITE_API_URL` 配置

### 5.4 推流失败

```bash
# 检查 SRS 服务状态
curl http://localhost:1985/api/v1/versions

# 查看 SRS 日志
docker compose logs srs
```

## 六、停止服务

```bash
# 停止所有容器
docker compose down

# 停止并删除数据卷（清空数据）
docker compose down -v
```
