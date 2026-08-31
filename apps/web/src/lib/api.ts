export type ApiRunStatus = 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'CANCELLED'

export type ApiRun = { id: string; name: string; model: string; dataset: string; gpu: string; epoch: number; total_epochs: number; nse: number | null; status: ApiRunStatus; eta: string | null }
export type ApiCatalogItem = { id: string; name: string; subtitle: string; status: string; metadata: Record<string, string> }
export type ApiCatalog = { datasets: ApiCatalogItem[]; code_repositories: ApiCatalogItem[]; templates: ApiCatalogItem[]; environments: ApiCatalogItem[]; experiments: ApiCatalogItem[]; checkpoints: ApiCatalogItem[]; results: ApiCatalogItem[] }
export type ApiDraft = { id: string; name: string; description: string; dataset_version_id: string | null; code_version_id: string | null; template_version_id: string | null; environment_version_id: string | null; parameter_values: Record<string, unknown> }
export type ApiResult = { id: string; run_id: string; dataset_version_id: string; created_at: string }
export type ApiCompatibility = { status: 'COMPATIBLE' | 'REPAIRABLE' | 'INCOMPATIBLE'; blockers: string[]; warnings: string[]; repair_plan: { code: string; title: string }[] }

type LoginResponse = { tokens: { access_token: string }; user: { display_name: string } }
type Workspace = { user_name: string; runs: ApiRun[]; gpu_count: number; queued_count: number }
const TOKEN_KEY = 'hydrolab-api-token'
const API_ROOT = '/api/v1'

export class ApiError extends Error { constructor(public status: number, message: string) { super(message) } }

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = sessionStorage.getItem(TOKEN_KEY)
  const response = await fetch(`${API_ROOT}${path}`, { ...init, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init.headers } })
  if (!response.ok) { const body = await response.json().catch(() => null) as { detail?: string; error?: { message?: string } } | null; throw new ApiError(response.status, body?.error?.message ?? body?.detail ?? `请求失败（${response.status}）`) }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>
}

export async function ensureDevSession(): Promise<string> {
  const token = sessionStorage.getItem(TOKEN_KEY)
  if (token) return token
  const result = await request<LoginResponse>('/auth/login', { method: 'POST', body: JSON.stringify({ email: 'admin@hydrolab.cn', password: 'admin123456' }) })
  sessionStorage.setItem(TOKEN_KEY, result.tokens.access_token)
  return result.user.display_name
}

async function withSessionRetry<T>(operation: () => Promise<T>): Promise<T> {
  try { return await operation() } catch (error) { if (!(error instanceof ApiError) || error.status !== 401) throw error; sessionStorage.removeItem(TOKEN_KEY); await ensureDevSession(); return operation() }
}
const authed = <T>(path: string, init?: RequestInit) => withSessionRetry(() => request<T>(path, init))

export const seedDemo = () => authed<Record<string, string>>('/dev-demo/seed', { method: 'POST' })
export const getWorkspace = () => authed<Workspace>('/dev-demo/workspace')
export async function getRealSection(section: 'datasets' | 'code' | 'experiments' | 'checkpoints' | 'results' | 'environments'): Promise<ApiCatalogItem[]> {
  const paths: Record<typeof section, string[]> = {
    datasets: ['/datasets'],
    code: ['/code-repositories', '/templates'],
    experiments: ['/experiments'],
    checkpoints: ['/checkpoints'],
    results: ['/results'],
    environments: ['/environments'],
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
export const advanceRun = (runId: string) => authed<ApiRun>(`/dev-demo/runs/${runId}/advance`, { method: 'POST' })
export const cancelRun = (runId: string) => authed<ApiRun>(`/dev-demo/runs/${runId}/cancel`, { method: 'POST' })
export const createDataset = (name: string, description: string) => authed<ApiCatalogItem>('/datasets', { method: 'POST', body: JSON.stringify({ name, description }) })
export const createDraft = (name: string, description: string) => authed<ApiDraft>('/experiment-drafts', { method: 'POST', body: JSON.stringify({ name, description }) })
export const checkCheckpoint = (checkpointId: string, mode: string, candidate: Record<string, unknown>) => authed<ApiCompatibility>(`/checkpoints/${checkpointId}/compatibility`, { method: 'POST', body: JSON.stringify({ mode, candidate }) })
export const listResults = () => authed<ApiResult[]>('/results')
