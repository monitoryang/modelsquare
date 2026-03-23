/**
 * 品牌色彩系统 - 融合公司Logo的金黄色
 */

export const BrandColors = {
  // 主色系 - 金黄色（来自Logo）
  primary: {
    50: '#FFFBF0',
    100: '#FEF3E0',
    200: '#FDE8C0',
    300: '#FDD9A0',
    400: '#FCC880',
    500: '#F4C430', // 主品牌色
    600: '#E8B800',
    700: '#D4A000',
    800: '#B88800',
    900: '#9C7000',
  },

  // 中性色系
  neutral: {
    50: '#FAFAFA',
    100: '#F5F5F5',
    200: '#EEEEEE',
    300: '#E0E0E0',
    400: '#BDBDBD',
    500: '#9E9E9E',
    600: '#757575',
    700: '#616161',
    800: '#424242',
    900: '#212121',
  },

  // 功能色
  success: '#10B981',
  warning: '#F59E0B',
  error: '#EF4444',
  info: '#3B82F6',

  // 深色模式
  dark: {
    bg: '#0F172A',
    surface: '#1E293B',
    border: '#334155',
  },
}

// CSS变量导出
export const getCSSVariables = () => `
  :root {
    --color-primary: ${BrandColors.primary[500]};
    --color-primary-light: ${BrandColors.primary[100]};
    --color-primary-dark: ${BrandColors.primary[700]};
    --color-success: ${BrandColors.success};
    --color-warning: ${BrandColors.warning};
    --color-error: ${BrandColors.error};
    --color-info: ${BrandColors.info};
  }
`
