import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, cancelRealRun, checkCheckpoint, compareResults, confirmDatasetMapping, createCodeRepository, createDataset, createDatasetImport, createDraft, createExport, createPlot, createTemplate, createTemplateVersion, dispatchOutbox, ensureDevSession, fakeUploadDataset, getCurrentUser, getDatasetMapping, getRealSection, getRun, getRunCollection, getRunEvents, getRunResources, getRunStages, getRunLogs, getStoredUser, importCodeDirectory, importCodeGit, importCodeZip, ingestRunResult, listCheckpoints, listCodeImportRoots, listCodeRepositories, listCodeVersions, listDatasetVersions, listDatasets, listEnvironments, listEnvironmentVersions, listMetrics, listResults, listRuns, listTemplateVersions, listTemplates, login, logout, previewDirectoryImport, seedDemo, startRun, submitBatch, submitDraft, subscribeRunEvents, updateDraft } from './lib/api'
import type { ApiBatchSubmitItem, ApiCatalogItem, ApiCodeRepository, ApiCodeVersion, ApiComparison, ApiDatasetVersion, ApiDirectoryPreview, ApiEnvironment, ApiMappingItem, ApiMetric, ApiResourceSample, ApiResult, ApiRunCollection, ApiRunEvent, ApiRunLog, ApiRunStage, ApiRunSummary, ApiTemplateVersion, ApiUser } from './lib/api'
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
  GripVertical,
  HardDrive,
  Home,
  Layers3,
  Menu,
  Moon,
  Play,
  Plus,
  RefreshCw,
  Search,
  SlidersHorizontal,
  Settings,
  Sun,
  X,
} from 'lucide-react'

type View = 'dashboard' | 'datasets' | 'code' | 'experiments' | 'checkpoints' | 'results' | 'run' | 'permissions' | 'environments'
type Theme = 'light' | 'dark' | 'system'
type RunCardId = 'metrics' | 'resources' | 'logs' | 'lineage'

const navItems = [
  { id: 'dashboard' as const, label: '运行中心', icon: Home },
  { id: 'datasets' as const, label: '数据', icon: Database },
  { id: 'code' as const, label: '模型代码', icon: FileCode2 },
  { id: 'experiments' as const, label: '实验', icon: FlaskConical },
  { id: 'checkpoints' as const, label: 'Checkpoint', icon: Layers3 },
  { id: 'results' as const, label: '结果与对比', icon: BarChart3 },
]



const chartValues = [18, 31, 27, 45, 54, 49, 63, 69, 72, 78, 83, 86]

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
  const tone = (status === '运行中' || status === '准备中' || status === 'RUNNING' || status === 'PREPARING')
    ? 'running'
    : (status === '已完成' || status === 'SUCCEEDED' || status === 'READY' || status === 'COMPATIBLE')
      ? 'success'
      : (status === '失败' || status === 'FAILED') ? 'danger' : 'neutral'
  return <span className={`status-badge ${tone}`}><span className="status-dot" />{status}</span>
}

const runStatusLabel: Record<string, string> = { QUEUED: '等待中', PREPARING: '准备中', RUNNING: '运行中', SUCCEEDED: '已完成', FAILED: '失败', CANCELLED: '已取消' }

function formatRunTime(value: string | null | undefined) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function Dashboard({ openRun, openWizard, openBatch, openGpu }: { openRun: (runId: string) => void; openWizard: () => void; openBatch: () => void; openGpu: () => void }) {
  const [onboardingOpen, setOnboardingOpen] = useState(true)
  const [apiRuns, setApiRuns] = useState<ApiRunSummary[]>([])
  const [bestNse, setBestNse] = useState<{ value: number; name: string } | null>(null)
  const [workspaceError, setWorkspaceError] = useState<string | null>(null)
  const [loadingWorkspace, setLoadingWorkspace] = useState(true)
  const [message, setMessage] = useState<string | null>(null)
  const loadWorkspace = async () => {
    setLoadingWorkspace(true)
    setWorkspaceError(null)
    setMessage(null)
    try {
      await ensureDevSession()
      const runs = await listRuns()
      setApiRuns([...runs].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()))
      try {
        const results = await listResults()
        let best: { value: number; name: string } | null = null
        for (const result of results) {
          try {
            const metrics = await listMetrics(result.id)
            const nse = metrics.find(item => item.name.toUpperCase() === 'NSE')
            if (nse && (!best || nse.value > best.value)) best = { value: nse.value, name: result.id.slice(0, 8) }
          } catch { /* 单个结果读取失败不阻塞整体 */ }
        }
        setBestNse(best)
      } catch { /* 结果统计失败不阻塞运行中心 */ }
    } catch (error) {
      setWorkspaceError(error instanceof ApiError ? error.message : '无法连接本地 API')
    } finally {
      setLoadingWorkspace(false)
    }
  }
  useEffect(() => { void loadWorkspace() }, [])
  const runningCount = apiRuns.filter(run => run.status === 'RUNNING' || run.status === 'PREPARING').length
  const queuedCount = apiRuns.filter(run => run.status === 'QUEUED').length
  const controlRun = async (runId: string, action: 'start' | 'cancel') => {
    try {
      await ensureDevSession()
      if (action === 'start') {
        await startRun(runId, 1)
        setMessage('Run 已启动，调度器将为其分配 GPU。')
      } else {
        await cancelRealRun(runId)
        setMessage('Run 已取消，GPU 租约已释放。')
      }
      await loadWorkspace()
    } catch (error) {
      setWorkspaceError(error instanceof ApiError ? error.message : 'Run 操作失败')
    }
  }
  const dispatch = async () => {
    try {
      await ensureDevSession()
      const result = await dispatchOutbox()
      setMessage(result.dispatched > 0 ? `已将 ${result.dispatched} 个待执行 Run 投递到队列。` : '当前没有待投递的 Run。')
      await loadWorkspace()
    } catch (error) {
      setWorkspaceError(error instanceof ApiError ? error.message : '投递队列失败')
    }
  }
  return (
    <div className="page-stack">
      <header className="page-heading">
        <div><p className="eyebrow">WORKSPACE / FLOOD-FORECAST</p><h1>运行中心</h1><p>先处理正在运行的实验，再检查等待中的任务。</p></div>
        <div className="page-actions"><button className="button secondary" onClick={openBatch}><Plus size={16} />批量提交</button><button className="button primary" onClick={openWizard}><Plus size={16} />创建实验</button></div>
      </header>

      {onboardingOpen && <section className="onboarding"><div><span className="mono-label">GETTING STARTED / 3 OF 5</span><b>完成首个可复现实验</b><p><span className="done">导入数据</span><span className="done">导入代码</span><span className="done">确认实验模板</span><span>创建实验</span><span>启动首个 Run</span></p></div><button className="button ghost" onClick={() => setOnboardingOpen(false)}>暂时隐藏</button></section>}
      <section className="run-overview">
        <div className="run-overview-copy"><span className="mono-label">ACTIVE QUEUE</span><strong>{runningCount} 项运行中 · {queuedCount} 项等待</strong><p>来自 FastAPI 真实 Run 状态机与事件流</p></div>
        <button className="gpu-compact" onClick={openGpu} aria-label="查看 GPU 使用详情"><Cpu size={16} /><span><b>{runningCount} 运行中</b><small>实时事件驱动</small></span><span><b>{queuedCount} 等待</b><small>FIFO 双卡调度</small></span><ChevronRight size={16} /></button>
      </section>

      <section className="section-block">
        <div className="section-heading"><div><h2>当前训练任务</h2><p>当前用户的全部 Run（提交时间倒序），状态来自后端事件流</p></div><div className="page-actions"><button className="button ghost" onClick={() => void dispatch()} disabled={loadingWorkspace}><RefreshCw size={14} />投递队列</button><button className="button ghost" onClick={() => void loadWorkspace()} disabled={loadingWorkspace}><RefreshCw size={14} />{loadingWorkspace ? '加载中' : '刷新状态'}</button></div></div>
        {message && <p className="onboarding"><b>{message}</b></p>}
        {workspaceError && <p className="error-notice">API 联调错误：{workspaceError}</p>}
        <div className="run-table-wrap">
          <table className="run-table">
            <thead><tr><th>任务</th><th>命令 / 参数</th><th>状态</th><th>创建时间</th><th /></tr></thead>
            <tbody>{apiRuns.map(run => (
              <tr key={run.id} onClick={() => openRun(run.id)} className="clickable-row">
                <td><span className="run-id">{run.id.slice(0, 8)}</span><b>{run.experiment_name}</b></td>
                <td><span>{run.argv.join(' ') || '—'}</span><small>{Object.keys(run.parameters).length ? Object.entries(run.parameters).map(([key, value]) => `${key}=${String(value)}`).join(' · ') : '默认参数'}</small></td>
                <td><StatusBadge status={runStatusLabel[run.status] ?? run.status} /></td>
                <td className="mono">{formatRunTime(run.created_at)}</td>
                <td onClick={event => event.stopPropagation()}>{run.status === 'QUEUED' && <button className="button ghost" onClick={() => void controlRun(run.id, 'start')}>启动</button>}{(run.status === 'QUEUED' || run.status === 'RUNNING' || run.status === 'PREPARING') && <button className="button ghost" onClick={() => void controlRun(run.id, 'cancel')}>取消</button>}</td>
              </tr>
            ))}{!loadingWorkspace && apiRuns.length === 0 && <tr><td colSpan={5}>暂无后端 Run；请先在“实验”页创建并提交实验。</td></tr>}</tbody>
          </table>
        </div>
      </section>

      <section className="summary-grid">
        <article><span className="mono-label">RECENT BEST</span><strong>{bestNse ? bestNse.value.toFixed(3) : '—'}</strong><p>NSE{bestNse ? ` · Result ${bestNse.name}` : ' · 尚无结果'}</p>{bestNse && <Sparkline values={chartValues} />}</article>
        <article><span className="mono-label">QUEUE</span><strong>{runningCount + queuedCount}</strong><p>运行中 + 等待中的 Run 总数</p><div className="mini-bars">{[40, 65, 48, 80, 55, 91, 72].map((v, i) => <i key={i} style={{ height: `${v}%` }} />)}</div></article>
        <article className="activity-list"><span className="mono-label">RECENT RUNS</span>{apiRuns.slice(0, 4).map(run => <p key={run.id}><Check size={14} />{run.experiment_name}<small>{runStatusLabel[run.status] ?? run.status} · {formatRunTime(run.created_at)}</small></p>)}</article>
      </section>
    </div>
  )
}





function AssetAdminPage({ type }: { type:'permissions'|'environments' }) {
  const [environments, setEnvironments] = useState<ApiEnvironment[]>([])
  const [versionsByEnvironment, setVersionsByEnvironment] = useState<Record<string, Array<{ id: string; version_no: number; status: string }>>>({})
  const [loading, setLoading] = useState(type === 'environments')
  useEffect(() => {
    if (type !== 'environments') return
    setLoading(true)
    void (async () => {
      try {
        const items = await listEnvironments()
        setEnvironments(items)
        const versions: Record<string, Array<{ id: string; version_no: number; status: string }>> = {}
        for (const item of items) {
          try { versions[item.id] = await listEnvironmentVersions(item.id) } catch { versions[item.id] = [] }
        }
        setVersionsByEnvironment(versions)
      } catch { /* 环境加载失败不阻塞页面 */ } finally { setLoading(false) }
    })()
  }, [type])
  return <div className="page-stack"><header className="page-heading"><div><p className="eyebrow">{type==='permissions'?'ACCESS CONTROL':'RUNTIME ASSETS'}</p><h1>{type==='permissions'?'权限与分享':'运行环境'}</h1><p>{type==='permissions'?'集中管理所有资源的只读分享链接。':'管理可供代码和实验选择的版本化运行环境。'}</p></div><button className="button primary"><Plus size={15}/>{type==='permissions'?'创建分享':'创建环境'}</button></header><section className="section-block">{type === 'environments' ? <div className="asset-list">{loading ? <p className="quiet">正在加载运行环境…</p> : environments.map(item => <div key={item.id}><HardDrive size={16}/><span><b>{item.name}</b><small>{item.description || '—'}</small></span><code>{versionsByEnvironment[item.id]?.length ?? 0} 个版本</code><button className="button ghost">管理</button></div>)}{!loading && !environments.length && <p className="quiet">暂无运行环境。</p>}</div> : <div className="asset-list">{[['北江目标流域 v3','有效至 09-05','尚未访问'],['Top-30 Best','永久有效','已访问 4 次']].map(row=><div key={row[0]}><HardDrive size={16}/><span><b>{row[0]}</b><small>{row[1]}</small></span><code>{row[2]}</code><button className="button ghost">管理</button></div>)}</div>}</section></div>
}



function GpuDrawer({ close }: { close: () => void }) {
  const [runs, setRuns] = useState<ApiRunSummary[]>([])
  const [resources, setResources] = useState<Record<string, ApiResourceSample[]>>({})
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let cancelled = false
    void (async () => {
      setError(null)
      try {
        await ensureDevSession()
        const loaded = await listRuns()
        if (cancelled) return
        setRuns(loaded)
        const running = loaded.filter(run => run.status === 'RUNNING' || run.status === 'PREPARING')
        const entries: Record<string, ApiResourceSample[]> = {}
        for (const run of running) {
          try { entries[run.id] = await getRunResources(run.id) } catch { entries[run.id] = [] }
        }
        if (!cancelled) setResources(entries)
      } catch (cause) {
        if (!cancelled) setError(cause instanceof ApiError ? cause.message : 'GPU 抽屉加载失败')
      }
    })()
    return () => { cancelled = true }
  }, [])
  const running = runs.filter(run => run.status === 'RUNNING' || run.status === 'PREPARING')
  const queued = runs.filter(run => run.status === 'QUEUED')
  const latest = (runId: string) => {
    const samples = resources[runId] ?? []
    return samples[samples.length - 1] ?? null
  }
  return <div className="drawer-backdrop" onClick={close}><aside className="gpu-drawer" onClick={event => event.stopPropagation()}><header><div><span className="mono-label">COMPUTE STATUS</span><h2>GPU 与队列</h2><p>真实 Run 事件驱动 · FIFO 双卡调度</p></div><button className="icon-button" onClick={close} aria-label="关闭 GPU 详情"><X size={18}/></button></header>{error && <p className="error-notice">GPU 抽屉错误：{error}</p>}{running.length ? running.map(run => { const sample = latest(run.id); return <section className="drawer-gpu" key={run.id}><div className="panel-topline"><b>{sample && Number.isFinite(sample.gpu_index) ? `GPU ${sample.gpu_index}` : 'GPU 待分配'} · {run.experiment_name}</b><StatusBadge status={runStatusLabel[run.status] ?? run.status}/></div>{sample ? <><div className="drawer-metric"><span>利用率</span><strong>{sample.utilization_percent}%</strong></div><div className="usage-bar"><span style={{width:`${sample.utilization_percent}%`}}/></div><div className="drawer-metric"><span>显存</span><strong>{sample.memory_used_mb} / {sample.memory_total_mb} MB</strong></div><div className="usage-bar"><span style={{width:`${Math.round(sample.memory_used_mb / sample.memory_total_mb * 100)}%`}}/></div><div className="resource-meta"><span>GPU {sample.gpu_index}</span><span>{sample.sampled_at ? formatRunTime(sample.sampled_at) : '—'}</span></div></> : <p className="quiet">暂无资源采样；调度器尚未上报利用率和显存。</p>}<dl><div><dt>Run</dt><dd>{run.id.slice(0, 8)}</dd></div><div><dt>命令</dt><dd>{run.argv.join(' ') || '—'}</dd></div></dl></section> }) : <p className="quiet" style={{ padding: '18px' }}>当前没有运行中的 Run。</p>}<section className="drawer-queue"><div className="panel-topline"><b>等待队列</b><span>{queued.length} 项</span></div>{queued.map((run, index) => <p key={run.id}><span>{index + 1}</span>{run.experiment_name}<small>{run.id.slice(0, 8)} · {formatRunTime(run.created_at)}</small></p>)}{!queued.length && <p className="quiet">队列为空。</p>}</section></aside></div>
}


function PlotBuilder({ resultIds, onCreated, close }: { resultIds: string[]; onCreated?: (info: { plot_id: string; artifact_count: number }) => void; close: () => void }) {
  const [plotType, setPlotType] = useState('grouped_metrics')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const plotTypes = [
    { id: 'grouped_metrics', label: '分组指标对比' },
    { id: 'horizon_lines', label: '预测时域过程线' },
    { id: 'nse_kge_panels', label: 'NSE/KGE 面板' },
    { id: 'basin_metric_distribution', label: '流域指标分布' },
  ]
  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      await ensureDevSession()
      const result = await createPlot(resultIds, plotType as 'grouped_metrics' | 'horizon_lines' | 'nse_kge_panels' | 'basin_metric_distribution', {})
      onCreated?.({ plot_id: result.plot.id, artifact_count: result.artifacts.length })
      close()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : cause instanceof Error ? cause.message : '创建绘图失败')
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="modal-backdrop">
      <div className="plot-modal">
        <header>
          <div>
            <span className="mono-label">NEW PLOT</span>
            <h2>添加可复现图表</h2>
            <p>选择绘图类型后，后端按冻结指标生成 SVG 产物并登记为 Plot。</p>
          </div>
          <button className="icon-button" onClick={close}><X size={18} /></button>
        </header>
        <main>
          <div className="plot-form">
            <label>
              图表类型
              <select value={plotType} onChange={event => setPlotType(event.target.value)}>
                {plotTypes.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
              </select>
            </label>
          </div>
          <p className="quiet" style={{ marginTop: 12 }}>
            将使用 {resultIds.length} 个结果（{resultIds.map(id => id.slice(0, 8)).join('、')}）生成图表。
          </p>
          {error && <p className="error-notice">绘图错误：{error}</p>}
        </main>
        <footer>
          <button className="button secondary" onClick={close}>取消</button>
          <button className="button primary" onClick={() => void submit()} disabled={busy}>
            {busy ? '正在生成…' : '确认生成图表'}
          </button>
        </footer>
      </div>
    </div>
  )
}

function ExportPicker({ resultIds, onCreated, close }: { resultIds: string[]; onCreated?: (info: { export_id: string; size_bytes: number; files: string[] }) => void; close: () => void }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      await ensureDevSession()
      const exported = await createExport(resultIds, [])
      onCreated?.({ export_id: exported.id, size_bytes: exported.manifest.size_bytes, files: exported.manifest.files })
      close()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : cause instanceof Error ? cause.message : '创建导出失败')
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="modal-backdrop">
      <div className="export-modal">
        <header>
          <div>
            <span className="mono-label">EXPORT RESULT</span>
            <h2>导出结果包</h2>
            <p>后端打包所选结果的指标 CSV、产物清单与可复现脚本（zip bundle）。</p>
          </div>
          <button className="icon-button" onClick={close}><X size={18} /></button>
        </header>
        <main>
          <p className="quiet">将导出 {resultIds.length} 个结果的指标与关联产物；object_key / sha256 / size 由后端登记到 ExportManifest。</p>
          {error && <p className="error-notice">导出错误：{error}</p>}
        </main>
        <footer>
          <button className="button secondary" onClick={close}>取消</button>
          <button className="button primary" onClick={() => void submit()} disabled={busy}>
            <Download size={15} />
            {busy ? '正在打包…' : '生成下载包'}
          </button>
        </footer>
      </div>
    </div>
  )
}


function ResultDetail({ result, back, onChanged }: { result: ApiResult; back: () => void; onChanged?: () => void }) {
  const [tab, setTab] = useState<'overview' | 'basins' | 'assets'>('overview')
  const [metrics, setMetrics] = useState<ApiMetric[]>([])
  const [collection, setCollection] = useState<ApiRunCollection | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [exportOpen, setExportOpen] = useState(false)
  const [plotOpen, setPlotOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    void (async () => {
      try {
        const [metricList, report] = await Promise.all([listMetrics(result.id), getRunCollection(result.run_id)])
        if (!cancelled) { setMetrics(metricList); setCollection(report) }
      } catch (cause) {
        if (!cancelled) setError(cause instanceof ApiError ? cause.message : cause instanceof Error ? cause.message : '加载结果详情失败')
      }
      finally { if (!cancelled) setLoading(false) }
    })()
    return () => { cancelled = true }
  }, [result.id, result.run_id])
  const global = metrics.filter(item => !item.basin_id && !item.event_id)
  const byBasin = metrics.filter(item => !!item.basin_id)
  const shown = global.slice(0, 4)
  return (
    <div className="page-stack">
      <header className="page-heading result-detail-heading"><button className="icon-button" onClick={back} aria-label="返回结果列表"><ArrowLeft size={18}/></button><div><p className="eyebrow">RESULT / {result.id.slice(0, 8)}</p><h1>Result {result.id.slice(0, 8)}</h1><p>Run {result.run_id.slice(0, 8)} · 冻结数据版本 {result.dataset_version_id.slice(0, 8)} · {formatRunTime(result.created_at)}</p></div><div className="page-actions"><button className="button secondary" onClick={() => setPlotOpen(true)}><Plus size={15}/>添加图表</button><button className="button primary" onClick={() => setExportOpen(true)}><Download size={16}/>选择文件导出</button></div></header>
      {message && <p className="onboarding"><b>{message}</b></p>}
      {error && <p className="error-notice">结果错误：{error}</p>}
      <div className="result-tabs"><button className={tab === 'overview' ? 'active' : ''} onClick={() => setTab('overview')}>结果总览</button><button className={tab === 'basins' ? 'active' : ''} onClick={() => setTab('basins')}>逐流域分析</button><button className={tab === 'assets' ? 'active' : ''} onClick={() => setTab('assets')}>结果资产</button></div>
      {tab === 'overview' && <>
        <section className="metric-cards">{loading ? <p className="quiet">正在加载指标…</p> : shown.length ? shown.map(item => <article key={`${item.name}-${item.split}`}><span>{item.name}</span><strong>{item.value}</strong><small className="neutral">{item.split}{item.horizon != null ? ` · h${item.horizon}` : ''}</small></article>) : <article><span>指标</span><strong>—</strong><small className="neutral">暂无全局指标</small></article>}</section>
        {shown.length ? <div className="result-conclusion"><span className="mono-label">METRIC DETAIL</span><b>该 Result 登记的全局指标</b><p>{metrics.map(item => `${item.name}=${item.value}${item.horizon != null ? `@h${item.horizon}` : ''}`).join(' · ')}</p></div> : <div className="result-conclusion"><span className="mono-label">NO METRICS</span><b>该 Result 尚未登记指标</b><p>真实 Runner 采集完成后，可在 Run 详情页执行「采集结果入库」，随后在此查看指标、绘图与导出。</p></div>}
      </>}
      {tab === 'basins' && <section className="section-block"><div className="section-heading"><div><h2>逐流域指标</h2><p>含 basin_id 的指标明细</p></div></div>{byBasin.length ? <div className="run-table-wrap"><table className="run-table"><thead><tr><th>流域 ID</th><th>指标</th><th>数值</th><th>时域</th></tr></thead><tbody>{byBasin.map(item => <tr key={`${item.basin_id}-${item.name}-${item.horizon}`}><td className="mono">{item.basin_id}</td><td>{item.name}</td><td className="metric">{item.value}</td><td>{item.horizon != null ? `h${item.horizon}` : '—'}</td></tr>)}</tbody></table></div> : <p className="quiet" style={{ padding: 16 }}>当前没有按流域拆分的指标。</p>}</section>}
      {tab === 'assets' && <section className="section-block"><div className="section-heading"><div><h2>结果资产</h2><p>真实执行采集到的产物（object_key / sha256 / size）</p></div><button className="button primary" onClick={() => setExportOpen(true)}>选择文件导出</button></div>{collection && collection.artifacts.length ? <div className="asset-list">{collection.artifacts.map(artifact => <div key={artifact.object_key}><FileCode2 size={16}/><span><b>{artifact.relative_path || artifact.object_key.split('/').pop()}</b><small>{artifact.kind} · {artifact.object_key}</small></span><code>{artifact.size_bytes ? `${(artifact.size_bytes / 1024).toFixed(1)} KB` : '—'}</code><button className="button ghost" disabled title="对象存储直链待 S3 适配后开放"><Download size={13}/>下载</button></div>)}</div> : <p className="quiet" style={{ padding: 16 }}>该 Result 尚无采集产物。绘图生成的 SVG 与导出 zip 会登记到对象存储。</p>}</section>}
      {exportOpen && <ExportPicker resultIds={[result.id]} onCreated={info => { setMessage(`导出包已生成：${info.export_id.slice(0, 8)} · ${(info.size_bytes / 1024).toFixed(1)} KB · ${info.files.length} 个文件`); onChanged?.() }} close={() => setExportOpen(false)} />}
      {plotOpen && <PlotBuilder resultIds={[result.id]} onCreated={info => { setMessage(`绘图规格已创建：${info.plot_id.slice(0, 8)} · ${info.artifact_count} 个 SVG 产物`); onChanged?.() }} close={() => setPlotOpen(false)} />}
    </div>
  )
}

function RunComparison({ resultIds, back }: { resultIds: string[]; back: () => void }) {
  const [comparison, setComparison] = useState<ApiComparison | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const resultKey = useMemo(() => resultIds.join(','), [resultIds])
  useEffect(() => {
    setLoading(true); setError(null)
    void (async () => {
      try {
        await ensureDevSession()
        setComparison(await compareResults(resultKey ? resultKey.split(',') : []))
      } catch (cause) {
        setError(cause instanceof ApiError ? cause.message : cause instanceof Error ? cause.message : '对比失败')
      } finally { setLoading(false) }
    })()
  }, [resultKey])
  const allNames = comparison ? Object.keys(comparison.metrics) : []
  const metricNames = comparison ? Array.from(new Set(allNames.flatMap(id => Object.keys(comparison.metrics[id] ?? {})))) : []
  const deltas = comparison?.delta_from_baseline ?? {}
  return (
    <div className="page-stack"><header className="page-heading result-detail-heading"><button className="icon-button" onClick={back}><ArrowLeft size={18}/></button><div><p className="eyebrow">COMPARE / {resultIds.length} RESULTS</p><h1>实验结果对比</h1><p>{comparison ? `冻结数据版本 ${comparison.dataset_version_id.slice(0, 8)} · 基线 ${comparison.baseline_result_id.slice(0, 8)}` : '调用 /results/compare 读取后端指标对比'}</p></div></header>
      {error && <p className="error-notice">对比错误：{error}</p>}
      {loading && <p className="quiet">正在对比…</p>}
      {comparison && <>
        <section className="compare-runs">{allNames.map(id => <article className={id === comparison.baseline_result_id ? 'baseline' : ''} key={id}><span className="mono-label">{id === comparison.baseline_result_id ? 'BASELINE' : 'CANDIDATE'}</span><b>{id.slice(0, 8)}</b><small>{id.slice(0, 8)}</small></article>)}</section>
        <section className="section-block"><div className="section-heading"><div><h2>指标对比</h2><p>相对基线差异（delta_from_baseline）</p></div></div><div className="run-table-wrap"><table className="run-table"><thead><tr><th>Result</th>{metricNames.map(name => <th key={name}>{name}</th>)}</tr></thead><tbody>{allNames.map(id => <tr key={id}><td className="run-id">{id.slice(0, 8)}{id === comparison.baseline_result_id ? ' · 基线' : ''}</td>{metricNames.map(name => { const value = comparison.metrics[id][name]; const delta = id !== comparison.baseline_result_id ? deltas[id]?.[name] : undefined; return <td key={name} className="metric">{value}{delta != null ? ` (${delta >= 0 ? '+' : ''}${delta.toFixed(3)})` : ''}</td> })}</tr>)}</tbody></table></div></section>
      </>}
    </div>
  )
}

function ResultIndex({ onOpen, onCompare }: { onOpen: (result: ApiResult) => void; onCompare: (ids: string[]) => void }) {
  const [results, setResults] = useState<ApiResult[]>([])
  const [metricsByResult, setMetricsByResult] = useState<Record<string, ApiMetric[]>>({})
  const [selected, setSelected] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const load = async () => {
    setLoading(true); setError(null)
    try {
      await ensureDevSession()
      const items = await listResults()
      setResults([...items].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()))
      const metrics: Record<string, ApiMetric[]> = {}
      for (const result of items) {
        try { metrics[result.id] = await listMetrics(result.id) } catch { metrics[result.id] = [] }
      }
      setMetricsByResult(metrics)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '加载结果失败')
    } finally { setLoading(false) }
  }
  useEffect(() => { void load() }, [])
  const toggle = (id: string) => setSelected(current => current.includes(id) ? current.filter(item => item !== id) : [...current, id])
  const best = results.map(result => ({ result, nse: (metricsByResult[result.id] ?? []).find(item => item.name.toUpperCase() === 'NSE')?.value })).filter(item => item.nse != null).sort((a, b) => (b.nse ?? 0) - (a.nse ?? 0))[0]
  return (
    <div className="page-stack"><header className="page-heading"><div><p className="eyebrow">RESULT INDEX</p><h1>结果与对比</h1><p>浏览所有已产生结果的实验，进入详情或选择 2–5 个结果进行对比。</p></div><div className="page-actions"><button className="button ghost" onClick={() => void load()} disabled={loading}><RefreshCw size={15}/>{loading ? '加载中' : '刷新'}</button><button className="button primary" disabled={selected.length < 2 || selected.length > 5} onClick={() => onCompare(selected)}>对比所选 ({selected.length})</button></div></header>
      {error && <p className="error-notice">结果加载错误：{error}</p>}
      <section className="result-summary"><div><span className="mono-label">RESULTS</span><strong>{results.length}</strong><small>已登记结果</small></div><div><span className="mono-label">BEST NSE</span><strong>{best ? best.nse!.toFixed(3) : '—'}</strong><small>{best ? best.result.id.slice(0, 8) : '尚无 NSE 指标'}</small></div><div><span className="mono-label">DATA VERSIONS</span><strong>{new Set(results.map(result => result.dataset_version_id)).size}</strong><small>冻结数据版本数</small></div></section>
      <section className="section-block"><div className="run-table-wrap"><table className="run-table result-index-table"><thead><tr><th aria-label="选择"/><th>结果</th><th>来源 Run</th><th>冻结数据版本</th><th>NSE</th><th>创建时间</th><th/></tr></thead><tbody>{results.map(result => { const nse = (metricsByResult[result.id] ?? []).find(item => item.name.toUpperCase() === 'NSE'); return <tr key={result.id} className="clickable-row"><td onClick={event => event.stopPropagation()}><input type="checkbox" checked={selected.includes(result.id)} onChange={() => toggle(result.id)} aria-label={`选择 ${result.id}`}/></td><td onClick={() => onOpen(result)}><span className="run-id">{result.id.slice(0, 8)}</span></td><td onClick={() => onOpen(result)} className="mono">{result.run_id.slice(0, 8)}</td><td onClick={() => onOpen(result)} className="mono">{result.dataset_version_id.slice(0, 8)}</td><td className="metric num" onClick={() => onOpen(result)}>{nse ? nse.value.toFixed(3) : '—'}</td><td onClick={() => onOpen(result)}>{formatRunTime(result.created_at)}</td><td><ChevronRight size={15}/></td></tr> })}{!loading && !results.length && <tr><td colSpan={7}>暂无结果；成功 Run 采集入库后会自动出现在这里。</td></tr>}</tbody></table></div></section>
    </div>
  )
}

function RunDetail({ runId, back, onUpdated }: { runId: string | null; back: () => void; onUpdated?: () => void }) {
  const defaultCards: RunCardId[] = ['metrics', 'resources', 'logs', 'lineage']
  const [cards, setCards] = useState<RunCardId[]>(() => {
    const saved = localStorage.getItem('hydrolab-run-layout')
    return saved ? JSON.parse(saved) : defaultCards
  })
  const [hidden, setHidden] = useState<RunCardId[]>([])
  const [editing, setEditing] = useState(false)
  const [dragged, setDragged] = useState<RunCardId | null>(null)
  const labels: Record<RunCardId, string> = { metrics: '训练指标', resources: 'GPU 资源', logs: '实时日志', lineage: '参数与数据血缘' }
  const [summary, setSummary] = useState<ApiRunSummary | null>(null)
  const [stages, setStages] = useState<ApiRunStage[]>([])
  const [events, setEvents] = useState<ApiRunEvent[]>([])
  const [logs, setLogs] = useState<ApiRunLog[]>([])
  const [resources, setResources] = useState<ApiResourceSample[]>([])
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [active, setActive] = useState(false)
  const logCursor = useRef(0)
  const loadAll = useCallback(async () => {
    if (!runId) return
    try {
      const [run, stageList, resourceList] = await Promise.all([getRun(runId), getRunStages(runId), getRunResources(runId)])
      setSummary(run)
      setStages(stageList)
      setResources(resourceList)
      setActive(['QUEUED', 'PREPARING', 'RUNNING'].includes(run.status))
      setLogs(await getRunLogs(runId, 0))
      setEvents(await getRunEvents(runId, 0))
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '加载 Run 失败')
    }
  }, [runId])
  useEffect(() => { if (runId) { setLogs([]); setEvents([]); logCursor.current = 0; void loadAll() } }, [runId, loadAll])
  useEffect(() => {
    if (!runId) return
    const controller = new AbortController()
    subscribeRunEvents(runId, event => {
      setEvents(prev => {
        const index = prev.findIndex(item => item.id === event.id)
        if (index === -1) return [...prev, event]
        const next = [...prev]
        next[index] = event
        return next
      })
      if (event.event_type === 'run.status.changed') {
        const status = String(event.payload.status ?? '')
        setSummary(prev => prev ? { ...prev, status } : prev)
        setActive(['QUEUED', 'PREPARING', 'RUNNING'].includes(status))
        // 收到终态后停止 SSE 重连，避免无限订阅。
        if (['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(status)) controller.abort()
      }
    }, controller.signal, cause => setError(cause instanceof ApiError ? cause.message : '事件流中断'))
    return () => controller.abort()
  }, [runId])
  useEffect(() => {
    if (!runId || !active) return
    let stopped = false
    const tick = async () => {
      try {
        const chunks = await getRunLogs(runId, logCursor.current)
        if (chunks.length) { setLogs(prev => [...prev, ...chunks]); logCursor.current = chunks[chunks.length - 1].id }
      } catch { /* 忽略 */ }
      if (!stopped) setTimeout(() => void tick(), 2000)
    }
    void tick()
    return () => { stopped = true }
  }, [runId, active])
  useEffect(() => {
    if (!runId || !active) return
    let stopped = false
    const tick = async () => {
      try { setResources(await getRunResources(runId)) } catch { /* 忽略 */ }
      if (!stopped) setTimeout(() => void tick(), 3000)
    }
    void tick()
    return () => { stopped = true }
  }, [runId, active])
  const saveLayout = () => { localStorage.setItem('hydrolab-run-layout', JSON.stringify(cards)); setEditing(false) }
  const dropCard = (target: RunCardId) => {
    if (!dragged || dragged === target) return
    setCards(current => { const next = current.filter(id => id !== dragged); next.splice(next.indexOf(target), 0, dragged); return next })
    setDragged(null)
  }
  const runAction = async (action: 'start' | 'cancel' | 'ingest') => {
    if (!runId) return
    setBusy(true); setError(null); setMessage(null)
    try {
      if (action === 'start') {
        const updated = await startRun(runId, 1)
        setSummary(prev => prev ? { ...prev, status: updated.status } : prev)
        setMessage('Run 已启动，等待 GPU 租约与执行。')
      } else if (action === 'cancel') {
        const updated = await cancelRealRun(runId)
        setSummary(prev => prev ? { ...prev, status: updated.status } : prev)
        setMessage('Run 已取消，GPU 租约已释放。')
      } else {
        const result = await ingestRunResult(runId)
        setMessage(`结果已入库：Result ${result.result.id.slice(0, 8)} · 指标 ${result.metrics_added} 条 · 产物 ${result.artifacts_added} 个${result.warnings?.length ? ` · 警告：${result.warnings.join('；')}` : ''}。`)
      }
      await loadAll()
      onUpdated?.()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Run 操作失败')
    } finally { setBusy(false) }
  }
  const latestProgress = [...events].reverse().find(event => event.event_type === 'run.progress.updated')
  const latestMetrics = events.filter(event => event.event_type === 'run.metric.reported')
  const metricValues = latestMetrics.slice(-10).reverse()
  const stageLabels: Record<string, string> = { TRAINING: '模型训练', EVALUATING: '评估', PLOTTING: '绘图', UPLOADING: '上传产物' }
  const renderCard = (id: RunCardId) => {
    if (hidden.includes(id)) return null
    const handle = editing ? <div className="drag-handle"><GripVertical size={15}/><span>拖动调整</span><button onClick={() => setHidden(current => [...current, id])}>隐藏</button></div> : null
    if (id === 'metrics') return (
      <section className="chart-panel metric-chart customizable-card">{handle}<div className="section-heading"><div><h2>训练指标</h2><p>来自 Run 事件流的指标上报</p></div></div>
        {metricValues.length ? <div className="event-table"><div><b>指标</b><b>数值</b><b>Step</b></div>{metricValues.map(event => <div key={event.id}><span>{String(event.payload.name ?? '—')}</span><span className="metric">{String(event.payload.value ?? '—')}</span><span>{String(event.payload.step ?? '—')}</span></div>)}</div> : <p className="quiet" style={{ padding: '16px' }}>暂无指标上报。</p>}
      </section>
    )
    if (id === 'resources') {
      const sample = resources[resources.length - 1]
      return (
        <section className="resource-panel customizable-card">{handle}<div className="panel-topline"><span className="mono-label">GPU / {active ? 'LIVE' : 'IDLE'}</span><Activity size={15} /></div>
          {sample ? <><div className="resource-row"><span>利用率</span><b>{sample.utilization_percent}%</b></div><div className="usage-bar"><span style={{ width: `${sample.utilization_percent}%` }} /></div><div className="resource-row"><span>显存</span><b>{sample.memory_used_mb} / {sample.memory_total_mb} MB</b></div><div className="usage-bar"><span style={{ width: `${Math.round(sample.memory_used_mb / sample.memory_total_mb * 100)}%` }} /></div><div className="resource-meta"><span>GPU {sample.gpu_index}</span><span>{sample.sampled_at ? formatRunTime(sample.sampled_at) : '—'}</span></div></> : <p className="quiet" style={{ padding: '16px' }}>暂无资源采样。</p>}
        </section>
      )
    }
    if (id === 'logs') return (
      <section className="log-panel customizable-card">{handle}<div className="log-heading"><div><ChevronDown size={16} /><b>实时训练日志</b><span>增量拉取 · {logs.length} 行</span></div><span className="live-indicator">{active ? 'LIVE' : 'END'}</span></div>
        <pre>{logs.length ? logs.map(chunk => chunk.content.split('\n').filter(Boolean).map((line, lineIndex) => <span key={`${chunk.id}-${lineIndex}`}>{chunk.created_at ? `${new Date(chunk.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })} ` : ''}{line}{'\n'}</span>)) : <em>暂无日志输出。</em>}</pre>
      </section>
    )
    return (
      <section className="lineage-panel customizable-card">{handle}<div><span className="mono-label">EXPERIMENT LINEAGE</span><h2>参数与数据血缘</h2></div>
        <div className="lineage graph">
          <span><Database size={15} />数据 {summary?.dataset_version_id ? summary.dataset_version_id.slice(0, 8) : '—'}</span><ChevronRight />
          <span><FileCode2 size={15} />代码 {summary?.code_version_id ? summary.code_version_id.slice(0, 8) : '—'}<br />模板 {summary?.template_version_id ? summary.template_version_id.slice(0, 8) : '—'}</span><ChevronRight />
          <span><FlaskConical size={15} />实验 {summary?.experiment_name ?? '—'}</span><ChevronRight />
          <span className="current"><Layers3 size={15} />Run {summary ? summary.id.slice(0, 8) : '—'}</span>
        </div>
        {Object.keys(summary?.parameters ?? {}).length > 0 && <div className="detail-section"><div className="section-heading"><div><h3>冻结参数</h3><p>ExperimentVersion.resolved_config.parameters</p></div></div><pre style={{ margin: '12px 0 0', fontSize: 10 }}>{JSON.stringify(summary?.parameters, null, 2)}</pre></div>}
      </section>
    )
  }
  const progressPercent = latestProgress ? Number(latestProgress.payload.percent ?? 0) : null
  const latestMetric = latestMetrics[latestMetrics.length - 1]
  return (
    <div className="page-stack">
      <header className="run-heading"><button className="icon-button" onClick={back} aria-label="返回运行中心"><ArrowLeft size={18} /></button><div><p className="eyebrow">RUN {summary ? summary.id.slice(0, 8) : '—'} / {(summary?.argv.join(' ') || 'EXECUTION')}</p><h1>{summary?.experiment_name ?? '正在加载…'}</h1><p>{summary ? `${runStatusLabel[summary.status] ?? summary.status} · 创建于 ${formatRunTime(summary.created_at)}` : '读取后端 Run 元数据'}</p></div><div className="run-actions"><button className="button ghost" onClick={() => editing ? saveLayout() : setEditing(true)}><SlidersHorizontal size={15}/>{editing ? '保存布局' : '调整布局'}</button>{summary?.status === 'QUEUED' && <button className="button secondary" onClick={() => void runAction('start')} disabled={busy}><Play size={15} />启动</button>}{(summary?.status === 'QUEUED' || summary?.status === 'RUNNING' || summary?.status === 'PREPARING') && <button className="button secondary" onClick={() => void runAction('cancel')} disabled={busy}><CircleStop size={15} />停止任务</button>}{summary?.status === 'SUCCEEDED' && <button className="button primary" onClick={() => void runAction('ingest')} disabled={busy}><Check size={15} />采集结果入库</button>}<button className="button ghost" onClick={() => void loadAll()} disabled={busy}><RefreshCw size={15} />刷新</button></div></header>
      {error && <p className="error-notice">Run 详情错误：{error}</p>}
      {message && <p className="onboarding"><b>{message}</b></p>}
      {editing && <section className="layout-toolbar"><div><b>个人布局</b><span>拖动卡片改变顺序，隐藏的模块可随时恢复。</span></div>{hidden.map(id => <button key={id} onClick={() => setHidden(current => current.filter(item => item !== id))}>恢复「{labels[id]}」</button>)}<button onClick={() => { setCards(defaultCards); setHidden([]) }}>恢复默认</button></section>}
      <section className="stage-track">{stages.length ? stages.map(stage => <div className={summary?.status === 'SUCCEEDED' ? 'done' : ''} key={stage.name}><span>{summary?.status === 'SUCCEEDED' ? <Check size={13} /> : stage.position + 1}</span><b>{stageLabels[stage.name] ?? stage.name}</b>{stage.position < stages.length - 1 && <i />}</div>) : <div><span>—</span><b>暂无阶段</b></div>}</section>
      <section className="run-kpis"><article><span className="mono-label">进度</span><strong>{progressPercent !== null ? `${progressPercent}%` : summary?.status === 'SUCCEEDED' ? '100%' : '—'}</strong>{progressPercent !== null && <div className="usage-bar"><span style={{ width: `${progressPercent}%` }} /></div>}</article><article><span className="mono-label">当前阶段</span><strong>{latestProgress ? String(latestProgress.payload.stage ?? 'TRAINING') : summary?.status ?? '—'}</strong><small>{latestProgress?.payload.eta_seconds != null ? `ETA ${String(latestProgress.payload.eta_seconds)}s` : '来自进度事件'}</small></article><article><span className="mono-label">最新指标</span><strong>{latestMetric ? `${String(latestMetric.payload.name ?? '')}=${String(latestMetric.payload.value ?? '')}` : '—'}</strong><small>{latestMetrics.length} 条指标上报</small></article><article><span className="mono-label">状态</span><strong>{summary ? runStatusLabel[summary.status] ?? summary.status : '—'}</strong><small>{summary ? `实验 ${summary.experiment_name}` : ''}</small></article></section>
      <div className={`custom-layout ${editing ? 'editing' : ''}`}>{cards.map(id => <div className={`card-slot ${id}`} draggable={editing} onDragStart={() => setDragged(id)} onDragOver={event => event.preventDefault()} onDrop={() => dropCard(id)} key={id}>{renderCard(id)}</div>)}</div>
    </div>
  )
}



function BatchSubmitPanel({ close }: { close: () => void }) {
  const [datasetVersions, setDatasetVersions] = useState<Array<ApiDatasetVersion & { datasetName: string }>>([])
  const [codeVersions, setCodeVersions] = useState<ApiCodeVersion[]>([])
  const [templateVersions, setTemplateVersions] = useState<ApiTemplateVersion[]>([])
  const [environmentVersions, setEnvironmentVersions] = useState<Array<{ id: string; version_no: number; status: string; environmentName: string }>>([])
  const [selectedDatasetIds, setSelectedDatasetIds] = useState<string[]>([])
  const [codeVersionId, setCodeVersionId] = useState('')
  const [templateVersionId, setTemplateVersionId] = useState('')
  const [environmentVersionId, setEnvironmentVersionId] = useState('')
  const [namePrefix, setNamePrefix] = useState('批量水文训练')
  const [epochs, setEpochs] = useState('20')
  const [preview, setPreview] = useState<ApiBatchSubmitItem[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => { void (async () => {
    try {
      const [loadedDatasets, loadedRepositories, loadedTemplates, loadedEnvironments] = await Promise.all([
        listDatasets(), listCodeRepositories(), listTemplates(), listEnvironments(),
      ])
      const versions = await Promise.all(loadedDatasets.map(async dataset => (await listDatasetVersions(dataset.id)).map(version => ({ ...version, datasetName: dataset.name }))))
      setDatasetVersions(versions.flat().filter(version => version.status === 'READY'))
      const code = await Promise.all(loadedRepositories.map(listCodeVersions)); setCodeVersions(code.flat().filter(version => version.status === 'READY'))
      const template = await Promise.all(loadedTemplates.map(listTemplateVersions)); setTemplateVersions(template.flat())
      const environment = await Promise.all(loadedEnvironments.map(async item => (await listEnvironmentVersions(item.id)).map(version => ({ ...version, environmentName: item.name }))))
      setEnvironmentVersions(environment.flat().filter(version => version.status === 'READY'))
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : '加载可运行资源失败') } finally { setLoading(false) }
  })() }, [])

  const valid = Boolean(namePrefix.trim() && selectedDatasetIds.length && codeVersionId && templateVersionId && environmentVersionId && Number(epochs) > 0)
  const buildBody = (dry_run: boolean) => ({ name_prefix: namePrefix, description: '网页批量提交', dataset_version_ids: selectedDatasetIds, code_version_id: codeVersionId, template_version_id: templateVersionId, environment_version_id: environmentVersionId, parameter_values: { epochs: Number(epochs) }, dry_run })
  const toggleDataset = (id: string) => setSelectedDatasetIds(current => current.includes(id) ? current.filter(item => item !== id) : [...current, id])
  const makePreview = async () => { if (!valid) return; setSubmitting(true); setError(null); try { setPreview((await submitBatch(buildBody(true))).items) } catch (cause) { setError(cause instanceof ApiError ? cause.message : '预览生成失败') } finally { setSubmitting(false) } }
  const enqueue = async () => { if (!valid) return; setSubmitting(true); setError(null); try { const result = await submitBatch(buildBody(false)); setPreview(result.items); setMessage(`已将 ${result.items.length} 个实验放入队列，双卡调度器会自动执行。`) } catch (cause) { setError(cause instanceof ApiError ? cause.message : '批量入队失败') } finally { setSubmitting(false) } }

  return <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="批量提交实验"><div className="wizard-modal batch-submit-modal"><header><div><span className="mono-label">BATCH LAUNCH</span><h2>一键并行提交实验</h2><p>每个已选数据版本生成一个独立、可复现的 Run；GPU 将以单卡单任务 FIFO 自动调度。</p></div><button className="icon-button" onClick={close} aria-label="关闭"><X size={18}/></button></header><main className="batch-submit-body">{loading ? <p>正在加载可运行资源…</p> : <><div className="form-stack"><label>批次名称<input value={namePrefix} onChange={event => setNamePrefix(event.target.value)} placeholder="例如：Top-30 流域扫描"/></label><label>训练 Epoch<input type="number" min="1" value={epochs} onChange={event => setEpochs(event.target.value)}/></label><label>代码版本<select value={codeVersionId} onChange={event => setCodeVersionId(event.target.value)}><option value="">选择已冻结代码版本</option>{codeVersions.map(version => <option key={version.id} value={version.id}>代码 v{version.version_no} · {version.content_hash?.slice(0, 8) ?? version.id.slice(0, 8)}</option>)}</select></label><label>训练模板<select value={templateVersionId} onChange={event => setTemplateVersionId(event.target.value)}><option value="">选择训练模板版本</option>{templateVersions.filter(version => !codeVersionId || version.code_version_id === codeVersionId).map(version => <option key={version.id} value={version.id}>模板 v{version.version_no} · {version.argv.join(' ')}</option>)}</select></label><label>运行环境<select value={environmentVersionId} onChange={event => setEnvironmentVersionId(event.target.value)}><option value="">选择运行环境版本</option>{environmentVersions.map(version => <option key={version.id} value={version.id}>{version.environmentName} · v{version.version_no}</option>)}</select></label></div><section className="detail-section"><div className="section-heading"><div><h3>选择数据版本</h3><p>勾选后，每个版本都会展开为一条独立的训练任务。</p></div><span className="status-badge neutral">已选 {selectedDatasetIds.length}</span></div><div className="selection-list">{datasetVersions.map(version => <label className={selectedDatasetIds.includes(version.id) ? 'selected' : ''} key={version.id}><input type="checkbox" checked={selectedDatasetIds.includes(version.id)} onChange={() => toggleDataset(version.id)}/><Database size={16}/><div><b>{version.datasetName} · v{version.version_no}</b><span>{String(version.manifest.format ?? '数据包')} · {version.content_hash?.slice(0, 10) ?? '未记录内容摘要'}</span></div></label>)}{!datasetVersions.length && <p>没有 READY 数据版本；请先在“数据”页导入并冻结数据。</p>}</div></section>{preview.length > 0 && <section className="plot-plan"><span className="mono-label">QUEUE PREVIEW</span><p>将创建 {preview.length} 个 Run：</p>{preview.map(item => <div key={item.dataset_version_id}><b>{item.name}</b><code>{item.argv.join(' ')}</code></div>)}</section>}{error && <p className="error-notice">{error}</p>}{message && <p className="success-notice">{message}</p>}</>}</main><footer><button className="button secondary" onClick={close}>取消</button><button className="button secondary" disabled={!valid || submitting} onClick={() => void makePreview}>{submitting ? '处理中…' : '预览任务'}</button><button className="button primary" disabled={!valid || submitting} onClick={() => void enqueue}><Play size={15}/>{submitting ? '入队中…' : `确认入队 ${selectedDatasetIds.length || ''}`}</button></footer></div></div>
}

type ApiParameterDefinition = { key: string; label: string; type: string; required?: boolean; default?: unknown; minimum?: number | null; maximum?: number | null; choices?: string[]; description?: string }
type ApiTemplateOption = { id: string; code_version_id: string; mode: string; argv: string[]; label: string; parameters: ApiParameterDefinition[] }

function ExperimentWizard({ close }: { close: () => void }) {
  const [step, setStep] = useState(1)
  const steps = ['实验信息', '代码模板', '数据版本', '运行环境', '参数与提交']
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [templateOptions, setTemplateOptions] = useState<ApiTemplateOption[]>([])
  const [datasetOptions, setDatasetOptions] = useState<Array<{ id: string; label: string }>>([])
  const [environmentOptions, setEnvironmentOptions] = useState<Array<{ id: string; label: string }>>([])
  const [templateVersionId, setTemplateVersionId] = useState('')
  const [datasetVersionId, setDatasetVersionId] = useState('')
  const [environmentVersionId, setEnvironmentVersionId] = useState('')
  const [parameterValues, setParameterValues] = useState<Record<string, unknown>>({})
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        await ensureDevSession()
        await seedDemo()
        const [loadedTemplates, loadedDatasets, loadedEnvironments] = await Promise.all([listTemplates(), listDatasets(), listEnvironments()])
        const templates = (await Promise.all(loadedTemplates.map(async item => (await listTemplateVersions(item.id)).map(version => ({ id: version.id, code_version_id: version.code_version_id, mode: version.mode, argv: version.argv, parameters: (version.parameters ?? []) as unknown as ApiParameterDefinition[], label: `${item.name} · v${version.version_no} · ${version.argv.join(' ')}` }))))).flat()
        const datasets = (await Promise.all(loadedDatasets.map(async item => (await listDatasetVersions(item.id)).filter(version => version.status === 'READY').map(version => ({ id: version.id, label: `${item.name} · v${version.version_no}` }))))).flat()
        const environments = (await Promise.all(loadedEnvironments.map(async item => (await listEnvironmentVersions(item.id)).filter(version => version.status === 'READY').map(version => ({ id: version.id, label: `${item.name} · v${version.version_no}` }))))).flat()
        if (!cancelled) { setTemplateOptions(templates); setDatasetOptions(datasets); setEnvironmentOptions(environments) }
      } catch (cause) {
        if (!cancelled) setError(cause instanceof ApiError ? cause.message : '加载可运行资源失败')
      } finally { if (!cancelled) setLoading(false) }
    })()
    return () => { cancelled = true }
  }, [])
  const selectedTemplate = templateOptions.find(option => option.id === templateVersionId)
  const validBasics = name.trim().length > 0
  const canSubmit = validBasics && Boolean(templateVersionId) && Boolean(datasetVersionId) && Boolean(environmentVersionId)
  const submit = async () => {
    if (!canSubmit) { setError('请完成全部步骤后再提交'); return }
    setSubmitting(true)
    setError(null)
    try {
      const draft = await createDraft(name.trim(), description.trim())
      const updated = await updateDraft(draft.id, {
        dataset_version_id: datasetVersionId,
        code_version_id: selectedTemplate?.code_version_id ?? null,
        template_version_id: templateVersionId,
        environment_version_id: environmentVersionId,
        parameter_values: parameterValues,
      })
      const submitted = await submitDraft(updated.id)
      setMessage(`实验「${submitted.experiment.name}」已提交并冻结为 v${submitted.version.version_no}；Run ${submitted.run.id.slice(0, 8)} 已进入 ${submitted.run.status} 队列。`)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : cause instanceof Error ? cause.message : '提交实验失败')
    } finally { setSubmitting(false) }
  }
  const goNext = () => { setError(null); setStep(current => Math.min(current + 1, steps.length)) }
  const goBack = () => { setError(null); setStep(current => Math.max(current - 1, 1)) }
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="创建实验">
      <div className="wizard-modal">
        <header>
          <div><span className="mono-label">NEW EXPERIMENT</span><h2>创建训练实验</h2><p>分步选择代码模板、数据版本与运行环境，最后冻结参数提交。</p></div>
          <button className="icon-button" onClick={close} aria-label="关闭"><X size={18} /></button>
        </header>
        <div className="wizard-body">
          <aside>{steps.map((label, i) => <button className={step === i + 1 ? 'active' : step > i + 1 ? 'done' : ''} onClick={() => setStep(i + 1)} key={label}><span>{step > i + 1 ? <Check size={13} /> : i + 1}</span><div><b>{label}</b></div></button>)}</aside>
          <main>
            <span className="step-counter">STEP {step} / {steps.length}</span><h3>{steps[step - 1]}</h3>
            {loading && <p className="quiet">正在加载可运行资源…</p>}
            {error && <p className="error-notice">向导错误：{error}</p>}
            {message && <p className="onboarding"><b>{message}</b></p>}
            {step === 1 && <div className="form-stack"><label>实验名称 <em>必填</em><input value={name} onChange={event => setName(event.target.value)} placeholder="例如：北江 Top-30 迁移训练" /></label><label>说明 <span>可选</span><input value={description} onChange={event => setDescription(event.target.value)} placeholder="例如：2026 汛期滚动预报" /></label></div>}
            {step === 2 && <div className="form-stack"><label>代码模板版本 <em>必填</em><select value={templateVersionId} onChange={event => setTemplateVersionId(event.target.value)}><option value="">选择一个可执行模板版本</option>{templateOptions.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}</select></label>{selectedTemplate && <div className="data-preview"><FileCode2 /><div><b>{selectedTemplate.label}</b><span>绑定 CodeVersion {selectedTemplate.code_version_id.slice(0, 8)} · {selectedTemplate.mode}</span></div><StatusBadge status="READY" /></div>}</div>}
            {step === 3 && <div className="form-stack"><label>目标数据版本 <em>必填</em><select value={datasetVersionId} onChange={event => setDatasetVersionId(event.target.value)}><option value="">选择一个 READY 数据版本</option>{datasetOptions.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}</select></label>{datasetVersionId && <div className="data-preview"><Database /><div><b>{datasetOptions.find(option => option.id === datasetVersionId)?.label}</b><span>READY 数据版本</span></div><StatusBadge status="READY" /></div>}</div>}
            {step === 4 && <div className="form-stack"><label>运行环境版本 <em>必填</em><select value={environmentVersionId} onChange={event => setEnvironmentVersionId(event.target.value)}><option value="">选择一个 READY 运行环境</option>{environmentOptions.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}</select></label></div>}
            {step === 5 && <>
              <div className="experiment-freeze-summary" style={{ border: '1px solid var(--border)', padding: '12px' }}>
                {[['实验名称', name || '—'], ['模板版本', selectedTemplate?.label ?? '—'], ['数据版本', datasetOptions.find(option => option.id === datasetVersionId)?.label ?? '—'], ['运行环境', environmentOptions.find(option => option.id === environmentVersionId)?.label ?? '—']].map(row => <div key={row[0]} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderTop: '1px solid var(--border)', fontSize: 11 }}><span style={{ color: 'var(--muted)' }}>{row[0]}</span><b>{row[1]}</b></div>)}
              </div>
              {selectedTemplate?.parameters.length ? <div className="parameter-grid" style={{ marginTop: 12 }}>{selectedTemplate.parameters.map(definition => <label key={definition.key}>{definition.label} ({definition.key}){definition.required ? ' <em>必填</em>' : ''}<input defaultValue={definition.default != null ? String(definition.default) : ''} onChange={event => setParameterValues(current => ({ ...current, [definition.key]: definition.type === 'INTEGER' || definition.type === 'NUMBER' ? Number(event.target.value) : event.target.value }))} /></label>)}</div> : <p className="quiet">该模板没有超参数定义。</p>}
            </>}
          </main>
        </div>
        <footer>
          <div><button className="button secondary" onClick={step === 1 ? close : goBack}>上一步</button></div>
          {step < steps.length ? <button className="button primary" onClick={goNext} disabled={loading}>下一步</button> : <button className="button primary" onClick={() => void submit()} disabled={!canSubmit || submitting}>{submitting ? '正在提交…' : '提交并进入队列'}</button>}
        </footer>
      </div>
    </div>
  )
}


function DatasetImportPanel({ reload }: { reload: () => Promise<void> }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [mappingJobId, setMappingJobId] = useState<string | null>(null)
  const [mappingItems, setMappingItems] = useState<ApiMappingItem[]>([])
  const choose = (files: FileList | null) => setFile(files?.[0] ?? null)
  const updateMapping = (index: number, patch: Partial<ApiMappingItem>) => setMappingItems(items => items.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch, user_modified: true } : item))
  const beginImport = async () => {
    if (!name.trim()) { setError('请填写数据集名称'); return }
    if (!file) { setError('请拖入或选择一个 CSV 文件'); return }
    if (file.size > 2_000_000) { setError('当前本地 Fake/InMemory 联调仅支持不超过 2 MB 的文件；大文件需配置对象存储直传。'); return }
    setSubmitting(true); setError(null); setMessage(null)
    try {
      await ensureDevSession()
      const dataset = await createDataset(name.trim(), description.trim())
      const job = await createDatasetImport(dataset.id)
      await fakeUploadDataset(job.id, file.name, await file.text())
      const mapping = await getDatasetMapping(job.id)
      setMappingJobId(job.id)
      setMappingItems(mapping.items)
      setMessage('文件已解析。请检查并确认每个字段的语义后，再生成不可变版本。')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : cause instanceof Error ? cause.message : '导入请求失败')
    } finally { setSubmitting(false) }
  }
  const confirmMapping = async () => {
    if (!mappingJobId) return
    const timeFields = mappingItems.filter(item => item.semantic === 'TIME')
    if (timeFields.length !== 1) { setError(`必须指定且只能指定 1 个时间字段；当前为 ${timeFields.length} 个。`); return }
    setSubmitting(true); setError(null)
    try {
      const version = await confirmDatasetMapping(mappingJobId, mappingItems)
      setMessage(`字段映射已确认，已生成不可变版本 v${version.version_no} · ${version.id.slice(0, 8)}`)
      setName(''); setDescription(''); setFile(null); setMappingJobId(null); setMappingItems([])
      await reload()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : cause instanceof Error ? cause.message : '确认映射失败')
    } finally { setSubmitting(false) }
  }
  const resetMapping = () => { setMappingJobId(null); setMappingItems([]); setMessage(null); setError(null) }
  return <section className="dataset-import-panel">
    <div className="dataset-import-heading"><div><p className="eyebrow">NEW DATASET</p><h2>{mappingJobId ? '确认字段映射' : '新建并导入数据'}</h2><p>{mappingJobId ? '映射决定不可变版本中的时间、流域、输入特征与预测目标。' : '创建数据集后先解析字段；由你确认映射后才会生成不可变版本。'}</p></div><span className="status-badge neutral">本地联调</span></div>
    {!mappingJobId && <><div className="dataset-import-fields"><label>数据集名称 <em>必填</em><input value={name} onChange={event => setName(event.target.value)} placeholder="例如：北江 2023 年小时尺度观测" /></label><label>说明 <span>可选</span><input value={description} onChange={event => setDescription(event.target.value)} placeholder="例如：雨量、流量与气象站观测" /></label></div><input id="dataset-file-picker" className="visually-hidden" type="file" accept=".csv,text/csv" onChange={event => choose(event.target.files)} /><label htmlFor="dataset-file-picker" className={`dataset-drop-zone ${dragging ? 'dragging' : ''}`} onDragOver={event => { event.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={event => { event.preventDefault(); setDragging(false); choose(event.dataTransfer.files) }}><FileUp size={26}/><div><b>{file ? file.name : '拖入 CSV 文件，或点击选择本地文件'}</b><span>{file ? `${(file.size / 1024).toFixed(1)} KB · 上传后先进入字段映射确认` : '当前本地联调支持 CSV，单文件不超过 2 MB'}</span></div>{file && <button type="button" className="button ghost" onClick={event => { event.preventDefault(); setFile(null) }}>移除</button>}</label><div className="dataset-import-footer"><p>步骤 1/2：创建数据集并解析 CSV 字段</p><button className="button primary" onClick={() => void beginImport()} disabled={submitting}><FileUp size={15}/>{submitting ? '正在上传并解析…' : '上传并配置字段映射'}</button></div></>}
    {mappingJobId && <><div className="mapping-review"><div className="mapping-review-head"><b>已检测到 {mappingItems.length} 个字段</b><span>请指定 1 个时间字段；其余字段可标记为流域 ID、特征、目标、静态属性或忽略。</span></div><div className="mapping-review-table"><div><span>原始字段</span><span>字段角色</span><span>标准名称</span><span>单位</span></div>{mappingItems.map((item, index) => <div key={item.source_name}><code>{item.source_name}</code><select value={item.semantic} onChange={event => updateMapping(index, { semantic: event.target.value })}><option value="TIME">时间字段</option><option value="BASIN_ID">流域 ID</option><option value="FEATURE">动态输入特征</option><option value="TARGET">预测目标</option><option value="STATIC">静态属性</option><option value="IGNORE">忽略</option></select><input value={item.standard_name ?? ''} onChange={event => updateMapping(index, { standard_name: event.target.value || null })} /><input value={item.unit ?? ''} onChange={event => updateMapping(index, { unit: event.target.value || null })} placeholder="例如：mm/h" /></div>)}</div></div><div className="dataset-import-footer"><p>步骤 2/2：确认映射后将创建不可变版本，之后不能修改其字段语义。</p><div className="page-actions"><button className="button secondary" onClick={resetMapping} disabled={submitting}>返回修改文件</button><button className="button primary" onClick={() => void confirmMapping()} disabled={submitting}><Check size={15}/>{submitting ? '正在生成版本…' : '确认映射并生成版本'}</button></div></div></>}
    {message && <p className="onboarding"><b>{message}</b></p>}
    {error && <p className="error-notice">数据导入错误：{error}</p>}
  </section>
}

function CodeRepositoryPanel() {
  const [repositories, setRepositories] = useState<ApiCodeRepository[]>([])
  const [versions, setVersions] = useState<Record<string, ApiCodeVersion[]>>({})
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [source, setSource] = useState<'zip' | 'git' | 'dir'>('zip')
  const [file, setFile] = useState<File | null>(null)
  const [gitUrl, setGitUrl] = useState('')
  const [commit, setCommit] = useState('')
  const [dirPath, setDirPath] = useState('')
  const [importRoots, setImportRoots] = useState<string[]>([])
  const [preview, setPreview] = useState<ApiDirectoryPreview | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [entrypoints, setEntrypoints] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const load = async () => {
    try {
      await ensureDevSession(); await seedDemo()
      // 目录导入白名单由后端配置决定；为空表示该能力未开放。
      try { setImportRoots(await listCodeImportRoots()) } catch { setImportRoots([]) }
      const repos = await listCodeRepositories()
      setRepositories(repos)
      const loaded = await Promise.all(repos.map(async repo => [repo.id, await listCodeVersions(repo.id)] as const))
      setVersions(Object.fromEntries(loaded))
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : '无法加载代码资产') }
  }
  useEffect(() => { void load() }, [])
  const toBase64 = async (selected: File) => {
    const bytes = new Uint8Array(await selected.arrayBuffer())
    let binary = ''
    bytes.forEach(byte => { binary += String.fromCharCode(byte) })
    return btoa(binary)
  }
  const createExecutable = async (repository: ApiCodeRepository, version: ApiCodeVersion) => {
    const entrypoint = (entrypoints[version.id] || 'python train.py').trim()
    const argv = entrypoint.split(/\s+/).filter(Boolean)
    if (!argv.length) { setError('请填写训练入口，例如：python train.py'); return }
    setSubmitting(true); setError(null)
    try {
      await ensureDevSession()
      const template = await createTemplate(repository.id, `${repository.name} · 训练`, '由代码资产页创建的受控训练入口')
      const created = await createTemplateVersion(template.id, version.id, argv)
      setMessage(`已创建可执行模板「${template.name}」v${created.version_no}。现在可在“实验”页选择它创建训练 Run。`)
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : cause instanceof Error ? cause.message : '创建执行模板失败') } finally { setSubmitting(false) }
  }
  const runPreview = async () => {
    if (!dirPath.trim()) { setError('请填写服务器上的目录绝对路径'); return }
    setPreviewing(true); setError(null); setMessage(null); setPreview(null)
    try {
      await ensureDevSession()
      const result = await previewDirectoryImport(dirPath.trim())
      setPreview(result)
      setMessage(`预览成功：${result.file_count} 个代码文件，内容哈希 ${result.content_hash.slice(0, 12)}。虚拟环境、缓存、数据与既有产物已自动排除。`)
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : cause instanceof Error ? cause.message : '目录预览失败') } finally { setPreviewing(false) }
  }
  const submit = async () => {
    if (!name.trim()) { setError('请填写代码仓库名称'); return }
    if (source === 'zip' && !file) { setError('请选择 ZIP 代码归档'); return }
    if (source === 'git' && !gitUrl.trim()) { setError('请填写无凭证的 HTTPS Git 地址'); return }
    if (source === 'dir' && !dirPath.trim()) { setError('请填写服务器上的目录绝对路径'); return }
    if (file && file.size > 10_000_000) { setError('当前本地联调 ZIP 不超过 10 MB；生产环境应使用对象存储直传。'); return }
    setSubmitting(true); setError(null); setMessage(null)
    try {
      await ensureDevSession()
      const repo = await createCodeRepository(name.trim(), description.trim())
      if (source === 'dir') {
        const imported = await importCodeDirectory(repo.id, dirPath.trim())
        setMessage(`已把目录 ${imported.preview.source_path} 固化为代码「${repo.name}」v${imported.code_version.version_no}，共 ${imported.preview.file_count} 个文件，哈希 ${imported.preview.content_hash.slice(0, 12)}；入口候选：${imported.preview.entrypoints.slice(0, 5).join('、') || '未识别'}。`)
        setPreview(null); setDirPath('')
      } else {
        const version = source === 'zip'
          ? await importCodeZip(repo.id, file!.name, await toBase64(file!))
          : await importCodeGit(repo.id, gitUrl.trim(), commit.trim())
        setMessage(source === 'zip'
          ? `已导入代码「${repo.name}」v${version.version_no}，状态 ${version.status}；可在实验中选择该不可变版本。`
          : `已登记 Git 代码「${repo.name}」v${version.version_no}，状态 ${version.status}；等待 Worker 拉取并冻结 Commit。`)
      }
      setName(''); setDescription(''); setFile(null); setGitUrl(''); setCommit('')
      await load()
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : cause instanceof Error ? cause.message : '代码导入失败') } finally { setSubmitting(false) }
  }
  return <div className="page-stack"><header className="page-heading"><div><p className="eyebrow">MODEL CODE</p><h1>模型代码 / 模板</h1><p>每位用户仅看到自己拥有或被授权的代码仓库、不可变版本与可执行模板。</p></div><button className="button secondary" onClick={() => void load()}><RefreshCw size={15}/>刷新</button></header><section className="code-import-panel"><div className="dataset-import-heading"><div><p className="eyebrow">IMPORT CODE</p><h2>导入模型代码</h2><p>ZIP 会安全检查并冻结到对象存储；Git 仅登记 HTTPS 来源，等待 Worker 拉取固定 Commit。</p></div></div><div className="source-toggle"><button className={source === 'zip' ? 'active' : ''} onClick={() => setSource('zip')}>本地 ZIP</button><button className={source === 'git' ? 'active' : ''} onClick={() => setSource('git')}>Git HTTPS</button><button className={source === 'dir' ? 'active' : ''} onClick={() => setSource('dir')}>服务器目录</button></div><div className="dataset-import-fields"><label>代码仓库名称 <em>必填</em><input value={name} onChange={event => setName(event.target.value)} placeholder="例如：KG-MoE-MS 北江实验" /></label><label>说明 <span>可选</span><input value={description} onChange={event => setDescription(event.target.value)} placeholder="例如：2024 训练脚本与配置" /></label></div>{source === 'zip' ? <label className="dataset-drop-zone"><FileUp size={26}/><div><b>{file ? file.name : '选择包含训练入口的 ZIP 归档'}</b><span>{file ? `${(file.size / 1024).toFixed(1)} KB · 将检查文件清单并创建不可变版本` : '不执行 ZIP 内代码；拒绝路径穿越、符号链接和压缩炸弹'}</span></div><input className="visually-hidden" type="file" accept=".zip,application/zip" onChange={event => setFile(event.target.files?.[0] ?? null)} /></label> : <div className="dataset-import-fields"><label>Git HTTPS 地址 <em>必填</em><input value={gitUrl} onChange={event => setGitUrl(event.target.value)} placeholder="https://github.com/org/repository.git" /></label><label>固定 Commit <span>建议填写</span><input value={commit} onChange={event => setCommit(event.target.value)} placeholder="例如：a1b2c3d4" /></label></div>}{source === 'dir' && <div className="directory-import"><div className="dataset-import-fields"><label>服务器目录绝对路径 <em>必填</em><input value={dirPath} onChange={event => setDirPath(event.target.value)} placeholder={importRoots[0] ? `${importRoots[0]}/my-project` : '/srv/projects/my-project'} /></label></div><p className="quiet">允许导入的根目录：{importRoots.length ? importRoots.join('、') : '管理员尚未配置 HYDROLAB_CODE_IMPORT_ROOTS，目录导入不可用'}</p><button className="button secondary" onClick={() => void runPreview()} disabled={previewing || !importRoots.length}><Search size={15}/>{previewing ? '正在扫描…' : '预览目录快照'}</button>{preview && <div className="directory-preview"><div className="metadata-grid"><div><span>代码文件</span><b>{preview.file_count} 个</b></div><div><span>解压体积</span><b>{(preview.uncompressed_bytes / 1024).toFixed(0)} KB</b></div><div><span>归档体积</span><b>{(preview.archive_bytes / 1024).toFixed(0)} KB</b></div><div><span>内容哈希</span><b className="mono">{preview.content_hash.slice(0, 12)}</b></div></div><p>入口候选：{preview.entrypoints.slice(0, 6).join('、') || '未识别到根目录 Python 入口'}</p><p>依赖清单：{preview.detected_manifests.join('、') || '未识别'}</p><details><summary>查看前 20 个文件</summary><p className="mono">{preview.files.slice(0, 20).join('、')}</p></details></div>}</div>}<div className="dataset-import-footer"><p>导入后，实验 Runner 会把选中的不可变版本物化到受控工作目录，再按模板 argv 执行；不会直接执行任意宿主机路径。</p><button className="button primary" onClick={() => void submit()} disabled={submitting}><FileCode2 size={15}/>{submitting ? '正在导入…' : '导入代码版本'}</button></div>{message && <p className="onboarding"><b>{message}</b></p>}{error && <p className="error-notice">代码导入错误：{error}</p>}</section><section className="section-block"><div className="section-heading"><div><h2>我的代码仓库</h2><p>{repositories.length} 个可访问仓库 · 每个版本均可追溯来源、内容摘要与执行入口。</p></div></div><div className="code-repository-list">{repositories.map(repo => <article key={repo.id}><header><div><FileCode2 size={18}/><span><b>{repo.name}</b><small>{repo.description || '未填写说明'}</small></span></div><code>{repo.id.slice(0, 8)}</code></header>{(versions[repo.id] ?? []).map(version => <div className="code-version-row" key={version.id}><div><b>v{version.version_no} · {version.source_type}</b><small>{version.status === 'READY' ? `存储键：${version.object_key ?? '—'}` : `来源：${version.source_ref ?? '—'}${version.commit_sha ? ` @ ${version.commit_sha}` : ''}`}</small></div><div><code>{version.content_hash?.slice(0, 12) ?? '等待拉取'}</code><span>{version.manifest.file_count ?? 0} 个文件 · {(version.manifest.detected_manifests ?? []).join('、') || '未识别依赖清单'}</span></div><details><summary>查看文件与执行说明</summary><p>Runner 工作目录：<code>/workspace/code</code>（运行时受控物化，不是宿主机固定路径）</p><p>文件：{(version.manifest.files ?? []).slice(0, 12).join('、') || 'Git 拉取后生成'}</p>{version.status === 'READY' && <div className="template-entrypoint"><label>训练入口 argv<input value={entrypoints[version.id] ?? 'python train.py'} onChange={event => setEntrypoints(current => ({ ...current, [version.id]: event.target.value }))} placeholder="python train.py" /></label><button className="button secondary" onClick={() => void createExecutable(repo, version)} disabled={submitting}>创建可执行模板</button></div>}</details></div>)}{!(versions[repo.id] ?? []).length && <p className="quiet">尚未导入版本。</p>}</article>)}{!repositories.length && <p className="quiet">还没有代码仓库。请先导入 ZIP 或登记 Git HTTPS 地址。</p>}</div></section></div>
}

function ApiCatalogPage({ section }: { section: 'datasets' | 'code' | 'experiments' | 'checkpoints' | 'results' | 'environments' }) {
  const [items, setItems] = useState<ApiCatalogItem[]>([])
  const [draftName, setDraftName] = useState('')
  const [commandMessage, setCommandMessage] = useState<string | null>(null)
  const [operationMessage, setOperationMessage] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [templateOptions, setTemplateOptions] = useState<{ id: string; codeVersionId: string; label: string }[]>([])
  const [selectedTemplateVersionId, setSelectedTemplateVersionId] = useState('')
  const [datasetOptions, setDatasetOptions] = useState<{ id: string; label: string }[]>([])
  const [environmentOptions, setEnvironmentOptions] = useState<{ id: string; label: string }[]>([])
  const [selectedDatasetVersionId, setSelectedDatasetVersionId] = useState('')
  const [selectedEnvironmentVersionId, setSelectedEnvironmentVersionId] = useState('')
  const [loading, setLoading] = useState(true)
  const config = {
    datasets: ['DATA', '数据', '不可变数据版本与字段映射'],
    code: ['MODEL CODE', '模型代码 / 模板', '代码快照与可执行实验模板'],
    experiments: ['EXPERIMENTS', '实验', '冻结配置与独立 Run 历史'],
    checkpoints: ['CHECKPOINTS', 'Checkpoint', '可复用模型权重与兼容性结论'],
    results: ['RESULTS', '结果与对比', '成功 Run 的指标、产物与可比性'],
    environments: ['RUNTIME ASSETS', '运行环境', '版本化镜像与依赖锁定'],
  }[section]
  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      await ensureDevSession()
      await seedDemo()
      const loadedItems = await getRealSection(section)
      setItems(loadedItems)
      if (section === 'experiments') {
        const templates = await listTemplates()
        const loadedTemplates = await Promise.all(templates.map(async template => ({ template, versions: await listTemplateVersions(template.id) })))
        const options = loadedTemplates.flatMap(({ template, versions }) => versions.map(version => ({ id: version.id, codeVersionId: version.code_version_id, label: `${template.name} · v${version.version_no} · ${version.argv.join(' ')}` })))
        setTemplateOptions(options)
        setSelectedTemplateVersionId(current => current || options[0]?.id || '')
        const datasets = await listDatasets()
        const datasetVersions = await Promise.all(datasets.map(async item => (await listDatasetVersions(item.id)).filter(version => version.status === 'READY').map(version => ({ id: version.id, label: `${item.name} · v${version.version_no}` }))))
        setDatasetOptions(datasetVersions.flat())
        const environments = await listEnvironments()
        const envVersions = await Promise.all(environments.map(async item => (await listEnvironmentVersions(item.id)).filter(version => version.status === 'READY').map(version => ({ id: version.id, label: `${item.name} · v${version.version_no}` }))))
        setEnvironmentOptions(envVersions.flat())
      }
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '无法连接本地 API')
    } finally { setLoading(false) }
  }, [section])
  useEffect(() => { void load() }, [load])
  const selectedTemplateOption = templateOptions.find(option => option.id === selectedTemplateVersionId)
  const canSubmitExperiment = Boolean(section === 'experiments' && draftName.trim() && selectedTemplateVersionId && selectedDatasetVersionId && selectedEnvironmentVersionId)
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
        const selectedTemplate = templateOptions.find(option => option.id === selectedTemplateVersionId)
        if (!selectedTemplate) throw new Error('请选择一个可执行模板版本；请先在“模型代码 / 模板”中为代码版本创建模板。')
        if (!selectedDatasetVersionId || !selectedEnvironmentVersionId) throw new Error('请明确选择数据版本与运行环境版本后再提交。')
        const draft = await createDraft(draftName.trim(), '通过前端真实 API 创建')
        await updateDraft(draft.id, {
          dataset_version_id: selectedDatasetVersionId,
          code_version_id: selectedTemplate.codeVersionId,
          template_version_id: selectedTemplate.id,
          environment_version_id: selectedEnvironmentVersionId,
          parameter_values: {},
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
    {section === 'datasets' && <DatasetImportPanel reload={load} />}
    {section === 'checkpoints' && <section className="section-block"><div className="section-heading"><div><h2>复用兼容性校验</h2><p>使用当前 Checkpoint 的冻结来源配置执行 Resume 校验。</p></div><button className="button primary" onClick={() => void runOperation('checkpoint')} disabled={submitting}>{submitting ? '正在校验…' : '校验 Resume 兼容性'}</button></div></section>}
    {section === 'results' && <section className="section-block"><div className="section-heading"><div><h2>结果操作</h2><p>以下操作调用正式指标、绘图规格、导出清单与结果对比 API。</p></div><div className="page-actions"><button className="button secondary" onClick={() => void runOperation('metrics')} disabled={submitting}>读取指标</button><button className="button secondary" onClick={() => void runOperation('plot')} disabled={submitting}>创建绘图</button><button className="button secondary" onClick={() => void runOperation('export')} disabled={submitting}>创建导出</button><button className="button primary" onClick={() => void runOperation('compare')} disabled={submitting}>比较结果</button></div></div></section>}
    {section === 'experiments' && <section className="experiment-launch-card"><div className="experiment-launch-head"><div><p className="eyebrow">NEW RUN</p><h2>创建训练实验</h2><p>明确选择代码模板、数据版本与运行环境后，冻结配置并创建一个独立的队列 Run。</p></div><span className="status-badge neutral">冻结提交</span></div><div className="experiment-launch-grid"><div className="experiment-config"><div className="experiment-step"><span>01</span><div><b>实验标识</b><small>该名称将用于实验、Run 与结果追溯。</small></div></div><label>实验名称 <em>必填</em><input value={draftName} onChange={event => setDraftName(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') void create() }} placeholder="例如：北江 Top-30 迁移训练" /></label><div className="experiment-step"><span>02</span><div><b>可执行代码与入口</b><small>模板固定关联一个不可变 CodeVersion 和 argv 训练入口。</small></div></div><label>训练模板版本 <em>必填</em><select value={selectedTemplateVersionId} onChange={event => setSelectedTemplateVersionId(event.target.value)}><option value="">请选择一个代码模板版本</option>{templateOptions.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}</select></label>{selectedTemplateOption && <div className="selected-template"><FileCode2 size={16}/><div><b>已选择可执行模板</b><span>{selectedTemplateOption.label}</span><code>CodeVersion {selectedTemplateOption.codeVersionId.slice(0, 8)}</code></div></div>}<div className="experiment-step"><span>03</span><div><b>目标数据版本</b><small>只能选择 READY 数据版本；提交后冻结为不可变输入。</small></div></div><label>数据版本 <em>必填</em><select value={selectedDatasetVersionId} onChange={event => setSelectedDatasetVersionId(event.target.value)}><option value="">选择一个 READY 数据版本</option>{datasetOptions.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}</select></label><div className="experiment-step"><span>04</span><div><b>运行环境版本</b><small>选择 READY 环境版本作为执行镜像。</small></div></div><label>运行环境版本 <em>必填</em><select value={selectedEnvironmentVersionId} onChange={event => setSelectedEnvironmentVersionId(event.target.value)}><option value="">选择一个 READY 运行环境</option>{environmentOptions.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}</select></label></div><aside className="experiment-freeze-summary"><p className="eyebrow">FROZEN INPUTS</p><h3>本次提交将冻结</h3><div><Database size={15}/><span><b>数据版本</b><small>{datasetOptions.find(option => option.id === selectedDatasetVersionId)?.label ?? '未选择'}</small></span><StatusBadge status={selectedDatasetVersionId ? 'READY' : 'PENDING'}/></div><div><FileCode2 size={15}/><span><b>代码与模板</b><small>{selectedTemplateOption ? `模板 ${selectedTemplateOption.id.slice(0, 8)} · 代码 ${selectedTemplateOption.codeVersionId.slice(0, 8)}` : '请选择代码模板版本'}</small></span><StatusBadge status={selectedTemplateOption ? 'READY' : 'PENDING'}/></div><div><HardDrive size={15}/><span><b>运行环境</b><small>{environmentOptions.find(option => option.id === selectedEnvironmentVersionId)?.label ?? '未选择'}</small></span><StatusBadge status={selectedEnvironmentVersionId ? 'READY' : 'PENDING'}/></div><p className="experiment-dispatch-note">提交会真实创建 Draft、冻结 ExperimentVersion 并进入队列；当前 Fake Runner 只模拟调度和事件，不执行真实 GPU 训练。</p></aside></div><footer className="experiment-launch-footer"><div><b>提交前检查</b><span>{canSubmitExperiment ? '已完成全部必填选择；提交后配置不可修改。' : '请完成实验名称、代码模板、数据版本与运行环境的选择。'}</span></div><button className="button primary" onClick={() => void create()} disabled={submitting || !canSubmitExperiment}><FlaskConical size={15}/>{submitting ? '正在冻结并提交…' : '冻结配置并创建 Run'}</button></footer>{!templateOptions.length && <p className="error-notice">尚无可执行模板。请先在“模型代码 / 模板”的代码版本详情中创建训练入口。</p>}</section>}
    <section className="section-block"><div className="section-heading"><div><h2>{loading ? '正在加载后端资源…' : `共 ${items.length} 项`}</h2><p>受保护 API · Token 自动恢复 · 后端重启后可重新登录</p></div></div>
    <div className="asset-list">{items.map(item => <div key={item.id}><HardDrive size={16}/><span><b>{item.name}</b><small>{item.subtitle}</small></span><code>{item.metadata.version ?? item.metadata.nse ?? item.metadata.mode ?? item.metadata.runs ?? item.metadata.model_signature ?? '—'}</code><StatusBadge status={item.status === 'SUCCEEDED' || item.status === 'READY' || item.status === 'COMPATIBLE' ? '已完成' : item.status}/></div>)}{!loading && !items.length && <p>当前没有可访问资源。</p>}</div>
    </section>
  </div>
}

function LoginScreen({ onLoggedIn }: { onLoggedIn: (user: ApiUser) => void }) {
  const [email, setEmail] = useState('admin@hydrolab.cn')
  const [password, setPassword] = useState('admin123456')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const submit = async () => {
    if (!email.trim() || !password) { setError('请输入邮箱和密码'); return }
    setSubmitting(true); setError(null)
    try { onLoggedIn(await login(email.trim(), password)) } catch (cause) { setError(cause instanceof ApiError ? cause.message : '登录失败') } finally { setSubmitting(false) }
  }
  return <main className="login-page"><section className="login-card"><div className="login-brand"><div className="brand-mark"><Activity size={20}/></div><div><b>HydroLab</b><span>EXPERIMENT OS</span></div></div><p className="eyebrow">SIGN IN</p><h1>登录实验平台</h1><p>使用你的账户访问已授权的数据、代码、实验与结果资产。</p><label>邮箱<input type="email" value={email} onChange={event => setEmail(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') void submit() }} /></label><label>密码<input type="password" value={password} onChange={event => setPassword(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') void submit() }} /></label>{error && <p className="error-notice">登录失败：{error}</p>}<button className="button primary" onClick={() => void submit()} disabled={submitting}>{submitting ? '正在登录…' : '登录 HydroLab'}<ChevronRight size={15}/></button><small>本地联调账号：<code>admin@hydrolab.cn</code> / <code>admin123456</code></small></section></main>
}

function AccountMenu({ user, close, onLogout }: { user: ApiUser; close: () => void; onLogout: () => void }) {
  const initials = user.display_name.slice(0, 2).toUpperCase()
  return <div className="account-menu"><div className="account-menu-user"><div className="avatar">{initials}</div><div><b>{user.display_name}</b><small>{user.email}</small></div></div><div className="account-menu-meta"><span>{user.is_admin ? '管理员' : '成员'}</span><span>{user.status}</span></div><button onClick={() => { close(); onLogout() }}>退出并切换账号</button></div>
}

export default function App() {
  const [user, setUser] = useState<ApiUser | null>(() => getStoredUser())
  const [accountOpen, setAccountOpen] = useState(false)
  const [view, setView] = useState<View>('dashboard')
  const [runId, setRunId] = useState<string | null>(null)
  const [wizardOpen, setWizardOpen] = useState(false)
  const [batchOpen, setBatchOpen] = useState(false)
  const [gpuOpen, setGpuOpen] = useState(false)
  const [datasetCreateOpen, setDatasetCreateOpen] = useState(false)
  const [selectedResult, setSelectedResult] = useState<ApiResult | null>(null)
  const [compareResultIds, setCompareResultIds] = useState<string[]>([])
  const [menuOpen, setMenuOpen] = useState(false)
  const [theme, setTheme] = useState<Theme>('system')
  const resolvedDark = useMemo(() => theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches), [theme])
  useEffect(() => { document.documentElement.classList.toggle('dark', resolvedDark) }, [resolvedDark])
  const cycleTheme = () => setTheme(t => t === 'system' ? 'light' : t === 'light' ? 'dark' : 'system')
  const ThemeIcon = theme === 'dark' ? Moon : theme === 'light' ? Sun : Settings
  // 仅在挂载时用 /me 校验一次已登录用户，避免随 user 变化反复刷新造成循环。
  const initialUserRef = useRef(user)
  useEffect(() => {
    const initial = initialUserRef.current
    if (!initial) return
    void getCurrentUser().then(setUser).catch(() => setUser(null))
  }, [])
  const handleLogout = async () => { await logout(); setAccountOpen(false); setUser(null); setView('dashboard') }
  if (!user) return <LoginScreen onLoggedIn={setUser} />
  const openRun = (id: string) => { setRunId(id); setView('run') }
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
              <button key={id} className={active ? 'active' : ''} onClick={() => { setView(id); setSelectedResult(null); setCompareResultIds([]); setMenuOpen(false) }}>
                <Icon size={17} />{label}
              </button>
            )
          })}
          <span className="nav-label">ACCOUNT</span>
          <button onClick={() => setView('permissions')} className={view==='permissions'?'active':''}><Settings size={17} />权限与分享</button>
          <button onClick={() => setView('environments')} className={view==='environments'?'active':''}><HardDrive size={17} />运行环境</button>
        </nav>
        <div className="sidebar-footer">
          <div className="server-health"><span /><div><b>服务运行正常</b><small>本地 Fake/InMemory API</small></div></div>
          <div className="account-anchor"><button onClick={() => setAccountOpen(open => !open)} aria-expanded={accountOpen}><div className="avatar">{user.display_name.slice(0, 2).toUpperCase()}</div><div><b>{user.display_name}</b><small>{user.is_admin ? '管理员' : '成员'}</small></div><ChevronRight size={14} /></button>{accountOpen && <AccountMenu user={user} close={() => setAccountOpen(false)} onLogout={() => void handleLogout()} />}</div>
        </div>
      </aside>
      {menuOpen && <button className="mobile-overlay" aria-label="关闭导航" onClick={() => setMenuOpen(false)} />}
      <main className="main-area">
        <div className="topbar">
          <button className="icon-button menu-button" onClick={() => setMenuOpen(true)} aria-label="打开导航"><Menu size={18} /></button>
          <div className="project-switcher"><span className="project-dot" /><b>水文时序实验平台</b><span className="flow-label">数据 → 实验 → 结果</span></div>
          <div className="top-actions">
            <span className="prototype-badge">已连接本地 API</span>
            <button className="icon-button" onClick={cycleTheme} title={`主题：${theme}`} aria-label="切换明暗主题"><ThemeIcon size={17} /></button>
            <button className="icon-button" aria-label="设置"><Settings size={17} /></button>
          </div>
        </div>
        <div className="content-area">
          {view === 'dashboard' && <Dashboard openRun={openRun} openWizard={() => setWizardOpen(true)} openBatch={() => setBatchOpen(true)} openGpu={() => setGpuOpen(true)} />}
          {view === 'datasets' && <ApiCatalogPage section="datasets" />}
          {view === 'code' && <CodeRepositoryPanel />}
          {view === 'checkpoints' && <ApiCatalogPage section="checkpoints" />}
          {view === 'experiments' && <ApiCatalogPage section="experiments" />}
          {view === 'results' && (selectedResult
            ? <ResultDetail result={selectedResult} back={() => setSelectedResult(null)} onChanged={() => setCompareResultIds([])} />
            : compareResultIds.length
              ? <RunComparison resultIds={compareResultIds} back={() => setCompareResultIds([])} />
              : <ResultIndex onOpen={setSelectedResult} onCompare={setCompareResultIds} />)}
          {view === 'permissions' && <AssetAdminPage type="permissions" />}
          {view === 'environments' && <ApiCatalogPage section="environments" />}
          {view === 'run' && <RunDetail runId={runId} back={() => setView('dashboard')} />}
        </div>
      </main>
      {wizardOpen && <ExperimentWizard close={() => setWizardOpen(false)} />}
      {batchOpen && <BatchSubmitPanel close={() => setBatchOpen(false)} />}
      {gpuOpen && <GpuDrawer close={() => setGpuOpen(false)} />}
      {datasetCreateOpen && <DatasetCreateModal close={() => setDatasetCreateOpen(false)} />}
    </div>
  )
}
