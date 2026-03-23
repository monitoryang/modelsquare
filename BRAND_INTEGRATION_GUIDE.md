# 🎨 品牌系统集成指南

## ✅ 已完成的集成

### 1. 主布局 (MainLayout.tsx)
已将你的金黄色Logo集成到应用的主布局中：

```tsx
// 导入品牌Logo
import { BrandLogo } from '../components/brand'

// 在Logo区域使用
<div style={S.logoArea} onClick={() => navigate('/')}>
  <BrandLogo size="sm" variant="default" />
  {!collapsed && <span style={S.logoText}>ModelSquare</span>}
</div>
```

**效果**:
- ✅ 导航栏左上角显示你的金黄色Logo
- ✅ Logo 可点击返回首页
- ✅ 侧边栏折叠时Logo自动隐藏文字
- ✅ Logo 文字颜色改为金黄色 (#F4C430)

---

## 🚀 后续集成建议

### 2. 首页 (Home/index.tsx)
```tsx
import { BrandLogo, BrandButton, BrandCard } from '@/components/brand'

export default function Home() {
  return (
    <div>
      {/* Hero区域 */}
      <section style={{ textAlign: 'center', padding: '60px 20px' }}>
        <BrandLogo size="xl" variant="animated" />
        <h1>欢迎来到 ModelSquare</h1>
        <p>部署和管理 AI 模型的最简单方式</p>
        <BrandButton variant="primary" size="lg">
          开始探索
        </BrandButton>
      </section>

      {/* 模型卡片 */}
      <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '20px' }}>
        {models.map(model => (
          <BrandCard
            key={model.id}
            title={model.name}
            description={model.description}
            status="active"
          />
        ))}
      </section>
    </div>
  )
}
```

### 3. 模型列表页面 (Models)
```tsx
import { BrandCard, BrandBadge, BrandButton } from '@/components/brand'

// 使用 BrandCard 替换现有的卡片组件
// 使用 BrandBadge 显示模型状态
// 使用 BrandButton 替换操作按钮
```

### 4. 加载状态
```tsx
import { BrandLoader } from '@/components/brand'

// 在数据加载时显示
{isLoading && <BrandLoader text="加载中..." size="lg" />}
```

### 5. 按钮替换
```tsx
import { BrandButton } from '@/components/brand'

// 替换所有 Ant Design 按钮
// 主要操作: <BrandButton variant="primary">操作</BrandButton>
// 次要操作: <BrandButton variant="secondary">操作</BrandButton>
// 文字链接: <BrandButton variant="ghost">链接</BrandButton>
```

---

## 📋 集成清单

- [x] 主布局 Logo 集成
- [ ] 首页 Hero 区域
- [ ] 模型列表卡片
- [ ] 加载指示器
- [ ] 按钮替换
- [ ] 表单元素
- [ ] 错误页面
- [ ] 成功提示

---

## 🎨 品牌色应用

### 主色 (#F4C430)
- Logo 文字
- 主按钮
- 活跃导航项
- 强调文字

### 功能色
- 成功: #10B981 (绿色)
- 警告: #F59E0B (橙色)
- 错误: #EF4444 (红色)
- 信息: #3B82F6 (蓝色)

---

## 💡 使用示例

### 导入组件
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

### 常见组合
```tsx
// 导航栏
<BrandLogo size="md" />

// 加载页面
<BrandLogo size="lg" variant="animated" />
<BrandLoader text="加载中..." />

// 模型卡片
<BrandCard title="Model" description="Desc" status="active">
  <BrandBadge label="Popular" />
</BrandCard>

// 按钮组
<BrandButton variant="primary">主操作</BrandButton>
<BrandButton variant="secondary">次操作</BrandButton>
```

---

## 📚 相关文档

- `frontend/src/components/brand/README.md` - 完整指南
- `frontend/src/components/brand/QUICK_REFERENCE.md` - 快速查询
- `frontend/src/components/brand/examples.tsx` - 8个使用示例

---

## ✨ 现在的效果

打开应用后，你会看到：
- ✅ 导航栏左上角显示你的金黄色Logo
- ✅ Logo 旁边是 "ModelSquare" 文字（金黄色）
- ✅ 侧边栏折叠时Logo自动调整
- ✅ Logo 可点击返回首页

---

**集成完成！现在可以继续在其他页面中使用品牌组件了。** 🎉
