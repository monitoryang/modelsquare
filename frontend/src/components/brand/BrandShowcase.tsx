/**
 * 品牌展示页面 - 完整的ModelSquare首页设计
 */

import React, { useState } from 'react'
import { motion } from 'framer-motion'
import BrandLogo from './BrandLogo'
import { BrandButton, BrandCard, BrandBadge } from './BrandComponents'

interface NavItem {
  label: string
  href: string
  icon?: string
}

const BrandShowcase: React.FC = () => {
  const [activeNav, setActiveNav] = useState('models')
  const [isLoading, setIsLoading] = useState(false)

  const navItems: NavItem[] = [
    { label: 'Models', href: '#models' },
    { label: 'Docs', href: '#docs' },
    { label: 'API', href: '#api' },
    { label: 'Community', href: '#community' },
  ]

  const models = [
    {
      title: 'YOLOv8 Detection',
      description: 'Real-time object detection with high accuracy',
      status: 'active' as const,
      badge: 'Popular',
    },
    {
      title: 'Qwen3-VL',
      description: 'Vision-Language model for image understanding',
      status: 'active' as const,
      badge: 'New',
    },
    {
      title: 'Custom Model',
      description: 'Upload and deploy your own models',
      status: 'active' as const,
      badge: 'Flexible',
    },
  ]

  const features = [
    {
      icon: '⚡',
      title: 'Real-time Inference',
      description: 'GPU-accelerated model inference with minimal latency',
    },
    {
      icon: '🎬',
      title: 'Video Processing',
      description: 'Process videos frame-by-frame with detection overlays',
    },
    {
      icon: '📡',
      title: 'Live Streaming',
      description: 'RTMP/HLS streaming with real-time detection',
    },
    {
      icon: '🔧',
      title: 'Easy Deployment',
      description: 'One-click model deployment with auto-scaling',
    },
  ]

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1,
        delayChildren: 0.2,
      },
    },
  }

  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: {
      opacity: 1,
      y: 0,
      transition: { duration: 0.6 },
    },
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-white to-gray-50">
      {/* ============ 导航栏 ============ */}
      <nav className="sticky top-0 z-50 bg-white/80 backdrop-blur-md border-b border-gray-200/50 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          {/* Logo */}
          <motion.div
            whileHover={{ scale: 1.05 }}
            className="cursor-pointer"
          >
            <BrandLogo size="md" showText={true} />
          </motion.div>

          {/* 导航项 */}
          <div className="hidden md:flex items-center gap-1">
            {navItems.map((item) => (
              <motion.button
                key={item.href}
                className={`px-4 py-2 rounded-lg transition-all duration-200 ${
                  activeNav === item.href.slice(1)
                    ? 'text-[#F4C430] font-semibold'
                    : 'text-gray-700 hover:text-[#F4C430]'
                }`}
                whileHover={{ backgroundColor: '#F4C430', color: 'white' }}
                onClick={() => setActiveNav(item.href.slice(1))}
              >
                {item.label}
              </motion.button>
            ))}
          </div>

          {/* 右侧操作 */}
          <BrandButton
            variant="primary"
            size="sm"
            onClick={() => setIsLoading(!isLoading)}
            loading={isLoading}
          >
            {isLoading ? 'Loading...' : 'Get Started'}
          </BrandButton>
        </div>
      </nav>

      {/* ============ Hero Section ============ */}
      <motion.section
        className="relative max-w-7xl mx-auto px-4 py-20 md:py-32"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.8 }}
      >
        {/* 背景装饰 */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="absolute top-20 right-10 w-72 h-72 bg-[#F4C430]/10 rounded-full blur-3xl" />
          <div className="absolute bottom-20 left-10 w-96 h-96 bg-blue-100/10 rounded-full blur-3xl" />
        </div>

        <div className="relative z-10 text-center">
          {/* Logo动画 */}
          <motion.div
            className="flex justify-center mb-8"
            animate={{ y: [0, -10, 0] }}
            transition={{ duration: 3, repeat: Infinity }}
          >
            <BrandLogo size="xl" variant="animated" />
          </motion.div>

          {/* 标题 */}
          <motion.h1
            className="text-5xl md:text-6xl font-bold text-gray-900 mb-6"
            variants={itemVariants}
            initial="hidden"
            animate="visible"
          >
            Welcome to{' '}
            <span
              className="bg-gradient-to-r from-[#F4C430] to-[#E8B800] bg-clip-text text-transparent"
            >
              ModelSquare
            </span>
          </motion.h1>

          {/* 副标题 */}
          <motion.p
            className="text-xl text-gray-600 mb-8 max-w-2xl mx-auto"
            variants={itemVariants}
            initial="hidden"
            animate="visible"
            transition={{ delay: 0.1 }}
          >
            Deploy, manage, and scale AI models with ease. Real-time inference, video processing, and live streaming all in one platform.
          </motion.p>

          {/* CTA按钮 */}
          <motion.div
            className="flex gap-4 justify-center flex-wrap"
            variants={itemVariants}
            initial="hidden"
            animate="visible"
            transition={{ delay: 0.2 }}
          >
            <BrandButton variant="primary" size="lg">
              Start Exploring
            </BrandButton>
            <BrandButton variant="secondary" size="lg">
              View Documentation
            </BrandButton>
          </motion.div>
        </div>
      </motion.section>

      {/* ============ 特性展示 ============ */}
      <motion.section
        className="max-w-7xl mx-auto px-4 py-16"
        variants={containerVariants}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true }}
      >
        <motion.h2
          className="text-4xl font-bold text-center mb-12 text-gray-900"
          variants={itemVariants}
        >
          Powerful Features
        </motion.h2>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {features.map((feature, idx) => (
            <motion.div
              key={idx}
              className="p-6 rounded-xl bg-white border border-gray-200 hover:border-[#F4C430]/50 transition-all"
              variants={itemVariants}
              whileHover={{ y: -4, boxShadow: '0 20px 40px rgba(244, 196, 48, 0.1)' }}
            >
              <div className="text-4xl mb-4">{feature.icon}</div>
              <h3 className="font-bold text-lg mb-2 text-gray-900">{feature.title}</h3>
              <p className="text-gray-600 text-sm">{feature.description}</p>
            </motion.div>
          ))}
        </div>
      </motion.section>

      {/* ============ 模型卡片网格 ============ */}
      <motion.section
        className="max-w-7xl mx-auto px-4 py-16"
        variants={containerVariants}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true }}
      >
        <motion.h2
          className="text-4xl font-bold text-center mb-12 text-gray-900"
          variants={itemVariants}
        >
          Featured Models
        </motion.h2>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {models.map((model, idx) => (
            <motion.div key={idx} variants={itemVariants}>
              <BrandCard
                title={model.title}
                description={model.description}
                status={model.status}
              >
                <div className="flex justify-between items-center mt-4">
                  <BrandBadge label={model.badge} variant="primary" />
                  <motion.button
                    className="text-[#F4C430] font-semibold text-sm hover:text-[#E8B800]"
                    whileHover={{ x: 4 }}
                  >
                    Try Now →
                  </motion.button>
                </div>
              </BrandCard>
            </motion.div>
          ))}
        </div>
      </motion.section>

      {/* ============ 技术栈展示 ============ */}
      <motion.section
        className="max-w-7xl mx-auto px-4 py-16"
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true }}
      >
        <div className="bg-gradient-to-r from-[#F4C430]/10 to-blue-100/10 rounded-2xl p-12 border border-[#F4C430]/20">
          <h2 className="text-3xl font-bold text-gray-900 mb-8 text-center">
            Powered by Advanced Technology
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            {['NVIDIA Triton', 'FastAPI', 'PostgreSQL', 'Redis', 'MinIO', 'SRS', 'FFmpeg', 'Docker'].map(
              (tech) => (
                <motion.div
                  key={tech}
                  className="p-4 rounded-lg bg-white border border-gray-200 text-center"
                  whileHover={{ scale: 1.05, borderColor: '#F4C430' }}
                >
                  <p className="font-semibold text-gray-900">{tech}</p>
                </motion.div>
              )
            )}
          </div>
        </div>
      </motion.section>

      {/* ============ CTA Section ============ */}
      <motion.section
        className="max-w-7xl mx-auto px-4 py-20"
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
      >
        <div className="bg-gradient-to-r from-[#F4C430] to-[#E8B800] rounded-2xl p-12 text-center text-white">
          <h2 className="text-4xl font-bold mb-4">Ready to Deploy Your Models?</h2>
          <p className="text-lg mb-8 opacity-90">
            Join thousands of developers using ModelSquare for AI inference
          </p>
          <BrandButton variant="primary" size="lg">
            Start Free Trial
          </BrandButton>
        </div>
      </motion.section>

      {/* ============ 页脚 ============ */}
      <footer className="bg-gray-900 text-gray-400 py-12 mt-20">
        <div className="max-w-7xl mx-auto px-4">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-8 mb-8">
            <div>
              <BrandLogo size="md" showText={true} />
            </div>
            <div>
              <h4 className="text-white font-bold mb-4">Product</h4>
              <ul className="space-y-2 text-sm">
                <li><a href="#" className="hover:text-[#F4C430]">Features</a></li>
                <li><a href="#" className="hover:text-[#F4C430]">Pricing</a></li>
                <li><a href="#" className="hover:text-[#F4C430]">Security</a></li>
              </ul>
            </div>
            <div>
              <h4 className="text-white font-bold mb-4">Resources</h4>
              <ul className="space-y-2 text-sm">
                <li><a href="#" className="hover:text-[#F4C430]">Documentation</a></li>
                <li><a href="#" className="hover:text-[#F4C430]">API Reference</a></li>
                <li><a href="#" className="hover:text-[#F4C430]">Community</a></li>
              </ul>
            </div>
            <div>
              <h4 className="text-white font-bold mb-4">Company</h4>
              <ul className="space-y-2 text-sm">
                <li><a href="#" className="hover:text-[#F4C430]">About</a></li>
                <li><a href="#" className="hover:text-[#F4C430]">Blog</a></li>
                <li><a href="#" className="hover:text-[#F4C430]">Contact</a></li>
              </ul>
            </div>
          </div>
          <div className="border-t border-gray-800 pt-8 text-center text-sm">
            <p>&copy; 2024 ModelSquare. All rights reserved.</p>
          </div>
        </div>
      </footer>

      {/* 品牌水印 */}
      <div className="fixed bottom-4 right-4 opacity-5 pointer-events-none">
        <BrandLogo size="xl" variant="default" />
      </div>
    </div>
  )
}

export default BrandShowcase
