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
  ColorPicker,
  Divider,
  Progress,
  Image,
} from 'antd';
import { UploadOutlined, ArrowLeftOutlined, PlusOutlined, DeleteOutlined, PictureOutlined } from '@ant-design/icons';
import type { UploadFile } from 'antd/es/upload/interface';
import type { Color } from 'antd/es/color-picker';
import { modelService } from '../../services';
import type { AxiosError } from 'axios';

const { Title, Text } = Typography;
const { TextArea } = Input;
const { Option } = Select;

interface ApiErrorResponse {
  detail?: string;
}

interface ClassConfigItem {
  name: string;
  color: string;
}

const DEFAULT_COLORS = [
  '#FF0000', '#00FF00', '#0000FF', '#FFFF00', '#FF00FF', '#00FFFF',
  '#FFA500', '#800080', '#008000', '#000080', '#FF6347', '#4682B4',
];

const ACCEPTED_FILE_TYPES = '.pt,.pth,.onnx,.engine,.trt';
const ACCEPTED_IMAGE_TYPES = '.jpg,.jpeg,.png,.gif,.webp';

const ModelUploadPage: React.FC = () => {
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [thumbnailList, setThumbnailList] = useState<UploadFile[]>([]);
  const [thumbnailPreview, setThumbnailPreview] = useState<string>('');
  const [classConfigs, setClassConfigs] = useState<ClassConfigItem[]>([]);
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [uploadStatus, setUploadStatus] = useState<string>('');
  const { message } = App.useApp();

  const handleAddClass = () => {
    const nextColor = DEFAULT_COLORS[classConfigs.length % DEFAULT_COLORS.length];
    setClassConfigs([...classConfigs, { name: '', color: nextColor }]);
  };

  const handleRemoveClass = (index: number) => {
    setClassConfigs(classConfigs.filter((_, i) => i !== index));
  };

  const handleClassNameChange = (index: number, name: string) => {
    const newConfigs = [...classConfigs];
    newConfigs[index].name = name;
    setClassConfigs(newConfigs);
  };

  const handleClassColorChange = (index: number, color: Color | string) => {
    const newConfigs = [...classConfigs];
    newConfigs[index].color = typeof color === 'string' ? color : color.toHexString();
    setClassConfigs(newConfigs);
  };

  const handleThumbnailChange = (info: { fileList: UploadFile[] }) => {
    setThumbnailList(info.fileList);
    if (info.fileList.length > 0 && info.fileList[0].originFileObj) {
      const reader = new FileReader();
      reader.onload = (e) => {
        setThumbnailPreview(e.target?.result as string);
      };
      reader.readAsDataURL(info.fileList[0].originFileObj);
    } else {
      setThumbnailPreview('');
    }
  };

  const handleSubmit = async (values: {
    name: string;
    description?: string;
    task_type: string;
    framework: string;
    network_type: string;
    version?: string;
    is_public: boolean;
  }) => {
    // Validate class configs
    const validClassConfigs = classConfigs.filter(c => c.name.trim() !== '');
    if (validClassConfigs.length === 0) {
      message.error('请至少添加一个检测类别');
      return;
    }

    // Check for duplicate class names
    const classNames = validClassConfigs.map(c => c.name.trim());
    const hasDuplicates = classNames.length !== new Set(classNames).size;
    if (hasDuplicates) {
      message.error('类别名称不能重复');
      return;
    }

    // Check if file is selected
    if (fileList.length === 0) {
      message.error('请选择模型文件');
      return;
    }

    const file = fileList[0].originFileObj;
    if (!file) {
      message.error('文件无效，请重新选择');
      return;
    }

    setLoading(true);
    setUploadProgress(0);
    setUploadStatus('正在创建模型...');

    try {
      // Step 1: Create model record
      const modelData = {
        name: values.name,
        description: values.description || null,
        task_type: values.task_type,
        framework: values.framework,
        network_type: values.network_type,
        version: values.version || '1.0.0',
        is_public: values.is_public,
        class_config: validClassConfigs.map(c => ({
          name: c.name.trim(),
          color: c.color,
        })),
      };

      const model = await modelService.create(modelData);
      console.log('Created model:', model);
      console.log('Model ID:', model.id);
      
      if (!model.id) {
        throw new Error('模型创建成功但未返回ID');
      }
      
      // Step 2: Upload thumbnail if selected
      if (thumbnailList.length > 0 && thumbnailList[0].originFileObj) {
        setUploadStatus('正在上传缩略图...');
        await modelService.uploadThumbnail(model.id, thumbnailList[0].originFileObj);
      }
      
      // Step 3: Upload model file
      setUploadStatus('正在上传模型文件...');
      await modelService.uploadFile(model.id, file, (percent) => {
        setUploadProgress(percent);
      });

      message.success('模型创建并上传成功');
      navigate('/profile');
    } catch (error: unknown) {
      console.error('Create model error:', error);
      const axiosError = error as AxiosError<ApiErrorResponse>;
      if (axiosError.response) {
        const errorDetail = axiosError.response.data?.detail;
        message.error(errorDetail || `操作失败: ${axiosError.response.status}`);
      } else {
        message.error('操作失败，请稍后重试');
      }
    } finally {
      setLoading(false);
      setUploadStatus('');
      setUploadProgress(0);
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
            label="模型缩略图"
          >
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16 }}>
              <Upload
                fileList={thumbnailList}
                onChange={handleThumbnailChange}
                beforeUpload={() => false}
                maxCount={1}
                accept={ACCEPTED_IMAGE_TYPES}
                showUploadList={false}
              >
                <Button icon={<PictureOutlined />}>选择图片</Button>
              </Upload>
              {thumbnailPreview && (
                <div style={{ position: 'relative' }}>
                  <Image
                    src={thumbnailPreview}
                    alt="缩略图预览"
                    style={{ maxWidth: 200, maxHeight: 150, objectFit: 'cover', borderRadius: 8 }}
                  />
                  <Button
                    type="text"
                    danger
                    icon={<DeleteOutlined />}
                    size="small"
                    style={{ position: 'absolute', top: 4, right: 4, background: 'rgba(255,255,255,0.8)' }}
                    onClick={() => {
                      setThumbnailList([]);
                      setThumbnailPreview('');
                    }}
                  />
                </div>
              )}
            </div>
            <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
              用于模型广场展示，支持 .jpg, .png, .gif, .webp 格式，最大 5MB
            </Text>
          </Form.Item>

          <Divider>检测类别配置</Divider>
          <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
            添加模型能检测的类别，并为每个类别选择颜色（用于检测框和分割mask的绘制）
          </Text>

          {classConfigs.map((config, index) => (
            <Space key={index} style={{ display: 'flex', marginBottom: 8 }} align="baseline">
              <Input
                placeholder="类别名称（如：person, car）"
                value={config.name}
                onChange={(e) => handleClassNameChange(index, e.target.value)}
                style={{ width: 200 }}
              />
              <ColorPicker
                value={config.color}
                onChange={(color) => handleClassColorChange(index, color)}
                showText
              />
              <Button
                type="text"
                danger
                icon={<DeleteOutlined />}
                onClick={() => handleRemoveClass(index)}
              />
            </Space>
          ))}

          <Button
            type="dashed"
            onClick={handleAddClass}
            block
            icon={<PlusOutlined />}
            style={{ marginBottom: 24 }}
          >
            添加类别
          </Button>

          <Form.Item
            label="模型文件"
            required
          >
            <Upload
              fileList={fileList}
              onChange={({ fileList }) => setFileList(fileList)}
              beforeUpload={() => false}
              maxCount={1}
              accept={ACCEPTED_FILE_TYPES}
            >
              <Button icon={<UploadOutlined />}>选择文件</Button>
            </Upload>
            <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
              支持 .pt, .pth, .onnx, .engine, .trt 格式
            </Text>
            {loading && uploadProgress > 0 && (
              <div style={{ marginTop: 16 }}>
                <Text>{uploadStatus}</Text>
                <Progress percent={uploadProgress} status="active" />
              </div>
            )}
          </Form.Item>

          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" loading={loading}>
                {loading ? uploadStatus || '处理中...' : '创建并上传模型'}
              </Button>
              <Button onClick={() => navigate('/profile')} disabled={loading}>
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
