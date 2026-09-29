import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, AudioLines, CalendarDays, ChevronDown, CircleHelp, Headphones, LogOut, ShieldCheck, Sprout } from 'lucide-react'
import { api, ApiError } from './lib/api'
import type { AuthResponse } from './lib/types'
import { InlineError, Spinner, StatusPill } from './components/ui'
import { Studio } from './features/studio/Studio'
import { Operator } from './features/operator/Operator'

type Page = 'studio' | 'operator'

function Login({ onLogin }: { onLogin: (auth: AuthResponse) => void }) {
  const [email, setEmail] = useState('operator@cedar.example.com')
  const [password, setPassword] = useState('DemoVoiceDesk2026!')
  const login = useMutation({ mutationFn: () => api.login(email, password), onSuccess: onLogin })

  return <main className="login-screen">
    <div className="login-story">
      <div className="brand brand-light"><span className="brand-mark"><AudioLines size={22} strokeWidth={2.2} /></span><span><strong>VoiceDesk</strong><small>by Cedar Home Services</small></span></div>
      <div className="login-copy"><span className="eyebrow light">THE FRONT DESK, REIMAGINED</span><h1>Every call, a clear next step.</h1><p>A voice receptionist that listens, checks the calendar, and books only after your customer confirms.</p></div>
      <div className="login-visual" aria-hidden="true"><span className="visual-ring ring-outer" /><span className="visual-ring ring-middle" /><span className="visual-ring ring-inner" /><div className="visual-core"><AudioLines size={52} strokeWidth={1.5} /></div><div className="visual-caption"><span className="mini-live" />A more considered conversation</div></div>
      <div className="login-foot">Independent portfolio project · Synthetic demo dataset</div>
    </div>
    <div className="login-form-wrap"><div className="login-form-card"><div className="login-topline"><span className="login-kicker">CEDAR WORKSPACE</span><ShieldCheck size={18} aria-hidden="true" /></div><h2>Welcome to the desk.</h2><p>Sign in to explore the local demo and operator console.</p><form onSubmit={(event) => { event.preventDefault(); login.mutate() }}><label htmlFor="email">Email address</label><input id="email" type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} /><label htmlFor="password">Password</label><input id="password" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} /><button className="button primary login-submit" type="submit" disabled={login.isPending}>{login.isPending ? <Spinner label="Signing in" /> : <>Enter workspace <ChevronDown className="h-4 w-4 -rotate-90" aria-hidden="true" /></>}</button></form>{login.isError && <InlineError message={login.error instanceof Error ? login.error.message : 'Sign-in failed.'} />}<div className="login-demo-note"><CircleHelp size={16} aria-hidden="true" /><span>Demo credentials are filled in. Data is fictional and stays in this installation.</span></div></div></div>
  </main>
}

export function App() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState<Page>('studio')
  const auth = useQuery({ queryKey: ['auth'], queryFn: api.me, retry: false })
  const health = useQuery({ queryKey: ['providers'], queryFn: api.providers, enabled: !!auth.data, refetchInterval: 30_000 })
  const logout = useMutation({ mutationFn: api.logout, onSettled: () => { sessionStorage.removeItem('voicedesk_session_id'); queryClient.clear(); setPage('studio') } })

  if (auth.isPending) return <div className="app-loading"><span className="brand-mark"><AudioLines size={22} /></span><Spinner label="Opening VoiceDesk" /></div>
  if (auth.isError) {
    if (auth.error instanceof ApiError && auth.error.status === 401) return <Login onLogin={(result) => queryClient.setQueryData(['auth'], result)} />
    return <div className="app-loading"><div className="max-w-sm text-center"><div className="brand mb-6 justify-center"><span className="brand-mark"><AudioLines size={22} /></span><strong>VoiceDesk</strong></div><InlineError message={auth.error instanceof Error ? auth.error.message : 'Cannot open VoiceDesk.'} onRetry={() => void auth.refetch()} /></div></div>
  }

  const user = auth.data.user
  const liveReady = health.data?.audio.status === 'ready' && health.data.model.status === 'ready'
  const liveConfigured = ['ready', 'unverified'].includes(health.data?.audio.status ?? '') && ['ready', 'unverified'].includes(health.data?.model.status ?? '')

  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to content</a>
    <header className="topbar"><div className="topbar-inner"><div className="brand"><span className="brand-mark"><AudioLines size={21} strokeWidth={2.1} /></span><span><strong>VoiceDesk</strong><small>CEDAR HOME SERVICES</small></span></div><nav className="primary-nav" aria-label="Main navigation"><button className={page === 'studio' ? 'active' : ''} type="button" onClick={() => setPage('studio')} aria-current={page === 'studio' ? 'page' : undefined}><Headphones size={17} />Demo studio</button><button className={page === 'operator' ? 'active' : ''} type="button" onClick={() => setPage('operator')} aria-current={page === 'operator' ? 'page' : undefined}><CalendarDays size={17} />Operator console</button></nav><div className="topbar-actions"><StatusPill status={health.isError ? 'error' : liveReady ? 'ready' : liveConfigured ? 'unverified' : health.data?.mode === 'connected' ? 'missing_config' : 'simulated'} label={health.isError ? 'Status unavailable' : liveReady ? 'Voice ready' : liveConfigured ? 'Voice configured' : health.data?.mode === 'connected' ? 'Voice needs setup' : 'Demo mode'} /><div className="user-chip" title={`${user.email} · ${user.role}`}><span className="user-avatar">{user.email[0]?.toUpperCase() ?? 'C'}</span><span className="user-label">{user.role}</span></div><button className="icon-button signout" type="button" onClick={() => logout.mutate()} disabled={logout.isPending} title="Sign out" aria-label="Sign out"><LogOut size={17} /></button></div></div></header>
    <div className="demo-banner"><div className="demo-banner-inner"><span><Sprout size={15} aria-hidden="true" /> Synthetic demo dataset · No messages are sent to real customers</span><span className="banner-side"><Activity size={14} aria-hidden="true" /> {liveConfigured ? 'Voice provider configured · call status shown in studio' : 'Text demo available · live audio requires configuration'}</span></div></div>
    <main id="main-content" className="main-content">{page === 'studio' ? <Studio health={health.data} userRole={user.role} onOpenOperator={() => setPage('operator')} /> : <Operator health={health.data} userRole={user.role} />}</main>
    <footer className="app-footer"><span>VoiceDesk / Cedar Home Services</span><span>Independent portfolio project · Synthetic demo dataset</span></footer>
  </div>
}
