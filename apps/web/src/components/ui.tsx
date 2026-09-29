import type { ReactNode } from 'react'
import { AlertCircle, ArrowRight, LoaderCircle, RefreshCw } from 'lucide-react'

export function Panel({ children, className = '', as: Element = 'section' }: { children: ReactNode; className?: string; as?: 'section' | 'div' | 'article' }) {
  return <Element className={`panel ${className}`}>{children}</Element>
}

export function Eyebrow({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <span className={`eyebrow ${className}`}>{children}</span>
}

export function StatusPill({ status, label }: { status: 'ready' | 'unverified' | 'missing_config' | 'error' | 'simulated' | 'active' | 'neutral'; label: string }) {
  return <span className={`status-pill status-${status}`}><span className="status-dot" aria-hidden="true" />{label}</span>
}

export function Spinner({ label = 'Loading' }: { label?: string }) {
  return <span className="inline-flex items-center gap-2 text-sm text-muted"><LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />{label}</span>
}

export function InlineError({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <div className="inline-error" role="alert"><AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" /><span>{message}</span>{onRetry && <button className="text-button ml-auto whitespace-nowrap" onClick={onRetry} type="button"><RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />Retry</button>}</div>
}

export function EmptyState({ icon, title, text, action }: { icon: ReactNode; title: string; text: string; action?: ReactNode }) {
  return <div className="empty-state"><div className="empty-icon" aria-hidden="true">{icon}</div><h3>{title}</h3><p>{text}</p>{action}</div>
}

export function SectionTitle({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: ReactNode }) {
  return <div className="section-title"><div>{eyebrow && <Eyebrow>{eyebrow}</Eyebrow>}<h2>{title}</h2>{description && <p>{description}</p>}</div>{action}</div>
}

export function ActionLink({ children, onClick }: { children: ReactNode; onClick: () => void }) {
  return <button type="button" className="action-link" onClick={onClick}>{children}<ArrowRight className="h-4 w-4" aria-hidden="true" /></button>
}
