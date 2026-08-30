# 图表类型全景参考（3 大类 13 种）

本文件是 svg-flowchart-designer skill 的类型速查手册，供 SKILL.md 调度后按需查阅。

---

## 快速索引表

| 代号 | 名称 | 输出格式 | 推荐尺寸 | 触发词 | 详细代码位置 |
|------|------|---------|---------|--------|-------------|
| T1 | 纵向分层流程图 | SVG | 900x600 | 流程图/管道/pipeline | `examples/T1-vertical-pipeline.svg` |
| T2 | 横向多阶段矩阵 | SVG | 1350x600 | 泳道图/多阶段/matrix | `examples/T2-horizontal-matrix.svg` |
| T3 | 双栏对比图 | SVG | 860x420 | 对比/before-after/VS | `article-svg-patterns.md` 范式 C |
| T4 | 多层架构图 | SVG | 900x500 | 架构图/分层/4层 | `article-svg-patterns.md` 范式 D |
| T5 | 多列卡片图 | SVG | 860x500 | 三个维度/并列/三列 | `article-svg-patterns.md` 范式 E |
| T6 | 分叉汇聚流程图 | SVG | 900x560 | 执行流程/分叉/汇聚 | `article-svg-patterns.md` 范式 F |
| T7 | 同心嵌套图 | SVG | 900x480 | 层次/核心外围/洋葱 | `article-svg-patterns.md` 范式 G |
| S1 | 场景化流程图 | SVG | 960x420 | 带图标的流程/文档流转 | 本文件 S1 章节 |
| S2 | 角色引导式图 | SVG | 900x480 | 机器人说话/AI角色/对话气泡 | 本文件 S2 章节 |
| S3 | 环形飞轮图 | SVG | 900x520 | 飞轮/循环/cycle/闭环 | 本文件 S3 章节 |
| S4 | 数据展示卡片 | SVG | 900x480 | 数据卡片/KPI/大数字/dashboard | 本文件 S4 章节 |
| E1 | 漫画信息图 | HTML | 680px宽 | 漫画信息图/数据+叙事 | 本文件 E1 章节 |
| E2 | 四格叙事漫画 | HTML | 820px宽 | 四格漫画/故事叙事 | 本文件 E2 章节 |

---

## T1-T7 关键参数速查

### T1 纵向分层流程图
- **尺寸**：900x600
- **结构**：顶部标题栏 -> 编号行标签 -> 各层色块 -> 垂直箭头
- **关键参数**：模块宽 155px，模块间距 10px，行间箭头 22-28px
- **完整示例**：`examples/T1-vertical-pipeline.svg`

### T2 横向多阶段矩阵
- **尺寸**：1350x600
- **结构**：阶段箭头标签 -> 列背景条 -> 步骤节点行 -> 详情卡片区
- **关键参数**：列宽 270px，阶段标签宽 260px，详情卡片宽 242px
- **完整示例**：`examples/T2-horizontal-matrix.svg`

### T3 双栏对比图
- **尺寸**：860x420
- **颜色**：左栏红色系(BEFORE) `#E05050`/`#FFF0F0`，右栏绿色系(AFTER) `#2A7A2A`/`#E8F8E8`，VS 圆 `#2D3E56`
- **步骤间距**：每步 y+48
- **完整代码**：`article-svg-patterns.md` 范式 C

### T4 多层架构图
- **尺寸**：900x500
- **层级**：数据层(蓝) -> 规则层(紫) -> 执行层(深色 `#2D3E56` 必须) -> 输出层(绿)
- **执行层规则**：必须深色背景，子卡片用 `rgba(255,255,255,0.12)`
- **完整代码**：`article-svg-patterns.md` 范式 D

### T5 多列卡片图
- **尺寸**：860x500
- **列布局**：3 列 x=30/306/582，宽 248，底部绿色输出栏 y=418 高 62
- **完整代码**：`article-svg-patterns.md` 范式 E

### T6 分叉汇聚流程图
- **尺寸**：900x560
- **结构**：触发框 -> Step -> 分叉 3 列 -> 汇聚 -> 输出 -> 完成徽章
- **完整代码**：`article-svg-patterns.md` 范式 F

### T7 同心嵌套图
- **尺寸**：900x480
- **椭圆中心**：cx=450 cy=280
- **三层**：外层 rx=400 ry=176 暖色 / 中层 rx=290 ry=126 蓝色 / 内层 rx=160 ry=76 深色
- **完整代码**：`article-svg-patterns.md` 范式 G

---

## S1 场景化流程图

适用于需要「看起来像公众号配图」的工作流说明。

### 设计要点
- 用几何图形拼出图标（文档=圆角矩形+折角、代码=`</>` 文字、清单=checkbox 行、仪表盘=进度条+圆点）
- 箭头用大型多边形 polygon（不是细线 marker），颜色跟随阶段主题色
- 每个阶段是独立的「场景卡片」，有自己的图标和细节
- 背景用浅渐变（`#F8FAFE -> #EDF2FA`），不用纯白

### 推荐参数
| 属性 | 值 |
|------|-----|
| 尺寸 | 960x420 |
| 背景 | 线性渐变 `#F8FAFE -> #EDF2FA` |
| 颜色方案 | 每阶段一个主题色（蓝->橙->绿） |

### 图标绘制技巧
```xml
<!-- 文档图标 -->
<rect x="10" y="0" width="130" height="170" rx="8" fill="white" stroke="#84B0DC" stroke-width="1.5"/>
<path d="M110 0 L140 0 L140 30 L110 30 Z" fill="#E0ECF8" stroke="#84B0DC" stroke-width="1"/>
<path d="M110 0 L110 30 L140 30" fill="none" stroke="#84B0DC" stroke-width="1.5"/>

<!-- 代码行（文档内） -->
<rect x="24" y="44" width="60" height="6" rx="2" fill="#5B8DD9" opacity="0.6"/>
<rect x="24" y="56" width="90" height="6" rx="2" fill="#9B6DC8" opacity="0.5"/>

<!-- 勾选框 -->
<rect x="18" y="72" width="16" height="16" rx="3" fill="#E88020"/>
<text fill="white" font-size="11" font-weight="bold">check</text>

<!-- 进度条 -->
<rect x="56" y="68" width="80" height="6" rx="3" fill="#F0C0C0"/>
<rect x="56" y="68" width="30" height="6" rx="3" fill="#E05050"/>

<!-- 大型箭头（polygon，不是 line+marker） -->
<polygon points="0 12, 60 0, 60 6, 90 6, 90 18, 60 18, 60 24" fill="#5B8DD9" opacity="0.8"/>
```

### 完整示例
文件：`examples/S1-scenario-workflow.svg`

---

## S2 角色引导式图

适用于需要「有趣但不失专业」的流程展示。

### 设计要点
- 几何机器人角色：圆角矩形头+圆眼+天线+矩形身体+短线手臂
- 对话气泡：圆角矩形+三角尾巴（polygon），尾巴方向指向角色
- 阶段卡片：与 T5 类似但加上小图标
- 背景用浅紫色系（`#F8F4FF`）

### 推荐参数
| 属性 | 值 |
|------|-----|
| 尺寸 | 900x480 |
| 主题色 | 紫色系 `#9B6DC8` |
| 背景 | `#F8F4FF` |

### 角色绘制代码
```xml
<!-- 机器人头 -->
<rect x="10" y="20" width="80" height="70" rx="16" fill="white" stroke="#9B6DC8" stroke-width="2.5"/>
<!-- 天线 -->
<line x1="50" y1="20" x2="50" y2="6" stroke="#9B6DC8" stroke-width="2.5"/>
<circle cx="50" cy="4" r="5" fill="#9B6DC8"/>
<!-- 眼睛 -->
<circle cx="35" cy="52" r="8" fill="#9B6DC8"/>
<circle cx="35" cy="52" r="4" fill="white"/>

<!-- 对话气泡 -->
<rect x="0" y="0" width="520" height="78" rx="16" fill="white" stroke="#9B6DC8" stroke-width="2"/>
<polygon points="-8 40, 12 30, 12 50" fill="white" stroke="#9B6DC8" stroke-width="2"/>
<rect x="10" y="29" width="6" height="22" fill="white"/>
```

### 完整示例
文件：`examples/S2-character-guided.svg`

---

## S3 环形飞轮图

适用于展示「持续改进」「闭环」「飞轮效应」。

### 设计要点
- 5 个彩色圆形节点围成圆形，中心放齿轮图标
- 节点间用曲线箭头（path Q 贝塞尔曲线）连接，形成顺时针环
- 纸张质感背景（`#FBF7F0`），边框用笔记本感（`#E0D8C8`）
- 底部可加对比栏，侧面可加注解箭头

### 推荐参数
| 属性 | 值 |
|------|-----|
| 尺寸 | 900x520 |
| 飞轮中心 | (420, 280) |
| 节点半径 | r=55，分布在 r=170 圆上 |
| 背景 | 纸张色 `#FBF7F0`，边框 `#E0D8C8` |
| 节点颜色 | 蓝/紫/青/橙/粉（各不同） |

### 核心代码
```xml
<!-- 中心齿轮 -->
<circle cx="0" cy="0" r="32" fill="#F0ECE4" stroke="#C8C0B0" stroke-width="2"/>
<circle cx="0" cy="0" r="10" fill="#C8C0B0"/>
<rect x="-4" y="-36" width="8" height="10" rx="2" fill="#C8C0B0"/>

<!-- 飞轮节点 -->
<circle cx="0" cy="-170" r="55" fill="#D8ECFF" stroke="#5B8DD9" stroke-width="2"/>

<!-- 节点间曲线箭头 -->
<path d="M50 -145 Q 130 -120 120 -60" fill="none" stroke="#2D3E56" stroke-width="2.5" marker-end="url(#arrowDark)"/>
```

### 完整示例
文件：`examples/S3-flywheel-cycle.svg`

---

## S4 数据展示卡片

适用于「汇报演示」「数据洞察」「公众号封面」。

### 设计要点
- 暗色渐变背景（`#1A1410 -> #2A2018`）
- 半透明玻璃卡片（`rgba(255,255,255,0.08)` + 细白边框 `rgba(255,255,255,0.12)`）
- 金色大数字（渐变 `#E8A020 -> #F0C860`）
- 几何小图标（咖啡杯/地球/趋势折线）
- 卡片悬挂效果（顶部加小矩形+两条细线）
- 左侧大标题区域 + 右侧 2x2 卡片网格

### 推荐参数
| 属性 | 值 |
|------|-----|
| 尺寸 | 900x480 |
| 背景 | 暗棕渐变 `#1A1410 -> #2A2018` |
| Accent 色 | 金色 `#E8A020 -> #F0C860` |
| 卡片填充 | `rgba(255,255,255,0.08)` |

### 暗色主题 defs
```xml
<linearGradient id="gBg" x1="0%" y1="0%" x2="100%" y2="100%">
  <stop offset="0%" style="stop-color:#1A1410"/>
  <stop offset="100%" style="stop-color:#2A2018"/>
</linearGradient>
<linearGradient id="gGold" x1="0%" y1="0%" x2="100%" y2="0%">
  <stop offset="0%" style="stop-color:#E8A020"/>
  <stop offset="100%" style="stop-color:#F0C860"/>
</linearGradient>
```

### 完整示例
文件：`examples/S4-data-showcase-cards.svg`

---

## E1 漫画信息图

适用于「公众号科普」「数据+叙事混合」的信息图。输出为 HTML 文件。

### 设计要点
- 宽度固定 680px，响应式
- 顶部深色渐变 header + 角色/主题插画
- 主体区域：2x2 统计卡片网格，每张卡片含：大数字 + 描述 + 场景插画
- 底部：洞察要点列表（带侧边色条）
- 尾部：金句 + 深色背景

### 图片占位交互规范

E1/E2 类型的 HTML 模板中，图片区域使用 emoji 占位 + hover 显示 AI 生图提示词 + 点击复制：

```html
<!-- 图片占位区域模板 -->
<div class="illust-slot" data-prompt="这里放 AI 生图英文提示词">
  <span class="placeholder">emoji占位</span>
  <div class="prompt-overlay">
    <p class="prompt-text">这里放 AI 生图英文提示词</p>
    <button class="copy-btn" onclick="copyPrompt(this)">复制提示词</button>
  </div>
</div>
```

```css
/* 提示词 hover 浮层 */
.illust-slot { position: relative; cursor: pointer; }
.prompt-overlay {
  display: none; position: absolute; bottom: calc(100% + 6px); left: 50%;
  transform: translateX(-50%); background: rgba(26, 26, 46, 0.96); color: white;
  padding: 14px 18px; border-radius: 12px; width: 320px; z-index: 100;
  box-shadow: 0 8px 32px rgba(0,0,0,0.3); backdrop-filter: blur(4px);
  font-size: 12px; line-height: 1.6;
}
.prompt-overlay::after {
  content: ''; position: absolute; top: 100%; left: 50%; transform: translateX(-50%);
  border: 8px solid transparent; border-top-color: rgba(26, 26, 46, 0.96);
}
/* Invisible hover bridge to prevent tooltip from disappearing */
.prompt-overlay::before {
  content: ''; position: absolute; top: 100%; left: 0; width: 100%; height: 24px;
  background: transparent;
}
.illust-slot:hover .prompt-overlay { display: block; }
.prompt-text { color: #E0E0FF; margin-bottom: 8px; word-break: break-word; }
.copy-btn {
  background: #6B48FF; color: white; border: none; padding: 5px 14px;
  border-radius: 6px; cursor: pointer; font-size: 11px; font-weight: 700;
  transition: all 0.2s;
}
.copy-btn:hover { background: #8B68FF; }
.copy-btn.copied { background: #2A9A3A; }
```

```javascript
function copyPrompt(btn) {
  const text = btn.closest('.prompt-overlay').querySelector('.prompt-text').textContent.trim();
  navigator.clipboard.writeText(text).then(() => {
    btn.textContent = '已复制';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = '复制提示词'; btn.classList.remove('copied'); }, 2000);
  });
}
```

### E1 HTML 模板骨架

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;700;900&display=swap');
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Noto Sans SC', sans-serif; background: #F5F0E8; display: flex; justify-content: center; padding: 30px; }
  .infographic { width: 680px; background: white; border-radius: 20px; overflow: hidden; box-shadow: 0 8px 40px rgba(0,0,0,0.12); }

  .header { background: linear-gradient(135deg, #1A1A2E, #16213E, #0F3460); padding: 36px 40px 28px; display: flex; align-items: center; gap: 24px; }
  .progress-bar { height: 4px; background: linear-gradient(90deg, #6B48FF, #2B7AE8, #2A9A3A, #E88020); }

  .stats-section { padding: 8px 0; }
  .stat-row { display: flex; border-bottom: 1px solid #F0EDE8; }
  .stat-row:last-child { border-bottom: none; }
  .stat-card { flex: 1; padding: 24px 28px; display: flex; align-items: center; gap: 18px; }
  .stat-card:first-child { border-right: 1px solid #F0EDE8; }

  .stat-illust { width: 90px; height: 90px; border-radius: 14px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; position: relative; overflow: hidden; }
  .big-number { font-size: 40px; font-weight: 900; line-height: 1; }
  .unit { font-size: 14px; font-weight: 700; color: #666; }
  .desc { font-size: 12px; color: #888; margin-top: 6px; line-height: 1.5; }
  .tag { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 10px; font-weight: 700; margin-top: 6px; }

  .card-purple { background: linear-gradient(135deg, #F8F4FF, #F0E8FF); }
  .card-purple .big-number { color: #6B48FF; }
  .card-purple .tag { background: #6B48FF; color: white; }
  .card-blue { background: linear-gradient(135deg, #F0F6FF, #E4EEFF); }
  .card-blue .big-number { color: #2B7AE8; }
  .card-blue .tag { background: #2B7AE8; color: white; }
  .card-orange { background: linear-gradient(135deg, #FFF8F0, #FFF0E0); }
  .card-orange .big-number { color: #E88020; }
  .card-orange .tag { background: #E88020; color: white; }
  .card-green { background: linear-gradient(135deg, #F0FFF4, #E0FFE8); }
  .card-green .big-number { color: #2A9A3A; }
  .card-green .tag { background: #2A9A3A; color: white; }

  .insight { padding: 24px 32px; background: #FAFAFA; border-top: 2px solid #F0EDE8; }
  .insight-item { display: flex; align-items: center; gap: 14px; padding: 14px 18px; background: white; border-radius: 14px; border-left: 4px solid; box-shadow: 0 2px 8px rgba(0,0,0,0.04); margin-bottom: 12px; }
  .insight-illust { width: 64px; height: 64px; border-radius: 12px; flex-shrink: 0; overflow: hidden; display: flex; align-items: center; justify-content: center; position: relative; }

  .footer { padding: 18px 32px; text-align: center; background: linear-gradient(135deg, #1A1A2E, #0F3460); }
  .footer .punch { color: #D0D0FF; font-size: 15px; font-weight: 700; }

  /* 提示词交互样式（所有 E 类型通用） */
  .illust-slot { position: relative; cursor: pointer; }
  .prompt-overlay {
    display: none; position: absolute; bottom: calc(100% + 6px); left: 50%;
    transform: translateX(-50%); background: rgba(26,26,46,0.96); color: white;
    padding: 14px 18px; border-radius: 12px; width: 320px; z-index: 100;
    box-shadow: 0 8px 32px rgba(0,0,0,0.3); font-size: 12px; line-height: 1.6;
  }
  .prompt-overlay::after {
    content: ''; position: absolute; top: 100%; left: 50%; transform: translateX(-50%);
    border: 8px solid transparent; border-top-color: rgba(26,26,46,0.96);
  }
  /* Invisible hover bridge */
  .prompt-overlay::before {
    content: ''; position: absolute; top: 100%; left: 0; width: 100%; height: 24px;
    background: transparent;
  }
  .illust-slot:hover .prompt-overlay { display: block; }
  .prompt-text { color: #E0E0FF; margin-bottom: 8px; word-break: break-word; }
  .copy-btn {
    background: #6B48FF; color: white; border: none; padding: 5px 14px;
    border-radius: 6px; cursor: pointer; font-size: 11px; font-weight: 700;
  }
  .copy-btn:hover { background: #8B68FF; }
  .copy-btn.copied { background: #2A9A3A; }
  .placeholder { font-size: 48px; }
</style>
</head>
<body>
<div class="infographic">
  <div class="header">
    <div class="illust-slot stat-illust" style="width:100px;height:100px;border-radius:16px;" data-prompt="HEADER_PROMPT_HERE">
      <span class="placeholder">emoji</span>
      <div class="prompt-overlay"><p class="prompt-text">HEADER_PROMPT_HERE</p><button class="copy-btn" onclick="copyPrompt(this)">复制提示词</button></div>
    </div>
    <div><h1 style="font-size:30px;font-weight:900;color:white;">标题</h1><p style="color:#A0A0CC;font-size:13px;">副标题</p></div>
  </div>
  <div class="progress-bar"></div>
  <div class="stats-section">
    <div class="stat-row">
      <div class="stat-card card-purple">
        <div class="illust-slot stat-illust" style="background:rgba(107,72,255,0.08);" data-prompt="STAT1_PROMPT">
          <span class="placeholder">emoji</span>
          <div class="prompt-overlay"><p class="prompt-text">STAT1_PROMPT</p><button class="copy-btn" onclick="copyPrompt(this)">复制提示词</button></div>
        </div>
        <div><div class="big-number">73<span class="unit">%</span></div><div class="desc">描述文字</div><span class="tag">标签</span></div>
      </div>
      <!-- 更多 stat-card... -->
    </div>
  </div>
  <div class="insight">
    <h3 style="font-size:15px;color:#6B48FF;font-weight:700;margin-bottom:16px;">洞察标题</h3>
    <div class="insight-item" style="border-color:#E05050;">
      <div class="illust-slot insight-illust" style="background:#FFF0F0;" data-prompt="INSIGHT1_PROMPT">
        <span class="placeholder">emoji</span>
        <div class="prompt-overlay"><p class="prompt-text">INSIGHT1_PROMPT</p><button class="copy-btn" onclick="copyPrompt(this)">复制提示词</button></div>
      </div>
      <div style="font-size:13px;color:#555;line-height:1.6;"><strong>要点标题</strong> - 要点描述</div>
    </div>
    <!-- 更多 insight-item... -->
  </div>
  <div class="footer"><div class="punch">金句</div></div>
</div>
<script>
function copyPrompt(btn) {
  const text = btn.closest('.prompt-overlay').querySelector('.prompt-text').textContent.trim();
  navigator.clipboard.writeText(text).then(() => {
    btn.textContent = '已复制';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = '复制提示词'; btn.classList.remove('copied'); }, 2000);
  });
}
</script>
</body>
</html>
```

### E1 统一风格前缀
所有 E1 的图片提示词建议统一加上此前缀：
```
Flat vector illustration style, soft pastel colors, minimal clean design,
no background (transparent or solid color), suitable for infographic panel,
friendly and professional tone,
```

---

## E2 四格叙事漫画

适用于「讲故事」「起承转合叙事」，4 格网格布局。输出为 HTML 文件。

### 设计要点
- 宽度固定 820px
- 2x2 网格布局，每格不同背景色（暖黄/薰紫/天蓝/粉红）
- 每格含：编号圆、对话气泡、场景插画占位、效果文字
- 第 4 格通常为「冲突+解决方案」结构
- 底部深色金句栏

### E2 HTML 模板骨架

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;700;900&display=swap');
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Noto Sans SC', sans-serif; background: #F5F0E6; display: flex; justify-content: center; padding: 30px; }
  .comic { width: 820px; background: #FDF8F0; border: 3px solid #2D3E56; border-radius: 12px; overflow: hidden; }

  .comic-title { background: linear-gradient(135deg, #2D3E56, #1A2A4A); padding: 18px 28px; display: flex; align-items: center; justify-content: space-between; }
  .comic-title h1 { font-size: 24px; font-weight: 900; color: white; }
  .comic-title .ep { color: #AACCFF; font-size: 12px; }

  .panels { display: grid; grid-template-columns: 1fr 1fr; gap: 0; }
  .panel { border: 2.5px solid #2D3E56; min-height: 340px; position: relative; }
  .panel-1 { background: linear-gradient(160deg, #FFF8E8, #FFF0D0); }
  .panel-2 { background: linear-gradient(160deg, #F0E8FF, #E8D8FF); }
  .panel-3 { background: linear-gradient(160deg, #E8F8FF, #D0F0FF); }
  .panel-4 { background: linear-gradient(160deg, #FFE8E8, #FFD0D0); }

  .panel-num { position: absolute; top: 8px; left: 10px; background: #2D3E56; color: white; width: 26px; height: 26px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700; z-index: 5; }
  .scene { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; padding: 40px 20px 20px; text-align: center; gap: 12px; }

  .illust-box { width: 160px; height: 120px; border-radius: 12px; overflow: hidden; display: flex; align-items: center; justify-content: center; position: relative; border: 2px dashed rgba(0,0,0,0.15); }

  .bubble { background: white; border: 2.5px solid #2D3E56; border-radius: 16px; padding: 12px 16px; position: relative; max-width: 340px; box-shadow: 2px 3px 0 rgba(0,0,0,0.08); }
  .bubble::after { content: ''; position: absolute; bottom: -10px; left: 50%; transform: translateX(-50%); border-left: 8px solid transparent; border-right: 8px solid transparent; border-top: 10px solid white; }
  .bubble::before { content: ''; position: absolute; bottom: -14px; left: 50%; transform: translateX(-50%); border-left: 10px solid transparent; border-right: 10px solid transparent; border-top: 12px solid #2D3E56; }
  .bubble p { font-size: 13px; line-height: 1.6; color: #333; }

  .bottom-bar { background: linear-gradient(135deg, #2D3E56, #1A2A4A); padding: 16px 28px; text-align: center; }
  .bottom-bar .moral { color: white; font-size: 16px; font-weight: 900; }

  /* 提示词交互样式（同 E1） */
  .illust-slot { position: relative; cursor: pointer; }
  .prompt-overlay {
    display: none; position: absolute; bottom: calc(100% + 6px); left: 50%;
    transform: translateX(-50%); background: rgba(26,26,46,0.96); color: white;
    padding: 14px 18px; border-radius: 12px; width: 320px; z-index: 100;
    box-shadow: 0 8px 32px rgba(0,0,0,0.3); font-size: 12px; line-height: 1.6;
  }
  .prompt-overlay::after {
    content: ''; position: absolute; top: 100%; left: 50%; transform: translateX(-50%);
    border: 8px solid transparent; border-top-color: rgba(26,26,46,0.96);
  }
  /* Invisible hover bridge */
  .prompt-overlay::before {
    content: ''; position: absolute; top: 100%; left: 0; width: 100%; height: 24px;
    background: transparent;
  }
  .illust-slot:hover .prompt-overlay { display: block; }
  .prompt-text { color: #E0E0FF; margin-bottom: 8px; word-break: break-word; }
  .copy-btn { background: #6B48FF; color: white; border: none; padding: 5px 14px; border-radius: 6px; cursor: pointer; font-size: 11px; font-weight: 700; }
  .copy-btn:hover { background: #8B68FF; }
  .copy-btn.copied { background: #2A9A3A; }
  .placeholder { font-size: 52px; }
</style>
</head>
<body>
<div class="comic">
  <div class="comic-title">
    <h1>漫画标题</h1>
    <span class="ep">四格漫画 EP.01</span>
  </div>
  <div class="panels">
    <div class="panel panel-1">
      <div class="panel-num">1</div>
      <div class="scene">
        <div class="bubble"><p>对话内容</p></div>
        <div class="illust-slot illust-box" style="background:#FFF8E0;border-color:#E8A020;" data-prompt="PANEL1_PROMPT">
          <span class="placeholder">emoji</span>
          <div class="prompt-overlay"><p class="prompt-text">PANEL1_PROMPT</p><button class="copy-btn" onclick="copyPrompt(this)">复制提示词</button></div>
        </div>
      </div>
    </div>
    <!-- Panel 2-4 同结构 -->
  </div>
  <div class="bottom-bar"><div class="moral">金句</div></div>
</div>
<script>
function copyPrompt(btn) {
  const text = btn.closest('.prompt-overlay').querySelector('.prompt-text').textContent.trim();
  navigator.clipboard.writeText(text).then(() => {
    btn.textContent = '已复制';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = '复制提示词'; btn.classList.remove('copied'); }, 2000);
  });
}
</script>
</body>
</html>
```

### E2 统一风格前缀
```
Flat vector illustration, cute comic style, consistent character design,
expressive cartoon faces, soft pastel colors, comic panel feel,
```


