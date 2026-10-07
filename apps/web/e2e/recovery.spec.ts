import { expect, test, type Page } from '@playwright/test'

async function login(page: Page) {
  await page.goto('/')
  await page.getByRole('button', { name: /Enter workspace/i }).click()
  await expect(page.getByRole('heading', { name: /Conversation workspace/i })).toBeVisible()
}

test('start focuses text; a lost response keeps the draft and retries the same turn once', async ({ page }) => {
  await login(page)
  await expect(page.getByRole('button', { name: 'Start microphone', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Start a conversation', exact: true }).click()
  await expect(page.locator('#message')).toBeFocused()
  let turnId = ''
  let lost = false
  await page.route('**/api/sessions/*/turns', async (route) => {
    const body = route.request().postDataJSON() as { turn_id: string }
    if (!lost) {
      lost = true; turnId = body.turn_id
      await route.fetch() // The server committed the turn; lose only the response.
      await route.abort('failed')
    } else {
      expect(body.turn_id).toBe(turnId)
      await route.continue()
    }
  })
  const text = 'What services do you offer?'
  await page.locator('#message').fill(text)
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.getByRole('alert').last()).toBeVisible()
  await expect(page.locator('#message')).toHaveValue(text)
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.locator('#message')).toHaveValue('')
  await expect(page.locator('.turn-user p').filter({ hasText: text })).toHaveCount(1)
  await expect(page.locator('.turn').first()).toHaveClass(/turn-user/)
  await page.reload()
  await expect(page.locator('.turn-user p').filter({ hasText: text })).toHaveCount(1)
  const sessionId = await page.evaluate(() => sessionStorage.getItem('voicedesk_session_id'))
  await page.route(`**/api/sessions/${sessionId}`, (route) => route.fulfill({ status: 503, json: { detail: 'Test outage' } }))
  await page.reload()
  await expect(page.getByText(/Cannot refresh this conversation/)).toBeVisible()
  expect(await page.evaluate(() => sessionStorage.getItem('voicedesk_session_id'))).toBe(sessionId)
  await page.unroute(`**/api/sessions/${sessionId}`)
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.locator('.turn-user p').filter({ hasText: text })).toHaveCount(1)
  await page.locator('#customer-name').fill('Old session customer')
  await page.getByRole('button', { name: 'New text session', exact: true }).click()
  await expect(page.locator('#customer-name')).toHaveValue('')
  await expect(page.locator('.turn-user p')).toHaveCount(0)
  expect(await page.evaluate(() => sessionStorage.getItem('voicedesk_session_id'))).not.toBe(sessionId)
})

test('replay disconnect recovers in the same session and switches to text', async ({ page }) => {
  let closeSocket = () => {}
  let connections = 0
  await page.routeWebSocket('**/api/sessions/*/stream', (ws) => {
    connections++
    ws.send(JSON.stringify({ type: 'status', status: 'connected' }))
    closeSocket = () => ws.close({ code: 1001, reason: 'Simulated disconnect' })
  })
  await login(page)
  await page.getByRole('button', { name: 'Scripted replay', exact: true }).click()
  await expect(page.getByText('Scripted replay connected', { exact: true })).toBeVisible()
  const id = await page.evaluate(() => sessionStorage.getItem('voicedesk_session_id'))
  for (const appearance of ['light', 'dark']) {
    await page.getByLabel('Appearance', { exact: true }).selectOption(appearance)
    await expect(page.getByText('Scripted replay connected', { exact: true })).toBeVisible()
    expect(connections).toBe(1)
    expect(await page.evaluate(() => sessionStorage.getItem('voicedesk_session_id'))).toBe(id)
  }
  closeSocket()
  await expect(page.getByText('Your conversation is still here.')).toBeVisible()
  await page.getByRole('button', { name: 'Reconnect audio', exact: true }).click()
  await expect(page.getByText('Scripted replay connected', { exact: true })).toBeVisible()
  expect(connections).toBe(2)
  expect(await page.evaluate(() => sessionStorage.getItem('voicedesk_session_id'))).toBe(id)
  closeSocket()
  await page.getByRole('button', { name: 'Continue with text', exact: true }).last().click()
  await expect(page.locator('#message')).toBeFocused()
  await page.locator('#message').fill('What services do you offer?')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.locator('.turn-user p')).toHaveCount(1)
  expect(await page.evaluate(() => sessionStorage.getItem('voicedesk_session_id'))).toBe(id)
})

test('microphone denial explains recovery without requesting real permission', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { value: () => Promise.reject(new DOMException('Test denial', 'NotAllowedError')) })
  })
  await page.route('**/api/health/providers', (route) => route.fulfill({ json: { mode: 'connected', model: { status: 'unverified', detail: 'Test fixture' }, audio: { status: 'unverified', detail: 'Test fixture' }, calendar: { status: 'unverified', detail: 'Test fixture' } } }))
  await page.route('**/api/sessions', async (route) => {
    if (route.request().method() !== 'POST') return route.continue()
    const response = await route.fetch({ postData: JSON.stringify({ mode: 'demo', channel: 'voice' }) })
    await route.fulfill({ response })
  })
  await login(page)
  await page.getByRole('button', { name: 'Start microphone', exact: true }).click()
  await expect(page.getByText(/Microphone access was denied/)).toBeVisible()
  await expect(page.getByText('Your conversation is still here.')).toBeVisible()
  await page.getByRole('button', { name: 'Continue with text', exact: true }).last().click()
  await expect(page.locator('#message')).toBeFocused()
})

test('workspace settings are readable to operators and persist for admins', async ({ page }) => {
  await login(page)
  await page.getByRole('button', { name: 'Workspace settings', exact: true }).click()
  await expect(page.locator('#business-name')).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Save configuration' })).toBeDisabled()
  await page.getByRole('button', { name: 'Sign out', exact: true }).click()
  await page.locator('#email').fill('admin@cedar.example.com')
  await page.getByRole('button', { name: /Enter workspace/i }).click()
  await page.getByRole('button', { name: 'Workspace settings', exact: true }).click()
  const originalResponse = await page.request.get('/api/workspace')
  const original = await originalResponse.json() as Record<string, unknown>
  const me = await page.request.get('/api/auth/me')
  const headers = { 'X-CSRF-Token': (await me.json() as { csrf_token: string }).csrf_token }
  try {
    await page.locator('#business-name').fill('Northline Home Care')
    await page.locator('#business-timezone').fill('Europe/London')
    await page.locator('#business-theme').selectOption('ocean')
    await page.getByRole('button', { name: 'Save configuration' }).click()
    await expect(page.getByText('Workspace updated')).toBeVisible()
    await page.reload()
    await page.getByRole('button', { name: 'Workspace settings', exact: true }).click()
    await expect(page.locator('#business-name')).toHaveValue('Northline Home Care')
    await expect(page.locator('#business-timezone')).toHaveValue('Europe/London')
    await expect(page.locator('.app-shell')).toHaveClass(/theme-ocean/)
    for (const width of [1440, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 900 })
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), `Settings overflow at ${width}`).toBeTruthy()
    }
    await page.getByRole('button', { name: 'Demo studio', exact: true }).click()
    await page.getByRole('button', { name: 'New text session', exact: true }).click()
    await expect(page.locator('#timezone')).toHaveValue('Europe/London')
    await page.getByRole('button', { name: 'Operator console', exact: true }).click()
    await expect(page.getByText(/team calendar.*Europe\/London/)).toBeVisible()
  } finally {
    const config = { ...original }; delete config.id; delete config.policy_review_required
    config.revision = (await (await page.request.get('/api/workspace')).json() as { revision: number }).revision
    const restored = await page.request.put('/api/workspace', { data: config, headers })
    expect(restored.ok()).toBeTruthy()
  }
})
