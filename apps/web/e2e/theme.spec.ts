import { expect, test } from '@playwright/test'

test('cold paint honors valid preferences before the app loads, including System and legacy choice', async ({ browser, baseURL }) => {
  for (const fixture of [
    { value: null, os: 'light', expected: 'dark', preference: 'dark', key: 'voicedesk_appearance' },
    { value: 'light', os: 'dark', expected: 'light', preference: 'light', key: 'voicedesk_appearance' },
    { value: 'dark', os: 'light', expected: 'dark', preference: 'dark', key: 'voicedesk_appearance' },
    { value: 'system', os: 'light', expected: 'light', preference: 'system', key: 'voicedesk_appearance' },
    { value: 'system', os: 'dark', expected: 'dark', preference: 'system', key: 'voicedesk_appearance' },
    { value: 'broken', os: 'light', expected: 'dark', preference: 'dark', key: 'voicedesk_appearance' },
    { value: 'light', os: 'dark', expected: 'light', preference: 'light', key: 'voicedesk_theme' },
  ] as const) {
    const context = await browser.newContext({ baseURL, colorScheme: fixture.os })
    await context.addInitScript(({ key, value }) => { if (value !== null) localStorage.setItem(key, value) }, fixture)
    const page = await context.newPage()
    await page.route('**/src/main.tsx', (route) => route.abort())
    await page.goto('/')
    await expect(page.locator('html')).toHaveAttribute('data-appearance', fixture.expected)
    await expect(page.locator('html')).toHaveAttribute('data-theme-preference', fixture.preference)
    expect(await page.evaluate(() => getComputedStyle(document.documentElement).colorScheme)).toBe(fixture.expected)
    expect(await page.evaluate(() => getComputedStyle(document.body).backgroundColor)).toBe(fixture.expected === 'dark' ? 'rgb(11, 16, 26)' : 'rgb(244, 246, 250)')
    await context.close()
  }
})

test('appearance changes preserve session, transcript nodes, drafts and booking fields without API traffic', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: /Enter workspace/i }).click()
  await expect(page.getByRole('heading', { name: /Conversation workspace/i })).toBeVisible()
  await page.getByRole('button', { name: 'New text session', exact: true }).click()
  await page.locator('#message').fill('Hello')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.locator('.turn-user')).toHaveCount(1)
  await expect(page.locator('#service option')).not.toHaveCount(1)
  const id = await page.evaluate(() => sessionStorage.getItem('voicedesk_session_id'))
  const transcript = await page.locator('.transcript-panel').elementHandle()
  await page.locator('#message').fill('Keep this unsent draft')
  await page.locator('#customer-name').fill('Synthetic theme customer')
  const calls: string[] = []
  page.on('request', (request) => { if (new URL(request.url()).pathname.startsWith('/api')) calls.push(request.url()) })
  for (const appearance of ['light', 'dark', 'system', 'light']) {
    await page.getByLabel('Appearance', { exact: true }).selectOption(appearance)
    await expect(page.getByLabel('Appearance', { exact: true })).toHaveValue(appearance)
    await expect(page.locator('#message')).toHaveValue('Keep this unsent draft')
    await expect(page.locator('#customer-name')).toHaveValue('Synthetic theme customer')
    expect(await transcript!.evaluate((node) => node === document.querySelector('.transcript-panel'))).toBeTruthy()
    expect(await page.evaluate(() => sessionStorage.getItem('voicedesk_session_id'))).toBe(id)
    await expect(page.locator('.turn-user')).toHaveCount(1)
  }
  expect(calls).toEqual([])
  await page.reload()
  await expect(page.getByLabel('Appearance', { exact: true })).toHaveValue('light')
  await expect(page.locator('.turn-user')).toHaveCount(1)
})

test('only System follows live OS changes; keyboard control and reduced motion remain usable', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' })
  await page.goto('/')
  const control = page.getByLabel('Appearance', { exact: true })
  await control.selectOption('system')
  await expect(page.locator('html')).toHaveAttribute('data-appearance', 'light')
  await page.emulateMedia({ colorScheme: 'dark' })
  await expect(page.locator('html')).toHaveAttribute('data-appearance', 'dark')
  await control.selectOption('light')
  await page.emulateMedia({ colorScheme: 'light' })
  await page.emulateMedia({ colorScheme: 'dark' })
  await expect(page.locator('html')).toHaveAttribute('data-appearance', 'light')
  await control.focus()
  await control.press('Home')
  await control.press('Enter')
  await expect(control).toBeFocused()
  expect(await control.evaluate((element) => getComputedStyle(element).outlineStyle)).not.toBe('none')
  expect(await page.locator('.button').first().evaluate((element) => getComputedStyle(element).transitionDuration)).toBe('0s')
})

test('blocked storage keeps a dark cold paint and allows in-memory choices without crashing', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.addInitScript(() => {
    Object.defineProperty(window, 'localStorage', { get() { throw new DOMException('Blocked synthetic storage', 'SecurityError') } })
  })
  await page.emulateMedia({ colorScheme: 'light' })
  await page.goto('/')
  await expect(page.locator('html')).toHaveAttribute('data-appearance', 'dark')
  await page.getByLabel('Appearance', { exact: true }).selectOption('light')
  await page.getByRole('button', { name: /Enter workspace/i }).click()
  await expect(page.getByRole('heading', { name: /Conversation workspace/i })).toBeVisible()
  await expect(page.locator('html')).toHaveAttribute('data-appearance', 'light')
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-appearance', 'dark')
  expect(errors).toEqual([])
})

test('theme bootstrap works under a self-only script policy without inline exceptions', async ({ page, baseURL }) => {
  await page.addInitScript(() => localStorage.setItem('voicedesk_appearance', 'light'))
  await page.route('**/src/main.tsx', (route) => route.abort())
  await page.route(new URL('/', baseURL!).href, async (route) => {
    const response = await route.fetch()
    await route.fulfill({ response, headers: { ...response.headers(), 'content-security-policy': "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'" } })
  })
  await page.goto('/')
  await expect(page.locator('html')).toHaveAttribute('data-appearance', 'light')
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).colorScheme)).toBe('light')
})

test('both appearances fit 320px to desktop and keep readable controls and semantic states', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: /Enter workspace/i }).click()
  await expect(page.getByRole('heading', { name: /Conversation workspace/i })).toBeVisible()
  for (const appearance of ['light', 'dark']) {
    await page.getByLabel('Appearance', { exact: true }).selectOption(appearance)
    for (const selector of ['.page-intro h1', '.page-intro p', '.button.primary', '.field label', '.composer-hint', '.status-pill']) {
      const ratio = await page.locator(selector).first().evaluate((element) => {
        const rgb = (value: string) => value.match(/[\d.]+/g)!.slice(0, 3).map(Number)
        const luminance = (value: number[]) => value.map((item) => { const s = item / 255; return s <= .04045 ? s / 12.92 : ((s + .055) / 1.055) ** 2.4 }).reduce((sum, item, index) => sum + item * [.2126, .7152, .0722][index]!, 0)
        let background = 'rgba(0, 0, 0, 0)'
        let parent: Element | null = element
        while (parent && background === 'rgba(0, 0, 0, 0)') { background = getComputedStyle(parent).backgroundColor; parent = parent.parentElement }
        const a = luminance(rgb(getComputedStyle(element).color)), b = luminance(rgb(background))
        return (Math.max(a, b) + .05) / (Math.min(a, b) + .05)
      })
      expect(ratio, `${appearance} contrast ${selector}`).toBeGreaterThanOrEqual(4.5)
    }
    for (const palette of ['forest', 'ocean', 'plum']) {
      await page.locator('.app-shell').evaluate((element, value) => { element.classList.remove('theme-forest', 'theme-ocean', 'theme-plum'); element.classList.add(`theme-${value}`) }, palette)
      const colours = await page.locator('.button.primary').first().evaluate((element) => { const style = getComputedStyle(element); return [style.color, style.backgroundColor] })
      const luminance = (colour: string) => colour.match(/[\d.]+/g)!.slice(0, 3).map(Number).map((item) => { const s = item / 255; return s <= .04045 ? s / 12.92 : ((s + .055) / 1.055) ** 2.4 }).reduce((sum, item, index) => sum + item * [.2126, .7152, .0722][index]!, 0)
      const [a, b] = colours.map(luminance)
      expect((Math.max(a!, b!) + .05) / (Math.min(a!, b!) + .05), `${appearance} ${palette} button contrast`).toBeGreaterThanOrEqual(4.5)
    }
    for (const width of [1440, 1024, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 900 })
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), `${appearance} studio overflow at ${width}`).toBeTruthy()
      await page.getByRole('button', { name: 'Operator console', exact: true }).click()
      await expect(page.getByRole('heading', { name: /Operations calendar/i })).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), `${appearance} operator overflow at ${width}`).toBeTruthy()
      await page.getByRole('button', { name: 'Demo studio', exact: true }).click()
    }
  }
})
