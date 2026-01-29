/**
 * Application routing configuration
 */

import React from 'react';
import { createBrowserRouter, Navigate } from 'react-router-dom';
import { MainLayout } from './layouts';
import {
  HomePage,
  ModelDetailPage,
  ModelUploadPage,
  ModelEditPage,
  ProfilePage,
  LoginPage,
  RegisterPage,
} from './pages';
import { authService } from './services';

// Protected route wrapper
const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  if (!authService.isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
};

const router = createBrowserRouter([
  {
    path: '/',
    element: <MainLayout />,
    children: [
      {
        index: true,
        element: <HomePage />,
      },
      {
        path: 'models',
        element: <HomePage />,
      },
      {
        // Upload route must come before :modelId to match first
        path: 'models/upload',
        element: (
          <ProtectedRoute>
            <ModelUploadPage />
          </ProtectedRoute>
        ),
      },
      {
        // Edit route must come before :modelId to match first
        path: 'models/:modelId/edit',
        element: (
          <ProtectedRoute>
            <ModelEditPage />
          </ProtectedRoute>
        ),
      },
      {
        path: 'models/:modelId',
        element: <ModelDetailPage />,
      },
      {
        path: 'profile',
        element: (
          <ProtectedRoute>
            <ProfilePage />
          </ProtectedRoute>
        ),
      },
    ],
  },
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    path: '/register',
    element: <RegisterPage />,
  },
  {
    path: '*',
    element: <Navigate to="/" replace />,
  },
]);

export default router;
