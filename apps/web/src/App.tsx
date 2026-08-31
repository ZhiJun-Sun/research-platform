import { useEffect, useMemo, useState } from 'react'
import { advanceRun, ApiError, cancelRun, checkCheckpoint, compareResults, createDataset, createDraft, createExport, createPlot, ensureDevSession, getRealSection, getWorkspace, listCheckpoints, listDrafts, listMetrics, listResults, seedDemo, submitDraft, updateDraft } from './lib/api'
import type { ApiCatalogItem, ApiRun } from './lib/api'
import {
  Activity,
  ArrowLeft,
  BarChart3,
  Check,
  ChevronDown,
  ChevronRight,
  CircleStop,
  Cpu,
  Database,
  Download,
  FileCode2,
  FileUp,
  FlaskConical,
  Folder,
  FolderInput,
  FolderPlus,
  GripVertical,
  GitBranch,
  HardDrive,
  Home,
  Layers3,
  Link2,
  Menu,
  Moon,
  Play,
  Plus,
  RefreshCw,
  Search,
  Share2,
  SlidersHorizontal,
  Settings,
  Sun,
  Trash2,
  X,
} from 'lucide-react'

type View = 'dashboard' | 'datasets' | 'code' | 'experiments' | 'checkpoints' | 'results' | 'run' | 'permissions' | 'environments'
type Theme = 'light' | 'dark' | 'system'
type AssetKind = 'dataset' | 'code' | 'checkpoint'
type RunCardId = 'metrics' | 'resources' | 'logs' | 'lineage'
type ExperimentParameter = { id: number; name: string; label: string; type: 'integer' | 'number' | 'boolean' | 'enum' | 'string'; value: string; mapping: string; custom?: boolean }

const navItems = [
  { id: 'dashboard' as const, label: '运行中心', icon: Home },
  { id: 'datasets' as const, label: '数据', icon: Database },
  { id: 'code' as const, label: '模型代码', icon: FileCode2 },
  { id: 'experiments' as const, label: '实验', icon: FlaskConical },
  { id: 'checkpoints' as const, label: 'Checkpoint', icon: Layers3 },
  { id: 'results' as const, label: '结果与对比', icon: BarChart3 },
]

const runs = [
  { id: 'RUN-042', name: 'Top-30 相似流域微调', model: 'KG-MoE-MS', dataset: 'CAMELS × 北江 v3', gpu: 'GPU 0', epoch: 36, total: 50, nse: 0.846, status: '运行中', eta: '18 分钟' },
  { id: 'RUN-043', name: 'GRU 跨流域基线', model: 'GRU Baseline', dataset: 'CAMELS-US v2', gpu: 'GPU 1', epoch: 12, total: 30, nse: 0.781, status: '运行中', eta: '27 分钟' },
  { id: 'RUN-041', name: 'Top-4 小样本迁移', model: 'KG-MoE-MS', dataset: '北江目标流域 v3', gpu: '—', epoch: 50, total: 50, nse: 0.812, status: '已完成', eta: '—' },
]

const assetTree = [
  { kind: 'dataset' as const, label: '数据集', count: 8, children: ['CAMELS-US', '北江目标流域', '融合训练集 Top-30'] },
  { kind: 'code' as const, label: '模型代码', count: 5, children: ['KG-MoE-MS', 'GRU Baseline', 'NeuralHydrology'] },
  { kind: 'checkpoint' as const, label: 'Checkpoint', count: 16, children: ['Top-30 Best', 'CAMELS Pretrain', 'GRU Baseline Best'] },
]

const chartValues = [18, 31, 27, 45, 54, 49, 63, 69, 72, 78, 83, 86]
const observedValues = [18, 32, 27, 49, 71, 58, 88, 76, 61, 47, 38, 29]
const predictedValues = [20, 29, 30, 45, 66, 61, 82, 79, 64, 45, 40, 31]

function Sparkline({ values, secondary }: { values: number[]; secondary?: number[] }) {
  const points = (data: number[]) => data.map((v, i) => `${(i / (data.length - 1)) * 100},${100 - v}`).join(' ')
  return (
    <svg className="sparkline" viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="指标变化曲线">
      <line x1="0" y1="25" x2="100" y2="25" className="chart-grid" />
      <line x1="0" y1="50" x2="100" y2="50" className="chart-grid" />
      <line x1="0" y1="75" x2="100" y2="75" className="chart-grid" />
      {secondary && <polyline points={points(secondary)} className="chart-line secondary-line" />}
      <polyline points={points(values)} className="chart-line primary-line" />
    </svg>
  )
}

function StatusBadge({ status }: { status: string }) {
  const tone = status === '运行中' ? 'running' : status === '已完成' ? 'success' : 'neutral'
  return <span className={`status-badge ${tone}`}><span className="status-dot" />{status}</span>
}

function Dashboard({ openRun, openWizard, openGpu }: { openRun: () => void; openWizard: () => void; openGpu: () => void }) {
  const [onboardingOpen,setOnboardingOpen]=useState(true)
  const [apiRuns, setApiRuns] = useState<ApiRun[]>([])
  const [workspaceError, setWorkspaceError] = useState<string | null>(null)
  const [loadingWorkspace, setLoadingWorkspace] = useState(true)
  const loadWorkspace = async () => {
    setLoadingWorkspace(true)
    setWorkspaceError(null)
    try {
      await ensureDevSession()
      const workspace = await getWorkspace()
      setApiRuns(workspace.runs)
    } catch (error) {
      setWorkspaceError(error instanceof ApiError ? error.message : '无法连接本地 API')
    } finally {
      setLoadingWorkspace(false)
    }
  }
  useEffect(() => { void loadWorkspace() }, [])
  const statusLabel: Record<ApiRun['status'], string> = { QUEUED: '等待中', RUNNING: '运行中', SUCCEEDED: '已完成', CANCELLED: '已取消' }
  const progressRun = async (runId: string, action: 'advance' | 'cancel') => {
    try {
      const updated = action === 'advance' ? await advanceRun(runId) : await cancelRun(runId)
      setApiRuns(items => items.map(item => item.id === updated.id ? updated : item))
    } catch (error) {
      setWorkspaceError(error instanceof ApiError ? error.message : 'Run 操作失败')
    }
  }
  return (
    <div className="page-stack">
      <header className="page-heading">
        <div><p className="eyebrow">WORKSPACE / FLOOD-FORECAST</p><h1>运行中心</h1><p>先处理正在运行的实验，再检查等待中的任务。</p></div>
        <button className="button primary" onClick={openWizard}><Plus size={16} />创建实验</button>
      </header>

      {onboardingOpen&&<section className="onboarding"><div><span className="mono-label">GETTING STARTED / 3 OF 5</span><b>完成首个可复现实验</b><p><span className="done">导入数据</span><span className="done">导入代码</span><span className="done">确认实验模板</span><span>创建实验</span><span>启动首个 Run</span></p></div><button className="button ghost" onClick={()=>setOnboardingOpen(false)}>暂时隐藏</button></section>}
      <section className="run-overview">
        <div className="run-overview-copy"><span className="mono-label">ACTIVE QUEUE</span><strong>2 项运行中 · 3 项等待</strong><p>预计下一项任务将在 18 分钟后获得资源</p></div>
        <button className="gpu-compact" onClick={openGpu} aria-label="查看 GPU 使用详情"><Cpu size={16} /><span><b>GPU 0</b><small>93% · 20.6 / 24 GB</small></span><span><b>GPU 1</b><small>76% · 17.2 / 24 GB</small></span><ChevronRight size={16} /></button>
      </section>

      <section className="section-block">
        <div className="section-heading"><div><h2>当前训练任务</h2><p>来自本地 FastAPI Fake Runner 的受保护 API 数据</p></div><button className="button ghost" onClick={() => void loadWorkspace()} disabled={loadingWorkspace}><RefreshCw size={14} />{loadingWorkspace ? '加载中' : '刷新状态'}</button></div>
        {workspaceError && <p className="error-notice">API 联调错误：{workspaceError}</p>}
        <div className="run-table-wrap">
          <table className="run-table">
            <thead><tr><th>任务</th><th>模型 / 数据</th><th>进度</th><th>NSE</th><th>GPU</th><th>状态</th><th /></tr></thead>
            <tbody>{apiRuns.map((run) => (
              <tr key={run.id} onClick={openRun} className="clickable-row">
                <td><span className="run-id">{run.id}</span><b>{run.name}</b></td>
                <td><span>{run.model}</span><small>{run.dataset}</small></td>
                <td><div className="table-progress"><span><i style={{ width: `${(run.epoch / run.total_epochs) * 100}%` }} /></span><small>Epoch {run.epoch}/{run.total_epochs} · {run.eta ?? '—'}</small></div></td>
                <td className="metric">{run.nse?.toFixed(3) ?? '—'}</td><td className="mono">{run.gpu}</td><td><StatusBadge status={statusLabel[run.status]} /></td>
                <td onClick={event => event.stopPropagation()}>{run.status === 'RUNNING' && <button className="button ghost" onClick={() => void progressRun(run.id, 'advance')}>推进</button>}{(run.status === 'RUNNING' || run.status === 'QUEUED') && <button className="button ghost" onClick={() => void progressRun(run.id, 'cancel')}>取消</button>}</td>
              </tr>
            ))}{!loadingWorkspace && apiRuns.length === 0 && <tr><td colSpan={7}>暂无后端 Run</td></tr>}</tbody>
          </table>
        </div>
      </section>

      <section className="summary-grid">
        <article><span className="mono-label">RECENT BEST</span><strong>0.846</strong><p>NSE · Top-30 相似流域</p><Sparkline values={chartValues} /></article>
        <article><span className="mono-label">THIS WEEK</span><strong>27.4h</strong><p>累计 GPU 训练时长</p><div className="mini-bars">{[40, 65, 48, 80, 55, 91, 72].map((v, i) => <i key={i} style={{ height: `${v}%` }} />)}</div></article>
        <article className="activity-list"><span className="mono-label">RECENT ACTIVITY</span><p><Check size={14} />RUN-041 已生成评估报告<small>12 分钟前</small></p><p><GitBranch size={14} />Checkpoint 派生出 2 个微调任务<small>1 小时前</small></p><p><Database size={14} />北江目标流域 v3 已冻结<small>昨天</small></p></article>
      </section>
    </div>
  )
}

function CodeTemplateWorkbench() {
  const [task, setTask] = useState<'训练' | '评估' | '预测' | '绘图'>('训练')
  const commands = {
    训练: ['TRAIN COMMAND', 'python train.py --config ${CONFIG_PATH} --epochs ${epochs} --batch-size ${batch_size}'],
    评估: ['EVALUATE COMMAND', 'python evaluate.py --checkpoint ${CHECKPOINT_PATH} --data ${DATASET_PATH}'],
    预测: ['PREDICT COMMAND', 'python predict.py --checkpoint ${CHECKPOINT_PATH} --data ${DATASET_PATH}'],
    绘图: ['PLOT COMMAND', 'python plot.py --predictions ${PREDICTIONS_PATH} --output ${OUTPUT_PATH}'],
  }
  return <section className="code-workbench"><div className="section-heading"><div><h3>实验模板</h3><p>清单优先；当前模板由 hydro-experiment.yaml 解析</p></div><button className="button secondary"><Plus size={14}/>创建模板</button></div><div className="template-cards"><article className="selected"><span className="mono-label">TEMPLATE / V4</span><b>标准水文预测</b><small>4 类任务 · 6 个参数 · JSONL</small></article><article><span className="mono-label">TEMPLATE / V2</span><b>跨流域微调</b><small>训练 + 评估 · 9 个参数</small></article></div><div className="task-tabs">{(['训练','评估','预测','绘图'] as const).map(item=><button className={task===item?'active':''} onClick={()=>setTask(item)} key={item}>{item}<span>已配置</span></button>)}</div><div className="command-preview"><span className="mono-label">{commands[task][0]}</span><code>{commands[task][1]}</code><button className="button ghost">编辑命令与参数</button></div></section>
}

function DatasetCreateModal({ close }: { close: () => void }) {
  const [source, setSource] = useState<'upload' | 'url' | 'derive'>('upload')
  const [stage, setStage] = useState<'source' | 'mapping'>('source')
  const sources = [
    { id: 'upload' as const, label: '本地上传', note: '文件或整个文件夹', icon: FileUp },
    { id: 'url' as const, label: 'URL 下载', note: '服务器后台下载', icon: Link2 },
    { id: 'derive' as const, label: '版本派生', note: '从已有版本加工', icon: GitBranch },
  ]
  return <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="创建数据"><div className="dataset-modal"><header><div><span className="mono-label">CREATE DATA</span><h2>{stage === 'source' ? '创建数据' : '确认字段映射'}</h2><p>{stage === 'source' ? '选择数据来源，导入后将自动识别字段语义。' : '自动识别结果可以修改；确认后生成新的不可变版本。'}</p></div><button className="icon-button" onClick={close}><X size={18}/></button></header>{stage === 'source' ? <main><div className="source-options">{sources.map(({id,label,note,icon:Icon})=><button key={id} className={source === id ? 'selected' : ''} onClick={()=>setSource(id)}><Icon size={19}/><b>{label}</b><span>{note}</span>{source===id&&<Check size={14}/>}</button>)}</div>{source==='upload'&&<div className="drop-zone"><FileUp size={24}/><b>拖入 CSV、Parquet、NetCDF 或文件夹</b><span>也可以点击选择；原始内容不会被覆盖</span><button className="button secondary">选择本地内容</button></div>}{source==='url'&&<div className="form-stack"><label>下载地址<input placeholder="https://example.org/dataset.zip"/></label><label>保存到文件夹<select><option>/公开数据/CAMELS</option><option>/北江数据</option></select></label></div>}{source==='derive'&&<div className="form-stack"><label>来源版本<select><option>北江目标流域 · v3</option><option>CAMELS-US · v2</option></select></label><label>派生说明<input placeholder="例如：修正单位并更新流域映射"/></label></div>}</main>:<main><div className="mapping-summary"><StatusBadge status="已完成"/><div><b>自动识别 8 个字段</b><span>置信度较低的字段已标记，请检查后确认。</span></div></div><div className="mapping-table"><div className="mapping-head"><span>原始字段</span><span>语义类型</span><span>标准名称 / 单位</span></div>{[['date','时间','time'],['gauge_id','流域 ID','basin_id'],['prcp','动态输入','precipitation · mm/h'],['temp','动态输入','temperature · °C'],['q_obs','目标变量','discharge · m³/s']].map(([raw,type,target],i)=><div key={raw} className={i===3?'needs-review':''}><code>{raw}</code><select defaultValue={type}><option>时间</option><option>流域 ID</option><option>动态输入</option><option>静态属性</option><option>目标变量</option><option>忽略</option></select><input defaultValue={target}/></div>)}</div><p className="mapping-note">修改映射不会改写已有版本；平台会创建新版本并记录映射来源。</p></main>}<footer><button className="button secondary" onClick={stage==='mapping'?()=>setStage('source'):close}>{stage==='mapping'?'返回数据来源':'暂不创建'}</button><button className="button primary" onClick={stage==='source'?()=>setStage('mapping'):close}>{stage==='source'?'导入并识别字段':'确认映射并创建版本'}<ChevronRight size={15}/></button></footer></div></div>
}

function ShareModal({ close }: { close: () => void }) {
  const [created,setCreated]=useState(false)
  const [revoked,setRevoked]=useState(false)
  return <div className="modal-backdrop"><div className="share-modal"><header><div><span className="mono-label">READ-ONLY SHARE</span><h2>只读链接管理</h2><p>链接仅允许查看当前不可变版本，不能派生或运行。</p></div><button className="icon-button" onClick={close}><X size={18}/></button></header><main>{!created?<div className="form-stack"><label>有效期<select><option>7 天</option><option>30 天</option><option>永久有效</option></select></label><div className="permission-notice"><b>只读权限</b><span>查看元数据、版本和允许下载的产物</span></div><button className="button primary" onClick={()=>setCreated(true)}>创建只读链接</button></div>:<div className="share-link"><label>分享链接<input readOnly value="https://hydrolab/share/ck_a82f9"/></label><div><span>有效期</span><b>{revoked?'已撤销':'2026-09-05 17:00'}</b></div><div><span>访问状态</span><b>{revoked?'不可访问':'尚未访问'}</b></div><div className="share-actions"><button className="button secondary" disabled={revoked}>复制链接</button><button className="button danger" disabled={revoked} onClick={()=>setRevoked(true)}>提前撤销</button></div></div>}</main></div></div>
}

function CheckpointReuse({ close }: { close: () => void }) {
  const [mode,setMode]=useState('finetune')
  const [repair,setRepair]=useState(false)
  return <div className="modal-backdrop"><div className="reuse-modal"><header><div><span className="mono-label">REUSE CHECKPOINT</span><h2>复用 Top-30 Best</h2><p>选择用途并在提交前处理兼容性问题。</p></div><button className="icon-button" onClick={close}><X size={18}/></button></header><main><div className="mode-grid">{[['resume','断点续训'],['finetune','跨数据集微调'],['evaluate','评估'],['predict','预测']].map(([id,label])=><button className={mode===id?'selected':''} onClick={()=>setMode(id)} key={id}><b>{label}</b><span>{id}</span></button>)}</div><div className="parameter-grid"><label>目标数据<select><option>北江目标流域 v3</option></select></label><label>运行环境<select><option>env-v3 · PyTorch 2.4</option></select></label></div><section className="compatibility-block"><div><span className="status-badge neutral">需要处理</span><b>发现 2 个兼容性差异</b></div><ul><li><code>head.weight</code>：输出形状 1 → 3</li><li><code>input_variables</code>：新增 soil_moisture</li></ul><button className="button secondary" onClick={()=>setRepair(!repair)}>配置兼容性修复</button>{repair&&<div className="repair-grid"><label>head.weight<select><option>跳过并重新初始化</option><option>映射到 output_head.weight</option></select></label><label>新增输入字段<select><option>部分加载输入层</option><option>阻止运行</option></select></label></div>}</section></main><footer><button className="button secondary" onClick={close}>取消</button><button className="button primary" disabled={!repair}>确认修复并继续</button></footer></div></div>
}

function AssetAdminPage({ type }: { type:'permissions'|'environments' }) {
  return <div className="page-stack"><header className="page-heading"><div><p className="eyebrow">{type==='permissions'?'ACCESS CONTROL':'RUNTIME ASSETS'}</p><h1>{type==='permissions'?'权限与分享':'运行环境'}</h1><p>{type==='permissions'?'集中管理所有资源的只读分享链接。':'管理可供代码和实验选择的版本化运行环境。'}</p></div><button className="button primary"><Plus size={15}/>{type==='permissions'?'创建分享':'创建环境'}</button></header><section className="section-block"><div className="asset-list">{(type==='permissions'?[['北江目标流域 v3','有效至 09-05','尚未访问'],['Top-30 Best','永久有效','已访问 4 次']]:[['env-v3 · PyTorch 2.4','CUDA 12.4','构建成功'],['env-v2 · PyTorch 2.2','CUDA 12.1','构建成功']]).map(row=><div key={row[0]}><HardDrive size={16}/><span><b>{row[0]}</b><small>{row[1]}</small></span><code>{row[2]}</code><button className="button ghost">管理</button></div>)}</div></section></div>
}

function Assets({ initialKind, openDatasetCreate }: { initialKind: AssetKind; openDatasetCreate?: () => void }) {
  const [selections, setSelections] = useState<Record<AssetKind, string>>({ dataset: '北江目标流域', code: 'KG-MoE-MS', checkpoint: 'Top-30 Best' })
  const [shareOpen,setShareOpen]=useState(false)
  const [reuseOpen,setReuseOpen]=useState(false)
  const selected = { kind: initialKind, name: selections[initialKind] }
  const selectAsset = (kind: AssetKind, name: string) => setSelections(current => ({ ...current, [kind]: name }))
  const iconFor = (kind: AssetKind) => kind === 'dataset' ? Database : kind === 'code' ? FileCode2 : Layers3
  const detailByKind = {
    dataset: {
      title: '数据概况',
      subtitle: '上传后自动解析的时间与字段摘要',
      rows: [['时间范围', '2012-01-01 — 2022-12-31'], ['时间频率', '1 hour'], ['流域数量', '33'], ['动态输入', 'precipitation, temperature, evaporation'], ['目标变量', 'discharge'], ['内容摘要', 'sha256: 9e1c...a402']],
      lineage: ['原始观测 v1', '质量修复 v2', '目标流域 v3'],
    },
    code: {
      title: '代码概况',
      subtitle: '导入时锁定的仓库、环境和实验协议',
      rows: [['代码来源', 'Git repository'], ['当前提交', '8fc2a1'], ['运行环境', 'PyTorch 2.4 · CUDA 12.4'], ['训练命令', 'python train.py --config ${CONFIG_PATH}'], ['进度协议', 'JSONL Schema v1'], ['内容摘要', 'sha256: c78a...11fd']],
      lineage: ['Git main', 'commit 8fc2a1', '代码快照 v5'],
    },
    checkpoint: {
      title: '权重概况',
      subtitle: '用于续训、微调和评估的模型资产',
      rows: [['来源任务', 'RUN-042'], ['保存 Epoch', '42 / 50'], ['架构签名', 'kg-moe-ms:v3'], ['验证 NSE', '0.851'], ['Scaler', 'CAMELS global train'], ['内容摘要', 'sha256: 02be...72a8']],
      lineage: ['CAMELS 预训练', 'RUN-042 微调', 'Best Checkpoint'],
    },
  }[selected.kind]
  return (
    <div className="page-stack">
      <header className="page-heading"><div><p className="eyebrow">{initialKind === 'dataset' ? 'DATA' : initialKind === 'code' ? 'MODEL CODE' : 'CHECKPOINTS'}</p><h1>{initialKind === 'dataset' ? '数据' : initialKind === 'code' ? '模型代码' : 'Checkpoint'}</h1><p>{initialKind === 'dataset' ? '用自由目录和全局搜索管理不可变数据版本。' : initialKind === 'code' ? '管理 ZIP 或 Git 导入的模型代码和运行协议。' : '管理可用于续训、微调、评估和预测的权重。'}</p></div><div className="page-actions">{initialKind === 'dataset'&&<button className="button secondary"><FolderPlus size={15}/>创建文件夹</button>}<button className="button primary" onClick={initialKind === 'dataset' ? openDatasetCreate : undefined}><Plus size={16} />{initialKind === 'dataset' ? '创建数据' : initialKind === 'checkpoint' ? '导入权重' : '导入代码'}</button></div></header>
      <div className="asset-browser">
        <aside className="asset-tree">
          <div className="tree-search"><Search size={15} /><input aria-label="搜索资源" placeholder={`搜索全部${initialKind === 'dataset' ? '数据' : initialKind === 'code' ? '代码' : '权重'}`} /></div>
          {initialKind === 'dataset' && <div className="folder-path"><FolderInput size={14}/><span>全部数据 / 北江研究 / 目标流域</span></div>}
          {assetTree.filter(group => group.kind === initialKind).map((group) => { const Icon = iconFor(group.kind); return <div className="tree-group" key={group.kind}><div className="tree-group-title"><ChevronDown size={14} /><Icon size={15} /><b>{group.label}</b><span>{group.count}</span></div>{group.children.map((child) => <button className={selected.name === child ? 'selected' : ''} key={child} onClick={() => selectAsset(group.kind, child)}><span className="tree-line" />{group.kind === 'dataset' ? <Folder size={14} /> : <FileCode2 size={14} />}{child}</button>)}</div> })}
        </aside>
        <main className="asset-detail">
          <div className="detail-heading"><div className="asset-icon">{selected.kind === 'dataset' ? <Database /> : selected.kind === 'code' ? <FileCode2 /> : <Layers3 />}</div><div><span className="mono-label">{selected.kind.toUpperCase()}</span><h2>{selected.name}</h2></div><div className="detail-actions">{selected.kind==='checkpoint'&&<button className="button primary" onClick={()=>setReuseOpen(true)}><Play size={14}/>复用权重</button>}<button className="button secondary" onClick={()=>setShareOpen(true)}><Share2 size={14}/>分享资源</button><button className="button secondary">查看版本</button></div></div>
          <div className="detail-tabs"><button className="active">概览</button><button>版本</button><button>血缘</button><button>使用记录</button></div>
          <section className="metadata-grid"><div><span>当前版本</span><b>v3 · 已冻结</b></div><div><span>更新时间</span><b>2026-08-28 21:40</b></div><div><span>所有者</span><b>sunzhijun03</b></div><div><span>可见范围</span><b>仅自己</b></div></section>
          {selected.kind === 'code' && <><CodeTemplateWorkbench/><section className="code-workbench"><div className="section-heading"><div><h3>运行环境版本</h3><p>代码版本可关联多个独立环境，实验锁定精确版本</p></div><button className="button secondary"><Plus size={14}/>创建环境</button></div><div className="environment-list"><div className="active"><span><b>env-v3 · PyTorch 2.4</b><small>Python 3.11 · CUDA 12.4 · sha256: 7c4e...</small></span><StatusBadge status="已完成"/></div><div><span><b>env-v2 · PyTorch 2.2</b><small>Python 3.10 · CUDA 12.1 · sha256: 29ad...</small></span><button className="button ghost">设为模板默认</button></div></div></section></>}
          <section className="detail-section"><div className="section-heading"><div><h3>{detailByKind.title}</h3><p>{detailByKind.subtitle}</p></div><StatusBadge status="已完成" /></div><dl className="property-list">{detailByKind.rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd className={label === '内容摘要' ? 'mono' : ''}>{value}</dd></div>)}</dl></section>
          {selected.kind === 'checkpoint' && <><section className="checkpoint-grid"><article><span className="mono-label">COMPATIBILITY</span><strong>部分兼容</strong><small>2 项需要映射或重新初始化</small></article><article><span className="mono-label">OPTIMIZER</span><strong>AdamW</strong><small>Scheduler 与 Epoch 状态完整</small></article><article><span className="mono-label">INPUT / OUTPUT</span><strong>12 → 1</strong><small>hourly discharge</small></article></section><section className="detail-section"><div className="section-heading"><div><h3>派生运行</h3><p>由该权重创建的续训、微调、评估和预测</p></div></div><div className="asset-list"><div><GitBranch size={15}/><span><b>RUN-046 · 北江 v4 微调</b><small>finetune · 运行中</small></span><code>今天 16:40</code></div><div><GitBranch size={15}/><span><b>RUN-045 · 洪峰评估</b><small>evaluate · 已完成</small></span><code>NSE 0.838</code></div></div></section></>}
          <section className="detail-section"><h3>版本血缘</h3><div className="lineage">{detailByKind.lineage.map((item, index) => <span key={item} className={index === detailByKind.lineage.length - 1 ? 'current' : ''}>{item}{index < detailByKind.lineage.length - 1 && <ChevronRight />}</span>)}</div></section>
          {shareOpen&&<ShareModal close={()=>setShareOpen(false)}/>} {reuseOpen&&<CheckpointReuse close={()=>setReuseOpen(false)}/>}
        </main>
      </div>
    </div>
  )
}

function ExperimentList({ openRun, openWizard }: { openRun: () => void; openWizard: () => void }) {
  const [selected,setSelected]=useState<string|null>(null)
  if(selected) return <div className="page-stack"><header className="page-heading result-detail-heading"><button className="icon-button" onClick={()=>setSelected(null)}><ArrowLeft size={18}/></button><div><p className="eyebrow">EXPERIMENT / EXP-012</p><h1>Top-30 相似流域微调</h1><p>可复用配置定义 · 当前版本 v4</p></div><button className="button primary" onClick={openWizard}><Play size={15}/>创建新 Run</button></header><section className="experiment-config"><div><span>实验模板</span><b>跨流域微调 · v2</b></div><div><span>数据版本</span><b>北江目标流域 · v3</b></div><div><span>运行环境</span><b>env-v3 · PyTorch 2.4</b></div><div><span>默认参数</span><b>6 项 · seed 42</b></div></section><section className="section-block"><div className="section-heading"><div><h2>运行历史</h2><p>同一实验配置产生的独立 Run</p></div><div className="tree-search"><Search size={14}/><input placeholder="按 Seed、状态或差异搜索"/></div></div><div className="run-table-wrap"><table className="run-table"><thead><tr><th>Run</th><th>Seed / 参数覆盖</th><th>状态</th><th>NSE</th><th>结束时间</th><th/></tr></thead><tbody>{[['RUN-042','42 · 默认参数','已完成','0.846','今天 15:28'],['RUN-040','17 · learning_rate=0.001','失败','—','今天 09:12'],['RUN-037','7 · hidden_size=256','已完成','0.829','昨天 20:04']].map((row,i)=><tr className="clickable-row" key={row[0]} onClick={openRun}><td><span className="run-id">{row[0]}</span></td><td>{row[1]}{i===1&&<small>失败现场已保留 · 可从评估阶段重试</small>}</td><td><StatusBadge status={row[2]}/></td><td className="metric">{row[3]}</td><td>{row[4]}</td><td><ChevronRight size={15}/></td></tr>)}</tbody></table></div></section></div>
  return <div className="page-stack"><header className="page-heading"><div><p className="eyebrow">EXPERIMENTS</p><h1>实验</h1><p>实验是可复用配置定义，每次执行会生成独立 Run。</p></div><button className="button primary" onClick={openWizard}><Plus size={16} />创建实验</button></header><section className="section-block"><div className="section-heading"><div><h2>全部实验</h2><p>按数据、模型或标签筛选</p></div><div className="tree-search"><Search size={15}/><input placeholder="搜索实验" /></div></div><div className="run-table-wrap"><table className="run-table"><thead><tr><th>实验定义</th><th>模型 / 数据</th><th>模式</th><th>运行次数</th><th>最近结果</th><th /></tr></thead><tbody>{runs.map((run,i)=><tr key={run.id} onClick={()=>setSelected(run.id)} className="clickable-row"><td><span className="run-id">EXP-{String(12-i).padStart(3,'0')}</span><b>{run.name}</b></td><td><span>{run.model}</span><small>{run.dataset}</small></td><td className="mono">finetune</td><td>{i===0?'3 Runs':'1 Run'}</td><td className="metric">NSE {run.nse.toFixed(3)}</td><td><ChevronRight size={16}/></td></tr>)}</tbody></table></div></section></div>
}

function GpuDrawer({ close }: { close: () => void }) {
  return <div className="drawer-backdrop" onClick={close}><aside className="gpu-drawer" onClick={event => event.stopPropagation()}><header><div><span className="mono-label">COMPUTE STATUS</span><h2>GPU 与队列</h2><p>按任务独占单张 GPU 调度</p></div><button className="icon-button" onClick={close} aria-label="关闭 GPU 详情"><X size={18}/></button></header>{[{id:0,util:93,memory:86,temp:'68°C',power:'289 W',run:'RUN-042'},{id:1,util:76,memory:72,temp:'64°C',power:'251 W',run:'RUN-043'}].map(gpu=><section className="drawer-gpu" key={gpu.id}><div className="panel-topline"><b>GPU {gpu.id} · RTX 4090</b><StatusBadge status="运行中"/></div><div className="drawer-metric"><span>利用率</span><strong>{gpu.util}%</strong></div><div className="usage-bar"><span style={{width:`${gpu.util}%`}}/></div><div className="drawer-metric"><span>显存</span><strong>{gpu.memory}%</strong></div><div className="usage-bar"><span style={{width:`${gpu.memory}%`}}/></div><dl><div><dt>温度</dt><dd>{gpu.temp}</dd></div><div><dt>功率</dt><dd>{gpu.power}</dd></div><div><dt>占用任务</dt><dd>{gpu.run}</dd></div></dl></section>)}<section className="drawer-queue"><div className="panel-topline"><b>等待队列</b><span>3 项</span></div><p><span>1</span>多 Seed 稳定性测试<small>预计 18 分钟</small></p><p><span>2</span>Top-40 迁移实验<small>预计 41 分钟</small></p><p><span>3</span>GRU 多流域评估<small>预计 52 分钟</small></p></section></aside></div>
}

function BasinDiagnostic({ close }: { close: () => void }) {
  const [tab,setTab]=useState<'overview'|'events'>('overview')
  return <div className="drawer-backdrop" onClick={close}><aside className="diagnostic-drawer" onClick={event=>event.stopPropagation()}><header><div><span className="mono-label">BASIN / 11480390</span><h2>流域诊断证据</h2><p>仅展示数据与计算结果，不自动推断原因。</p></div><button className="icon-button" onClick={close}><X size={18}/></button></header><div className="result-tabs"><button className={tab==='overview'?'active':''} onClick={()=>setTab('overview')}>综合诊断</button><button className={tab==='events'?'active':''} onClick={()=>setTab('events')}>洪水事件</button></div>{tab==='overview'?<main><section className="metric-cards compact"><article><span>NSE</span><strong>0.412</strong></article><article><span>KGE</span><strong>0.583</strong></article><article><span>RMSE</span><strong>18.92</strong></article></section><section className="chart-panel diagnostic-chart"><div className="section-heading"><div><h2>实测—预测过程线</h2><p>红色区间表示误差超过 P90</p></div></div><Sparkline values={predictedValues} secondary={observedValues}/></section><div className="evidence-grid"><article><b>散点证据</b><span>高流量区系统性低估</span><strong>R² 0.64</strong></article><article><b>残差证据</b><span>正残差 P90 = 22.4 m³/s</span><strong>偏度 1.82</strong></article><article><b>数据质量</b><span>输入缺失 3.1%，连续缺失最长 6h</span><strong>12 个区间</strong></article></div></main>:<main><div className="event-table"><div><b>事件</b><b>洪峰误差</b><b>峰现偏差</b><b>洪量误差</b></div>{[['2022-06-18','-14.2%','+2h','-8.1%'],['2022-07-03','-22.8%','+4h','-17.3%'],['2022-08-11','+5.4%','-1h','+2.9%']].map(row=><div key={row[0]}>{row.map(value=><span key={value}>{value}</span>)}</div>)}</div><p className="evidence-note">事件按流量阈值自动识别。以上均为计算证据，不代表原因判断。</p></main>}</aside></div>
}

function PlotBuilder({ close }: { close: () => void }) {
  const [mode,setMode]=useState<'form'|'natural'>('form')
  const [planned,setPlanned]=useState(false)
  return <div className="modal-backdrop"><div className="plot-modal"><header><div><span className="mono-label">NEW PLOT</span><h2>添加可复现图表</h2><p>执行前先确认结构化绘图计划。</p></div><button className="icon-button" onClick={close}><X size={18}/></button></header><div className="mode-switch plot-switch"><button className={mode==='form'?'active':''} onClick={()=>setMode('form')}>结构化配置</button><button className={mode==='natural'?'active':''} onClick={()=>setMode('natural')}>自然语言</button></div><main>{mode==='form'?<div className="plot-form"><label>图表类型<select><option>实测—预测过程线</option><option>散点图</option><option>残差图</option><option>指标分布</option></select></label><label>流域<select><option>全部流域</option><option>11480390</option></select></label><label>时间范围<input defaultValue="2022-06-01 — 2022-08-31"/></label><label>导出格式<select><option>PNG + SVG</option><option>SVG</option></select></label></div>:<div className="natural-plot"><textarea defaultValue="绘制流域 11480390 在 2022 年汛期的实测与预测流量过程线，并标出三个最大洪峰。"/><button className="button secondary" onClick={()=>setPlanned(true)}>转换为绘图计划</button></div>}{(mode==='form'||planned)&&<section className="plot-plan"><span className="mono-label">STRUCTURED PLAN</span><dl><div><dt>数据</dt><dd>RUN-042 / predictions.parquet</dd></div><div><dt>图形</dt><dd>hydrograph · observed + predicted</dd></div><div><dt>范围</dt><dd>basin 11480390 · 2022-06—08</dd></div><div><dt>保存</dt><dd>PNG、SVG、CSV、plot-config.yaml、plot.py</dd></div></dl></section>}</main><footer><button className="button secondary" onClick={close}>继续编辑</button><button className="button primary" disabled={mode==='natural'&&!planned} onClick={close}>确认计划并生成</button></footer></div></div>
}

function ExportPicker({ close }: { close: () => void }) {
  const files = ['experiment.yaml','environment.lock','data-manifest.json','metrics.json','predictions.parquet','hydrograph.svg','hydrograph-data.csv','report.md']
  const [selected, setSelected] = useState<string[]>(['metrics.json','predictions.parquet','hydrograph.svg','hydrograph-data.csv'])
  const toggle = (file:string) => setSelected(items => items.includes(file) ? items.filter(item=>item!==file) : [...items,file])
  return <div className="modal-backdrop"><div className="export-modal"><header><div><span className="mono-label">EXPORT RESULT</span><h2>选择导出文件</h2><p>平台将把勾选内容打包，并保留来源清单。</p></div><button className="icon-button" onClick={close}><X size={18}/></button></header><div className="export-presets"><button onClick={()=>setSelected(files)}>全部结果</button><button onClick={()=>setSelected(['hydrograph.svg','hydrograph-data.csv','metrics.json'])}>论文图表</button><button onClick={()=>setSelected(['experiment.yaml','environment.lock','data-manifest.json','metrics.json'])}>复现资料</button></div><main>{files.map(file=><label key={file}><input type="checkbox" checked={selected.includes(file)} onChange={()=>toggle(file)}/><FileCode2 size={15}/><span><b>{file}</b><small>{file.endsWith('.parquet')?'42.8 MB':file.endsWith('.svg')?'284 KB':'12 KB'}</small></span></label>)}</main><footer><span>已选择 {selected.length} 个文件</span><button className="button primary" disabled={!selected.length} onClick={close}><Download size={15}/>生成下载包</button></footer></div></div>
}

function ResultDetail({ back }: { back: () => void }) {
  const [tab,setTab]=useState<'overview'|'basins'|'assets'>('overview')
  const [exportOpen,setExportOpen]=useState(false)
  const [plotOpen,setPlotOpen]=useState(false)
  const [diagnosticOpen,setDiagnosticOpen]=useState(false)
  const basins=[['03173000','0.912','0.938','5.42'],['02053800','0.884','0.906','6.18'],['01632000','0.846','0.919','8.17'],['02315500','0.731','0.802','11.43'],['11480390','0.412','0.583','18.92']]
  const assets=[['predictions.parquet','预测结果','42.8 MB'],['metrics.json','指标','18 KB'],['hydrograph.svg','自动图表','284 KB'],['scatter.svg','自动图表','196 KB'],['best-checkpoint.pt','Checkpoint','186 MB'],['report.md','报告','24 KB']]
  return <div className="page-stack">
    <header className="page-heading result-detail-heading"><button className="icon-button" onClick={back} aria-label="返回结果列表"><ArrowLeft size={18}/></button><div><p className="eyebrow">RESULT / RUN-042</p><h1>Top-30 相似流域微调</h1><p>评估完成 · 北江目标流域 v3 · 33 个流域</p></div><div className="page-actions"><button className="button secondary" onClick={()=>setPlotOpen(true)}><Plus size={15}/>添加图表</button><button className="button primary" onClick={()=>setExportOpen(true)}><Download size={16}/>选择文件导出</button></div></header>
    <div className="result-tabs"><button className={tab==='overview'?'active':''} onClick={()=>setTab('overview')}>结果总览</button><button className={tab==='basins'?'active':''} onClick={()=>setTab('basins')}>逐流域分析</button><button className={tab==='assets'?'active':''} onClick={()=>setTab('assets')}>结果资产</button></div>
    {tab==='overview'&&<><section className="metric-cards"><article><span>RMSE</span><strong>8.170</strong><small className="positive">较基线降低 12.4%</small></article><article><span>NSE</span><strong>0.846</strong><small className="positive">33 流域中位数</small></article><article><span>KGE</span><strong>0.919</strong><small className="positive">提高 0.027</small></article><article><span>MAE / PBIAS</span><strong>5.42</strong><small className="neutral">PBIAS -2.8%</small></article></section><div className="result-conclusion"><span className="mono-label">AUTO SUMMARY</span><b>Top-30 在整体拟合与洪峰过程上优于 Top-4 基线</b><p>33 个流域中 27 个 NSE 提升；低流量时段偏差仍集中在 3 个流域，建议进入逐流域分析。</p></div><div className="comparison-main"><section className="chart-panel"><div className="section-heading"><div><h2>实测—预测过程线</h2><p>自动生成 · 2022-06-18 至 2022-06-20</p></div><div className="legend"><span className="observed">实测</span><span className="predicted">预测</span></div></div><Sparkline values={predictedValues} secondary={observedValues}/><div className="chart-axis"><span>06-18</span><span>06-19</span><span>06-20</span></div></section><section className="distribution-panel"><div className="section-heading"><div><h2>流域 NSE 分布</h2><p>33 个流域 · 中位数 0.846</p></div></div><div className="distribution-bars">{[42,58,66,73,81,84,87,91,94].map((v,i)=><div key={i}><i style={{height:`${v}%`}}/><span>{(0.4+i*.07).toFixed(2)}</span></div>)}</div></section></div></>}
    {tab==='basins'&&<section className="section-block"><div className="section-heading"><div><h2>逐流域指标</h2><p>按任意指标排序，快速定位异常流域</p></div><div className="tree-search"><Search size={14}/><input placeholder="搜索流域 ID"/></div></div><div className="basin-layout"><div className="run-table-wrap"><table className="run-table"><thead><tr><th>流域 ID</th><th>NSE</th><th>KGE</th><th>RMSE</th><th>诊断</th></tr></thead><tbody>{basins.map((row,i)=><tr key={row[0]} className={i===4?'warning-row clickable-row':''} onClick={()=>setDiagnosticOpen(true)}><td className="mono">{row[0]}</td><td className="metric">{row[1]}</td><td>{row[2]}</td><td>{row[3]}</td><td>{i===4?<span className="status-badge">需要检查</span>:'正常'}</td></tr>)}</tbody></table></div><aside><span className="mono-label">DISTRIBUTION</span><h3>NSE 分布</h3><div className="horizontal-bars">{[['≥0.9',6],['0.8–0.9',18],['0.6–0.8',7],['<0.6',2]].map(([label,value])=><div key={label}><span>{label}</span><i><b style={{width:`${Number(value)*5}%`}}/></i><strong>{value}</strong></div>)}</div></aside></div></section>}
    {tab==='assets'&&<section className="section-block"><div className="section-heading"><div><h2>结果资产</h2><p>预测、指标、图表、权重、配置和报告的完整清单</p></div><button className="button primary" onClick={()=>setExportOpen(true)}>选择文件导出</button></div><div className="asset-list">{assets.map(([name,type,size])=><div key={name}><FileCode2 size={16}/><span><b>{name}</b><small>{type} · 来源 RUN-042</small></span><code>{size}</code><button className="button ghost"><Download size={13}/>下载</button></div>)}</div></section>}
    {exportOpen&&<ExportPicker close={()=>setExportOpen(false)}/>} 
    {plotOpen&&<PlotBuilder close={()=>setPlotOpen(false)}/>} 
    {diagnosticOpen&&<BasinDiagnostic close={()=>setDiagnosticOpen(false)}/>} 
  </div>
}

function RunComparison({ selected, back }: { selected:string[]; back:()=>void }) {
  const compared = selected.length ? selected : ['RUN-042','RUN-041']
  return <div className="page-stack"><header className="page-heading result-detail-heading"><button className="icon-button" onClick={back}><ArrowLeft size={18}/></button><div><p className="eyebrow">COMPARE / {compared.length} RUNS</p><h1>实验结果对比</h1><p>基线 RUN-041 · 所选 Run 的任务类型、指标和流域维度兼容</p></div><button className="button secondary">管理对比项</button></header><section className="compare-runs">{compared.map((id,i)=><article className={i===1?'baseline':''} key={id}><span className="mono-label">{i===1?'BASELINE':'CANDIDATE'}</span><b>{id}</b><small>{id==='RUN-042'?'Top-30 相似流域微调':'Top-4 小样本迁移'}</small></article>)}</section><section className="section-block"><div className="section-heading"><div><h2>指标对比</h2><p>全局汇总与相对基线变化</p></div></div><table className="compare-table"><thead><tr><th>Run</th><th>NSE</th><th>KGE</th><th>RMSE</th><th>PBIAS</th></tr></thead><tbody><tr><td>RUN-042</td><td className="positive">0.846 (+0.034)</td><td>0.919</td><td>8.170</td><td>-2.8%</td></tr><tr><td>RUN-041 · 基线</td><td>0.812</td><td>0.892</td><td>9.326</td><td>-4.1%</td></tr></tbody></table></section><div className="comparison-main"><section className="diff-panel"><div className="section-heading"><div><h2>参数差异</h2><p>相同参数已折叠</p></div></div><table><tbody><tr><th>参数</th><th>RUN-041</th><th>RUN-042</th></tr><tr><td>source_basins</td><td>4</td><td className="changed">30</td></tr><tr><td>learning_rate</td><td>0.001</td><td className="changed">0.0005</td></tr><tr><td>seed</td><td>7</td><td className="changed">42</td></tr></tbody></table></section><section className="chart-panel"><div className="section-heading"><div><h2>多 Run 过程线</h2><p>实测值与两组预测结果</p></div></div><Sparkline values={predictedValues} secondary={observedValues}/></section></div><section className="section-block"><div className="section-heading"><div><h2>逐流域差异</h2><p>相对基线的 NSE 变化，按改善幅度排序</p></div></div><div className="basin-diff-grid">{[['03173000','+0.081'],['02053800','+0.052'],['01632000','+0.034'],['02315500','-0.008']].map(([id,delta])=><div key={id}><code>{id}</code><strong className={delta.startsWith('+')?'positive':'negative'}>{delta}</strong><i><b style={{width:`${Math.max(12,Math.abs(Number(delta))*800)}%`}}/></i></div>)}</div></section></div>
}

function ResultIndex({ openDetail, openCompare }: { openDetail: () => void; openCompare:(ids:string[])=>void }) {
  const [selected, setSelected] = useState<string[]>([])
  const results = [
    ['RUN-042','Top-30 相似流域微调','KG-MoE-MS','北江目标流域 v3','0.846','0.919','8.170','今天 15:28','8'],
    ['RUN-041','Top-4 小样本迁移','KG-MoE-MS','北江目标流域 v3','0.812','0.892','9.326','今天 11:04','7'],
    ['RUN-038','CAMELS 全量预训练','KG-MoE-MS','CAMELS-US v2','0.784','0.861','10.482','昨天 22:16','12'],
    ['RUN-035','GRU 跨流域基线','GRU Baseline','CAMELS-US v2','0.731','0.806','12.214','08-27 18:42','6'],
  ]
  const toggle = (id:string) => setSelected(current => current.includes(id) ? current.filter(item=>item!==id) : [...current,id])
  return <div className="page-stack"><header className="page-heading"><div><p className="eyebrow">RESULT INDEX</p><h1>结果与对比</h1><p>浏览所有已产生结果的实验，进入详情或选择多个结果进行对比。</p></div><button className="button primary" disabled={selected.length<2} onClick={()=>openCompare(selected)}>对比所选实验 ({selected.length})</button></header><section className="result-summary"><div><span className="mono-label">RESULTS</span><strong>24</strong><small>已完成实验</small></div><div><span className="mono-label">BEST NSE</span><strong>0.846</strong><small>RUN-042</small></div><div><span className="mono-label">ASSETS</span><strong>186</strong><small>结果文件与图表</small></div></section><section className="section-block"><div className="result-filters"><div className="tree-search"><Search size={14}/><input placeholder="搜索实验名称或 Run ID"/></div><select aria-label="模型筛选"><option>全部模型</option><option>KG-MoE-MS</option><option>GRU Baseline</option></select><select aria-label="数据筛选"><option>全部数据版本</option><option>北江目标流域 v3</option><option>CAMELS-US v2</option></select><select aria-label="排序"><option>NSE 从高到低</option><option>完成时间</option><option>RMSE 从低到高</option></select></div><div className="run-table-wrap"><table className="run-table result-index-table"><thead><tr><th aria-label="选择"/><th>实验结果</th><th>模型 / 数据版本</th><th className="num">NSE</th><th className="num">KGE</th><th className="num">RMSE</th><th>完成时间</th><th>资产</th><th/></tr></thead><tbody>{results.map(row=><tr key={row[0]} className="clickable-row"><td onClick={event=>event.stopPropagation()}><input type="checkbox" checked={selected.includes(row[0])} onChange={()=>toggle(row[0])} aria-label={`选择 ${row[0]}`}/></td><td onClick={openDetail}><span className="run-id">{row[0]}</span><b>{row[1]}</b></td><td onClick={openDetail}><span>{row[2]}</span><small>{row[3]}</small></td><td className="metric num" onClick={openDetail}>{row[4]}</td><td className="num" onClick={openDetail}>{row[5]}</td><td className="num" onClick={openDetail}>{row[6]}</td><td onClick={openDetail}>{row[7]}</td><td onClick={openDetail}>{row[8]} 项</td><td onClick={openDetail}><ChevronRight size={15}/></td></tr>)}</tbody></table></div>{selected.length>0&&<div className="selection-bar"><span>已选择 {selected.length} 个结果</span><button className="button ghost" onClick={()=>setSelected([])}>清除选择</button><button className="button primary" disabled={selected.length<2} onClick={()=>openCompare(selected)}>开始对比</button></div>}</section></div>
}

function RunDetail({ back }: { back: () => void }) {
  const defaultCards: RunCardId[] = ['metrics', 'resources', 'logs', 'lineage']
  const [cards, setCards] = useState<RunCardId[]>(() => {
    const saved = localStorage.getItem('hydrolab-run-layout')
    return saved ? JSON.parse(saved) : defaultCards
  })
  const [hidden, setHidden] = useState<RunCardId[]>([])
  const [editing, setEditing] = useState(false)
  const [dragged, setDragged] = useState<RunCardId | null>(null)
  const labels: Record<RunCardId, string> = { metrics: '训练指标', resources: 'GPU 资源', logs: '实时日志', lineage: '参数与数据血缘' }
  const saveLayout = () => { localStorage.setItem('hydrolab-run-layout', JSON.stringify(cards)); setEditing(false) }
  const dropCard = (target: RunCardId) => {
    if (!dragged || dragged === target) return
    setCards(current => { const next = current.filter(id => id !== dragged); next.splice(next.indexOf(target), 0, dragged); return next })
    setDragged(null)
  }
  const renderCard = (id: RunCardId) => {
    if (hidden.includes(id)) return null
    const handle = editing ? <div className="drag-handle"><GripVertical size={15}/><span>拖动调整</span><button onClick={() => setHidden(current => [...current, id])}>隐藏</button></div> : null
    if (id === 'metrics') return <section className="chart-panel metric-chart customizable-card">{handle}<div className="section-heading"><div><h2>训练指标</h2><p>每个 Epoch 聚合更新</p></div><select aria-label="选择指标"><option>Loss / NSE</option><option>KGE / RMSE</option></select></div><Sparkline values={chartValues} secondary={chartValues.map(v => Math.max(8, 95 - v))} /></section>
    if (id === 'resources') return <section className="resource-panel customizable-card">{handle}<div className="panel-topline"><span className="mono-label">GPU 0 / LIVE</span><Activity size={15} /></div><div className="resource-row"><span>利用率</span><b>93%</b></div><div className="usage-bar"><span style={{ width: '93%' }} /></div><div className="resource-row"><span>显存</span><b>20.6 / 24 GB</b></div><div className="usage-bar"><span style={{ width: '86%' }} /></div><div className="resource-meta"><span>68°C</span><span>289 W</span><span>14.2 it/s</span></div></section>
    if (id === 'logs') return <section className="log-panel customizable-card">{handle}<div className="log-heading"><div><ChevronDown size={16} /><b>实时训练日志</b><span>最后更新 2 秒前</span></div><span className="live-indicator">LIVE</span></div><pre><span>15:08:31</span> Epoch 36/50 · batch 184/216 · loss=0.0832 · lr=0.0005{`\n`}<span>15:08:33</span> Epoch 36/50 · batch 185/216 · loss=0.0819 · gpu_mem=20.6GB{`\n`}<span>15:08:35</span> Evaluating validation basins 18/33 · NSE=0.846 · KGE=0.919{`\n`}<em>15:08:37 Waiting for next progress event...</em></pre></section>
    return <section className="lineage-panel customizable-card">{handle}<div><span className="mono-label">EXPERIMENT LINEAGE</span><h2>参数与数据血缘</h2></div><div className="lineage graph"><span><Database size={15} />北江 v3</span><ChevronRight /><span><FileCode2 size={15} />KG-MoE-MS<br/>commit 8fc2a1</span><ChevronRight /><span><Layers3 size={15} />CAMELS Best<br/>epoch 42</span><ChevronRight /><span className="current"><FlaskConical size={15} />RUN-042</span></div></section>
  }
  return <div className="page-stack">
    <header className="run-heading"><button className="icon-button" onClick={back} aria-label="返回运行中心"><ArrowLeft size={18} /></button><div><p className="eyebrow">RUN-042 / FINETUNE</p><h1>Top-30 相似流域微调</h1><p>KG-MoE-MS · CAMELS × 北江 v3 · GPU 0</p></div><div className="run-actions"><button className="button ghost" onClick={() => editing ? saveLayout() : setEditing(true)}><SlidersHorizontal size={15}/>{editing ? '保存布局' : '调整布局'}</button><button className="button secondary"><CircleStop size={15} />停止任务</button><button className="button primary"><Play size={15} />重新运行</button></div></header>
    {editing && <section className="layout-toolbar"><div><b>个人布局</b><span>拖动卡片改变顺序，隐藏的模块可随时恢复。</span></div>{hidden.map(id => <button key={id} onClick={() => setHidden(current => current.filter(item => item !== id))}>恢复「{labels[id]}」</button>)}<button onClick={() => { setCards(defaultCards); setHidden([]) }}>恢复默认</button></section>}
    <section className="stage-track">{['准备环境', '准备数据', '模型训练', '评估', '绘图', '上传产物'].map((stage, i) => <div className={i < 2 ? 'done' : i === 2 ? 'active' : ''} key={stage}><span>{i < 2 ? <Check size={13} /> : i + 1}</span><b>{stage}</b>{i < 5 && <i />}</div>)}</section>
    <section className="run-kpis"><article><span className="mono-label">EPOCH</span><strong>36 / 50</strong><div className="usage-bar"><span style={{ width: '72%' }} /></div></article><article><span className="mono-label">TRAIN LOSS</span><strong>0.0832</strong><small>过去 5 Epoch -8.2%</small></article><article><span className="mono-label">VAL NSE</span><strong>0.846</strong><small>当前最佳 0.851</small></article><article><span className="mono-label">ETA</span><strong>18m 24s</strong><small>已运行 2h 30m</small></article></section>
    <div className={`custom-layout ${editing ? 'editing' : ''}`}>{cards.map(id => <div className={`card-slot ${id}`} draggable={editing} onDragStart={() => setDragged(id)} onDragOver={event => event.preventDefault()} onDrop={() => dropCard(id)} key={id}>{renderCard(id)}</div>)}</div>
  </div>
}

function ParameterEditor() {
  const [query, setQuery] = useState('')
  const [parameters, setParameters] = useState<ExperimentParameter[]>([
    { id: 1, name: 'epochs', label: 'Epochs', type: 'integer', value: '50', mapping: '--epochs ${value}' },
    { id: 2, name: 'batch_size', label: 'Batch Size', type: 'integer', value: '128', mapping: '--batch-size ${value}' },
    { id: 3, name: 'learning_rate', label: 'Learning Rate', type: 'number', value: '0.0005', mapping: '--learning-rate ${value}' },
    { id: 4, name: 'hidden_size', label: 'Hidden Size', type: 'integer', value: '128', mapping: 'model.hidden_size' },
    { id: 5, name: 'seq_length', label: 'Sequence Length', type: 'integer', value: '365', mapping: 'data.seq_length' },
    { id: 6, name: 'seed', label: '随机种子', type: 'integer', value: '42', mapping: '--seed ${value}' },
  ])
  const update = (id: number, patch: Partial<ExperimentParameter>) => setParameters(items => items.map(item => item.id === id ? { ...item, ...patch } : item))
  const add = () => setParameters(items => [...items, { id: Date.now(), name: 'custom_parameter', label: '自定义参数', type: 'string', value: '', mapping: '--custom-parameter ${value}', custom: true }])
  return <div className="parameter-editor"><div className="parameter-tools"><div className="tree-search"><Search size={14}/><input value={query} onChange={event=>setQuery(event.target.value)} placeholder="搜索超参数"/></div><button className="button secondary" onClick={add}><Plus size={14}/>增加超参数</button><button className="button ghost">恢复模板默认值</button></div><div className="parameter-header"><span>参数</span><span>类型</span><span>当前值</span><span>传递映射</span><span/></div>{parameters.filter(item => `${item.name}${item.label}`.toLowerCase().includes(query.toLowerCase())).map(item=><div className="parameter-row" key={item.id}><div><input value={item.label} onChange={event=>update(item.id,{label:event.target.value})}/><code>{item.name}</code></div><select value={item.type} onChange={event=>update(item.id,{type:event.target.value as ExperimentParameter['type']})}><option value="integer">整数</option><option value="number">浮点</option><option value="boolean">布尔</option><option value="enum">枚举</option><option value="string">字符串</option></select><input value={item.value} onChange={event=>update(item.id,{value:event.target.value})}/><input value={item.mapping} onChange={event=>update(item.id,{mapping:event.target.value})}/><button className="icon-button" disabled={!item.custom} onClick={()=>setParameters(items=>items.filter(p=>p.id!==item.id))} title={item.custom?'删除自定义参数':'模板参数不可删除'}><Trash2 size={14}/></button></div>)}<div className="parameter-foot"><span>{parameters.length} 个参数 · 其中 {parameters.filter(item=>item.custom).length} 个自定义</span><button className="button secondary">另存为参数预设</button></div></div>
}

function AdvancedExperimentForm() {
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({ source: true, training: true, runtime: false, outputs: false })
  const sections = [
    { id: 'source', title: '代码与数据', summary: 'KG-MoE-MS · 北江目标流域 v3', fields: [['模型代码', 'KG-MoE-MS · 8fc2a1'], ['数据版本', '北江目标流域 · v3']] },
    { id: 'training', title: '训练与权重', summary: 'finetune · CAMELS Best', fields: [['运行模式', '跨数据集微调'], ['初始 Checkpoint', 'CAMELS Best · epoch 42']] },
    { id: 'runtime', title: '参数与运行资源', summary: '6 个参数 · auto GPU', fields: [] },
    { id: 'outputs', title: '输出与进度协议', summary: 'JSONL · 标准输出目录', fields: [['进度协议', 'JSONL Schema v1'], ['产物目录', '/work/output']] },
  ]
  return <div className="advanced-form">{sections.map(section => <section key={section.id}><button className="advanced-section-head" onClick={() => setOpenSections(current => ({ ...current, [section.id]: !current[section.id] }))}><ChevronDown className={!openSections[section.id] ? 'collapsed' : ''} size={16}/><div><b>{section.title}</b><span>{section.summary}</span></div></button>{openSections[section.id] && (section.id === 'runtime' ? <div className="advanced-parameters"><ParameterEditor/><div className="parameter-grid runtime-fields"><label>运行环境<select><option>PyTorch 2.4 · CUDA 12.4 · env-v3</option><option>PyTorch 2.2 · CUDA 12.1 · env-v2</option></select></label><label>GPU 资源<select><option>自动分配单张 GPU</option></select></label></div></div> : <div className="advanced-fields">{section.fields.map(([label,value]) => <label key={label}>{label}<input defaultValue={value}/></label>)}</div>)}</section>)}</div>
}

function ExperimentWizard({ close }: { close: () => void }) {
  const [step, setStep] = useState(1)
  const [createMode, setCreateMode] = useState<'wizard' | 'advanced'>('wizard')
  const steps = ['选择代码', '选择数据', '训练方式', '配置参数', '确认提交']
  return <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="创建实验"><div className="wizard-modal"><header><div><span className="mono-label">NEW EXPERIMENT</span><h2>创建训练实验</h2><p>向导与高级模式共享同一份实验草稿。</p></div><div className="mode-switch"><button className={createMode === 'wizard' ? 'active' : ''} onClick={() => setCreateMode('wizard')}>分步向导</button><button className={createMode === 'advanced' ? 'active' : ''} onClick={() => setCreateMode('advanced')}>高级配置</button><button className="icon-button" onClick={close} aria-label="关闭"><X size={18} /></button></div></header>{createMode === 'advanced' ? <div className="advanced-body"><div className="advanced-intro"><span className="step-counter">ADVANCED CONFIG</span><h3>完整实验配置</h3><p>按区域展开并一次完成全部配置。字段与分步向导保持同步。</p></div><AdvancedExperimentForm /></div> : <div className="wizard-body"><aside>{steps.map((label, i) => <button className={step === i + 1 ? 'active' : step > i + 1 ? 'done' : ''} onClick={() => setStep(i + 1)} key={label}><span>{step > i + 1 ? <Check size={13} /> : i + 1}</span><div><b>{label}</b><small>{['模型与代码版本','目标数据版本','初始化与 Checkpoint','超参数与资源','检查后进入队列'][i]}</small></div></button>)}</aside><main><span className="step-counter">STEP {step} / 5</span><h3>{steps[step - 1]}</h3>{step === 1 && <div className="selection-list"><button className="selected"><FileCode2 /><div><b>KG-MoE-MS</b><span>commit 8fc2a1 · PyTorch 2.4 · CUDA 12.4</span></div><Check /></button><button><FileCode2 /><div><b>GRU Baseline</b><span>commit e921d0 · PyTorch 2.4 · CUDA 12.4</span></div></button><button><FileCode2 /><div><b>NeuralHydrology</b><span>v1.12.0 · 标准适配器</span></div></button></div>}{step === 2 && <div className="form-stack"><label>目标数据版本<select><option>北江目标流域 · v3</option><option>CAMELS-US · v2</option></select></label><div className="data-preview"><Database /><div><b>北江目标流域 v3</b><span>33 个流域 · 2012—2022 · 1 hour</span></div><StatusBadge status="已完成" /></div></div>}{step === 3 && <div className="mode-grid">{[['scratch','从头训练'],['resume','断点续训'],['finetune','跨数据集微调'],['evaluate','仅评估']].map(([id,label],i) => <button className={i === 2 ? 'selected' : ''} key={id}><b>{label}</b><span>{id}</span>{i === 2 && <Check />}</button>)}</div>}{step === 4 && <div><ParameterEditor/><div className="parameter-grid runtime-fields"><label>GPU 资源<select><option>自动分配单张 GPU</option></select></label><label>优先级<select><option>普通</option></select></label></div></div>}{step === 5 && <div className="review-list"><div><span>模型代码</span><b>KG-MoE-MS · 8fc2a1</b></div><div><span>数据版本</span><b>北江目标流域 · v3</b></div><div><span>训练方式</span><b>跨数据集微调</b></div><div><span>初始权重</span><b>CAMELS Best · epoch 42</b></div><div><span>资源估算</span><b>单 GPU · 约 3 小时</b></div></div>}</main></div>}<footer><button className="button secondary" onClick={createMode === 'wizard' && step > 1 ? () => setStep(step - 1) : close}>{createMode === 'wizard' && step > 1 ? '返回上一步' : '暂不创建'}</button><button className="button primary" onClick={createMode === 'wizard' && step < 5 ? () => setStep(step + 1) : close}>{createMode === 'wizard' && step < 5 ? '继续下一步' : '创建并进入队列'}<ChevronRight size={15} /></button></footer></div></div>
}

function ApiCatalogPage({ section }: { section: 'datasets' | 'code' | 'experiments' | 'checkpoints' | 'results' | 'environments' }) {
  const [items, setItems] = useState<ApiCatalogItem[]>([])
  const [draftName, setDraftName] = useState('')
  const [commandMessage, setCommandMessage] = useState<string | null>(null)
  const [operationMessage, setOperationMessage] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const config = {
    datasets: ['DATA', '数据', '不可变数据版本与字段映射'],
    code: ['MODEL CODE', '模型代码 / 模板', '代码快照与可执行实验模板'],
    experiments: ['EXPERIMENTS', '实验', '冻结配置与独立 Run 历史'],
    checkpoints: ['CHECKPOINTS', 'Checkpoint', '可复用模型权重与兼容性结论'],
    results: ['RESULTS', '结果与对比', '成功 Run 的指标、产物与可比性'],
    environments: ['RUNTIME ASSETS', '运行环境', '版本化镜像与依赖锁定'],
  }[section]
  const load = async () => {
    setLoading(true); setError(null)
    try {
      await ensureDevSession()
      await seedDemo()
      const loadedItems = await getRealSection(section)
      setItems(loadedItems)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '无法连接本地 API')
    } finally { setLoading(false) }
  }
  useEffect(() => { void load() }, [section])
  const runOperation = async (operation: 'checkpoint' | 'metrics' | 'plot' | 'export' | 'compare') => {
    setError(null); setOperationMessage(null); setSubmitting(true)
    try {
      await ensureDevSession()
      if (operation === 'checkpoint') {
        const checkpoint = (await listCheckpoints())[0]
        if (!checkpoint) throw new Error('没有可校验的 Checkpoint')
        const report = await checkCheckpoint(checkpoint.id, 'RESUME', { ...checkpoint.source_config, feature_names: ['precip'], target_names: ['flow'], model_signature: checkpoint.model_signature, scaler_signature: 'scaler-v1' })
        setOperationMessage(`兼容性校验完成：${report.status}${report.blockers.length ? ` · ${report.blockers.join('；')}` : ''}`)
      } else {
        const ids = (await listResults()).map(result => result.id)
        if (!ids.length) throw new Error('没有可操作的结果')
        if (operation === 'metrics') {
          const metrics = await listMetrics(ids[0])
          setOperationMessage(`已读取 ${metrics.length} 条指标：${metrics.map(item => `${item.name}=${item.value}`).join('，')}`)
        } else if (operation === 'plot') {
          const plot = await createPlot([ids[0]])
          setOperationMessage(`绘图规格已创建：${plot.id}`)
        } else if (operation === 'export') {
          const exported = await createExport([ids[0]])
          setOperationMessage(`导出清单已创建：${exported.id}`)
        } else if (ids.length < 2) {
          setOperationMessage('结果对比至少需要 2 个同一冻结数据版本的结果；当前只有 1 个。')
        } else {
          const comparison = await compareResults(ids.slice(0, 5))
          setOperationMessage(`结果对比完成：${Object.keys(comparison.metrics).length} 个结果，基线 ${comparison.baseline_result_id.slice(0, 8)}`)
        }
      }
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : cause instanceof Error ? cause.message : '操作请求失败')
    } finally { setSubmitting(false) }
  }
  const create = async () => {
    if (!draftName.trim()) {
      setError('请先填写名称再创建')
      return
    }
    setCommandMessage(null); setError(null); setSubmitting(true)
    try {
      await ensureDevSession()
      if (section === 'datasets') {
        const created = await createDataset(draftName.trim(), '通过前端真实 API 创建')
        setCommandMessage(`后端已创建数据集「${draftName.trim()}」· ${created.id}`)
      } else {
        const draft = await createDraft(draftName.trim(), '通过前端真实 API 创建')
        const configuredDraft = (await listDrafts()).find(item => item.status === 'SUBMITTED' && item.dataset_version_id && item.code_version_id && item.template_version_id && item.environment_version_id)
        if (!configuredDraft) throw new Error('未找到可复用的完整联调配置')
        await updateDraft(draft.id, {
          dataset_version_id: configuredDraft.dataset_version_id,
          code_version_id: configuredDraft.code_version_id,
          template_version_id: configuredDraft.template_version_id,
          environment_version_id: configuredDraft.environment_version_id,
          parameter_values: { ...configuredDraft.parameter_values, epochs: 50 },
        })
        const submitted = await submitDraft(draft.id)
        setCommandMessage(`实验「${submitted.experiment.name}」已提交 · Run ${submitted.run.id.slice(0, 8)} 已进入 ${submitted.run.status} 队列`)
      }
      setDraftName('')
      await load()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '创建请求失败')
    } finally { setSubmitting(false) }
  }
  return <div className="page-stack">
    <header className="page-heading"><div><p className="eyebrow">{config[0]}</p><h1>{config[1]}</h1><p>{config[2]} · 当前内容来自 FastAPI 本地 Fake/InMemory 工作区。</p></div><button className="button secondary" onClick={() => void load()} disabled={loading}><RefreshCw size={15}/>{loading ? '加载中' : '刷新'}</button></header>
    {error && <p className="error-notice">API 联调错误：{error}</p>}
    {commandMessage && <p className="onboarding"><b>{commandMessage}</b></p>}
    {operationMessage && <p className="onboarding"><b>{operationMessage}</b></p>}
    {section === 'checkpoints' && <section className="section-block"><div className="section-heading"><div><h2>复用兼容性校验</h2><p>使用当前 Checkpoint 的冻结来源配置执行 Resume 校验。</p></div><button className="button primary" onClick={() => void runOperation('checkpoint')} disabled={submitting}>{submitting ? '正在校验…' : '校验 Resume 兼容性'}</button></div></section>}
    {section === 'results' && <section className="section-block"><div className="section-heading"><div><h2>结果操作</h2><p>以下操作调用正式指标、绘图规格、导出清单与结果对比 API。</p></div><div className="page-actions"><button className="button secondary" onClick={() => void runOperation('metrics')} disabled={submitting}>读取指标</button><button className="button secondary" onClick={() => void runOperation('plot')} disabled={submitting}>创建绘图</button><button className="button secondary" onClick={() => void runOperation('export')} disabled={submitting}>创建导出</button><button className="button primary" onClick={() => void runOperation('compare')} disabled={submitting}>比较结果</button></div></div></section>}
    {(section === 'datasets' || section === 'experiments') && <section className="section-block"><div className="form-stack"><label>{section === 'datasets' ? '新数据集名称' : '新实验名称'}<input value={draftName} onChange={event => setDraftName(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') void create() }} placeholder={section === 'datasets' ? '例如：北江新增观测 v4' : '例如：Top-30 参数试验'} /></label><button className="button primary" onClick={() => void create()} disabled={submitting}><Plus size={15}/>{submitting ? '正在提交…' : section === 'datasets' ? '创建数据集' : '创建并提交实验'}</button></div>{section === 'experiments' && <p className="form-hint">创建会自动复用已验证的版本化数据、代码、模板与环境配置，随后通过 PATCH 草稿和 submit API 进入队列。</p>}</section>}
    <section className="section-block"><div className="section-heading"><div><h2>{loading ? '正在加载后端资源…' : `共 ${items.length} 项`}</h2><p>受保护 API · Token 自动恢复 · 后端重启后可重新登录</p></div></div>
    <div className="asset-list">{items.map(item => <div key={item.id}><HardDrive size={16}/><span><b>{item.name}</b><small>{item.subtitle}</small></span><code>{item.metadata.version ?? item.metadata.nse ?? item.metadata.mode ?? item.metadata.runs ?? item.metadata.model_signature ?? '—'}</code><StatusBadge status={item.status === 'SUCCEEDED' || item.status === 'READY' || item.status === 'COMPATIBLE' ? '已完成' : item.status}/></div>)}{!loading && !items.length && <p>当前没有可访问资源。</p>}</div>
    </section>
  </div>
}

export default function App() {
  const [view, setView] = useState<View>('dashboard')
  const [wizardOpen, setWizardOpen] = useState(false)
  const [gpuOpen, setGpuOpen] = useState(false)
  const [datasetCreateOpen, setDatasetCreateOpen] = useState(false)
  const [resultDetailOpen, setResultDetailOpen] = useState(false)
  const [compareRuns,setCompareRuns]=useState<string[]>([])
  const [menuOpen, setMenuOpen] = useState(false)
  const [theme, setTheme] = useState<Theme>('system')
  const resolvedDark = useMemo(() => theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches), [theme])
  useEffect(() => { document.documentElement.classList.toggle('dark', resolvedDark) }, [resolvedDark])
  const cycleTheme = () => setTheme(t => t === 'system' ? 'light' : t === 'light' ? 'dark' : 'system')
  const ThemeIcon = theme === 'dark' ? Moon : theme === 'light' ? Sun : Settings
  return (
    <div className="app-shell">
      <aside className={`sidebar ${menuOpen ? 'open' : ''}`}>
        <div className="brand">
          <div className="brand-mark"><Activity size={18} /></div>
          <div><b>HydroLab</b><span>EXPERIMENT OS</span></div>
        </div>
        <nav>
          {navItems.map(({ id, label, icon: Icon }) => {
            const active = view === id || (view === 'run' && id === 'dashboard')
            return (
              <button key={id} className={active ? 'active' : ''} onClick={() => { setView(id); if (id === 'results') { setResultDetailOpen(false); setCompareRuns([]) } setMenuOpen(false) }}>
                <Icon size={17} />{label}
              </button>
            )
          })}
          <span className="nav-label">ACCOUNT</span>
          <button onClick={() => setView('permissions')} className={view==='permissions'?'active':''}><Settings size={17} />权限与分享</button>
          <button onClick={() => setView('environments')} className={view==='environments'?'active':''}><HardDrive size={17} />运行环境</button>
        </nav>
        <div className="sidebar-footer">
          <div className="server-health"><span /><div><b>服务运行正常</b><small>2 GPU · 3 队列任务</small></div></div>
          <button><div className="avatar">SZ</div><div><b>sunzhijun03</b><small>管理员</small></div><ChevronRight size={14} /></button>
        </div>
      </aside>
      {menuOpen && <button className="mobile-overlay" aria-label="关闭导航" onClick={() => setMenuOpen(false)} />}
      <main className="main-area">
        <div className="topbar">
          <button className="icon-button menu-button" onClick={() => setMenuOpen(true)} aria-label="打开导航"><Menu size={18} /></button>
          <div className="project-switcher"><span className="project-dot" /><b>水文时序实验平台</b><span className="flow-label">数据 → 实验 → 结果</span></div>
          <div className="top-actions">
            <span className="prototype-badge">交互原型 · 模拟数据</span>
            <button className="icon-button" onClick={cycleTheme} title={`主题：${theme}`} aria-label="切换明暗主题"><ThemeIcon size={17} /></button>
            <button className="icon-button" aria-label="设置"><Settings size={17} /></button>
          </div>
        </div>
        <div className="content-area">
          {view === 'dashboard' && <Dashboard openRun={() => setView('run')} openWizard={() => setWizardOpen(true)} openGpu={() => setGpuOpen(true)} />}
          {view === 'datasets' && <ApiCatalogPage section="datasets" />}
          {view === 'code' && <ApiCatalogPage section="code" />}
          {view === 'checkpoints' && <ApiCatalogPage section="checkpoints" />}
          {view === 'experiments' && <ApiCatalogPage section="experiments" />}
          {view === 'results' && <ApiCatalogPage section="results" />}
          {view === 'permissions' && <AssetAdminPage type="permissions" />}
          {view === 'environments' && <ApiCatalogPage section="environments" />}
          {view === 'run' && <RunDetail back={() => setView('dashboard')} />}
        </div>
      </main>
      {wizardOpen && <ExperimentWizard close={() => setWizardOpen(false)} />}
      {gpuOpen && <GpuDrawer close={() => setGpuOpen(false)} />}
      {datasetCreateOpen && <DatasetCreateModal close={() => setDatasetCreateOpen(false)} />}
    </div>
  )
}
