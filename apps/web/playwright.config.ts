import { defineConfig } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const browserTemp = fileURLToPath(new URL('../../.tmp-playwright/', import.meta.url))
mkdirSync(browserTemp, { recursive: true })
process.env.TEMP = browserTemp
process.env.TMP = browserTemp

const baseURL = process.env.VOICEDESK_BASE_URL ?? 'http://127.0.0.1:5173'
const port = new URL(baseURL).port || '5173'

export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  expect: { timeout: 12_000 },
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL,
    browserName: 'chromium',
    launchOptions: { executablePath: process.env.CHROME_PATH || undefined },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: `node node_modules/vite/bin/vite.js --host 127.0.0.1 --port ${port} --strictPort`,
    url: baseURL,
    reuseExistingServer: true,
    timeout: 30_000,
  },
})
