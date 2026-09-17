export type ApiCatalogItem = { id: string; name: string; subtitle: string; status: string; metadata: Record<string, string> }
export type ApiDraft = { id: string; name: string; description: string; dataset_version_id: string | null; code_version_id: string | null; template_version_id: string | null; environment_version_id: string | null; parameter_values: Record<string, unknown> }
export type ApiResult = { id: string; run_id: string; dataset_version_id: string; created_at: string }
export type ApiCompatibility = { status: 'COMPATIBLE' | 'REPAIRABLE' | 'INCOMPATIBLE'; blockers: string[]; warnings: string[]; repair_plan: { code: string; title: string }[] }
export type ApiHealthComponent = { backend: string; healthy: boolean; detail: string | null }
export type ApiHealthReady = { status: string; environment: string; components: Record<string, ApiHealthComponent> }
export type ApiEnvironmentVersion = { id: string; version_no: number; status: string }

export type ApiSubmitResponse = { experiment: { id: string; name: string; description: string }; version: { id: string; version_no: number }; run: { id: string; status: string } }
export type ApiMetric = { name: string; value: number; split: string; horizon: number | null; basin_id: string | null; event_id: string | null }
export type ApiCheckpoint = { id: string; source_config: Record<string, unknown>; model_signature: string }
export type ApiComparison = { metrics: Record<string, Record<string, number>>; delta_from_baseline: Record<string, Record<string, number>>; baseline_result_id: string; dataset_version_id: string }
export type ApiBatchSubmitItem = { dataset_version_id: string; name: string; argv: string[]; parameter_values: Record<string, unknown>; run: { id: string; status: string } | null }
export type ApiBatchSubmitResponse = { dry_run: boolean; items: ApiBatchSubmitItem[] }
export type ApiArtifact = { id: string; result_id: string; kind: string; object_key: string; sha256: string }
export type ApiPlotResponse = { plot: { id: string; plot_type: string }; artifacts: ApiArtifact[] }
export type ApiExport = { id: string; manifest: { format: string; object_key: string; sha256: string; size_bytes: number; files: string[] } }
export type ApiDataset = { id: string; name: string; description: string }
export type ApiEnvironment = { id: string; name: string; description: string }

export type ApiTemplate = { id: string; code_repository_id: string; name: string; description: string }
export type ApiTemplateVersion = { id: string; version_no: number; code_version_id: string; mode: string; argv: string[]; parameters: unknown[] }
export type ApiCodeRepository = { id: string; name: string; description: string }
export type ApiCodeVersion = { id: string; version_no: number; source_type: 'ZIP' | 'GIT'; status: string; object_key: string | null; source_ref: string | null; commit_sha: string | null; content_hash: string | null; manifest: { files?: string[]; file_count?: number; detected_manifests?: string[] } }
export type ApiDatasetImport = { id: string; dataset_id: string; status: string; source_type: string; detected_format: string; progress: number; error_code: string | null }
export type ApiMappingItem = { source_name: string; standard_name: string | null; semantic: string; unit: string | null; order: number; confidence: number; user_modified: boolean }
export type ApiFieldMapping = { id: string; import_job_id: string; items: ApiMappingItem[]; created_at: string; confirmed_at: string | null }
export type ApiDatasetVersion = { id: string; version_no: number; status: string; content_hash: string | null; manifest: Record<string, unknown> }

export type ApiDirectoryPreview = { source_path: string; content_hash: string; file_count: number; uncompressed_bytes: number; archive_bytes: number; files: string[]; detected_manifests: string[]; entrypoints: string[]; skipped_sample: string[] }
export type ApiDirectoryImport = { code_version: ApiCodeVersion; preview: ApiDirectoryPreview }
export type ApiRunLog = { id: number; run_id: string; content: string; stream: string; created_at: string }
export type ApiCollectedMetric = { name: string; value: number; split: string; horizon: number | null }
export type ApiCollectedArtifact = { kind: string; relative_path: string; object_key: string; sha256: string; size_bytes: number }
export type ApiRunCollection = { collected: boolean; experiment_dirs?: string[]; metrics: ApiCollectedMetric[]; artifacts: ApiCollectedArtifact[]; warnings: string[] }
export type ApiRunIngest = { result: ApiResult; metrics_added: number; artifacts_added: number; experiment_dirs?: string[]; warnings: string[] }

export type ApiRunSummary = { id: string; experiment_id: string; experiment_name: string; experiment_version_id: string; status: string; argv: string[]; parameters: Record<string, unknown>; dataset_version_id: string | null; code_version_id: string | null; template_version_id: string | null; environment_version_id: string | null; created_at: string | null }
export type ApiRunStage = { name: string; position: number; status: string }
export type ApiRunEvent = { id: number; event_type: string; run_id: string; occurred_at: string; payload: Record<string, unknown> }
export type ApiResourceSample = { run_id: string; gpu_index: number; utilization_percent: number; memory_used_mb: number; memory_total_mb: number; sampled_at: string }

export type ApiUser = { id: string; email: string; display_name: string; is_admin: boolean; status: string }
type LoginResponse = { tokens: { access_token: string; refresh_token: string }; user: ApiUser }
const TOKEN_KEY = 'hydrolab-api-token'
const REFRESH_KEY = 'hydrolab-api-refresh-token'
const USER_KEY = 'hydrolab-api-user'
const API_ROOT = '/api/v1'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
  static isNetwork(error: unknown): boolean { return error instanceof TypeError }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = sessionStorage.getItem(TOKEN_KEY)
  let response: Response
  try {
    response = await fetch(`${API_ROOT}${path}`, { ...init, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init.headers } })
  } catch {
    // 网络断开 / 后端不可达：统一为可识别错误，避免被当作业务空结果吞掉。
    throw new ApiError(0, '无法连接 API 服务，请检查后端是否已启动。')
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: unknown; error?: { message?: string } } | null
    const detail = typeof body?.detail === 'string' ? body.detail : null
    throw new ApiError(response.status, body?.error?.message ?? detail ?? `请求失败（${response.status}）`)
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>
}

export const getStoredUser = (): ApiUser | null => {
  const raw = sessionStorage.getItem(USER_KEY)
  try { return raw ? JSON.parse(raw) as ApiUser : null } catch { return null }
}
const storeSession = (tokens: LoginResponse['tokens'], user: ApiUser) => {
  sessionStorage.setItem(TOKEN_KEY, tokens.access_token)
  sessionStorage.setItem(REFRESH_KEY, tokens.refresh_token)
  sessionStorage.setItem(USER_KEY, JSON.stringify(user))
}
const clearSession = () => {
  sessionStorage.removeItem(TOKEN_KEY)
  sessionStorage.removeItem(REFRESH_KEY)
  sessionStorage.removeItem(USER_KEY)
}
export const login = async (email: string, password: string): Promise<ApiUser> => {
  const result = await request<LoginResponse>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })
  storeSession(result.tokens, result.user)
  return result.user
}
export const getCurrentUser = async () => {
  const user = await request<ApiUser>('/me')
  sessionStorage.setItem(USER_KEY, JSON.stringify(user))
  return user
}
export const logout = async () => {
  try { await request<void>('/auth/logout', { method: 'POST' }) } finally { clearSession() }
}
export async function ensureDevSession(): Promise<string> {
  const token = sessionStorage.getItem(TOKEN_KEY)
  if (!token) throw new ApiError(401, '请先登录后再继续操作')
  return getStoredUser()?.display_name ?? '当前用户'
}

let refreshInFlight: Promise<void> | null = null
async function refreshSession(): Promise<void> {
  const refreshToken = sessionStorage.getItem(REFRESH_KEY)
  if (!refreshToken) throw new ApiError(401, '会话已过期，请重新登录')
  // 单飞刷新：并发 401 共享同一次 refresh，避免相互覆盖 Token 或无限刷新。
  if (!refreshInFlight) {
    refreshInFlight = request<LoginResponse>('/auth/refresh', { method: 'POST', body: JSON.stringify({ refresh_token: refreshToken }) })
      .then(result => storeSession(result.tokens, result.user))
      .catch(error => { clearSession(); throw error })
      .finally(() => { refreshInFlight = null })
  }
  await refreshInFlight
}

async function withSessionRetry<T>(operation: () => Promise<T>): Promise<T> {
  try {
    return await operation()
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      // access token 失效：仅允许一次 refresh + 原请求重试；refresh 失败会清会话并抛错回到登录页。
      await refreshSession()
      return await operation()
    }
    throw error
  }
}
const authed = <T>(path: string, init?: RequestInit) => withSessionRetry(() => request<T>(path, init))

export const seedDemo = () => authed<Record<string, string>>('/dev-demo/seed', { method: 'POST' })
// 健康检查：无需登录；/api/v1 下的 health 由后端同时挂载，便于反向代理按 /api 前缀转发。
export const getHealthReady = () => request<ApiHealthReady>('/health/ready')
export async function getRealSection(section: 'datasets' | 'code' | 'experiments' | 'checkpoints' | 'results'): Promise<ApiCatalogItem[]> {
  const paths: Record<typeof section, string[]> = {
    datasets: ['/datasets'],
    code: ['/code-repositories', '/templates'],
    experiments: ['/experiments'],
    checkpoints: ['/checkpoints'],
    results: ['/results'],
  }
  const groups = await Promise.all(paths[section].map(path => authed<Array<Record<string, unknown>>>(path)))
  const short = (value: unknown) => String(value ?? '').slice(0, 8)
  return groups.flat().map(item => {
    const fallbackName = section === 'checkpoints'
      ? `Checkpoint ${short(item.id)} · ${String(item.model_signature ?? '未知签名')}`
      : section === 'results'
        ? `结果 ${short(item.id)} · Run ${short(item.run_id)}`
        : `资源 ${short(item.id)}`
    const fallbackSubtitle = section === 'checkpoints'
      ? `来源 Run ${short(item.source_run_id)} · ${item.optimizer_included ? '含 Optimizer' : '仅权重'}`
      : section === 'results'
        ? `冻结数据版本 ${short(item.dataset_version_id)}`
        : '已从后端读取'
    return {
      id: String(item.id),
      name: String(item.name ?? fallbackName),
      subtitle: String(item.description || fallbackSubtitle),
      status: String(item.status ?? 'READY'),
      metadata: Object.fromEntries(Object.entries(item).filter(([, value]) => typeof value === 'string').map(([key, value]) => [key, String(value)])),
    }
  })
}
export const listTemplates = () => authed<ApiTemplate[]>('/templates')
export const createTemplate = (repositoryId: string, name: string, description: string) => authed<ApiTemplate>('/templates', { method: 'POST', body: JSON.stringify({ code_repository_id: repositoryId, name, description }) })
export const listTemplateVersions = (templateId: string) => authed<ApiTemplateVersion[]>(`/templates/${templateId}/versions`)
export const createTemplateVersion = (templateId: string, codeVersionId: string, argv: string[]) => authed<ApiTemplateVersion>(`/templates/${templateId}/versions`, { method: 'POST', body: JSON.stringify({ code_version_id: codeVersionId, mode: 'TRAIN', argv, parameters: [], input_contract: {}, output_contract: {} }) })
export const createCodeRepository = (name: string, description: string) => authed<ApiCodeRepository>('/code-repositories', { method: 'POST', body: JSON.stringify({ name, description }) })
export const listCodeRepositories = () => authed<ApiCodeRepository[]>('/code-repositories')
export const listCodeVersions = (repositoryId: string) => authed<ApiCodeVersion[]>(`/code-repositories/${repositoryId}/versions`)
export const importCodeZip = (repositoryId: string, filename: string, contentBase64: string) => authed<ApiCodeVersion>(`/code-repositories/${repositoryId}/zip-imports`, { method: 'POST', body: JSON.stringify({ filename, content_base64: contentBase64 }) })
export const importCodeGit = (repositoryId: string, sourceRef: string, commitSha: string) => authed<ApiCodeVersion>(`/code-repositories/${repositoryId}/git-imports`, { method: 'POST', body: JSON.stringify({ source_ref: sourceRef, commit_sha: commitSha || null }) })
export const listCodeImportRoots = () => authed<string[]>('/code-import-roots')
export const previewDirectoryImport = (path: string) => authed<ApiDirectoryPreview>('/code-import-previews', { method: 'POST', body: JSON.stringify({ path, extra_ignore: [] }) })
export const importCodeDirectory = (repositoryId: string, path: string) => authed<ApiDirectoryImport>(`/code-repositories/${repositoryId}/directory-imports`, { method: 'POST', body: JSON.stringify({ path, extra_ignore: [] }) })
export const startRun = (runId: string, gpuCount = 1) => authed<{ id: string; status: string }>(`/runs/${runId}/start`, { method: 'POST', body: JSON.stringify({ gpu_count: gpuCount }) })
export const cancelRealRun = (runId: string) => authed<{ id: string; status: string }>(`/runs/${runId}/cancel`, { method: 'POST' })
export const awaitRun = (runId: string, timeoutSeconds = 1800) => authed<{ id: string; status: string }>(`/runs/${runId}/await`, { method: 'POST', body: JSON.stringify({ timeout_seconds: timeoutSeconds }) })
export const listRuns = () => authed<ApiRunSummary[]>('/runs')
export const getRun = (runId: string) => authed<ApiRunSummary>(`/runs/${runId}`)
export const getRunStages = (runId: string) => authed<ApiRunStage[]>(`/runs/${runId}/stages`)
export const getRunEvents = (runId: string, afterId = 0) => authed<ApiRunEvent[]>(`/runs/${runId}/events?after_id=${afterId}`)
export const getRunResources = (runId: string) => authed<ApiResourceSample[]>(`/runs/${runId}/resources`)
export const getRunLogs = (runId: string, afterId = 0) => authed<ApiRunLog[]>(`/runs/${runId}/logs?after_id=${afterId}`)
export const getRunCollection = (runId: string) => authed<ApiRunCollection>(`/runs/${runId}/collection`)
export const ingestRunResult = (runId: string) => authed<ApiRunIngest>(`/runs/${runId}/result/ingest`, { method: 'POST' })
export const dispatchOutbox = () => authed<{ dispatched: number }>('/internal/outbox/dispatch', { method: 'POST' })

export function subscribeRunEvents(runId: string, onEvent: (event: ApiRunEvent) => void, signal: AbortSignal, onError?: (error: unknown) => void) {
  let lastId = 0
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  const connect = async () => {
    if (signal.aborted) return
    try {
      const token = sessionStorage.getItem(TOKEN_KEY)
      const response = await fetch(`${API_ROOT}/runs/${runId}/events/stream`, {
        headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(lastId > 0 ? { 'Last-Event-ID': String(lastId) } : {}) },
        signal,
      })
      if (!response.ok || !response.body) {
        // 非 2xx（如权限失效）不自动重连，避免 401 风暴；交给上层提示与决策。
        if (!response.ok) onError?.(new ApiError(response.status, `事件流不可用（${response.status}）`))
        else if (!response.body && !signal.aborted) onError?.(new ApiError(0, '事件流缺少响应体'))
        return
      }
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (!signal.aborted) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        let boundary: number
        while ((boundary = buffer.indexOf('\n\n')) !== -1) {
          const block = buffer.slice(0, boundary)
          buffer = buffer.slice(boundary + 2)
          const idLine = block.split('\n').find(line => line.startsWith('id:'))
          const eventLine = block.split('\n').find(line => line.startsWith('event:'))
          const dataLine = block.split('\n').find(line => line.startsWith('data:'))
          if (idLine && dataLine) {
            lastId = Number(idLine.slice(3).trim()) || 0
            try {
              const payload = JSON.parse(dataLine.slice(5).trim()) as Record<string, unknown>
              onEvent({ id: lastId, event_type: (eventLine?.slice(6).trim() ?? 'message'), run_id: runId, occurred_at: '', payload })
            } catch { /* 忽略无法解析的事件块 */ }
          }
        }
      }
    } catch (error) {
      if (!signal.aborted) onError?.(error)
    } finally {
      // 正常/瞬断后保留 Last-Event-ID 重连；Abort（终态/卸载）后清理计时器，不再重连。
      if (!signal.aborted && reconnectTimer === null) {
        reconnectTimer = setTimeout(() => { reconnectTimer = null; void connect() }, 1500)
      }
    }
  }
  signal.addEventListener('abort', () => { if (reconnectTimer !== null) { clearTimeout(reconnectTimer); reconnectTimer = null } })
  void connect()
}
export const createDataset = (name: string, description: string) => authed<ApiCatalogItem>('/datasets', { method: 'POST', body: JSON.stringify({ name, description }) })
export const createDatasetImport = (datasetId: string) => authed<ApiDatasetImport>('/dataset-imports', { method: 'POST', body: JSON.stringify({ dataset_id: datasetId, source_type: 'UPLOAD' }), headers: { 'Idempotency-Key': crypto.randomUUID() } })
export const fakeUploadDataset = (jobId: string, filename: string, content: string) => authed<ApiDatasetImport>(`/dataset-imports/${jobId}/fake-upload`, { method: 'POST', body: JSON.stringify({ filename, content }) })
export const getDatasetMapping = (jobId: string) => authed<ApiFieldMapping>(`/dataset-imports/${jobId}/mapping`)
export const confirmDatasetMapping = (jobId: string, items: ApiMappingItem[]) => authed<ApiDatasetVersion>(`/dataset-imports/${jobId}/confirm-mapping`, { method: 'POST', body: JSON.stringify({ items }) })
export const listDatasets = () => authed<ApiDataset[]>('/datasets')
export const listDatasetVersions = (datasetId: string) => authed<ApiDatasetVersion[]>(`/datasets/${datasetId}/versions`)
export const listEnvironments = () => authed<ApiEnvironment[]>('/environments')
export const listEnvironmentVersions = (environmentId: string) => authed<ApiEnvironmentVersion[]>(`/environments/${environmentId}/versions`)
export const createEnvironment = (name: string, description: string) => authed<ApiEnvironment>('/environments', { method: 'POST', body: JSON.stringify({ name, description }) })
export const createEnvironmentVersion = (environmentId: string, body: { base_image: string; python_version: string; dependency_file?: string | null; dependency_content?: string | null }) => authed<ApiEnvironmentVersion>(`/environments/${environmentId}/versions`, { method: 'POST', body: JSON.stringify(body) })
export const submitBatch = (body: { name_prefix: string; description: string; dataset_version_ids: string[]; code_version_id: string; template_version_id: string; environment_version_id: string; parameter_values: Record<string, unknown>; dry_run: boolean }) => authed<ApiBatchSubmitResponse>('/runs/batch', { method: 'POST', body: JSON.stringify(body) })
export const createDraft = (name: string, description: string) => authed<ApiDraft>('/experiment-drafts', { method: 'POST', body: JSON.stringify({ name, description }) })
export const listDrafts = () => authed<ApiDraft[]>('/experiment-drafts')
export const updateDraft = (draftId: string, patch: Partial<Pick<ApiDraft, 'dataset_version_id' | 'code_version_id' | 'template_version_id' | 'environment_version_id' | 'parameter_values'>>) => authed<ApiDraft>(`/experiment-drafts/${draftId}`, { method: 'PATCH', body: JSON.stringify(patch) })
export const submitDraft = (draftId: string) => authed<ApiSubmitResponse>(`/experiment-drafts/${draftId}/submit`, { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() } })
export const checkCheckpoint = (checkpointId: string, mode: 'RESUME' | 'FINETUNE' | 'EVALUATE' | 'PREDICT', candidate: Record<string, unknown>) => authed<ApiCompatibility>(`/checkpoints/${checkpointId}/compatibility`, { method: 'POST', body: JSON.stringify({ mode, candidate }) })
export const listCheckpoints = () => authed<ApiCheckpoint[]>('/checkpoints')
export const listResults = () => authed<ApiResult[]>('/results')
export const listMetrics = (resultId: string) => authed<ApiMetric[]>(`/results/${resultId}/metrics`)
export const compareResults = (resultIds: string[]) => authed<ApiComparison>('/results/compare', { method: 'POST', body: JSON.stringify({ result_ids: resultIds }) })
export const createPlot = (resultIds: string[], plotType: 'grouped_metrics' | 'horizon_lines' | 'nse_kge_panels' | 'basin_metric_distribution' = 'grouped_metrics', options: Record<string, unknown> = {}) => authed<ApiPlotResponse>('/plots', { method: 'POST', body: JSON.stringify({ result_ids: resultIds, plot_type: plotType, data_selection: {}, options }) })
export const createExport = (resultIds: string[], artifactIds: string[] = []) => authed<ApiExport>('/exports', { method: 'POST', body: JSON.stringify({ result_ids: resultIds, artifact_ids: artifactIds }) })
