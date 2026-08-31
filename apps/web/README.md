# HydroLab 前端与 FastAPI 联调

面向水文与通用时序预测研究的实验管理平台。前端保留定版交互原型；运行中心已接入本地 FastAPI 的认证与受保护 Fake/InMemory 工作区 API，用于验证真实请求、加载、错误和 Run 状态操作。

## 技术栈

| 类别 | 技术 |
|------|------|
| 框架 | Vite 8 + React 18 + TypeScript 5 |
| UI | shadcn/ui + TailwindCSS v4 |
| 路由 | React Router v7 |
| 状态管理 | Zustand v5 |
| 数据请求 | Fetch API |
| 后端 / 部署 | 参见 `cf-web-artifacts` 或者 `website-builder` skill |

## 目录结构

```
react-ts/
├── src/
│   ├── pages/            # 页面组件
│   ├── components/
│   │   └── ui/           # shadcn/ui 组件（用 npx shadcn@latest add 添加）
│   ├── lib/
│   │   ├── appwrite.ts   # Appwrite client 初始化 + loginWithKuaishou
│   │   └── utils.ts      # tailwind-merge / clsx 工具
│   ├── App.tsx           # 路由配置（React Router <Routes>）
│   ├── main.tsx          # 应用入口
│   └── index.css
├── .env.example          # 环境变量模版
├── .npmrc                # 快手内部 npm 源配置
├── components.json       # shadcn/ui 配置
├── AGENTS.md             # AI Agent 上下文说明
└── README.md
```

## 本地前后端联调

终端一：启动 FastAPI（默认 InMemory/Fake Adapter，重启会重置开发数据）：

```bash
cd apps/api
uv sync
uv run uvicorn hydrolab.main:app --host 127.0.0.1 --port 8011
```

终端二：启动 Vite（`/api` 自动代理到 `8011`）：

```bash
cd apps/web
npm install
npm run dev -- --host 127.0.0.1 --port 5175
```

访问 `http://127.0.0.1:5175/`。前端会以本地开发管理员 `admin@hydrolab.cn / admin123456` 登录，读取受保护的 Fake 工作区数据；若 API 重启导致 Token 失效，客户端会自动重新登录并重试一次请求。

```bash
# 前端构建
npm run build
```

生产部署编排及 Ubuntu GPU 验收见 `../../infra/README.md`。

## 当前接入范围

- **运行中心**：已接入 FastAPI `/auth/login` 和仅 local/test 启用的受保护 Demo 工作区 API；真实展示 Fake Runner 的任务列表，并支持推进/取消状态操作。浏览器已验证任务加载、推进与 Token 重启恢复。
- **其他页面**：数据、代码、实验、Checkpoint、结果与对比仍保留交互原型数据。后端已具备相应 B1–B8 API，但尚待按页面替换为真实 API Client。
- **训练执行**：当前是 Fake/InMemory Runner，不会启动真实训练或占用服务器 GPU。

## 原型范围

- 运行中心：首页优先展示训练任务与等待队列；GPU 状态缩为可点击摘要，并在侧边抽屉中展示详细资源信息。
- 全局资源流：平台不设项目层级，侧栏按“数据 → 模型代码 → 实验 → Checkpoint → 结果与对比”组织。
- 实验向导：分步骤选择代码、数据、训练模式、Checkpoint、动态超参数与资源；同时提供高级结构化单页模式。
- 训练详情：阶段/Epoch、Loss 与水文指标、实时日志、GPU 状态、参数和数据血缘；支持拖拽卡片排序、隐藏/恢复并保存个人布局。
- 资源详情：资源默认仅自己可见，并从详情页直接发起分享。
- 实验创建：标准分步向导与分区折叠的高级结构化表单可切换。
- 结果与对比：先进入所有完成实验的结果索引，支持搜索、筛选、排序、进入单次结果详情，以及勾选 2–5 个结果进入指标、参数、过程线和逐流域四区对比；详情包含总览、逐流域诊断、结果资产、绘图与自选导出。
- Checkpoint：完整展示来源、Scaler、优化器、兼容性和派生运行，并通过统一向导完成续训、微调、评估或预测；不兼容时必须配置修复。
- 资源分享：详情内创建、复制与撤销有期限只读链接；侧栏集中管理分享链接和运行环境。
- 运行恢复：失败或取消的 Run 保留现场，允许按条件从失败阶段重试或复制配置。
- 首次使用：运行中心提供可跳过的新手清单，各列表使用带主操作的空状态。
- 主题：工程控制台视觉，信号橙 `#FF4D00`，支持系统/亮色/深色切换。

当前所有业务数据均为演示数据，不会发起真实训练或修改服务器资源。

## 路由

本模板使用 **React Router v7**，路由配置在 `src/App.tsx`，页面组件放在 `src/pages/`。

**新增页面**：
1. 在 `src/pages/` 下创建页面组件（如 `ProfilePage.tsx`）
2. 在 `src/App.tsx` 的 `<Routes>` 中添加对应 `<Route>`

```tsx
// src/App.tsx
<Routes>
  <Route path="/" element={<HomePage />} />
  <Route path="/about" element={<AboutPage />} />
</Routes>
```

页面内跳转：

```tsx
import { Link, useNavigate } from 'react-router'

<Link to="/about">关于</Link>

const navigate = useNavigate()
navigate('/about')
navigate(-1) // 返回上一页
```

## 添加更多 shadcn/ui 组件

```bash
npx shadcn@latest add <component-name>
```

## 约束说明

- **npm 源**：必须使用 `https://npm.corp.kuaishou.com/`
- **Appwrite SDK**：只能使用 `@codeflicker/appwrite`，禁用官方包
- **登录**：只允许快手 SSO (`OAuthProvider.Kuaishou`)
- **UI 组件**：推荐使用 shadcn/ui + TailwindCSS

> Appwrite 数据库配置、用户认证、部署等详细说明，请参见 `cf-web-artifacts` skill。
