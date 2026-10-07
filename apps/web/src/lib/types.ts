export type Role = 'admin' | 'operator' | 'viewer'
export type ProviderStatus = 'ready' | 'unverified' | 'missing_config' | 'error' | 'simulated'

export interface User {
  id: string
  email: string
  role: Role
  workspace_id: string
}

export interface AuthResponse {
  user: User
  csrf_token: string
}

export interface Service {
  id: string
  name: string
  description?: string
  duration_minutes?: number
  base_price_cents?: number
  price_from_cents?: number
  price_policy?: string
  eligible_zone_ids?: string[]
}

export interface WorkspaceConfig {
  id: string
  revision: number
  policy_review_required: boolean
  name: string
  timezone: string
  tagline: string
  theme: 'forest' | 'ocean' | 'plum'
  hours: { day: 'monday' | 'tuesday' | 'wednesday' | 'thursday' | 'friday' | 'saturday' | 'sunday'; closed: boolean; start: string; end: string }[]
  services: { id: string; name: string; description: string; duration_minutes: number; price_from_cents: number; active: boolean }[]
}

export interface Zone {
  id: string
  name: string
  description?: string
  postal_codes?: string[]
}

export interface Staff {
  id: string
  name: string
  role?: string
}

export interface Catalog {
  services: Service[]
  zones: Zone[]
  staff: Staff[]
}

export interface KnowledgeArticle {
  id: string
  title: string
  body: string
  source: string
}

export interface Provider {
  status: ProviderStatus
  detail: string
}

export interface ProviderHealth {
  mode: 'demo' | 'connected'
  model: Provider
  audio: Provider
  calendar: Provider
}

export interface TranscriptTurn {
  id: string
  turn_id: string
  speaker: 'user' | 'assistant' | 'system'
  text: string
  source: 'text' | 'stt' | 'model' | 'demo' | string
  created_at: string
  superseded: boolean
}

export interface SessionEvent {
  id: string
  type: string
  detail: Record<string, unknown>
  created_at: string
}

export interface Proposal {
  id: string
  version: number
  hash: string
  service_id: string
  service_name: string
  zone_id: string
  zone_name: string
  staff_id: string
  staff_name: string
  customer_name: string
  customer_email: string
  customer_phone: string | null
  start_at: string
  end_at: string
  timezone: string
  status: 'pending' | 'confirmed' | 'invalidated' | 'expired' | string
  expires_at: string
}

export interface Session {
  id: string
  workspace_id: string
  mode: 'demo' | 'connected'
  channel: 'text' | 'voice'
  status: string
  timezone: string
  stable_slots: Record<string, unknown>
  proposal_version: number
  proposal: Proposal | null
  turns: TranscriptTurn[]
  events: SessionEvent[]
  last_reply: string | null
  created_at: string
  updated_at: string
}

export interface TurnResponse {
  session: Session
  turn: TranscriptTurn
  reply_text: string
  verification_code?: string | null
}

export interface AvailabilitySlot {
  start_at: string
  end_at: string
  staff_id: string
  staff_name: string
}

export interface Availability {
  date: string
  slots: AvailabilitySlot[]
  timezone: string
}

export interface Appointment {
  id: string
  booking_reference: string
  customer_id: string
  customer_name: string
  customer_email: string
  customer_phone?: string
  service_id: string
  service_name: string
  zone_id: string
  zone_name: string
  staff_id: string
  staff_name: string
  start_at: string
  end_at: string
  status: 'confirmed' | 'cancelled' | 'completed' | string
  source_session_id: string | null
  created_at: string
}

export interface ReplayFixture {
  id: string
  title: string
  script: { speaker: 'customer' | 'assistant'; text: string; interrupts_previous: boolean }[]
  turns: { speaker: 'customer' | 'assistant'; text: string; interrupts_previous: boolean }[]
  provenance: string
  status: 'script_only_audio_pending' | string
  audio_fixture_url: string | null
}

export interface Handoff {
  id: string
  session_id: string
  status: string
  reason: string
  summary: string
  created_at: string
  customer_name?: string
  customer_email?: string
  events?: SessionEvent[]
}

export interface ConfirmResponse {
  appointment: Appointment
  session: Session
  verification_code?: string
}

export interface ProposalResponse {
  proposal: Proposal
  session: Session
}

export interface CreateProposalInput {
  service_id: string
  zone_id: string
  start_at: string
  timezone: string
  customer_name: string
  customer_email: string
  customer_phone: string
}
