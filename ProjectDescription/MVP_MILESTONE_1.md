# MVP 节点 1 验收报告

**版本**: 1.0  
**验收日期**: 2026-01-29  
**验收状态**: **通过**

---

## 1. 验收范围

根据 TECH_DESIGN.md 中定义的 MVP 节点 1 交付物：
> 模型管理（上传+加载+卸载+删除） + 元数据管理 + 图片推理 API + 不同用户权限

---

## 2. 已完成功能清单

### 2.1 用户认证系统

| 功能 | 状态 | 说明 |
| --- | --- | --- |
| 用户注册 | **已完成** | 支持邮箱+用户名注册，前端实时校验唯一性 |
| 用户登录 | **已完成** | JWT Token 认证，有效期可配置 |
| 用户类型 | **已完成** | 超级用户（可管理模型）、普通用户（仅使用模型） |
| 密码加密 | **已完成** | bcrypt 哈希存储 |

### 2.2 模型管理系统

| 功能 | 状态 | 说明 |
| --- | --- | --- |
| 模型创建 | **已完成** | 超级用户可创建模型，填写元数据 |
| 模型编辑 | **已完成** | 支持修改名称、描述、类别配置等 |
| 模型删除 | **已完成** | 级联删除模型文件、缩略图、Triton 部署 |
| 模型文件上传 | **已完成** | 支持 .onnx/.engine/.trt/.pt/.pth 格式 |
| 缩略图上传 | **已完成** | 支持 .jpg/.png/.gif/.webp 格式 |
| 类别配置 | **已完成** | 支持配置检测类别名称和颜色 |
| 模型列表 | **已完成** | 支持分页、按任务类型/框架筛选 |
| 权限控制 | **已完成** | 普通用户仅能查看公开模型 |

### 2.3 Triton 自动部署系统

| 功能 | 状态 | 说明 |
| --- | --- | --- |
| 自动部署 | **已完成** | 上传 ONNX/TensorRT 后自动部署到 Triton |
| 配置生成 | **已完成** | 从 ONNX 自动提取 shape 生成 config.pbtxt |
| 状态反馈 | **已完成** | 上传后返回 Triton 加载状态（成功/失败） |
| 状态显示 | **已完成** | 模型广场和个人中心显示 Triton 加载状态 |
| 自动卸载 | **已完成** | 删除模型时自动从 Triton 卸载并清理文件 |

### 2.4 图片推理系统

| 功能 | 状态 | 说明 |
| --- | --- | --- |
| 图片上传推理 | **已完成** | 支持 JPG/PNG 格式 |
| 动态模型适配 | **已完成** | 自动获取模型输入 shape，无需硬编码 |
| 置信度阈值 | **已完成** | 前端可调节 conf_threshold |
| IoU 阈值 | **已完成** | 前端可调节 iou_threshold |
| 重新推理 | **已完成** | 调整参数后可重新推理同一图片 |

### 2.5 前端渲染系统

| 功能 | 状态 | 说明 |
| --- | --- | --- |
| Canvas 检测框渲染 | **已完成** | 绘制检测框、类别标签、置信度 |
| 颜色映射 | **已完成** | 使用后端配置的类别颜色 |
| 类别统计表 | **已完成** | 显示各类别检测数量 |
| 延迟显示 | **已完成** | 显示推理耗时 |
| 推理中状态 | **已完成** | Overlay 遮罩显示，不丢失 canvas 内容 |

---

## 3. 技术方案总结

### 3.1 技术栈

| 层级 | 技术选型 |
| --- | --- |
| 前端 | React 19 + TypeScript + Vite + Ant Design 5 |
| 后端 | Python 3.11 + FastAPI + SQLAlchemy (async) + Pydantic |
| 数据库 | PostgreSQL 15 |
| 对象存储 | MinIO |
| 推理引擎 | NVIDIA Triton Inference Server 25.04 |
| 容器化 | Docker |

### 3.2 核心模块

| 模块 | 文件路径 | 功能 |
| --- | --- | --- |
| 认证服务 | `backend/app/api/v1/auth.py` | JWT 认证、用户注册登录 |
| 模型管理 | `backend/app/api/v1/models.py` | 模型 CRUD、文件上传 |
| 推理服务 | `backend/app/api/v1/inference.py` | 图片推理 API |
| Triton 客户端 | `backend/app/core/triton.py` | gRPC 推理调用、预处理、后处理 |
| Triton 仓库管理 | `backend/app/core/triton_repository.py` | 模型部署、config 生成 |
| MinIO 客户端 | `backend/app/core/minio.py` | 文件上传下载 |
| 模型详情页 | `frontend/src/pages/ModelDetail/` | 在线测试、结果渲染 |
| 模型上传页 | `frontend/src/pages/ModelUpload/` | 模型创建、文件上传 |

### 3.3 关键设计决策

| 决策点 | 方案 | 原因 |
| --- | --- | --- |
| Triton 部署模式 | 轮询模式 (poll) | 简化运维，无需显式 load/unload API |
| 模型命名 | model_{uuid} | 确保唯一性，避免命名冲突 |
| 配置生成 | 从 ONNX 提取元数据 | 支持不同输入尺寸的模型 |
| Canvas 渲染 | Overlay 遮罩 | 避免条件渲染导致内容丢失 |
| 状态反馈 | gRPC is_model_ready() | 端到端验证，确保真实可用 |
---

## 4. 测试报告

### 4.1 功能测试

| 测试用例 | 结果 | 备注 |
| --- | --- | --- |
| 超级用户注册登录 | **通过** | |
| 普通用户注册登录 | **通过** | |
| 超级用户创建模型 | **通过** | |
| 普通用户创建模型 | **通过** | 返回 403 Forbidden |
| ONNX 模型上传 | **通过** | 自动部署到 Triton |
| Triton 加载状态显示 | **通过** | 模型广场/个人中心显示状态 |
| 图片推理（有检测目标） | **通过** | 正确绘制检测框 |
| 图片推理（无检测目标） | **通过** | 显示"未检测到目标" |
| 调整阈值重新推理 | **通过** | |
| 模型删除 | **通过** | 级联删除文件和 Triton 部署 |

### 4.2 API 测试

```bash
# 模型元数据获取
GET /api/v1/models/{model_id}
Response: 200 OK
{
  "id": "f57bef24-7751-4fc6-bed6-51cec757bda4",
  "name": "松材线虫检测",
  "task_type": "detection",
  "framework": "onnx",
  "network_type": "YOLO11",
  "triton_status": {"deployed": true, "loaded": true},
  ...
}

# 图片推理
POST /api/v1/models/{model_id}/infer/image
Content-Type: multipart/form-data
Response: 200 OK
{
  "latency_ms": 47.89,
  "result": {
    "boxes": [...],
    "scores": [...],
    "labels": [...],
    "class_names": ["bad_tree"],
    "class_colors": {"bad_tree": "#FF0000"},
    "detection_count": 0
  }
}

# Triton 模型状态
GET http://localhost:8003/v2/models/model_{uuid}
Response: 200 OK
{
  "name": "model_f57bef24-7751-4fc6-bed6-51cec757bda4",
  "platform": "onnxruntime_onnx",
  "inputs": [{"name": "images", "datatype": "FP32", "shape": [1, 3, 384, 640]}],
  "outputs": [{"name": "output0", "datatype": "FP32", "shape": [1, 5, 5040]}]
}
```

### 4.3 性能指标

| 指标 | 目标值 | 实测值 | 状态 |
| --- | --- | --- | --- |
| 图片推理延迟 | < 500ms | ~48ms | **达标** |
| 模型冷启动 | < 5s | ~1s | **达标** |
| Triton 自动加载 | < 10s | ~5s | **达标** |

---

## 5. 已解决的技术问题

| 问题 | 根因 | 解决方案 |
| --- | --- | --- |
| Permission denied: /models | 后端进程无写权限 | 使用宿主机绝对路径，chown 修改权限 |
| explicit load not allowed | Triton 轮询模式限制 | 改用等待轮询自动加载 |
| 端口 8000 冲突 | 后端 API 占用 | Triton HTTP 映射到 8003 |
| 输入 shape 不匹配 | config.pbtxt 硬编码 | 从 ONNX 自动提取实际 shape |
| Canvas 内容丢失 | 条件渲染卸载组件 | 改用 Overlay 遮罩方式 |
| gRPC 连接失败 | Triton 未启动 | 添加服务可用性检查和友好提示 |

---

## 6. 后续规划

### 6.1 节点 2 目标
- RTMP 推流接入
- SRS 流媒体服务集成
- FFmpeg 帧提取
- 实时视频流检测结果渲染

### 6.2 待优化项
- 模型关键词搜索功能
- 推理结果缓存机制
- 批量推理优化
- 更多模型格式支持（TensorRT 动态 shape）

---

## 7. 验收结论

MVP 节点 1 所有功能已完成开发和测试，具备以下能力：

1. **完整的用户认证体系** - 支持超级用户/普通用户权限分离
2. **模型全生命周期管理** - 创建、编辑、上传、删除
3. **Triton 自动部署** - 上传即部署，实时状态反馈
4. **图片推理服务** - 支持 YOLO 检测模型，动态适配不同输入尺寸
5. **前端可视化** - Canvas 渲染检测结果，类别统计展示

**验收结果**: **通过**

---

*文档编写：AI Assistant*  
*验收日期：2026-01-29*
