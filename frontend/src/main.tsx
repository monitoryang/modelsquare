import React from 'react';
import ReactDOM from 'react-dom/client';
import { RouterProvider } from 'react-router-dom';
import { ConfigProvider, App, theme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import router from './router';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: '#00d4ff',
          colorBgBase: '#040810',
          colorBgContainer: '#0d1425',
          colorBgElevated: '#0d1425',
          colorBgLayout: '#040810',
          colorText: '#e2eeff',
          colorTextSecondary: '#8ba4cc',
          colorBorder: 'rgba(0,212,255,0.15)',
          colorLink: '#00d4ff',
          colorLinkHover: '#33deff',
          borderRadius: 8,
          fontFamily: "'Noto Sans SC', system-ui, sans-serif",
        },
        components: {
          Layout: {
            bodyBg: '#040810',
            headerBg: '#080d1a',
          },
          Card: {
            colorBgContainer: '#0d1425',
          },
          Menu: {
            colorItemBg: 'transparent',
          },
        },
      }}
    >
      <App>
        <RouterProvider router={router} />
      </App>
    </ConfigProvider>
  </React.StrictMode>
);
