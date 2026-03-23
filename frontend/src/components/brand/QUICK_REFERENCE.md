/**
 * 品牌系统快速参考卡
 * 开发者速查手册
 */

# 🚀 ModelSquare 品牌系统 - 快速参考

## 📦 导入

```tsx
import {
  BrandLogo,
  BrandButton,
  BrandCard,
  BrandBadge,
  BrandLoader,
  BrandColors,
} from '@/components/brand'
```

---

## 🎨 Logo 组件

### 基础用法
```tsx
<BrandLogo size="md" />
```

### 所有变体
```tsx
// 默认版本 (推荐用于导航栏)
<BrandLogo size="md" variant="default" />

// 动画版本 (推荐用于加载状态)
<BrandLogo size="lg" variant="animated" />

// 极简版本 (推荐用于小图标)
<BrandLogo size="sm" variant="minimal" />

// 显示文字
<BrandLogo size="md" showText={true} />
```

### 尺寸选项
```tsx
<BrandLogo size="sm" />   // 32px
<BrandLogo size="md" />   // 48px
<BrandLogo size="lg" />   // 64px
<BrandLogo size="xl" />   // 96px
```

### 常见场景
```tsx
// 导航栏
<BrandLogo size="md" showText={true} />

// 加载指示器
<BrandLogo size="lg" variant="animated" />

// Hero区域
<BrandLogo size="xl" variant="animated" />

// Favicon
<BrandLogo size="sm" variant="minimal" />
```

---

## 🔘 按钮组件

### 基础用法
```tsx
<BrandButton>Click me</BrandButton>
```

### 所有变体
```tsx
// 主按钮 (推荐用于主要操作)
<BrandButton variant="primary">Get Started</BrandButton>

// 次按钮 (推荐用于次要操作)
<BrandButton variant="secondary">Learn More</BrandButton>

// 幽灵按钮 (推荐用于文字链接)
<BrandButton variant="ghost">View Details</BrandButton>
```

### 尺寸选项
```tsx
<BrandButton size="sm">Small</BrandButton>
<BrandButton size="md">Medium</BrandButton>
<BrandButton size="lg">Large</BrandButton>
```

### 加载状态
```tsx
<BrandButton loading={true}>Processing...</BrandButton>
```

### 完整示例
```tsx
<BrandButton
  variant="primary"
  size="lg"
  loading={isLoading}
  onClick={handleClick}
>
  Start Exploring
</BrandButton>
```

---

## 🎴 卡片组件

### 基础用法
```tsx
<BrandCard
  title="Model Name"
  description="Model description"
  status="active"
/>
```

### 状态选项
```tsx
<BrandCard status="active" />    // 绿色指示器
<BrandCard status="loading" />   // 黄色脉动
<BrandCard status="error" />     // 红色指示器
```

### 完整示例
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

---

## 🏷️ 徽章组件

### 基础用法
```tsx
<BrandBadge label="New" />
```

### 颜色变体
```tsx
<BrandBadge label="New" variant="primary" />      // 金黄
<BrandBadge label="Success" variant="success" />  // 绿色
<BrandBadge label="Warning" variant="warning" />  // 橙色
<BrandBadge label="Error" variant="error" />      // 红色
```

### 尺寸选项
```tsx
<BrandBadge label="Small" size="sm" />
<BrandBadge label="Medium" size="md" />
```

---

## ⏳ 加载器组件

### 基础用法
```tsx
<BrandLoader />
```

### 自定义文字
```tsx
<BrandLoader text="Loading models..." />
```

### 尺寸选项
```tsx
<BrandLoader size="sm" />   // 32px
<BrandLoader size="md" />   // 48px
<BrandLoader size="lg" />   // 64px
```

---

## 🎨 色彩系统

### 主色系
```tsx
import { BrandColors } from '@/components/brand'

const primary = BrandColors.primary[500]        // #F4C430
const primaryLight = BrandColors.primary[100]   // #FEF3E0
const primaryDark = BrandColors.primary[700]    // #D4A000
```

### 功能色
```tsx
const success = BrandColors.success   // #10B981
const warning = BrandColors.warning   // #F59E0B
const error = BrandColors.error       // #EF4444
const info = BrandColors.info         // #3B82F6
```

### 在样式中使用
```tsx
<div style={{ color: BrandColors.primary[500] }}>
  Colored text
</div>
```

---

## 📋 常见组合

### 导航栏
```tsx
<nav className="flex items-center justify-between p-4">
  <BrandLogo size="md" showText={true} />
  <div className="flex gap-2">
    <BrandButton variant="ghost">Models</BrandButton>
    <BrandButton variant="ghost">Docs</BrandButton>
    <BrandButton variant="primary">Sign In</BrandButton>
  </div>
</nav>
```

### Hero区域
```tsx
<section className="text-center py-20">
  <BrandLogo size="xl" variant="animated" />
  <h1 className="text-5xl font-bold mt-8">Welcome</h1>
  <p className="text-xl text-gray-600 mt-4">
    Deploy AI models with ease
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
```

### 模型卡片网格
```tsx
<div className="grid grid-cols-1 md:grid-cols-3 gap-6">
  {models.map((model) => (
    <BrandCard
      key={model.id}
      title={model.name}
      description={model.description}
      status={model.status}
    >
      <BrandBadge label={model.badge} variant="primary" />
    </BrandCard>
  ))}
</div>
```

### 加载页面
```tsx
<div className="flex flex-col items-center justify-center min-h-screen">
  <BrandLogo size="xl" variant="animated" />
  <BrandLoader text="Loading..." size="lg" />
</div>
```

---

## 🎯 尺寸速查表

| 组件 | sm | md | lg | xl |
|------|----|----|----|----|
| Logo | 32px | 48px | 64px | 96px |
| Button | 小 | 中 | 大 | - |
| Badge | 小 | 中 | - | - |
| Loader | 32px | 48px | 64px | - |

---

## 🎨 颜色速查表

| 用途 | 颜色 | 十六进制 |
|------|------|---------|
| 主色 | 金黄 | #F4C430 |
| 悬停 | 深金 | #E8B800 |
| 背景 | 浅金 | #FEF3E0 |
| 成功 | 绿色 | #10B981 |
| 警告 | 橙色 | #F59E0B |
| 错误 | 红色 | #EF4444 |
| 信息 | 蓝色 | #3B82F6 |

---

## ⚡ 性能提示

```tsx
// ✅ 好的做法
const MyComponent = () => {
  return <BrandLogo size="md" />
}

// ❌ 避免
const MyComponent = () => {
  return <BrandLogo size={Math.random() > 0.5 ? 'md' : 'lg'} />
}
```

---

## 🔧 常见问题速答

| 问题 | 答案 |
|------|------|
| Logo可以改颜色吗? | 不建议，使用透明度代替 |
| 动画影响性能吗? | 否，使用CSS动画，60fps |
| 支持深色模式吗? | 是，完全支持 |
| 支持移动端吗? | 是，响应式设计 |
| 可以自定义吗? | 可以，修改BrandColors.ts |

---

## 📚 文件导航

```
brand/
├── BrandColors.ts       ← 色彩系统
├── BrandLogo.tsx        ← Logo组件
├── BrandComponents.tsx  ← 按钮、卡片等
├── BrandShowcase.tsx    ← 完整展示页面
├── examples.tsx         ← 8个使用示例
├── index.ts             ← 统一导出
├── README.md            ← 完整指南
├── DESIGN_GUIDE.md      ← 设计规范
├── VISUAL_GUIDE.md      ← 视觉指南
└── QUICK_REFERENCE.md   ← 本文件
```

---

## 🚀 快速开始 (3步)

### 1️⃣ 导入
```tsx
import { BrandLogo, BrandButton } from '@/components/brand'
```

### 2️⃣ 使用
```tsx
<BrandLogo size="md" />
<BrandButton variant="primary">Click</BrandButton>
```

### 3️⃣ 完成！
```tsx
// 就这么简单！
```

---

## 💡 Pro Tips

1. **Logo动画** - 仅在加载/等待状态使用，避免过度使用
2. **按钮变体** - primary用于主操作，secondary用于次操作
3. **卡片状态** - 使用status属性显示实时状态
4. **色彩一致** - 整个平台使用相同的BrandColors
5. **响应式** - 使用sm/md/lg/xl自动适配屏幕

---

## 🎓 学习路径

1. **快速上手** ← 你在这里
2. **查看示例** → examples.tsx (8个实际场景)
3. **深入学习** → DESIGN_GUIDE.md (完整规范)
4. **视觉参考** → VISUAL_GUIDE.md (详细设计)
5. **实际应用** → 集成到你的项目

---

## 📞 需要帮助?

- 查看 `examples.tsx` 中的8个实际使用示例
- 阅读 `DESIGN_GUIDE.md` 了解完整规范
- 参考 `VISUAL_GUIDE.md` 查看视觉细节

---

**最后更新**: 2024-01-20
**版本**: 1.0.0
**状态**: ✅ 生产就绪

祝你使用愉快！🎉
