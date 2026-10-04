import { test, expect } from '@playwright/test'

for (const failure of [
  {
    contentType: 'text/html',
    body: '<!doctype html><html>Wrong server</html>',
    message: 'The API returned HTML',
  },
  { contentType: 'application/json', body: '{"broken":', message: 'The API returned invalid JSON' },
]) {
  test(`demo explains ${failure.contentType} failure and recovers on retry`, async ({ page }) => {
    await page.route('**/api/v1/investigations/run', (route) =>
      route.fulfill({ status: 200, ...failure }),
    )
    await page.goto('/?demo=billwise')
    await expect(page.getByRole('alert')).toContainText(failure.message)
    await expect(page.getByRole('alert')).not.toContainText('Unexpected token')
    await page.unroute('**/api/v1/investigations/run')
    await page.getByRole('button', { name: 'Retry', exact: true }).click()
    // The test API has no public demo fixture, so the real response is now an auth error.
    await expect(page.getByRole('alert')).toContainText('demo data is unavailable')
  })
}

test('project login explains an HTML API response', async ({ page }) => {
  await page.route('**/api/v1/projects/me', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'text/html',
      body: '<html>Dashboard fallback</html>',
    }),
  )
  await page.goto('/')
  await page.getByLabel('Private read key').fill('alr_example')
  await page.getByRole('button', { name: 'Connect', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('The API returned HTML')
  await expect(page.getByRole('alert')).toContainText('proxy configuration')
})

test('MCP examples expose discovered goal IDs, denominators, raw evidence and export', async ({
  page,
}) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const goalId = 'discovered-signup-id'
  let goalWindow: Record<string, string> = {}
  await page.route('**/api/v1/goals', (route) =>
    route.fulfill({
      json: [
        { id: 'unrelated', name: 'Activation', event_name: 'activation' },
        { id: goalId, name: 'Account signup', event_name: 'signup' },
      ],
    }),
  )
  await page.route('**/api/v1/goals/*/report?**', (route) => {
    expect(new URL(route.request().url()).pathname).toContain(goalId)
    goalWindow = Object.fromEntries(new URL(route.request().url()).searchParams)
    return route.fulfill({
      json: {
        id: goalId,
        name: 'Account signup',
        event_name: 'signup',
        eligible_visitors: 100,
        converted_visitors: 20,
        conversion_rate: 0.2,
        occurrences: 25,
        unidentified_occurrences: 1,
        definition: 'Unique visitors after a pageview.',
      },
    })
  })
  await page.route('**/api/v1/query/run', (route) => {
    const plan = route.request().postDataJSON()
    expect(plan).toMatchObject({
      metric: 'event_count',
      event_name: 'signup',
      dimension: 'utm_campaign',
    })
    return route.fulfill({
      json: {
        total: 25,
        rows: [{ value: '(not set)', count: 25 }],
        truncated: false,
        plan,
        notes: [],
      },
    })
  })
  await page.route('**/api/v1/query/retention?**', (route) =>
    route.fulfill({
      json: {
        cohorts: [
          {
            cohort: '2026-09-07',
            size: 100,
            weeks: [
              { week: 0, visitors: 100, rate: 1 },
              { week: 1, visitors: 20, rate: 0.2 },
              { week: 2, visitors: null, rate: null },
              { week: 3, visitors: null, rate: null },
            ],
          },
        ],
        notes: ['Incomplete weeks are null.'],
      },
    }),
  )
  await page.goto('/?demo=billwise')
  await page.getByRole('button', { name: '2. Campaign signups' }).click()
  await expect(page.getByRole('heading', { name: 'run_query', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: '(not set)', exact: true })).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
  await page.getByRole('button', { name: '3. Signup conversion' }).click()
  await expect(page.getByRole('heading', { name: 'goal_report', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: '100', exact: true })).toBeVisible()
  await expect(page.getByText('20.0%', { exact: false })).toBeVisible()
  expect(goalWindow.date_from).toBeTruthy()
  expect(goalWindow.date_to).toBeTruthy()
  await page.getByText('Inspect full returned JSON', { exact: true }).click()
  await expect(page.locator('pre').filter({ hasText: '"converted_visitors": 20' })).toBeVisible()
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export calls and evidence' }).click()
  expect((await download).suggestedFilename()).toBe('metricairn-billwise-evidence.json')
  await page.getByRole('button', { name: '4. Returning visitors' }).click()
  await expect(page.getByRole('cell', { name: '20.0%', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: '—', exact: true })).toHaveCount(2)
  await page.setViewportSize({ width: 390, height: 844 })
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBeTruthy()
  expect(errors).toEqual([])
})
