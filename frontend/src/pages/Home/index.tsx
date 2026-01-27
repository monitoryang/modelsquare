/**
 * Home Page - Model discovery and quick test entry
 */

import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Card,
  Row,
  Col,
  Input,
  Select,
  Tag,
  Typography,
  Spin,
  Empty,
  Statistic,
  Space,
} from 'antd';
import {
  SearchOutlined,
  EyeOutlined,
  HeartOutlined,
  RocketOutlined,
} from '@ant-design/icons';
import { modelService } from '../../services';
import type { Model } from '../../services';

const { Title, Paragraph, Text } = Typography;
const { Search } = Input;
const { Option } = Select;

const taskTypeColors: Record<string, string> = {
  classification: 'blue',
  detection: 'green',
  segmentation: 'purple',
  multimodal: 'orange',
  nlp: 'cyan',
};

const taskTypeLabels: Record<string, string> = {
  classification: '分类',
  detection: '检测',
  segmentation: '分割',
  multimodal: '多模态',
  nlp: 'NLP',
};

const frameworkColors: Record<string, string> = {
  pytorch: 'red',
  onnx: 'blue',
  tensorrt: 'green',
};

const HomePage: React.FC = () => {
  const navigate = useNavigate();
  const [models, setModels] = useState<Model[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [taskFilter, setTaskFilter] = useState<string | undefined>();

  useEffect(() => {
    fetchModels();
  }, [taskFilter]);

  const fetchModels = async () => {
    setLoading(true);
    try {
      const response = await modelService.list({
        task_type: taskFilter,
        keyword: searchKeyword,
        page_size: 12,
      });
      setModels(response.items);
    } catch (error) {
      console.error('Failed to fetch models:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = (value: string) => {
    setSearchKeyword(value);
    fetchModels();
  };

  const handleModelClick = (modelId: string) => {
    navigate(`/models/${modelId}`);
  };

  return (
    <div>
      {/* Hero Section */}
      <Card
        style={{
          marginBottom: 24,
          background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
          border: 'none',
        }}
      >
        <Row align="middle" justify="center" style={{ minHeight: 200 }}>
          <Col span={24} style={{ textAlign: 'center' }}>
            <Title level={1} style={{ color: '#fff', marginBottom: 8 }}>
              <RocketOutlined /> ModelSquare
            </Title>
            <Paragraph style={{ color: 'rgba(255,255,255,0.9)', fontSize: 18 }}>
              实时交互式模型广场平台 - 发现、测试、对比 AI 模型
            </Paragraph>
            <Space size="large" style={{ marginTop: 24 }}>
              <Statistic
                title={<span style={{ color: 'rgba(255,255,255,0.8)' }}>公开模型</span>}
                value={models.length}
                valueStyle={{ color: '#fff' }}
              />
              <Statistic
                title={<span style={{ color: 'rgba(255,255,255,0.8)' }}>支持任务</span>}
                value={5}
                valueStyle={{ color: '#fff' }}
              />
              <Statistic
                title={<span style={{ color: 'rgba(255,255,255,0.8)' }}>实时推理</span>}
                value="< 500ms"
                valueStyle={{ color: '#fff' }}
              />
            </Space>
          </Col>
        </Row>
      </Card>

      {/* Search and Filter */}
      <Card style={{ marginBottom: 24 }}>
        <Row gutter={16}>
          <Col flex="auto">
            <Search
              placeholder="搜索模型名称、描述..."
              allowClear
              enterButton={<><SearchOutlined /> 搜索</>}
              size="large"
              onSearch={handleSearch}
            />
          </Col>
          <Col>
            <Select
              placeholder="任务类型"
              allowClear
              size="large"
              style={{ width: 150 }}
              onChange={setTaskFilter}
            >
              <Option value="classification">分类</Option>
              <Option value="detection">检测</Option>
              <Option value="segmentation">分割</Option>
              <Option value="multimodal">多模态</Option>
              <Option value="nlp">NLP</Option>
            </Select>
          </Col>
        </Row>
      </Card>

      {/* Model List */}
      <Title level={4}>热门模型</Title>
      {loading ? (
        <div style={{ textAlign: 'center', padding: 50 }}>
          <Spin size="large" />
        </div>
      ) : models.length === 0 ? (
        <Empty description="暂无模型" />
      ) : (
        <Row gutter={[16, 16]}>
          {models.map((model) => (
            <Col xs={24} sm={12} md={8} lg={6} key={model.id}>
              <Card
                hoverable
                onClick={() => handleModelClick(model.id)}
                cover={
                  model.thumbnail_url ? (
                    <img
                      alt={model.name}
                      src={model.thumbnail_url}
                      style={{ height: 160, objectFit: 'cover' }}
                    />
                  ) : (
                    <div
                      style={{
                        height: 160,
                        background: 'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}
                    >
                      <RocketOutlined style={{ fontSize: 48, color: '#8c8c8c' }} />
                    </div>
                  )
                }
              >
                <Card.Meta
                  title={
                    <Space>
                      <Text strong ellipsis style={{ maxWidth: 150 }}>
                        {model.name}
                      </Text>
                    </Space>
                  }
                  description={
                    <>
                      <Space style={{ marginBottom: 8 }}>
                        <Tag color={taskTypeColors[model.task_type]}>
                          {taskTypeLabels[model.task_type]}
                        </Tag>
                        <Tag color={frameworkColors[model.framework]}>
                          {model.framework.toUpperCase()}
                        </Tag>
                      </Space>
                      <Paragraph
                        ellipsis={{ rows: 2 }}
                        style={{ marginBottom: 8, minHeight: 44 }}
                      >
                        {model.description || '暂无描述'}
                      </Paragraph>
                      <Space>
                        <Text type="secondary">
                          <EyeOutlined /> {model.download_count}
                        </Text>
                        <Text type="secondary">
                          <HeartOutlined /> {model.like_count}
                        </Text>
                      </Space>
                    </>
                  }
                />
              </Card>
            </Col>
          ))}
        </Row>
      )}
    </div>
  );
};

export default HomePage;
