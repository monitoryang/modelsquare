/**
 * Profile Page - User profile and model management
 */

import React, { useState, useEffect, useCallback } from 'react';
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
  Tooltip,
  Progress,
  Modal,
  Form,
  InputNumber,
  Switch,
  Statistic,
} from 'antd';
import {
  UserOutlined,
  EditOutlined,
  PlusOutlined,
  DeleteOutlined,
  CopyOutlined,
  CrownOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  DownloadOutlined,
  StopOutlined,
  SyncOutlined,
  VideoCameraOutlined,
  EyeOutlined,
  EyeInvisibleOutlined,
  BarChartOutlined,
  ExclamationCircleOutlined,
  CalendarOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { authService, modelService } from '../../services';
import type { User, Model, UserVideoTask, VideoTaskStatus, ApiKeyInfo, ApiKeyUsageResponse } from '../../services';

const { Title, Text, Paragraph } = Typography;
const { TabPane } = Tabs;

const ProfilePage: React.FC = () => {
  const navigate = useNavigate();
  const [user, setUser] = useState<User | null>(null);
  const [models, setModels] = useState<Model[]>([]);
  const [loading, setLoading] = useState(true);
  const { message } = App.useApp();

  // API Key state - new multi-key support
  const [apiKeys, setApiKeys] = useState<ApiKeyInfo[]>([]);
  const [apiKeyLoading, setApiKeyLoading] = useState(false);
  const [showKeyMap, setShowKeyMap] = useState<Record<string, boolean>>({});
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [createForm] = Form.useForm();
  const [createLoading, setCreateLoading] = useState(false);
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [selectedKeyDetail, setSelectedKeyDetail] = useState<ApiKeyUsageResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Video tasks state
  const [videoTasks, setVideoTasks] = useState<UserVideoTask[]>([]);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [tasksPagination, setTasksPagination] = useState({ page: 1, pageSize: 10, total: 0 });
  const [downloadingTaskId, setDownloadingTaskId] = useState<string | null>(null);
  const [cancellingTaskId, setCancellingTaskId] = useState<string | null>(null);

  useEffect(() => {
    fetchUserData();
    fetchUserModels();
    fetchApiKeys();
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

  const fetchApiKeys = async () => {
    setApiKeyLoading(true);
    try {
      const data = await authService.listApiKeys();
      setApiKeys(data.items);
    } catch (error) {
      console.error('Failed to fetch API keys:', error);
    } finally {
      setApiKeyLoading(false);
    }
  };

  const handleCreateApiKey = async (values: { name: string; expires_in_days: number }) => {
    setCreateLoading(true);
    try {
      const newKey = await authService.createApiKey(values);
      setApiKeys([newKey, ...apiKeys]);
      setShowKeyMap({ ...showKeyMap, [newKey.id]: true });
      setCreateModalVisible(false);
      createForm.resetFields();
      message.success('API Key 创建成功，请立即复制保存');
    } catch (error) {
      message.error('创建 API Key 失败');
      console.error(error);
    } finally {
      setCreateLoading(false);
    }
  };

  const handleToggleKeyStatus = async (keyId: string, isActive: boolean) => {
    try {
      await authService.updateApiKey(keyId, { is_active: isActive });
      setApiKeys(apiKeys.map(k => k.id === keyId ? { ...k, is_active: isActive } : k));
      message.success(isActive ? 'API Key 已启用' : 'API Key 已禁用');
    } catch (error) {
      message.error('操作失败');
      console.error(error);
    }
  };

  const handleDeleteApiKey = async (keyId: string) => {
    try {
      await authService.deleteApiKey(keyId);
      setApiKeys(apiKeys.filter(k => k.id !== keyId));
      message.success('API Key 已删除');
    } catch (error) {
      message.error('删除失败');
      console.error(error);
    }
  };

  const handleViewKeyDetail = async (keyId: string) => {
    setDetailLoading(true);
    setDetailModalVisible(true);
    try {
      const detail = await authService.getApiKeyDetail(keyId, 30);
      setSelectedKeyDetail(detail);
    } catch (error) {
      message.error('获取详情失败');
      console.error(error);
    } finally {
      setDetailLoading(false);
    }
  };

  const handleCopyApiKey = (key: string) => {
    navigator.clipboard.writeText(key);
    message.success('API Key 已复制到剪贴板');
  };

  const handleDeleteModel = async (modelId: string) => {
    try {
      console.log('Deleting model:', modelId);
      await modelService.delete(modelId);
      message.success('模型已删除');
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

  // Fetch user video tasks
  const fetchVideoTasks = useCallback(async (page = 1, pageSize = 10) => {
    setTasksLoading(true);
    try {
      const response = await modelService.getUserVideoTasks(page, pageSize);
      setVideoTasks(response.items);
      setTasksPagination({
        page: response.page,
        pageSize: response.page_size,
        total: response.total,
      });
    } catch (error) {
      console.error('Failed to fetch video tasks:', error);
    } finally {
      setTasksLoading(false);
    }
  }, []);

  // Handle download video result
  const handleDownloadTaskResult = async (task: UserVideoTask) => {
    setDownloadingTaskId(task.task_id);
    try {
      const blob = await modelService.downloadVideoResult(task.model_id, task.task_id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `detection_result_${task.task_id}.mp4`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      message.success('视频下载成功');
    } catch (error) {
      message.error('视频下载失败');
      console.error(error);
    } finally {
      setDownloadingTaskId(null);
    }
  };

  // Handle cancel task
  const handleCancelTask = async (taskId: string) => {
    setCancellingTaskId(taskId);
    try {
      await modelService.cancelVideoTask(taskId);
      message.success('任务已取消');
      fetchVideoTasks(tasksPagination.page, tasksPagination.pageSize);
    } catch (error) {
      message.error('取消任务失败');
      console.error(error);
    } finally {
      setCancellingTaskId(null);
    }
  };

  // Handle delete task
  const handleDeleteTask = async (taskId: string) => {
    try {
      await modelService.deleteVideoTask(taskId);
      message.success('记录已删除');
      fetchVideoTasks(tasksPagination.page, tasksPagination.pageSize);
    } catch (error) {
      message.error('删除失败');
      console.error(error);
    }
  };

  // Format file size
  const formatFileSize = (bytes: number | null): string => {
    if (!bytes || bytes === 0) return '-';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  // Get status tag
  const getStatusTag = (status: VideoTaskStatus) => {
    const statusConfig: Record<VideoTaskStatus, { color: string; icon: React.ReactNode; text: string }> = {
      pending: { color: 'default', icon: <LoadingOutlined />, text: '等待中' },
      processing: { color: 'processing', icon: <SyncOutlined spin />, text: '处理中' },
      rendering: { color: 'processing', icon: <SyncOutlined spin />, text: '渲染中' },
      completed: { color: 'success', icon: <CheckCircleOutlined />, text: '已完成' },
      failed: { color: 'error', icon: <CloseCircleOutlined />, text: '失败' },
      cancelled: { color: 'warning', icon: <StopOutlined />, text: '已取消' },
    };
    const config = statusConfig[status] || statusConfig.pending;
    return <Tag icon={config.icon} color={config.color}>{config.text}</Tag>;
  };

  // Calculate days remaining
  const getDaysRemaining = (expiresAt: string): number => {
    const now = new Date();
    const expires = new Date(expiresAt);
    const diff = expires.getTime() - now.getTime();
    return Math.ceil(diff / (1000 * 60 * 60 * 24));
  };

  // API Keys table columns
  const apiKeyColumns: ColumnsType<ApiKeyInfo> = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: 120,
    },
    {
      title: 'API Key',
      dataIndex: 'key',
      key: 'key',
      width: 280,
      render: (key: string, record) => (
        <Space>
          <Input
            value={showKeyMap[record.id] ? key : '••••••••••••••••••••••••'}
            readOnly
            size="small"
            style={{ width: 180, fontFamily: 'monospace' }}
          />
          <Tooltip title={showKeyMap[record.id] ? "隐藏" : "显示"}>
            <Button
              size="small"
              icon={showKeyMap[record.id] ? <EyeInvisibleOutlined /> : <EyeOutlined />}
              onClick={() => setShowKeyMap({ ...showKeyMap, [record.id]: !showKeyMap[record.id] })}
            />
          </Tooltip>
          <Tooltip title="复制">
            <Button
              size="small"
              icon={<CopyOutlined />}
              onClick={() => handleCopyApiKey(key)}
            />
          </Tooltip>
        </Space>
      ),
    },
    {
      title: '状态',
      key: 'status',
      width: 100,
      render: (_, record) => {
        if (record.is_expired) {
          return <Tag color="error" icon={<ExclamationCircleOutlined />}>已过期</Tag>;
        }
        if (!record.is_active) {
          return <Tag color="default">已禁用</Tag>;
        }
        const daysRemaining = getDaysRemaining(record.expires_at);
        if (daysRemaining <= 7) {
          return <Tag color="warning" icon={<CalendarOutlined />}>即将过期 ({daysRemaining}天)</Tag>;
        }
        return <Tag color="success" icon={<CheckCircleOutlined />}>有效</Tag>;
      },
    },
    {
      title: '调用次数',
      dataIndex: 'total_calls',
      key: 'total_calls',
      width: 90,
      render: (calls: number) => calls.toLocaleString(),
    },
    {
      title: '过期时间',
      dataIndex: 'expires_at',
      key: 'expires_at',
      width: 160,
      render: (date: string) => new Date(date).toLocaleString(),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_, record) => (
        <Space size="small">
          <Button
            size="small"
            icon={<BarChartOutlined />}
            onClick={() => handleViewKeyDetail(record.id)}
          >
            统计
          </Button>
          <Switch
            size="small"
            checked={record.is_active}
            disabled={record.is_expired}
            onChange={(checked) => handleToggleKeyStatus(record.id, checked)}
          />
          <Popconfirm
            title="确定要删除此 API Key 吗？"
            description="删除后将无法恢复"
            onConfirm={() => handleDeleteApiKey(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  // Video tasks table columns
  const videoTaskColumns: ColumnsType<UserVideoTask> = [
    {
      title: '视频文件',
      dataIndex: 'video_filename',
      key: 'video_filename',
      width: 180,
      ellipsis: true,
      render: (filename: string, record) => (
        <Tooltip title={filename}>
          <Space>
            <VideoCameraOutlined />
            <span>{filename}</span>
            {record.video_size && (
              <Tag>{formatFileSize(record.video_size)}</Tag>
            )}
          </Space>
        </Tooltip>
      ),
    },
    {
      title: '模型',
      dataIndex: 'model_name',
      key: 'model_name',
      width: 120,
      render: (name: string | null, record) => (
        name ? (
          <a onClick={() => navigate(`/models/${record.model_id}`)}>{name}</a>
        ) : (
          <Text type="secondary">-</Text>
        )
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: VideoTaskStatus) => getStatusTag(status),
    },
    {
      title: '进度',
      key: 'progress',
      width: 150,
      render: (_, record) => {
        if (record.status === 'completed') {
          return <Progress percent={100} size="small" />;
        }
        if (record.status === 'failed' || record.status === 'cancelled') {
          return <Progress percent={record.progress_percent} size="small" status="exception" />;
        }
        return <Progress percent={Math.round(record.progress_percent)} size="small" />;
      },
    },
    {
      title: '结果大小',
      dataIndex: 'render_video_size',
      key: 'render_video_size',
      width: 100,
      render: (size: number | null) => formatFileSize(size),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (date: string) => new Date(date).toLocaleString(),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_, record) => (
        <Space size="small">
          {record.status === 'completed' && (
            <Button
              type="primary"
              size="small"
              icon={<DownloadOutlined />}
              loading={downloadingTaskId === record.task_id}
              onClick={() => handleDownloadTaskResult(record)}
            >
              下载
            </Button>
          )}
          {(record.status === 'pending' || record.status === 'processing' || record.status === 'rendering') && (
            <Popconfirm
              title="确定要取消此任务吗？"
              onConfirm={() => handleCancelTask(record.task_id)}
              okText="确定"
              cancelText="取消"
            >
              <Button
                size="small"
                danger
                icon={<StopOutlined />}
                loading={cancellingTaskId === record.task_id}
              >
                取消
              </Button>
            </Popconfirm>
          )}
          {(record.status === 'completed' || record.status === 'failed' || record.status === 'cancelled') && (
            <Popconfirm
              title="确定要删除此记录吗？"
              onConfirm={() => handleDeleteTask(record.task_id)}
              okText="确定"
              cancelText="取消"
            >
              <Button size="small" icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

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
        title: 'Triton状态',
        dataIndex: 'triton_status',
        key: 'triton_status',
        render: (tritonStatus: Model['triton_status']) => {
          if (!tritonStatus) {
            return (
              <Tooltip title="请上传ONNX或TensorRT模型文件">
                <Tag icon={<CloseCircleOutlined />} color="default">未部署</Tag>
              </Tooltip>
            );
          }
          if (tritonStatus.loaded) {
            return (
              <Tooltip title="模型已在Triton中加载，可进行推理">
                <Tag icon={<CheckCircleOutlined />} color="success">已加载</Tag>
              </Tooltip>
            );
          }
          if (tritonStatus.deployed) {
            return (
              <Tooltip title="模型已部署到Triton仓库，等待加载">
                <Tag icon={<LoadingOutlined />} color="warning">已部署</Tag>
              </Tooltip>
            );
          }
          return (
            <Tooltip title="请上传ONNX或TensorRT模型文件">
              <Tag icon={<CloseCircleOutlined />} color="default">未部署</Tag>
            </Tooltip>
          );
        },
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

          {/* API Key Summary Card */}
          <Card title="API Key 概览" style={{ marginTop: 16 }} loading={apiKeyLoading}>
            <Row gutter={16}>
              <Col span={12}>
                <Statistic title="API Key 数量" value={apiKeys.length} />
              </Col>
              <Col span={12}>
                <Statistic 
                  title="有效 Key" 
                  value={apiKeys.filter(k => k.is_valid).length} 
                  valueStyle={{ color: '#3f8600' }}
                />
              </Col>
            </Row>
            <Row gutter={16} style={{ marginTop: 16 }}>
              <Col span={12}>
                <Statistic 
                  title="总调用次数" 
                  value={apiKeys.reduce((sum, k) => sum + k.total_calls, 0)} 
                />
              </Col>
              <Col span={12}>
                <Statistic 
                  title="已过期" 
                  value={apiKeys.filter(k => k.is_expired).length}
                  valueStyle={{ color: apiKeys.filter(k => k.is_expired).length > 0 ? '#cf1322' : undefined }}
                />
              </Col>
            </Row>
            <Button 
              type="primary" 
              block 
              icon={<PlusOutlined />}
              style={{ marginTop: 16 }}
              onClick={() => setCreateModalVisible(true)}
            >
              创建新的 API Key
            </Button>
          </Card>
        </Col>

        {/* Content Area */}
        <Col xs={24} lg={16}>
          <Card>
            <Tabs 
              defaultActiveKey="apikeys"
              onChange={(key) => {
                if (key === 'history') {
                  fetchVideoTasks(1, tasksPagination.pageSize);
                }
              }}
            >
              <TabPane tab="API Key 管理" key="apikeys">
                <div style={{ marginBottom: 16 }}>
                  <Space>
                    <Button
                      type="primary"
                      icon={<PlusOutlined />}
                      onClick={() => setCreateModalVisible(true)}
                    >
                      创建 API Key
                    </Button>
                    <Button
                      icon={<SyncOutlined />}
                      onClick={fetchApiKeys}
                      loading={apiKeyLoading}
                    >
                      刷新
                    </Button>
                  </Space>
                  <Text type="secondary" style={{ marginLeft: 16 }}>
                    API Key 有效期最长 90 天
                  </Text>
                </div>
                <Table
                  columns={apiKeyColumns}
                  dataSource={apiKeys}
                  rowKey="id"
                  loading={apiKeyLoading}
                  pagination={{ pageSize: 10 }}
                  locale={{ emptyText: <Empty description="暂无 API Key，点击上方按钮创建" /> }}
                  scroll={{ x: 900 }}
                />
              </TabPane>

              <TabPane tab={user.is_superuser ? "模型管理" : "可用模型"} key="models">
                {/* 只有超级用户才显示上传按钮 */}
                {user.is_superuser && (
                  <div style={{ marginBottom: 16 }}>
                    <Button
                      type="primary"
                      icon={<PlusOutlined />}
                      onClick={() => navigate('/models/upload')}
                    >
                      注册模型
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
                <div style={{ marginBottom: 16 }}>
                  <Button
                    icon={<SyncOutlined />}
                    onClick={() => fetchVideoTasks(tasksPagination.page, tasksPagination.pageSize)}
                    loading={tasksLoading}
                  >
                    刷新
                  </Button>
                </div>
                <Table
                  columns={videoTaskColumns}
                  dataSource={videoTasks}
                  rowKey="task_id"
                  loading={tasksLoading}
                  pagination={{
                    current: tasksPagination.page,
                    pageSize: tasksPagination.pageSize,
                    total: tasksPagination.total,
                    showSizeChanger: true,
                    showTotal: (total) => `共 ${total} 条记录`,
                    onChange: (page, pageSize) => fetchVideoTasks(page, pageSize),
                  }}
                  locale={{ emptyText: <Empty description="暂无测试记录" /> }}
                  scroll={{ x: 1000 }}
                />
              </TabPane>
            </Tabs>
          </Card>
        </Col>
      </Row>

      {/* Create API Key Modal */}
      <Modal
        title="创建新的 API Key"
        open={createModalVisible}
        onCancel={() => {
          setCreateModalVisible(false);
          createForm.resetFields();
        }}
        footer={null}
      >
        <Form
          form={createForm}
          layout="vertical"
          onFinish={handleCreateApiKey}
          initialValues={{ expires_in_days: 30 }}
        >
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入 API Key 名称' }]}
          >
            <Input placeholder="例如：测试环境、生产环境" maxLength={64} />
          </Form.Item>
          <Form.Item
            name="expires_in_days"
            label="有效期（天）"
            rules={[{ required: true, message: '请输入有效期' }]}
            extra="最长有效期为 90 天"
          >
            <InputNumber min={1} max={90} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button onClick={() => setCreateModalVisible(false)}>取消</Button>
              <Button type="primary" htmlType="submit" loading={createLoading}>
                创建
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* API Key Detail Modal */}
      <Modal
        title="API Key 调用统计"
        open={detailModalVisible}
        onCancel={() => {
          setDetailModalVisible(false);
          setSelectedKeyDetail(null);
        }}
        footer={[
          <Button key="close" onClick={() => setDetailModalVisible(false)}>
            关闭
          </Button>
        ]}
        width={600}
      >
        {detailLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <LoadingOutlined style={{ fontSize: 24 }} />
            <p>加载中...</p>
          </div>
        ) : selectedKeyDetail ? (
          <>
            <Card size="small" style={{ marginBottom: 16 }}>
              <Row gutter={16}>
                <Col span={6}>
                  <Statistic title="总调用" value={selectedKeyDetail.usage_summary.total_calls} />
                </Col>
                <Col span={6}>
                  <Statistic 
                    title="成功" 
                    value={selectedKeyDetail.usage_summary.total_success}
                    valueStyle={{ color: '#3f8600' }}
                  />
                </Col>
                <Col span={6}>
                  <Statistic 
                    title="失败" 
                    value={selectedKeyDetail.usage_summary.total_errors}
                    valueStyle={{ color: selectedKeyDetail.usage_summary.total_errors > 0 ? '#cf1322' : undefined }}
                  />
                </Col>
                <Col span={6}>
                  <Statistic 
                    title="平均延迟" 
                    value={selectedKeyDetail.usage_summary.avg_latency_ms.toFixed(0)}
                    suffix="ms"
                  />
                </Col>
              </Row>
            </Card>
            <Table
              size="small"
              dataSource={selectedKeyDetail.usage_summary.daily_usage}
              rowKey="date"
              pagination={{ pageSize: 7 }}
              columns={[
                { title: '日期', dataIndex: 'date', key: 'date' },
                { title: '调用次数', dataIndex: 'call_count', key: 'call_count' },
                { title: '成功', dataIndex: 'success_count', key: 'success_count' },
                { title: '失败', dataIndex: 'error_count', key: 'error_count' },
                { 
                  title: '平均延迟(ms)', 
                  dataIndex: 'avg_latency_ms', 
                  key: 'avg_latency_ms',
                  render: (v: number) => v.toFixed(0)
                },
              ]}
              locale={{ emptyText: '暂无调用记录' }}
            />
          </>
        ) : (
          <Empty description="无数据" />
        )}
      </Modal>
    </div>
  );
};

export default ProfilePage;
