/**
 * 品牌设计指南 - ModelSquare Logo融入方案
 * 
 * 本文档详细说明如何在整个平台中使用品牌元素
 */

# ModelSquare 品牌设计指南

## 📋 目录
1. [品牌概述](#品牌概述)
2. [Logo改造方案](#logo改造方案)
3. [色彩系统](#色彩系统)
4. [排版规范](#排版规范)
5. [组件使用](#组件使用)
6. [应用场景](#应用场景)
7. [动画指南](#动画指南)

---

## 品牌概述

### 品牌核心
- **名称**: ModelSquare
- **主色**: 金黄色 (#F4C430)
- **理念**: 现代、科技、高效、可靠
- **目标用户**: AI开发者、数据科学家、企业用户

### Logo特点
原始Logo是一个金黄色的圆形设计，代表：
- 🔄 **循环流动** - AI推理的持续过程
- ⚡ **能量** - 高性能计算
- 🎯 **精准** - 模型的准确性

---

## Logo改造方案

### 方案一：渐变增强版（推荐用于主Logo）
```
特点：
- 添加线性渐变（#FDD9A0 → #F4C430 → #E8B800）
- 增加立体感和深度
- 适合大尺寸展示
- 用途：导航栏、品牌标识、大型展示
```

### 方案二：动画版（用于加载状态）
```
特点：
- 持续旋转动画（3秒一圈）
- 中心脉动效果
- 光晕背景
- 用途：加载指示器、进度动画、实时推理状态
```

### 方案三：极简版（用于小尺寸）
```
特点：
- 纯色填充
- 无渐变、无动画
- 清晰易识别
- 用途：favicon、小图标、列表项
```

### 尺寸规范
```
- sm:  32px   (列表项、小图标)
- md:  48px   (导航栏、卡片标题)
- lg:  64px   (页面标题、模态框)
- xl:  96px   (Hero区域、大型展示)
```

---

## 色彩系统

### 主色系 - 金黄色
```
#FFFBF0  - 最浅（背景）
#FEF3E0  - 浅色
#FDE8C0  - 浅色
#FDD9A0  - 浅色
#FCC880  - 浅色
#F4C430  ← 主品牌色
#E8B800  - 深色（悬停）
#D4A000  - 深色
#B88800  - 深色
#9C7000  - 最深（文字）
```

### 功能色
```
成功: #10B981 (绿色)
警告: #F59E0B (橙色)
错误: #EF4444 (红色)
信息: #3B82F6 (蓝色)
```

### 使用规则
```
✅ 主操作按钮 → 主色 (#F4C430)
✅ 悬停状态 → 深色 (#E8B800)
✅ 背景强调 → 浅色 (#FEF3E0)
✅ 文字强调 → 主色 (#F4C430)
❌ 不要使用纯黑或纯白作为主色
❌ 不要在深色背景上使用浅色主色
```

---

## 排版规范

### 字体选择
```
显示字体（标题）: 
  - 推荐: Poppins Bold, Montserrat Bold
  - 用途: H1, H2, 品牌标题
  - 特点: 现代、有力、易识别

正文字体:
  - 推荐: Inter, Roboto
  - 用途: 正文、描述、标签
  - 特点: 清晰、易读、专业

代码字体:
  - 推荐: JetBrains Mono, Fira Code
  - 用途: 代码块、API文档
  - 特点: 等宽、清晰
```

### 字号规范
```
H1: 48px - 64px  (页面标题)
H2: 32px - 40px  (章节标题)
H3: 24px - 28px  (小标题)
Body: 14px - 16px (正文)
Small: 12px - 13px (辅助文字)
```

---

## 组件使用

### 1. BrandLogo 组件
```tsx
// 基础用法
<BrandLogo size="md" />

// 显示文字
<BrandLogo size="md" showText={true} />

// 动画版本（加载状态）
<BrandLogo size="lg" variant="animated" />

// 极简版本（小图标）
<BrandLogo size="sm" variant="minimal" />
```

### 2. BrandButton 组件
```tsx
// 主按钮（推荐用于主要操作）
<BrandButton variant="primary" size="md">
  Start Exploring
</BrandButton>

// 次按钮（推荐用于次要操作）
<BrandButton variant="secondary" size="md">
  Learn More
</BrandButton>

// 幽灵按钮（推荐用于文字链接）
<BrandButton variant="ghost" size="sm">
  View Details
</BrandButton>

// 加载状态
<BrandButton loading={true}>
  Processing...
</BrandButton>
```

### 3. BrandCard 组件
```tsx
<BrandCard
  title="YOLOv8 Detection"
  description="Real-time object detection"
  status="active"
  onClick={() => console.log('clicked')}
>
  <BrandBadge label="Popular" variant="primary" />
</BrandCard>
```

### 4. BrandLoader 组件
```tsx
// 加载动画
<BrandLoader text="Loading Models..." size="md" />
```

### 5. BrandBadge 组件
```tsx
<BrandBadge label="New" variant="primary" size="md" />
<BrandBadge label="Popular" variant="success" size="sm" />
```

---

## 应用场景

### 场景1：导航栏
```
位置: 左上角
大小: md (48px)
变体: default
文字: 显示 (showText=true)
效果: 悬停时轻微放大
```

### 场景2：加载指示器
```
位置: 页面中心
大小: lg (64px)
变体: animated
文字: 显示加载文本
效果: 持续旋转 + 脉动
```

### 场景3：模型卡片
```
位置: 卡片顶部
大小: sm (32px)
变体: default
效果: 卡片悬停时发光
```

### 场景4：页面Hero区域
```
位置: 标题上方
大小: xl (96px)
变体: animated
效果: 上下浮动动画
```

### 场景5：品牌水印
```
位置: 页面右下角
大小: xl (96px)
变体: default
透明度: 5% - 10%
效果: 不可交互
```

### 场景6：Favicon
```
位置: 浏览器标签
大小: 16px / 32px
变体: minimal
格式: .ico / .png
```

---

## 动画指南

### 1. Logo旋转动画
```
持续时间: 3秒
循环: 无限
缓动: linear
用途: 加载状态、实时推理
```

### 2. 脉动动画
```
持续时间: 2秒
循环: 无限
缓动: ease-in-out
用途: 状态指示器、中心点缀
```

### 3. 浮动动画
```
持续时间: 3秒
循环: 无限
距离: ±10px
用途: Hero区域Logo
```

### 4. 按钮交互
```
悬停: scale(1.02)
点击: scale(0.98)
过渡: 200ms
```

### 5. 卡片交互
```
悬停: translateY(-4px) + 阴影增强
过渡: 300ms
```

---

## 最佳实践

### ✅ 推荐做法
1. **一致性** - 在整个平台使用相同的Logo和色彩
2. **对比度** - 确保文字与背景有足够对比
3. **响应式** - 在不同屏幕尺寸上测试Logo显示
4. **性能** - 使用SVG格式以获得最佳性能
5. **可访问性** - 为Logo添加alt文本和ARIA标签

### ❌ 避免做法
1. **变形** - 不要拉伸或压缩Logo
2. **颜色改变** - 不要改变Logo的金黄色
3. **过度装饰** - 不要添加额外的效果或阴影
4. **过小显示** - 不要在小于32px的尺寸显示复杂Logo
5. **背景冲突** - 不要在相似颜色背景上显示Logo

---

## 集成步骤

### 1. 导入组件
```tsx
import BrandLogo from '@/components/brand/BrandLogo'
import { BrandButton, BrandCard, BrandBadge } from '@/components/brand/BrandComponents'
import { BrandColors } from '@/components/brand/BrandColors'
```

### 2. 在导航栏中使用
```tsx
<nav>
  <BrandLogo size="md" showText={true} />
  {/* 其他导航项 */}
</nav>
```

### 3. 在按钮中使用
```tsx
<BrandButton variant="primary" size="lg">
  Start Exploring
</BrandButton>
```

### 4. 在卡片中使用
```tsx
<BrandCard title="Model" description="Description">
  <BrandBadge label="Active" />
</BrandCard>
```

### 5. 应用色彩系统
```tsx
import { BrandColors } from '@/components/brand/BrandColors'

const primaryColor = BrandColors.primary[500] // #F4C430
const successColor = BrandColors.success      // #10B981
```

---

## 文件结构
```
frontend/src/components/brand/
├── BrandColors.ts          # 色彩系统定义
├── BrandLogo.tsx           # Logo组件
├── BrandComponents.tsx     # 按钮、卡片等组件
├── BrandShowcase.tsx       # 完整展示页面
└── README.md              # 本文档
```

---

## 常见问题

### Q: 可以改变Logo的颜色吗？
A: 不建议。金黄色是品牌的核心识别元素。如需特殊场景，请使用透明度而非改变颜色。

### Q: Logo可以用在深色背景上吗？
A: 可以，但需要确保对比度足够。建议在深色背景上使用浅色版本或添加白色背景。

### Q: 如何在移动端显示Logo？
A: 使用响应式尺寸：
- 手机: sm (32px)
- 平板: md (48px)
- 桌面: lg (64px)

### Q: 动画会影响性能吗？
A: 使用CSS动画而非JavaScript，性能影响最小。建议仅在关键位置使用动画。

### Q: 如何导出Logo为PNG/SVG？
A: 所有Logo都是SVG格式，可直接导出。使用浏览器开发者工具或在线转换工具。

---

## 更新日志

### v1.0.0 (2024-01-20)
- ✅ 初始版本发布
- ✅ 完成Logo改造方案
- ✅ 建立色彩系统
- ✅ 创建核心组件
- ✅ 编写设计指南

---

## 联系方式

如有设计相关问题，请联系：
- 设计团队: design@modelsquare.com
- 技术支持: support@modelsquare.com

---

**最后更新**: 2024-01-20
**版本**: 1.0.0
**维护者**: ModelSquare Design Team
