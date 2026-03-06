/**
 * Register Page - Superuser registration only with email verification
 */

import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Card, Form, Input, Button, Typography, Divider, App, Alert } from 'antd';
import { UserOutlined, LockOutlined, MailOutlined, SafetyOutlined } from '@ant-design/icons';
import { authService } from '../../services';
import type { AxiosError } from 'axios';

const { Title, Text } = Typography;

interface ApiErrorResponse {
  detail?: string;
}

const SUPERUSER_EMAIL_DOMAIN = 'jouav.com';

const RegisterPage: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [sendingCode, setSendingCode] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [form] = Form.useForm();
  const { message } = App.useApp();

  // Countdown timer for resend button
  useEffect(() => {
    if (countdown > 0) {
      const timer = setTimeout(() => setCountdown(countdown - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [countdown]);

  const handleSendCode = async () => {
    try {
      const email = form.getFieldValue('email');
      if (!email) {
        message.error('请先输入邮箱');
        return;
      }

      // Validate email format
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      if (!emailRegex.test(email)) {
        message.error('请输入有效的邮箱地址');
        return;
      }

      // Check if email is from jouav.com
      const domain = email.split('@')[1]?.toLowerCase();
      if (domain !== SUPERUSER_EMAIL_DOMAIN) {
        message.error(`只允许 @${SUPERUSER_EMAIL_DOMAIN} 邮箱注册超级用户`);
        return;
      }

      setSendingCode(true);
      const response = await authService.sendVerificationCode(email);
      message.success(response.message);
      setCountdown(60); // Start 60 second countdown
    } catch (error: unknown) {
      const axiosError = error as AxiosError<ApiErrorResponse>;
      if (axiosError.response?.data?.detail) {
        message.error(axiosError.response.data.detail);
      } else {
        message.error('发送验证码失败，请稍后重试');
      }
    } finally {
      setSendingCode(false);
    }
  };

  const handleRegister = async (values: {
    email: string;
    username: string;
    password: string;
    confirmPassword: string;
    verification_code: string;
  }) => {
    setLoading(true);
    try {
      await authService.register({
        email: values.email,
        username: values.username,
        password: values.password,
        verification_code: values.verification_code,
      });
      message.success('注册成功，请登录');
      navigate('/login');
    } catch (error: unknown) {
      console.error('Register error:', error);
      const axiosError = error as AxiosError<ApiErrorResponse>;
      if (axiosError.response) {
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
        message.error('服务器无响应，请检查网络连接');
      } else {
        message.error('注册失败，请稍后重试');
      }
    } finally {
      setLoading(false);
    }
  };

  // Validate email domain on change
  const validateJouavEmail = (_: unknown, value: string) => {
    if (!value) {
      return Promise.reject(new Error('请输入邮箱'));
    }
    const domain = value.split('@')[1]?.toLowerCase();
    if (domain !== SUPERUSER_EMAIL_DOMAIN) {
      return Promise.reject(new Error(`只允许 @${SUPERUSER_EMAIL_DOMAIN} 邮箱注册`));
    }
    return Promise.resolve();
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
      <Card style={{ width: 420, boxShadow: '0 4px 12px rgba(0,0,0,0.15)' }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Title level={2}>ModelSquare</Title>
          <Text type="secondary">超级用户注册</Text>
        </div>

        <Alert
          message="仅限超级用户注册"
          description={`只有 @${SUPERUSER_EMAIL_DOMAIN} 邮箱可以注册超级用户。普通用户请联系管理员创建账号。`}
          type="info"
          showIcon
          style={{ marginBottom: 24 }}
        />

        <Form
          form={form}
          name="register"
          onFinish={handleRegister}
          layout="vertical"
          size="large"
        >
          <Form.Item
            name="email"
            rules={[
              { required: true, message: '请输入邮箱' },
              { type: 'email', message: '请输入有效的邮箱地址' },
              { validator: validateJouavEmail },
            ]}
          >
            <Input 
              prefix={<MailOutlined />} 
              placeholder={`邮箱 (仅 @${SUPERUSER_EMAIL_DOMAIN})`} 
            />
          </Form.Item>

          <Form.Item
            name="verification_code"
            rules={[
              { required: true, message: '请输入验证码' },
              { len: 6, message: '验证码为6位数字' },
              { pattern: /^\d{6}$/, message: '验证码必须是6位数字' },
            ]}
          >
            <Input.Search
              prefix={<SafetyOutlined />}
              placeholder="邮箱验证码"
              maxLength={6}
              enterButton={
                <Button 
                  type="primary" 
                  loading={sendingCode}
                  disabled={countdown > 0}
                  onClick={handleSendCode}
                  style={{ minWidth: 110 }}
                >
                  {countdown > 0 ? `${countdown}s 后重试` : '获取验证码'}
                </Button>
              }
              onSearch={() => {}} // Prevent default search behavior
            />
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
