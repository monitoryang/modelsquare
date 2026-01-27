根据您提供的技术方案，我为您整理并编写了这份 `AGENTS.md`。这份文档旨在为参与“实时交互式模型广场平台”开发的工程师提供明确的指导和协作准则。

---

# AGENTS.md - 实时交互式模型广场平台开发指南

## 1. 项目概述 (Project Overview)

本项目旨在构建一个**低延迟、高并发**的实时模型推理与可视化平台。通过解耦流媒体处理（SRS + FFmpeg）与推理引擎（NVIDIA Triton），实现从“视频推流”到“AI 结果渲染”的全链路闭环。

* **核心目标**：端到端延迟 ms，支持 50+ 并发流。
* **核心架构**：基于微服务架构，采用 FastAPI 处理业务逻辑，Triton 负责高性能模型推理，SRS 处理实时流媒体。
* **当前阶段**：MVP (Minimum Viable Product) 开发阶段。

---

## 2. 开发规范 (Development Standards)

### 2.1 协作流程

* **分支管理**：采用 Git Flow。`main` 为稳定版本，`develop` 为日常集成，功能开发需建立 `feature/issue-id-description` 分支。
* **提交规范**：遵循 [Conventional Commits](https://www.conventionalcommits.org/)，例如 `feat: add Triton gRPC client`, `fix: resolve ffmpeg frame leak`。

### 2.2 环境一致性

* **容器化**：所有服务必须提供 `Dockerfile`。MVP 阶段统一使用 `docker-compose` 进行本地调试与集成。
* **环境隔离**：开发、测试与生产环境的配置通过 `.env` 文件隔离，严禁将敏感密钥（MinIO Secret, Database Password）硬编码在代码中。

### 2.3 接口定义

* **RESTful API**：遵循 OpenAPI 3.0 规范，统一使用 FastAPI 自动生成的 `/docs` 进行接口联调。
* **数据格式**：
* 推理结果必须包含 `timestamp_in` 和 `timestamp_out` 用于延迟计算。
* 坐标信息统一使用归一化坐标 ()，以适配不同分辨率的渲染。



---

## 3. 测试要求 (Testing Requirements)

### 3.1 单元测试

* **后端**：Pytest 覆盖率需 ，重点测试模型元数据校验逻辑与权限控制。
* **前端**：使用 Vitest 进行组件单元测试，确保 Canvas 渲染函数在边界情况（如空结果）下不崩溃。

### 3.2 集成与性能测试

* **Triton 连通性**：验证 gRPC 接口在不同 Batch Size 下的稳定性。
* **流媒体压测**：使用脚本模拟 50 路 RTMP 并发推流，监测 FFmpeg CPU 占用与 Redis Stream 堆积情况。
* **延迟测试**：



必须在内网环境下定期执行端到端延迟采样，确保均值 ms。

---

## 4. 代码风格 (Code Style)

### 4.1 后端 (Python)

* **规范**：遵循 **PEP 8**。
* **类型提示**：必须使用 `typing` 模块（Type Hints），利用 Pydantic 进行模型强类型约束。
* **Linting**：统一使用 `Ruff` 或 `Black` 进行代码格式化。

### 4.2 前端 (TypeScript/React)

* **框架**：React 18 (Hooks Only)。
* **风格**：遵循 Airbnb JavaScript Style Guide。
* **工具**：使用 ESLint + Prettier 自动修复。
* **组件化**：Canvas 绘图逻辑需抽离为独立的自定义 Hook (e.g., `useInferenceRenderer`)。

### 4.3 数据库 (SQL)

* 关键字大写，表名小写，使用下划线命名法。
* 所有模型元数据变更必须编写 `migration` 脚本。

---

## 5. 注意事项 (Notes & Precautions)

### 5.1 资源管理

* **显存溢出 (OOM)**：Triton 加载模型时需严格配置 `instance_group` 和 `max_batch_size`，防止显存被单个模型撑满。
* **帧丢弃策略**：当 Redis Stream 堆积超过 10 帧时，消费者应主动丢弃旧帧（LIFO），优先保证推理结果的实时性而非完整性。

### 5.2 安全与合规

* **数据脱敏**：MinIO 桶策略必须严格配置。除公开模型外，私有模型的推理结果图片在 10 分钟后必须从缓存中失效。
* **频率限制**：网关层必须开启 Redis 限流，防止 API Key 泄露导致的资源被非法刷用。

### 5.3 监控告警

* 开发过程中需关注 Grafana 中的“端到端延迟”仪表盘。
* 若 Triton 服务返回 503，后端业务层需具备自动重试或优雅降级机制。
### 5.4 环境配置

* 开发过程中构建镜像时看本地是否有所需要的基础镜像如果没有则进行提示需要开发人员，开发人员确认后再进行拉取。
---
