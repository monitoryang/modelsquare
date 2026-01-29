/**
 * Model Upload Page - Upload and create new models (superuser only)
 */

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Card,
  Form,
  Input,
  Select,
  Button,
  Upload,
  Typography,
  Space,
  Switch,
  App,
} from 'antd';
import { UploadOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import type { UploadFile } from 'antd/es/upload/interface';
import { modelService } from '../../services';
import type { AxiosError } from 'axios';

const { Title, Text } = Typography;
const { TextArea } = Input;
const { Option } = Select;

interface ApiErrorResponse {
  detail?: string;
}

const ModelUploadPage: React.FC = () => {
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const { message } = App.useApp();

  const handleSubmit = async (values: {
    name: string;
    description?: string;
    task_type: string;
    framework: string;
    network_type: string;
    version?: string;
    is_public: boolean;
  }) => {
    setLoading(true);
    try {
      const modelData = {
        name: values.name,
        description: values.description || null,
        task_type: values.task_type,
        framework: values.framework,
        network_type: values.network_type,
        version: values.version || '1.0.0',
        is_public: values.is_public,
      };

      await modelService.create(modelData);
      message.success('模型创建成功');
      navigate('/profile');
    } catch (error: unknown) {
      console.error('Create model error:', error);
      const axiosError = error as AxiosError<ApiErrorResponse>;
      if (axiosError.response) {
        const errorDetail = axiosError.response.data?.detail;
        message.error(errorDetail || `创建失败: ${axiosError.response.status}`);
      } else {
        message.error('创建失败，请稍后重试');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 800, margin: '0 auto', padding: '24px' }}>
      <Space style={{ marginBottom: 24 }}>
        <Button
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate('/profile')}
        >
          返回
        </Button>
      </Space>

      <Card>
        <Title level={3}>上传新模型</Title>
        <Text type="secondary" style={{ display: 'block', marginBottom: 24 }}>
          填写模型信息并上传模型文件
        </Text>

        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          initialValues={{
            is_public: false,
            version: '1.0.0',
            framework: 'pytorch',
            task_type: 'detection',
            network_type: 'YOLOv8',
          }}
        >
          <Form.Item
            name="name"
            label="模型名称"
            rules={[
              { required: true, message: '请输入模型名称' },
              { max: 128, message: '模型名称最多128个字符' },
            ]}
          >
            <Input placeholder="请输入模型名称" />
          </Form.Item>

          <Form.Item
            name="description"
            label="模型描述"
          >
            <TextArea
              rows={4}
              placeholder="请输入模型描述（可选）"
            />
          </Form.Item>

          <Form.Item
            name="network_type"
            label="网络类型"
            rules={[{ required: true, message: '请选择网络类型' }]}
          >
            <Select placeholder="请选择网络类型">
              <Option value="YOLOv8">YOLOv8</Option>
              <Option value="YOLO11">YOLO11</Option>
            </Select>
          </Form.Item>

          <Form.Item
            name="task_type"
            label="任务类型"
            rules={[{ required: true, message: '请选择任务类型' }]}
          >
            <Select placeholder="请选择任务类型">
              <Option value="classification">图像分类</Option>
              <Option value="detection">目标检测</Option>
              <Option value="segmentation">图像分割</Option>
              <Option value="multimodal">多模态</Option>
              <Option value="nlp">自然语言处理</Option>
            </Select>
          </Form.Item>

          <Form.Item
            name="framework"
            label="模型框架"
            rules={[{ required: true, message: '请选择模型框架' }]}
          >
            <Select placeholder="请选择模型框架">
              <Option value="pytorch">PyTorch</Option>
              <Option value="onnx">ONNX</Option>
              <Option value="tensorrt">TensorRT</Option>
            </Select>
          </Form.Item>

          <Form.Item
            name="version"
            label="版本号"
          >
            <Input placeholder="1.0.0" />
          </Form.Item>

          <Form.Item
            name="is_public"
            label="公开模型"
            valuePropName="checked"
          >
            <Switch checkedChildren="公开" unCheckedChildren="私有" />
          </Form.Item>

          <Form.Item
            label="模型文件"
          >
            <Upload
              fileList={fileList}
              onChange={({ fileList }) => setFileList(fileList)}
              beforeUpload={() => false}
              maxCount={1}
            >
              <Button icon={<UploadOutlined />}>选择文件</Button>
            </Upload>
            <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
              支持 .pt, .onnx, .engine 格式（文件上传功能开发中）
            </Text>
          </Form.Item>

          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" loading={loading}>
                创建模型
              </Button>
              <Button onClick={() => navigate('/profile')}>
                取消
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
};

export default ModelUploadPage;
