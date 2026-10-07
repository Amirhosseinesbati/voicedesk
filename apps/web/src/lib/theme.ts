export type ThemePreference = 'light' | 'dark' | 'system'

const KEY = 'voicedesk_appearance'
const valid = (value: string | null | undefined): ThemePreference => value === 'light' || value === 'system' ? value : 'dark'
let preference = valid(document.documentElement.dataset.themePreference)
const listeners = new Set<() => void>()
let media: MediaQueryList | undefined
try { media = window.matchMedia('(prefers-color-scheme: dark)') } catch { /* OS preference is optional. */ }

function apply() {
  const appearance = preference === 'system' ? (media?.matches === false ? 'light' : 'dark') : preference
  document.documentElement.dataset.themePreference = preference
  document.documentElement.dataset.appearance = appearance
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', appearance === 'dark' ? '#0b101a' : '#f4f6fa')
}

function followSystem() {
  media?.removeEventListener('change', apply)
  if (preference === 'system') media?.addEventListener('change', apply)
}

export function setThemePreference(next: ThemePreference) {
  if (preference === next) return
  preference = next
  try { localStorage.setItem(KEY, next) } catch { /* In-memory choice still works. */ }
  apply()
  followSystem()
  listeners.forEach((notify) => notify())
}

export const getThemePreference = () => preference
export function subscribeTheme(notify: () => void) {
  listeners.add(notify)
  return () => { listeners.delete(notify) }
}

window.addEventListener('storage', (event) => {
  if (event.key !== KEY && event.key !== null) return
  preference = valid(event.newValue)
  apply()
  followSystem()
  listeners.forEach((notify) => notify())
})
apply()
followSystem()
