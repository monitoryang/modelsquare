# 模型广场需求调研（优化版）
## 项目目标
构建一个支持实时交互式推理的模型广场平台，用户可便捷地搜索、对比和测试各类AI模型，并通过视频推流实现对模型输出的低延迟实时渲染，显著区别于当前仅支持静态文件上传与事后推理的同类产品。
## 市场现状洞察
当前主流模型平台（如 Hugging Face、ModelScope 等）普遍仅支持用户上传图片或视频文件进行离线推理，缺乏对实时视频流输入的支持，无法满足需要即时反馈与可视化效果的应用场景（如直播分析、实时监控、交互式演示等）。
## 核心功能需求
1. 智能模型搜索
支持按任务类型、模型架构、性能指标、标签等多维度筛选与关键词检索。
2. 多模型横向对比
允许用户同时加载多个模型，在相同输入下并行运行，直观比较输出结果、延迟、资源占用等关键指标。
3. 在线模型测试
提供零代码交互界面，用户可直接上传样本或连接摄像头/视频流进行快速验证。
4. 视频推流接入
支持 RTMP、WebRTC 等主流推流协议，接收实时视频流作为模型输入。
5. 模型结果实时渲染
在浏览器端对模型输出（如检测框、分割掩码、姿态关键点等）进行低延迟叠加渲染，实现“所见即所得”的交互体验。
6. API 接口支持
提供标准化 RESTful/gRPC API，允许开发者通过接口直接上传图片/视频或推送流数据进行推理，便于集成到第三方系统。
## 差异化价值
本平台将填补市场在实时流式推理 + 可视化交互领域的空白，为开发者、研究人员及企业提供更高效、直观的模型评估与部署体验。

---

## MVP3 技术调研：实时流媒体与推理管道

### 1. 流媒体服务器选型：SRS vs 其他方案

| 方案 | 协议支持 | 延迟 | 资源占用 | 钩子机制 | 结论 |
| --- | --- | --- | --- | --- | --- |
| **SRS v6** | RTMP/HLS/HTTP-FLV/WebRTC | RTMP~1s，WebRTC~100ms | 低 | 完整 HTTP 钩子 | **选用** |
| Nginx-RTMP | RTMP/HLS | ~3s | 低 | 有限 | 不支持 WebRTC |
| MediaMTX | RTMP/HLS/WebRTC/SRT | ~200ms | 低 | 有 | 备选 |
| Janus | WebRTC | ~100ms | 中 | 复杂 | 仅 WebRTC |

**选用 SRS 的原因**：
- 原生 HTTP 钩子（on_publish/on_unpublish）与 FFmpeg Worker 无缝集成
- 同时支持 RTMP 推流 + HTTP-FLV/HLS 拉流，满足前端 mpegts.js 播放需求
- 配置简洁，Docker 镜像成熟（ossrs/srs:v6.0.155）
- 国内社区活跃，文档完整

### 2. 帧传输通道选型：Redis Stream vs 其他方案

| 方案 | 持久化 | 多消费者 | 背压控制 | 延迟 | 结论 |
| --- | --- | --- | --- | --- | --- |
| **Redis Stream** | 可选 | 原生支持 | maxlen 限流 | 极低 | **选用** |
| Kafka | 强 | 原生支持 | 完善 | 较低 | 运维复杂，MVP 过重 |
| RabbitMQ | 中 | 支持 | 支持 | 低 | 额外依赖 |
| 共享内存 | 否 | 受限 | 无 | 最低 | 跨容器不适用 |
| ZeroMQ | 否 | 支持 | 无 | 极低 | 无持久化 |

**Redis Stream 关键特性**：
- `xadd` + `maxlen` 自动丢弃旧帧，天然实现 LIFO 策略保证实时性
- `xread block=1000` 低延迟阻塞读取，避免忙轮询
- 与现有 Redis 实例共用，无额外基础设施
- 帧数据以 hex 编码存储，避免二进制序列化问题

### 3. 前端视频播放方案：mpegts.js vs 其他

| 方案 | 流格式 | 延迟 | 浏览器兼容 | 结论 |
| --- | --- | --- | --- | --- |
| **mpegts.js** | HTTP-FLV / MPEG-TS | ~1-2s | Chrome/Firefox/Safari | **选用** |
| hls.js | HLS (.m3u8) | ~3-10s | 全平台 | 延迟过高 |
| video.js | HLS/DASH | ~3-10s | 全平台 | 延迟过高 |
| WebRTC 原生 | WebRTC | ~100ms | 现代浏览器 | 推流端配合复杂 |
| flv.js（原版）| HTTP-FLV | ~1-2s | Chrome/Firefox | 已停维护，mpegts.js 为继任 |

**mpegts.js 优势**：
- 基于 HTTP-FLV，SRS 原生支持，无需额外配置
- 延迟约 1-2s，相比 HLS 大幅降低
- flv.js 的活跃继任者，API 兼容，支持更多格式
- 纯前端库，无服务端 WebSocket 信令依赖

### 4. OWLv2 开放词汇检测技术调研

#### 4.1 模型架构
OWLv2（Owl Vision Transformer v2）是 Google 发布的 Zero-shot 目标检测模型，基于 ViT 架构：

```
文本分支：CLIPTokenizer → 文本编码器（Transformer）→ text_embeds [N, 512]
图像分支：图像预处理（960px/1008px）→ 图像编码器（ViT）→ 
          image_class_embeds [1, P, 512] + pred_boxes [1, P, 4]
融合：余弦相似度 → logit_shift/scale 修正 → sigmoid → NMS
```

#### 4.2 部署方案对比

| 方案 | 推理延迟 | 显存 | 灵活性 | 结论 |
| --- | --- | --- | --- | --- |
| **Triton（文本ONNX + 图像TensorRT）** | ~80-110ms | ~4GB | 高 | **选用** |
| HuggingFace transformers | ~200-400ms | ~8GB | 高 | 延迟高，无法满足实时 |
| ONNX Runtime 直接调用 | ~120ms | ~5GB | 中 | 无法与 Triton 统一管理 |
| TensorRT 全模型 | ~60ms | ~3GB | 低 | 文本编码器难以 TRT 化 |

**双编码器分离部署优势**：
- 文本编码器（ONNX）：推理次数少（会话级缓存），兼容性好
- 图像编码器（TensorRT）：逐帧推理，TensorRT 加速效果显著
- 两个编码器均通过 Triton gRPC 统一管理，与 YOLO 推理共用基础设施

#### 4.3 文本嵌入 LRU 缓存策略
文本嵌入计算开销约 15-30ms，在实时推理场景中不可忽视：
- 相同文本提示词在会话期间固定不变，适合缓存
- 采用 OrderedDict 实现 LRU，最多缓存 100 条，MD5(texts+variant) 为键
- 实测缓存命中后跳过文本编码，单帧延迟从 ~110ms 降至 ~85ms

### 5. GPU 加速帧提取：NVDEC 调研

**NVDEC（NVIDIA Video Decode Engine）** 是 NVIDIA GPU 内置的硬件视频解码单元：

| 指标 | NVDEC 硬解 | CPU 软解 |
| --- | --- | --- |
| 解码 1080p@30fps CPU 占用 | ~2-5% | ~30-60% |
| 延迟 | 极低（硬件流水线） | 较低 |
| 功耗 | 低（专用硬件） | 高 |
| 支持格式 | H.264/H.265/AV1/VP9 | 所有格式 |

**FFmpeg NVDEC 命令参数说明**：
```bash
-hwaccel cuda          # 指定使用 CUDA/NVDEC 硬件加速
-hwaccel_device 0      # 指定 GPU 设备索引
# 解码后帧自动传回 CPU 内存（hwaccel_output_format 默认为 nv12，scale 滤镜会自动转换）
-vf fps=10,scale=640:480  # 软件滤镜（帧在 CPU 上处理）
-pix_fmt rgb24         # 输出 RGB24 格式（推理预处理输入）
```

**注意**：NVDEC 仅加速解码步骤，缩放/格式转换仍在 CPU 完成。如需全 GPU 处理可用 `hwdownload,format=nv12` + CUDA 滤镜，但增加复杂度，当前 640x480 规模下 CPU 转换开销可忽略。

### 6. 实时推理结果分发：Pub/Sub vs 轮询

**双模式设计原因**：

| 模式 | 延迟 | 实现复杂度 | 适用场景 |
| --- | --- | --- | --- |
| Redis Pub/Sub + WebSocket | 极低（<10ms） | 较高 | 主路径，高频结果推送 |
| Redis GET latest-result + 轮询 | 较低（取决于轮询间隔） | 低 | 降级路径，WebSocket 不可用时 |

- **主路径**：推理完成 → redis.publish → WebSocket 订阅者立即收到
- **降级路径**：推理完成 → redis.setex latest → 前端 polling GET /latest-result
- 前端优先建立 WebSocket 连接，失败时自动切换轮询模式

### 7. 当前已实现的实时推理延迟分解（内网实测）

```
RTMP 推流端 → SRS 接收：          ~100ms（RTMP 协议缓冲）
SRS → FFmpeg Hook 触发：          ~50ms（钩子通知延迟）
FFmpeg 帧提取 → Redis Stream：    ~30ms（NVDEC 解码 + 写入）
Redis Stream → 推理服务消费：     ~10ms（xread block）
Triton YOLO 推理（640x480）：     ~38-45ms（TensorRT A100）
Triton OWL 推理（960x960）：      ~80-110ms（TensorRT A100）
Redis Pub/Sub → WebSocket 下发：  ~5ms
WebSocket → 前端 Canvas 渲染：    ~16ms（一帧@60fps）
────────────────────────────────────────
YOLO 端到端总延迟（估算）：       ~250-350ms ✓
OWL 端到端总延迟（估算）：        ~400-450ms ✓
目标要求（内网）：                 ≤ 500ms    ✓
```