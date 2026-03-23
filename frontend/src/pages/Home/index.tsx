/**
 * Home Page — Deep-Space AI Tech Theme
 * Hero with animated grid, stat counters, model cards with glow effects
 */

import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Input, Select, Tag, Spin, Empty } from 'antd';
import {
  SearchOutlined,
  EyeOutlined,
  HeartOutlined,
  RocketOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ThunderboltOutlined,
  ApiOutlined,
  CodeOutlined,
} from '@ant-design/icons';
import { modelService } from '../../services';
import type { Model } from '../../services';

const { Search } = Input;
const { Option } = Select;

// ─── Color maps ─────────────────────────────────────────────
const TASK_COLORS: Record<string, string> = {
  classification: '#0066ff',
  detection:      '#00d4ff',
  segmentation:   '#7c3aed',
  multimodal:     '#f59e0b',
  nlp:            '#00ff9d',
};
const TASK_LABELS: Record<string, string> = {
  classification: '分类',
  detection:      '检测',
  segmentation:   '分割',
  multimodal:     '多模态',
  nlp:            'NLP',
};
const FW_COLORS: Record<string, string> = {
  pytorch:   '#ff4d6a',
  onnx:      '#0066ff',
  tensorrt:  '#00d4ff',
};

// ─── Animated Grid Canvas ───────────────────────────────────
const GridCanvas: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId: number;
    let t = 0;

    const resize = () => {
      canvas.width  = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
    };
    resize();
    window.addEventListener('resize', resize);

    const draw = () => {
      const { width: w, height: h } = canvas;
      ctx.clearRect(0, 0, w, h);
      t += 0.008;

      // Grid lines
      const step = 48;
      ctx.strokeStyle = 'rgba(0,212,255,0.06)';
      ctx.lineWidth = 1;
      for (let x = 0; x < w; x += step) {
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
      }
      for (let y = 0; y < h; y += step) {
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
      }

      // Floating nodes
      const nodes = 12;
      for (let i = 0; i < nodes; i++) {
        const px = (Math.sin(t * 0.4 + i * 1.3) * 0.4 + 0.5) * w;
        const py = (Math.cos(t * 0.3 + i * 0.9) * 0.4 + 0.5) * h;
        const r = 2 + Math.sin(t + i) * 1;
        const alpha = 0.3 + Math.sin(t * 0.8 + i) * 0.2;
        ctx.beginPath();
        ctx.arc(px, py, r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(0,212,255,${alpha})`;
        ctx.fill();
        // Pulse ring
        ctx.beginPath();
        ctx.arc(px, py, r + 6 + Math.sin(t * 2 + i) * 4, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(0,212,255,${alpha * 0.3})`;
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      animId = requestAnimationFrame(draw);
    };
    draw();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
    />
  );
};

// ─── Stat Item ───────────────────────────────────────────────
const StatItem: React.FC<{ value: string; label: string; icon: React.ReactNode }> = ({ value, label, icon }) => (
  <div style={{ textAlign: 'center', padding: '0 24px', borderRight: '1px solid rgba(0,212,255,0.12)' }}>
    <div style={{ color: 'var(--color-cyan)', fontFamily: 'var(--font-mono)', fontSize: 28, fontWeight: 700, lineHeight: 1.1, textShadow: '0 0 20px rgba(0,212,255,0.5)' }}>
      {icon} {value}
    </div>
    <div style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase', marginTop: 4 }}>
      {label}
    </div>
  </div>
);

// ─── Model Card ─────────────────────────────────────────────
const ModelCard: React.FC<{ model: Model; onClick: () => void }> = ({ model, onClick }) => {
  const [hovered, setHovered] = useState(false);
  const taskColor = TASK_COLORS[model.task_type] ?? '#00d4ff';

  return (
    <div
      className="model-card-shimmer"
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: 'var(--color-bg-card)',
        border: `1px solid ${hovered ? 'rgba(0,212,255,0.35)' : 'rgba(0,212,255,0.1)'}`,
        borderRadius: 10,
        overflow: 'hidden',
        cursor: 'pointer',
        transition: 'all 0.22s ease',
        transform: hovered ? 'translateY(-4px)' : 'none',
        boxShadow: hovered
          ? '0 8px 40px rgba(0,0,0,0.7), 0 0 24px rgba(0,212,255,0.12)'
          : '0 2px 16px rgba(0,0,0,0.5)',
      }}
    >
      {/* Cover / Thumbnail */}
      <div style={{ height: 148, position: 'relative', overflow: 'hidden' }}>
        {model.thumbnail_url ? (
          <img src={model.thumbnail_url} alt={model.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        ) : (
          <div style={{ width: '100%', height: '100%', background: 'linear-gradient(135deg, #0a1020 0%, #0d1e3a 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
            <div style={{ position: 'absolute', inset: 0, backgroundImage: 'linear-gradient(rgba(0,212,255,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(0,212,255,0.04) 1px, transparent 1px)', backgroundSize: '24px 24px' }} />
            <ApiOutlined style={{ fontSize: 36, color: taskColor, opacity: 0.7, filter: `drop-shadow(0 0 8px ${taskColor})` }} />
          </div>
        )}
        {/* Triton badge */}
        <div style={{ position: 'absolute', top: 8, right: 8 }}>
          {model.triton_status?.loaded ? (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 8px', borderRadius: 12, background: 'rgba(0,255,157,0.15)', border: '1px solid rgba(0,255,157,0.4)', fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--color-green)', letterSpacing: '0.05em' }}>
              <CheckCircleOutlined /> LIVE
            </span>
          ) : (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 8px', borderRadius: 12, background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.12)', fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--color-text-muted)', letterSpacing: '0.05em' }}>
              <CloseCircleOutlined /> OFFLINE
            </span>
          )}
        </div>
      </div>

      {/* Body */}
      <div style={{ padding: '14px 16px' }}>
        {/* Task / Framework tags */}
        <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
          <span style={{ padding: '2px 8px', borderRadius: 4, background: `${taskColor}18`, border: `1px solid ${taskColor}55`, color: taskColor, fontSize: 10, fontFamily: 'var(--font-mono)', fontWeight: 700, letterSpacing: '0.06em' }}>
            {TASK_LABELS[model.task_type] ?? model.task_type}
          </span>
          <span style={{ padding: '2px 8px', borderRadius: 4, background: `${FW_COLORS[model.framework] ?? '#666'}18`, border: `1px solid ${FW_COLORS[model.framework] ?? '#666'}55`, color: FW_COLORS[model.framework] ?? '#aaa', fontSize: 10, fontFamily: 'var(--font-mono)', fontWeight: 700, letterSpacing: '0.06em' }}>
            {model.framework.toUpperCase()}
          </span>
        </div>

        {/* Name */}
        <div style={{ fontWeight: 600, fontSize: 15, color: 'var(--color-text-primary)', fontFamily: 'var(--font-display)', marginBottom: 6, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {model.name}
        </div>

        {/* Description */}
        <div style={{ fontSize: 13, color: 'var(--color-text-muted)', lineHeight: 1.5, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden', minHeight: 40, marginBottom: 12 }}>
          {model.description || '暂无描述'}
        </div>

        {/* Stats */}
        <div style={{ display: 'flex', gap: 16, borderTop: '1px solid var(--color-border)', paddingTop: 10 }}>
          <span style={{ fontSize: 12, color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)', display: 'flex', alignItems: 'center', gap: 4 }}>
            <EyeOutlined /> {model.download_count}
          </span>
          <span style={{ fontSize: 12, color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)', display: 'flex', alignItems: 'center', gap: 4 }}>
            <HeartOutlined /> {model.like_count}
          </span>
        </div>
      </div>
    </div>
  );
};

// ─── HomePage ────────────────────────────────────────────────
const HomePage: React.FC = () => {
  const navigate = useNavigate();
  const [models, setModels] = useState<Model[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [taskFilter, setTaskFilter] = useState<string | undefined>();

  useEffect(() => { fetchModels(); }, [taskFilter]);

  const fetchModels = async () => {
    setLoading(true);
    try {
      const res = await modelService.list({ task_type: taskFilter, keyword: searchKeyword, page_size: 12 });
      setModels(res.items);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ fontFamily: 'var(--font-body)' }}>

      {/* ── Hero ── */}
      <div
        className="fade-in-up"
        style={{
          position: 'relative',
          borderRadius: 12,
          overflow: 'hidden',
          marginBottom: 28,
          minHeight: 260,
          background: 'linear-gradient(135deg, #040c1e 0%, #060f28 60%, #08152e 100%)',
          border: '1px solid rgba(0,212,255,0.15)',
          boxShadow: '0 0 60px rgba(0,212,255,0.06)',
        }}
      >
        <GridCanvas />

        {/* Content */}
        <div style={{ position: 'relative', zIndex: 2, padding: '48px 48px 40px', display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center' }}>
          {/* Badge */}
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '4px 14px', borderRadius: 20, border: '1px solid rgba(0,212,255,0.3)', background: 'rgba(0,212,255,0.06)', fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--color-cyan)', letterSpacing: '0.1em', marginBottom: 20 }}>
            <span className="status-dot" style={{ width: 6, height: 6 }} />
            REAL-TIME AI INFERENCE PLATFORM
          </div>

          {/* Title */}
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 'clamp(32px, 5vw, 54px)', fontWeight: 700, color: '#fff', letterSpacing: '0.04em', lineHeight: 1.1, marginBottom: 12, textShadow: '0 0 40px rgba(0,212,255,0.25)' }}>
            Model<span style={{ color: 'var(--color-cyan)', textShadow: '0 0 20px rgba(0,212,255,0.6)' }}>Square</span>
          </h1>
          <p style={{ color: 'var(--color-text-secondary)', fontSize: 15, maxWidth: 480, lineHeight: 1.7, marginBottom: 36 }}>
            发现、测试、对比顶尖 AI 模型 — 图像检测 · 目标分割 · 多模态理解
          </p>

          {/* Stats row */}
          <div style={{ display: 'flex', gap: 0, background: 'rgba(0,0,0,0.3)', borderRadius: 10, border: '1px solid rgba(0,212,255,0.1)', overflow: 'hidden' }}>
            <StatItem value={String(models.length)} label="公开模型" icon={<ApiOutlined style={{ fontSize: 18 }} />} />
            <StatItem value="5" label="任务类型" icon={<CodeOutlined style={{ fontSize: 18 }} />} />
            <StatItem value="<500ms" label="推理延迟" icon={<ThunderboltOutlined style={{ fontSize: 18 }} />} />
            <div style={{ textAlign: 'center', padding: '0 24px' }}>
              <div style={{ color: 'var(--color-cyan)', fontFamily: 'var(--font-mono)', fontSize: 28, fontWeight: 700, lineHeight: 1.1, textShadow: '0 0 20px rgba(0,212,255,0.5)' }}>
                <RocketOutlined style={{ fontSize: 18 }} /> GPU
              </div>
              <div style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase', marginTop: 4 }}>实时推理</div>
            </div>
          </div>
        </div>

        {/* Bottom glow line */}
        <div style={{ position: 'absolute', bottom: 0, left: '10%', right: '10%', height: 1, background: 'linear-gradient(90deg, transparent, var(--color-cyan), transparent)', opacity: 0.4 }} />
      </div>

      {/* ── Search & Filter ── */}
      <div
        className="fade-in-up fade-in-up-delay-1"
        style={{ display: 'flex', gap: 12, marginBottom: 28, alignItems: 'center' }}
      >
        <div style={{ flex: 1 }}>
          <Search
            placeholder="搜索模型名称、描述..."
            allowClear
            size="large"
            enterButton={<><SearchOutlined /> 搜索</>}
            onSearch={(v) => { setSearchKeyword(v); fetchModels(); }}
            style={{ width: '100%' }}
          />
        </div>
        <Select
          placeholder="任务类型"
          allowClear
          size="large"
          style={{ width: 160 }}
          onChange={setTaskFilter}
        >
          {Object.entries(TASK_LABELS).map(([k, v]) => (
            <Option key={k} value={k}>{v}</Option>
          ))}
        </Select>
      </div>

      {/* ── Section header ── */}
      <div
        className="fade-in-up fade-in-up-delay-2"
        style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}
      >
        <span style={{ display: 'inline-block', width: 3, height: 18, borderRadius: 2, background: 'var(--color-cyan)', boxShadow: '0 0 8px var(--color-cyan)' }} />
        <span style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700, color: 'var(--color-text-primary)', letterSpacing: '0.04em' }}>热门模型</span>
        <Tag style={{ marginLeft: 8, borderRadius: 10, fontFamily: 'var(--font-mono)', fontSize: 11, background: 'var(--color-cyan-dim)', borderColor: 'var(--color-border-bright)', color: 'var(--color-cyan)' }}>
          {models.length} 个
        </Tag>
      </div>

      {/* ── Model Grid ── */}
      <div className="fade-in-up fade-in-up-delay-3">
        {loading ? (
          <div style={{ textAlign: 'center', padding: '80px 0' }}>
            <Spin size="large" />
            <div style={{ marginTop: 16, color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)', fontSize: 12, letterSpacing: '0.08em' }}>
              LOADING MODELS...
            </div>
          </div>
        ) : models.length === 0 ? (
          <Empty
            description={<span style={{ color: 'var(--color-text-muted)' }}>暂无模型</span>}
            style={{ padding: '60px 0' }}
          />
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 20 }}>
            {models.map((model) => (
              <ModelCard
                key={model.id}
                model={model}
                onClick={() => navigate(`/models/${model.id}`)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default HomePage;
