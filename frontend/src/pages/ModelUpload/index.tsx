/**
 * Model Upload Page - Upload and create new models (superuser only)
 */

import React, { useState, useMemo } from 'react';
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
  Checkbox,
  Alert,
} from 'antd';
import { UploadOutlined, ArrowLeftOutlined, PlusOutlined, DeleteOutlined, PictureOutlined, FileTextOutlined, ThunderboltOutlined } from '@ant-design/icons';
import type { UploadFile } from 'antd/es/upload/interface';
import type { Color } from 'antd/es/color-picker';
import { modelService } from '../../services';
import type { TensorRTConversionProgress, OwlDeploymentProgress } from '../../services';
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
  const [uploadRate, setUploadRate] = useState<number>(0); // bytes/s
  const [uploadStatus, setUploadStatus] = useState<string>('');
  const [convertToTensorRT, setConvertToTensorRT] = useState(false);
  const [conversionProgress, setConversionProgress] = useState<number>(0);
  const [conversionStatus, setConversionStatus] = useState<string>('');
  const [isConverting, setIsConverting] = useState(false);
  const { message } = App.useApp();

  // OWL-specific state
  const [owlTextEncoderList, setOwlTextEncoderList] = useState<UploadFile[]>([]);
  const [owlTextEncoderLargeList, setOwlTextEncoderLargeList] = useState<UploadFile[]>([]);
  const [owlBaseEncoderList, setOwlBaseEncoderList] = useState<UploadFile[]>([]);
  const [owlLargeEncoderList, setOwlLargeEncoderList] = useState<UploadFile[]>([]);
  const [owlTokenizerFiles, setOwlTokenizerFiles] = useState<UploadFile[]>([]);
  const [owlDeployProgress, setOwlDeployProgress] = useState<number>(0);
  const [owlDeployMessage, setOwlDeployMessage] = useState<string>('');
  const [isOwlDeploying, setIsOwlDeploying] = useState(false);

  // Watch form values for framework and network type
  const framework = Form.useWatch('framework', form);
  const networkType = Form.useWatch('network_type', form);
  const isOwlv2 = networkType === 'OWLv2';
  
  // Check if file is ONNX
  const isOnnxFile = useMemo(() => {
    if (fileList.length === 0) return false;
    const fileName = fileList[0].name?.toLowerCase() || '';
    return fileName.endsWith('.onnx');
  }, [fileList]);

  // Show conversion option when TensorRT framework is selected and ONNX file is uploaded
  const showConversionOption = framework === 'tensorrt' && isOnnxFile;

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

  const generateRandomColor = (): string => {
    const h = Math.floor(Math.random() * 360);
    const s = Math.floor(Math.random() * 30) + 55; // 55-85%
    const l = Math.floor(Math.random() * 20) + 45; // 45-65%
    // Convert HSL to hex
    const hslToHex = (h: number, s: number, l: number): string => {
      s /= 100;
      l /= 100;
      const a = s * Math.min(l, 1 - l);
      const f = (n: number) => {
        const k = (n + h / 30) % 12;
        const color = l - a * Math.max(Math.min(k - 3, 9 - k, 1), -1);
        return Math.round(255 * color).toString(16).padStart(2, '0');
      };
      return `#${f(0)}${f(8)}${f(4)}`;
    };
    return hslToHex(h, s, l);
  };

  const handleClassFileUpload = (file: File) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      if (!text) return;
      const lines = text.split(/\r?\n/).map(l => l.trim()).filter(l => l.length > 0);
      if (lines.length === 0) {
        message.warning('文件中没有有效的类别名称');
        return;
      }
      const newConfigs: ClassConfigItem[] = lines.map((name) => ({
        name,
        color: generateRandomColor(),
      }));
      setClassConfigs(newConfigs);
      message.success(`已从文件导入 ${lines.length} 个类别`);
    };
    reader.readAsText(file);
    return false; // prevent auto upload
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

  // Format upload/download rate as human-readable string
  const formatRate = (bytesPerSec: number): string => {
    if (bytesPerSec <= 0) return '';
    if (bytesPerSec >= 1024 * 1024) {
      return `${(bytesPerSec / (1024 * 1024)).toFixed(1)} MB/s`;
    }
    if (bytesPerSec >= 1024) {
      return `${(bytesPerSec / 1024).toFixed(0)} KB/s`;
    }
    return `${bytesPerSec.toFixed(0)} B/s`;
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
    // --- OWLv2 specific flow ---
    if (isOwlv2) {
      // Validate 4 OWL ONNX files
      const textFile = owlTextEncoderList[0]?.originFileObj;
      const textLargeFile = owlTextEncoderLargeList[0]?.originFileObj;
      const baseFile = owlBaseEncoderList[0]?.originFileObj;
      const largeFile = owlLargeEncoderList[0]?.originFileObj;
      if (!textFile || !textLargeFile || !baseFile || !largeFile) {
        message.error('请选择所有 4 个 OWL ONNX 文件');
        return;
      }

      // Validate tokenizer files (5 required)
      const requiredTokenizerNames = [
        'vocab.json', 'merges.txt', 'tokenizer_config.json',
        'special_tokens_map.json', 'added_tokens.json',
      ];
      const tokenizerMap: Record<string, File> = {};
      for (const uf of owlTokenizerFiles) {
        if (uf.originFileObj) {
          tokenizerMap[uf.name] = uf.originFileObj;
        }
      }
      const missingTokenizer = requiredTokenizerNames.filter(n => !tokenizerMap[n]);
      if (missingTokenizer.length > 0) {
        message.error(`缺少 Tokenizer 文件: ${missingTokenizer.join(', ')}`);
        return;
      }

      setLoading(true);
      setUploadStatus('正在创建模型...');

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

        const model = await modelService.create(modelData);
        if (!model.id) {
          throw new Error('模型创建成功但未返回ID');
        }

        // Upload thumbnail if selected
        if (thumbnailList.length > 0 && thumbnailList[0].originFileObj) {
          setUploadStatus('正在上传缩略图...');
          await modelService.uploadThumbnail(model.id, thumbnailList[0].originFileObj);
        }

        // Upload OWL files with SSE progress
        setIsOwlDeploying(true);
        setOwlDeployProgress(0);
        setOwlDeployMessage('准备上传 OWL 模型文件...');

        await new Promise<void>((resolve, reject) => {
          modelService.uploadOwlFiles(
            model.id,
            textFile,
            textLargeFile,
            baseFile,
            largeFile,
            {
              vocab_json: tokenizerMap['vocab.json'],
              merges_txt: tokenizerMap['merges.txt'],
              tokenizer_config: tokenizerMap['tokenizer_config.json'],
              special_tokens_map: tokenizerMap['special_tokens_map.json'],
              added_tokens: tokenizerMap['added_tokens.json'],
            },
            (data: OwlDeploymentProgress) => {
              setOwlDeployProgress(data.progress);
              setOwlDeployMessage(data.message);
            },
            (data: OwlDeploymentProgress) => {
              setIsOwlDeploying(false);
              if (data.status === 'completed') {
                const gpuInfos = [
                  { name: 'Text Encoder(base)', id: data.owl_text_encoder_gpu_id },
                  { name: 'Image Encoder(base)', id: data.owl_image_encoder_gpu_id },
                  { name: 'Text Encoder(large)', id: data.owl_text_encoder_large_gpu_id },
                  { name: 'Image Encoder(large)', id: data.owl_image_encoder_large_gpu_id },
                ].filter(item => item.id !== undefined && item.id !== null);

                if (gpuInfos.length > 0) {
                  const gpuSummary = gpuInfos.map(item => `${item.name}: GPU ${item.id}`).join('，');
                  message.success(`OWL 模型上传并部署完成（${gpuSummary}）`);
                } else {
                  message.success('OWL 模型上传并部署完成');
                }
                resolve();
              } else {
                message.error(`OWL 部署失败: ${data.error || '未知错误'}`);
                reject(new Error(data.error || 'Deployment failed'));
              }
            },
            (error: Error) => {
              setIsOwlDeploying(false);
              message.error(`OWL 部署失败: ${error.message}`);
              reject(error);
            }
          );
        });

        navigate('/profile');
      } catch (error: unknown) {
        console.error('Create OWL model error:', error);
        const axiosError = error as AxiosError<ApiErrorResponse>;
        if (axiosError.response) {
          const errorDetail = axiosError.response.data?.detail;
          message.error(errorDetail || `操作失败: ${axiosError.response.status}`);
        } else if (error instanceof Error) {
          // Already handled in deployment flow
        } else {
          message.error('操作失败，请稍后重试');
        }
      } finally {
        setLoading(false);
        setIsOwlDeploying(false);
        setUploadStatus('');
        setOwlDeployProgress(0);
        setOwlDeployMessage('');
      }
      return;
    }

    // --- Standard (YOLO) flow ---
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

    // Determine if we need to convert ONNX to TensorRT
    const needsConversion = showConversionOption && convertToTensorRT;

    setLoading(true);
    setUploadProgress(0);
    setUploadStatus('正在创建模型...');

    try {
      // Step 1: Create model record (with target framework, not upload format)
      const modelData = {
        name: values.name,
        description: values.description || null,
        task_type: values.task_type,
        framework: values.framework, // Keep target framework
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
      const uploadResult = await modelService.uploadFile(model.id, file, (percent, _loaded, _total, rate) => {
        setUploadProgress(percent);
        setUploadRate(rate);
      });

      // Step 4: Convert to TensorRT if needed
      if (needsConversion) {
        setUploadStatus('正在转换为 TensorRT...');
        setUploadProgress(100);
        setIsConverting(true);
        setConversionProgress(0);
        setConversionStatus('准备转换...');

        await new Promise<void>((resolve, reject) => {
          modelService.convertToTensorRT(
            model.id,
            true, // use FP16
            (data: TensorRTConversionProgress) => {
              setConversionProgress(data.progress);
              setConversionStatus(data.message);
            },
            (data: TensorRTConversionProgress) => {
              setIsConverting(false);
              if (data.status === 'completed') {
                if (data.triton_loaded) {
                  message.success('模型转换成功，已在 Triton 中加载就绪');
                } else {
                  message.warning('模型转换成功，但 Triton 加载失败');
                }
                resolve();
              } else {
                message.error(`转换失败: ${data.error || '未知错误'}`);
                reject(new Error(data.error || 'Conversion failed'));
              }
            },
            (error: Error) => {
              setIsConverting(false);
              message.error(`转换失败: ${error.message}`);
              reject(error);
            }
          );
        });
      } else {
        // Show Triton deployment status for non-conversion uploads
        if (uploadResult.triton_deployment) {
          const { deployed, triton_loaded, error } = uploadResult.triton_deployment;
          if (deployed && triton_loaded) {
            message.success('模型创建并上传成功，已在 Triton 中加载就绪');
          } else if (deployed && !triton_loaded) {
            message.warning('模型上传成功，已部署到 Triton 但尚未加载（服务器重启后将自动加载）');
          } else {
            message.warning(`模型上传成功，但 Triton 部署失败: ${error || '未知错误'}`);
          }
        } else {
          message.success('模型创建并上传成功');
        }
      }
      
      navigate('/profile');
    } catch (error: unknown) {
      console.error('Create model error:', error);
      const axiosError = error as AxiosError<ApiErrorResponse>;
      if (axiosError.response) {
        const errorDetail = axiosError.response.data?.detail;
        message.error(errorDetail || `操作失败: ${axiosError.response.status}`);
      } else if (error instanceof Error) {
        // Already handled in conversion flow
      } else {
        message.error('操作失败，请稍后重试');
      }
    } finally {
      setLoading(false);
      setIsConverting(false);
      setUploadStatus('');
      setUploadProgress(0);
      setUploadRate(0);
      setConversionProgress(0);
      setConversionStatus('');
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
        <Title level={3}>注册模型</Title>
        <Text type="secondary" style={{ display: 'block', marginBottom: 24 }}>
          填写模型信息并注册模型文件
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
              <Option value="OWLv2">OWLv2 (开放词汇检测)</Option>
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

          {!isOwlv2 && (
            <>
              <Divider>检测类别配置</Divider>
              <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
                添加模型能检测的类别，并为每个类别选择颜色（用于检测框和分割mask的绘制）
              </Text>

              <Space style={{ marginBottom: 16 }}>
                <Upload
                  accept=".txt"
                  showUploadList={false}
                  beforeUpload={handleClassFileUpload}
                >
                  <Button icon={<FileTextOutlined />}>导入 class.txt</Button>
                </Upload>
                {classConfigs.length > 0 && (
                  <Text type="secondary">{classConfigs.length} 个类别</Text>
                )}
              </Space>

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
                
                {showConversionOption && (
                  <Alert
                    type="info"
                    showIcon
                    icon={<ThunderboltOutlined />}
                    style={{ marginTop: 12 }}
                    message={
                      <Checkbox
                        checked={convertToTensorRT}
                        onChange={(e) => setConvertToTensorRT(e.target.checked)}
                      >
                        自动转换为 TensorRT (FP16)
                      </Checkbox>
                    }
                    description="上传 ONNX 模型后自动使用 FP16 精度转换为 TensorRT 引擎，可获得更快的推理速度。转换可能需要几分钟。"
                  />
                )}
                
                {loading && uploadProgress > 0 && !isConverting && (
                  <div style={{ marginTop: 16 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                      <Text>{uploadStatus}</Text>
                      {uploadRate > 0 && (
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {formatRate(uploadRate)}
                        </Text>
                      )}
                    </div>
                    <Progress percent={uploadProgress} status="active" />
                  </div>
                )}
                
                {isConverting && (
                  <div style={{ marginTop: 16 }}>
                    <Text strong style={{ color: '#1890ff' }}>
                      <ThunderboltOutlined style={{ marginRight: 8 }} />
                      {conversionStatus || '正在转换为 TensorRT...'}
                    </Text>
                    <Progress 
                      percent={conversionProgress} 
                      status="active" 
                      strokeColor={{
                        '0%': '#108ee9',
                        '100%': '#87d068',
                      }}
                    />
                    <Text type="secondary" style={{ display: 'block', marginTop: 4 }}>
                      TensorRT 转换可能需要几分钟，请耐心等待...
                    </Text>
                  </div>
                )}
              </Form.Item>
            </>
          )}

          {isOwlv2 && (
            <>
              <Divider>OWL 模型文件</Divider>
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
                message="OWLv2 开放词汇检测"
                description="OWLv2 无需预定义类别，检测目标通过推理时输入的文本提示词指定。请上传 4 个 ONNX 文件（2 个 Text Encoder + 2 个 Image Encoder），上传后将自动部署到 Triton 推理服务器（Image Encoder 会自动转换为 TensorRT）。"
              />

              <Form.Item label="Text Encoder (base) ONNX" required>
                <Upload
                  fileList={owlTextEncoderList}
                  onChange={({ fileList }) => setOwlTextEncoderList(fileList)}
                  beforeUpload={() => false}
                  maxCount={1}
                  accept=".onnx"
                >
                  <Button icon={<UploadOutlined />}>选择 base Text Encoder</Button>
                </Upload>
                <Text type="secondary" style={{ display: 'block', marginTop: 4 }}>
                  base-patch16 文本编码器 ONNX（512 维，来自 owlv2-base-patch16-ensemble）
                </Text>
              </Form.Item>

              <Form.Item label="Text Encoder (large) ONNX" required>
                <Upload
                  fileList={owlTextEncoderLargeList}
                  onChange={({ fileList }) => setOwlTextEncoderLargeList(fileList)}
                  beforeUpload={() => false}
                  maxCount={1}
                  accept=".onnx"
                >
                  <Button icon={<UploadOutlined />}>选择 large Text Encoder</Button>
                </Upload>
                <Text type="secondary" style={{ display: 'block', marginTop: 4 }}>
                  large-patch14 文本编码器 ONNX（768 维，来自 owlv2-large-patch14-ensemble）
                </Text>
              </Form.Item>

              <Form.Item label="Image Encoder (base-patch16) ONNX" required>
                <Upload
                  fileList={owlBaseEncoderList}
                  onChange={({ fileList }) => setOwlBaseEncoderList(fileList)}
                  beforeUpload={() => false}
                  maxCount={1}
                  accept=".onnx"
                >
                  <Button icon={<UploadOutlined />}>选择 base-patch16 Encoder</Button>
                </Upload>
                <Text type="secondary" style={{ display: 'block', marginTop: 4 }}>
                  图像编码器 base-patch16 变体（输入 960x960，将转换为 TensorRT FP16）
                </Text>
              </Form.Item>

              <Form.Item label="Image Encoder (large-patch14) ONNX" required>
                <Upload
                  fileList={owlLargeEncoderList}
                  onChange={({ fileList }) => setOwlLargeEncoderList(fileList)}
                  beforeUpload={() => false}
                  maxCount={1}
                  accept=".onnx"
                >
                  <Button icon={<UploadOutlined />}>选择 large-patch14 Encoder</Button>
                </Upload>
                <Text type="secondary" style={{ display: 'block', marginTop: 4 }}>
                  图像编码器 large-patch14 变体（输入 1008x1008，将转换为 TensorRT FP16）
                </Text>
              </Form.Item>

              <Divider orientation="left" plain>Tokenizer 配置文件</Divider>
              <Form.Item label="CLIPTokenizer 文件 (5个)" required>
                <Upload
                  fileList={owlTokenizerFiles}
                  onChange={({ fileList }) => setOwlTokenizerFiles(fileList)}
                  beforeUpload={() => false}
                  multiple
                  accept=".json,.txt"
                >
                  <Button icon={<UploadOutlined />}>选择 Tokenizer 文件</Button>
                </Upload>
                <Text type="secondary" style={{ display: 'block', marginTop: 4 }}>
                  需要 5 个文件: vocab.json, merges.txt, tokenizer_config.json, special_tokens_map.json, added_tokens.json
                </Text>
              </Form.Item>

              {isOwlDeploying && (
                <div style={{ marginTop: 8, marginBottom: 16 }}>
                  <Text strong style={{ color: '#1890ff' }}>
                    <ThunderboltOutlined style={{ marginRight: 8 }} />
                    {owlDeployMessage || '正在部署 OWL 模型...'}
                  </Text>
                  <Progress
                    percent={owlDeployProgress}
                    status="active"
                    strokeColor={{
                      '0%': '#108ee9',
                      '100%': '#87d068',
                    }}
                  />
                  <Text type="secondary" style={{ display: 'block', marginTop: 4 }}>
                    TensorRT 转换可能需要较长时间，请耐心等待...
                  </Text>
                </div>
              )}
            </>
          )}

          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" loading={loading}>
                {loading ? uploadStatus || '处理中...' : '创建并注册模型'}
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
