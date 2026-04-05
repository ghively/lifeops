# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: walkthrough.spec.ts >> Knowledge OS — Full E2E Walkthrough >> 9. Search page — semantic, exact, result click
- Location: e2e/walkthrough.spec.ts:480:3

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByRole('heading', { name: 'Search' })
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for getByRole('heading', { name: 'Search' })

```

# Page snapshot

```yaml
- generic [ref=e4]:
  - generic [ref=e5]:
    - heading "Welcome back" [level=3] [ref=e6]
    - paragraph [ref=e7]: Enter your credentials to access Knowledge OS
  - generic [ref=e9]:
    - generic [ref=e10]:
      - text: Email
      - generic [ref=e11]:
        - img [ref=e12]
        - textbox "Email" [ref=e15]:
          - /placeholder: name@example.com
    - generic [ref=e16]:
      - text: Password
      - generic [ref=e17]:
        - img [ref=e18]
        - textbox "Password" [ref=e21]:
          - /placeholder: Enter your password
    - link "Forgot password?" [ref=e23] [cursor=pointer]:
      - /url: /reset-password
    - button "Sign in" [ref=e24] [cursor=pointer]
  - generic [ref=e26]:
    - text: Don't have an account?
    - button "Sign up" [ref=e27] [cursor=pointer]
```

# Test source

```ts
  391 | 
  392 |     // Status filters
  393 |     for (const status of ['all', 'indexed', 'processing', 'pending', 'error']) {
  394 |       await page.getByRole('button', { name: new RegExp(`^${status}$`, 'i') }).click()
  395 |       await page.waitForTimeout(200)
  396 |     }
  397 | 
  398 |     // Add Folder dialog
  399 |     await page.getByRole('button', { name: /Add Folder/i }).click()
  400 |     await page.waitForTimeout(500)
  401 |     await expect(page.getByRole('heading', { name: 'Add Watched Folder' })).toBeVisible()
  402 |     await page.getByPlaceholder(/Documents/).fill('/tmp/test-folder')
  403 |     await page.waitForTimeout(200)
  404 |     // Cancel
  405 |     await page.getByRole('button', { name: 'Cancel' }).click()
  406 |     await page.waitForTimeout(500)
  407 | 
  408 |     // File row interaction (if files exist)
  409 |     const fileRow = page.getByTestId('file-row').first()
  410 |     if (await fileRow.isVisible()) {
  411 |       await fileRow.click()
  412 |       await page.waitForTimeout(500)
  413 |       // Details dialog should open
  414 |       await expect(page.getByRole('dialog')).toBeVisible()
  415 |       // Close
  416 |       await page.getByRole('button', { name: 'Close' }).click()
  417 |       await page.waitForTimeout(500)
  418 |     }
  419 | 
  420 |     // Reindex button (if file exists)
  421 |     const reindexBtn = page.getByTestId('file-reindex-button').first()
  422 |     if (await reindexBtn.isVisible()) {
  423 |       await reindexBtn.click({ force: true })
  424 |       await page.waitForTimeout(500)
  425 |     }
  426 |   })
  427 | 
  428 |   // -----------------------------------------------------------------------
  429 |   // 8. Agents Page
  430 |   // -----------------------------------------------------------------------
  431 |   test('8. Agents page — stats, agent click, chat panel', async ({ page }) => {
  432 |     await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' })
  433 |     await page.getByPlaceholder('name@example.com').first().fill(TEST_EMAIL)
  434 |     await page.getByPlaceholder('Enter your password').fill(TEST_PASSWORD)
  435 |     await page.getByRole('button', { name: 'Sign in' }).click()
  436 |     await page.waitForTimeout(2000)
  437 | 
  438 |     await page.goto(`${BASE}/agents`, { waitUntil: 'networkidle' })
  439 |     await page.waitForTimeout(500)
  440 | 
  441 |     // Header
  442 |     await expect(page.getByRole('heading', { name: 'Agents' })).toBeVisible()
  443 |     await expect(page.getByRole('button', { name: 'Refresh' })).toBeVisible()
  444 | 
  445 |     // Stats
  446 |     await expect(page.getByText('Total Agents')).toBeVisible()
  447 |     await expect(page.getByText('Working')).toBeVisible()
  448 |     await expect(page.getByText('Idle')).toBeVisible()
  449 |     await expect(page.getByText('Offline')).toBeVisible()
  450 | 
  451 |     // Agent card click (if agents exist)
  452 |     const agentCard = page.getByTestId('agent-card').first()
  453 |     if (await agentCard.isVisible()) {
  454 |       await agentCard.click()
  455 |       await page.waitForTimeout(1000)
  456 | 
  457 |       // Chat panel should open
  458 |       await expect(page.getByLabel('Close chat')).toBeVisible()
  459 | 
  460 |       // Type in chat
  461 |       const chatInput = page.getByPlaceholder(/message|type/i)
  462 |       if (await chatInput.isVisible()) {
  463 |         await chatInput.fill('Hello agent')
  464 |         await page.waitForTimeout(300)
  465 |       }
  466 | 
  467 |       // Close chat
  468 |       await page.getByLabel('Close chat').click()
  469 |       await page.waitForTimeout(500)
  470 |     }
  471 | 
  472 |     // Refresh
  473 |     await page.getByRole('button', { name: 'Refresh' }).click()
  474 |     await page.waitForTimeout(1000)
  475 |   })
  476 | 
  477 |   // -----------------------------------------------------------------------
  478 |   // 9. Search Page
  479 |   // -----------------------------------------------------------------------
  480 |   test('9. Search page — semantic, exact, result click', async ({ page }) => {
  481 |     await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' })
  482 |     await page.getByPlaceholder('name@example.com').first().fill(TEST_EMAIL)
  483 |     await page.getByPlaceholder('Enter your password').fill(TEST_PASSWORD)
  484 |     await page.getByRole('button', { name: 'Sign in' }).click()
  485 |     await page.waitForTimeout(2000)
  486 | 
  487 |     await page.goto(`${BASE}/search`, { waitUntil: 'networkidle' })
  488 |     await page.waitForTimeout(500)
  489 | 
  490 |     // Search form
> 491 |     await expect(page.getByRole('heading', { name: 'Search' })).toBeVisible()
      |                                                                 ^ Error: expect(locator).toBeVisible() failed
  492 |     await expect(page.getByRole('button', { name: 'Search' })).toBeVisible()
  493 |     await expect(page.getByRole('button', { name: 'Semantic Search' })).toBeVisible()
  494 |     await expect(page.getByRole('button', { name: 'Exact Match' })).toBeVisible()
  495 | 
  496 |     // Semantic search
  497 |     const searchInput = page.getByPlaceholder(/Search across/i)
  498 |     await searchInput.fill('test page')
  499 |     await page.getByRole('button', { name: 'Search' }).click()
  500 |     await page.waitForTimeout(2000)
  501 | 
  502 |     // Should show results or "No results"
  503 |     const hasResults = await page.getByTestId('search-result').first().isVisible()
  504 |     const noResults = await page.getByText('No results found').isVisible()
  505 |     expect(hasResults || noResults).toBeTruthy()
  506 | 
  507 |     // Exact search toggle
  508 |     await page.getByRole('button', { name: 'Exact Match' }).click()
  509 |     await page.waitForTimeout(200)
  510 |     await page.getByRole('button', { name: 'Search' }).click()
  511 |     await page.waitForTimeout(2000)
  512 | 
  513 |     // Click a result if exists
  514 |     if (hasResults) {
  515 |       const result = page.getByTestId('search-result').first()
  516 |       if (await result.isVisible()) {
  517 |         await result.click()
  518 |         await page.waitForTimeout(1000)
  519 |         // Should navigate somewhere
  520 |         const currentUrl = page.url()
  521 |         expect(currentUrl).not.toBe(`${BASE}/search`)
  522 |       }
  523 |     }
  524 |   })
  525 | 
  526 |   // -----------------------------------------------------------------------
  527 |   // 10. Settings Page
  528 |   // -----------------------------------------------------------------------
  529 |   test('10. Settings — OpenClaw, folders, backup, indexing, save', async ({ page }) => {
  530 |     await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' })
  531 |     await page.getByPlaceholder('name@example.com').first().fill(TEST_EMAIL)
  532 |     await page.getByPlaceholder('Enter your password').fill(TEST_PASSWORD)
  533 |     await page.getByRole('button', { name: 'Sign in' }).click()
  534 |     await page.waitForTimeout(2000)
  535 | 
  536 |     await page.goto(`${BASE}/settings`, { waitUntil: 'networkidle' })
  537 |     await page.waitForTimeout(500)
  538 | 
  539 |     // All sections
  540 |     await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible()
  541 |     await expect(page.getByText('OpenClaw Integration')).toBeVisible()
  542 |     await expect(page.getByText('Watched Folders')).toBeVisible()
  543 |     await expect(page.getByText('Backup & Export')).toBeVisible()
  544 |     await expect(page.getByText('Indexing')).toBeVisible()
  545 | 
  546 |     // --- 10a. OpenClaw Integration ---
  547 |     const openclawToggle = page.getByLabel('Enable OpenClaw')
  548 |     if (await openclawToggle.isVisible()) {
  549 |       await openclawToggle.click()
  550 |       await page.waitForTimeout(200)
  551 |     }
  552 | 
  553 |     const urlInput = page.getByLabel('Gateway URL')
  554 |     if (await urlInput.isVisible()) {
  555 |       await urlInput.clear()
  556 |       await urlInput.fill('http://localhost:18789')
  557 |       await page.waitForTimeout(200)
  558 |     }
  559 | 
  560 |     const tokenInput = page.getByLabel('Gateway Token')
  561 |     if (await tokenInput.isVisible()) {
  562 |       await tokenInput.clear()
  563 |       await tokenInput.fill('test-token-123')
  564 |       await page.waitForTimeout(200)
  565 |     }
  566 | 
  567 |     // --- 10b. Watched Folders ---
  568 |     await page.getByRole('button', { name: /Add Folder/i }).click()
  569 |     await page.waitForTimeout(500)
  570 |     const folderInput = page.getByPlaceholder(/Documents/)
  571 |     if (await folderInput.isVisible()) {
  572 |       await folderInput.fill('/tmp/e2e-test-folder')
  573 |       // Toggle recursive
  574 |       const recursive = page.getByLabel(/recursive/i)
  575 |       if (await recursive.isVisible()) {
  576 |         await recursive.click()
  577 |         await page.waitForTimeout(200)
  578 |       }
  579 |     }
  580 |     await page.getByRole('button', { name: 'Cancel' }).click()
  581 |     await page.waitForTimeout(500)
  582 | 
  583 |     // Remove folder (if exists)
  584 |     const removeBtn = page.getByTestId('remove-folder-button').first()
  585 |     if (await removeBtn.isVisible()) {
  586 |       await removeBtn.click()
  587 |       await page.waitForTimeout(500)
  588 |     }
  589 | 
  590 |     // --- 10c. Backup & Export ---
  591 |     // Toggle checkboxes
```