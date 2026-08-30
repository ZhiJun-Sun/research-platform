---
name: svg-flowchart-designer
description: 画图/图表/流程图/架构图/场景图/数据卡片/飞轮图/漫画/信息图/配图/SVG/HTML图表/分析图片/仿照参考图/生成示意图/图示。当用户说'帮我画个图'、'生成一张图'、'做一张配图'、'出一张图'、'图表'、'draw'、'diagram'等任何作图、出图意图时触发。支持 3 大类 13 种子类型，SVG 或 HTML 输出。
metadata:
  version: 4
  skillId: 98e4e67c-57eb-4510-963f-ff47ebc517b3
---

# SVG/HTML 图表设计 Skill（v3.1）

基于 20+ 张真实落地图 + 外部案例分析，提供 **3 大类 13 种子类型** 的完整设计规范与代码骨架。
支持从"描述画图"到"参考图模仿"到"修改迭代"的全流程。

---

## 一、4 种使用姿势（入口路由）

收到用户请求后，首先判断属于哪种使用姿势：

| 姿势 | 触发信号 | 处理流程 |
|------|---------|---------|
| **A. 描述画图** | 用户说"画一个 XX 图"、"帮我做张配图" | 意图识别 -> 匹配类型 -> 加载 type-gallery -> 生成代码 -> 输出文件 -> 告知路径 |
| **B. 参考图模仿** | 用户传入一张图片 + "画一个类似的" | 分析参考图结构/配色/布局 -> 匹配最近类型 -> 提取参数 -> 生成定制化代码 |
| **C. 修改迭代** | 用户说"改一下标题"/"颜色换成蓝色" | 定位已输出文件 -> 修改 SVG/HTML 源码 -> 告知更新后路径 |
| **D. 提示词输出** | 类型为 E1/E2 且有图片占位 | 输出的 HTML 中 hover 可见提示词 + 点击复制（交互已内嵌） |

### 姿势判断决策树

```
用户请求是什么？
├── 传入了图片（文件/截图/链接）
│   ├── 说"画类似的"/"模仿这个" → 姿势 B
│   └── 说"分析这张图" → 姿势 B（分析后给出建议，不直接生成）
├── 说"修改"/"改一下"/"换成"/"替换"
│   └── → 姿势 C（修改迭代）
├── 说"画"/"生成"/"做一个"/"出一张"/"draw"
│   └── → 姿势 A（描述画图）→ 进入类型匹配
└── 不确定 → 追问用户
```

---

## 二、类型匹配（姿势 A 详细流程）

### 图表分类体系

| 大类 | 代号 | 特征 | 输出格式 |
|------|------|------|---------|
| **技术正式类** | T | 架构图/流程图/对比图/矩阵图 | SVG |
| **场景化类** | S | 含图标/角色/对话气泡/数据卡片 | SVG |
| **漫画娱乐类** | E | 信息图/四格漫画/卡通排版 | HTML |

### 13 种子类型速查

| 代号 | 名称 | 触发词 | 输出 |
|------|------|--------|------|
| T1 | 纵向分层流程图 | 流程图/管道/pipeline | SVG |
| T2 | 横向多阶段矩阵 | 泳道图/多阶段/matrix | SVG |
| T3 | 双栏对比图 | 对比/before-after/VS | SVG |
| T4 | 多层架构图 | 架构图/分层/4层 | SVG |
| T5 | 多列卡片图 | 三个维度/并列/三列 | SVG |
| T6 | 分叉汇聚流程图 | 执行流程/分叉/汇聚 | SVG |
| T7 | 同心嵌套图 | 层次/核心外围/洋葱 | SVG |
| S1 | 场景化流程图 | 带图标的流程/文档流转 | SVG |
| S2 | 角色引导式图 | 机器人说话/AI角色/对话 | SVG |
| S3 | 环形飞轮图 | 飞轮/循环/cycle/闭环 | SVG |
| S4 | 数据展示卡片 | 数据卡片/KPI/大数字 | SVG |
| E1 | 漫画信息图 | 漫画信息图/数据+叙事 | HTML |
| E2 | 四格叙事漫画 | 四格漫画/故事叙事 | HTML |

### 意图识别决策树

```
用户说了什么？
├── 含「对比」「VS」「前后」→ T3
├── 含「架构」「分层」「4 层」→ T4
├── 含「三个」「并列」「三列」「维度」→ T5
├── 含「飞轮」「循环」「闭环」→ S3
├── 含「数据」「KPI」「大数字」「dashboard」→ S4
├── 含「机器人」「AI 角色」「对话气泡」→ S2
├── 含「图标」「场景」「文档流转」「带图的流程」→ S1
├── 含「流程」「pipeline」→ T1 或 T6（看是否分叉）
├── 含「层次」「核心外围」「洋葱」→ T7
├── 含「矩阵」「泳道」「阶段」→ T2
├── 含「漫画」「四格」「故事」→ E2
├── 含「信息图」「数据可视化」「公众号」→ E1
└── 不确定 → 追问用户，列出类型选项
```

匹配到类型后，加载 `references/type-gallery.md` 中对应章节的设计规范和代码骨架。

---

## 三、参考图分析（姿势 B 详细流程）

当用户传入一张参考图时：

### Step 1: 分析图片内容

观察并记录：
- **布局结构**：纵向/横向/网格/环形/同心/双栏
- **配色方案**：主色/辅助色/背景色/强调色
- **文字元素**：标题层级/字体大小/对齐方式
- **图标类型**：几何图标/emoji/无图标
- **特殊元素**：箭头形式/气泡/卡片/进度条/角色

### Step 2: 匹配最近类型

从 T1-T7/S1-S4/E1-E2 中找到最接近的 1-2 个类型。如果没有完全匹配的，选最近的并说明差异。

### Step 3: 提取关键参数

从参考图中提取：
- 颜色 hex 值（用于替换默认配色）
- 布局参数（列数/行数/间距）
- 内容结构（节点数量/层级数）

### Step 4: 生成代码

基于匹配的类型范式 + 提取的参数，生成定制化代码。

### Step 5: 告知差异

如有无法复刻的部分（如真实照片、复杂手绘），明确告知并给出替代建议。

---

## 四、输出规范

### 文件路径

所有产物统一输出到用户文稿目录：

```
~/Documents/svg-output/{工作目录}/
```

工作目录命名规则：`{类型代号}-{描述短语}-{YYYYMMDD-HHmm}`
例：`T4-test-architecture-20260323-1542/`

每个工作目录内包含：
```
T4-test-architecture-20260323-1542/
  T4-test-architecture.svg    # SVG 源文件（可编辑，可用浏览器直接打开）
```

### 创建工作目录

每次生成新图时，执行：
```bash
mkdir -p ~/Documents/svg-output/{工作目录名}
```

### 文件命名

- SVG/HTML 文件：`{类型代号}-{描述短语}.{svg|html}`

### 插图文件编号规则（用于文章配图场景）

当为文章生成多张配图时，images 目录下的文件按**引用顺序**加数字前缀：

```
images/
├── 1_three-way-comparison.svg      # 第 1 张引用
├── 2_type-overview.svg             # 第 2 张引用
├── 3_1-T1-vertical-pipeline.svg    # 第 3 章第 1 张
├── 3_2-T2-horizontal-matrix.svg    # 第 3 章第 2 张
├── 3_2b-T2b-variant.svg            # 第 3 章第 2 张的变体（b 后缀）
├── 4_skill-architecture.svg        # 第 4 张引用
└── 5_usage-modes.svg               # 第 5 张引用
```

**规则**：
- 主序号 = 文章中首次引用的顺序（1, 2, 3, 4, 5...）
- 同一章节有多张图时用下划线分隔子序号：`3_1`, `3_2`, `3_3`...
- 中途插入新图不打乱已有编号，用小数/字母后缀：`1_1`, `3_2b`
- 文件名格式：`{序号}_{描述短语}.{svg|html}`

### 输出完成后

生成文件后，直接告知用户文件路径：
- SVG/HTML 文件可用浏览器直接打开预览
- 路径格式：`~/Documents/svg-output/{工作目录}/{文件名}.{svg|html}`

---

## 五、修改迭代流程（姿势 C）

用户说"修改"时的处理流程：

### Step 1: 定位文件

- 优先找当前会话中最近生成的文件
- 如果用户指定了文件名或路径，按指定的来
- 检查 `~/Documents/svg-output/` 下最近的工作目录

### Step 2: 修改源文件

直接修改 SVG 或 HTML 源文件。常见修改操作：

| 用户说 | 操作 |
|--------|------|
| "把标题改成 XX" | 找到 `<text>` 标签修改文字 |
| "颜色换成蓝色" | 修改 `fill`/`stroke` 属性 |
| "加一个步骤" | 复制节点代码块，调整 y 坐标 |
| "删掉第三列" | 移除对应的 SVG 元素组 |
| "换个背景色" | 修改最外层 `<rect>` 的 fill |

### Step 3: 告知路径

修改完成后，告知用户更新后的文件路径，可用浏览器直接打开预览。

---

## 六、通用技术规范

### SVG 基础设置
```xml
<svg xmlns="http://www.w3.org/2000/svg"
     width="{宽}" height="{高}"
     viewBox="0 0 {宽} {高}"
     font-family="Microsoft YaHei, PingFang SC, sans-serif">
```

> **注意** 避免SVG输出尺寸和内容实际尺寸不一样，有大量空白的情况，注意检查各个尺寸输出防止大量边界的空白。


### 必备 defs
```xml
<defs>
  <marker id="arrow" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
    <polygon points="0 0, 10 3.5, 0 7" fill="#555"/>
  </marker>
  <filter id="s"><feDropShadow dx="1" dy="2" stdDeviation="3" flood-opacity="0.13"/></filter>
  <filter id="s2"><feDropShadow dx="0" dy="1" stdDeviation="2" flood-opacity="0.09"/></filter>
  <linearGradient id="gTitle" x1="0%" y1="0%" x2="100%" y2="0%">
    <stop offset="0%" style="stop-color:#1A3060"/>
    <stop offset="100%" style="stop-color:#3A60A0"/>
  </linearGradient>
</defs>
```

### 颜色体系

| 语义 | 边框 | 卡片填充 | 标题文字 | 次级文字 |
|------|------|---------|---------|---------|
| 数据/信息层（蓝） | `#5B8DD9` | `#E8F2FF` | `#2B5090` | `#5A7AAA` |
| 规则/知识层（紫） | `#9B6DC8` | `#F0E8FC` | `#4A2070` | `#7A4AAA` |
| 执行层（深色） | — | `#2D3E56` | `white` | `#AACCFF` |
| 输出/成功（绿） | `#3A9A3A` | `#E8F8E8` | `#1A5A1A` | `#5A9A5A` |
| 问题/BEFORE（红） | `#C03030` | `#FFF0F0` | `#B03030` | `#C06060` |
| 警告（橙） | `#E08020` | `#FFF8E8` | `#7A4000` | `#AA6020` |

### 字体规范

| 层级 | font-size | font-weight |
|------|-----------|-------------|
| 主标题 | 17-19 | bold |
| 副标题 | 11 | normal |
| 卡片标题 | 12-13 | bold |
| 卡片描述 | 10 | normal |
| 小标注 | 9 | — |

### 关键规范提醒

- **禁止 `writing-mode="tb"`**：用横排或 `transform="rotate(-90)"`
- **圆角标题头补丁**：彩色 header 下方加同色无圆角 rect 覆盖缝隙
- **执行层必须深色背景**：范式 D（T4）的核心视觉特征
- **XML 注释禁止 `--`**：用 `====` 替代
- **`refX` 统一用 `9`**（不是 `10`）

---

## 七、详细规范参考（按需加载）

当匹配到具体类型后，按需加载以下参考文件：

| 文件 | 内容 | 何时加载 |
|------|------|---------|
| `references/type-gallery.md` | 13 种类型的设计要点 + 关键代码 + S1-S4 详细规范 + E1-E2 HTML 模板 | 匹配到类型后 |
| `references/article-svg-patterns.md` | T3-T7（范式 C-G）完整 SVG 代码骨架 | 需要 T3-T7 完整代码时 |
### 完整示例文件（`examples/` 目录）

可用 `examples/index.html` 在浏览器中打开画廊总览（`python3 -m http.server` 即可）。

| 文件 | 类型 | 格式 |
|------|------|------|
| `examples/index.html` | 画廊总览页（iframe 聚合所有示例） | HTML |
| `examples/T1-vertical-pipeline.svg` | T1 纵向分层流程图 | SVG |
| `examples/T2-horizontal-matrix.svg` | T2 横向多阶段矩阵 | SVG |
| `examples/T2b-horizontal-matrix-eval.svg` | T2 变体 — 评测横向矩阵 | SVG |
| `examples/T3-before-after-comparison.svg` | T3 双栏对比图 (Before/After) | SVG |
| `examples/T3b-dual-column-vs.svg` | T3 变体 — VS 双栏 | SVG |
| `examples/T4-multi-layer-architecture.svg` | T4 多层架构图 | SVG |
| `examples/T5-multi-column-cards.svg` | T5 多列卡片图 | SVG |
| `examples/T7-concentric-nested.svg` | T7 同心嵌套图 | SVG |
| `examples/T-branch-cards.svg` | T6 分叉汇聚流程图 | SVG |
| `examples/T-mixed-timeline-signal.svg` | T 混合时间线信号图 | SVG |
| `examples/S1-scenario-workflow.svg` | S1 场景化流程图 | SVG |
| `examples/S2-character-guided.svg` | S2 角色引导式图 | SVG |
| `examples/S3-flywheel-cycle.svg` | S3 环形飞轮图 | SVG |
| `examples/S4-data-showcase-cards.svg` | S4 数据展示卡片 | SVG |
| `examples/E1-comic-infographic.html` | E1 漫画信息图（含 hover 提示词交互） | HTML |
| `examples/E2-four-panel-comic.html` | E2 四格叙事漫画（含 hover 提示词交互） | HTML |

### 加载策略

1. **先加载 `type-gallery.md`** 中对应类型的章节（设计要点 + 关键代码片段）
2. 如果需要 T3-T7 完整代码骨架，再加载 `article-svg-patterns.md` 中对应范式
3. 配色/字体规范直接参考本文件第六节「通用技术规范」
4. 完整示例文件在 `examples/` 目录，可用 `examples/index.html` 浏览画廊

---

## 八、注意事项

| 坑 | 解决方法 |
|----|---------|
| XML 注释 `--` | 用 `====` 替代 |
| 圆角标题头缝隙 | 加同色无圆角补丁 rect |
| `writing-mode="tb"` | 横排或 rotate |
| `refX="10"` | 统一 `refX="9"` |
| 执行层无深色背景 | 必须 `#2D3E56` |
| 多列宽度不等 | 统一列宽 |
| 层间箭头悬空 | y2=层底+17 |
| 中文不显示 | `<svg>` 标签设 font-family |
| SVG输出尺寸和内容实际尺寸不一样，有大量空白 | 注意检查尺寸防止大量边界的空白 |
| E 类型预览 | HTML 用浏览器直接打开即可 |