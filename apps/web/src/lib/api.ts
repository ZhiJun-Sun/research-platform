export type ApiRunStatus = 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'CANCELLED'

export type ApiRun = {
  id: string
  name: string
  model: string
  dataset: string
  gpu: string
  epoch: number
  total_epochs: number
  nse: number | null
  status: ApiRunStatus
  eta: string | null
}

type LoginResponse = { tokens: { access_token: string }; user: { display_name: string } }
type Workspace = { user_name: string; runs: ApiRun[]; gpu_count: number; queued_count: number }

const TOKEN_KEY = 'hydrolab-api-token'
const API_ROOT = '/api/v1'

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = sessionStorage.getItem(TOKEN_KEY)
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new ApiError(response.status, body?.detail ?? `请求失败（${response.status}）`)
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>
}

export async function ensureDevSession(): Promise<string> {
  const token = sessionStorage.getItem(TOKEN_KEY)
  if (token) return token
  const result = await request<LoginResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email: 'admin@hydrolab.cn', password: 'admin123456' }),
  })
  sessionStorage.setItem(TOKEN_KEY, result.tokens.access_token)
  return result.user.display_name
}

export async function getWorkspace(): Promise<Workspace> {
  try {
    return await request<Workspace>('/dev-demo/workspace')
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401) throw error
    sessionStorage.removeItem(TOKEN_KEY)
    await ensureDevSession()
    return request<Workspace>('/dev-demo/workspace')
  }
}

export async function advanceRun(runId: string): Promise<ApiRun> {
  try {
    return await request<ApiRun>(`/dev-demo/runs/${runId}/advance`, { method: 'POST' })
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401) throw error
    sessionStorage.removeItem(TOKEN_KEY)
    await ensureDevSession()
    return request<ApiRun>(`/dev-demo/runs/${runId}/advance`, { method: 'POST' })
  }
}

export async function cancelRun(runId: string): Promise<ApiRun> {
  try {
    return await request<ApiRun>(`/dev-demo/runs/${runId}/cancel`, { method: 'POST' })
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401) throw error
    sessionStorage.removeItem(TOKEN_KEY)
    await ensureDevSession()
    return request<ApiRun>(`/dev-demo/runs/${runId}/cancel`, { method: 'POST' })
  }
}
