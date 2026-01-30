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
} from '@ant-design/icons';
import type { UploadFile as _UploadFile } from 'antd';
import { modelService } from '../../services';
import type { Model, InferenceResponse, DetectionResult, VideoTaskProgress, VideoTaskResult } from '../../services';

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
          
          // Draw label text
          ctx.fillStyle = '#ffffff';
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
        } catch (err) {
          console.error('Failed to get video result:', err);
        }
      } else if (progress.status === 'failed') {
        stopPolling();
        message.error(progress.error_message || '视频推理失败');
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
        (percent) => setVideoUploadProgress(percent)
      );
      
      setVideoTaskId(taskResponse.task_id);
      message.success('视频上传成功，开始处理');
      
      // Start polling for progress
      startPolling(taskResponse.task_id);
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
                {model.class_config.map((cls, index) => (
                  <Tag 
                    key={index} 
                    style={{ 
                      backgroundColor: cls.color,
                      color: '#fff',
                      border: 'none'
                    }}
                  >
                    {cls.name}
                  </Tag>
                ))}
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
                  <Row gutter={24}>
                    <Col span={12}>
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
                    <Col span={12}>
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
                  </Row>
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
                      <p className="ant-upload-hint">支持 MP4 格式，最大 2GB</p>
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
                            </>
                          )}
                        </Space>
                      </Card>
                    )}

                    {/* Completed State - Show results and download in single card */}
                    {videoProgress?.status === 'completed' && (
                      <Card 
                        title={
                          <Space>
                            <CheckCircleOutlined style={{ color: '#52c41a' }} />
                            <span>推理完成</span>
                          </Space>
                        }
                        extra={
                          <Button
                            type="primary"
                            icon={<DownloadOutlined />}
                            onClick={handleDownloadVideo}
                            loading={videoDownloading}
                          >
                            下载结果视频 {resultVideoSize > 0 && `(${formatFileSize(resultVideoSize)})`}
                          </Button>
                        }
                      >
                        {videoResult && (
                          <>
                            {/* Video Statistics */}
                            <Row gutter={16}>
                              <Col span={8}>
                                <Statistic
                                  title="总帧数"
                                  value={videoResult.total_frames}
                                />
                              </Col>
                              <Col span={8}>
                                <Statistic
                                  title="帧率"
                                  value={videoResult.fps.toFixed(1)}
                                  suffix="FPS"
                                />
                              </Col>
                              <Col span={8}>
                                <Statistic
                                  title="时长"
                                  value={videoResult.duration_seconds.toFixed(1)}
                                  suffix="秒"
                                />
                              </Col>
                            </Row>
                            
                            <Divider style={{ margin: '16px 0' }} />
                            
                            {/* Detection Statistics */}
                            <Text strong>检测统计</Text>
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
                                return <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>未检测到目标</Text>;
                              }
                              
                              return (
                                <Table
                                  dataSource={classStats}
                                  rowKey="name"
                                  size="small"
                                  pagination={false}
                                  style={{ marginTop: 8 }}
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
                          </>
                        )}
                      </Card>
                    )}
                  </Col>
                </Row>
              </TabPane>

              <TabPane
                tab={<><CameraOutlined /> 实时推流</>}
                key="stream"
              >
                <Alert
                  message="实时推流功能即将上线"
                  description="支持 RTMP/WebRTC 推流，实时查看推理结果"
                  type="info"
                  showIcon
                />
              </TabPane>
            </Tabs>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default ModelDetailPage;
