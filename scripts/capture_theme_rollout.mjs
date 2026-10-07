// Synthetic, local-only evidence for the approved Light/Dark operations layout.
import { createRequire } from 'node:module'
import { mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const require = createRequire(new URL('../apps/web/package.json', import.meta.url))
const { chromium } = require('@playwright/test')
const baseURL = process.env.VOICEDESK_BASE_URL || 'http://127.0.0.1:4315'
const output = fileURLToPath(new URL('../docs/screenshots/theme-rollout/', import.meta.url))
const temp = fileURLToPath(new URL('../.tmp-playwright/', import.meta.url))
mkdirSync(output, { recursive: true })
process.env.TEMP = temp
process.env.TMP = temp
const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe' })
const deadline = setTimeout(async () => { await browser.close(); process.exitCode = 1 }, 45_000)
const context = await browser.newContext({ baseURL, viewport: { width: 1440, height: 1050 }, reducedMotion: 'reduce' })
await context.route('**/*', (route) => new URL(route.request().url()).origin === new URL(baseURL).origin ? route.continue() : route.abort())
const page = await context.newPage()
page.setDefaultTimeout(12_000)
const errors = []
page.on('pageerror', (error) => errors.push(error.message))
try {
  await page.goto(baseURL)
  await page.getByRole('button', { name: /Enter workspace/i }).click()
  await page.getByRole('heading', { name: /Conversation workspace/ }).waitFor()
  await page.getByRole('button', { name: 'Start a conversation', exact: true }).click()
  await page.locator('#message').fill('Hello. What services do you offer?')
  await page.getByRole('button', { name: 'Send message' }).click()
  await page.locator('.turn-assistant').first().waitFor()
  await page.locator('#customer-name').fill('Avery Morgan')
  await page.locator('#message').fill('Could we check a time for tomorrow?')
  for (const appearance of ['dark', 'light']) {
    await page.getByLabel('Appearance', { exact: true }).selectOption(appearance)
    await page.screenshot({ path: `${output}/studio-${appearance}-desktop.png`, fullPage: true })
  }
  await page.getByRole('button', { name: 'Operator console', exact: true }).click()
  const payload = await (await page.request.get('/api/appointments')).json()
  const appointments = Array.isArray(payload) ? payload : payload.appointments
  const example = appointments.find((item) => item.status === 'confirmed')
  if (example) {
    const config = await (await page.request.get('/api/workspace')).json()
    const day = new Intl.DateTimeFormat('en-CA', { timeZone: config.timezone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(example.start_at))
    await page.locator('#calendar-date').fill(day)
    await page.locator('.calendar-card').first().waitFor()
  }
  await page.setViewportSize({ width: 390, height: 844 })
  for (const appearance of ['dark', 'light']) {
    await page.getByLabel('Appearance', { exact: true }).selectOption(appearance)
    await page.screenshot({ path: `${output}/operator-${appearance}-mobile.png`, fullPage: true })
  }
  if (errors.length) throw new Error(errors.join('\n'))
  process.stdout.write('Four synthetic local screenshots captured; no browser page errors.\n')
} finally {
  clearTimeout(deadline)
  await browser.close()
}
