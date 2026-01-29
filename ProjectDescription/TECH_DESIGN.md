# 实时交互式模型广场平台

## 微服务化技术设计方案（基于 Triton + SRS）

**版本**：1.0
**日期**：2026-01-23
**作者**：杨汶

---
## 1.架构总览
本平台采用 微服务 + 流媒体管道 + 推理引擎解耦 的分层架构，核心目标是实现 低延迟、高并发、可扩展的实时模型推理与可视化体验。整体系统划分为以下模块：
+ 前端交互层：负责用户界面、流媒体采集、结果渲染
+ API 网关层：统一入口、认证鉴权、限流熔断
+ 业务逻辑层：模型管理、测试调度、对比分析
+ 流媒体处理层：推流接收、转码、帧提取
+ 推理执行层：模型加载、推理执行、结果结构化
+ 数据存储层：元数据、用户信息、测试记录
+ 基础设施层：容器编排、监控告警、CDN/对象存储（所有服务通过 Docker 容器化部署，MVP 阶段运行于单集群，V2 支持 Kubernetes 自动扩缩容。）
## 2.模块详细设计
### 2.1 前端交互层（Web Client）
技术栈
+ React 18 + TypeScript
+ Ant Design Pro（UI 组件库）
+ WebRTC（本地摄像头接入V2实现）
+ Canvas（2D 渲染）+ WebGL（高性能叠加，如热力图）
+ MediaSource Extensions（MSE）用于 HLS 播放
+ Axios + SWR（API 调用与缓存）

核心功能实现

| 功能 | 技术方案 |
| --- | --- |
| RTMP/WebRTC/HLS 输入 | - RTMP：由用户输入地址，前端仅展示播放器 - WebRTC：建立 P2P 或 SFU 连接至 SRS - HLS：使用 hls.js 播放 .m3u8 流 |
| 实时结果渲染 | 后端返回每帧推理结果（JSON）+ 可选合成图像 URL；前端使用 Canvas 叠加检测框/关键点，支持颜色映射表（按类别 ID → RGB）  |
| 延迟指示器 | 记录每帧 timestamp_in（推流时间戳）与 timestamp_out（结果返回时间），计算 Δt 并动态显示 |
性能优化
使用 requestAnimationFrame 同步渲染帧率
对高频更新的 Canvas 区域做局部重绘
推理结果缓存（避免重复请求相同帧）

### 2.2 API 网关与认证
技术栈
+ FastAPI（主后端框架）
+ Uvicorn（ASGI 服务器）
+ JWT + API Key 双认证
+ Redis（限流计数器）

接口规范（RESTful）

| 接口 | 方法 | 描述 | 认证 | 限流策略 |
| --- | --- | --- | --- | --- |
| /api/v1/models | GET | 模型列表（支持 task_type, framework 等过滤） | 可公开访问（含公开模型） | 100 req/min |
| /api/v1/models/{id} | GET | 模型详情（含 input/output spec） | 可公开访问（含公开模型） | 200 req/min |
| /api/v1/models/{id}/infer/image | POST | 图片推理 | API Key | 100 req/min |
| /api/v1/models/{id}/infer/video | POST | 短视频（≤30s）批量推理 | 可公开访问（含公开模型） | 100 req/min |
| /api/v1/stream/start | POST | 创建实时推流会话 | API Key + 用户登录 | 5 并发会话/用户 |
| /api/v1/stream/{session_id}/status | GET | 查询推流状态与最新结果 | API Key | 5 req/sec |

### 2.3 模型管理与元数据服务
数据模型（PostgreSQL）

```sql
-- models 表
CREATE TABLE models (
  id UUID PRIMARY KEY,
  owner_id UUID REFERENCES users(id),
  name VARCHAR(128) NOT NULL,
  description TEXT,
  task_type VARCHAR(32) CHECK (task_type IN ('classification', 'detection', 'segmentation', 'multimodal', 'nlp')),
  framework VARCHAR(16) CHECK (framework IN ('pytorch', 'onnx', 'tensorrt')),
  input_spec JSONB,   -- e.g., {"image": "HWC", "text": "str"}
  output_spec JSONB,  -- e.g., {"boxes": "Nx4", "labels": "N"}
  version VARCHAR(16),
  is_public BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ
);
-- model_files 表（存储模型文件路径）
CREATE TABLE model_files (
  model_id UUID REFERENCES models(id),
  file_path VARCHAR(256),  -- MinIO 路径
  format VARCHAR(16)       -- 'onnx', 'pt', 'engine'
);
```
功能实现
+ 模型上传：前端分片上传至 MinIO，后端校验格式并注册到 Triton
+ 元数据编辑：通过 PATCH /models/{id} 更新
+ 权限控制：SQL 查询自动附加 WHERE (is_public = true OR owner_id = current_user)

### 2.4 流媒体梳理管道
#### 架构流程
```text
[用户推流] 
   → RTMP/WebRTC → [SRS 服务器] 
   → FFmpeg 转码（1080p@30fps → 720p@25fps） 
   → 每帧抽帧（YUV → RGB） 
   → 写入 Redis Stream（key: stream:{session_id}）
   → 推理服务消费帧
```
#### 技术组件
+ SRS (Simple Realtime Server)：开源流媒体服务器，支持 RTMP/WebRTC/HLS
+ FFmpeg：运行于独立容器，监听 SRS 的 ingest 事件
+ Redis Streams：作为帧队列，支持多消费者（未来可扩展多模型并行）

### 2.5 模型推理引擎（Triton Inference Server）
#### 配置
+ 支持模型格式：ONNX、PyTorch (.pt)、TensorRT (.engine)
+ 每个模型部署为独立 Triton Model Repository
+ 动态批处理（Dynamic Batching）启用，提升吞吐
#### 推理流程
1. 业务服务从 Redis Stream 读取一帧图像 + session_id
2. 根据 session 关联的 model_id，调用 Triton gRPC 接口
3. Triton 返回结构化输出（如 boxes, scores, masks）
4. 结果序列化为 JSON，写回 Redis（供前端轮询）或 WebSocket（可选）

#### 多模态支持
+ 对于多模态模型（如 CLIP、Flamingo），前端需同时提交：
```json
{
  "image": "<base64 or url>",
  "text": "What is in the image?",
  "audio": null  // 可选
}
```

### 2.6 存储与 CDN

| 数据类型 | 存储方案 | 说明 |
| --- | --- | --- |
| 用户头像、模型图标 | MinIO（私有桶） | 通过 Presigned URL 临时授权访问 |
| 推理结果图像 | MinIO（temp/ 目录，7天过期） | 用于 API 返回的 render_url |
| 视频录制文件 | MinIO（recordings/） | 用户可下载 |
| 静态资源（JS/CSS） | Nginx + 缓存 | 或对接 Cloudflare CDN |

## 3.部署运维
### 3.1 容器化部署（Docker Compose- mvp）
开发过程中需要构建dev镜像，一个是runtime镜像
```yaml

services:
   web:       自定义 (./frontend/Dockerfile)   # React 前端
   api:       自定义 (./backend/Dockerfile)   # FastAPI 后端
   triton:    nvcr.io/nvidia/tritonserver:25.04-py3   # NVIDIA Triton Server
   srs:       ossrs/srs:v6.0.155   # 流媒体服务器
   ffmpeg-worker: 自定义 # 帧提取服务
   postgres:    postgres # 元数据库
   redis:       redis # 缓存 + Stream
   minio:       minio/minio # 对象存储

```
### 3.2 监控与日志
+ Prometheus：采集 Triton QPS、GPU 利用率、API 延迟
+ Grafana：可视化仪表盘（含“当前并发推流数”、“平均端到端延迟”）
+ ELK Stack：日志聚合（错误日志自动告警）

### 3.3 SLA 保障
+ 推流中断 > 10s → 前端提示“连接丢失，尝试重连”
+ Triton 服务宕机 → API 返回 503 Service Unavailable
+ 自动健康检查：每 30s ping /health

## 4. 性能与安全合规
### 4.1 性能指标（MVP 目标）
| 指标 | 局域网 |
| --- | --- |
| 端到端延迟 | ≤ 500ms |
| 并发推流 | ≥ 50 路 |
| 模型冷启动 | ≤ 5s |
| 静态资源（JS/CSS） | Nginx + 缓存 |
### 4.2 安全措施
+ 数据隔离：MinIO 桶策略 + PostgreSQL Row-Level Security
+ 防 DDoS：API 网关集成 rate-limiting（基于 IP + API Key）
+ 隐私合规：用户可删除所有测试记录；不存储原始推流视频（仅帧缓存 10 分钟）

## 5. 扩展性设计
+ 新增模型框架：只需在 Triton 中添加对应 backend（如 TensorFlow）
+ 边缘部署：未来可将 Triton + SRS 打包为边缘一体机镜像

## 6. MVP 开发里程碑
| 节点 | 交付物 | 状态 |
| --- | --- | --- |
| 1 | 模型管理（上传+加载+卸载+删除） + 元数据管理 + 图片推理 API + 不同用户权限 | **已完成** |
| 2 | 图片推理结果Canvas 渲染 + 单模型测试页 | **已完成** |
| 3 | RTMP 推流接入 + SRS + FFmpeg 帧提取 + web页面能正常渲染视频流的检测结果 | 待开发 |
| 4 | 基础搜索 + 用户权限 | 待开发 |
| 5 | 压测 + 延迟优化 + 安全加固 | 待开发 |
| 6 | 全部服务docker部署上线交付 | 待开发 |

---

## 7. MVP 节点 1 技术实现详情（已完成）

### 7.1 系统架构实现

#### 7.1.1 服务拓扑
```
┌─────────────────────────────────────────────────────────────────────┐
│                          前端 (React + Vite)                        │
│                         http://localhost:5173                        │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │ HTTP API
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      后端 API (FastAPI + Uvicorn)                    │
│                         http://localhost:8000                        │
└──────────┬──────────────────────┬──────────────────────┬────────────┘
           │                      │                      │
           ▼                      ▼                      ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐
│   PostgreSQL     │  │     MinIO        │  │   Triton Inference       │
│   localhost:5432 │  │ localhost:9000   │  │   Server (gRPC:8001)     │
│   (元数据存储)    │  │ (模型文件存储)    │  │   (模型推理引擎)          │
└──────────────────┘  └──────────────────┘  └──────────────────────────┘
```

#### 7.1.2 端口映射
| 服务 | 端口 | 协议 | 说明 |
| --- | --- | --- | --- |
| Frontend | 5173 | HTTP | Vite 开发服务器 |
| Backend API | 8000 | HTTP | FastAPI 主服务 |
| PostgreSQL | 5432 | TCP | 数据库 |
| MinIO API | 9000 | HTTP | 对象存储 API |
| MinIO Console | 9001 | HTTP | MinIO 管理界面 |
| Triton HTTP | 8003 | HTTP | Triton REST API（映射自容器8000） |
| Triton gRPC | 8001 | gRPC | Triton 推理接口 |
| Triton Metrics | 8002 | HTTP | Prometheus 指标 |

### 7.2 核心功能实现

#### 7.2.1 用户认证系统
- **技术方案**: JWT (JSON Web Token) 认证
- **用户类型**: 超级用户（可上传/管理模型）、普通用户（仅可使用公开模型）
- **注册验证**: 前端实时校验用户名/邮箱唯一性
- **密码加密**: bcrypt 哈希算法

#### 7.2.2 模型管理系统

**数据库模型**:
```python
class Model:
    id: UUID                    # 主键
    owner_id: UUID              # 所有者（外键关联users）
    name: str                   # 模型名称
    description: str            # 描述
    task_type: TaskType         # 任务类型（detection/classification/segmentation等）
    framework: Framework        # 框架（pytorch/onnx/tensorrt）
    network_type: NetworkType   # 网络类型（YOLOv8/YOLO11）
    class_config: List[Dict]    # 类别配置（名称+颜色映射）
    input_spec: Dict            # 输入规范
    output_spec: Dict           # 输出规范
    version: str                # 版本号
    is_public: bool             # 是否公开
    thumbnail_url: str          # 缩略图路径
    
class ModelFile:
    id: UUID
    model_id: UUID              # 关联模型
    file_path: str              # MinIO 存储路径
    file_format: str            # 文件格式（onnx/engine/pt）
    file_size: int              # 文件大小
    checksum: str               # SHA256 校验和
```

**模型上传流程**:
1. 前端创建模型元数据 (POST /api/v1/models)
2. 前端上传模型文件 (POST /api/v1/models/{id}/files)
3. 后端存储文件到 MinIO
4. 后端自动部署到 Triton（仅 ONNX/TensorRT 格式）
5. 返回部署状态反馈

#### 7.2.3 Triton 自动部署系统

**核心模块**: `backend/app/core/triton_repository.py`

**自动部署流程**:
```
[模型上传] 
  → 存储至 MinIO (models/{model_id}/model.onnx)
  → 下载到 Triton 仓库 (/models/model_{uuid}/1/model.onnx)
  → 自动读取 ONNX 元数据（输入/输出 shape、dtype）
  → 生成 config.pbtxt 配置文件
  → Triton 轮询模式自动加载
  → gRPC 验证模型就绪状态
  → 返回部署结果给前端
```

**关键技术点**:
- **ONNX 元数据提取**: 使用 `onnx` 库读取模型输入/输出张量信息
- **动态配置生成**: 根据实际模型 shape 生成 config.pbtxt（避免硬编码）
- **轮询模式兼容**: Triton 启用 `--model-control-mode=poll` 后无法显式调用 load_model()，改用等待轮询加载
- **状态验证**: 通过 gRPC `is_model_ready()` 验证真实加载状态

**config.pbtxt 模板示例**:
```protobuf
name: "model_{uuid}"
platform: "onnxruntime_onnx"
max_batch_size: 0

input [
  {
    name: "images"
    data_type: TYPE_FP32
    dims: [ 1, 3, 384, 640 ]  # 从 ONNX 自动提取
  }
]

output [
  {
    name: "output0"
    data_type: TYPE_FP32
    dims: [ 1, 5, 5040 ]      # 从 ONNX 自动提取
  }
]

instance_group [
  {
    count: 1
    kind: KIND_GPU
    gpus: [ 0 ]
  }
]
```

#### 7.2.4 图片推理系统

**核心模块**: `backend/app/core/triton.py`

**推理流程**:
```
[图片上传] 
  → 格式验证（JPG/PNG）
  → 获取模型元数据（从 Triton gRPC）
  → 动态确定输入 shape
  → 图片预处理（Letterbox resize + 归一化）
  → gRPC 调用 Triton 推理
  → 后处理（NMS + 坐标还原）
  → 返回结构化检测结果
```

**推理服务类设计**:
```python
class YOLOInferenceService:
    - _model_metadata_cache: Dict  # 模型元数据缓存
    - preprocessor: YOLOPreprocessor
    - postprocessor: YOLOPostprocessor
    
    async def infer(model_name, image_bytes, class_names, conf_threshold, iou_threshold):
        # 1. 获取模型元数据（带缓存）
        # 2. 动态预处理（适配不同输入尺寸）
        # 3. gRPC 推理调用
        # 4. 后处理（NMS、坐标缩放）
        # 5. 返回 {boxes, scores, labels, class_names}
```

**关键技术点**:
- **动态输入适配**: 从 Triton 获取模型实际输入 shape，而非硬编码
- **Letterbox 预处理**: 保持宽高比的图片缩放，边缘填充
- **YOLO 后处理**: xywh→xyxy 转换、NMS 去重、坐标还原

#### 7.2.5 前端渲染系统

**Canvas 渲染流程**:
```
[图片选择] 
  → 立即绘制原始图片（用户反馈）
  → 显示推理中遮罩层（Overlay 方式，不卸载 canvas）
  → 推理完成后绘制检测框
  → 显示类别统计表格
```

**关键技术点**:
- **Canvas 持久化**: 使用 Overlay 遮罩而非条件渲染，避免 canvas 被卸载丢失内容
- **动态缩放**: 根据原图与 canvas 尺寸计算坐标缩放比例
- **颜色映射**: 从后端 class_colors 获取每个类别的显示颜色

### 7.3 API 接口实现

#### 7.3.1 认证接口
| 接口 | 方法 | 描述 |
| --- | --- | --- |
| /api/v1/auth/register | POST | 用户注册 |
| /api/v1/auth/login | POST | 用户登录，返回 JWT |
| /api/v1/auth/me | GET | 获取当前用户信息 |

#### 7.3.2 模型管理接口
| 接口 | 方法 | 描述 |
| --- | --- | --- |
| /api/v1/models | GET | 模型列表（支持筛选、分页） |
| /api/v1/models | POST | 创建模型（超级用户） |
| /api/v1/models/{id} | GET | 模型详情 |
| /api/v1/models/{id} | PATCH | 更新模型元数据 |
| /api/v1/models/{id} | DELETE | 删除模型 |
| /api/v1/models/{id}/files | POST | 上传模型文件 |
| /api/v1/models/{id}/files | GET | 列出模型文件 |
| /api/v1/models/{id}/thumbnail | POST | 上传缩略图 |

#### 7.3.3 推理接口
| 接口 | 方法 | 描述 |
| --- | --- | --- |
| /api/v1/models/{id}/infer/image | POST | 图片推理 |

**推理响应格式**:
```json
{
  "model_id": "uuid",
  "timestamp_in": "2026-01-29T08:45:57.856564Z",
  "timestamp_out": "2026-01-29T08:45:57.904450Z",
  "latency_ms": 47.89,
  "result_type": "detection",
  "result": {
    "boxes": [[x1, y1, x2, y2], ...],
    "scores": [0.95, 0.87, ...],
    "labels": [0, 1, ...],
    "class_names": ["bad_tree", ...],
    "class_colors": {"bad_tree": "#FF0000"},
    "detection_count": 5
  }
}
```

### 7.4 环境配置

#### 7.4.1 后端环境变量
```bash
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/modelsquare
SECRET_KEY=your-secret-key
CORS_ORIGINS=["http://localhost:5173"]

# MinIO
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET_MODELS=models
MINIO_BUCKET_THUMBNAILS=thumbnails

# Triton
TRITON_URL=localhost:8001
TRITON_MODEL_REPOSITORY=/mnt/14TB/yangwen/code/AIcoder/ModelSquare/models
```

#### 7.4.2 Triton 启动命令
```bash
docker run -d --name modelsquare-triton --gpus all \
  -p 8003:8000 -p 8001:8001 -p 8002:8002 \
  -v /mnt/14TB/yangwen/code/AIcoder/ModelSquare/models:/models:rw \
  nvcr.io/nvidia/tritonserver:25.04-py3 \
  tritonserver --model-repository=/models \
  --model-control-mode=poll \
  --repository-poll-secs=5
```

### 7.5 测试方案

#### 7.5.1 功能测试
| 测试项 | 测试方法 | 预期结果 |
| --- | --- | --- |
| 用户注册 | 使用有效邮箱注册 | 注册成功，可登录 |
| 用户登录 | 使用正确凭证登录 | 返回 JWT Token |
| 模型创建 | 超级用户创建检测模型 | 模型创建成功 |
| 模型文件上传 | 上传 ONNX 文件 | 文件存储成功，Triton 加载成功 |
| 图片推理 | 上传测试图片 | 返回检测结果，前端正确渲染 |
| 权限控制 | 普通用户尝试上传模型 | 返回 403 Forbidden |

#### 7.5.2 API 测试示例
```bash
# 测试推理接口
curl -X POST "http://localhost:8000/api/v1/models/{model_id}/infer/image" \
  -F "image=@test.jpg" \
  -F "conf_threshold=0.25" \
  -F "iou_threshold=0.45"

# 验证 Triton 模型状态
curl http://localhost:8003/v2/models/{model_name}
```

### 7.6 已知问题与解决方案

| 问题 | 原因 | 解决方案 |
| --- | --- | --- |
| Permission denied: /models | 后端进程无写权限 | 使用宿主机绝对路径 + chown 修改权限 |
| polling is enabled 错误 | Triton 轮询模式禁止显式 load | 改用等待轮询自动加载 |
| 端口 8000 冲突 | 后端占用 8000 | Triton HTTP 映射到 8003 |
| 输入 shape 不匹配 | config.pbtxt 硬编码 shape | 从 ONNX 自动提取实际 shape |
| Canvas 内容丢失 | 条件渲染卸载 canvas | 改用 Overlay 遮罩方式 |

