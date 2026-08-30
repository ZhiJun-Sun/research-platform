// skills: canvas
import { useState } from "react";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  Divider,
  H1,
  H3,
  Row,
  setCustomTheme,
  Stack,
  Text,
  TextInput,
  useCanvasAction,
  useCanvasState,
  useHostTheme,
} from "codeflicker/canvas";

// ─────────────────────────────────────────────────────────────
// 固定模板：禁止修改本文件内容。
// 使用方式：原样 cp 到画布目录，只创建/更新同名的
// `<name>.canvas.data.json`，把 briefData 填成本次项目的内容。
// data.json 只存配置数据（标题、问题、选项、主题候选、默认假设），
// 不存用户交互状态（选择结果由组件内 useState 管理，不落盘）。
// ─────────────────────────────────────────────────────────────

type BriefOption = { label: string; value: string };

type BriefQuestion = {
  id: string;
  question: string;
  hint?: string;
  multi?: boolean;
  options: BriefOption[];
};

type ThemeSection = {
  question?: string;
  hint?: string;
  presets?: BriefOption[];
};

type BriefData = {
  badge?: string;
  title?: string;
  subtitle?: string;
  questions?: BriefQuestion[];
  theme?: ThemeSection;
  assumptions?: string[];
  submitLabel?: string;
  defaultLabel?: string;
  summaryTitle?: string;
};

type SelectionMap = Record<string, string[]>;
type CustomAnswerMap = Record<string, string>;

const DEFAULT_DATA: Required<
  Pick<
    BriefData,
    | "badge"
    | "title"
    | "subtitle"
    | "questions"
    | "theme"
    | "assumptions"
    | "submitLabel"
    | "defaultLabel"
    | "summaryTitle"
  >
> = {
  badge: "Website Brief",
  title: "网站需求确认",
  subtitle: "点击选项选择，也可在输入框里自定义补充。底部操作条会一直跟随滚动。",
  questions: [],
  theme: {
    question: "视觉主题想用哪个？",
    hint: "色块只是主题代表色，也可取色或直接输入 #3B6CF4 / 25, 25, 25 / rgb(25,25,25)",
    presets: [],
  },
  assumptions: [
    "优先保证首屏目标清楚，并让主要行动入口在首屏可见",
    "使用符合场景的视觉系统，避免通用 AI 模板感",
    "先做完整可运行体验，真实内容不足时使用可替换占位内容",
    "需要交互时先完成关键路径，再补充次要状态",
  ],
  submitLabel: "提交我的选择",
  defaultLabel: "按默认假设直接开始",
  summaryTitle: "网站需求确认",
};

// ────── 画布自身的视觉风格（与 data.json 里的主题候选无关，固定不改）──────
// Canvas style source: references/website-design/themes/A-enterprise-light.md
// 企业亮色风：极浅灰页底 + 白卡 + 中性产品蓝强调，干净克制的「大厂风」。
// 注意：setCustomTheme 会让画布配色固定，不再跟随 IDE 的 dark/light 切换。
setCustomTheme({
  kind: "light",
  palette: {
    foreground: "#1A1A2E",
    foregroundSecondary: "#4B4D63",
    foregroundTertiary: "#9395A8",
    foregroundQuaternary: "#C0C2CF",
    editor: "#F7F8FA",
    chrome: "#FFFFFF",
    sidebar: "#F0F1F5",
    elevated: "#FFFFFF",
    fillPrimary: "#DFE0E8",
    fillSecondary: "#EBF1FE",
    fillTertiary: "#FFFFFF",
    fillQuaternary: "#F0F1F5",
    strokePrimary: "#C0C2CF",
    strokeSecondary: "#DFE0E8",
    strokeTertiary: "#F0F1F5",
    accent: "#3B6CF4",
    buttonBackground: "#3B6CF4",
    buttonForeground: "#FFFFFF",
    buttonHoverBackground: "#1E54D4",
    link: "#1E54D4",
  },
});

const ENTERPRISE = {
  radiusSm: 6,
  radiusMd: 8,
  labelFont: '"Inter", -apple-system, "PingFang SC", "Helvetica Neue", sans-serif',
  labelTracking: "0.06em",
  accentSoft: "#EBF1FE",
  borderStrong: "#3B6CF4",
} as const;

/**
 * 把用户输入的颜色统一解析成 #RRGGBB。
 * 支持：#RGB、#RRGGBB（可省略 #）、"25, 25, 25"、"rgb(25 25 25)"。
 * 无法识别或数值越界时返回空字符串。
 */
function parseColorInput(raw: string): string {
  const input = raw.trim();
  if (!input) return "";

  const toHex = (r: number, g: number, b: number) =>
    "#" +
    [r, g, b]
      .map((channel) => channel.toString(16).padStart(2, "0"))
      .join("")
      .toUpperCase();

  const hex = input.replace(/^#/, "");
  if (/^[0-9a-fA-F]{6}$/.test(hex)) {
    return `#${hex.toUpperCase()}`;
  }
  if (/^[0-9a-fA-F]{3}$/.test(hex)) {
    return `#${hex
      .split("")
      .map((char) => char + char)
      .join("")
      .toUpperCase()}`;
  }

  const rgbBody = input.replace(/^rgba?\s*\(/i, "").replace(/\)\s*$/, "");
  const channels = rgbBody
    .split(/[\s,]+/)
    .filter(Boolean)
    .slice(0, 3);

  if (channels.length === 3 && channels.every((part) => /^\d{1,3}$/.test(part))) {
    const values = channels.map(Number);
    if (values.every((value) => value <= 255)) {
      return toHex(values[0], values[1], values[2]);
    }
  }

  return "";
}

function OptionChip({
  label,
  selected,
  onClick,
}: {
  label: string;
  selected: boolean;
  onClick: () => void;
}) {
  const { tokens } = useHostTheme();

  return (
    <div
      onClick={onClick}
      style={{
        padding: "7px 14px",
        borderRadius: ENTERPRISE.radiusMd,
        border: `1px solid ${selected ? ENTERPRISE.borderStrong : tokens.stroke.secondary}`,
        background: selected ? ENTERPRISE.accentSoft : tokens.fill.tertiary,
        fontSize: 13,
        color: selected ? tokens.text.primary : tokens.text.secondary,
        cursor: "pointer",
        userSelect: "none",
        transition: "border-color 0.12s ease, background 0.12s ease",
        fontWeight: selected ? 500 : 400,
        display: "flex",
        alignItems: "center",
        gap: 6,
      }}
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          flexShrink: 0,
          background: selected ? tokens.accent.primary : tokens.stroke.primary,
        }}
      />
      {label}
    </div>
  );
}

function SectionLabel({ text }: { text: string }) {
  const { tokens } = useHostTheme();

  return (
    <Text
      style={{
        fontFamily: ENTERPRISE.labelFont,
        fontSize: 11,
        fontWeight: 700,
        color: tokens.accent.primary,
        letterSpacing: ENTERPRISE.labelTracking,
      }}
    >
      {text}
    </Text>
  );
}

export default function InteractiveBriefTemplate() {
  const { tokens } = useHostTheme();
  const dispatch = useCanvasAction();

  // ✅ 只有 briefData 从 data.json 读取（AI 注入的配置数据）
  const [data] = useCanvasState<BriefData>("briefData", DEFAULT_DATA);

  // ✅ 用户交互状态用普通 useState，不写回 data.json
  const [selections, setSelections] = useState<SelectionMap>({});
  const [customAnswers, setCustomAnswers] = useState<CustomAnswerMap>({});
  const [themeColor, setThemeColor] = useState<string>("");

  const badge = data.badge ?? DEFAULT_DATA.badge;
  const title = data.title ?? DEFAULT_DATA.title;
  const subtitle = data.subtitle ?? DEFAULT_DATA.subtitle;
  const questions = data.questions ?? DEFAULT_DATA.questions;
  const assumptions = data.assumptions ?? DEFAULT_DATA.assumptions;
  const submitLabel = data.submitLabel ?? DEFAULT_DATA.submitLabel;
  const defaultLabel = data.defaultLabel ?? DEFAULT_DATA.defaultLabel;
  const summaryTitle = data.summaryTitle ?? DEFAULT_DATA.summaryTitle;

  const themeQuestion = data.theme?.question ?? DEFAULT_DATA.theme.question!;
  const themeHint = data.theme?.hint ?? DEFAULT_DATA.theme.hint!;
  const themePresets = (data.theme?.presets ?? []).slice(0, 6);

  const normalizedColor = parseColorInput(themeColor);

  function toggle(questionId: string, value: string, multi?: boolean) {
    setSelections((prev) => {
      const current = prev[questionId] ?? [];
      if (multi) {
        return {
          ...prev,
          [questionId]: current.includes(value)
            ? current.filter((item) => item !== value)
            : [...current, value],
        };
      }
      return { ...prev, [questionId]: [value] };
    });
  }

  function setCustom(questionId: string, value: string) {
    setCustomAnswers((prev) => ({ ...prev, [questionId]: value }));
  }

  const answeredCount = questions.filter(
    (question) =>
      (selections[question.id] ?? []).length > 0 ||
      (customAnswers[question.id] ?? "").trim().length > 0
  ).length;
  const totalCount = questions.length + 1;
  const completedCount = answeredCount + (normalizedColor ? 1 : 0);

  function buildSummary() {
    const lines = questions
      .map((question) => {
        const selectedValues = selections[question.id] ?? [];
        const custom = (customAnswers[question.id] ?? "").trim();
        if (selectedValues.length === 0 && custom.length === 0) return null;

        const selectedLabels = question.options
          .filter((option) => selectedValues.includes(option.value))
          .map((option) => option.label)
          .join("、");

        const parts = [selectedLabels, custom ? `补充：${custom}` : ""].filter(
          Boolean
        );

        return `${question.question} → ${parts.join("；")}`;
      })
      .filter(Boolean);

    const colorCustom = (customAnswers.themeColor ?? "").trim();
    if (normalizedColor || colorCustom) {
      const presetLabel = themePresets.find(
        (preset) => preset.value.toUpperCase() === normalizedColor
      )?.label;
      const colorParts = [
        normalizedColor
          ? `主题色 ${normalizedColor}${presetLabel ? `（${presetLabel}）` : ""}`
          : "",
        colorCustom ? `补充：${colorCustom}` : "",
      ].filter(Boolean);
      lines.push(`${themeQuestion} → ${colorParts.join("；")}`);
    }

    return `${summaryTitle}：\n${lines.join("\n")}`;
  }

  if (questions.length === 0) {
    return (
      <Stack gap={12}>
        <H1>{title}</H1>
        <Card>
          <CardBody>
            <Stack gap={6}>
              <Text tone="secondary">
                还没有读到 briefData.questions，画布无内容可展示。
              </Text>
              <Text tone="tertiary" size="small">
                请先在同名的 `&lt;name&gt;.canvas.data.json` 中写入 briefData（badge /
                title / subtitle / questions / theme / assumptions），再重新预览本画布。
              </Text>
            </Stack>
          </CardBody>
        </Card>
      </Stack>
    );
  }

  return (
    <Stack gap={24}>
      <Stack gap={8}>
        <Text
          style={{
            fontFamily: ENTERPRISE.labelFont,
            fontSize: 11,
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: ENTERPRISE.labelTracking,
            color: tokens.accent.primary,
          }}
        >
          {badge}
        </Text>
        <H1>{title}</H1>
        <Text tone="secondary">{subtitle}</Text>
      </Stack>

      <Divider />

      {questions.map((question, index) => (
        <Stack key={question.id} gap={10}>
          <Stack gap={2}>
            <Row gap={10} style={{ alignItems: "baseline" }}>
              <SectionLabel text={`Q${index + 1}`} />
              <H3>{question.question}</H3>
            </Row>
            {question.hint ? (
              <Text tone="tertiary" size="small" style={{ paddingLeft: 28 }}>
                {question.hint}
              </Text>
            ) : null}
          </Stack>
          <Row gap={8} style={{ flexWrap: "wrap", paddingLeft: 28 }}>
            {question.options.map((option) => (
              <OptionChip
                key={option.value}
                label={option.label}
                selected={(selections[question.id] ?? []).includes(option.value)}
                onClick={() => toggle(question.id, option.value, question.multi)}
              />
            ))}
          </Row>
          <div style={{ paddingLeft: 28 }}>
            <TextInput
              value={customAnswers[question.id] ?? ""}
              onChange={(value) => setCustom(question.id, value)}
              placeholder="自定义回答（可选，优先于上方选项）"
            />
          </div>
        </Stack>
      ))}

      <Stack gap={10}>
        <Stack gap={2}>
          <Row gap={10} style={{ alignItems: "baseline" }}>
            <SectionLabel text={`Q${questions.length + 1}`} />
            <H3>{themeQuestion}</H3>
          </Row>
          <Text tone="tertiary" size="small" style={{ paddingLeft: 28 }}>
            {themeHint}
          </Text>
        </Stack>

        <Row gap={8} style={{ flexWrap: "wrap", paddingLeft: 28 }}>
          {themePresets.map((preset) => {
            const selected = normalizedColor === preset.value.toUpperCase();
            return (
              <div
                key={preset.value}
                onClick={() => setThemeColor(preset.value.toUpperCase())}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "6px 12px",
                  borderRadius: ENTERPRISE.radiusMd,
                  border: `1px solid ${selected ? ENTERPRISE.borderStrong : tokens.stroke.secondary}`,
                  background: selected
                    ? ENTERPRISE.accentSoft
                    : tokens.fill.tertiary,
                  cursor: "pointer",
                  userSelect: "none",
                }}
              >
                <div
                  style={{
                    width: 12,
                    height: 12,
                    borderRadius: 3,
                    background: preset.value,
                    border: `1px solid ${tokens.stroke.secondary}`,
                  }}
                />
                <Text size="small" tone={selected ? "primary" : "secondary"}>
                  {preset.label}
                </Text>
              </div>
            );
          })}
        </Row>

        <Row gap={10} style={{ alignItems: "center", paddingLeft: 28 }}>
          <input
            type="color"
            value={normalizedColor || themePresets[0]?.value || "#3B6CF4"}
            onChange={(event) => setThemeColor(event.target.value.toUpperCase())}
            style={{
              width: 40,
              height: 28,
              padding: 0,
              borderRadius: ENTERPRISE.radiusSm,
              border: `1px solid ${tokens.stroke.secondary}`,
              background: tokens.fill.tertiary,
              cursor: "pointer",
            }}
          />
          <div style={{ width: 170 }}>
            <TextInput
              value={themeColor}
              onChange={setThemeColor}
              placeholder="#1D4ED8 或 29, 78, 216"
            />
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "4px 10px",
              borderRadius: ENTERPRISE.radiusSm,
              border: `1px solid ${tokens.stroke.secondary}`,
              background: tokens.fill.tertiary,
            }}
          >
            <div
              style={{
                width: 14,
                height: 14,
                borderRadius: 3,
                background: normalizedColor || "transparent",
                border: `1px solid ${tokens.stroke.secondary}`,
              }}
            />
            <Text
              size="small"
              tone={normalizedColor ? "primary" : "tertiary"}
              style={{ fontFamily: "ui-monospace, Menlo, Consolas, monospace" }}
            >
              {normalizedColor || (themeColor.trim() ? "无法识别" : "未选择")}
            </Text>
          </div>
        </Row>

        <div style={{ paddingLeft: 28 }}>
          <TextInput
            value={customAnswers.themeColor ?? ""}
            onChange={(value) => setCustom("themeColor", value)}
            placeholder="自定义补充（如：跟品牌色、高饱和度、需要深浅两套）"
          />
        </div>
      </Stack>

      <Divider />

      <Card>
        <CardHeader>
          <Text
            style={{
              fontFamily: ENTERPRISE.labelFont,
              fontSize: 13,
              fontWeight: 600,
              letterSpacing: "0.01em",
              color: tokens.text.primary,
            }}
          >
            AI 默认假设（如果你直接开始）
          </Text>
        </CardHeader>
        <CardBody>
          <Stack gap={6}>
            {assumptions.map((assumption, index) => (
              <Row key={index} gap={10} style={{ alignItems: "flex-start" }}>
                <Text
                  style={{
                    fontFamily: ENTERPRISE.labelFont,
                    fontSize: 11,
                    fontWeight: 700,
                    color: tokens.accent.primary,
                    letterSpacing: ENTERPRISE.labelTracking,
                    flexShrink: 0,
                    lineHeight: "20px",
                  }}
                >
                  {index + 1}
                </Text>
                <Text tone="secondary" size="small">
                  {assumption}
                </Text>
              </Row>
            ))}
          </Stack>
        </CardBody>
      </Card>

      {/* 吸底操作条：位于内容末尾（符合阅读顺序），但滚动时始终可见。
          bottom 必须为 0：sticky 的偏移是相对可视滚动区域计算的，写成负值会把操作条
          顶到可视区域下方而被裁切（按钮显示不全）。
          左右负 margin 抵消 canvas runtime 给 #root 的默认左右 padding（32px），
          让背景横向铺满、滚动时不漏边；底部负 margin 抵消 24px 下 padding，
          同时在 padding-bottom 里补回同样的 24px，保证操作条自身高度完整。 */}
      <div
        style={{
          position: "sticky",
          bottom: 0,
          marginBottom: -24,
          marginLeft: -32,
          marginRight: -32,
          padding: "14px 32px 38px",
          background: tokens.bg.chrome,
          borderTop: `1px solid ${tokens.stroke.secondary}`,
          zIndex: 10,
        }}
      >
        <Row gap={12} style={{ alignItems: "center", flexWrap: "wrap" }}>
          <Button
            onClick={() =>
              dispatch({ type: "appendToAgentInput", text: buildSummary() })
            }
            disabled={completedCount === 0}
          >
            {submitLabel}
          </Button>
          <Button
            variant="secondary"
            onClick={() =>
              dispatch({
                type: "appendToAgentInput",
                text: "按 AI 默认假设直接开始做网站",
              })
            }
          >
            {defaultLabel}
          </Button>
          <div style={{ flex: 1 }} />
          <div
            style={{
              padding: "3px 12px",
              borderRadius: 999,
              background:
                completedCount === totalCount
                  ? ENTERPRISE.accentSoft
                  : tokens.fill.quaternary,
              border: `1px solid ${
                completedCount === totalCount
                  ? tokens.accent.primary
                  : tokens.stroke.secondary
              }`,
              fontFamily: ENTERPRISE.labelFont,
              fontSize: 12,
              fontWeight: 500,
              color:
                completedCount === totalCount
                  ? tokens.accent.primary
                  : tokens.text.tertiary,
            }}
          >
            {completedCount} / {totalCount} 已回答
          </div>
        </Row>
      </div>
    </Stack>
  );
}
