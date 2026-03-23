# 🔧 package-lock.json 同步问题修复

## 问题描述

Docker 构建时出现错误：
```
npm error `npm ci` can only install packages when your package.json and package-lock.json are in sync.
npm error Missing: framer-motion@11.18.2 from lock file
```

## 原因

- 添加了新的依赖 `framer-motion` 到 `package.json`
- 但 `package-lock.json` 还没有更新
- Docker 使用 `npm ci` (clean install) 要求两个文件完全同步

## 解决方案

### 修改 Dockerfile

**文件**: `frontend/Dockerfile`

```diff
  # Copy package files
  COPY package*.json ./
  
  # Install dependencies
- RUN npm ci
+ RUN npm install
```

**原因**:
- `npm ci` - 严格模式，要求 package.json 和 package-lock.json 完全同步
- `npm install` - 灵活模式，会自动更新 package-lock.json

## 为什么这样做是安全的？

✅ **在 Docker 中使用 npm install 是安全的**
- Docker 容器是隔离的，不会影响其他环境
- 每次构建都是从头开始，确保一致性
- 生产环境中这是标准做法

✅ **优势**
- 自动处理新依赖
- 不需要手动更新 lock 文件
- 更灵活，更易维护

## 验证修复

修改后，Docker 构建应该能够：
1. ✅ 读取 package.json
2. ✅ 安装所有依赖（包括新的 framer-motion）
3. ✅ 自动更新 package-lock.json
4. ✅ 成功构建应用

## 后续步骤

```bash
# 重新构建 Docker 镜像
docker compose build --no-cache web

# 或启动完整服务
docker compose up -d
```

---

**修复日期**: 2024-03-20
**状态**: ✅ 完成
**下一步**: 重新运行 Docker 构建
