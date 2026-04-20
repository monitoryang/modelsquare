/**
 * MainLayout — Deep-Space AI Tech Theme
 */

import React, { useState, useEffect } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Dropdown, Avatar, Space, message } from 'antd';
import type { MenuProps } from 'antd';
import {
  HomeOutlined,
  AppstoreOutlined,
  UserOutlined,
  LogoutOutlined,
  LoginOutlined,
  RobotOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from '@ant-design/icons';
import { authService } from '../services';
import { BrandLogo } from '../components/brand';

interface NavItem {
  path: string;
  label: string;
  icon: React.ReactNode;
}

const NAV_ITEMS: NavItem[] = [
  { path: '/',        label: '首页',       icon: <HomeOutlined /> },
  { path: '/models',  label: '模型广场',   icon: <AppstoreOutlined /> },
  { path: '/vlm',     label: '大模型检测', icon: <RobotOutlined /> },
  { path: '/profile', label: '个人中心',   icon: <UserOutlined /> },
];

// ─── Styles ─────────────────────────────────────────────────
const S: Record<string, React.CSSProperties> = {
  root:       { display: 'flex', minHeight: '100vh', background: 'var(--color-bg-base)', fontFamily: 'var(--font-body)' },
  sider:      { width: 220, minWidth: 220, background: 'var(--color-bg-surface)', borderRight: '1px solid var(--color-border)', display: 'flex', flexDirection: 'column', position: 'relative', transition: 'width 0.25s ease', flexShrink: 0, overflow: 'hidden' },
  siderColl:  { width: 64, minWidth: 64 },
  gridBg:     { position: 'absolute', inset: 0, backgroundImage: 'linear-gradient(rgba(0,212,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(0,212,255,0.03) 1px, transparent 1px)', backgroundSize: '32px 32px', pointerEvents: 'none', zIndex: 0 },
  inner:      { position: 'relative', zIndex: 1, display: 'flex', flexDirection: 'column', height: '100%' },
  logoArea:   { padding: '18px 14px', borderBottom: '1px solid var(--color-border)', display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', minHeight: 60 },
  logoIcon:   { width: 32, height: 32, borderRadius: 8, background: 'linear-gradient(135deg,#0066ff,#00d4ff)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 0 16px rgba(0,212,255,0.4)', flexShrink: 0, fontSize: 16, color: '#fff' },
  logoText:   { fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 17, color: '#F4C430', letterSpacing: '0.08em', textShadow: '0 0 12px rgba(244,196,48,0.4)', whiteSpace: 'nowrap' },
  nav:        { padding: '10px 8px', flex: 1 },
  navItem:    { display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', borderRadius: 6, cursor: 'pointer', transition: 'all 0.18s ease', color: 'var(--color-text-secondary)', fontSize: 14, fontWeight: 500, marginBottom: 2, whiteSpace: 'nowrap', overflow: 'hidden', position: 'relative', borderLeft: '2px solid transparent' },
  navActive:  { color: 'var(--color-cyan)', background: 'rgba(0,212,255,0.08)', borderLeft: '2px solid var(--color-cyan)' },
  siderFoot:  { padding: '10px 8px', borderTop: '1px solid var(--color-border)' },
  collBtn:    { display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 8, borderRadius: 6, cursor: 'pointer', color: 'var(--color-text-muted)', transition: 'all 0.18s ease' },
  main:       { flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 },
  header:     { height: 54, background: 'rgba(8,13,26,0.93)', backdropFilter: 'blur(12px)', borderBottom: '1px solid var(--color-border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 24px', flexShrink: 0, position: 'sticky', top: 0, zIndex: 100 },
  breadcrumb: { fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--color-text-muted)', letterSpacing: '0.05em' },
  bcActive:   { color: 'var(--color-cyan)' },
  statusPill: { display: 'flex', alignItems: 'center', gap: 6, padding: '3px 10px', borderRadius: 20, border: '1px solid rgba(0,255,157,0.25)', background: 'rgba(0,255,157,0.07)', fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--color-green)', letterSpacing: '0.05em' },
  avatarBtn:  { cursor: 'pointer', padding: '4px 10px', borderRadius: 20, border: '1px solid var(--color-border)', background: 'var(--color-bg-elevated)', display: 'flex', alignItems: 'center', gap: 8, transition: 'all 0.18s ease', color: 'var(--color-text-secondary)', fontSize: 13 },
  content:    { flex: 1, overflow: 'auto', padding: 24, background: 'var(--color-bg-base)' },
};

// ─── Component ──────────────────────────────────────────────
const MainLayout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [hovered, setHovered] = useState<string | null>(null);
  const [time, setTime] = useState(() => new Date());
  const isAuthenticated = authService.isAuthenticated();

  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const handleLogout = () => {
    authService.logout();
    message.success('已退出登录');
  };

  const userMenu: MenuProps['items'] = isAuthenticated
    ? [
        { key: 'profile', icon: <UserOutlined />, label: '个人中心', onClick: () => navigate('/profile') },
        { type: 'divider' },
        { key: 'logout',  icon: <LogoutOutlined />, label: '退出登录', danger: true, onClick: handleLogout },
      ]
    : [{ key: 'login', icon: <LoginOutlined />, label: '登录', onClick: () => navigate('/login') }];

  const currentLabel = NAV_ITEMS.find((n) => n.path === location.pathname)?.label ?? '页面';
  const timeStr = time.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });

  return (
    <div style={S.root}>
      {/* ── Sidebar ── */}
      <aside style={{ ...S.sider, ...(collapsed ? S.siderColl : {}) }}>
          <div style={S.gridBg} />
          <div style={S.inner}>
            {/* Logo */}
            <div style={S.logoArea} onClick={() => navigate('/')}>
              <BrandLogo size="sm" variant="default" />
              {!collapsed && <span style={S.logoText}>ModelSquare</span>}
            </div>

            {/* Nav */}
            <nav style={S.nav}>
              {NAV_ITEMS.map((item) => {
                const isActive  = location.pathname === item.path;
                const isHovered = hovered === item.path;
                return (
                  <div
                    key={item.path}
                    style={{
                      ...S.navItem,
                      ...(isActive ? S.navActive : {}),
                      ...(isHovered && !isActive ? { color: 'var(--color-text-primary)', background: 'var(--color-bg-hover)' } : {}),
                      justifyContent: collapsed ? 'center' : 'flex-start',
                    }}
                    onClick={() => navigate(item.path)}
                    onMouseEnter={() => setHovered(item.path)}
                    onMouseLeave={() => setHovered(null)}
                    title={collapsed ? item.label : undefined}
                  >
                    <span style={{ fontSize: 16, flexShrink: 0 }}>{item.icon}</span>
                    {!collapsed && <span>{item.label}</span>}
                    {isActive && !collapsed && (
                      <span style={{ marginLeft: 'auto', width: 5, height: 5, borderRadius: '50%', background: 'var(--color-cyan)', boxShadow: '0 0 8px var(--color-cyan)' }} />
                    )}
                  </div>
                );
              })}
            </nav>

            {/* Collapse toggle */}
            <div style={S.siderFoot}>
              <div
                style={S.collBtn}
                onClick={() => setCollapsed((c) => !c)}
                onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.color = 'var(--color-cyan)'; (e.currentTarget as HTMLDivElement).style.background = 'var(--color-cyan-dim)'; }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.color = 'var(--color-text-muted)'; (e.currentTarget as HTMLDivElement).style.background = 'transparent'; }}
              >
                {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              </div>
            </div>
          </div>
        </aside>

        {/* ── Main ── */}
        <main style={S.main}>
          {/* Header */}
          <header style={S.header}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <span style={S.breadcrumb}>
                ModelSquare
                <span style={{ margin: '0 6px', opacity: 0.4 }}>/</span>
                <span style={S.bcActive}>{currentLabel}</span>
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--color-text-muted)', letterSpacing: '0.08em' }}>
                {timeStr}
              </span>
              <div style={S.statusPill}>
                <span className="status-dot" />
                ONLINE
              </div>
              <Dropdown menu={{ items: userMenu }} placement="bottomRight" trigger={['click']}>
                <div
                  style={S.avatarBtn}
                  onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--color-cyan)'; (e.currentTarget as HTMLDivElement).style.color = 'var(--color-cyan)'; }}
                  onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--color-border)'; (e.currentTarget as HTMLDivElement).style.color = 'var(--color-text-secondary)'; }}
                >
                  <Avatar size={22} icon={<UserOutlined />} style={{ background: 'linear-gradient(135deg,#0066ff,#00d4ff)', fontSize: 11 }} />
                  <Space size={4}>{isAuthenticated ? '我的账户' : '未登录'}</Space>
                </div>
              </Dropdown>
            </div>
          </header>

          {/* Content */}
          <div style={S.content}>
            <Outlet />
          </div>
        </main>
      </div>
  );
};

export default MainLayout;
