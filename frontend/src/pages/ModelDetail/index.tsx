/**
 * Model Detail Page - View model info and run inference tests
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card,
  Row,
  Col,
  Typography,
  Tag,
  Button,
  Tabs,
  Upload,
  message,
  Spin,
  Descriptions,
  Space,
  Divider,
  Alert,
  Slider,
  Statistic,
  Table,
  Progress,
  Switch,
  Popconfirm,
} from 'antd';
import {
  UploadOutlined,
  PlayCircleOutlined,
  CameraOutlined,
  ApiOutlined,
  ArrowLeftOutlined,
  HeartOutlined,
  ShareAltOutlined,
  DownloadOutlined,
  VideoCameraOutlined,
  LoadingOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  StopOutlined,
  CopyOutlined,
  CodeOutlined,
} from '@ant-design/icons';
import type { UploadFile as _UploadFile } from 'antd';
import { modelService } from '../../services';
import type { Model, InferenceResponse, DetectionResult, VideoTaskProgress, VideoTaskResult } from '../../services';
import StreamTest from './StreamTest';
import VideoPlayer from '../../components/VideoPlayer';

const { Title, Paragraph, Text } = Typography;
const { TabPane } = Tabs;

const taskTypeLabels: Record<string, string> = {
  classification: '图像分类',
  detection: '目标检测',
  segmentation: '图像分割',
  multimodal: '多模态',
  nlp: '自然语言处理',
};

interface ClassStatistics {
  name: string;
  count: number;
  color: string;
}

// API Documentation Component
const ApiDocumentation: React.FC<{ model: Model }> = ({ model }) => {
  const [copied, setCopied] = React.useState<string | null>(null);
  
  const apiBaseUrl = window.location.origin.replace(':3010', ':8020');
  const modelId = model.id;
  
  const handleCopy = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopied(key);
    setTimeout(() => setCopied(null), 2000);
  };
  
  const curlExample = `curl -X POST "${apiBaseUrl}/api/v1/openapi/models/${modelId}/detect?api_key=YOUR_API_KEY" \\
  -F "image=@/path/to/your/image.jpg" \\
  -F "conf_threshold=0.25" \\
  -F "iou_threshold=0.45"`;

  const pythonExample = `import requests

API_KEY = "YOUR_API_KEY"
MODEL_ID = "${modelId}"
API_URL = "${apiBaseUrl}/api/v1/openapi/models/{}/detect".format(MODEL_ID)

# 准备图片文件
with open("image.jpg", "rb") as f:
    files = {"image": ("image.jpg", f, "image/jpeg")}
    data = {
        "conf_threshold": 0.25,
        "iou_threshold": 0.45
    }
    params = {"api_key": API_KEY}
    
    response = requests.post(API_URL, files=files, data=data, params=params)
    
if response.status_code == 200:
    result = response.json()
    print(f"检测到 {len(result['boxes'])} 个目标")
    for i, (box, score, class_name) in enumerate(zip(
        result['boxes'], result['scores'], result['class_names']
    )):
        print(f"  {i+1}. {class_name}: {score*100:.1f}% at {box}")
else:
    print(f"Error: {response.status_code}")
    print(response.text)`;

  const responseExample = `{
  "boxes": [[x1, y1, x2, y2], ...],
  "scores": [0.95, 0.87, ...],
  "labels": [0, 1, ...],
  "class_names": ["person", "car", ...],
  "inference_time_ms": 45.2
}`;

  const visualizeExample = `curl -X POST "${apiBaseUrl}/api/v1/openapi/models/${modelId}/detect/visualize?api_key=YOUR_API_KEY" \\
  -F "image=@/path/to/your/image.jpg" \\
  -o result.jpg`;

  return (
    <div>
      <Alert
        message="API 调用说明"
        description={
          <span>
            使用 API Key 调用模型推理接口。请先在 <a href="/profile">个人中心</a> 生成 API Key。
            所有 API 请求需要在 URL 中携带 api_key 参数进行认证。
          </span>
        }
        type="info"
        showIcon
        style={{ marginBottom: 24 }}
      />
      
      <Row gutter={[16, 16]}>
        <Col span={24}>
          <Card 
            title="接口地址" 
            size="small"
            extra={
              <Button
                size="small"
                icon={<CopyOutlined />}
                onClick={() => handleCopy(`${apiBaseUrl}/api/v1/openapi/models/${modelId}/detect`, 'endpoint')}
              >
                {copied === 'endpoint' ? '已复制' : '复制'}
              </Button>
            }
          >
            <Descriptions column={1} size="small">
              <Descriptions.Item label="检测接口">
                <Text code>POST /api/v1/openapi/models/{modelId}/detect</Text>
              </Descriptions.Item>
              <Descriptions.Item label="可视化接口">
                <Text code>POST /api/v1/openapi/models/{modelId}/detect/visualize</Text>
              </Descriptions.Item>
              <Descriptions.Item label="模型信息">
                <Text code>GET /api/v1/openapi/models/{modelId}</Text>
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
        
        <Col span={24}>
          <Card title="请求参数" size="small">
            <Table
              size="small"
              pagination={false}
              dataSource={[
                { key: 'api_key', name: 'api_key', type: 'string', required: '是', location: 'Query', desc: '您的 API Key' },
                { key: 'image', name: 'image', type: 'file', required: '是', location: 'Form', desc: '图片文件 (JPG/PNG)' },
                { key: 'conf', name: 'conf_threshold', type: 'float', required: '否', location: 'Form', desc: '置信度阈值 (0-1, 默认: 0.25)' },
                { key: 'iou', name: 'iou_threshold', type: 'float', required: '否', location: 'Form', desc: 'NMS IoU 阈值 (0-1, 默认: 0.45)' },
              ]}
              columns={[
                { title: '参数名', dataIndex: 'name', key: 'name', render: (t: string) => <Text code>{t}</Text> },
                { title: '类型', dataIndex: 'type', key: 'type' },
                { title: '位置', dataIndex: 'location', key: 'location' },
                { title: '必填', dataIndex: 'required', key: 'required' },
                { title: '说明', dataIndex: 'desc', key: 'desc' },
              ]}
            />
          </Card>
        </Col>
        
        <Col span={24}>
          <Card 
            title="cURL 示例" 
            size="small"
            extra={
              <Button
                size="small"
                icon={<CopyOutlined />}
                onClick={() => handleCopy(curlExample, 'curl')}
              >
                {copied === 'curl' ? '已复制' : '复制'}
              </Button>
            }
          >
            <pre style={{ 
              background: '#1e1e1e', 
              color: '#d4d4d4',
              padding: 16, 
              borderRadius: 4,
              overflow: 'auto',
              fontSize: 13,
              lineHeight: 1.5,
            }}>
              {curlExample}
            </pre>
          </Card>
        </Col>
        
        <Col span={24}>
          <Card 
            title="Python 示例" 
            size="small"
            extra={
              <Button
                size="small"
                icon={<CopyOutlined />}
                onClick={() => handleCopy(pythonExample, 'python')}
              >
                {copied === 'python' ? '已复制' : '复制'}
              </Button>
            }
          >
            <pre style={{ 
              background: '#1e1e1e', 
              color: '#d4d4d4',
              padding: 16, 
              borderRadius: 4,
              overflow: 'auto',
              fontSize: 13,
              lineHeight: 1.5,
            }}>
              {pythonExample}
            </pre>
          </Card>
        </Col>
        
        <Col span={24}>
          <Card 
            title="响应格式" 
            size="small"
            extra={
              <Button
                size="small"
                icon={<CopyOutlined />}
                onClick={() => handleCopy(responseExample, 'response')}
              >
                {copied === 'response' ? '已复制' : '复制'}
              </Button>
            }
          >
            <pre style={{ 
              background: '#1e1e1e', 
              color: '#d4d4d4',
              padding: 16, 
              borderRadius: 4,
              overflow: 'auto',
              fontSize: 13,
              lineHeight: 1.5,
            }}>
              {responseExample}
            </pre>
            <Divider style={{ margin: '16px 0' }} />
            <Descriptions column={1} size="small">
              <Descriptions.Item label="boxes">检测框坐标列表 [[x1,y1,x2,y2], ...]</Descriptions.Item>
              <Descriptions.Item label="scores">置信度分数列表</Descriptions.Item>
              <Descriptions.Item label="labels">类别索引列表</Descriptions.Item>
              <Descriptions.Item label="class_names">类别名称列表</Descriptions.Item>
              <Descriptions.Item label="inference_time_ms">推理耗时(毫秒)</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
        
        <Col span={24}>
          <Card 
            title="可视化接口 (返回带检测框的图片)" 
            size="small"
            extra={
              <Button
                size="small"
                icon={<CopyOutlined />}
                onClick={() => handleCopy(visualizeExample, 'visualize')}
              >
                {copied === 'visualize' ? '已复制' : '复制'}
              </Button>
            }
          >
            <pre style={{ 
              background: '#1e1e1e', 
              color: '#d4d4d4',
              padding: 16, 
              borderRadius: 4,
              overflow: 'auto',
              fontSize: 13,
              lineHeight: 1.5,
            }}>
              {visualizeExample}
            </pre>
            <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
              可视化接口直接返回 JPEG 图片，可通过 -o 参数保存到文件
            </Text>
          </Card>
        </Col>
        
        {model.class_config && model.class_config.length > 0 && (
          <Col span={24}>
            <Card title="支持的检测类别" size="small">
              <Space wrap>
                {model.class_config.map((cls, index) => {
                  // Calculate contrast text color
                  const hex = cls.color.replace('#', '');
                  const r = parseInt(hex.substring(0, 2), 16) || 0;
                  const g = parseInt(hex.substring(2, 4), 16) || 0;
                  const b = parseInt(hex.substring(4, 6), 16) || 0;
                  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
                  const textColor = luminance > 0.5 ? '#000000' : '#ffffff';

                  return (
                    <Tag
                      key={index}
                      style={{
                        backgroundColor: cls.color,
                        color: textColor,
                        border: 'none'
                      }}
                    >
                      {cls.name}
                    </Tag>
                  );
                })}
              </Space>
            </Card>
          </Col>
        )}
        
        <Col span={24}>
          <Card title="错误码说明" size="small">
            <Table
              size="small"
              pagination={false}
              dataSource={[
                { key: '400', code: '400', desc: '请求参数错误 (图片格式不支持等)' },
                { key: '401', code: '401', desc: 'API Key 无效或缺失' },
                { key: '403', code: '403', desc: '账户已被禁用' },
                { key: '404', code: '404', desc: '模型不存在或不可用' },
                { key: '503', code: '503', desc: '模型服务暂不可用 (未加载到推理引擎)' },
              ]}
              columns={[
                { title: '状态码', dataIndex: 'code', key: 'code', width: 100, render: (c: string) => <Tag color="red">{c}</Tag> },
                { title: '说明', dataIndex: 'desc', key: 'desc' },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
};

const ModelDetailPage: React.FC = () => {
  const { modelId } = useParams<{ modelId: string }>();
  const navigate = useNavigate();
  const [model, setModel] = useState<Model | null>(null);
  const [loading, setLoading] = useState(true);
  const [inferring, setInferring] = useState(false);
  const [inferenceResult, setInferenceResult] = useState<InferenceResponse | null>(null);
  const [confThreshold, setConfThreshold] = useState(0.25);
  const [iouThreshold, setIouThreshold] = useState(0.45);
  const [currentImage, setCurrentImage] = useState<File | null>(null);
  const [downloading, setDownloading] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Video inference states
  const [videoUploading, setVideoUploading] = useState(false);
  const [videoUploadProgress, setVideoUploadProgress] = useState(0);
  const [videoTaskId, setVideoTaskId] = useState<string | null>(null);
  const [videoProgress, setVideoProgress] = useState<VideoTaskProgress | null>(null);
  const [videoResult, setVideoResult] = useState<VideoTaskResult | null>(null);
  const [videoDownloading, setVideoDownloading] = useState(false);
  const [uploadedVideoSize, setUploadedVideoSize] = useState<number>(0);
  const [resultVideoSize, setResultVideoSize] = useState<number>(0);
  const [backgroundMode, setBackgroundMode] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [originalVideoFile, setOriginalVideoFile] = useState<File | null>(null);
  const [videoBlob, setVideoBlob] = useState<Blob | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (modelId) {
      fetchModel();
    }
  }, [modelId]);

  const fetchModel = async () => {
    setLoading(true);
    try {
      const data = await modelService.get(modelId!);
      setModel(data);
    } catch (error) {
      message.error('获取模型信息失败');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  // Calculate class statistics from detection result
  const getClassStatistics = (): ClassStatistics[] => {
    const detectionResult = inferenceResult?.result as DetectionResult | undefined;
    if (!detectionResult?.class_names || detectionResult.class_names.length === 0) {
      return [];
    }

    const countMap: Record<string, { count: number; color: string }> = {};
    
    detectionResult.class_names.forEach((className) => {
      if (!countMap[className]) {
        const color = detectionResult.class_colors?.[className] || '#666666';
        countMap[className] = { count: 0, color };
      }
      countMap[className].count++;
    });

    return Object.entries(countMap).map(([name, { count, color }]) => ({
      name,
      count,
      color,
    })).sort((a, b) => b.count - a.count);
  };

  const handleImageUpload = async (file: File) => {
    if (!modelId) return false;

    setCurrentImage(file);
    
    // First draw the original image immediately
    drawOriginalImage(file);
    
    setInferring(true);
    try {
      const result = await modelService.inferImage(modelId, file, confThreshold, iouThreshold);
      setInferenceResult(result);
      message.success(`推理完成，耗时 ${result.latency_ms.toFixed(1)}ms`);
      
      // Draw result on canvas
      if (result && canvasRef.current) {
        drawInferenceResult(file, result);
      }
    } catch (error) {
      message.error('推理失败');
      console.error(error);
    } finally {
      setInferring(false);
    }
    return false;
  };

  const handleReInfer = async () => {
    if (!currentImage || !modelId) return;
    
    setInferring(true);
    try {
      const result = await modelService.inferImage(modelId, currentImage, confThreshold, iouThreshold);
      setInferenceResult(result);
      message.success(`推理完成，耗时 ${result.latency_ms.toFixed(1)}ms`);
      
      if (result && canvasRef.current) {
        drawInferenceResult(currentImage, result);
      }
    } catch (error) {
      message.error('推理失败');
      console.error(error);
    } finally {
      setInferring(false);
    }
  };

  const handleDownloadRender = async () => {
    if (!currentImage || !modelId) return;
    
    setDownloading(true);
    try {
      const blob = await modelService.inferImageRender(modelId, currentImage, confThreshold, iouThreshold);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `detection_result_${modelId}.png`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      message.success('图片下载成功');
    } catch (error) {
      message.error('下载失败');
      console.error(error);
    } finally {
      setDownloading(false);
    }
  };

  // Draw original image without detection boxes
  const drawOriginalImage = (file: File) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const img = new Image();
    img.onload = () => {
      const maxWidth = 800;
      const maxHeight = 600;
      let width = img.width;
      let height = img.height;
      
      if (width > maxWidth) {
        height = (maxWidth / width) * height;
        width = maxWidth;
      }
      if (height > maxHeight) {
        width = (maxHeight / height) * width;
        height = maxHeight;
      }
      
      canvas.width = width;
      canvas.height = height;
      ctx.drawImage(img, 0, 0, width, height);
    };
    img.src = URL.createObjectURL(file);
  };

  const drawInferenceResult = (file: File, result: InferenceResponse) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Load and draw the image
    const img = new Image();
    img.onload = () => {
      // Set canvas size
      const maxWidth = 800;
      const maxHeight = 600;
      let width = img.width;
      let height = img.height;
      
      if (width > maxWidth) {
        height = (maxWidth / width) * height;
        width = maxWidth;
      }
      if (height > maxHeight) {
        width = (maxHeight / height) * width;
        height = maxHeight;
      }
      
      canvas.width = width;
      canvas.height = height;
      ctx.drawImage(img, 0, 0, width, height);

      // Draw detection boxes
      const detectionResult = result.result as DetectionResult;
      if (detectionResult?.boxes && detectionResult.boxes.length > 0) {
        const scaleX = width / img.width;
        const scaleY = height / img.height;
        
        detectionResult.boxes.forEach((box: number[], index: number) => {
          const [x1, y1, x2, y2] = box;
          const className = detectionResult.class_names?.[index] || `Class ${detectionResult.labels?.[index]}`;
          const score = detectionResult.scores?.[index] || 0;
          
          // Get color from class_colors or use default
          let color = '#ff0000';
          if (detectionResult.class_colors && className) {
            color = detectionResult.class_colors[className] || color;
          }
          
          // Scale coordinates
          const sx1 = x1 * scaleX;
          const sy1 = y1 * scaleY;
          const sx2 = x2 * scaleX;
          const sy2 = y2 * scaleY;
          
          // Draw box
          ctx.strokeStyle = color;
          ctx.lineWidth = 2;
          ctx.strokeRect(sx1, sy1, sx2 - sx1, sy2 - sy1);
          
          // Draw label background
          const label = `${className}: ${(score * 100).toFixed(1)}%`;
          ctx.font = 'bold 14px Arial';
          const textMetrics = ctx.measureText(label);
          const textHeight = 18;
          const padding = 4;

          ctx.fillStyle = color;
          ctx.fillRect(
            sx1,
            sy1 - textHeight - padding,
            textMetrics.width + padding * 2,
            textHeight + padding
          );

          // Draw label text with contrast color
          const hex = color.replace('#', '');
          const r = parseInt(hex.substring(0, 2), 16) || 0;
          const g = parseInt(hex.substring(2, 4), 16) || 0;
          const b = parseInt(hex.substring(4, 6), 16) || 0;
          const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
          ctx.fillStyle = luminance > 0.5 ? '#000000' : '#ffffff';
          ctx.fillText(label, sx1 + padding, sy1 - padding - 2);
        });
      }
    };
    img.src = URL.createObjectURL(file);
  };

  // Video inference functions
  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  }, []);

  const pollVideoProgress = useCallback(async (taskId: string) => {
    if (!modelId) return;
    
    try {
      const progress = await modelService.getVideoTaskProgress(modelId, taskId);
      setVideoProgress(progress);
      
      if (progress.status === 'completed') {
        stopPolling();
        message.success('视频推理完成');
        // Fetch result
        try {
          const result = await modelService.getVideoTaskResult(modelId, taskId);
          setVideoResult(result);
          // Set video size from result if available
          if (result.render_video_size) {
            setResultVideoSize(result.render_video_size);
          }
          // If no local file, download video for playback
          if (!originalVideoFile) {
            await loadVideoForPlayback(taskId);
          }
        } catch (err) {
          console.error('Failed to get video result:', err);
        }
      } else if (progress.status === 'failed') {
        stopPolling();
        message.error(progress.error_message || '视频推理失败');
      } else if (progress.status === 'cancelled') {
        stopPolling();
        message.info('视频推理任务已取消');
      }
    } catch (err) {
      console.error('Failed to poll video progress:', err);
    }
  }, [modelId, stopPolling]);

  const startPolling = useCallback((taskId: string) => {
    stopPolling();
    // Poll every 1 second
    pollIntervalRef.current = setInterval(() => {
      pollVideoProgress(taskId);
    }, 1000);
    // Initial poll
    pollVideoProgress(taskId);
  }, [pollVideoProgress, stopPolling]);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      stopPolling();
    };
  }, [stopPolling]);

  const handleVideoUpload = async (file: File) => {
    if (!modelId) return false;
    
    // Check file size (2GB limit)
    const maxSize = 2 * 1024 * 1024 * 1024;
    if (file.size > maxSize) {
      message.error('视频文件不能超过 2GB');
      return false;
    }
    
    // Reset states
    setVideoTaskId(null);
    setVideoProgress(null);
    setVideoResult(null);
    setOriginalVideoFile(file);
    setVideoBlob(null);
    setVideoUploading(true);
    setVideoUploadProgress(0);
    setUploadedVideoSize(file.size);
    setResultVideoSize(0);
    
    try {
      const taskResponse = await modelService.inferVideo(
        modelId,
        file,
        confThreshold,
        iouThreshold,
        undefined,
        backgroundMode,
        (percent) => setVideoUploadProgress(percent)
      );
      
      setVideoTaskId(taskResponse.task_id);
      
      if (backgroundMode) {
        message.success('视频已提交后台处理，可在个人中心查看进度');
        // Reset video states for background mode
        setVideoProgress(null);
        setVideoResult(null);
      } else {
        message.success('视频上传成功，开始处理');
        // Start polling for progress
        startPolling(taskResponse.task_id);
      }
    } catch (error) {
      message.error('视频上传失败');
      console.error(error);
    } finally {
      setVideoUploading(false);
    }
    
    return false;
  };

  const handleDownloadVideo = async () => {
    if (!modelId || !videoTaskId) return;
    
    setVideoDownloading(true);
    try {
      const blob = await modelService.downloadVideoResult(modelId, videoTaskId);
      setResultVideoSize(blob.size);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `detection_result_${videoTaskId}.mp4`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      message.success('视频下载成功');
    } catch (error) {
      message.error('视频下载失败');
      console.error(error);
    } finally {
      setVideoDownloading(false);
    }
  };

  // Download video for playback (try original first, fall back to rendered)
  const loadVideoForPlayback = async (taskId: string) => {
    if (!modelId) return;
    try {
      // Try original video first
      const blob = await modelService.downloadOriginalVideo(modelId, taskId);
      setVideoBlob(blob);
    } catch {
      try {
        // Fall back to rendered video
        const blob = await modelService.downloadVideoResult(modelId, taskId);
        setVideoBlob(blob);
      } catch (error) {
        console.error('Failed to load video for playback:', error);
      }
    }
  };

  const handleCancelVideoTask = async () => {
    if (!videoTaskId) return;
    
    setCancelling(true);
    try {
      await modelService.cancelVideoTask(videoTaskId);
      stopPolling();
      message.success('任务已取消');
      // Update local state
      if (videoProgress) {
        setVideoProgress({
          ...videoProgress,
          status: 'cancelled',
          current_stage: 'cancelled',
        });
      }
    } catch (error) {
      message.error('取消任务失败');
      console.error(error);
    } finally {
      setCancelling(false);
    }
  };

  // Helper function to format file size
  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const getVideoStatusIcon = () => {
    if (!videoProgress) return null;
    
    switch (videoProgress.status) {
      case 'pending':
        return <LoadingOutlined style={{ color: '#1890ff' }} />;
      case 'processing':
      case 'rendering':
        return <LoadingOutlined style={{ color: '#1890ff' }} spin />;
      case 'completed':
        return <CheckCircleOutlined style={{ color: '#52c41a' }} />;
      case 'failed':
        return <CloseCircleOutlined style={{ color: '#ff4d4f' }} />;
      case 'cancelled':
        return <StopOutlined style={{ color: '#faad14' }} />;
      default:
        return null;
    }
  };

  const getVideoStageLabel = (stage: string) => {
    const labels: Record<string, string> = {
      pending: '等待处理',
      analyzing: '分析视频',
      decoding: '解码视频帧',
      inferring: '推理中',
      rendering: '渲染结果',
      uploading: '上传结果',
      completed: '已完成',
      failed: '失败',
      cancelled: '已取消',
    };
    return labels[stage] || stage;
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 100 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!model) {
    return (
      <Alert
        type="error"
        message="模型不存在"
        description="请检查模型ID是否正确"
        showIcon
      />
    );
  }

  const detectionResult = inferenceResult?.result as DetectionResult | undefined;

  return (
    <div>
      {/* Header */}
      <Button
        icon={<ArrowLeftOutlined />}
        onClick={() => navigate(-1)}
        style={{ marginBottom: 16 }}
      >
        返回
      </Button>

      <Row gutter={24}>
        {/* Left: Model Info */}
        <Col xs={24} lg={8}>
          <Card>
            <Title level={3}>{model.name}</Title>
            <Space style={{ marginBottom: 16 }}>
              <Tag color="blue">{taskTypeLabels[model.task_type]}</Tag>
              <Tag color="green">{model.framework.toUpperCase()}</Tag>
              <Tag>v{model.version}</Tag>
            </Space>
            <Paragraph>{model.description || '暂无描述'}</Paragraph>
            
            <Divider />
            
            <Descriptions column={1} size="small">
              <Descriptions.Item label="网络类型">
                {model.network_type}
              </Descriptions.Item>
              <Descriptions.Item label="创建时间">
                {new Date(model.created_at).toLocaleDateString()}
              </Descriptions.Item>
              <Descriptions.Item label="更新时间">
                {new Date(model.updated_at).toLocaleDateString()}
              </Descriptions.Item>
              <Descriptions.Item label="下载次数">
                {model.download_count}
              </Descriptions.Item>
            </Descriptions>

            <Divider />

            <Space>
              <Button icon={<HeartOutlined />}>收藏</Button>
              <Button icon={<ShareAltOutlined />}>分享</Button>
              <Button icon={<ApiOutlined />}>API 文档</Button>
            </Space>
          </Card>

          {/* Class Config */}
          {model.class_config && model.class_config.length > 0 && (
            <Card title="检测类别" size="small" style={{ marginTop: 16 }}>
              <Space wrap>
                {model.class_config.map((cls, index) => {
                  // Calculate contrast text color
                  const hex = cls.color.replace('#', '');
                  const r = parseInt(hex.substring(0, 2), 16) || 0;
                  const g = parseInt(hex.substring(2, 4), 16) || 0;
                  const b = parseInt(hex.substring(4, 6), 16) || 0;
                  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
                  const textColor = luminance > 0.5 ? '#000000' : '#ffffff';

                  return (
                    <Tag
                      key={index}
                      style={{
                        backgroundColor: cls.color,
                        color: textColor,
                        border: 'none'
                      }}
                    >
                      {cls.name}
                    </Tag>
                  );
                })}
              </Space>
            </Card>
          )}

          {/* Input/Output Spec */}
          {(model.input_spec || model.output_spec) && (
            <Card title="输入/输出规范" style={{ marginTop: 16 }}>
              {model.input_spec && (
                <>
                  <Text strong>输入规范:</Text>
                  <pre style={{ background: '#f5f5f5', padding: 8, borderRadius: 4 }}>
                    {JSON.stringify(model.input_spec, null, 2)}
                  </pre>
                </>
              )}
              {model.output_spec && (
                <>
                  <Text strong>输出规范:</Text>
                  <pre style={{ background: '#f5f5f5', padding: 8, borderRadius: 4 }}>
                    {JSON.stringify(model.output_spec, null, 2)}
                  </pre>
                </>
              )}
            </Card>
          )}
        </Col>

        {/* Right: Test Area */}
        <Col xs={24} lg={16}>
          <Card title="在线测试">
            <Tabs defaultActiveKey="image">
              <TabPane
                tab={<><UploadOutlined /> 图片测试</>}
                key="image"
              >
                {/* Inference Parameters */}
                <Card size="small" style={{ marginBottom: 16 }}>
                  <Row gutter={24}>
                    <Col span={12}>
                      <Text>置信度阈值: {confThreshold.toFixed(2)}</Text>
                      <Slider
                        min={0}
                        max={1}
                        step={0.05}
                        value={confThreshold}
                        onChange={setConfThreshold}
                      />
                    </Col>
                    <Col span={12}>
                      <Text>IoU 阈值: {iouThreshold.toFixed(2)}</Text>
                      <Slider
                        min={0}
                        max={1}
                        step={0.05}
                        value={iouThreshold}
                        onChange={setIouThreshold}
                      />
                    </Col>
                  </Row>
                  {currentImage && (
                    <Space style={{ marginTop: 8 }}>
                      <Button 
                        type="primary" 
                        onClick={handleReInfer} 
                        loading={inferring}
                      >
                        重新推理
                      </Button>
                      {inferenceResult && !inferenceResult.result.status && (
                        <Button
                          icon={<DownloadOutlined />}
                          onClick={handleDownloadRender}
                          loading={downloading}
                        >
                          下载结果图
                        </Button>
                      )}
                    </Space>
                  )}
                </Card>

                <Row gutter={16}>
                  <Col span={8}>
                    <Upload.Dragger
                      accept="image/jpeg,image/png"
                      beforeUpload={handleImageUpload}
                      showUploadList={false}
                      disabled={inferring}
                    >
                      <p className="ant-upload-drag-icon">
                        <UploadOutlined />
                      </p>
                      <p className="ant-upload-text">点击或拖拽图片上传</p>
                      <p className="ant-upload-hint">支持 JPG、PNG 格式</p>
                    </Upload.Dragger>
                    
                    {/* Statistics */}
                    {inferenceResult && (
                      <Card size="small" style={{ marginTop: 16 }}>
                        <Statistic 
                          title="检测数量" 
                          value={detectionResult?.detection_count || 0} 
                        />
                        <Statistic 
                          title="推理延迟" 
                          value={inferenceResult.latency_ms.toFixed(1)} 
                          suffix="ms"
                          style={{ marginTop: 8 }}
                        />
                        {detectionResult?.image_size && (
                          <Descriptions size="small" column={1} style={{ marginTop: 8 }}>
                            <Descriptions.Item label="原图尺寸">
                              {detectionResult.image_size.width} x {detectionResult.image_size.height}
                            </Descriptions.Item>
                            {detectionResult.input_size && (
                              <Descriptions.Item label="输入尺寸">
                                {detectionResult.input_size.width} x {detectionResult.input_size.height}
                              </Descriptions.Item>
                            )}
                            {detectionResult.inference_device && (
                              <Descriptions.Item label="推理设备">
                                {detectionResult.inference_device}
                              </Descriptions.Item>
                            )}
                          </Descriptions>
                        )}
                      </Card>
                    )}
                  </Col>
                  <Col span={16}>
                    <div
                      style={{
                        border: '1px solid #d9d9d9',
                        borderRadius: 4,
                        minHeight: 400,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        background: '#141414',
                        overflow: 'hidden',
                        position: 'relative',
                      }}
                    >
                      <canvas
                        ref={canvasRef}
                        style={{ maxWidth: '100%', maxHeight: '100%' }}
                      />
                      {inferring && (
                        <div
                          style={{
                            position: 'absolute',
                            top: 0,
                            left: 0,
                            right: 0,
                            bottom: 0,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            background: 'rgba(0, 0, 0, 0.5)',
                          }}
                        >
                          <Spin tip="推理中..." />
                        </div>
                      )}
                    </div>
                  </Col>
                </Row>
                
                {inferenceResult && (
                  <Card
                    title="检测结果统计"
                    size="small"
                    style={{ marginTop: 16 }}
                  >
                    {(() => {
                      const detResult = inferenceResult.result as DetectionResult;
                      // Check if model is not deployed or triton unavailable
                      if (detResult?.status === 'model_not_deployed' || detResult?.status === 'triton_unavailable') {
                        return (
                          <Alert
                            type="warning"
                            message={detResult.status === 'model_not_deployed' ? '模型未部署' : 'Triton 服务不可用'}
                            description={detResult.message}
                            showIcon
                          />
                        );
                      }
                      
                      const stats = getClassStatistics();
                      if (stats.length === 0) {
                        return <Text type="secondary">未检测到目标</Text>;
                      }
                      
                      return (
                        <Table
                          dataSource={stats}
                          rowKey="name"
                          size="small"
                          pagination={false}
                          columns={[
                            {
                              title: '类别',
                              dataIndex: 'name',
                              key: 'name',
                              render: (name: string, record: ClassStatistics) => (
                                <Space>
                                  <div 
                                    style={{ 
                                      width: 16, 
                                      height: 16, 
                                      backgroundColor: record.color,
                                      borderRadius: 2,
                                    }} 
                                  />
                                  <span>{name}</span>
                                </Space>
                              ),
                            },
                            {
                              title: '检测数量',
                              dataIndex: 'count',
                              key: 'count',
                              width: 100,
                              align: 'center' as const,
                              render: (count: number) => (
                                <Tag color="blue">{count}</Tag>
                              ),
                            },
                          ]}
                          summary={() => (
                            <Table.Summary fixed>
                              <Table.Summary.Row>
                                <Table.Summary.Cell index={0}>
                                  <Text strong>总计</Text>
                                </Table.Summary.Cell>
                                <Table.Summary.Cell index={1} align="center">
                                  <Tag color="green">{detResult?.detection_count || 0}</Tag>
                                </Table.Summary.Cell>
                              </Table.Summary.Row>
                            </Table.Summary>
                          )}
                        />
                      );
                    })()}
                  </Card>
                )}
              </TabPane>

              <TabPane
                tab={<><PlayCircleOutlined /> 视频测试</>}
                key="video"
              >
                {/* Video Inference Parameters */}
                <Card size="small" style={{ marginBottom: 16 }}>
                  <Row gutter={24} align="middle">
                    <Col span={10}>
                      <Text>置信度阈值: {confThreshold.toFixed(2)}</Text>
                      <Slider
                        min={0}
                        max={1}
                        step={0.05}
                        value={confThreshold}
                        onChange={setConfThreshold}
                        disabled={videoUploading || (videoProgress?.status === 'processing' || videoProgress?.status === 'rendering')}
                      />
                    </Col>
                    <Col span={10}>
                      <Text>IoU 阈值: {iouThreshold.toFixed(2)}</Text>
                      <Slider
                        min={0}
                        max={1}
                        step={0.05}
                        value={iouThreshold}
                        onChange={setIouThreshold}
                        disabled={videoUploading || (videoProgress?.status === 'processing' || videoProgress?.status === 'rendering')}
                      />
                    </Col>
                    <Col span={4}>
                      <Space direction="vertical" size="small">
                        <Text>后台推理</Text>
                        <Switch
                          checked={backgroundMode}
                          onChange={setBackgroundMode}
                          disabled={videoUploading || (videoProgress?.status === 'processing' || videoProgress?.status === 'rendering')}
                        />
                      </Space>
                    </Col>
                  </Row>
                  {backgroundMode && (
                    <Alert
                      type="info"
                      message="后台推理模式"
                      description="视频上传后将在后台处理，您可以在个人中心的测试记录中查看进度和下载结果。"
                      showIcon
                      style={{ marginTop: 12 }}
                    />
                  )}
                </Card>

                <Row gutter={16}>
                  <Col span={8}>
                    <Upload.Dragger
                      accept="video/mp4,video/quicktime"
                      beforeUpload={handleVideoUpload}
                      showUploadList={false}
                      disabled={videoUploading || (videoProgress?.status === 'processing' || videoProgress?.status === 'rendering')}
                    >
                      <p className="ant-upload-drag-icon">
                        <VideoCameraOutlined />
                      </p>
                      <p className="ant-upload-text">点击或拖拽视频上传</p>
                      <p className="ant-upload-hint">支持 MP4 格式，最长 10 分钟，最大 2GB</p>
                    </Upload.Dragger>
                  </Col>

                  <Col span={16}>
                    {/* Initial State - No video uploaded */}
                    {!videoResult && !videoProgress && !videoUploading && (
                      <div
                        style={{
                          border: '1px dashed #d9d9d9',
                          borderRadius: 4,
                          minHeight: 300,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          background: '#fafafa',
                        }}
                      >
                        <Text type="secondary">上传视频后将显示推理结果</Text>
                      </div>
                    )}

                    {/* Processing State - Show progress info in card */}
                    {(videoUploading || (videoProgress && videoProgress.status !== 'completed')) && (
                      <Card style={{ minHeight: 300 }}>
                        <Space direction="vertical" style={{ width: '100%' }} size="middle">
                          {/* Upload Progress */}
                          {videoUploading && (
                            <>
                              <Space>
                                <LoadingOutlined spin style={{ color: '#1890ff' }} />
                                <Text strong style={{ fontSize: 16 }}>正在上传视频...</Text>
                              </Space>
                              <Progress percent={videoUploadProgress} status="active" />
                              {uploadedVideoSize > 0 && (
                                <Text type="secondary">
                                  视频大小: {formatFileSize(uploadedVideoSize)}
                                </Text>
                              )}
                            </>
                          )}

                          {/* Processing Progress */}
                          {videoProgress && !videoUploading && (
                            <>
                              <Space>
                                {getVideoStatusIcon()}
                                <Text strong style={{ fontSize: 16 }}>{getVideoStageLabel(videoProgress.current_stage)}</Text>
                              </Space>
                              
                              <Progress 
                                percent={Math.round(videoProgress.progress_percent)} 
                                status={videoProgress.status === 'failed' ? 'exception' : 'active'}
                              />
                              
                              {videoProgress.total_frames > 0 && (
                                <Row gutter={[16, 8]}>
                                  <Col span={12}>
                                    <Statistic 
                                      title="处理帧数" 
                                      value={videoProgress.processed_frames} 
                                      suffix={`/ ${videoProgress.total_frames}`}
                                    />
                                  </Col>
                                  {videoProgress.fps && (
                                    <Col span={12}>
                                      <Statistic 
                                        title="帧率" 
                                        value={videoProgress.fps.toFixed(1)} 
                                        suffix="FPS"
                                      />
                                    </Col>
                                  )}
                                  {videoProgress.duration_seconds && (
                                    <Col span={12}>
                                      <Statistic 
                                        title="时长" 
                                        value={videoProgress.duration_seconds.toFixed(1)} 
                                        suffix="秒"
                                      />
                                    </Col>
                                  )}
                                  {uploadedVideoSize > 0 && (
                                    <Col span={12}>
                                      <Statistic 
                                        title="原视频大小" 
                                        value={formatFileSize(uploadedVideoSize)} 
                                      />
                                    </Col>
                                  )}
                                </Row>
                              )}
                              
                              {videoProgress.error_message && (
                                <Alert
                                  type="error"
                                  message={videoProgress.error_message}
                                  showIcon
                                />
                              )}
                              
                              {/* Cancel button for processing tasks */}
                              {videoProgress.status !== 'cancelled' && videoProgress.status !== 'failed' && (
                                <div style={{ marginTop: 16 }}>
                                  <Popconfirm
                                    title="确定要取消此任务吗？"
                                    description="取消后任务将停止处理，已处理的数据将丢失。"
                                    onConfirm={handleCancelVideoTask}
                                    okText="确定"
                                    cancelText="取消"
                                  >
                                    <Button
                                      danger
                                      icon={<StopOutlined />}
                                      loading={cancelling}
                                    >
                                      取消任务
                                    </Button>
                                  </Popconfirm>
                                </div>
                              )}
                            </>
                          )}
                        </Space>
                      </Card>
                    )}

                    {/* Completed State - Show Video Player with Detection Overlay */}
                    {videoProgress?.status === 'completed' && (
                      <>
                        {/* Video Player - Use original file or downloaded blob */}
                        {(originalVideoFile || videoBlob) && videoResult && (
                          <VideoPlayer
                            videoFile={originalVideoFile || undefined}
                            videoBlob={!originalVideoFile ? videoBlob || undefined : undefined}
                            result={videoResult}
                            classColors={videoResult.class_colors || {}}
                          />
                        )}

                        {/* Download Button */}
                        <Card size="small" style={{ marginTop: 16 }}>
                          <Row justify="space-between" align="middle">
                            <Col>
                              <Space>
                                <CheckCircleOutlined style={{ color: '#52c41a' }} />
                                <Text strong>推理完成</Text>
                                {videoResult && (
                                  <Text type="secondary">
                                    {videoResult.total_frames} 帧 | {videoResult.fps.toFixed(1)} FPS | {videoResult.duration_seconds.toFixed(1)} 秒
                                  </Text>
                                )}
                              </Space>
                            </Col>
                            <Col>
                              <Button
                                type="primary"
                                icon={<DownloadOutlined />}
                                onClick={handleDownloadVideo}
                                loading={videoDownloading}
                              >
                                下载结果视频 {resultVideoSize > 0 && `(${formatFileSize(resultVideoSize)})`}
                              </Button>
                            </Col>
                          </Row>
                        </Card>

                        {/* Detection Statistics */}
                        {videoResult && (
                          <Card size="small" title="检测统计" style={{ marginTop: 16 }}>
                            {(() => {
                              // Calculate total detections per class
                              const classCount: Record<string, number> = {};
                              let totalDetections = 0;

                              videoResult.frame_results.forEach((frame) => {
                                frame.class_names.forEach((className) => {
                                  classCount[className] = (classCount[className] || 0) + 1;
                                  totalDetections++;
                                });
                              });

                              const classStats = Object.entries(classCount)
                                .map(([name, count]) => ({
                                  name,
                                  count,
                                  color: videoResult.class_colors?.[name] || '#666666',
                                }))
                                .sort((a, b) => b.count - a.count);

                              if (classStats.length === 0) {
                                return <Text type="secondary">未检测到目标</Text>;
                              }

                              return (
                                <Table
                                  dataSource={classStats}
                                  rowKey="name"
                                  size="small"
                                  pagination={false}
                                  columns={[
                                    {
                                      title: '类别',
                                      dataIndex: 'name',
                                      key: 'name',
                                      render: (name: string, record: { color: string }) => (
                                        <Space>
                                          <div
                                            style={{
                                              width: 16,
                                              height: 16,
                                              backgroundColor: record.color,
                                              borderRadius: 2,
                                            }}
                                          />
                                          <span>{name}</span>
                                        </Space>
                                      ),
                                    },
                                    {
                                      title: '总检测次数',
                                      dataIndex: 'count',
                                      key: 'count',
                                      width: 120,
                                      align: 'center' as const,
                                      render: (count: number) => (
                                        <Tag color="blue">{count}</Tag>
                                      ),
                                    },
                                  ]}
                                  summary={() => (
                                    <Table.Summary fixed>
                                      <Table.Summary.Row>
                                        <Table.Summary.Cell index={0}>
                                          <Text strong>总计</Text>
                                        </Table.Summary.Cell>
                                        <Table.Summary.Cell index={1} align="center">
                                          <Tag color="green">{totalDetections}</Tag>
                                        </Table.Summary.Cell>
                                      </Table.Summary.Row>
                                    </Table.Summary>
                                  )}
                                />
                              );
                            })()}
                          </Card>
                        )}
                      </>
                    )}
                  </Col>
                </Row>
              </TabPane>

              <TabPane
                tab={<><CameraOutlined /> 实时推流</>}
                key="stream"
              >
                <StreamTest model={model} />
              </TabPane>

              <TabPane
                tab={<><CodeOutlined /> API 文档</>}
                key="api"
              >
                <ApiDocumentation model={model} />
              </TabPane>
            </Tabs>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default ModelDetailPage;
