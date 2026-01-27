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
| 节点 | 交付物 |
| --- | --- |
| 1 | 模型上传 + 元数据管理 + 图片推理 API |
| 2 | 图片推理结果Canvas 渲染 + 单模型测试页 |
| 3 | RTMP 推流接入 + SRS + FFmpeg 帧提取 + web页面能正常渲染视频流的检测结果 |
| 4 | 基础搜索 + 用户权限 |
| 5 | 压测 + 延迟优化 + 安全加固 |
| 6 | 全部服务docker部署上线交付 |

