/**
 * VLM 万物检测页面
 * 
 * 使用视觉语言模型检测图片中的任意物体
 * 支持单次检测和对话式检测两种模式
 */

import React, { useState, useRef, useEffect } from 'react';
import {
  Card,
  Upload,
  Input,
  Button,
  Space,
  Typography,
  Alert,
  Spin,
  Tabs,
  List,
  Tag,
  message,
  Image,
  Divider,
  Row,
  Col,
  Statistic,
  Empty,
} from 'antd';
import {
  UploadOutlined,
  SearchOutlined,
  SendOutlined,
  ClearOutlined,
  ReloadOutlined,
  PictureOutlined,
  RobotOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons';
import type { UploadProps } from 'antd';
import { modelService } from '../../services';
import type {
  VLMBoundingBox,
  VLMGroundingResponse,
  VLMChatMessage,
  VLMHealthResponse,
} from '../../services/model';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;
const { TabPane } = Tabs;

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  boxes?: VLMBoundingBox[];
  renderUrl?: string;
  timestamp: Date;
}

const VLMDetectionPage: React.FC = () => {
  // 服务健康状态
  const [healthStatus, setHealthStatus] = useState<VLMHealthResponse | null>(null);
  const [checkingHealth, setCheckingHealth] = useState(false);

  // 单次检测模式状态
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string>('');
  const [prompt, setPrompt] = useState('');
  const [detecting, setDetecting] = useState(false);
  const [detectionResult, setDetectionResult] = useState<VLMGroundingResponse | null>(null);

  // 对话模式状态
  const [chatImageFile, setChatImageFile] = useState<File | null>(null);
  const [chatImagePreview, setChatImagePreview] = useState<string>('');
  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatting, setChatting] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // 组件挂载时检查 VLM 服务健康状态
  useEffect(() => {
    checkHealth();
  }, []);

  // 滚动到聊天底部
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages]);

  const checkHealth = async () => {
    setCheckingHealth(true);
    try {
      const status = await modelService.vlmHealthCheck();
      setHealthStatus(status);
    } catch (error) {
      setHealthStatus({ status: 'unavailable', available_models: [] });
    } finally {
      setCheckingHealth(false);
    }
  };

  // 单次检测处理器
  const handleImageChange: UploadProps['onChange'] = ({ file }) => {
    const originFile = file.originFileObj || (file as unknown as File);
    if (originFile && originFile instanceof File) {
      setImageFile(originFile);
      const reader = new FileReader();
      reader.onload = (e) => setImagePreview(e.target?.result as string);
      reader.readAsDataURL(originFile);
      setDetectionResult(null);
    }
  };

  const handleDetect = async () => {
    if (!imageFile) {
      message.warning('请先上传图片');
      return;
    }
    if (!prompt.trim()) {
      message.warning('请输入要检测的目标');
      return;
    }

    setDetecting(true);
    try {
      const result = await modelService.vlmGroundingDetection(imageFile, prompt, true);
      setDetectionResult(result);
      if (result.detection_count === 0) {
        message.info('未检测到符合描述的目标');
      } else {
        message.success(`检测到 ${result.detection_count} 个目标`);
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '检测失败');
    } finally {
      setDetecting(false);
    }
  };

  const clearDetection = () => {
    setImageFile(null);
    setImagePreview('');
    setPrompt('');
    setDetectionResult(null);
  };

  // 对话模式处理器
  const handleChatImageChange: UploadProps['onChange'] = ({ file }) => {
    const originFile = file.originFileObj || (file as unknown as File);
    if (originFile && originFile instanceof File) {
      setChatImageFile(originFile);
      const reader = new FileReader();
      reader.onload = (e) => setChatImagePreview(e.target?.result as string);
      reader.readAsDataURL(originFile);
      setChatMessages([]);
    }
  };

  const handleSendMessage = async () => {
    if (!chatImageFile) {
      message.warning('请先上传图片');
      return;
    }
    if (!chatInput.trim()) {
      return;
    }

    const userMessage: ChatMessage = {
      role: 'user',
      content: chatInput,
      timestamp: new Date(),
    };
    setChatMessages((prev) => [...prev, userMessage]);
    setChatInput('');
    setChatting(true);

    try {
      // 从之前的消息构建历史记录
      const history: VLMChatMessage[] = chatMessages.map((msg) => ({
        role: msg.role,
        content: msg.content,
      }));

      const result = await modelService.vlmGroundingChat(
        chatImageFile,
        chatInput,
        history,
        true
      );

      const assistantMessage: ChatMessage = {
        role: 'assistant',
        content: result.response,
        boxes: result.boxes,
        renderUrl: result.render_url,
        timestamp: new Date(),
      };
      setChatMessages((prev) => [...prev, assistantMessage]);
    } catch (error: any) {
      message.error(error.response?.data?.detail || '获取响应失败');
      // 如果失败则移除用户消息
      setChatMessages((prev) => prev.slice(0, -1));
    } finally {
      setChatting(false);
    }
  };

  const clearChat = () => {
    setChatImageFile(null);
    setChatImagePreview('');
    setChatMessages([]);
    setChatInput('');
  };

  const renderHealthStatus = () => (
    <Card size="small" style={{ marginBottom: 16 }}>
      <Space>
        <Text strong>VLM 服务状态：</Text>
        {checkingHealth ? (
          <Spin size="small" />
        ) : healthStatus?.status === 'healthy' ? (
          <>
            <Tag icon={<CheckCircleOutlined />} color="success">
              在线
            </Tag>
            <Text type="secondary">模型：{healthStatus.model_name}</Text>
          </>
        ) : (
          <Tag icon={<CloseCircleOutlined />} color="error">
            离线
          </Tag>
        )}
        <Button
          size="small"
          icon={<ReloadOutlined />}
          onClick={checkHealth}
          loading={checkingHealth}
        >
          刷新
        </Button>
      </Space>
    </Card>
  );

  const renderBoxList = (boxes: VLMBoundingBox[]) => (
    <List
      size="small"
      dataSource={boxes}
      renderItem={(box, index) => (
        <List.Item>
          <Space>
            <Tag color="blue">#{index + 1}</Tag>
            <Text strong>{box.label}</Text>
            {box.confidence && (
              <Text type="secondary">({(box.confidence * 100).toFixed(1)}%)</Text>
            )}
            <Text type="secondary" style={{ fontSize: 12 }}>
              [{Math.round(box.x1)}, {Math.round(box.y1)}, {Math.round(box.x2)},{' '}
              {Math.round(box.y2)}]
            </Text>
          </Space>
        </List.Item>
      )}
    />
  );

  const renderSingleDetection = () => (
    <Row gutter={24}>
      <Col xs={24} lg={12}>
        <Card title="上传图片" style={{ marginBottom: 16 }}>
          <Upload
            accept="image/jpeg,image/png"
            showUploadList={false}
            beforeUpload={() => false}
            onChange={handleImageChange}
          >
            <Button icon={<UploadOutlined />}>选择图片</Button>
          </Upload>

          {imagePreview && (
            <div style={{ marginTop: 16 }}>
              <Image
                src={imagePreview}
                alt="预览"
                style={{ maxWidth: '100%', maxHeight: 400 }}
              />
            </div>
          )}
        </Card>

        <Card title="检测设置">
          <Space direction="vertical" style={{ width: '100%' }}>
            <div>
              <Text strong>检测目标：</Text>
              <TextArea
                placeholder="描述要检测的目标，例如：'所有人'、'红色汽车'、'猫和狗'"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={3}
                style={{ marginTop: 8 }}
              />
            </div>

            <Space>
              <Button
                type="primary"
                icon={<SearchOutlined />}
                onClick={handleDetect}
                loading={detecting}
                disabled={!imageFile || !prompt.trim() || healthStatus?.status !== 'healthy'}
              >
                开始检测
              </Button>
              <Button icon={<ClearOutlined />} onClick={clearDetection}>
                清除
              </Button>
            </Space>
          </Space>
        </Card>
      </Col>

      <Col xs={24} lg={12}>
        <Card title="检测结果">
          {detecting ? (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <Spin size="large" />
              <Paragraph style={{ marginTop: 16 }}>
                正在使用 VLM 分析图片...
              </Paragraph>
            </div>
          ) : detectionResult ? (
            <Space direction="vertical" style={{ width: '100%' }}>
              <Row gutter={16}>
                <Col span={8}>
                  <Statistic
                    title="检测到目标"
                    value={detectionResult.detection_count}
                    suffix="个"
                  />
                </Col>
                <Col span={8}>
                  <Statistic
                    title="耗时"
                    value={detectionResult.latency_ms.toFixed(0)}
                    suffix="ms"
                  />
                </Col>
                <Col span={8}>
                  <Statistic
                    title="图片尺寸"
                    value={`${detectionResult.image_width}x${detectionResult.image_height}`}
                  />
                </Col>
              </Row>

              <Divider />

              {detectionResult.render_url && (
                <div>
                  <Text strong>渲染结果：</Text>
                  <Image
                    src={detectionResult.render_url}
                    alt="检测结果"
                    style={{ maxWidth: '100%', marginTop: 8 }}
                  />
                </div>
              )}

              {detectionResult.boxes.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <Text strong>检测到的目标：</Text>
                  {renderBoxList(detectionResult.boxes)}
                </div>
              )}

              <Divider />

              <div>
                <Text strong>原始响应：</Text>
                <Paragraph
                  style={{
                    background: '#f5f5f5',
                    padding: 12,
                    borderRadius: 4,
                    marginTop: 8,
                    whiteSpace: 'pre-wrap',
                    fontSize: 12,
                  }}
                >
                  {detectionResult.raw_response}
                </Paragraph>
              </div>
            </Space>
          ) : (
            <Empty description="上传图片并描述要检测的目标" />
          )}
        </Card>
      </Col>
    </Row>
  );

  const renderChatMode = () => (
    <Row gutter={24}>
      <Col xs={24} lg={8}>
        <Card title="图片" style={{ marginBottom: 16 }}>
          <Upload
            accept="image/jpeg,image/png"
            showUploadList={false}
            beforeUpload={() => false}
            onChange={handleChatImageChange}
          >
            <Button icon={<UploadOutlined />}>选择图片</Button>
          </Upload>

          {chatImagePreview && (
            <div style={{ marginTop: 16 }}>
              <Image
                src={chatImagePreview}
                alt="对话图片"
                style={{ maxWidth: '100%', maxHeight: 300 }}
              />
            </div>
          )}
        </Card>

        <Button icon={<ClearOutlined />} onClick={clearChat} block>
          清除对话
        </Button>
      </Col>

      <Col xs={24} lg={16}>
        <Card
          title="对话"
          style={{ height: 600, display: 'flex', flexDirection: 'column' }}
          bodyStyle={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}
        >
          <div style={{ flex: 1, overflowY: 'auto', marginBottom: 16 }}>
            {chatMessages.length === 0 ? (
              <Empty
                image={<RobotOutlined style={{ fontSize: 48 }} />}
                description="开始关于图片的对话"
              />
            ) : (
              chatMessages.map((msg, index) => (
                <div
                  key={index}
                  style={{
                    marginBottom: 16,
                    textAlign: msg.role === 'user' ? 'right' : 'left',
                  }}
                >
                  <div
                    style={{
                      display: 'inline-block',
                      maxWidth: '80%',
                      padding: '8px 12px',
                      borderRadius: 8,
                      background: msg.role === 'user' ? '#1890ff' : '#f0f0f0',
                      color: msg.role === 'user' ? 'white' : 'black',
                    }}
                  >
                    <Paragraph style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                      {msg.content}
                    </Paragraph>
                  </div>

                  {msg.boxes && msg.boxes.length > 0 && (
                    <div style={{ marginTop: 8, textAlign: 'left' }}>
                      <Text type="secondary">检测到 {msg.boxes.length} 个目标：</Text>
                      {renderBoxList(msg.boxes)}
                    </div>
                  )}

                  {msg.renderUrl && (
                    <div style={{ marginTop: 8, textAlign: 'left' }}>
                      <Image
                        src={msg.renderUrl}
                        alt="检测结果"
                        style={{ maxWidth: 300 }}
                      />
                    </div>
                  )}
                </div>
              ))
            )}
            {chatting && (
              <div style={{ textAlign: 'left', marginBottom: 16 }}>
                <Spin /> <Text type="secondary">思考中...</Text>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          <div style={{ display: 'flex', gap: 8 }}>
            <TextArea
              placeholder="询问关于图片的问题，例如：'找出所有人' 或 '图片中有哪些物体？'"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onPressEnter={(e) => {
                if (!e.shiftKey) {
                  e.preventDefault();
                  handleSendMessage();
                }
              }}
              rows={2}
              disabled={!chatImageFile || chatting || healthStatus?.status !== 'healthy'}
            />
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={handleSendMessage}
              loading={chatting}
              disabled={!chatImageFile || !chatInput.trim() || healthStatus?.status !== 'healthy'}
            >
              发送
            </Button>
          </div>
        </Card>
      </Col>
    </Row>
  );

  return (
    <div style={{ padding: 24 }}>
      <Title level={2}>
        <RobotOutlined /> 万物检测
      </Title>
      <Paragraph type="secondary">
        使用视觉语言模型检测图片中的任意物体。只需上传图片并描述要查找的目标即可。
      </Paragraph>

      {renderHealthStatus()}

      {healthStatus?.status !== 'healthy' && !checkingHealth && (
        <Alert
          message="VLM 服务不可用"
          description="VLM 服务未运行。请使用以下命令启动 vLLM 服务器：docker compose --profile vllm up -d"
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

      <Tabs defaultActiveKey="single">
        <TabPane
          tab={
            <span>
              <PictureOutlined /> 单次检测
            </span>
          }
          key="single"
        >
          {renderSingleDetection()}
        </TabPane>
        <TabPane
          tab={
            <span>
              <RobotOutlined /> 对话模式
            </span>
          }
          key="chat"
        >
          {renderChatMode()}
        </TabPane>
      </Tabs>
    </div>
  );
};

export default VLMDetectionPage;
