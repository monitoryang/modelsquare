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
} from 'antd';
import {
  UserOutlined,
  EditOutlined,
  PlusOutlined,
  DeleteOutlined,
  KeyOutlined,
  CopyOutlined,
  CrownOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  DownloadOutlined,
  StopOutlined,
  SyncOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { authService, modelService } from '../../services';
import type { User, Model, UserVideoTask, VideoTaskStatus } from '../../services';

const { Title, Text, Paragraph } = Typography;
const { TabPane } = Tabs;

const ProfilePage: React.FC = () => {
  const navigate = useNavigate();
  const [user, setUser] = useState<User | null>(null);
  const [models, setModels] = useState<Model[]>([]);
  const [loading, setLoading] = useState(true);
  const [apiKey] = useState<string>('');
  const { message } = App.useApp();

  // Video tasks state
  const [videoTasks, setVideoTasks] = useState<UserVideoTask[]>([]);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [tasksPagination, setTasksPagination] = useState({ page: 1, pageSize: 10, total: 0 });
  const [downloadingTaskId, setDownloadingTaskId] = useState<string | null>(null);
  const [cancellingTaskId, setCancellingTaskId] = useState<string | null>(null);

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
            <Tabs 
              defaultActiveKey="models"
              onChange={(key) => {
                if (key === 'history') {
                  fetchVideoTasks(1, tasksPagination.pageSize);
                }
              }}
            >
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
