/**
 * Register Page — Deep-Space AI Tech Theme
 * Full-screen dark terminal-style registration with animated grid background
 * Superuser registration only with email verification
 */

import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Form, Input, Button, App } from 'antd';
import { UserOutlined, LockOutlined, MailOutlined, SafetyOutlined, ApiOutlined } from '@ant-design/icons';
import { authService } from '../../services';
import type { AxiosError } from 'axios';

interface ApiErrorResponse {
  detail?: string;
}

const SUPERUSER_EMAIL_DOMAIN = 'jouav.com';

// ─── Animated BG canvas (matches Login page) ────────────────
const BgCanvas: React.FC = () => {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    let animId: number;
    let t = 0;
    const resize = () => { canvas.width = innerWidth; canvas.height = innerHeight; };
    resize();
    window.addEventListener('resize', resize);
    const draw = () => {
      const { width: w, height: h } = canvas;
      ctx.clearRect(0, 0, w, h);
      t += 0.006;
      // Grid
      ctx.strokeStyle = 'rgba(0,212,255,0.05)';
      ctx.lineWidth = 1;
      const step = 56;
      for (let x = 0; x < w; x += step) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke(); }
      for (let y = 0; y < h; y += step) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke(); }
      // Pulse rings
      for (let i = 0; i < 6; i++) {
        const cx = (Math.sin(t * 0.3 + i * 1.1) * 0.35 + 0.5) * w;
        const cy = (Math.cos(t * 0.25 + i * 0.8) * 0.35 + 0.5) * h;
        const maxR = 80 + i * 20;
        const phase = (t * 0.5 + i * 0.5) % 1;
        const r = phase * maxR;
        const alpha = (1 - phase) * 0.15;
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(0,212,255,${alpha})`;
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }
      animId = requestAnimationFrame(draw);
    };
    draw();
    return () => { cancelAnimationFrame(animId); window.removeEventListener('resize', resize); };
  }, []);
  return <canvas ref={ref} style={{ position: 'fixed', inset: 0, zIndex: 0, pointerEvents: 'none' }} />;
};

// ─── Shared input style ─────────────────────────────────────
const inputStyle: React.CSSProperties = {
  background: 'rgba(0,0,0,0.4)',
  border: '1px solid rgba(0,212,255,0.15)',
  color: 'var(--color-text-primary)',
  borderRadius: 8,
  fontFamily: 'var(--font-mono)',
};

// ─── Component ──────────────────────────────────────────────
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

      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      if (!emailRegex.test(email)) {
        message.error('请输入有效的邮箱地址');
        return;
      }

      const domain = email.split('@')[1]?.toLowerCase();
      if (domain !== SUPERUSER_EMAIL_DOMAIN) {
        message.error(`只允许 @${SUPERUSER_EMAIL_DOMAIN} 邮箱注册超级用户`);
        return;
      }

      setSendingCode(true);
      const response = await authService.sendVerificationCode(email);
      message.success(response.message);
      setCountdown(60);
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
    <div style={{ minHeight: '100vh', background: '#030812', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--font-body)', position: 'relative', overflow: 'hidden' }}>
      <BgCanvas />

      {/* Radial glow behind card */}
      <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', width: 600, height: 600, background: 'radial-gradient(circle, rgba(0,102,255,0.08) 0%, transparent 70%)', pointerEvents: 'none', zIndex: 1 }} />

      {/* Register card */}
      <div
        style={{
          position: 'relative',
          zIndex: 2,
          width: 440,
          background: 'rgba(8,13,26,0.92)',
          backdropFilter: 'blur(20px)',
          border: '1px solid rgba(0,212,255,0.2)',
          borderRadius: 14,
          boxShadow: '0 0 0 1px rgba(0,212,255,0.05), 0 24px 80px rgba(0,0,0,0.8), 0 0 60px rgba(0,212,255,0.06)',
          overflow: 'hidden',
        }}
      >
        {/* Top accent line */}
        <div style={{ height: 2, background: 'linear-gradient(90deg, transparent, #00d4ff, #0066ff, transparent)' }} />

        <div style={{ padding: '32px 40px 36px' }}>
          {/* Logo area */}
          <div style={{ textAlign: 'center', marginBottom: 28 }}>
            <div style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 52, height: 52, borderRadius: 14, background: 'linear-gradient(135deg,#0066ff,#00d4ff)', boxShadow: '0 0 24px rgba(0,212,255,0.4)', marginBottom: 16 }}>
              <ApiOutlined style={{ fontSize: 24, color: '#fff' }} />
            </div>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 26, fontWeight: 700, color: 'var(--color-cyan)', letterSpacing: '0.08em', textShadow: '0 0 16px rgba(0,212,255,0.4)', lineHeight: 1 }}>
              ModelSquare
            </div>
            <div style={{ marginTop: 6, fontSize: 12, color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)', letterSpacing: '0.08em' }}>
              SUPERUSER REGISTRATION
            </div>
          </div>

          {/* Info banner */}
          <div style={{ background: 'rgba(0,102,255,0.08)', borderRadius: 8, border: '1px solid rgba(0,102,255,0.2)', padding: '10px 14px', marginBottom: 24, display: 'flex', alignItems: 'flex-start', gap: 10 }}>
            <SafetyOutlined style={{ color: 'var(--color-blue)', fontSize: 14, marginTop: 2, flexShrink: 0 }} />
            <span style={{ fontSize: 12, color: 'var(--color-text-secondary)', lineHeight: 1.6 }}>
              仅限 <span style={{ color: 'var(--color-cyan)', fontFamily: 'var(--font-mono)' }}>@{SUPERUSER_EMAIL_DOMAIN}</span> 邮箱注册超级用户。普通用户请联系管理员创建账号。
            </span>
          </div>

          {/* Form */}
          <Form form={form} name="register" onFinish={handleRegister} layout="vertical" size="large">
            <Form.Item
              name="email"
              rules={[
                { required: true, message: '请输入邮箱' },
                { type: 'email', message: '请输入有效的邮箱地址' },
                { validator: validateJouavEmail },
              ]}
              style={{ marginBottom: 14 }}
            >
              <Input
                prefix={<MailOutlined style={{ color: 'var(--color-text-muted)' }} />}
                placeholder={`邮箱 (仅 @${SUPERUSER_EMAIL_DOMAIN})`}
                style={inputStyle}
              />
            </Form.Item>

            <Form.Item
              name="verification_code"
              rules={[
                { required: true, message: '请输入验证码' },
                { len: 6, message: '验证码为6位数字' },
                { pattern: /^\d{6}$/, message: '验证码必须是6位数字' },
              ]}
              style={{ marginBottom: 14 }}
            >
              <Input
                prefix={<SafetyOutlined style={{ color: 'var(--color-text-muted)' }} />}
                placeholder="邮箱验证码"
                maxLength={6}
                style={inputStyle}
                suffix={
                  <Button
                    type="link"
                    size="small"
                    loading={sendingCode}
                    disabled={countdown > 0}
                    onClick={handleSendCode}
                    style={{ color: countdown > 0 ? 'var(--color-text-muted)' : 'var(--color-cyan)', fontFamily: 'var(--font-mono)', fontSize: 12, padding: 0 }}
                  >
                    {countdown > 0 ? `${countdown}s` : '获取验证码'}
                  </Button>
                }
              />
            </Form.Item>

            <Form.Item
              name="username"
              rules={[
                { required: true, message: '请输入用户名' },
                { min: 3, message: '用户名至少3个字符' },
                { max: 64, message: '用户名最多64个字符' },
              ]}
              style={{ marginBottom: 14 }}
            >
              <Input
                prefix={<UserOutlined style={{ color: 'var(--color-text-muted)' }} />}
                placeholder="用户名"
                style={inputStyle}
              />
            </Form.Item>

            <Form.Item
              name="password"
              rules={[
                { required: true, message: '请输入密码' },
                { min: 8, message: '密码至少8个字符' },
              ]}
              style={{ marginBottom: 14 }}
            >
              <Input.Password
                prefix={<LockOutlined style={{ color: 'var(--color-text-muted)' }} />}
                placeholder="密码"
                style={inputStyle}
              />
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
              style={{ marginBottom: 22 }}
            >
              <Input.Password
                prefix={<LockOutlined style={{ color: 'var(--color-text-muted)' }} />}
                placeholder="确认密码"
                style={inputStyle}
              />
            </Form.Item>

            <Form.Item style={{ marginBottom: 16 }}>
              <Button
                type="primary"
                htmlType="submit"
                loading={loading}
                block
                size="large"
                style={{
                  background: 'linear-gradient(135deg,#0066ff,#00d4ff)',
                  border: 'none',
                  borderRadius: 8,
                  fontFamily: 'var(--font-display)',
                  fontWeight: 700,
                  fontSize: 15,
                  letterSpacing: '0.06em',
                  boxShadow: '0 0 24px rgba(0,212,255,0.3)',
                  height: 46,
                }}
              >
                REGISTER
              </Button>
            </Form.Item>
          </Form>

          {/* Login link */}
          <div style={{ textAlign: 'center', borderTop: '1px solid rgba(0,212,255,0.08)', paddingTop: 18 }}>
            <span style={{ fontSize: 13, color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)' }}>
              已有账号？{' '}
              <Link to="/login" style={{ color: 'var(--color-cyan)', textDecoration: 'none', fontWeight: 600 }}>
                立即登录
              </Link>
            </span>
          </div>
        </div>

        {/* Bottom accent line */}
        <div style={{ height: 1, background: 'linear-gradient(90deg, transparent, rgba(0,212,255,0.2), transparent)' }} />
      </div>
    </div>
  );
};

export default RegisterPage;
