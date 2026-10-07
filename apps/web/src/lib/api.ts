import type {
  Appointment,
  AuthResponse,
  Availability,
  Catalog,
  ConfirmResponse,
  CreateProposalInput,
  Handoff,
  KnowledgeArticle,
  ProposalResponse,
  ProviderHealth,
  ReplayFixture,
  Session,
  TurnResponse,
  WorkspaceConfig,
} from './types'

let csrfToken = ''

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

function errorMessage(payload: unknown, status: number): string {
  if (typeof payload === 'object' && payload !== null) {
    const detail = 'detail' in payload ? payload.detail : undefined
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map((item) => typeof item === 'object' && item !== null && 'msg' in item ? String(item.msg) : String(item)).join('; ')
    const message = 'message' in payload ? payload.message : undefined
    if (typeof message === 'string') return message
  }
  return status === 0 ? 'Cannot reach VoiceDesk. Check that the API is running.' : `Request failed (${status}). Please try again.`
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response
  const timeout = AbortSignal.timeout(30_000)
  try {
    response = await fetch(path, {
      ...options,
      credentials: 'include',
      signal: options.signal ? AbortSignal.any([options.signal, timeout]) : timeout,
      headers: {
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...(options.method && options.method !== 'GET' && csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
        ...options.headers,
      },
    })
  } catch {
    if (timeout.aborted) throw new ApiError(0, 'The request timed out. It may have reached the server. Retry to check the saved result.')
    throw new ApiError(0, errorMessage(null, 0))
  }

  const payload: unknown = response.status === 204 ? null : await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(response.status, errorMessage(payload, response.status))
  if (response.status !== 204 && payload === null) throw new ApiError(response.status, 'VoiceDesk returned an incomplete response. Retry to check the saved result.')
  return payload as T
}

function withAuthToken(response: AuthResponse): AuthResponse {
  csrfToken = response.csrf_token
  return response
}

export const api = {
  me: async () => withAuthToken(await request<AuthResponse>('/api/auth/me')),
  login: async (email: string, password: string) => withAuthToken(await request<AuthResponse>('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })),
  logout: async () => {
    await request<unknown>('/api/auth/logout', { method: 'POST' })
    csrfToken = ''
  },
  catalog: () => request<Catalog>('/api/catalog'),
  workspace: () => request<WorkspaceConfig>('/api/workspace'),
  saveWorkspace: (config: WorkspaceConfig) => request<WorkspaceConfig>('/api/workspace', { method: 'PUT', body: JSON.stringify({ revision: config.revision, name: config.name, timezone: config.timezone, tagline: config.tagline, theme: config.theme, hours: config.hours, services: config.services }) }),
  knowledge: () => request<{ articles: KnowledgeArticle[] }>('/api/knowledge'),
  providers: () => request<ProviderHealth>('/api/health/providers'),
  replays: () => request<ReplayFixture[]>('/api/replays'),
  createSession: (mode: 'demo' | 'connected', channel: 'text' | 'voice') => request<Session>('/api/sessions', { method: 'POST', body: JSON.stringify({ mode, channel }) }),
  sessions: () => request<Session[] | { sessions: Session[] }>('/api/sessions'),
  session: (id: string) => request<Session>(`/api/sessions/${encodeURIComponent(id)}`),
  sendTurn: (id: string, text: string, turnId: string, source: 'text' | 'stt' = 'text') => request<TurnResponse>(`/api/sessions/${encodeURIComponent(id)}/turns`, { method: 'POST', body: JSON.stringify({ turn_id: turnId, text, source }) }),
  createProposal: (sessionId: string, input: CreateProposalInput) => request<ProposalResponse>(`/api/sessions/${encodeURIComponent(sessionId)}/proposals`, { method: 'POST', body: JSON.stringify(input) }),
  confirmProposal: (sessionId: string, proposalId: string, version: number, hash: string, idempotencyKey: string) => request<ConfirmResponse>(`/api/sessions/${encodeURIComponent(sessionId)}/proposals/${encodeURIComponent(proposalId)}/confirm`, { method: 'POST', body: JSON.stringify({ version, hash, confirmed: true, idempotency_key: idempotencyKey }) }),
  availability: (serviceId: string, zoneId: string, date: string, timezone: string) => request<Availability>(`/api/calendar/availability?${new URLSearchParams({ service_id: serviceId, zone_id: zoneId, date, timezone })}`),
  appointments: (fromAt: string, toAt: string) => request<Appointment[] | { appointments: Appointment[] }>(`/api/appointments?${new URLSearchParams({ from_at: fromAt, to_at: toAt })}`),
  verifyAppointment: (id: string, email: string, verificationCode: string) => request<{ verified: true; token: string }>(`/api/appointments/${encodeURIComponent(id)}/verify`, { method: 'POST', body: JSON.stringify({ email, verification_code: verificationCode }) }),
  rescheduleAppointment: (id: string, verificationToken: string, startAt: string, timezone: string, idempotencyKey: string, serviceId?: string, zoneId?: string) => request<{ appointment: Appointment }>(`/api/appointments/${encodeURIComponent(id)}/reschedule`, { method: 'POST', body: JSON.stringify({ verification_token: verificationToken, start_at: startAt, timezone, idempotency_key: idempotencyKey, service_id: serviceId, zone_id: zoneId }) }),
  cancelAppointment: (id: string, verificationToken: string, idempotencyKey: string) => request<{ appointment: Appointment }>(`/api/appointments/${encodeURIComponent(id)}/cancel`, { method: 'POST', body: JSON.stringify({ verification_token: verificationToken, idempotency_key: idempotencyKey }) }),
  handoffs: () => request<Handoff[] | { handoffs: Handoff[] }>('/api/handoffs'),
}

export function asList<T>(response: T[] | Record<string, T[]>, key: string): T[] {
  if (Array.isArray(response)) return response
  return response[key] ?? []
}
