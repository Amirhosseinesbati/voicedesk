import { expect, test } from '@playwright/test'

test('studio and operator navigation fit common desktop and mobile widths', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: /Enter workspace/i }).click()
  await expect(page.getByRole('heading', { name: /Make every conversation count/i })).toBeVisible()

  for (const width of [1440, 1024, 390]) {
    await page.setViewportSize({ width, height: 900 })
    await expect(page.getByRole('heading', { name: /Make every conversation count/i })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), `Studio horizontal overflow at ${width}px`).toBeTruthy()
    await page.getByRole('button', { name: 'Operator console', exact: true }).click()
    await expect(page.getByRole('heading', { name: /A clearer view of the day/i })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), `Operator horizontal overflow at ${width}px`).toBeTruthy()
    await page.getByRole('button', { name: 'Demo studio', exact: true }).click()
  }
})
