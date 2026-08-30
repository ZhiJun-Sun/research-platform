# HydroLab 交互原型

面向水文与通用时序预测研究的实验管理平台原型。当前阶段使用明确标记的模拟数据验证信息架构和关键操作流程，随后再接入 FastAPI、PostgreSQL、Redis、MinIO、MLflow 与双 GPU Runner。

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

## 快速开始

```bash
# 1. 复制环境变量
cp .env.example .env.local
# 填写 VITE_APPWRITE_PROJECT_ID

# 2. 安装依赖
npm install

# 3. 启动开发服务器
npm run dev

# 4. 构建
npm run build
```

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
