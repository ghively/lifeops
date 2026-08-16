import { test, expect } from '@playwright/test'
import { captureBrowserLogs } from '../../helpers/console'
import { FRONTEND_URL } from '../../helpers/env'

test.describe('Search page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/search`)
    await page.waitForLoadState('networkidle').catch(() => {})
  })

  test('renders the search input', async ({ page }) => {
    const cap = captureBrowserLogs(page)
    const input = page
      .getByPlaceholder(/search/i)
      .or(page.locator('input[type="search"]'))
      .first()
    await expect(input).toBeVisible({ timeout: 10_000 })
    cap.detach()
  })

  test('submitting a query does not throw', async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', (e) => errors.push(e.message))

    const input = page
      .getByPlaceholder(/search/i)
      .or(page.locator('input[type="search"]'))
      .first()
    if (!(await input.isVisible().catch(() => false))) {
      test.skip(true, 'no search input visible')
    }
    await input.fill('knowledge')
    await input.press('Enter')
    await page.waitForTimeout(2000)
    expect(errors).toEqual([])
  })

  test('search results list is rendered after query', async ({ page }) => {
    const cap = captureBrowserLogs(page)

    const input = page
      .getByPlaceholder(/search/i)
      .or(page.locator('input[type="search"]'))
      .first()

    if (!(await input.isVisible().catch(() => false))) {
      test.skip(true, 'no search input visible')
    }

    await input.fill('knowledge')
    await input.press('Enter')

    // The results area can be a list of items OR an explicit empty state.
    // We don't assert the count — just that either signal appeared.
    const resultsList = page.locator(
      '[data-testid="search-results"], [class*="search-results"], ' +
      '[class*="searchResults"], [role="list"], [role="listbox"], ul'
    )
    const emptyState = page.getByText(
      /no results|nothing found|0 results|try a different/i
    )

    const hasResults = await resultsList
      .first()
      .isVisible({ timeout: 8_000 })
      .catch(() => false)
    const hasEmpty = await emptyState.isVisible({ timeout: 8_000 }).catch(() => false)

    cap.detach()
    expect(
      hasResults || hasEmpty,
      'neither a results list nor an empty-state appeared after search submission'
    ).toBe(true)
    expect(cap.logs.filter((l) => l.type === 'pageerror')).toEqual([])
  })

  test('search result items are clickable', async ({ page }) => {
    const input = page
      .getByPlaceholder(/search/i)
      .or(page.locator('input[type="search"]'))
      .first()

    if (!(await input.isVisible().catch(() => false))) {
      test.skip(true, 'no search input visible')
    }

    await input.fill('knowledge')
    await input.press('Enter')

    // Wait up to 8 s for at least one result to appear
    const resultItem = page
      .locator(
        '[data-testid="search-result"], [class*="result-item"], ' +
        '[class*="resultItem"], [class*="search-result"]'
      )
      .or(
        // Fall back to any list item inside a results container
        page
          .locator(
            '[data-testid="search-results"] li, [class*="searchResults"] li, ' +
            '[class*="search-results"] li'
          )
      )
      .first()

    const hasResult = await resultItem.isVisible({ timeout: 8_000 }).catch(() => false)
    if (!hasResult) {
      test.skip(true, 'no search result items returned — database may be empty')
    }

    const urlBefore = page.url()

    // Click the first result and assert navigation or a detail panel appeared
    await resultItem.click()
    await page.waitForLoadState('networkidle').catch(() => {})

    const urlAfter = page.url()
    const detailPanel = page
      .locator(
        '[data-testid="detail-panel"], [class*="detail-panel"], ' +
        '[class*="detailPanel"], [role="dialog"], aside'
      )
      .first()
    const panelVisible = await detailPanel.isVisible({ timeout: 3_000 }).catch(() => false)

    expect(
      urlAfter !== urlBefore || panelVisible,
      'clicking a search result did not navigate or open a detail panel'
    ).toBe(true)
  })

  test('clearing the search input resets results', async ({ page }) => {
    const input = page
      .getByPlaceholder(/search/i)
      .or(page.locator('input[type="search"]'))
      .first()

    if (!(await input.isVisible().catch(() => false))) {
      test.skip(true, 'no search input visible')
    }

    // Submit a query
    await input.fill('knowledge')
    await input.press('Enter')

    // Wait briefly for results or empty state to settle
    await page.waitForTimeout(1_500)

    // Clear the input
    await input.clear()

    // Some implementations require pressing Enter or Backspace to reset
    await input.press('Enter')

    await page.waitForTimeout(1_000)

    // After clearing we expect one of:
    //  - the result list to disappear
    //  - the result list to be empty (0 children)
    //  - a "start typing" prompt to appear
    const resultItems = page.locator(
      '[data-testid="search-result"], [class*="result-item"], ' +
      '[class*="resultItem"], [data-testid="search-results"] li, ' +
      '[class*="search-results"] li'
    )
    const itemCount = await resultItems.count()
    const startPrompt = page.getByText(/start typing|search for|enter a query/i)
    const promptVisible = await startPrompt.isVisible().catch(() => false)

    // Any of these signals is acceptable
    const wasReset = itemCount === 0 || promptVisible
    expect(
      wasReset,
      `expected results to clear after input was emptied, but found ${itemCount} items`
    ).toBe(true)
  })
})
