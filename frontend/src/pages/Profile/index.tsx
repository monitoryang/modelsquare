/**
 * Profile Page - User profile and model management
 */

import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Card,
  Row,
  Col,
  Typography,
  Avatar,
  Button,
  Tabs,
  Table,
  Tag,
  Space,
  Empty,
  Popconfirm,
  Input,
  App,
} from 'antd';
import {
  UserOutlined,
  EditOutlined,
  PlusOutlined,
  DeleteOutlined,
  KeyOutlined,
  CopyOutlined,
  CrownOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { authService, modelService } from '../../services';
import type { User, Model } from '../../services';

const { Title, Text, Paragraph } = Typography;
const { TabPane } = Tabs;

const ProfilePage: React.FC = () => {
  const navigate = useNavigate();
  const [user, setUser] = useState<User | null>(null);
  const [models, setModels] = useState<Model[]>([]);
  const [loading, setLoading] = useState(true);
  const [apiKey] = useState<string>('');
  const { message } = App.useApp();

  useEffect(() => {
    fetchUserData();
    fetchUserModels();
  }, []);

  const fetchUserData = async () => {
    try {
      const userData = await authService.getCurrentUser();
      setUser(userData);
    } catch (error) {
      message.error('获取用户信息失败');
      navigate('/login');
    }
  };

  const fetchUserModels = async () => {
    setLoading(true);
    try {
      const response = await modelService.list({ page_size: 100 });
      setModels(response.items);
    } catch (error) {
      console.error('Failed to fetch models:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteModel = async (modelId: string) => {
    try {
      console.log('Deleting model:', modelId);
      await modelService.delete(modelId);
      message.success('模型已删除');
      // 重新获取模型列表
      await fetchUserModels();
      console.log('Model list refreshed');
    } catch (error: unknown) {
      console.error('Delete error:', error);
      const axiosError = error as { response?: { data?: { detail?: string }, status?: number } };
      if (axiosError.response) {
        const errorDetail = axiosError.response.data?.detail;
        message.error(errorDetail || `删除失败: ${axiosError.response.status}`);
      } else {
        message.error('删除失败，请稍后重试');
      }
    }
  };

  const handleCopyApiKey = () => {
    if (apiKey) {
      navigator.clipboard.writeText(apiKey);
      message.success('API Key 已复制到剪贴板');
    }
  };

  // 根据用户类型生成不同的列配置
  const getModelColumns = (): ColumnsType<Model> => {
    const baseColumns: ColumnsType<Model> = [
      {
        title: '模型名称',
        dataIndex: 'name',
        key: 'name',
        render: (text, record) => (
          <a onClick={() => navigate(`/models/${record.id}`)}>{text}</a>
        ),
      },
      {
        title: '任务类型',
        dataIndex: 'task_type',
        key: 'task_type',
        render: (type) => <Tag>{type}</Tag>,
      },
      {
        title: '框架',
        dataIndex: 'framework',
        key: 'framework',
        render: (fw) => <Tag color="blue">{fw.toUpperCase()}</Tag>,
      },
      {
        title: '可见性',
        dataIndex: 'is_public',
        key: 'is_public',
        render: (isPublic) =>
          isPublic ? <Tag color="green">公开</Tag> : <Tag>私有</Tag>,
      },
      {
        title: '创建时间',
        dataIndex: 'created_at',
        key: 'created_at',
        render: (date) => new Date(date).toLocaleDateString(),
      },
    ];

    // 只有超级用户才显示操作列
    if (user?.is_superuser) {
      baseColumns.push({
        title: '操作',
        key: 'actions',
        render: (_, record) => (
          <Space>
            <Button
              size="small"
              icon={<EditOutlined />}
              onClick={() => navigate(`/models/${record.id}/edit`)}
            >
              编辑
            </Button>
            <Popconfirm
              title="确定要删除这个模型吗？"
              onConfirm={() => handleDeleteModel(record.id)}
              okText="确定"
              cancelText="取消"
            >
              <Button size="small" danger icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          </Space>
        ),
      });
    }

    return baseColumns;
  };

  if (!user) {
    return null;
  }

  return (
    <div>
      <Row gutter={24}>
        {/* User Profile Card */}
        <Col xs={24} lg={8}>
          <Card>
            <div style={{ textAlign: 'center' }}>
              <Avatar
                size={100}
                icon={<UserOutlined />}
                src={user.avatar_url}
              />
              <Title level={3} style={{ marginTop: 16, marginBottom: 4 }}>
                {user.username}
                {user.is_superuser && (
                  <Tag color="gold" style={{ marginLeft: 8 }}>
                    <CrownOutlined /> 超级用户
                  </Tag>
                )}
              </Title>
              <Text type="secondary">{user.email}</Text>
              {user.bio && (
                <Paragraph style={{ marginTop: 16 }}>{user.bio}</Paragraph>
              )}
              <Button
                icon={<EditOutlined />}
                style={{ marginTop: 16 }}
              >
                编辑资料
              </Button>
            </div>
          </Card>

          {/* API Key Card */}
          <Card title="API Key 管理" style={{ marginTop: 16 }}>
            <Space direction="vertical" style={{ width: '100%' }}>
              <Text type="secondary">
                使用 API Key 进行接口调用认证
              </Text>
              <Input.Group compact>
                <Input
                  style={{ width: 'calc(100% - 100px)' }}
                  value={apiKey || '••••••••••••••••'}
                  readOnly
                  prefix={<KeyOutlined />}
                />
                <Button
                  icon={<CopyOutlined />}
                  onClick={handleCopyApiKey}
                  disabled={!apiKey}
                >
                  复制
                </Button>
              </Input.Group>
              <Button type="primary" block>
                生成新的 API Key
              </Button>
            </Space>
          </Card>
        </Col>

        {/* Content Area */}
        <Col xs={24} lg={16}>
          <Card>
            <Tabs defaultActiveKey="models">
              <TabPane tab={user.is_superuser ? "模型管理" : "可用模型"} key="models">
                {/* 只有超级用户才显示上传按钮 */}
                {user.is_superuser && (
                  <div style={{ marginBottom: 16 }}>
                    <Button
                      type="primary"
                      icon={<PlusOutlined />}
                      onClick={() => navigate('/models/upload')}
                    >
                      上传模型
                    </Button>
                  </div>
                )}
                <Table
                  columns={getModelColumns()}
                  dataSource={models}
                  rowKey="id"
                  loading={loading}
                  pagination={{ pageSize: 10 }}
                  locale={{ emptyText: <Empty description="暂无模型" /> }}
                />
              </TabPane>

              <TabPane tab="测试记录" key="history">
                <Empty description="暂无测试记录" />
              </TabPane>

              <TabPane tab="API 调用统计" key="stats">
                <Empty description="暂无调用统计" />
              </TabPane>
            </Tabs>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default ProfilePage;
