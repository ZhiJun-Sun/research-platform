# AGENTS.md

> [!IMPORTANT]
> **用户认证、数据库操作、部署等详细说明，请读取并使用 `cf-web-artifacts` 或者 `website-builder` skill，本文件不重复记录。**

> 本文件遵循 [agents.md](https://agents.md/) 规范，为 AI Agent 提供项目上下文。

## 项目概览

本项目基于 `cf-web-artifacts` 或者 `website-builder` skill 构建的快手内部全栈 React 模板。

- **前端**：Vite 8 + React 18 + TypeScript 5
- **UI**：shadcn/ui + TailwindCSS v4
- **路由**：React Router v7
- **状态管理**：Zustand v5
- **数据请求**：Fetch API
- **当前阶段**：业务页面已全部接入真实后端 API（运行中心真实 Runs、Run 详情 SSE/日志/事件流、结果绘图/导出/对比、实验草稿提交）；Fake/InMemory Adapter 提供本地联调数据，真实 S3/Celery/MLflow/Docker Runner 待 Spike 门禁后切换
- **产品重点**：任务与队列优先的运行中心、紧凑 GPU 抽屉、无项目层级的六入口资源流、向导/结构化表单双模式创建、可拖拽训练详情、详情内资源分享、结果索引与单次/多次实验分析
- **视觉规范**：工程控制台亮/暗主题，`#FF4D00` 仅作操作强调色，中等信息密度，无渐变和装饰阴影
- **设计记录**：`../../docs/prototype-design-record.md`
- **后端 / 部署**：参见 `pde-agent` skill

## 目录结构

```
src/
├── pages/            # 页面组件（每个路由对应一个文件）
├── components/
│   └── ui/           # shadcn/ui 组件（用 npx shadcn@latest add 添加，不要手动修改）
├── lib/
│   ├── appwrite.ts   # Appwrite client、account、databases、storage、loginWithKuaishou 导出（endpoint 已固定，禁止修改）
│   └── utils.ts      # cn() 工具函数（tailwind-merge + clsx）
├── App.tsx           # 路由配置（React Router <Routes>）
├── main.tsx          # 应用入口（BrowserRouter 包裹）
└── index.css         # 全局样式（TailwindCSS 入口）
```

## 路由开发规范

路由统一在 `src/App.tsx` 的 `<Routes>` 中配置，页面组件放在 `src/pages/` 目录。

### 新增页面步骤

1. 在 `src/pages/` 下创建页面组件文件（如 `ProfilePage.tsx`）
2. 在 `src/App.tsx` 中添加对应的 `<Route>`

### App.tsx 示例

```tsx
import { Routes, Route } from 'react-router'
import HomePage from '@/pages/HomePage'
import AboutPage from '@/pages/AboutPage'

function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/about" element={<AboutPage />} />
      <Route path="/profile/:id" element={<ProfilePage />} />
    </Routes>
  )
}
```

### 页面内跳转

```tsx
import { Link, useNavigate, useParams } from 'react-router'

// 声明式跳转
<Link to="/about">关于</Link>

// 编程式跳转
const navigate = useNavigate()
navigate('/about')
navigate(-1) // 返回上一页

// 动态路由参数
const { id } = useParams<{ id: string }>()
```

## 构建与启动命令

```bash
# 安装依赖（必须使用快手内部 npm 源）
pnpm install

# 启动开发服务器
pnpm dev

# 构建产物
pnpm build

# 预览构建产物
pnpm preview
```

## 已安装的 shadcn/ui 组件

`button` `card`

添加更多组件：
```bash
npx shadcn@latest add <component-name>
```

## 安全约束（禁止违反）

| 规则 | ✅ 允许 | ❌ 禁止 |
|------|---------|---------|
| 登录方式 | `loginWithKuaishou()` / `OAuthProvider.Kuaishou` | 邮箱/手机号/Google/GitHub |
| Appwrite SDK | `@codeflicker/appwrite` | 官方 `appwrite` npm 包 |
| 数据库 CLI | `appwrite-cf` | 官方 `appwrite` CLI |
| UI 组件库 | shadcn/ui + TailwindCSS（推荐） | — |
| npm 源 | `https://npm.corp.kuaishou.com/` | npmjs.org 直连（网络受限）|
| Endpoint | 禁止手动修改 | 硬编码其他 URL 字符串 |
| project_id 格式 | 纯字母数字下划线 | 含连字符 `-` |
| `appwrite-cf.config.json` | 只读，由 `appwrite-cf` 工具自动管理 | 手动修改文件内容 |
| `.static-site-deploy.json` | 只读，由部署工具自动管理 | 手动修改文件内容 |

> 用户认证、数据库操作、部署等详细说明，请读取并使用 `cf-web-artifacts` 或者 `website-builder` skill。

## 测试指令

- **开发中**：`pnpm dev` 启动后，使用浏览器自动化工具验证无白屏、无 JS 报错
- **构建验证**：`pnpm build`（无报错即通过）
- **代码检查**：`pnpm lint`
