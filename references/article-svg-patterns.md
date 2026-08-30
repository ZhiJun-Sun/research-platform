# SVG 代码模板（范式 C-G）

技术正式类 T3-T7 的五种完整 SVG 代码骨架。配色/字号规范见 SKILL.md 第六节。

---

## 范式 C：双栏对比图（Before / After）

尺寸：860×420。左栏红色系（BEFORE），右栏绿色系（AFTER），中间 VS 圆徽章。

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 860 420"
     font-family="Microsoft YaHei, PingFang SC, sans-serif">
  <defs>
    <filter id="s"><feDropShadow dx="1" dy="2" stdDeviation="3" flood-opacity="0.12"/></filter>
    <filter id="s2"><feDropShadow dx="0" dy="1" stdDeviation="2" flood-opacity="0.08"/></filter>
    <marker id="arrow-red" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
      <polygon points="0 0, 10 3.5, 0 7" fill="#E05050"/>
    </marker>
    <marker id="arrow-green" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
      <polygon points="0 0, 10 3.5, 0 7" fill="#3A9A3A"/>
    </marker>
  </defs>

  <rect width="860" height="420" fill="#F4F6F8"/>

  <!-- 标题栏 -->
  <rect x="0" y="0" width="860" height="48" fill="#2D3E56"/>
  <text x="430" y="30" text-anchor="middle" fill="white" font-size="18" font-weight="bold">标题：手工 vs 自动化</text>
  <text x="430" y="43" text-anchor="middle" fill="#9BB0CC" font-size="11">副标题描述</text>

  <!-- BEFORE 左栏 -->
  <rect x="20" y="62" width="390" height="346" rx="10" fill="white" filter="url(#s)"/>
  <rect x="20" y="62" width="390" height="40" rx="10" fill="#E05050"/>
  <rect x="20" y="88" width="390" height="14" fill="#E05050"/>
  <text x="215" y="87" text-anchor="middle" fill="white" font-size="14" font-weight="bold">😩  手工方式（BEFORE）</text>

  <!-- 步骤1（y=116，高38，间距48；5步时最后一步y=308） -->
  <rect x="42" y="116" width="346" height="38" rx="6" fill="#FFF0F0" stroke="#F0A0A0" stroke-width="1.2" filter="url(#s2)"/>
  <text x="66" y="132" fill="#B03030" font-size="12" font-weight="bold">① 步骤标题</text>
  <text x="66" y="148" fill="#C06060" font-size="11">具体操作描述</text>
  <line x1="215" y1="154" x2="215" y2="164" stroke="#E05050" stroke-width="1.5" marker-end="url(#arrow-red)"/>

  <!-- 步骤2-5（y 依次 +48）...省略，按需复制 -->

  <!-- 时间徽章 -->
  <rect x="60" y="356" width="296" height="40" rx="8" fill="#FFE0E0" stroke="#F0A0A0" stroke-width="1.5"/>
  <text x="208" y="371" text-anchor="middle" fill="#B03030" font-size="13" font-weight="bold">⏰ 总耗时：3～4 小时</text>
  <text x="208" y="387" text-anchor="middle" fill="#C06060" font-size="11">高度消耗脑力，每版本都来一遍</text>

  <!-- AFTER 右栏 -->
  <rect x="450" y="62" width="390" height="346" rx="10" fill="white" filter="url(#s)"/>
  <rect x="450" y="62" width="390" height="40" rx="10" fill="#2A7A2A"/>
  <rect x="450" y="88" width="390" height="14" fill="#2A7A2A"/>
  <text x="645" y="87" text-anchor="middle" fill="white" font-size="14" font-weight="bold">🚀  自动化方式（AFTER）</text>

  <rect x="472" y="116" width="346" height="38" rx="6" fill="#E8F8E8" stroke="#80C880" stroke-width="1.2" filter="url(#s2)"/>
  <text x="496" y="132" fill="#1A6A1A" font-size="12" font-weight="bold">① 步骤标题</text>
  <text x="496" y="148" fill="#3A8A3A" font-size="11">改进后描述</text>
  <line x1="645" y1="154" x2="645" y2="164" stroke="#3A9A3A" stroke-width="1.5" marker-end="url(#arrow-green)"/>

  <!-- 步骤2-5（y 依次 +48）...省略，按需复制 -->

  <!-- 效果徽章 -->
  <rect x="490" y="356" width="296" height="40" rx="8" fill="#D8F8D8" stroke="#80C880" stroke-width="1.5"/>
  <text x="638" y="371" text-anchor="middle" fill="#1A6A1A" font-size="13" font-weight="bold">⚡ 总耗时：约 2 分钟</text>
  <text x="638" y="387" text-anchor="middle" fill="#3A8A3A" font-size="11">只需一条指令，其余全自动</text>

  <!-- VS 圆 -->
  <circle cx="430" cy="234" r="24" fill="#2D3E56" filter="url(#s)"/>
  <text x="430" y="240" text-anchor="middle" fill="white" font-size="14" font-weight="bold">VS</text>
</svg>
```

**坐标规律（5步版本）**：
| 步骤 | y起点 | 箭头 y1→y2 |
|------|-------|-----------|
| ① | 116 | 154→164 |
| ② | 164 | 202→212 |
| ③ | 212 | 250→260 |
| ④ | 260 | 298→308 |
| ⑤ | 308 | —（最后一步无箭头） |

---

## 范式 D：多层分区架构图

尺寸：900×500。左侧竖线+层级标签，右侧4层色块，层间带箭头连接。

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 500"
     font-family="Microsoft YaHei, PingFang SC, sans-serif">
  <defs>
    <filter id="s"><feDropShadow dx="1" dy="2" stdDeviation="3" flood-opacity="0.13"/></filter>
    <filter id="s2"><feDropShadow dx="0" dy="1" stdDeviation="2" flood-opacity="0.09"/></filter>
    <marker id="arrow" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
      <polygon points="0 0, 10 3.5, 0 7" fill="#666"/>
    </marker>
    <linearGradient id="gTitle" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" style="stop-color:#1A3060"/>
      <stop offset="100%" style="stop-color:#3A60A0"/>
    </linearGradient>
  </defs>

  <rect width="900" height="500" fill="#F0F3F8"/>

  <!-- 标题栏 -->
  <rect x="0" y="0" width="900" height="52" fill="url(#gTitle)"/>
  <text x="450" y="31" text-anchor="middle" fill="white" font-size="19" font-weight="bold">系统架构标题</text>
  <text x="450" y="46" text-anchor="middle" fill="#AACCFF" font-size="11">数据层 · 规则层 · 执行层 · 输出层</text>

  <!-- 左侧层级标签 -->
  <text x="28" y="110" fill="#555" font-size="11" font-weight="bold">数据层</text>
  <text x="28" y="210" fill="#555" font-size="11" font-weight="bold">规则层</text>
  <text x="28" y="318" fill="#555" font-size="11" font-weight="bold">执行层</text>
  <text x="28" y="430" fill="#555" font-size="11" font-weight="bold">输出层</text>
  <line x1="70" y1="70" x2="70" y2="490" stroke="#CCCCCC" stroke-width="1" stroke-dasharray="4,3"/>

  <!-- 数据层（蓝色系，y=68 高90） -->
  <rect x="80" y="68" width="770" height="90" rx="10" fill="white" stroke="#5B8DD9" stroke-width="1.5" filter="url(#s)"/>
  <text x="465" y="84" text-anchor="middle" fill="#2B5090" font-size="12" font-weight="bold">📡  数据来源</text>
  <!-- 3 个子卡片，宽230，x=98/348/598 -->
  <rect x="98" y="92" width="230" height="54" rx="6" fill="#E8F2FF" stroke="#84B0DC" stroke-width="1.2"/>
  <text x="213" y="112" text-anchor="middle" fill="#2B5090" font-size="11" font-weight="bold">数据源1</text>
  <text x="213" y="127" text-anchor="middle" fill="#5A7AAA" font-size="10">说明行1</text>
  <text x="213" y="140" text-anchor="middle" fill="#5A7AAA" font-size="10">说明行2</text>
  <!-- 重复 x=348, x=598 ... -->
  <line x1="465" y1="158" x2="465" y2="175" stroke="#666" stroke-width="2" marker-end="url(#arrow)"/>

  <!-- 规则层（紫色系，y=175 高100） -->
  <rect x="80" y="175" width="770" height="100" rx="10" fill="white" stroke="#9B6DC8" stroke-width="1.5" filter="url(#s)"/>
  <text x="465" y="191" text-anchor="middle" fill="#5A3A8A" font-size="12" font-weight="bold">📚  知识库/规则层</text>
  <!-- 4 个子卡片，宽170/170/170/175，x=98/283/468/653 -->
  <rect x="98" y="200" width="170" height="62" rx="6" fill="#F0E8FC" stroke="#C090D8" stroke-width="1.2"/>
  <text x="183" y="218" text-anchor="middle" fill="#4A2070" font-size="11" font-weight="bold">规则文件1</text>
  <!-- 重复 x=283/468/653 ... -->
  <line x1="465" y1="275" x2="465" y2="292" stroke="#666" stroke-width="2" marker-end="url(#arrow)"/>

  <!-- 执行层（深色背景，y=292 高100） -->
  <rect x="80" y="292" width="770" height="100" rx="10" fill="#2D3E56" filter="url(#s)"/>
  <text x="465" y="309" text-anchor="middle" fill="white" font-size="13" font-weight="bold">🤖  AI 执行层</text>
  <text x="465" y="323" text-anchor="middle" fill="#AACCFF" font-size="10">加载 Skill → 推理 → 生成方案</text>
  <!-- 3 个半透明子框，宽180/180/218，x=100/355/610 -->
  <rect x="100" y="330" width="180" height="50" rx="6" fill="rgba(255,255,255,0.12)"/>
  <text x="190" y="351" text-anchor="middle" fill="white" font-size="11" font-weight="bold">执行模块1</text>
  <!-- 重复 x=355, x=610 ... -->
  <line x1="465" y1="392" x2="465" y2="412" stroke="#666" stroke-width="2" marker-end="url(#arrow)"/>

  <!-- 输出层（绿色系，y=412 高72） -->
  <rect x="80" y="412" width="770" height="72" rx="10" fill="white" stroke="#3A9A3A" stroke-width="1.5" filter="url(#s)"/>
  <text x="465" y="428" text-anchor="middle" fill="#1A5A1A" font-size="12" font-weight="bold">📤  输出层</text>
  <!-- 3 个输出卡片，宽200/200/296，x=100/318/536 -->
  <rect x="100" y="436" width="200" height="36" rx="5" fill="#E8F8E8" stroke="#80C880" stroke-width="1"/>
  <text x="200" y="450" text-anchor="middle" fill="#1A5A1A" font-size="11" font-weight="bold">输出项1</text>
  <text x="200" y="464" text-anchor="middle" fill="#5A9A5A" font-size="10">描述</text>
</svg>
```

---

## 范式 E：多列卡片图（3 列平行概念）

尺寸：860×500。3 列卡片 + 底部汇聚输出栏，适合展示三层上下文、三个维度等。

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 860 500"
     font-family="Microsoft YaHei, PingFang SC, sans-serif">
  <defs>
    <filter id="s"><feDropShadow dx="1" dy="2" stdDeviation="3" flood-opacity="0.12"/></filter>
    <filter id="s2"><feDropShadow dx="0" dy="1" stdDeviation="2" flood-opacity="0.08"/></filter>
    <marker id="arrow" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
      <polygon points="0 0, 10 3.5, 0 7" fill="#888"/>
    </marker>
    <linearGradient id="gTitle" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" style="stop-color:#1A3060"/>
      <stop offset="100%" style="stop-color:#3A60A0"/>
    </linearGradient>
    <linearGradient id="gOut" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" style="stop-color:#1E4A1E"/>
      <stop offset="100%" style="stop-color:#2E6A2E"/>
    </linearGradient>
  </defs>

  <rect width="860" height="500" fill="#F2F5FA"/>
  <rect x="0" y="0" width="860" height="50" fill="url(#gTitle)"/>
  <text x="430" y="27" text-anchor="middle" fill="white" font-size="17" font-weight="bold">三层概念标题</text>
  <text x="430" y="43" text-anchor="middle" fill="#AACCFF" font-size="11">副标题说明</text>

  <!-- 列1（蓝色系，x=30 宽248） -->
  <rect x="30" y="68" width="248" height="320" rx="12" fill="white" stroke="#5B8DD9" stroke-width="1.8" filter="url(#s)"/>
  <rect x="30" y="68" width="248" height="38" rx="12" fill="#5B8DD9"/>
  <rect x="30" y="92" width="248" height="14" fill="#5B8DD9"/>
  <text x="154" y="91" text-anchor="middle" fill="white" font-size="13" font-weight="bold">第一层 · 层名称</text>
  <text x="154" y="124" text-anchor="middle" fill="#2B5090" font-size="11" font-weight="bold">解决什么问题</text>
  <!-- 内容区 -->
  <rect x="46" y="135" width="216" height="238" rx="7" fill="#F0F8FF" stroke="#84B0DC" stroke-width="1"/>
  <!-- 条目：文字 y=156/170，分隔线 y=177，依次 +37 ... -->
  <text x="58" y="156" fill="#1A4080" font-size="11" font-weight="bold">条目标题</text>
  <text x="58" y="170" fill="#4A6090" font-size="10">条目描述</text>
  <line x1="58" y1="177" x2="246" y2="177" stroke="#D0E0F0" stroke-width="1"/>
  <text x="154" y="375" text-anchor="middle" fill="#7A5AAA" font-size="10">→ 这层的核心价值</text>
  <!-- 向下箭头 -->
  <line x1="154" y1="388" x2="154" y2="418" stroke="#5B8DD9" stroke-width="2" marker-end="url(#arrow)"/>

  <!-- 列2（紫色系，x=306 宽248）- 同结构，改配色 -->
  <!-- <rect x="306" ... stroke="#9B6DC8" ... -->

  <!-- 列3（绿色系，x=582 宽248）- 同结构，改配色 -->
  <!-- <rect x="582" ... stroke="#2E8A50" ... -->

  <!-- 汇聚输出栏（y=418 高62） -->
  <rect x="30" y="418" width="800" height="62" rx="10" fill="url(#gOut)" filter="url(#s)"/>
  <text x="430" y="440" text-anchor="middle" fill="white" font-size="14" font-weight="bold">🤖  三层汇总 → AI 综合推理 → 最终输出</text>
  <text x="200" y="462" text-anchor="middle" fill="#90D890" font-size="11">要点1</text>
  <text x="430" y="462" text-anchor="middle" fill="#90D890" font-size="11">要点2</text>
  <text x="665" y="462" text-anchor="middle" fill="#90D890" font-size="11">要点3</text>
</svg>
```

---

## 范式 F：Step-by-Step 流程图（分叉汇聚型）

尺寸：900×560。顶部触发→单列 Step→分叉 3 列→汇聚→输出→完成徽章。

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 560"
     font-family="Microsoft YaHei, PingFang SC, sans-serif">
  <defs>
    <filter id="s"><feDropShadow dx="1" dy="2" stdDeviation="3" flood-opacity="0.12"/></filter>
    <filter id="s2"><feDropShadow dx="0" dy="1" stdDeviation="2" flood-opacity="0.09"/></filter>
    <marker id="arrow" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
      <polygon points="0 0, 10 3.5, 0 7" fill="#555"/>
    </marker>
    <linearGradient id="gTitle" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" style="stop-color:#2B5090"/>
      <stop offset="100%" style="stop-color:#4472C4"/>
    </linearGradient>
    <linearGradient id="gGreen" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" style="stop-color:#2A7A2A"/>
      <stop offset="100%" style="stop-color:#4AAA4A"/>
    </linearGradient>
  </defs>

  <rect width="900" height="560" fill="#F0F3F8"/>
  <rect x="0" y="0" width="900" height="52" fill="url(#gTitle)"/>
  <text x="450" y="31" text-anchor="middle" fill="white" font-size="19" font-weight="bold">执行流程标题</text>
  <text x="450" y="46" text-anchor="middle" fill="#AACCFF" font-size="11">从输入到输出的全自动化过程</text>

  <!-- 触发框（深色胶囊，y=70 高44） -->
  <rect x="290" y="70" width="320" height="44" rx="22" fill="#2D3E56" filter="url(#s)"/>
  <text x="450" y="88" text-anchor="middle" fill="white" font-size="13" font-weight="bold">💬  用户输入</text>
  <text x="450" y="106" text-anchor="middle" fill="#AACCFF" font-size="11">「触发语句」</text>
  <line x1="450" y1="114" x2="450" y2="134" stroke="#555" stroke-width="2" marker-end="url(#arrow)"/>

  <!-- Step 蓝色框（y=134 高44） -->
  <rect x="290" y="134" width="320" height="44" rx="8" fill="#5B8DD9" filter="url(#s2)"/>
  <text x="450" y="152" text-anchor="middle" fill="white" font-size="12" font-weight="bold">Step 0  步骤名称</text>
  <text x="450" y="168" text-anchor="middle" fill="#D0E8FF" font-size="10">步骤描述</text>
  <line x1="450" y1="178" x2="450" y2="198" stroke="#555" stroke-width="2" marker-end="url(#arrow)"/>

  <!-- 宽步骤框（白色边框，y=198 高56，x=200 宽500） -->
  <rect x="200" y="198" width="500" height="56" rx="8" fill="white" stroke="#4472C4" stroke-width="1.5" filter="url(#s2)"/>
  <text x="450" y="218" text-anchor="middle" fill="#2B5090" font-size="12" font-weight="bold">Step 0A  数据处理</text>
  <text x="450" y="234" text-anchor="middle" fill="#555" font-size="10">命令行/脚本说明</text>
  <text x="450" y="248" text-anchor="middle" fill="#888" font-size="10">数据量/耗时说明</text>

  <!-- 分叉横线 + 3 列 -->
  <line x1="170" y1="254" x2="730" y2="254" stroke="#AAA" stroke-width="1.5"/>
  <line x1="170" y1="254" x2="170" y2="274" stroke="#AAA" stroke-width="1.5"/>
  <line x1="730" y1="254" x2="730" y2="274" stroke="#AAA" stroke-width="1.5"/>

  <!-- 列1（紫色边框，x=60 宽220） -->
  <rect x="60" y="274" width="220" height="72" rx="8" fill="white" stroke="#9B6DC8" stroke-width="1.5" filter="url(#s2)"/>
  <text x="170" y="294" text-anchor="middle" fill="#5A3A8A" font-size="12" font-weight="bold">Step 1-2</text>
  <text x="170" y="310" text-anchor="middle" fill="#5A3A8A" font-size="11">步骤描述</text>
  <text x="170" y="325" text-anchor="middle" fill="#888" font-size="10">细节说明1</text>
  <text x="170" y="338" text-anchor="middle" fill="#888" font-size="10">细节说明2</text>

  <!-- 列2（橙色边框，x=340 宽220） -->
  <rect x="340" y="274" width="220" height="72" rx="8" fill="white" stroke="#E88020" stroke-width="1.5" filter="url(#s2)"/>
  <text x="450" y="294" text-anchor="middle" fill="#7A4010" font-size="12" font-weight="bold">Step 3-4</text>

  <!-- 列3（绿色边框，x=620 宽220） -->
  <rect x="620" y="274" width="220" height="72" rx="8" fill="white" stroke="#3A9A3A" stroke-width="1.5" filter="url(#s2)"/>
  <text x="730" y="294" text-anchor="middle" fill="#1A5A1A" font-size="12" font-weight="bold">Step 5-6</text>

  <!-- 汇聚线 -->
  <line x1="170" y1="346" x2="170" y2="378" stroke="#AAA" stroke-width="1.5"/>
  <line x1="450" y1="346" x2="450" y2="378" stroke="#AAA" stroke-width="1.5"/>
  <line x1="730" y1="346" x2="730" y2="378" stroke="#AAA" stroke-width="1.5"/>
  <line x1="170" y1="378" x2="730" y2="378" stroke="#AAA" stroke-width="1.5"/>
  <line x1="450" y1="378" x2="450" y2="390" stroke="#555" stroke-width="2" marker-end="url(#arrow)"/>

  <!-- 生成结果框（绿色渐变，y=390 高56） -->
  <rect x="200" y="390" width="500" height="56" rx="8" fill="url(#gGreen)" filter="url(#s2)"/>
  <text x="450" y="410" text-anchor="middle" fill="white" font-size="12" font-weight="bold">Step 7  生成完整方案</text>
  <text x="450" y="426" text-anchor="middle" fill="#D0FFD0" font-size="10">方案说明1 · 说明2 · 说明3</text>
  <text x="450" y="440" text-anchor="middle" fill="#AAFFAA" font-size="10">输出描述</text>
  <line x1="450" y1="446" x2="450" y2="466" stroke="#555" stroke-width="2" marker-end="url(#arrow)"/>

  <!-- 发送框（深色，y=466 高50） -->
  <rect x="270" y="466" width="360" height="50" rx="8" fill="#2D3E56" filter="url(#s)"/>
  <text x="450" y="486" text-anchor="middle" fill="white" font-size="12" font-weight="bold">Step 8  推送 / 同步</text>
  <text x="450" y="502" text-anchor="middle" fill="#AACCFF" font-size="10">说明</text>
  <line x1="450" y1="516" x2="450" y2="532" stroke="#3A9A3A" stroke-width="2" marker-end="url(#arrow)"/>

  <!-- 完成徽章 -->
  <rect x="320" y="532" width="260" height="22" rx="11" fill="#D8F8D8" stroke="#80C880" stroke-width="1.2"/>
  <text x="450" y="547" text-anchor="middle" fill="#1A6A1A" font-size="11" font-weight="bold">✅ 完成！全程约 X 分钟</text>
</svg>
```

---

## 配色速查

| 颜色系 | 边框 | 卡片填充 | 标题文字 | 次级文字 |
|--------|------|---------|---------|---------|
| 蓝（数据/信息层） | `#5B8DD9` | `#E8F2FF` | `#2B5090` | `#5A7AAA` |
| 紫（规则/知识层） | `#9B6DC8` | `#F0E8FC` | `#4A2070` | `#7A4AAA` |
| 深色（执行层） | — | `#2D3E56` | `white` | `#AACCFF` |
| 绿（输出/AFTER） | `#3A9A3A` | `#E8F8E8` | `#1A5A1A` | `#5A9A5A` |
| 红（问题/BEFORE） | `#E05050` | `#FFF0F0` | `#B03030` | `#C06060` |
| 标题渐变 | — | `#1A3060→#3A60A0` | `white` | `#AACCFF` |

## 字号速查

| 场景 | font-size |
|------|-----------|
| 图表大标题 | 17–19 |
| 图表副标题 | 11 |
| 层/卡片大标题 | 12–13 bold |
| 卡片内小标题 | 11 bold |
| 卡片内描述 | 10 |
| 小标注 | 9–10 |

---

## 范式 G：同心嵌套图（概念层次关系）

尺寸：900×480。展示「核心 → 中间层 → 外围层」的层次概念（意图三层、记忆层次等）。

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 480"
     font-family="Microsoft YaHei, PingFang SC, sans-serif">
  <defs>
    <filter id="s"><feDropShadow dx="1" dy="2" stdDeviation="3" flood-opacity="0.13"/></filter>
    <linearGradient id="gTitle" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" style="stop-color:#1A3060"/>
      <stop offset="100%" style="stop-color:#3A60A0"/>
    </linearGradient>
  </defs>

  <rect width="900" height="480" fill="#F0F3F8"/>
  <rect x="0" y="0" width="900" height="52" fill="url(#gTitle)"/>
  <text x="450" y="31" text-anchor="middle" fill="white" font-size="17" font-weight="bold">图表标题</text>
  <text x="450" y="46" text-anchor="middle" fill="#AACCFF" font-size="11">副标题说明</text>

  <!-- 外层椭圆（最外圈，暖色系） -->
  <ellipse cx="450" cy="280" rx="400" ry="176" fill="#FFF4E8" stroke="#E8A050" stroke-width="1.5"/>
  <!-- 外层标签 -->
  <text x="68" y="204" fill="#804A10" font-size="12" font-weight="bold">外层名称</text>
  <text x="68" y="220" fill="#AA6A30" font-size="10">外层说明文字</text>

  <!-- 中层椭圆 -->
  <ellipse cx="450" cy="280" rx="290" ry="126" fill="#E8F2FF" stroke="#5B8DD9" stroke-width="1.5"/>
  <!-- 中层标签 -->
  <text x="172" y="224" fill="#2B5090" font-size="12" font-weight="bold">中层名称</text>
  <text x="172" y="240" fill="#5A7AAA" font-size="10">中层说明文字</text>

  <!-- 内层椭圆（深色背景，强调核心） -->
  <ellipse cx="450" cy="280" rx="160" ry="76" fill="#2D3E56"/>
  <text x="450" y="272" text-anchor="middle" fill="white" font-size="14" font-weight="bold">内层名称</text>
  <text x="450" y="290" text-anchor="middle" fill="#AACCFF" font-size="11">内层核心说明</text>
  <text x="450" y="310" text-anchor="middle" fill="#7090B0" font-size="10">注释（如：大多数 Skill 止步于此）</text>

  <!-- 底部三列注释块 -->
  <rect x="20" y="380" width="270" height="82" rx="8" fill="#2D3E56" filter="url(#s)"/>
  <text x="155" y="400" text-anchor="middle" fill="white" font-size="11" font-weight="bold">内层核心</text>
  <text x="155" y="418" text-anchor="middle" fill="#AACCFF" font-size="10">说明行1</text>
  <text x="155" y="433" text-anchor="middle" fill="#AACCFF" font-size="10">说明行2</text>
  <text x="155" y="452" text-anchor="middle" fill="#AACCFF" font-size="10">说明行3</text>

  <rect x="310" y="380" width="270" height="82" rx="8" fill="#1A5A9A" filter="url(#s)"/>
  <text x="445" y="400" text-anchor="middle" fill="white" font-size="11" font-weight="bold">中层名称</text>
  <text x="445" y="418" text-anchor="middle" fill="#AAC8FF" font-size="10">说明行1</text>
  <text x="445" y="433" text-anchor="middle" fill="#AAC8FF" font-size="10">说明行2</text>
  <text x="445" y="452" text-anchor="middle" fill="#AAC8FF" font-size="10">说明行3</text>

  <rect x="600" y="380" width="280" height="82" rx="8" fill="#804A10" filter="url(#s)"/>
  <text x="740" y="400" text-anchor="middle" fill="white" font-size="11" font-weight="bold">外层名称</text>
  <text x="740" y="418" text-anchor="middle" fill="#FFCC99" font-size="10">说明行1</text>
  <text x="740" y="433" text-anchor="middle" fill="#FFCC99" font-size="10">说明行2</text>
  <text x="740" y="452" text-anchor="middle" fill="#FFCC99" font-size="10">说明行3</text>
</svg>
```

**已验证椭圆坐标（cx=450, cy=280）：**

| 层 | rx | ry | 填充 | 边框 |
|----|----|----|------|------|
| 外层（隐含意图）| 400 | 176 | `#FFF4E8` | `#E8A050` |
| 中层（实际意图）| 290 | 126 | `#E8F2FF` | `#5B8DD9` |
| 内层（表面意图）| 160 | 76 | `#2D3E56` | — |

底部三列注释块：宽270/270/280，y=380，高82，x=20/310/600

---

## 常见坑

| 坑 | 症状 | 解决方法 |
|----|------|---------|
| `writing-mode="tb"` | 竖排文字渲染错乱或不显示 | 改为横排放左侧，或用 `transform="rotate(-90)"` |
| 圆角标题头有缝隙 | 彩色 header 底部露出背景色 | 加同色无圆角补丁 rect 覆盖 |
| 中文乱码/不显示 | 字体回退到非中文字体 | `font-family` 必须设在 `<svg>` 标签，优先 `Microsoft YaHei` |
| 箭头不显示 | marker 没生效 | 确认 `refX="9"`（不是 10），且 id 引用正确 |
| 执行层无深色背景 | 各层视觉差异弱，范式 D 失效 | 执行层必须用 `fill="#2D3E56"` 整层深色背景 |
| 4 列/多列宽度不等 | 视觉失衡 | 统一列宽，如有需要最后一列可宽 10–15px |
| 层间箭头悬空 | 箭头终点离下层顶部有空隙 | `y2 = 下层 y + 17`（留 17px 空隙） |
| XML 注释里有 `--` | SVG 解析报错 | 用 `====` 替代分隔符 |


