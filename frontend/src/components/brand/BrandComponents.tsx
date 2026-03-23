/**
 * 品牌按钮和交互组件
 */

import React from 'react'
import { motion } from 'framer-motion'

interface BrandButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost'
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
  icon?: React.ReactNode
}

export const BrandButton: React.FC<BrandButtonProps> = ({
  variant = 'primary',
  size = 'md',
  loading = false,
  icon,
  children,
  disabled,
  ...props
}) => {
  const baseStyles =
    'font-medium rounded-lg transition-all duration-200 flex items-center justify-center gap-2 disabled:opacity-50'

  const variantStyles = {
    primary:
      'bg-gradient-to-r from-[#F4C430] to-[#E8B800] text-white hover:shadow-lg hover:shadow-[#F4C430]/50 active:scale-95',
    secondary: 'border-2 border-[#F4C430] text-[#F4C430] hover:bg-[#F4C430]/10',
    ghost: 'text-[#F4C430] hover:bg-[#F4C430]/10',
  }

  const sizeStyles = {
    sm: 'px-3 py-1.5 text-sm',
    md: 'px-4 py-2 text-base',
    lg: 'px-6 py-3 text-lg',
  }

  return (
    <motion.button
      className={`${baseStyles} ${variantStyles[variant]} ${sizeStyles[size]}`}
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
      disabled={loading || disabled}
      {...(props as any)}
    >
      {loading && (
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <circle cx="12" cy="12" r="10" strokeWidth="2" opacity="0.3" />
            <path d="M12 2a10 10 0 0 1 10 10" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </motion.div>
      )}
      {icon && !loading && icon}
      {children}
    </motion.button>
  )
}

// 加载动画组件
export const BrandLoader: React.FC<{ text?: string; size?: 'sm' | 'md' | 'lg' }> = ({
  text = 'Loading',
  size = 'md',
}) => {
  const sizeMap = { sm: 32, md: 48, lg: 64 }

  return (
    <div className="flex flex-col items-center justify-center gap-4">
      <motion.div
        animate={{ rotate: 360 }}
        transition={{ duration: 2, repeat: Infinity, ease: 'linear' }}
      >
        <svg
          width={sizeMap[size]}
          height={sizeMap[size]}
          viewBox="0 0 200 200"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            <linearGradient id="loadGradient" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#FDD9A0" />
              <stop offset="50%" stopColor="#F4C430" />
              <stop offset="100%" stopColor="#E8B800" />
            </linearGradient>
          </defs>
          <circle cx="100" cy="100" r="90" fill="none" stroke="url(#loadGradient)" strokeWidth="8" />
        </svg>
      </motion.div>
      <motion.p
        className="text-sm font-medium"
        style={{ color: '#F4C430' }}
        animate={{ opacity: [0.5, 1, 0.5] }}
        transition={{ duration: 1.5, repeat: Infinity }}
      >
        {text}
      </motion.p>
    </div>
  )
}

// 品牌卡片组件
interface BrandCardProps {
  title: string
  description: string
  image?: string
  status?: 'active' | 'loading' | 'error'
  onClick?: () => void
  children?: React.ReactNode
}

export const BrandCard: React.FC<BrandCardProps> = ({
  title,
  description,
  image,
  status = 'active',
  onClick,
  children,
}) => {
  const statusColors = {
    active: '#10B981',
    loading: '#F4C430',
    error: '#EF4444',
  }

  return (
    <motion.div
      className="relative overflow-hidden rounded-xl border border-gray-200 bg-white p-4 cursor-pointer group hover:border-[#F4C430]/50 transition-colors"
      whileHover={{ y: -4, boxShadow: '0 20px 40px rgba(244, 196, 48, 0.15)' }}
      onClick={onClick}
    >
      {/* 品牌色渐变背景 - 悬停时显示 */}
      <div className="absolute inset-0 bg-gradient-to-br from-[#F4C430]/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />

      {/* 内容 */}
      <div className="relative z-10">
        {/* 状态指示器 */}
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-bold text-lg text-gray-900">{title}</h3>
          <motion.div
            className="w-3 h-3 rounded-full"
            style={{ backgroundColor: statusColors[status] }}
            animate={status === 'loading' ? { scale: [1, 1.2, 1] } : {}}
            transition={{ duration: 1, repeat: Infinity }}
          />
        </div>

        {/* 描述 */}
        <p className="text-sm text-gray-600 mb-3">{description}</p>

        {/* 图片 */}
        {image && (
          <img
            src={image}
            alt={title}
            className="w-full h-32 object-cover rounded-lg mb-3"
          />
        )}

        {/* 自定义内容 */}
        {children}

        {/* 底部装饰线 - 品牌色 */}
        <div className="h-1 bg-gradient-to-r from-[#F4C430] to-transparent rounded-full mt-3" />
      </div>
    </motion.div>
  )
}

// 品牌徽章
interface BrandBadgeProps {
  label: string
  variant?: 'primary' | 'success' | 'warning' | 'error'
  size?: 'sm' | 'md'
}

export const BrandBadge: React.FC<BrandBadgeProps> = ({
  label,
  variant = 'primary',
  size = 'md',
}) => {
  const variantStyles = {
    primary: 'bg-[#F4C430]/20 text-[#F4C430]',
    success: 'bg-green-100 text-green-700',
    warning: 'bg-yellow-100 text-yellow-700',
    error: 'bg-red-100 text-red-700',
  }

  const sizeStyles = {
    sm: 'px-2 py-1 text-xs',
    md: 'px-3 py-1.5 text-sm',
  }

  return (
    <span className={`rounded-full font-medium ${variantStyles[variant]} ${sizeStyles[size]}`}>
      {label}
    </span>
  )
}

export default BrandButton
