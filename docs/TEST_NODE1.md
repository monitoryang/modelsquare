# MVP 节点一 测试文档

## 交付物范围

- 模型上传功能
- 模型元数据管理
- 图片推理 API

---

## 一、环境准备

### 1.1 依赖要求

| 依赖 | 版本要求 | 检查命令 |
|------|----------|----------|
| Docker | >= 20.x | `docker --version` |
| Docker Compose | >= 2.x | `docker compose version` |
| Node.js | >= 18.x | `node --version` |
| Python | >= 3.10 | `python3 --version` |

### 1.2 启动服务

```bash
# 1. 复制环境变量
cp .env.example .env

# 2. 启动基础设施（PostgreSQL、Redis、MinIO）
docker compose up -d postgres redis minio

# 3. 等待服务就绪（约10秒）
docker compose ps
```

**预期输出：**
```
NAME                    STATUS
modelsquare-postgres    running (healthy)
modelsquare-redis       running (healthy)
modelsquare-minio       running (healthy)
```

### 1.3 启动后端 API

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**预期输出：**
```
INFO:     Will watch for changes in these directories: ['/mnt/14TB/yangwen/code/AIcoder/ModelSquare/backend']
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [2912376] using WatchFiles
INFO:     Started server process [2912382]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

### 1.4 启动前端

```bash
cd frontend
npm install
npm run dev
```

**预期输出：**
```
VITE v7.x.x  ready in xxx ms
➜  Local:   http://localhost:5173/
```

---

## 二、单元测试

### 2.1 后端单元测试

```bash
cd backend
source venv/bin/activate
pytest tests/ -v --cov=app
```

**预期输出特征：**
- 所有测试用例显示 `PASSED`
- 覆盖率报告正常生成
- 无 `FAILED` 或 `ERROR` 状态

**失败判定标准：**
- 任何测试用例显示 `FAILED`
- 出现 `ImportError` 或 `ModuleNotFoundError`

**日志定位：**
- 测试日志：终端直接输出
- 详细日志：`pytest tests/ -v --tb=long`

### 2.2 前端单元测试

```bash
cd frontend
npm run test
```

**预期输出特征：**
- 测试套件全部通过
- 无控制台错误

---

## 三、集成测试

### 3.1 健康检查接口

```bash
# 基础健康检查
curl -s http://localhost:8000/api/v1/health | jq
```

**预期输出：**
```json
{
  "status": "healthy",
  "service": "modelsquare-api"
}
```

**失败判定：** `status` 不为 `healthy` 或连接超时

---

### 3.2 用户注册接口

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@modelsquare.com",
    "username": "testuser",
    "password": "Test@123456"
  }' | jq
```

**预期输出：**
```json
{
  "id": "uuid-string",
  "email": "test@modelsquare.com",
  "username": "testuser",
  "full_name": null,
  "is_active": true,
  "created_at": "2026-01-26T..."
}
```

**失败判定：**
- HTTP 状态码非 201
- 返回 `detail: "Email already registered"` 表示重复注册

---

### 3.3 用户登录接口

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=test@modelsquare.com&password=Test@123456" | jq
```

**预期输出：**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

**保存 Token 供后续测试使用：**
```bash
export TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=test@modelsquare.com&password=Test@123456" | jq -r '.access_token')

echo $TOKEN
```

**失败判定：**
- HTTP 状态码 401：用户名或密码错误
- HTTP 状态码 403：用户被禁用

---

### 3.4 模型创建接口

```bash
curl -s -X POST http://localhost:8000/api/v1/models \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "name": "YOLOv8-Detection",
    "description": "目标检测模型，支持80类物体识别",
    "task_type": "detection",
    "framework": "onnx",
    "version": "1.0.0",
    "is_public": true,
    "tags": ["detection", "yolo", "coco"],
    "input_spec": {"image": "HWC", "shape": [640, 640, 3]},
    "output_spec": {"boxes": "Nx4", "scores": "N", "labels": "N"}
  }' | jq
```

**预期输出：**
```json
{
  "id": "uuid-string",
  "owner_id": "uuid-string",
  "name": "YOLOv8-Detection",
  "task_type": "detection",
  "framework": "onnx",
  "is_public": true,
  "created_at": "2026-01-26T...",
  "updated_at": "2026-01-26T..."
}
```

**保存模型 ID：**
```bash
export MODEL_ID=$(curl -s -X POST http://localhost:8000/api/v1/models \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"name":"TestModel","task_type":"detection","framework":"onnx"}' | jq -r '.id')

echo $MODEL_ID
```

**失败判定：**
- HTTP 状态码 401：未认证
- HTTP 状态码 422：请求参数校验失败

---

### 3.5 模型列表查询接口

```bash
# 查询所有公开模型
curl -s "http://localhost:8000/api/v1/models" | jq

# 按任务类型筛选
curl -s "http://localhost:8000/api/v1/models?task_type=detection" | jq

# 关键词搜索
curl -s "http://localhost:8000/api/v1/models?keyword=yolo" | jq

# 分页查询
curl -s "http://localhost:8000/api/v1/models?page=1&page_size=10" | jq
```

**预期输出：**
```json
{
  "items": [...],
  "total": 1,
  "page": 1,
  "page_size": 20,
  "pages": 1
}
```

**失败判定：**
- `items` 数组为空（应至少包含刚创建的模型）
- `total` 与实际数量不符

---

### 3.6 模型详情查询接口

```bash
curl -s "http://localhost:8000/api/v1/models/$MODEL_ID" | jq
```

**预期输出：**
```json
{
  "id": "uuid-string",
  "name": "YOLOv8-Detection",
  "description": "...",
  "task_type": "detection",
  "framework": "onnx",
  "input_spec": {...},
  "output_spec": {...}
}
```

**失败判定：**
- HTTP 状态码 404：模型不存在
- 返回数据与创建时不一致

---

### 3.7 模型更新接口

```bash
curl -s -X PATCH "http://localhost:8000/api/v1/models/$MODEL_ID" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "description": "更新后的模型描述",
    "version": "1.0.1"
  }' | jq
```

**预期输出：**
```json
{
  "id": "uuid-string",
  "description": "更新后的模型描述",
  "version": "1.0.1",
  "updated_at": "2026-01-26T..."
}
```

**失败判定：**
- HTTP 状态码 403：非模型所有者
- `updated_at` 未更新

---

### 3.8 图片推理接口

```bash
# 准备测试图片（如果没有，可以创建一个简单的测试图片）
# 或使用网络图片下载
curl -o /tmp/test.jpg https://via.placeholder.com/640x480.jpg

# 调用推理接口
curl -s -X POST "http://localhost:8000/api/v1/models/$MODEL_ID/infer/image" \
  -H "Authorization: Bearer $TOKEN" \
  -F "image=@/tmp/test.jpg" | jq
```

**预期输出：**
```json
{
  "model_id": "uuid-string",
  "timestamp_in": "2026-01-26T...",
  "timestamp_out": "2026-01-26T...",
  "latency_ms": 12.5,
  "result_type": "detection",
  "result": {
    "status": "mock_result",
    "message": "Inference endpoint ready - Triton integration pending"
  },
  "render_url": null
}
```

**失败判定：**
- HTTP 状态码 400：图片格式不支持
- HTTP 状态码 404：模型不存在
- `latency_ms` 为负数或异常大

---

### 3.9 模型删除接口

```bash
# 创建临时模型用于删除测试
TEMP_MODEL_ID=$(curl -s -X POST http://localhost:8000/api/v1/models \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"name":"TempModel","task_type":"classification","framework":"pytorch"}' | jq -r '.id')

# 删除模型
curl -s -X DELETE "http://localhost:8000/api/v1/models/$TEMP_MODEL_ID" \
  -H "Authorization: Bearer $TOKEN" -w "\nHTTP Status: %{http_code}\n"

# 验证删除成功
curl -s "http://localhost:8000/api/v1/models/$TEMP_MODEL_ID" -w "\nHTTP Status: %{http_code}\n"
```

**预期输出：**
- 删除请求：HTTP Status 204
- 验证请求：HTTP Status 404

**失败判定：**
- 删除后仍能查询到模型
- HTTP 状态码 403：权限不足

---

## 四、端到端测试

### 4.1 前端页面访问测试

| 序号 | 页面 | URL | 验证内容 | 预期结果 |
|------|------|-----|----------|----------|
| 1 | 首页 | http://localhost:5173/ | 页面加载、模型列表展示 | 无控制台错误，列表正常渲染 |
| 2 | 登录页 | http://localhost:5173/login | 表单渲染、提交功能 | 表单可交互 |
| 3 | 注册页 | http://localhost:5173/register | 表单渲染、提交功能 | 表单可交互 |
| 4 | 模型详情 | http://localhost:5173/models/{id} | 模型信息、测试区域 | 信息正确展示 |

### 4.2 前端功能流程测试

**测试流程 1：用户注册 → 登录 → 查看首页**

1. 访问 http://localhost:5173/register
2. 填写注册表单并提交
3. 跳转至登录页
4. 使用注册的账号登录
5. 登录成功后跳转首页
6. 验证用户头像区域显示

**测试流程 2：模型详情 → 图片测试**

1. 访问首页，点击任意模型卡片
2. 进入模型详情页
3. 在"图片测试"标签页上传图片
4. 等待推理完成
5. 验证 Canvas 区域显示结果
6. 验证推理结果 JSON 展示

---

## 五、测试检查清单

### 5.1 后端接口检查清单

| 序号 | 接口 | 方法 | 状态 |
|------|------|------|------|
| 1 | /api/v1/health | GET | [ ] |
| 2 | /api/v1/auth/register | POST | [ ] |
| 3 | /api/v1/auth/login | POST | [ ] |
| 4 | /api/v1/auth/me | GET | [ ] |
| 5 | /api/v1/models | GET | [ ] |
| 6 | /api/v1/models | POST | [ ] |
| 7 | /api/v1/models/{id} | GET | [ ] |
| 8 | /api/v1/models/{id} | PATCH | [ ] |
| 9 | /api/v1/models/{id} | DELETE | [ ] |
| 10 | /api/v1/models/{id}/infer/image | POST | [ ] |

### 5.2 前端页面检查清单

| 序号 | 页面 | 功能点 | 状态 |
|------|------|--------|------|
| 1 | 首页 | 模型列表加载 | [ ] |
| 2 | 首页 | 搜索功能 | [ ] |
| 3 | 首页 | 任务类型筛选 | [ ] |
| 4 | 登录页 | 表单提交 | [ ] |
| 5 | 注册页 | 表单提交 | [ ] |
| 6 | 模型详情 | 信息展示 | [ ] |
| 7 | 模型详情 | 图片上传推理 | [ ] |

---

## 六、常见问题排查

### 6.1 后端启动失败

**问题：** `ModuleNotFoundError`

```bash
# 解决方案：确保在虚拟环境中且已安装依赖
source venv/bin/activate
pip install -r requirements.txt
```

### 6.2 数据库连接失败

**问题：** `Connection refused`

```bash
# 检查 PostgreSQL 容器状态
docker compose ps postgres
docker compose logs postgres

# 重启服务
docker compose restart postgres
```

### 6.3 前端 API 请求 CORS 错误

**问题：** `Access-Control-Allow-Origin` 错误

```bash
# 检查后端 CORS 配置
# 确保 .env 中 CORS_ORIGINS 包含前端地址
CORS_ORIGINS=["http://localhost:5173"]
```

### 6.4 Token 过期

**问题：** HTTP 401 Unauthorized

```bash
# 重新登录获取新 Token
export TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=test@modelsquare.com&password=Test@123456" | jq -r '.access_token')
```

---

## 七、测试完成标准

节点一测试通过的判定标准：

- [ ] 所有后端接口返回预期状态码
- [ ] 模型 CRUD 操作完整可用
- [ ] 图片推理接口正常响应
- [ ] 前端页面无控制台错误
- [ ] 用户注册/登录流程通畅
- [ ] 模型详情页图片测试功能可用
