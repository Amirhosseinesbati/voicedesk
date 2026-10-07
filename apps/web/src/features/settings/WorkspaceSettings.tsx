import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Clock3, Palette, Save, ShieldCheck, SlidersHorizontal } from 'lucide-react'
import { api, ApiError } from '../../lib/api'
import type { Role, WorkspaceConfig } from '../../lib/types'
import { Eyebrow, InlineError, Panel, Spinner } from '../../components/ui'

export function WorkspaceSettings({ config, role }: { config: WorkspaceConfig; role: Role }) {
  const [draft, setDraft] = useState(config)
  const [saved, setSaved] = useState(false)
  const queryClient = useQueryClient()
  const canEdit = role === 'admin'
  const reload = useMutation({ mutationFn: api.workspace, onSuccess: (updated) => {
    setDraft(updated); setSaved(false); save.reset(); queryClient.setQueryData(['workspace'], updated)
  } })
  const save = useMutation({ mutationFn: api.saveWorkspace, onSuccess: (updated) => {
    setDraft(updated); setSaved(true)
    queryClient.setQueryData(['workspace'], updated)
    for (const key of ['catalog', 'availability', 'session']) void queryClient.invalidateQueries({ queryKey: [key] })
  } })
  function change(next: WorkspaceConfig) { setDraft(next); setSaved(false); save.reset() }
  const dirty = JSON.stringify(draft) !== JSON.stringify(config)

  return <div className="settings-page">
    <div className="page-intro"><div><Eyebrow>CLIENT CONFIGURATION</Eyebrow><h1>Make the desk your own<span className="period">.</span></h1><p>One workspace, your brand and booking rules. Changes apply to this installation.</p></div><span className="settings-role"><ShieldCheck size={17} />{canEdit ? 'Admin access' : 'Read-only access'}</span></div>
    <form onSubmit={(event) => { event.preventDefault(); save.mutate(draft) }}>
      {config.policy_review_required && <InlineError message="Business policies need review. The assistant will defer policy questions to an operator until approved sources are configured for this client. Booking and availability remain available." />}
      <fieldset disabled={!canEdit || save.isPending} className="settings-fieldset">
        <div className="settings-grid">
          <Panel className="settings-card"><div className="settings-heading"><Palette size={21} /><div><Eyebrow>01 / PRESENTATION</Eyebrow><h2>A familiar welcome</h2></div></div>
            <div className="field"><label htmlFor="business-name">Business name</label><input id="business-name" required minLength={2} maxLength={160} value={draft.name} onChange={(e) => change({ ...draft, name: e.target.value })} /></div>
            <div className="field"><label htmlFor="business-tagline">Welcome line</label><input id="business-tagline" maxLength={120} value={draft.tagline} onChange={(e) => change({ ...draft, tagline: e.target.value })} /></div>
            <div className="field"><label htmlFor="business-timezone">Business timezone</label><input id="business-timezone" required list="timezone-options" value={draft.timezone} onChange={(e) => change({ ...draft, timezone: e.target.value })} aria-describedby="timezone-help" /><datalist id="timezone-options">{['America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles', 'Europe/London', 'Europe/Berlin', 'Asia/Dubai', 'UTC'].map((tz) => <option key={tz} value={tz} />)}</datalist><p id="timezone-help" className="muted-small">Use an IANA timezone. Hours are interpreted here; saved appointments keep their existing times.</p></div>
            <div className="field"><label htmlFor="business-theme">Brand palette</label><select id="business-theme" value={draft.theme} onChange={(e) => change({ ...draft, theme: e.target.value as WorkspaceConfig['theme'] })}><option value="forest">Forest / calm green</option><option value="ocean">Ocean / confident blue</option><option value="plum">Plum / warm violet</option></select></div>
            <div className={`brand-preview theme-${draft.theme}`}><span className="brand-mark"><SlidersHorizontal size={20} /></span><div><strong>{draft.name || 'Your business'}</strong><p>{draft.tagline || 'Your welcome line'}</p></div></div>
          </Panel>
          <Panel className="settings-card"><div className="settings-heading"><Clock3 size={21} /><div><Eyebrow>02 / AVAILABILITY</Eyebrow><h2>Your working week</h2></div></div><p className="muted-small">Appointments must fit both these hours and the assigned staff member’s schedule. Closed days have no available times.</p>
            <div className="hours-list">{draft.hours.map((hours, index) => <div className="hours-row" key={hours.day}><label className="day-toggle"><input type="checkbox" checked={!hours.closed} aria-label={`Open on ${hours.day}`} onChange={(e) => change({ ...draft, hours: draft.hours.map((row, i) => i === index ? { ...row, closed: !e.target.checked, start: row.start === row.end ? '09:00' : row.start, end: row.start === row.end ? '17:00' : row.end } : row) })} /><span>{hours.day}</span></label>{hours.closed ? <span className="closed-label">Closed</span> : <div className="hours-times"><input type="time" aria-label={`${hours.day} opening time`} required value={hours.start} onChange={(e) => change({ ...draft, hours: draft.hours.map((row, i) => i === index ? { ...row, start: e.target.value } : row) })} /><span>to</span><input type="time" aria-label={`${hours.day} closing time`} required value={hours.end} onChange={(e) => change({ ...draft, hours: draft.hours.map((row, i) => i === index ? { ...row, end: e.target.value } : row) })} /></div>}</div>)}</div>
          </Panel>
        </div>
        <Panel className="settings-card service-settings"><div className="settings-heading"><SlidersHorizontal size={21} /><div><Eyebrow>03 / SERVICE CATALOGUE</Eyebrow><h2>What customers can book</h2></div></div><p className="muted-small">Keep at least one service enabled. Duration changes affect new proposals; confirmed bookings retain their original duration. Add services and staff qualifications through the deployment catalogue.</p>
          <div className="service-edit-grid">{draft.services.map((service, index) => {
            const update = (patch: Partial<typeof service>) => change({ ...draft, services: draft.services.map((row, i) => i === index ? { ...row, ...patch } : row) })
            return <div className="service-edit" key={service.id}><label className="service-toggle"><input type="checkbox" checked={service.active} onChange={(e) => update({ active: e.target.checked })} /> Available to book</label><div className="field"><label htmlFor={`service-name-${index}`}>Service name</label><input id={`service-name-${index}`} required minLength={2} maxLength={160} value={service.name} onChange={(e) => update({ name: e.target.value })} /></div><div className="field"><label htmlFor={`service-description-${index}`}>Description</label><textarea id={`service-description-${index}`} maxLength={2000} rows={2} value={service.description} onChange={(e) => update({ description: e.target.value })} /></div><div className="service-numbers"><div className="field"><label htmlFor={`service-duration-${index}`}>Duration (minutes)</label><input id={`service-duration-${index}`} type="number" min={15} max={480} step={15} required value={service.duration_minutes} onChange={(e) => update({ duration_minutes: Number(e.target.value) })} /></div><div className="field"><label htmlFor={`service-price-${index}`}>Starting price (cents)</label><input id={`service-price-${index}`} type="number" min={0} max={10000000} step={1} required value={service.price_from_cents} onChange={(e) => update({ price_from_cents: Number(e.target.value) })} /></div></div></div>
          })}</div>
        </Panel>
      </fieldset>
      {save.isError && <InlineError message={save.error instanceof Error ? save.error.message : 'Settings could not be saved.'} />}
      {save.error instanceof ApiError && save.error.status === 409 && <button type="button" className="button secondary" onClick={() => reload.mutate()} disabled={reload.isPending}>{reload.isPending ? 'Loading saved settings' : 'Reload saved settings (replaces your edits)'}</button>}
      {reload.isError && <InlineError message="Saved settings could not load. Your edits are still here." />}
      <div className="settings-save"><p>{canEdit ? 'Saving refreshes availability and requires any pending booking review to be made again.' : 'Ask a workspace admin to update the configuration.'}</p>{saved && <span className="saved-note" role="status"><CheckCircle2 size={17} />Workspace updated</span>}<button className="button primary" type="submit" disabled={!canEdit || !dirty || save.isPending}>{save.isPending ? <Spinner label="Saving settings" /> : <><Save size={17} />Save configuration</>}</button></div>
    </form>
  </div>
}
