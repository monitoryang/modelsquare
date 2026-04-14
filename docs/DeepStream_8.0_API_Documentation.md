# NVIDIA DeepStream 8.0 API 文档

> 文档来源: https://docs.nvidia.com/metropolis/deepstream/8.0/
> 生成日期: 2026-04-08

---

## 目录

1. [API文档入口](#1-api文档入口)
2. [Service Maker Python API](#2-service-maker-python-api)
3. [GXF Core C++ APIs](#3-gxf-core-c-apis)
4. [GXF App C++ APIs](#4-gxf-app-c-apis)
5. [GXF App Python APIs](#5-gxf-app-python-apis)
6. [GXF Component Interfaces](#6-gxf-component-interfaces)
7. [GStreamer插件API](#7-gstreamer插件api)

---

## 1. API文档入口

DeepStream 8.0提供以下主要API参考文档：

| API类型 | 位置 |
|---------|------|
| DeepStream SDK API参考文档 | `../sdk-api/index.html` |
| Python API文档 | `../python-api/index.html` |

---

## 2. Service Maker Python API

### 2.1 Pipeline和Flow基础

Pipeline由多个处理节点链接组成，用于处理或操作数据流。

```python
from pyservicemaker import Pipeline
pipeline = Pipeline("sample-pipeline")
```

每次调用Flow方法时，会将上一个流的预期输出流作为当前流的输入。

### 2.2 简单视频播放器

```python
from pyservicemaker import Pipeline, Flow

pipeline = Pipeline("playback")
video_file = "/opt/nvidia/deepstream/deepstream/samples/streams/sample_1080p_h264.mp4"
Flow(pipeline).capture([video_file]).render()()
```

或使用显式启动/等待：

```python
Flow(pipeline).capture([video_file]).render()
pipeline.start()
pipeline.wait()
```

### 2.3 目标检测应用

```python
from pyservicemaker import Pipeline, Flow

pipeline = Pipeline("detector")
infer_config = "/opt/nvidia/deepstream/deepstream/samples/configs/deepstream-app/config_infer_primary.yml"
video_file = "/opt/nvidia/deepstream/deepstream/samples/streams/sample_1080p_h264.mp4"
Flow(pipeline).batch_capture([video_file]).infer(infer_config).render()()
```

### 2.4 自定义Probe用于推理结果

```python
from pyservicemaker import Pipeline, Flow, Probe, BatchMetadataOperator
import torch

class TensorOutput(BatchMetadataOperator):
    def handle_metadata(self, batch_meta):
        for frame_meta in batch_meta.frame_items:
            for user_meta in frame_meta.tensor_items:
                for n, tensor in user_meta.as_tensor_output().get_layers().items():
                    torch_tensor = torch.utils.dlpack.from_dlpack(tensor.clone())

pipeline = Pipeline("detector")
probe = Probe('tensor_retriver', TensorOutput())
Flow(pipeline).batch_capture([video_file]).infer(infer_config, output_tensor_meta=True).attach(probe).render()()
```

### 2.5 Buffer和Tensor

#### BufferProvider

用于生成缓冲区的接口：

```python
from pyservicemaker import BufferProvider, Buffer

class MyBufferProvider(BufferProvider):
    def generate(self, size):
        data = [128]*(self.width*self.height*3)
        return Buffer() if self.count == self.expected else Buffer(data)
```

使用inject flow：

```python
Flow(Pipeline("playback")).inject([MyBufferProvider(640, 480)]).render()()
```

#### BufferRetriever

用于消费缓冲区的接口：

```python
from pyservicemaker import BufferRetriever

class MyBufferRetriever(BufferRetriever):
    def consume(self, buffer):
        tensor = buffer.extract(0)
        return 1
```

使用retrieve flow：

```python
Flow(Pipeline("retrieve")).capture([video_file]).retrieve(MyBufferRetriever())()
```

#### Tensor

Tensor是深度学习领域广泛使用的多维数组。

PyTorch转换：

```python
torch_tensor = torch.utils.dlpack.from_dlpack(tensor.clone())
```

从PyTorch tensor创建buffer：

```python
from pyservicemaker import BufferProvider, ColorFormat, as_tensor

class MyBufferProvider(BufferProvider):
    def generate(self, size):
        torch_tensor = torch.load('tensor_data.pt')
        ds_tensor = as_tensor(torch_tensor, "HWC")
        return ds_tensor.wrap(ColorFormat.RGB)
```

---

## 3. GXF Core C++ APIs

### 3.1 Expected

模板类型 `nvidia::gxf::Expected<T>` 表示"包含类型T的结果或gxf_result_t错误代码的值"。

关键函数：
- `has_value()` - 检查是否有值
- `value()` - 获取值
- `error()` - 获取错误
- `ForwardError()` - 转发错误
- `ToResultCode()` - 转换为结果码
- `ExpectedOrCode()` - 获取Expected或Code

### 3.2 Component

所有GXF组件的基类，包含纯虚方法：

- `initialize()` - 用于启动组件生命周期，应替代构造函数使用
- `deinitialize()` - 用于结束组件生命周期
- `registerInterface()` - 用于注册组件的所有参数

参数访问方法：
- `getParameter()` - 获取参数
- `setParameter()` - 设置参数
- `parseParameter()` - 解析参数

### 3.3 Entity

Entity拥有多个定义其功能的组件。

静态方法：
- `New()` - 创建引用计数为1的新实体
- `Own()` - 获取所有权而不增加引用计数
- `Shared()` - 共享所有权，增加引用计数

实例方法：
- `add()` - 添加组件
- `get()` - 获取组件
- `findAll()` - 查找所有组件
- `remove()` - 移除组件
- `activate()` - 激活实体
- `deactivate()` - 停用实体
- `clone()` - 克隆实体

### 3.4 Handle

两个类：
- **UntypedHandle** - 基类，用于在不指定类型的情况下访问组件
- **Handle<T>** - 模板类，派生自UntypedHandle，提供对特定类型组件的访问

特殊值：
- `Null()` - 空句柄
- `Unspecified()` - 唯一句柄，表示将在未来创建的组件

### 3.5 Parameters

`Parameter<T>` 类提供"类型安全且方便的方式来管理组件属性"。

通过 `Registrar` 类进行注册，支持多个重载的 `parameter()` 方法，支持key、headline、description、default values和flags。

---

## 4. GXF App C++ APIs

### 4.1 Arg

**`struct nvidia::gxf::ArgInfo`** - 保存Arg的类型信息
- `gxf_parameter_type_t type` - Arg的类型
- `std::string type_name` - Arg类型的名称
- `int32_t rank` - Arg的秩
- `std::array<int32_t, ParameterInfo<int32_t>::kMaxRank> shape` - Arg的形状

**`struct nvidia::gxf::ArgOverride`** - 用于覆盖各种Arg类型的ArgInfo的模板结构

**`class nvidia::gxf::Arg`** - "参数接口，用于从应用层配置GXF组件中的参数。支持gxf_parameter_type_t枚举中的所有参数类型。"

构造函数：
- `Arg(const std::string &key)` - 使用给定key构造
- `Arg(const std::string &key, const T &value)` - 使用key和value构造
- `Arg(const std::string &key, const Handle<T> &value)` - 使用组件句柄构造

方法：
- `as()` - 转换为特定类型
- `handle_uid()` - 获取句柄UID
- `handle_tid()` - 获取句柄TID
- `key()` - 获取key
- `arg_type_name()` - 获取参数类型名
- `arg_info()` - 获取参数信息
- `yaml_node()` - 获取YAML节点
- `rank()` - 获取秩
- `shape()` - 获取形状
- `parameter_type()` - 获取参数类型
- `has_value()` - 检查是否有值
- `value()` - 获取值

### 4.2 Arg Parse

- `parseArgsOfType()` - 解析类型T对象的参数包
- `applyArg()` - 将Arg应用到组件
- `findArg()` - 按键和类型查找Arg

### 4.3 Application

**`class nvidia::gxf::Application`** - "表示GXF应用的类。此类提供了一种方便的方式来命令式地创建和管理GXF应用。"

关键方法：
- `compose()` - 组合应用的虚函数
- `setConfig()` - 从文件或CLI参数设置配置
- `createSegment()` - 在应用中创建段
- `loadExtensionManifest()` - 加载扩展清单
- `connect()` - 连接两个段
- `run()` - "运行图的阻塞API"
- `runAsync()` - "运行应用的非阻塞API调用"
- `interrupt()` - 停止运行中的段
- `wait()` - 等待执行完成

### 4.4 Segment

**`enum nvidia::gxf::SchedulerType`** - `kGreedy`, `kMultiThread`, `KEventBased`

**`class nvidia::gxf::Segment`** - "Segment是在单个GXF运行时上下文中创建的图实体组。"

关键方法：
- `compose()` - 组合段的虚函数
- `makeEntity()` - 创建带/不带codelet的图实体
- `makeTerm()` - 创建调度项
- `makeResource()` - 创建资源
- `setClock()` - 添加时钟组件
- `setScheduler()` - 添加调度器组件
- `connect()` - 添加实体之间的连接
- `activate()`/`deactivate()` - 控制实体激活
- `run()`/`runAsync()`/`interrupt()`/`wait()` - 执行控制

### 4.5 Graph Entity

**`class nvidia::gxf::GraphEntity`** - "管理可编程图实体的nvidia::gxf::Entity包装器。"

关键方法：
- `add()` - 创建通用组件
- `findAll()`/`get()`/`try_get()` - 组件查找
- `addCodelet()` - 添加codelet组件
- `addClock()`/`getClock()` - 时钟管理
- `addSchedulingTerm()` - 添加调度项
- `addTransmitter()`/`getTransmitter()` - 发送器管理
- `addReceiver()`/`getReceiver()` - 接收器管理
- `configTransmitter()`/`configReceiver()` - 配置队列参数
- `activate()`/`deactivate()` - 实体控制

---

## 5. GXF App Python APIs

### 5.1 Node

Graph、Entity、EntityGroup的抽象基类。关键方法：`activate()` 和 `set_params()`。

### 5.2 Graph

包装 `nvidia::gxf::Graph` 的Python类。

核心功能：
- 使用可选名称初始化
- 属性：`context`, `name`, `qualified_name`, `parent`, `aliases`, `is_subgraph`
- 方法：`add()`, `load_extensions()`, `set_severity()`, `run()`, `run_async()`, `interrupt()`, `wait()`, `destroy()`, `save()`

### 5.3 Entity

包装 `nvidia::gxf::Entity`。

特性：
- 属性：`context`, `components`, `named_components`, `eid`, `name`, `qualified_name`, `is_system_entity`
- 方法：`add()`, `activate()`, `set_params()`

### 5.4 Component

所有组件的基类。关键属性：`gxf_native_type`, `_validation_info_parameters`。方法包括 `add_to()`, `validate_params()`, `set_param()`, `get_param()`。

### 5.5 EntityGroup

将实体分组在一起，具有 `add()`, `activate()`, `set_params()` 方法。

### 5.6 ComputeEntity

自动添加调度项。`add_codelet()` 方法处理Transmitter/Receiver队列和调度项。

### 5.7 PyComputeEntity

用于Python实现的codelet。类似于ComputeEntity，但用于Python代码。

### 5.8 标准方法

- `connect()` - 连接队列组件
- `enable_job_statistics()` - 添加JobStatistics
- `set_scheduler()` / `set_clock()` - 图配置
- `Tensor` 类 - 多维数组，支持DLPack/NumPy/CUDA接口

---

## 6. GXF Component Interfaces

### 6.1 Codelet

"Codelet是允许执行自定义代码的特殊组件。"用户通过派生自 `nvidia::gxf::Codelet` 并覆盖以下方法创建自定义codelet：

- `start()` - "在启动阶段调用...是获取资源的好地方"
- `tick()` - "codelet的主要工作引擎"（纯虚）
- `stop()` - "清理任何资源"

其他方法：
- `getExecutionTimestamp()` - 获取执行时间戳
- `getExecutionTime()` - 获取执行时间
- `getDeltaTime()` - 获取增量时间
- `getExecutionCount()` - 获取执行计数
- `isFirstTick()` - 是否是第一次tick

### 6.2 Allocator

提供"内存的分配和释放"，三种存储类型：
- `kHost` - "页面锁定/固定内存"
- `kDevice` - "在设备/GPU上分配的内存"
- `kSystem` - "在堆上分配的内存"

关键方法：
- `allocate()` - 分配内存
- `free()` - 释放内存
- `is_available_abi()` - 检查是否可用
- `block_size_abi()` - 获取块大小

### 6.3 CudaAllocator

扩展Allocator，提供"流顺序内存分配器"。

添加方法：
- `allocate_async_abi()` - 异步分配
- `free_async_abi()` - 异步释放
- `get_pool_size()` - 获取池大小

### 6.4 Receiver

"用于接收实体的接口。"

关键方法：
- `receive()` - "从主阶段接收下一个实体"
- `sync()` - "将最近到达的实体移动到主阶段"
- `wait()` - "等待实体到达"
- `peekBack()` - "在特定索引处查看后台"

### 6.5 Transmitter

"用于发布实体的接口。"

关键方法：
- `publish()` - "发布给定实体"
- `sync()` - "将已发布的实体移动到主阶段"
- `pop()` - "弹出下一个实体"

### 6.6 System/Scheduler

System提供：
- `schedule()` - 调度
- `unschedule()` - 取消调度
- `runAsync()` - 异步运行
- `stop()` - 停止
- `wait()` - 等待

Scheduler扩展System，添加 `prepare_abi()` 用于"访问实体执行器"。

### 6.7 SchedulingTerm

"调度器用于确定实体中的codelet是否准备好执行。"

关键方法：
- `check()` - 检查
- `onExecute()` - 执行时
- `update_state_abi()` - 更新状态

### 6.8 Router

在实体中路由消息进出，具有：
- `addRoutes()` - 添加路由
- `removeRoutes()` - 移除路由
- `syncInbox()` - 同步收件箱
- `syncOutbox()` - 同步发件箱
- `setClock()` - 设置时钟

### 6.9 Clock

时间管理：
- `time()` - 时间（秒）
- `timestamp()` - 时间戳（纳秒）
- `sleepFor()` - 睡眠一段时间
- `sleepUntil()` - 睡眠直到某时

### 6.10 Benchmark Components

- `BenchmarkController` - "管理整个基准流程"
- `BenchmarkPublisher` - "发布缓冲的基准消息"
- `BenchmarkSink` - "记录消息到达时间戳"

---

## 7. GStreamer插件API

### 7.1 Gst-nvinfer

#### 概述

Gst-nvinfer插件使用NVIDIA TensorRT对输入数据进行推理。接受带有NvDsBatchMeta的批处理NV12/RGBA缓冲区。

预处理公式：`y = net scale factor*(x-mean)`

#### 操作模式

| 模式 | 描述 |
|------|------|
| Primary | 在全帧上操作 |
| Secondary | 对上游组件的对象进行操作 |
| Preprocessed Tensor Input | 使用Gst-nvdspreprocess的张量，跳过内部预处理 |

#### 支持的网络

- 多类目标检测
- 多标签分类
- 语义分割
- 实例分割

#### 关键配置属性

**[property] 组键：**
- `network-type`: 0=检测器, 1=分类器, 2=分割, 3=实例分割
- `batch-size`: 每批帧/对象数
- `model-engine-file`: 序列化TensorRT引擎路径
- `onnx-file`: ONNX模型路径
- `input-tensor-from-meta`: 使用元数据中的预处理张量
- `output-tensor-meta`: 将原始张量输出附加为元数据
- `cluster-mode`: 0=GroupRectangles, 1=DBSCAN, 2=NMS, 3=Hybrid, 4=无聚类

**聚类算法：**
- "GroupRectangles是OpenCV库的聚类算法，将相似大小和位置的矩形聚类"
- "DBSCAN是一种聚类算法，通过检查特定矩形是否有最少数量的邻居来识别聚类"
- "NMS是一种聚类算法，基于重叠程度(IOU)过滤重叠矩形"

#### 元数据输出

- **Primary模式：** NvDsInferTensorMeta附加到 `frame_user_meta_list`
- **Secondary模式：** 附加到 `obj_user_meta_list`
- **分割：** 类型为 `NVDSINFER_SEGMENTATION_META` 的NvDsInferSegmentationMeta

#### Gst属性

| 属性 | 类型 | 描述 |
|------|------|------|
| `config-file-path` | String | 配置文件路径名 |
| `process-mode` | Integer | 1=Primary, 2=Secondary |
| `unique-id` | Integer | 元数据标识符 (0-4,294,967,295) |
| `gpu-id` | Integer | GPU设备ID (仅dGPU) |
| `interval` | Integer | 推理之间跳过的批次数 |

#### 重要说明

- "UFF模型支持已从TRT 10.3中移除"
- DLA支持仅限于Jetson AGX Orin和Jetson Orin NX
- 二级分类器缓存：使用跟踪器ID避免对相同对象重新推理

---

### 7.2 Gst-nvtracker

#### 概述

"Gst-nvtracker插件允许DS管道使用低级跟踪器库来随时间持续跟踪检测到的对象，并分配唯一ID。"

该插件支持任何实现 `NvDsTracker` API的低级库，包括参考实现：IOU、NvSORT、NvDCF、MaskTracker和NvDeepSORT。

#### 关键能力

- **输入格式**：NV12或RGBA（转换为低级库所需的格式）
- **批处理**：在单个批次中处理来自多个流的帧
- **子批处理**：将批次拆分为并行子批次以提高资源利用率
- **杂项数据检索**：通过 `NvMOT_RetrieveMiscData` 获取过去帧数据、影子跟踪、Re-ID特征

#### Gst属性

| 属性 | 类型 | 描述 |
|------|------|------|
| `tracker-width` | Integer | 跟踪器操作的帧宽度 |
| `tracker-height` | Integer | 跟踪器操作的帧高度 |
| `ll-lib-file` | String | 低级跟踪器库路径 |
| `ll-config-file` | String | 低级库的配置文件 |
| `gpu-id` | Integer | GPU设备ID (仅dGPU) |
| `display-tracking-id` | Boolean | 在OSD上启用跟踪ID显示 |
| `compute-hw` | Integer | 计算引擎: 0=默认, 1=GPU, 2=VIC |
| `tracking-id-reset-mode` | Integer | 流事件上的ID重置行为 |
| `sub-batches` | String | 子批次配置 |
| `input-tensor-meta` | Boolean | 使用Gst-nvdspreprocess的tensor-meta |
| `tensor-meta-gie-id` | Unsigned Integer | 张量元数据GIE ID |

#### NvDsTracker API函数

1. **`NvMOT_Query`** - 查询库能力和需求
2. **`NvMOT_Init`** - 初始化跟踪上下文
3. **`NvMOT_Process`** - 处理带有检测对象的帧批次
4. **`NvMOT_RetrieveMiscData`** - 检索杂项跟踪数据
5. **`NvMOT_RemoveStreams`** - 移除流资源（可选）
6. **`NvMOT_DeInit`** - 清理上下文

#### 跟踪算法 (NvMultiObjectTracker)

| 算法 | 描述 |
|------|------|
| **IOU** | 基于交并比的关联；最小化跟踪器 |
| **NvSORT** | 具有级联数据关联和卡尔曼滤波器的NVIDIA增强SORT |
| **NvDeepSORT** | 具有Re-ID神经网络的深度关联度量 |
| **NvDCF** | 用于视觉跟踪的判别相关滤波器 |
| **MaskTracker** | 基于SAM2的跟踪和分割 (DS 8.0) |

#### 核心模块

- **数据关联**：使用IOU、大小相似性、Re-ID、视觉相似性将检测与目标匹配
- **目标管理**：延迟激活、影子跟踪、状态转换
- **状态估计**：卡尔曼滤波器变体（简单边界框、常规边界框、简单位置）
- **模型推理**：基于TensorRT的Re-ID、姿态估计、分割
- **目标重新关联**：基于运动和Re-ID的跟踪段匹配

#### 配置段

- `BaseConfig` - 基本参数
- `TargetManagement` - 目标生命周期设置
- `TrajectoryManagement` - 重新关联参数
- `DataAssociator` - 匹配算法设置
- `StateEstimator` - 卡尔曼滤波器配置
- `ReID` / `Object Re-ID` - 重新识别网络
- `ObjectModelProjection` - SV3DT相机和模型信息
- `PoseEstimator` - 2D/3D姿态估计
- `Model Inference` - TensorRT推理设置

#### 元数据输出

- `tracker_confidence` - 跟踪器置信度（仅NvDCF；其他默认为1.0）
- `mask_params` - 分割掩码（MaskTracker）
- `detector_bbox_info` - 原始检测边界框
- 用户元数据：Re-ID特征、过去帧数据、终止的跟踪、3D边界框

---

### 7.3 Gst-nvstreammux (New)

#### 概述

Gst-nvstreammux插件从多个输入源形成帧批次。"将源连接到nvstreammux（muxer）时，必须使用 `gst_element_get_request_pad()` 和pad模板 `sink_%u` 从muxer请求新pad。"muxer支持视频（NV12/RGBA）和音频（单声道S16LE/F32LE）缓冲区。

#### 关键特性

| 特性 | 版本 |
|------|------|
| 具有单独mux配置文件中的config-keys的新streammux | DS 5.0 |
| 缓冲区时间戳同步 | DS 6.0 |
| GstMeta和NvDsMeta复制支持 | DS 6.1 |
| 级联nvstreammux使用 | DS 6.1 |
| 运行时配置文件更改 | DS 6.1 |
| 延迟测量支持 | DS 6.1 |

#### Gst属性

| 属性 | 类型 | 描述 |
|------|------|------|
| batch-size | Integer (0 to 4,294,967,295) | 批次中的最大帧数 |
| batched-push-timeout | Signed integer (-1 to 2,147,483,647) | 超时时间（微秒） |
| num-surfaces-per-frame | Integer | 每帧最大表面数 |
| config-file-path | String | 配置文件路径 |
| sync-inputs | Boolean (0 or 1) | 强制时间戳同步 |
| max-latency | Integer | 最大上游延迟（纳秒） |
| frame-duration | Unsigned Integer64 | 帧持续时间（毫秒） |
| attach-sys-ts | Boolean | 将系统时间戳附加为NTP |
| drop-pipeline-eos | Boolean | 控制EOS传播 |

#### Mux配置属性

**[property] 组：**
- `algorithm-type`: 1=轮询（默认）
- `batch-size`: 期望的批次大小
- `overall-max-fps-n/d`: 最大输出帧率（默认：120/1）
- `overall-min-fps-n/d`: 最小输出帧率（默认：5/1）
- `max-same-source-frames`: 每批次每源最大帧数（默认：1）
- `adaptive-batching`: 启用动态批次大小（默认：1）
- `max-fps-control`: 控制最大帧率（默认：0）

**[source-config-N] 组：**
- `max-fps-n/d`, `min-fps-n/d`, `priority`, `max-num-frames-per-batch`（已弃用）

#### 重要说明

- "新的nvstreammux不会将批处理缓冲区缩放到单一分辨率"
- "批次可以包含来自不同流的具有不同分辨率的缓冲区"
- 使用以下命令启用：`export USE_NEW_NVSTREAMMUX=yes`
- 对于级联muxing：在下游实例上设置 `adaptive-batching=0`

#### 元数据传播

在nvstreammux之前附加的GstMeta被复制到：
1. 批处理缓冲区的NvDsBatchMeta→NvDsFrameMeta→user_meta_list上的NvDsUserMeta
2. 在nvstreamdemux之后作为解复用输出的GstMeta直接复制

API函数：`nvds_copy_gst_meta_to_frame_meta()`, `nvds_copy_gst_meta_to_audio_frame_meta()`

---

### 7.4 Gst-nvdspreprocess

#### 核心功能

该插件提供"用于在输入流上进行预处理的自定义库接口"，有两种主要模式：
- **PGIE模式** (`process-on-frame=1`): 在ROI/帧上进行主推理预处理
- **SGIE模式** (`process-on-frame=0`): 在检测到的对象上进行二级推理预处理

#### 关键配置组

##### [property] 组

| 键 | 描述 |
|-----|------|
| `enable` | 启用插件或直通模式 |
| `unique-id` | 元数据标识符 (0-4,294,967,295) |
| `gpu-id` | GPU设备ID (仅dGPU) |
| `process-on-frame` | 模式: 1=PGIE, 0=SGIE |
| `target-unique-ids` | 用于张量准备的分号分隔的GIE ID |
| `operate-on-gie-id` | 用于元数据预处理的源GIE |
| `network-input-order` | 0=NCHW, 1=NHWC, 2=CUSTOM |
| `network-input-shape` | 张量形状 (例如 `60;3;368;640`) |
| `processing-width/height` | ROI缩放尺寸 |
| `custom-lib-path` | .so自定义库路径 |
| `custom-tensor-preparation-function` | 张量准备函数名称 |

##### [group-<id>] 组

| 键 | 描述 |
|-----|------|
| `src-ids` | 此组的源ID |
| `custom-input-transformation-function` | 自定义转换函数 |
| `process-on-roi` | 启用ROI与全帧处理 |
| `roi-params-src-<id>` | ROI坐标: `left;top;width;height` |
| `operate-on-class-ids` | 按类ID过滤对象 |
| `input-object-min/max-width/height` | 对象大小过滤器 |

##### [user-configs] 组

| 键 | 描述 |
|-----|------|
| `pixel-normalization-factor` | 像素缩放因子 |
| `offsets` | 每颜色通道的均值 |
| `mean-file` | PPM格式均值数据文件 |

#### 自定义库接口

- `custom_transform`: "组转换（每组的缩放和转换功能）"
- `custom_tensor_function`: "从转换后的ROI准备原始张量"

#### 关键Gst属性

| 属性 | 类型 | 描述 |
|------|------|------|
| `config-file` | String | 配置文件路径 |
| `unique-id` | Integer | 元素元数据标识符 |
| `gpu-id` | Integer | GPU设备选择 |
| `enable` | Boolean | 插件启用/禁用 |
| `process-on-frame` | Boolean | PGIE/SGIE模式选择器 |
| `target-unique-ids` | String | 目标GIE组件ID |
| `operate-on-gie-id` | Integer | 元数据的源GIE |

---

## 相关文档链接

- [DeepStream 8.0 文档主页](https://docs.nvidia.com/metropolis/deepstream/8.0/)
- [Service Maker Python Flow API介绍](DS_service_maker_python_into_to_flow_api.html)
- [Service Maker Python Pipeline API介绍](DS_service_maker_python_into_to_pipeline_api.html)
- [Service Maker Python高级特性](DS_service_maker_python_advanced_features.html)
- [传统DeepStream应用迁移](DS_service_maker_traditional_app_migration.html)
- [GXF内部机制](graphtools-docs/docs/text/GXF_Internals.html)
- [扩展开发手册](text/Extensionmanual_toc.html)
- [DeepStream库](text/DS_Libraries.html)
- [推理构建器](text/DS_Inference_Builder.html)

---

*本文档由QoderWork自动生成*
