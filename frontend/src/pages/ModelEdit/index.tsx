/**
 * Model Edit Page - Edit existing model configuration (superuser only)
 */

import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
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
  Spin,
} from 'antd';
import { UploadOutlined, ArrowLeftOutlined, PlusOutlined, DeleteOutlined, PictureOutlined } from '@ant-design/icons';
import type { UploadFile } from 'antd/es/upload/interface';
import type { Color } from 'antd/es/color-picker';
import { modelService } from '../../services';
import type { Model } from '../../services';
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

const ModelEditPage: React.FC = () => {
  const navigate = useNavigate();
  const { modelId } = useParams<{ modelId: string }>();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [pageLoading, setPageLoading] = useState(true);
  const [model, setModel] = useState<Model | null>(null);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [thumbnailList, setThumbnailList] = useState<UploadFile[]>([]);
  const [thumbnailPreview, setThumbnailPreview] = useState<string>('');
  const [classConfigs, setClassConfigs] = useState<ClassConfigItem[]>([]);
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [uploadStatus, setUploadStatus] = useState<string>('');
  const { message } = App.useApp();

  useEffect(() => {
    if (modelId) {
      fetchModel();
    }
  }, [modelId]);

  const fetchModel = async () => {
    setPageLoading(true);
    try {
      const modelData = await modelService.get(modelId!);
      setModel(modelData);
      
      // Set form values
      form.setFieldsValue({
        name: modelData.name,
        description: modelData.description,
        network_type: modelData.network_type,
        task_type: modelData.task_type,
        framework: modelData.framework,
        version: modelData.version,
        is_public: modelData.is_public,
      });
      
      // Set class configs
      if (modelData.class_config && Array.isArray(modelData.class_config)) {
        setClassConfigs(modelData.class_config);
      }
      
      // Set thumbnail preview if exists
      if (modelData.thumbnail_url) {
        setThumbnailPreview(modelData.thumbnail_url);
      }
    } catch (error) {
      console.error('Failed to fetch model:', error);
      message.error('获取模型信息失败');
      navigate('/profile');
    } finally {
      setPageLoading(false);
    }
  };

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
    } else if (info.fileList.length === 0) {
      // If thumbnail list is cleared, keep original thumbnail
      if (model?.thumbnail_url) {
        setThumbnailPreview(model.thumbnail_url);
      } else {
        setThumbnailPreview('');
      }
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
    if (!modelId) {
      message.error('模型ID无效');
      return;
    }

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

    setLoading(true);
    setUploadProgress(0);
    setUploadStatus('正在更新模型信息...');

    try {
      // Step 1: Update model record
      const modelData = {
        name: values.name,
        description: values.description || null,
        network_type: values.network_type,
        version: values.version || '1.0.0',
        is_public: values.is_public,
        class_config: validClassConfigs.map(c => ({
          name: c.name.trim(),
          color: c.color,
        })),
      };

      await modelService.update(modelId, modelData);
      
      // Step 2: Upload new thumbnail if selected
      if (thumbnailList.length > 0 && thumbnailList[0].originFileObj) {
        setUploadStatus('正在上传缩略图...');
        await modelService.uploadThumbnail(modelId, thumbnailList[0].originFileObj);
      }
      
      // Step 3: Upload new model file if selected
      if (fileList.length > 0 && fileList[0].originFileObj) {
        setUploadStatus('正在上传模型文件...');
        const uploadResult = await modelService.uploadFile(modelId, fileList[0].originFileObj, (percent) => {
          setUploadProgress(percent);
        });

        // Show Triton deployment status
        if (uploadResult.triton_deployment) {
          const { deployed, triton_loaded, error } = uploadResult.triton_deployment;
          if (deployed && triton_loaded) {
            message.success('模型更新成功，已在 Triton 中加载就绪');
          } else if (deployed && !triton_loaded) {
            message.warning('模型更新成功，已部署到 Triton 但尚未加载（服务器重启后将自动加载）');
          } else {
            message.warning(`模型更新成功，但 Triton 部署失败: ${error || '未知错误'}`);
          }
        } else {
          message.success('模型更新成功');
        }
      } else {
        message.success('模型更新成功');
      }
      navigate('/profile');
    } catch (error: unknown) {
      console.error('Update model error:', error);
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

  if (pageLoading) {
    return (
      <div style={{ textAlign: 'center', padding: 100 }}>
        <Spin size="large" />
        <div style={{ marginTop: 16 }}>
          <Text>加载模型信息...</Text>
        </div>
      </div>
    );
  }

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
        <Title level={3}>编辑模型</Title>
        <Text type="secondary" style={{ display: 'block', marginBottom: 24 }}>
          修改模型配置信息
        </Text>

        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
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
            <Select placeholder="请选择任务类型" disabled>
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
            <Select placeholder="请选择模型框架" disabled>
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
                <Button icon={<PictureOutlined />}>更换图片</Button>
              </Upload>
              {thumbnailPreview && (
                <div style={{ position: 'relative' }}>
                  <Image
                    src={thumbnailPreview}
                    alt="缩略图预览"
                    style={{ maxWidth: 200, maxHeight: 150, objectFit: 'cover', borderRadius: 8 }}
                  />
                  {thumbnailList.length > 0 && (
                    <Button
                      type="text"
                      danger
                      icon={<DeleteOutlined />}
                      size="small"
                      style={{ position: 'absolute', top: 4, right: 4, background: 'rgba(255,255,255,0.8)' }}
                      onClick={() => {
                        setThumbnailList([]);
                        if (model?.thumbnail_url) {
                          setThumbnailPreview(model.thumbnail_url);
                        } else {
                          setThumbnailPreview('');
                        }
                      }}
                    />
                  )}
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
            label="模型文件（可选）"
          >
            <Upload
              fileList={fileList}
              onChange={({ fileList }) => setFileList(fileList)}
              beforeUpload={() => false}
              maxCount={1}
              accept={ACCEPTED_FILE_TYPES}
            >
              <Button icon={<UploadOutlined />}>更换模型文件</Button>
            </Upload>
            <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
              如需更换模型文件，支持 .pt, .pth, .onnx, .engine, .trt 格式
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
                {loading ? uploadStatus || '处理中...' : '保存修改'}
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

export default ModelEditPage;
