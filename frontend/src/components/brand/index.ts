/**
 * 品牌系统导出文件
 * 统一导出所有品牌相关组件和工具
 */

// 颜色系统
export { BrandColors, getCSSVariables } from './BrandColors'

// Logo组件
export { default as BrandLogo } from './BrandLogo'
export type { LogoProps } from './BrandLogo'

// 交互组件
export {
  BrandButton,
  BrandLoader,
  BrandCard,
  BrandBadge,
} from './BrandComponents'

// 完整展示页面
export { default as BrandShowcase } from './BrandShowcase'
