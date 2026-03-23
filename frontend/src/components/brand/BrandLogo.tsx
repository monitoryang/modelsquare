/**
 * 改造后的Logo组件 - 添加渐变、光晕、动态效果
 */

import React from 'react'
import { motion } from 'framer-motion'

export interface LogoProps {
  size?: 'sm' | 'md' | 'lg' | 'xl'
  variant?: 'default' | 'animated' | 'minimal'
  showText?: boolean
}

const sizeMap = {
  sm: 32,
  md: 48,
  lg: 64,
  xl: 96,
}

export const BrandLogo: React.FC<LogoProps> = ({
  size = 'md',
  variant = 'default',
  showText = false,
}) => {
  const dimension = sizeMap[size]

  const animationVariants = {
    default: {},
    animated: {
      rotate: [0, 360],
      transition: { duration: 3, repeat: Infinity, ease: 'linear' },
    },
    minimal: {},
  }

  return (
    <motion.div
      className="inline-flex items-center gap-2"
      animate={animationVariants[variant]}
    >
      <svg
        width={dimension}
        height={dimension}
        viewBox="0 0 200 200"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="drop-shadow-lg"
      >
        <defs>
          {/* 渐变定义 */}
          <radialGradient id="glow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#F4C430" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#F4C430" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="goldGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#FDD9A0" />
            <stop offset="50%" stopColor="#F4C430" />
            <stop offset="100%" stopColor="#E8B800" />
          </linearGradient>
          {/* 光晕滤镜 */}
          <filter id="glow-filter">
            <feGaussianBlur stdDeviation="2" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* 光晕背景 - 仅在animated模式显示 */}
        {variant === 'animated' && (
          <circle cx="100" cy="100" r="95" fill="url(#glow)" filter="url(#glow-filter)" />
        )}

        {/* 主体圆环 - 8段设计 */}
        <g filter={variant === 'animated' ? 'url(#glow-filter)' : undefined}>
          {/* 上 */}
          <path
            d="M 100 20 A 80 80 0 0 1 156.57 43.43 L 140 60 A 60 60 0 0 0 100 40 Z"
            fill={variant === 'animated' ? 'url(#goldGradient)' : '#F4C430'}
            opacity="0.95"
          />
          {/* 右上 */}
          <path
            d="M 156.57 43.43 A 80 80 0 0 1 180 100 L 160 100 A 60 60 0 0 0 140 60 Z"
            fill={variant === 'animated' ? 'url(#goldGradient)' : '#F4C430'}
            opacity="0.9"
          />
          {/* 右 */}
          <path
            d="M 180 100 A 80 80 0 0 1 156.57 156.57 L 140 140 A 60 60 0 0 0 160 100 Z"
            fill={variant === 'animated' ? 'url(#goldGradient)' : '#F4C430'}
            opacity="0.85"
          />
          {/* 右下 */}
          <path
            d="M 156.57 156.57 A 80 80 0 0 1 100 180 L 100 160 A 60 60 0 0 0 140 140 Z"
            fill={variant === 'animated' ? 'url(#goldGradient)' : '#F4C430'}
            opacity="0.8"
          />
          {/* 下 */}
          <path
            d="M 100 180 A 80 80 0 0 1 43.43 156.57 L 60 140 A 60 60 0 0 0 100 160 Z"
            fill={variant === 'animated' ? 'url(#goldGradient)' : '#F4C430'}
            opacity="0.85"
          />
          {/* 左下 */}
          <path
            d="M 43.43 156.57 A 80 80 0 0 1 20 100 L 40 100 A 60 60 0 0 0 60 140 Z"
            fill={variant === 'animated' ? 'url(#goldGradient)' : '#F4C430'}
            opacity="0.9"
          />
          {/* 左 */}
          <path
            d="M 20 100 A 80 80 0 0 1 43.43 43.43 L 60 60 A 60 60 0 0 0 40 100 Z"
            fill={variant === 'animated' ? 'url(#goldGradient)' : '#F4C430'}
            opacity="0.95"
          />
          {/* 左上 */}
          <path
            d="M 43.43 43.43 A 80 80 0 0 1 100 20 L 100 40 A 60 60 0 0 0 60 60 Z"
            fill={variant === 'animated' ? 'url(#goldGradient)' : '#F4C430'}
          />
        </g>

        {/* 中心白色圆形 */}
        <circle cx="100" cy="100" r="50" fill="white" />

        {/* 中心点缀 - 暗示AI/技术 */}
        {variant === 'animated' && (
          <motion.circle
            cx="100"
            cy="100"
            r="8"
            fill="#F4C430"
            opacity="0.6"
            animate={{ scale: [1, 1.3, 1] }}
            transition={{ duration: 2, repeat: Infinity }}
          />
        )}
      </svg>

      {/* 品牌文字 */}
      {showText && (
        <div className="flex flex-col">
          <span className="font-bold text-lg" style={{ color: '#F4C430' }}>
            ModelSquare
          </span>
          <span className="text-xs text-gray-500">AI Model Platform</span>
        </div>
      )}
    </motion.div>
  )
}

export default BrandLogo
