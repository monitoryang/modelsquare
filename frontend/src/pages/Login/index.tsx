/**
 * Login Page — Deep-Space AI Tech Theme
 * Full-screen dark terminal-style login with animated grid background
 */

import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Form, Input, Button, App } from 'antd';
import { LockOutlined, MailOutlined, ApiOutlined } from '@ant-design/icons';
import { authService } from '../../services';
import type { AxiosError } from 'axios';

interface ApiErrorResponse { detail?: string; }

// ─── Animated BG canvas ─────────────────────────────────────
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

// ─── Component ──────────────────────────────────────────────
const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [lineIdx, setLineIdx] = useState(0);
  const { message } = App.useApp();

  const bootLines = [
    '[ OK ] Initializing neural engine...',
    '[ OK ] Loading model registry...',
    '[ OK ] GPU cluster online (4x A100)',
    '[ OK ] Inference service ready',
    '> Awaiting authentication...',
  ];

  useEffect(() => {
    if (lineIdx < bootLines.length) {
      const id = setTimeout(() => setLineIdx((i) => i + 1), 420);
      return () => clearTimeout(id);
    }
  }, [lineIdx]);

  const handleLogin = async (values: { email: string; password: string }) => {
    setLoading(true);
    try {
      await authService.login({ username: values.email, password: values.password });
      message.success('登录成功');
      navigate('/');
    } catch (error: unknown) {
      const axiosError = error as AxiosError<ApiErrorResponse>;
      message.error(axiosError.response?.data?.detail || '登录失败，请检查邮箱和密码');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', background: 'var(--color-bg-base)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--font-body)', position: 'relative', overflow: 'hidden' }}>
      <BgCanvas />

      {/* Radial glow behind card */}
      <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', width: 600, height: 600, background: 'radial-gradient(circle, rgba(0,102,255,0.08) 0%, transparent 70%)', pointerEvents: 'none', zIndex: 1 }} />

      {/* Login card */}
      <div
        style={{
          position: 'relative',
          zIndex: 2,
          width: 420,
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

        <div style={{ padding: '36px 40px 40px' }}>
          {/* Logo area */}
          <div style={{ textAlign: 'center', marginBottom: 32 }}>
            <div style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 52, height: 52, borderRadius: 14, background: 'linear-gradient(135deg,#0066ff,#00d4ff)', boxShadow: '0 0 24px rgba(0,212,255,0.4)', marginBottom: 16 }}>
              <ApiOutlined style={{ fontSize: 24, color: '#fff' }} />
            </div>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 26, fontWeight: 700, color: 'var(--color-cyan)', letterSpacing: '0.08em', textShadow: '0 0 16px rgba(0,212,255,0.4)', lineHeight: 1 }}>
              ModelSquare
            </div>
            <div style={{ marginTop: 6, fontSize: 12, color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)', letterSpacing: '0.08em' }}>
              AI INFERENCE PLATFORM
            </div>
          </div>

          {/* Boot log */}
          <div style={{ background: 'rgba(0,0,0,0.4)', borderRadius: 8, border: '1px solid rgba(0,212,255,0.08)', padding: '12px 14px', marginBottom: 28, minHeight: 108 }}>
            {bootLines.slice(0, lineIdx).map((line, i) => (
              <div
                key={i}
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 11,
                  lineHeight: 1.8,
                  color: i === lineIdx - 1 ? 'var(--color-cyan)' : 'rgba(139,164,204,0.7)',
                  letterSpacing: '0.03em',
                }}
              >
                {line}{i === lineIdx - 1 && lineIdx === bootLines.length && <span className="cursor-blink" />}
              </div>
            ))}
          </div>

          {/* Form */}
          <Form name="login" onFinish={handleLogin} layout="vertical" size="large">
            <Form.Item
              name="email"
              rules={[
                { required: true, message: '请输入邮箱' },
                { type: 'email', message: '请输入有效邮箱' },
              ]}
              style={{ marginBottom: 16 }}
            >
              <Input
                prefix={<MailOutlined style={{ color: 'var(--color-text-muted)' }} />}
                placeholder="邮箱地址"
                style={{ background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(0,212,255,0.15)', color: 'var(--color-text-primary)', borderRadius: 8, fontFamily: 'var(--font-mono)' }}
              />
            </Form.Item>

            <Form.Item
              name="password"
              rules={[{ required: true, message: '请输入密码' }]}
              style={{ marginBottom: 24 }}
            >
              <Input.Password
                prefix={<LockOutlined style={{ color: 'var(--color-text-muted)' }} />}
                placeholder="密码"
                style={{ background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(0,212,255,0.15)', color: 'var(--color-text-primary)', borderRadius: 8, fontFamily: 'var(--font-mono)' }}
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
                LOGIN
              </Button>
            </Form.Item>
          </Form>

          {/* Register link */}
          <div style={{ textAlign: 'center', borderTop: '1px solid rgba(0,212,255,0.08)', paddingTop: 20 }}>
            <span style={{ fontSize: 13, color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)' }}>
              还没有账号？{' '}
              <Link to="/register" style={{ color: 'var(--color-cyan)', textDecoration: 'none', fontWeight: 600 }}>
                立即注册
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

export default LoginPage;
