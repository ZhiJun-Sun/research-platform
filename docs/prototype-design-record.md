# 交互原型设计记录

## 设计路由

- Mode: C（从零生成）
- Scene: 工具型应用 / 内部系统 — `references/website-design/scenes/tool-app.md`
- Purpose: 帮助水文与时序预测研究者快速查看 GPU 训练状态、创建实验、追踪训练、管理资产并比较结果。
- Tone: 冷静、精密、可信的科研工程工具；中等信息密度，避免监控大屏式压迫感。
- Differentiation: 以双 GPU 任务轨道和实验血缘为核心识别特征；信号橙只标记可执行动作与当前上下文。

## Scene Rules Applied

- 采用桌面优先的 Sidebar + Main Content 操作布局，导航稳定、内容区独立滚动。
- 页面以 14px 正文和紧凑标签为主，表格、树和详情面板保持中等密度。
- 使用边框和间距划分区域，不使用装饰性渐变与阴影。
- 所有操作提供 active、hover、focus、disabled 等明确反馈。
- 低于 768px 时侧栏折叠，双栏/三栏内容降级为单栏，表格可横向滚动。

## Theme Tokens Applied

- Theme: G 工程控制台 — `references/website-design/themes/G-technical-console.md`
- `#FF4D00` → `--color-primary`，仅用于主要按钮、激活导航和当前步骤。
- 亮色页面/卡片 `#F7F7F8` / `#FFFFFF` → 页面背景与内容表面。
- 深色页面/卡片 `#0A0A0B` / `#141416` → 系统深色模式。
- `#16A34A` / `#DC2626` → 成功与失败语义，不被主题强调色替代。
- 2/4/6px 圆角 → 按钮、输入、面板；所有表面无阴影。
- 标签、指标、日志、参数值使用等宽字体；中文标题与正文使用系统无衬线字体。
- 图表颜色通过 CSS 变量映射；实测序列使用中性深色，预测序列使用信号橙，指标语义保持独立。

## Chart Tokens Applied

- `--chart-1` / `#FF4D00` → 预测流量与主要 Loss 曲线。
- `--chart-2` / 工程蓝 → 对照实验或次级指标曲线。
- `--chart-axis-label`、`--chart-split-line` → 坐标与网格线，并随明暗主题切换。
- 图表容器使用弹性最小高度，不固定死高度；标题与图例留足顶部空间。

## Loaded Files

- `references/website-design-integration.md`
- `references/website-design/website-design.md`
- `references/website-design/scenes/tool-app.md`
- `references/website-design/themes/G-technical-console.md`
- `references/website-design/core/interaction-states.md`
- `references/website-design/core/responsive-spec.md`
- `references/website-design/data-components/echarts-config.md`

## Self-Checks Required

- 通用：无 Emoji、无渐变、无装饰阴影、非灰彩色受控、五级字号、正文对比度达标。
- 工具场景：侧栏 active、顶部操作区稳定、表单 focus、按钮多状态、数字等宽、移动端侧栏折叠。
- 工程控制台：标签/数字等宽、1px 边框、圆角不超过 6px、橙色不表达数据好坏、动效不超过 300ms。
- 交互：按钮与输入覆盖 hover/focus/active/disabled/loading/error/success 中适用状态；空状态提供下一步行动。
- 响应式：小屏触控区域至少 44px，输入字号至少 16px，表格横向滚动，不依赖 hover 传递关键信息。
