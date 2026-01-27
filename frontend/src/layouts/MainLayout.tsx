/**
 * Main application layout with Ant Design Pro
 */

import React, { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { ProLayout, PageContainer } from '@ant-design/pro-components';
import {
  HomeOutlined,
  AppstoreOutlined,
  UserOutlined,
  LogoutOutlined,
  LoginOutlined,
} from '@ant-design/icons';
import { Dropdown, Avatar, Space, message } from 'antd';
import type { MenuProps } from 'antd';
import { authService } from '../services';

const MainLayout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const isAuthenticated = authService.isAuthenticated();

  const menuItems = [
    {
      path: '/',
      name: '首页',
      icon: <HomeOutlined />,
    },
    {
      path: '/models',
      name: '模型广场',
      icon: <AppstoreOutlined />,
    },
    ...(isAuthenticated
      ? [
          {
            path: '/profile',
            name: '个人中心',
            icon: <UserOutlined />,
          },
        ]
      : []),
  ];

  const handleLogout = () => {
    authService.logout();
    message.success('已退出登录');
  };

  const userMenuItems: MenuProps['items'] = isAuthenticated
    ? [
        {
          key: 'profile',
          icon: <UserOutlined />,
          label: '个人中心',
          onClick: () => navigate('/profile'),
        },
        {
          type: 'divider',
        },
        {
          key: 'logout',
          icon: <LogoutOutlined />,
          label: '退出登录',
          onClick: handleLogout,
        },
      ]
    : [
        {
          key: 'login',
          icon: <LoginOutlined />,
          label: '登录',
          onClick: () => navigate('/login'),
        },
      ];

  return (
    <ProLayout
      title="ModelSquare"
      logo="/logo.svg"
      layout="mix"
      splitMenus={false}
      collapsed={collapsed}
      onCollapse={setCollapsed}
      location={{ pathname: location.pathname }}
      route={{
        path: '/',
        routes: menuItems,
      }}
      menuItemRender={(item, dom) => (
        <div onClick={() => item.path && navigate(item.path)}>{dom}</div>
      )}
      actionsRender={() => [
        <Dropdown key="user" menu={{ items: userMenuItems }} placement="bottomRight">
          <Space style={{ cursor: 'pointer' }}>
            <Avatar icon={<UserOutlined />} />
          </Space>
        </Dropdown>,
      ]}
      token={{
        header: {
          colorBgHeader: '#001529',
          colorHeaderTitle: '#fff',
        },
        sider: {
          colorMenuBackground: '#001529',
          colorTextMenu: 'rgba(255, 255, 255, 0.65)',
          colorTextMenuSelected: '#fff',
          colorBgMenuItemSelected: '#1890ff',
        },
      }}
    >
      <PageContainer>
        <Outlet />
      </PageContainer>
    </ProLayout>
  );
};

export default MainLayout;
