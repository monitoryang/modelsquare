import React from 'react';
import ReactDOM from 'react-dom/client';
import { RouterProvider } from 'react-router-dom';
import { ConfigProvider, App } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import router from './router';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#1677ff',
          colorBgBase: '#ffffff',
          colorBgContainer: '#ffffff',
          colorBgLayout: '#f5f7fa',
          colorLink: '#1677ff',
          colorLinkHover: '#4096ff',
        },
        components: {
          Layout: {
            bodyBg: '#f5f7fa',
            headerBg: '#ffffff',
          },
          Card: {
            colorBgContainer: '#ffffff',
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
