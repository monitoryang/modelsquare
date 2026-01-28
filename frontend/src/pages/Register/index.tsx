/**
 * Register Page
 */

import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Card, Form, Input, Button, Typography, Divider, App, Radio } from 'antd';
import { UserOutlined, LockOutlined, MailOutlined } from '@ant-design/icons';
import { authService } from '../../services';
import type { AxiosError } from 'axios';

const { Title, Text } = Typography;

interface ApiErrorResponse {
  detail?: string;
}

const RegisterPage: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();
  const { message } = App.useApp();

  const handleRegister = async (values: {
    email: string;
    username: string;
    password: string;
    confirmPassword: string;
    userType: 'normal' | 'super';
  }) => {
    setLoading(true);
    try {
      await authService.register({
        email: values.email,
        username: values.username,
        password: values.password,
        is_superuser: values.userType === 'super',
      });
      message.success('注册成功，请登录');
      navigate('/login');
    } catch (error: unknown) {
      console.error('Register error:', error);
      const axiosError = error as AxiosError<ApiErrorResponse>;
      if (axiosError.response) {
        console.log('Response data:', axiosError.response.data);
        console.log('Response status:', axiosError.response.status);
        // 服务器返回了错误响应
        const responseData = axiosError.response.data;
        const errorDetail = typeof responseData === 'string' 
          ? responseData 
          : responseData?.detail;
        if (errorDetail) {
          message.error(errorDetail);
        } else {
          message.error(`注册失败: ${axiosError.response.status}`);
        }
      } else if (axiosError.request) {
        // 请求已发送但没有收到响应
        message.error('服务器无响应，请检查网络连接');
      } else {
        // 请求配置出错
        message.error('注册失败，请稍后重试');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      }}
    >
      <Card style={{ width: 400, boxShadow: '0 4px 12px rgba(0,0,0,0.15)' }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Title level={2}>ModelSquare</Title>
          <Text type="secondary">创建新账号</Text>
        </div>

        <Form
          form={form}
          name="register"
          onFinish={handleRegister}
          layout="vertical"
          size="large"
          initialValues={{ userType: 'normal' }}
        >
          <Form.Item
            name="email"
            rules={[
              { required: true, message: '请输入邮箱' },
              { type: 'email', message: '请输入有效的邮箱地址' },
            ]}
          >
            <Input prefix={<MailOutlined />} placeholder="邮箱" />
          </Form.Item>

          <Form.Item
            name="username"
            rules={[
              { required: true, message: '请输入用户名' },
              { min: 3, message: '用户名至少3个字符' },
              { max: 64, message: '用户名最多64个字符' },
            ]}
          >
            <Input prefix={<UserOutlined />} placeholder="用户名" />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[
              { required: true, message: '请输入密码' },
              { min: 8, message: '密码至少8个字符' },
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>

          <Form.Item
            name="confirmPassword"
            dependencies={['password']}
            rules={[
              { required: true, message: '请确认密码' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('password') === value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error('两次输入的密码不一致'));
                },
              }),
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="确认密码" />
          </Form.Item>

          <Form.Item
            name="userType"
            label="用户类型"
            rules={[{ required: true, message: '请选择用户类型' }]}
          >
            <Radio.Group>
              <Radio value="normal">普通用户（仅可使用模型）</Radio>
              <Radio value="super">超级用户（可管理模型）</Radio>
            </Radio.Group>
          </Form.Item>

          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block>
              注册
            </Button>
          </Form.Item>
        </Form>

        <Divider />

        <div style={{ textAlign: 'center' }}>
          <Text>已有账号？ </Text>
          <Link to="/login">立即登录</Link>
        </div>
      </Card>
    </div>
  );
};

export default RegisterPage;
