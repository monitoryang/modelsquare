/**
 * Model Detail Page - View model info and run inference tests
 */

import React, { useState, useEffect, useRef } from 'react';
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
} from 'antd';
import {
  UploadOutlined,
  PlayCircleOutlined,
  CameraOutlined,
  ApiOutlined,
  ArrowLeftOutlined,
  HeartOutlined,
  ShareAltOutlined,
} from '@ant-design/icons';
import type { UploadFile as _UploadFile } from 'antd';
import { modelService } from '../../services';
import type { Model } from '../../services';

const { Title, Paragraph, Text } = Typography;
const { TabPane } = Tabs;

const taskTypeLabels: Record<string, string> = {
  classification: '图像分类',
  detection: '目标检测',
  segmentation: '图像分割',
  multimodal: '多模态',
  nlp: '自然语言处理',
};

interface DetectionResult {
  boxes: number[][];
  scores: number[];
  labels: number[];
  class_names: string[];
  class_colors: Record<string, string> | null;
  detection_count: number;
}

interface InferenceResult {
  model_id: string;
  timestamp_in: string;
  timestamp_out: string;
  latency_ms: number;
  result_type: string;
  result: DetectionResult | Record<string, unknown>;
  render_url: string | null;
}

const ModelDetailPage: React.FC = () => {
  const { modelId } = useParams<{ modelId: string }>();
  const navigate = useNavigate();
  const [model, setModel] = useState<Model | null>(null);
  const [loading, setLoading] = useState(true);
  const [inferring, setInferring] = useState(false);
  const [inferenceResult, setInferenceResult] = useState<InferenceResult | null>(null);
  const [confThreshold, setConfThreshold] = useState(0.25);
  const [iouThreshold, setIouThreshold] = useState(0.45);
  const [currentImage, setCurrentImage] = useState<File | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

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

  const handleImageUpload = async (file: File) => {
    if (!modelId) return false;

    setCurrentImage(file);
    setInferring(true);
    try {
      const result = await modelService.inferImage(modelId, file, confThreshold, iouThreshold) as InferenceResult;
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
      const result = await modelService.inferImage(modelId, currentImage, confThreshold, iouThreshold) as InferenceResult;
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

  const drawInferenceResult = async (file: File, result: InferenceResult) => {
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
                    <Button 
                      type="primary" 
                      onClick={handleReInfer} 
                      loading={inferring}
                      style={{ marginTop: 8 }}
                    >
                      重新推理
                    </Button>
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
                      }}
                    >
                      {inferring ? (
                        <Spin tip="推理中..." />
                      ) : (
                        <canvas
                          ref={canvasRef}
                          style={{ maxWidth: '100%', maxHeight: '100%' }}
                        />
                      )}
                    </div>
                  </Col>
                </Row>
                
                {inferenceResult && (
                  <Card
                    title="推理结果详情"
                    size="small"
                    style={{ marginTop: 16 }}
                  >
                    <pre style={{ maxHeight: 200, overflow: 'auto', fontSize: 12 }}>
                      {JSON.stringify(inferenceResult, null, 2)}
                    </pre>
                  </Card>
                )}
              </TabPane>

              <TabPane
                tab={<><PlayCircleOutlined /> 视频测试</>}
                key="video"
              >
                <Alert
                  message="视频测试功能即将上线"
                  description="支持上传短视频（不超过30秒）进行逐帧推理"
                  type="info"
                  showIcon
                />
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
