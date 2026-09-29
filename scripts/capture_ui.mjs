/** Capture real local VoiceDesk pages for visual review and the portfolio. */
import { mkdir } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const require = createRequire(new URL('../apps/web/package.json', import.meta.url))
const { chromium } = require('@playwright/test')
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const output = path.join(root, 'docs', 'screenshots', 'verified')
const baseURL = process.env.VOICEDESK_BASE_URL ?? 'http://127.0.0.1:5173'
const executablePath = process.env.CHROME_PATH ?? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'

await mkdir(output, { recursive: true })
const browser = await chromium.launch({ headless: true, executablePath })
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' })
const page = await context.newPage()
const errors = []
page.on('pageerror', (error) => errors.push(error.message))

async function capture(name, width, height) {
  await page.setViewportSize({ width, height })
  await page.evaluate(() => {
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()
    window.scrollTo(0, 0)
  })
  await page.screenshot({ path: path.join(output, name), fullPage: true, animations: 'disabled' })
  console.log(`${name}: ${width}x${height}`)
}

try {
  await page.goto(baseURL, { waitUntil: 'domcontentloaded' })
  const authProbe = await page.request.get(`${baseURL}/api/auth/me`)
  if (authProbe.status() !== 401) throw new Error(`Expected unauthenticated VoiceDesk API response (401); got ${authProbe.status()}. Check Vite proxy target.`)
  await page.getByRole('heading', { name: 'Welcome to the desk.' }).waitFor()
  await capture('01-login-1440.png', 1440, 900)

  await page.getByLabel('Password').fill('incorrect-demo-password')
  await page.getByRole('button', { name: 'Enter workspace' }).click()
  await page.getByText('Invalid credentials.').waitFor()
  await capture('02-login-error-1440.png', 1440, 900)

  await page.getByLabel('Password').fill('DemoVoiceDesk2026!')
  await page.getByRole('button', { name: 'Enter workspace' }).click()
  await page.getByRole('heading', { name: 'Make every conversation count.' }).waitFor()
  await capture('03-studio-1440.png', 1440, 900)
  await capture('04-studio-1024.png', 1024, 768)
  await capture('05-studio-390.png', 390, 844)

  await page.setViewportSize({ width: 1440, height: 900 })
  await page.getByRole('button', { name: 'New text session' }).click()
  await page.locator('#service').selectOption('boiler-service')
  await page.locator('#zone').selectOption('central')
  await page.locator('#date').fill('2026-10-06')
  await page.locator('.slot-button').first().waitFor()
  await page.locator('.slot-button').first().click()
  await page.locator('#customer-name').fill('Avery Example')
  await page.locator('#customer-email').fill('avery@example.com')
  await page.getByRole('button', { name: 'Review booking details' }).click()
  await page.getByText('Review before booking').waitFor()
  await capture('06-review-1440.png', 1440, 900)

  await page.getByLabel('I confirm these exact appointment details.').check()
  await page.getByRole('button', { name: 'Confirm booking' }).click()
  await page.getByRole('heading', { name: "It's on the calendar." }).waitFor()
  await capture('07-booked-1440.png', 1440, 900)

  await page.getByRole('button', { name: 'Operator console', exact: true }).click()
  await page.getByRole('heading', { name: 'A clearer view of the day.' }).waitFor()
  await page.locator('#calendar-date').fill('2026-10-06')
  await page.getByText('Avery Example').first().waitFor()
  await capture('08-operator-1440.png', 1440, 900)
  await capture('09-operator-1024.png', 1024, 768)
  await capture('10-operator-390.png', 390, 844)
  if (errors.length) throw new Error(`Browser errors: ${errors.join(' | ')}`)
} catch (error) {
  await page.screenshot({ path: path.join(output, 'capture-failure.png'), fullPage: true }).catch(() => {})
  throw error
} finally {
  await browser.close()
}

