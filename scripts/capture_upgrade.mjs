// Provisional UI evidence, not the final visual direction. Local URLs only.
import { createRequire } from 'node:module'
import { mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const require = createRequire(new URL('../apps/web/package.json', import.meta.url))
const { chromium } = require('@playwright/test')
const baseURL = process.env.VOICEDESK_BASE_URL || 'http://127.0.0.1:4315'
const output = fileURLToPath(new URL('../docs/screenshots/upgrade-checkpoint/', import.meta.url))
const temp = fileURLToPath(new URL('../.tmp-playwright/', import.meta.url))
mkdirSync(output, { recursive: true })
process.env.TEMP = temp
process.env.TMP = temp
const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe' })
const context = await browser.newContext({ baseURL, viewport: { width: 1440, height: 1050 }, reducedMotion: 'reduce' })
const page = await context.newPage()
await page.route('**/*', (route) => {
  const url = new URL(route.request().url())
  return url.origin === new URL(baseURL).origin ? route.continue() : route.abort()
})
const errors = []
page.on('pageerror', (error) => errors.push(error.message))
try {
  await page.goto(baseURL)
  await page.locator('#email').fill('admin@cedar.example.com')
  await page.getByRole('button', { name: /Enter workspace/i }).click()
  await page.getByRole('heading', { name: /Conversation workspace/ }).waitFor()
  await page.getByRole('button', { name: 'Start a conversation', exact: true }).click()
  await page.locator('#message').fill('Hello')
  await page.getByRole('button', { name: 'Send message' }).click()
  await page.locator('.turn-assistant p').first().waitFor()
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: `${output}/01-studio-desktop.png`, fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: `${output}/02-studio-mobile.png`, fullPage: true })
  await page.getByRole('button', { name: 'Workspace settings', exact: true }).click()
  await page.locator('#business-name').waitFor()
  await page.screenshot({ path: `${output}/03-settings-mobile.png`, fullPage: true })
  await page.setViewportSize({ width: 1440, height: 1050 })
  await page.screenshot({ path: `${output}/04-settings-desktop.png`, fullPage: true })
  await page.getByRole('button', { name: 'Operator console', exact: true }).click()
  await page.getByRole('heading', { name: /Operations calendar/ }).waitFor()
  const payload = await (await page.request.get('/api/appointments')).json()
  const appointments = Array.isArray(payload) ? payload : payload.appointments
  const example = appointments.find((item) => item.status === 'confirmed')
  if (example) {
    const config = await (await page.request.get('/api/workspace')).json()
    const day = new Intl.DateTimeFormat('en-CA', { timeZone: config.timezone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(example.start_at))
    await page.locator('#calendar-date').fill(day)
    await page.locator('.calendar-card').first().waitFor()
  }
  await page.screenshot({ path: `${output}/05-operator-desktop.png`, fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: `${output}/06-operator-mobile.png`, fullPage: true })
  if (errors.length) throw new Error(errors.join('\n'))
  process.stdout.write('Six local provisional screenshots captured; no browser page errors.\n')
} finally {
  await browser.close()
}
