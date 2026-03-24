# 任务清单 - 置信度与IOU实时调整功能

- [x] 1. 新建前端 NMS 工具函数模块
  - 在 `frontend/src/utils/nms.ts` 中新建文件，实现 `applyNMS` 函数
  - `applyNMS` 接收检测框列表（每项含 `box: [x1,y1,x2,y2]`、`score: number`、`className: string` 字段）和 `iouThreshold: number` 参数
  - 内部按 `className` 分组，对每组按 `score` 降序排列，循环取最高分框加入结果集，计算其余框与该框的 IOU，丢弃 IOU > iouThreshold 的低分框
  - IOU 计算使用 `[x1, y1, x2, y2]` 坐标格式：`交集面积 / 并集面积`
  - 函数返回过滤后的检测框列表（保持与入参相同结构）
  - 确保模块可独立导入、运行
  - _需求：[FR-003, FR-005]_

- [x] 2. 修改后端视频推理低阈值输出
  - 修改 `backend/app/core/video_inference.py` 中 `process_video` 方法
  - 在 `process_video` 调用 `self.infer_frame(...)` 时，将 `conf_threshold` 和 `iou_threshold` 参数固定为极低值 `0.001`，不再使用调用方传入的用户参数值
  - 修改 `process_video_owl` 方法，在调用 `self.infer_frame_owl(...)` 时同样将 `conf_threshold` 和 `iou_threshold` 固定为 `0.001`
  - 方法签名保持不变，接口层（`inference.py`）无需改动，`VideoTaskResult` 数据结构不变
  - _需求：[FR-001]_
  - _测试：[视频推理完成后 result.json 中 frame_results 包含低分候选框（score < 0.25 的框也存在），框总量明显多于过滤后的预期值]_

- [x] 3. 修改后端实时推流低阈值输出
  - 修改 `backend/app/core/stream_inference.py` 中 `_process_frame` 方法
  - 在 OWL 推理分支中（`owl_inference_service.infer_frame` 调用），将 `conf_threshold` 和 `iou_threshold` 参数改为固定值 `0.001`，不再使用 `session.conf_threshold` / `session.iou_threshold`
  - 在 YOLO 推理分支中（`yolo_inference_service.infer` 调用），将 `conf_threshold` 和 `iou_threshold` 参数改为固定值 `0.001`
  - `StreamSession` 数据类的 `conf_threshold` / `iou_threshold` 字段保留（仅作记录，不传给推理引擎）
  - WebSocket 推送的 `detections` 结构不变，差异仅在于 `scores` 数组包含更多低分候选框
  - _需求：[FR-002]_
  - _测试：[推流推理激活后，WebSocket 接收到的 detections.scores 数组包含低分框（score < 0.25），boxes 数量多于通常过滤后结果]_

- [x] 4. 扩展 VideoPlayer 组件置信度/IOU 过滤能力
  - 修改 `frontend/src/components/VideoPlayer/index.tsx`
  - 在 `VideoPlayerProps` 接口中新增 `confThreshold?: number`（默认 `0.25`）和 `iouThreshold?: number`（默认 `0.45`）两个可选 prop
  - 在组件内部通过解构参数接收这两个 prop 并设置默认值
  - 修改 `getFilteredDetections` 函数：在现有类别过滤（`selectedClasses.has(className)`）之后，追加置信度过滤步骤（`score >= confThreshold`），对通过前两步的框调用 `applyNMS(filteredBoxes, iouThreshold)`，返回 NMS 过滤后的最终检测框列表
  - 引入 `applyNMS` 工具函数（从 `../../utils/nms` 导入）
  - 修改主播放器 `useEffect` 依赖数组：在现有 `[currentTime, selectedClasses, drawOverlay]` 基础上追加 `confThreshold`、`iouThreshold`，确保滑块变化时立即触发 canvas 重绘
  - 修改弹窗播放器 `useEffect` 依赖数组：同样追加 `confThreshold`、`iouThreshold`
  - _需求：[FR-003]_

- [x] 5. 在视频测试结果页（ModelDetail）添加参数调整滑块
  - 修改 `frontend/src/pages/ModelDetail/index.tsx`
  - 在组件中新增视频结果专用的 `videoConfThreshold` 和 `videoIouThreshold` state（初始值根据模型类型决定：OWL 模型 conf=0.1/iou=0.3，普通模型 conf=0.25/iou=0.45）
  - 在视频测试 TabPane 中，视频任务完成后（`videoResult` 不为 null 时）、`VideoPlayer` 组件上方，渲染置信度和 IOU 滑块控件（Ant Design `Slider`，范围 [0,1]，步长 0.05）
  - 将 `videoConfThreshold` 和 `videoIouThreshold` 作为 `confThreshold` / `iouThreshold` props 传入 `<VideoPlayer>` 组件
  - 视频任务进行中时，推理前的滑块（现有的 `confThreshold` / `iouThreshold` 用于提交任务）保持现有行为不变，新增的视频结果滑块仅在结果展示区域显示
  - _需求：[FR-004]_
  - _测试：[视频推理完成后出现置信度/IOU 滑块，拖动滑块后 VideoPlayer canvas 检测框立即更新，无网络请求触发]_

- [x] 6. 改造实时推流页（StreamTest）置信度/IOU 过滤与滑块解禁
  - 修改 `frontend/src/pages/ModelDetail/StreamTest.tsx`
  - 移除置信度和 IOU 两个 `Slider` 组件的 `disabled={streamSession?.status === 'active'}` 约束，使推流激活后滑块保持可操作
  - 引入 `applyNMS` 工具函数（从 `../../utils/nms` 导入）
  - 修改 `drawDetections` 函数：在遍历 `boxes` 绘制之前，先对 `result.detections` 中的全量候选框按当前 `confThreshold` 过滤（`score >= confThreshold`），再调用 `applyNMS` 执行 IOU 过滤，只对过滤后的框进行 canvas 绘制
  - 同步修改 `drawDetectionsOnModal` 函数，以相同的过滤逻辑处理弹窗中的检测框绘制
  - 在 canvas 绘制时，于左上角额外绘制实时渲染的检测框数量文字（参考 `VideoPlayer` 中 `检测: N 个` 的实现方式）
  - 统计面板中"检测数量"的 `value` 由 `latestResult?.detections?.boxes?.length || 0` 改为过滤后的实际渲染框数量
  - _需求：[FR-005]_
  - _测试：[推流激活状态下滑块可拖动，调整阈值后下一帧渲染框数量立即按新阈值变化，无请求后端]_

- [x] 7. 在个人中心历史预览弹窗（Profile）添加参数调整滑块
  - 修改 `frontend/src/pages/Profile/index.tsx`
  - 新增弹窗级别的 `previewConfThreshold` 和 `previewIouThreshold` state（初始值 conf=0.25、iou=0.45）
  - 在 `handlePreviewVideo` 函数中，每次打开预览弹窗时将两个 state 重置为默认值（或根据任务对应模型类型设置合适初始值）
  - 在视频预览 Modal 的 `VideoPlayer` 组件上方，新增置信度和 IOU 滑块控件（与 ModelDetail 风格一致）
  - 将 `previewConfThreshold` 和 `previewIouThreshold` 作为 `confThreshold` / `iouThreshold` props 传入弹窗内的 `<VideoPlayer>` 组件
  - _需求：[FR-006]_
