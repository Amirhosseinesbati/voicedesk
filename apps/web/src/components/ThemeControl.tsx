import { useSyncExternalStore } from 'react'
import { Monitor, Moon, Sun } from 'lucide-react'
import { getThemePreference, setThemePreference, subscribeTheme, type ThemePreference } from '../lib/theme'

export function ThemeControl() {
  const preference = useSyncExternalStore(subscribeTheme, getThemePreference)
  const Icon = preference === 'system' ? Monitor : preference === 'light' ? Sun : Moon
  return <label className="theme-control"><Icon size={15} aria-hidden="true" /><span className="sr-only">Appearance</span><select aria-label="Appearance" value={preference} onChange={(event) => setThemePreference(event.target.value as ThemePreference)}><option value="dark">Dark</option><option value="light">Light</option><option value="system">System</option></select></label>
}
