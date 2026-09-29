import { expect, test } from '@playwright/test'

type Catalog = { services: { id: string; name: string }[]; zones: { id: string; name: string }[] }
type Availability = { slots: { start_at: string; staff_id: string }[] }
type Appointment = { id: string; customer_email: string; status: string }

function dateAfter(days: number): string {
  const date = new Date()
  date.setDate(date.getDate() + days)
  return date.toISOString().slice(0, 10)
}

test('text session requires confirmation before booking and rejects an invalid management code', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: /Enter workspace/i }).click()
  await expect(page.getByRole('heading', { name: /Make every conversation count/i })).toBeVisible()

  const healthResponse = await page.request.get('/api/health/providers')
  expect(healthResponse.ok()).toBeTruthy()
  expect((await healthResponse.json() as { mode: string }).mode).toBe('demo')

  const catalogResponse = await page.request.get('/api/catalog')
  expect(catalogResponse.ok()).toBeTruthy()
  const catalog = await catalogResponse.json() as Catalog
  const service = catalog.services[0]!
  const zone = catalog.zones[0]!
  expect(service).toBeTruthy()
  expect(zone).toBeTruthy()

  let availableDate = ''
  for (let offset = 1; offset <= 21; offset += 1) {
    const date = dateAfter(offset)
    const response = await page.request.get(`/api/calendar/availability?${new URLSearchParams({ service_id: service.id, zone_id: zone.id, date, timezone: 'America/New_York' })}`)
    if (!response.ok()) continue
    const availability = await response.json() as Availability
    if (availability.slots.length > 0) { availableDate = date; break }
  }
  expect(availableDate, 'The seeded calendar needs at least one future slot').not.toBe('')

  await page.getByRole('button', { name: /New text session/i }).click()
  await expect(page.getByText(/Saved transcript/i)).toBeVisible()
  await page.locator('#message').fill(`I need ${service.name} in ${zone.name}. Please check availability.`)
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.getByText(`I need ${service.name} in ${zone.name}. Please check availability.`)).toBeVisible()

  await page.locator('#service').selectOption(service.id)
  await page.locator('#zone').selectOption(zone.id)
  await page.locator('#date').fill(availableDate)
  await expect(page.locator('.slot-button').first()).toBeVisible()
  await page.locator('.slot-button').first().click()
  const unique = crypto.randomUUID().slice(0, 8)
  const email = `browser-${unique}@example.com`
  const name = `Avery ${unique}`
  await page.locator('#customer-name').fill(name)
  await page.locator('#customer-email').fill(email)
  await page.getByRole('button', { name: /Review booking details/i }).click()
  await expect(page.getByText('Review before booking')).toBeVisible()

  const appointmentQuery = `/api/appointments?${new URLSearchParams({ from_at: `${availableDate}T00:00:00Z`, to_at: `${dateAfter(22)}T23:59:59Z` })}`
  const beforeResponse = await page.request.get(appointmentQuery)
  expect(beforeResponse.ok()).toBeTruthy()
  const beforePayload = await beforeResponse.json() as Appointment[] | { appointments: Appointment[] }
  const before = Array.isArray(beforePayload) ? beforePayload : beforePayload.appointments
  expect(before.filter((item) => item.customer_email === email)).toHaveLength(0)

  await page.getByRole('checkbox', { name: /I confirm these exact appointment details/i }).check()
  await page.getByRole('button', { name: /Confirm booking/i }).click()
  await expect(page.getByRole('heading', { name: /It's on the calendar/i })).toBeVisible()
  const code = (await page.locator('.verification-note strong').textContent())?.trim()
  expect(code, 'Demo booking should return a one-time local management code').toBeTruthy()

  const afterResponse = await page.request.get(appointmentQuery)
  expect(afterResponse.ok()).toBeTruthy()
  const afterPayload = await afterResponse.json() as Appointment[] | { appointments: Appointment[] }
  const after = Array.isArray(afterPayload) ? afterPayload : afterPayload.appointments
  expect(after.filter((item) => item.customer_email === email && item.status === 'confirmed')).toHaveLength(1)

  await page.getByRole('button', { name: /Open operator calendar/i }).click()
  await page.locator('#calendar-date').fill(availableDate)
  await page.getByRole('button', { name: new RegExp(name) }).first().click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.locator('#verify-code').fill('incorrect-code')
  await page.getByRole('button', { name: /Verify ownership/i }).click()
  await expect(page.getByRole('alert').last()).toBeVisible()
  await page.locator('#verify-code').fill(code!)
  await page.getByRole('button', { name: /Verify ownership/i }).click()
  await expect(page.getByText(/Ownership verified for this action/i)).toBeVisible()
})
