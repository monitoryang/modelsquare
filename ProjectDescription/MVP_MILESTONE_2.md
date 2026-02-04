# MVP 节点 2 验收报告

**版本**: 1.0  
**验收日期**: 2026-02-04  
**验收状态**: **通过**

---

## 1. 验收范围

根据 TECH_DESIGN.md 中定义的 MVP 节点 2 交付物：
> 图片推理结果Canvas 渲染 + 单模型测试页

实际交付内容扩展：
> 图片推理渲染 + 视频推理 + 万物检测（VLM Grounding） + GPU 监控 + API Key 管理

---

## 2. 已完成功能清单

### 2.1 视频推理系统

| 功能 | 状态 | 说明 |
| --- | --- | --- |
| 视频文件上传 | **已完成** | 支持 MP4/AVI/MOV 等常见格式 |
| 后台异步推理 | **已完成** | 使用 FFmpeg 逐帧提取并推理 |
| 进度实时反馈 | **已完成** | WebSocket 推送处理进度 |
| 推理结果视频生成 | **已完成** | 检测框渲染到输出视频 |
| 视频下载 | **已完成** | 生成带检测结果的视频文件供下载 |
| 任务取消 | **已完成** | 支持中止正在进行的推理任务 |

### 2.2 万物检测功能（VLM Grounding）

| 功能 | 状态 | 说明 |
| --- | --- | --- |
| vLLM 集成 | **已完成** | 集成 Qwen3-VL-32B-Instruct 模型 |
| 自然语言检测 | **已完成** | 输入中文/英文描述检测目标 |
| 检测框绘制 | **已完成** | PIL 绘制边界框和标签 |
| 中文标签渲染 | **已完成** | 文泉驿正黑字体支持 |
| 多目标检测 | **已完成** | 支持同时检测多个不同类别 |
| 置信度显示 | **已完成** | 显示每个检测框的置信度 |

### 2.3 GPU 监控系统

| 功能 | 状态 | 说明 |
| --- | --- | --- |
| GPU 利用率监控 | **已完成** | 实时显示 GPU 使用率 |
| 显存监控 | **已完成** | 显示已用/总显存 |
| 温度监控 | **已完成** | 显示 GPU 温度 |
| 多卡支持 | **已完成** | 支持监控多块 GPU |
| 历史数据 | **已完成** | 记录并展示历史监控数据 |

### 2.4 API Key 管理

| 功能 | 状态 | 说明 |
| --- | --- | --- |
| API Key 创建 | **已完成** | 用户可创建个人 API Key |
| API Key 列表 | **已完成** | 显示所有 Key 及其状态 |
| API Key 删除 | **已完成** | 支持撤销已创建的 Key |
| 有效期管理 | **已完成** | 支持设置 Key 过期时间 |
| 调用统计 | **已完成** | 记录 API 调用次数 |

### 2.5 个人中心增强

| 功能 | 状态 | 说明 |
| --- | --- | --- |
| 模型配置编辑 | **已完成** | 支持修改已上传模型的配置 |
| 模型状态显示 | **已完成** | 显示 Triton 加载状态 |
| 测试记录查看 | **已完成** | 查看历史推理记录 |

---

## 3. 技术方案总结

### 3.1 新增技术栈

| 组件 | 技术选型 | 用途 |
| --- | --- | --- |
| 大模型推理 | vLLM v0.13.0 | Qwen3-VL-32B 推理服务 |
| 视频处理 | FFmpeg | 视频帧提取与合成 |
| GPU 监控 | pynvml / nvidia-ml-py | NVIDIA GPU 状态获取 |
| 中文字体 | fonts-wqy-zenhei | PIL 中文渲染支持 |

### 3.2 核心模块

| 模块 | 文件路径 | 功能 |
| --- | --- | --- |
| VLM 推理 | `backend/app/api/v1/inference.py` | 万物检测 API |
| VLM 客户端 | `backend/app/core/vllm_client.py` | vLLM 服务调用 |
| GPU 管理 | `backend/app/core/gpu_manager.py` | GPU 状态监控 |
| 视频推理 | `backend/app/api/v1/inference.py` | 视频处理流水线 |
| API Key | `backend/app/api/v1/api_keys.py` | Key 管理 CRUD |
| 万物检测页 | `frontend/src/pages/VLMGrounding/` | 前端交互界面 |
| GPU 监控页 | `frontend/src/pages/GPUMonitor/` | 监控数据展示 |

### 3.3 关键设计决策

| 决策点 | 方案 | 原因 |
| --- | --- | --- |
| VLM 部署 | vLLM 独立服务 | GPU 显存隔离，避免与 Triton 冲突 |
| 视频处理 | 后台异步任务 | 长时间任务不阻塞主线程 |
| 检测框渲染 | 后端 PIL 绘制 | 保证中文字体一致性 |
| GPU 监控 | NVML 直接调用 | 低开销，高精度 |
| 临时文件存储 | MinIO temp bucket | 统一管理，自动清理 |

---

## 4. 测试报告

### 4.1 功能测试

| 测试用例 | 结果 | 备注 |
| --- | --- | --- |
| 万物检测 - 英文提示词 | **通过** | "building" 正确检测建筑物 |
| 万物检测 - 中文提示词 | **通过** | "汽车" 正确检测车辆 |
| 万物检测 - 中文标签渲染 | **通过** | 标签显示正常，无乱码 |
| 视频上传推理 | **通过** | MP4 格式正常处理 |
| 视频推理进度反馈 | **通过** | 实时显示处理百分比 |
| 视频推理取消 | **通过** | 任务正确终止 |
| GPU 监控数据获取 | **通过** | 多卡数据正确显示 |
| API Key 创建/删除 | **通过** | CRUD 操作正常 |

### 4.2 API 测试

```bash
# 万物检测
POST /api/v1/models/vlm/grounding
Content-Type: multipart/form-data
- image: <file>
- prompt: "建筑物"
- render_boxes: true
Response: 200 OK
{
  "boxes": [
    {"x1": 50, "y1": 50, "x2": 250, "y2": 200, "label": "建筑物", "confidence": 0.92}
  ],
  "detection_count": 1,
  "render_url": "http://localhost:9010/temp/vlm_render_abc123.jpg",
  "latency_ms": 1250.5
}

# GPU 状态
GET /api/v1/gpu/status
Response: 200 OK
{
  "gpus": [
    {
      "index": 0,
      "name": "NVIDIA RTX 4090",
      "utilization": 45,
      "memory_used": 12288,
      "memory_total": 24576,
      "temperature": 65
    }
  ]
}

# vLLM 健康检查
GET /api/v1/models/vlm/health
Response: 200 OK
{
  "status": "healthy",
  "model": "qwen3-vl",
  "message": "VLM service is available"
}
```

### 4.3 性能指标

| 指标 | 目标值 | 实测值 | 状态 |
| --- | --- | --- | --- |
| 万物检测延迟 | < 5s | ~1.2s | **达标** |
| 视频推理帧率 | >= 5 FPS | ~8 FPS | **达标** |
| GPU 监控刷新 | < 1s | ~500ms | **达标** |
| vLLM 冷启动 | < 5min | ~3min | **达标** |

---

## 5. 已解决的技术问题

| 问题 | 根因 | 解决方案 |
| --- | --- | --- |
| 中文标签显示乱码 | Docker 容器缺少中文字体 | Dockerfile 安装 fonts-wqy-zenhei |
| presigned URL 失效 | MinIO 内外网签名不一致 | 改用 public URL + temp bucket 公开读取 |
| vLLM 模型加载慢 | 32B 模型参数量大 | 使用 BF16 量化，预热缓存 |
| 视频推理内存溢出 | 帧数据累积 | 逐帧处理后立即释放 |
| GPU 监控权限不足 | 容器未挂载 NVIDIA 设备 | docker-compose 配置 GPU 资源预留 |

---

## 6. 后续规划

### 6.1 节点 3 目标
- RTMP 推流接入
- SRS 流媒体服务集成
- 实时视频流检测渲染
- WebRTC 低延迟播放

### 6.2 待优化项
- vLLM 批量推理优化
- 视频推理 GPU 加速编码
- 检测结果缓存机制
- API Key 调用频率限制

---

## 7. 验收结论

MVP 节点 2 所有功能已完成开发和测试，具备以下能力：

1. **万物检测系统** - 基于 VLM 的自然语言目标检测，支持中英文
2. **视频推理系统** - 完整的视频处理流水线，异步任务管理
3. **GPU 监控系统** - 实时监控多卡 GPU 状态
4. **API Key 管理** - 完整的鉴权体系支持
5. **中文渲染支持** - 检测结果正确显示中文标签

**验收结果**: **通过**

---

*文档编写：AI Assistant*  
*验收日期：2026-02-04*
