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
          colorPrimary: '#d4a017',
          colorBgBase: '#fffef5',
          colorBgContainer: '#fffdf0',
          colorBgLayout: '#fefce8',
          colorLink: '#b8860b',
          colorLinkHover: '#d4a017',
        },
        components: {
          Layout: {
            bodyBg: '#fefce8',
            headerBg: '#fef9c3',
          },
          Card: {
            colorBgContainer: '#fffdf0',
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
