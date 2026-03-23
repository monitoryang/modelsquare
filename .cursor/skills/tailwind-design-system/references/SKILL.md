---
name: tailwind-design-system
description: >
  Tailwind CSS v4 设计系统专家。当用户需要创建或修改 UI 组件、配置主题颜色、
  构建表单/导航/数据展示/弹窗等界面、使用设计 token、添加动画交互时使用此 skill。
  涵盖 59 个组件（Button、Input、Select、Dialog、Table、Sidebar 等），
  基于 Radix UI + CVA 模式，支持亮/暗双主题。
---
# Tailwind Design System Skill
## 设计系统位置
本设计系统源码在：/mnt/14TB/yangwen/agent/skills/tailwind-design-system/
## 关键规则
### 颜色 — 只用语义 token，禁止硬编码
- `bg-primary` / `text-primary-foreground` — 主操作
- `bg-background` / `text-foreground` — 页面背景/正文
- `bg-card` — 卡片/浮层背景
- `text-muted-foreground` — 次要文字
- `bg-destructive` / `bg-success` / `bg-warning` / `bg-info` — 状态色
- `hover:bg-primary-subtle-hover` — 菜单项悬停
- 禁止使用 `bg-blue-500`、`text-gray-500`、`#3b82f6` 等
### 交互动画
- 触发器：`transition-all duration-200` + `active:scale-[0.98]`
- 菜单项：`transition-all duration-150`
- 下拉箭头：`data-[state=open]:rotate-180`
### 菜单项固定样式
`rounded-[2px] px-2 py-1.5 hover:bg-primary-subtle-hover transition-all duration-150`
### 文件组织
- 组件实现：`design-system-app/components/ui/<name>.tsx`
- Storyboard：`design-system-app/app/storyboard/components/<category>/<name>-example.tsx`
- 每组件独立文件，禁止混合
- 禁止从 `organized-components/` 导入
### 组件分类（共 59 个）
| 分类 | 组件 |
|------|------|
| 按钮 & 操作 | Button, IconButton, Toggle, ToggleGroup, DropdownMenu, ContextMenu, Command, Menubar |
| 表单元素 | Input, Textarea, Select, Checkbox, RadioGroup, Switch, Slider, InputOTP, DatePicker, FileUpload |
| 反馈 | Alert, Toast, Progress, Skeleton, Dialog, AlertDialog, Sheet, Drawer |
| 导航 | NavigationMenu, DropdownMenu, ContextMenu, Menubar, Command, Breadcrumb, Pagination, Tabs, Sidebar |
| 数据展示 | Card, Accordion, Collapsible, Table, Avatar, Badge, Chart, Carousel, AspectRatio, ScrollArea |
| 浮层 | Popover, HoverCard, Tooltip |
| 布局 | Separator, Resizable, Calendar, Timeline |
### CVA 组件变体模式
```tsx
import { cva, type VariantProps } from "class-variance-authority"
const buttonVariants = cva(
  "inline-flex items-center justify-center transition-all duration-200 active:scale-[0.98]",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary-hover",
        destructive: "bg-destructive text-destructive-foreground hover:bg-destructive-hover",
        outline: "border border-border hover:bg-muted",
        ghost: "hover:bg-muted",
        success: "bg-success text-success-foreground hover:bg-success-hover",
      },
      size: {
        sm: "h-8 px-3 text-sm",
        default: "h-9 px-4",
        lg: "h-10 px-6",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
)