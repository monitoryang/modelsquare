/**
 * 品牌系统集成示例
 * 展示如何在实际项目中使用品牌组件
 */

import React, { useState } from 'react'
import {
  BrandLogo,
  BrandButton,
  BrandCard,
  BrandBadge,
  BrandColors,
} from './index'

/**
 * 示例1: 导航栏集成
 */
export const NavbarExample: React.FC = () => {
  return (
    <nav className="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between">
      <BrandLogo size="md" showText={true} />
      <div className="flex gap-4">
        <BrandButton variant="ghost" size="sm">
          Models
        </BrandButton>
        <BrandButton variant="ghost" size="sm">
          Docs
        </BrandButton>
        <BrandButton variant="primary" size="sm">
          Sign In
        </BrandButton>
      </div>
    </nav>
  )
}

/**
 * 示例2: 加载页面
 */
export const LoadingPageExample: React.FC = () => {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-gray-50 to-gray-100">
      <div className="text-center">
        <BrandLogo size="xl" variant="animated" />
        <h1 className="text-2xl font-bold mt-6 text-gray-900">
          Loading your models...
        </h1>
        <p className="text-gray-600 mt-2">
          Please wait while we prepare your workspace
        </p>
      </div>
    </div>
  )
}

/**
 * 示例3: 模型列表页面
 */
export const ModelListExample: React.FC = () => {
  const models = [
    {
      id: 1,
      name: 'YOLOv8 Detection',
      description: 'Real-time object detection',
      status: 'active' as const,
      badge: 'Popular',
    },
    {
      id: 2,
      name: 'Qwen3-VL',
      description: 'Vision-Language understanding',
      status: 'active' as const,
      badge: 'New',
    },
    {
      id: 3,
      name: 'Custom Model',
      description: 'Your uploaded model',
      status: 'loading' as const,
      badge: 'Training',
    },
  ]

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold mb-8 text-gray-900">
        Available Models
      </h1>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {models.map((model) => (
          <BrandCard
            key={model.id}
            title={model.name}
            description={model.description}
            status={model.status}
          >
            <div className="flex justify-between items-center mt-4">
              <BrandBadge label={model.badge} variant="primary" />
              <BrandButton variant="ghost" size="sm">
                Try →
              </BrandButton>
            </div>
          </BrandCard>
        ))}
      </div>
    </div>
  )
}

/**
 * 示例4: 表单页面
 */
export const FormPageExample: React.FC = () => {
  const [loading, setLoading] = useState(false)

  const handleSubmit = async () => {
    setLoading(true)
    // 模拟API调用
    await new Promise((resolve) => setTimeout(resolve, 2000))
    setLoading(false)
  }

  return (
    <div className="max-w-md mx-auto py-12">
      <div className="flex justify-center mb-8">
        <BrandLogo size="lg" />
      </div>

      <h1 className="text-2xl font-bold text-center mb-6 text-gray-900">
        Deploy Your Model
      </h1>

      <form className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Model Name
          </label>
          <input
            type="text"
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-[#F4C430]"
            placeholder="Enter model name"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Model File
          </label>
          <input
            type="file"
            className="w-full px-4 py-2 border border-gray-300 rounded-lg"
          />
        </div>

        <BrandButton
          variant="primary"
          size="lg"
          className="w-full"
          loading={loading}
          onClick={handleSubmit}
        >
          {loading ? 'Deploying...' : 'Deploy Model'}
        </BrandButton>
      </form>
    </div>
  )
}

/**
 * 示例5: 仪表板卡片
 */
export const DashboardExample: React.FC = () => {
  const stats = [
    { label: 'Active Models', value: '12', color: BrandColors.primary[500] },
    { label: 'Total Inferences', value: '45.2K', color: BrandColors.success },
    { label: 'GPU Utilization', value: '78%', color: BrandColors.warning },
    { label: 'API Calls', value: '1.2M', color: BrandColors.info },
  ]

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold mb-8 text-gray-900">Dashboard</h1>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        {stats.map((stat, idx) => (
          <div
            key={idx}
            className="bg-white rounded-lg p-6 border border-gray-200"
            style={{ borderTopColor: stat.color, borderTopWidth: '4px' }}
          >
            <p className="text-gray-600 text-sm mb-2">{stat.label}</p>
            <p className="text-3xl font-bold text-gray-900">{stat.value}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

/**
 * 示例6: 错误页面
 */
export const ErrorPageExample: React.FC = () => {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-red-50 to-red-100">
      <div className="text-center">
        <div className="text-6xl mb-4">⚠️</div>
        <h1 className="text-3xl font-bold text-gray-900 mb-2">
          Something went wrong
        </h1>
        <p className="text-gray-600 mb-8">
          We encountered an error while processing your request
        </p>
        <div className="flex gap-4 justify-center">
          <BrandButton variant="primary" size="lg">
            Try Again
          </BrandButton>
          <BrandButton variant="secondary" size="lg">
            Go Home
          </BrandButton>
        </div>
      </div>
    </div>
  )
}

/**
 * 示例7: 成功提示
 */
export const SuccessNotificationExample: React.FC = () => {
  return (
    <div className="fixed top-4 right-4 bg-white rounded-lg shadow-lg p-4 border-l-4 border-[#10B981]">
      <div className="flex items-center gap-3">
        <div className="text-2xl">✓</div>
        <div>
          <h3 className="font-bold text-gray-900">Success!</h3>
          <p className="text-sm text-gray-600">Model deployed successfully</p>
        </div>
      </div>
    </div>
  )
}

/**
 * 示例8: 完整页面模板
 */
export const FullPageTemplate: React.FC = () => {
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
      {/* 导航栏 */}
      <NavbarExample />

      {/* Hero区域 */}
      <section className="max-w-7xl mx-auto px-4 py-20 text-center">
        <BrandLogo size="xl" variant="animated" />
        <h1 className="text-5xl font-bold mt-8 text-gray-900">
          Welcome to <span style={{ color: '#F4C430' }}>ModelSquare</span>
        </h1>
        <p className="text-xl text-gray-600 mt-4 max-w-2xl mx-auto">
          Deploy and manage AI models with ease
        </p>
        <div className="flex gap-4 justify-center mt-8">
          <BrandButton variant="primary" size="lg">
            Get Started
          </BrandButton>
          <BrandButton variant="secondary" size="lg">
            Learn More
          </BrandButton>
        </div>
      </section>

      {/* 模型列表 */}
      <ModelListExample />

      {/* 页脚 */}
      <footer className="bg-gray-900 text-gray-400 py-12 mt-20">
        <div className="max-w-7xl mx-auto px-4 text-center">
          <BrandLogo size="md" showText={true} />
          <p className="mt-4">&copy; 2024 ModelSquare. All rights reserved.</p>
        </div>
      </footer>
    </div>
  )
}

export default FullPageTemplate
