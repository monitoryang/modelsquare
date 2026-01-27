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

const ModelDetailPage: React.FC = () => {
  const { modelId } = useParams<{ modelId: string }>();
  const navigate = useNavigate();
  const [model, setModel] = useState<Model | null>(null);
  const [loading, setLoading] = useState(true);
  const [inferring, setInferring] = useState(false);
  const [inferenceResult, setInferenceResult] = useState<Record<string, unknown> | null>(null);
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

    setInferring(true);
    try {
      const result = await modelService.inferImage(modelId, file) as Record<string, unknown>;
      setInferenceResult(result);
      message.success('推理完成');
      
      // Draw result on canvas if available
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

  const drawInferenceResult = async (file: File, result: unknown) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Load and draw the image
    const img = new Image();
    img.onload = () => {
      canvas.width = img.width;
      canvas.height = img.height;
      ctx.drawImage(img, 0, 0);

      // Draw detection boxes if applicable
      const inferResult = result as { result?: { boxes?: number[][]; labels?: number[] } };
      if (inferResult?.result?.boxes) {
        const boxes = inferResult.result.boxes;
        const labels = inferResult.result.labels || [];
        
        boxes.forEach((box: number[], index: number) => {
          const [x1, y1, x2, y2] = box;
          ctx.strokeStyle = '#ff0000';
          ctx.lineWidth = 2;
          ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
          
          if (labels[index] !== undefined) {
            ctx.fillStyle = '#ff0000';
            ctx.font = '14px Arial';
            ctx.fillText(`Class: ${labels[index]}`, x1, y1 - 5);
          }
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
                <Row gutter={16}>
                  <Col span={12}>
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
                  </Col>
                  <Col span={12}>
                    <div
                      style={{
                        border: '1px solid #d9d9d9',
                        borderRadius: 4,
                        minHeight: 200,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        background: '#141414',
                      }}
                    >
                      {inferring ? (
                        <Spin tip="推理中..." />
                      ) : (
                        <canvas
                          ref={canvasRef}
                          style={{ maxWidth: '100%', maxHeight: 400 }}
                        />
                      )}
                    </div>
                  </Col>
                </Row>
                
                {inferenceResult && (
                  <Card
                    title="推理结果"
                    size="small"
                    style={{ marginTop: 16 }}
                  >
                    <pre style={{ maxHeight: 300, overflow: 'auto' }}>
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
