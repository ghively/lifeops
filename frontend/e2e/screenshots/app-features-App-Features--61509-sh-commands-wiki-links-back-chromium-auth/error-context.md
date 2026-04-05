# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: app-features.spec.ts >> App Features >> 5. Note editor — title, toolbar, slash commands, wiki links, back
- Location: e2e/app-features.spec.ts:24:3

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: locator('button').filter({ hasText: 'test link' })
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for locator('button').filter({ hasText: 'test link' })

```

# Page snapshot

```yaml
- generic [ref=e3]:
  - generic [ref=e4]:
    - generic [ref=e5]:
      - link "Knowledge OS" [ref=e6] [cursor=pointer]:
        - /url: /
      - button "Toggle sidebar" [ref=e7] [cursor=pointer]:
        - img [ref=e8]
    - generic [ref=e13]:
      - generic [ref=e14]:
        - link "Today" [ref=e15] [cursor=pointer]:
          - /url: /tasks?filter=today
          - button "Today" [ref=e16]:
            - img [ref=e17]
            - text: Today
        - link "Inbox" [ref=e19] [cursor=pointer]:
          - /url: /inbox
          - button "Inbox" [ref=e20]:
            - img [ref=e21]
            - text: Inbox
      - generic [ref=e24]:
        - button "Spaces" [expanded] [ref=e25] [cursor=pointer]:
          - generic [ref=e26]: Spaces
          - img [ref=e27]
        - generic [ref=e30]:
          - link "Home" [ref=e31] [cursor=pointer]:
            - /url: /
            - button "Home" [ref=e32]:
              - img [ref=e33]
              - text: Home
          - link "Tasks" [ref=e36] [cursor=pointer]:
            - /url: /tasks
            - button "Tasks" [ref=e37]:
              - img [ref=e38]
              - text: Tasks
          - link "Files" [ref=e41] [cursor=pointer]:
            - /url: /files
            - button "Files" [ref=e42]:
              - img [ref=e43]
              - text: Files
          - link "Agents" [ref=e45] [cursor=pointer]:
            - /url: /agents
            - button "Agents" [ref=e46]:
              - img [ref=e47]
              - text: Agents
          - link "Search" [ref=e50] [cursor=pointer]:
            - /url: /search
            - button "Search" [ref=e51]:
              - img [ref=e52]
              - text: Search
      - generic [ref=e55]:
        - button "Agents" [expanded] [ref=e56] [cursor=pointer]:
          - generic [ref=e57]: Agents
          - img [ref=e59]
        - generic [ref=e62]:
          - button "@researcher" [ref=e63] [cursor=pointer]:
            - generic [ref=e65]: "@researcher"
          - button "@sampler" [ref=e66] [cursor=pointer]:
            - generic [ref=e68]: "@sampler"
          - button "@sampler" [ref=e69] [cursor=pointer]:
            - generic [ref=e71]: "@sampler"
          - button "@writer" [ref=e72] [cursor=pointer]:
            - generic [ref=e74]: "@writer"
      - generic [ref=e75]:
        - generic [ref=e76]: Recent Objects
        - generic [ref=e77]:
          - link "📄 E2E inline task" [ref=e78] [cursor=pointer]:
            - /url: /object/01e992a9-a95a-435d-89f9-444abae718f8
            - button "📄 E2E inline task" [ref=e79]:
              - generic [ref=e80]: 📄
              - generic [ref=e81]: E2E inline task
          - link "📄 E2E inline task" [ref=e82] [cursor=pointer]:
            - /url: /object/02d03609-8859-4d4e-b8ee-488a8d50e690
            - button "📄 E2E inline task" [ref=e83]:
              - generic [ref=e84]: 📄
              - generic [ref=e85]: E2E inline task
          - link "📄 sampler" [ref=e86] [cursor=pointer]:
            - /url: /object/06226477-7c75-4d3f-976a-4edf298622d8
            - button "📄 sampler" [ref=e87]:
              - generic [ref=e88]: 📄
              - generic [ref=e89]: sampler
          - link "📄 E2E Test Page" [ref=e90] [cursor=pointer]:
            - /url: /object/06fd220e-9525-4709-93f6-e60641e93780
            - button "📄 E2E Test Page" [ref=e91]:
              - generic [ref=e92]: 📄
              - generic [ref=e93]: E2E Test Page
          - link "📄 Target Page" [ref=e94] [cursor=pointer]:
            - /url: /object/0a39dc95-c1f0-4ecc-8408-c6ba51c32cfc
            - button "📄 Target Page" [ref=e95]:
              - generic [ref=e96]: 📄
              - generic [ref=e97]: Target Page
          - link "📄 New Task" [ref=e98] [cursor=pointer]:
            - /url: /object/0c5da691-6b25-40bf-8f41-a7131de3fba4
            - button "📄 New Task" [ref=e99]:
              - generic [ref=e100]: 📄
              - generic [ref=e101]: New Task
          - link "📄 Page Two" [ref=e102] [cursor=pointer]:
            - /url: /object/0e80a6c4-f7e2-4eec-b4f8-c3c011c6e0ac
            - button "📄 Page Two" [ref=e103]:
              - generic [ref=e104]: 📄
              - generic [ref=e105]: Page Two
          - link "📄 New Task" [ref=e106] [cursor=pointer]:
            - /url: /object/0f6780ec-46e9-469c-a12e-9d0e8735d0bf
            - button "📄 New Task" [ref=e107]:
              - generic [ref=e108]: 📄
              - generic [ref=e109]: New Task
      - generic [ref=e110]:
        - button "Watched Folders" [expanded] [ref=e111] [cursor=pointer]:
          - generic [ref=e112]: Watched Folders
          - img [ref=e114]
        - generic [ref=e118]: No folders watched
    - generic [ref=e119]:
      - generic [ref=e120]:
        - generic [ref=e121]:
          - img [ref=e122]
          - generic [ref=e125]: e2ewalk
        - generic [ref=e126]: e2ewalk@test.com
      - link "Settings" [ref=e127] [cursor=pointer]:
        - /url: /settings
        - button "Settings" [ref=e128]:
          - img [ref=e129]
          - text: Settings
      - button "Logout" [ref=e132] [cursor=pointer]:
        - img [ref=e133]
        - text: Logout
  - generic [ref=e136]:
    - banner [ref=e137]:
      - generic [ref=e139]:
        - img [ref=e140]
        - textbox "Search... (Ctrl+K)" [ref=e143]
      - generic [ref=e144]:
        - button "Notifications" [ref=e145] [cursor=pointer]:
          - img [ref=e146]
        - button "Settings" [ref=e150] [cursor=pointer]:
          - img [ref=e151]
    - main [ref=e154]:
      - generic [ref=e155]:
        - generic [ref=e156]:
          - button "Back" [ref=e157] [cursor=pointer]:
            - img [ref=e158]
            - text: Back
          - generic [ref=e160]: •
          - generic [ref=e161]: page
          - generic [ref=e162]: •
          - generic [ref=e163]: Last edited 4/5/2026
        - generic [ref=e165]:
          - heading "📄 Edited E2E Title" [level=1] [ref=e167] [cursor=pointer]:
            - generic [ref=e168]: 📄
            - text: Edited E2E Title
          - generic [ref=e169]:
            - button "Share" [ref=e170] [cursor=pointer]:
              - img [ref=e171]
            - button "More" [ref=e174] [cursor=pointer]:
              - img [ref=e175]
        - generic [ref=e179]:
          - generic [ref=e180]:
            - button "Type" [ref=e181] [cursor=pointer]:
              - img [ref=e182]
            - button "Heading" [ref=e184] [cursor=pointer]:
              - img [ref=e185]
            - button "Todo" [ref=e187] [cursor=pointer]:
              - img [ref=e188]
            - button "List" [ref=e191] [cursor=pointer]:
              - img [ref=e192]
            - button "Quote" [ref=e193] [cursor=pointer]:
              - img [ref=e194]
            - button "Code" [ref=e197] [cursor=pointer]:
              - img [ref=e198]
          - generic [ref=e203]: You
          - generic [ref=e207]:
            - textbox "Outliner editor" [ref=e208]:
              - paragraph [ref=e209]:
                - generic [ref=e211]: Hello world
              - checkbox [checked] [ref=e213]
              - heading [level=2] [ref=e214]
              - paragraph [ref=e215]
              - paragraph [ref=e216]
            - button "Add a block" [active] [ref=e217] [cursor=pointer]:
              - img [ref=e218]
              - text: Add a block
        - generic [ref=e219]:
          - heading "Properties" [level=3] [ref=e220]
          - generic [ref=e221]:
            - generic [ref=e222]:
              - generic [ref=e223]:
                - img [ref=e224]
                - text: Created
              - generic [ref=e226]: 4/5/2026
            - generic [ref=e227]:
              - generic [ref=e228]:
                - img [ref=e229]
                - text: Tags
              - generic [ref=e232]: No tags
```

# Test source

```ts
  1   | import { test, expect } from '@playwright/test'
  2   | 
  3   | const BASE = 'http://localhost:3010'
  4   | const API = 'http://localhost:8010/api/v1'
  5   | 
  6   | // These tests use stored auth from global setup (no login needed)
  7   | test.describe('App Features', () => {
  8   |   test.beforeEach(async ({ page }) => {
  9   |     page.on('requestfailed', () => {})
  10  |   })
  11  | 
  12  |   test('4. Dashboard — welcome screen, Create First Page button', async ({ page }) => {
  13  |     await page.goto(`${BASE}/`, { waitUntil: 'networkidle' })
  14  |     await page.waitForTimeout(500)
  15  | 
  16  |     await expect(page.getByRole('heading', { name: 'Welcome to Knowledge OS' })).toBeVisible()
  17  |     await expect(page.getByRole('button', { name: /Create Your First Page/i })).toBeVisible()
  18  | 
  19  |     await page.getByRole('button', { name: /Create Your First Page/i }).click()
  20  |     await page.waitForTimeout(2000)
  21  |     await expect(page).toHaveURL(/\/object\//)
  22  |   })
  23  | 
  24  |   test('5. Note editor — title, toolbar, slash commands, wiki links, back', async ({ page }) => {
  25  |     await page.goto(`${BASE}/`, { waitUntil: 'networkidle' })
  26  |     await page.waitForTimeout(500)
  27  | 
  28  |     const accessToken = await page.evaluate(() => localStorage.getItem('access_token'))
  29  |     expect(accessToken).not.toBeNull()
  30  | 
  31  |     const createRes = await fetch(`${API}/objects`, {
  32  |       method: 'POST',
  33  |       headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
  34  |       body: JSON.stringify({ type: 'page', title: 'E2E Test Page', content: '', properties: {} }),
  35  |     })
  36  |     const obj = (await createRes.json()) as { id: string }
  37  | 
  38  |     await page.goto(`${BASE}/object/${obj.id}`, { waitUntil: 'networkidle' })
  39  |     await page.waitForTimeout(3000)
  40  | 
  41  |     const bodyText = await page.locator('body').innerText().catch(() => '')
  42  |     if (!bodyText.trim() || bodyText.includes('Something went wrong')) {
  43  |       await page.screenshot({ path: 'e2e/screenshots/react-310-known-bug.png' })
  44  |       test.skip(true, 'React #310 error on object page — tracked bug')
  45  |     }
  46  | 
  47  |     await page.locator('h1').click()
  48  |     const titleInput = page.getByRole('main').locator('input[type="text"]')
  49  |     await expect(titleInput).toBeVisible()
  50  |     await titleInput.fill('Edited E2E Title')
  51  |     await titleInput.press('Enter')
  52  |     await page.waitForTimeout(500)
  53  | 
  54  |     await expect(page.getByRole('button', { name: 'Type' })).toBeVisible()
  55  |     await expect(page.getByRole('button', { name: 'Heading' })).toBeVisible()
  56  |     await expect(page.getByRole('button', { name: 'Todo' })).toBeVisible()
  57  |     await expect(page.getByRole('button', { name: 'List' })).toBeVisible()
  58  |     await expect(page.getByRole('button', { name: 'Quote' })).toBeVisible()
  59  |     await expect(page.getByRole('button', { name: 'Code' })).toBeVisible()
  60  | 
  61  |     const editor = page.locator('[data-slate-editor]')
  62  |     await editor.click()
  63  |     await page.keyboard.type('Hello world')
  64  |     await page.waitForTimeout(300)
  65  |     await expect(page.getByText('Hello world')).toBeVisible()
  66  | 
  67  |     await page.keyboard.press('Enter')
  68  |     await page.keyboard.type('/todo ')
  69  |     await page.waitForTimeout(500)
  70  |     const checkboxes = page.locator('input[type="checkbox"]')
  71  |     expect(await checkboxes.count()).toBeGreaterThan(0)
  72  |     await checkboxes.last().click()
  73  |     await page.waitForTimeout(200)
  74  | 
  75  |     await page.keyboard.press('Enter')
  76  |     await page.keyboard.type('/heading ')
  77  |     await page.waitForTimeout(500)
  78  |     expect(await page.locator('h2').count()).toBeGreaterThan(0)
  79  | 
  80  |     await page.getByRole('button', { name: /Add a block/i }).click()
  81  |     await page.waitForTimeout(300)
  82  | 
  83  |     await page.keyboard.type('[[test link]]')
  84  |     await page.waitForTimeout(300)
> 85  |     await expect(page.locator('button', { hasText: 'test link' })).toBeVisible()
      |                                                                    ^ Error: expect(locator).toBeVisible() failed
  86  | 
  87  |     await page.getByTestId('share-button').click()
  88  |     await page.waitForTimeout(200)
  89  |     await page.getByTestId('more-button').click()
  90  |     await page.waitForTimeout(200)
  91  | 
  92  |     await page.getByRole('button', { name: 'Back' }).click()
  93  |     await page.waitForTimeout(1000)
  94  |     await expect(page).toHaveURL(/\//)
  95  |   })
  96  | 
  97  |   test('6. Tasks page — create, inline create, filters, selection, details', async ({ page }) => {
  98  |     await page.goto(`${BASE}/tasks`, { waitUntil: 'networkidle' })
  99  |     await page.waitForTimeout(500)
  100 | 
  101 |     await expect(page.getByRole('heading', { name: 'Tasks' })).toBeVisible()
  102 |     await expect(page.getByRole('button', { name: 'New Task', exact: true })).toBeVisible()
  103 | 
  104 |     await page.getByRole('button', { name: 'New Task', exact: true }).click()
  105 |     await page.waitForTimeout(2000)
  106 | 
  107 |     const inlineInput = page.getByPlaceholder('Create a task inline...')
  108 |     await inlineInput.fill('E2E inline task')
  109 |     await inlineInput.press('Enter')
  110 |     await page.waitForTimeout(2000)
  111 | 
  112 |     for (const filter of ['All', 'To Do', 'In Progress', 'Blocked', 'In Review', 'Done']) {
  113 |       await page.getByRole('button', { name: new RegExp(filter, 'i') }).first().click()
  114 |       await page.waitForTimeout(200)
  115 |     }
  116 | 
  117 |     for (const filter of ['All Priorities', 'urgent', 'high', 'medium', 'low']) {
  118 |       await page.getByRole('button', { name: new RegExp(`^${filter}`, 'i') }).first().click()
  119 |       await page.waitForTimeout(200)
  120 |     }
  121 | 
  122 |     const taskRow = page.getByTestId('task-row').first()
  123 |     if (await taskRow.isVisible()) {
  124 |       await taskRow.click()
  125 |       await page.waitForTimeout(500)
  126 |       await expect(page.getByText('Task Details')).toBeVisible()
  127 |       await expect(page.getByText('Open Note')).toBeVisible()
  128 | 
  129 |       await page.getByRole('button', { name: 'Open Note' }).click()
  130 |       await page.waitForTimeout(1000)
  131 |       await expect(page).toHaveURL(/\/object\//)
  132 | 
  133 |       await page.goto(`${BASE}/tasks`, { waitUntil: 'networkidle' })
  134 |       await page.waitForTimeout(500)
  135 |     }
  136 |   })
  137 | 
  138 |   test('7. Files page — search, filters, add folder dialog, file details', async ({ page }) => {
  139 |     await page.goto(`${BASE}/files`, { waitUntil: 'networkidle' })
  140 |     await page.waitForTimeout(500)
  141 | 
  142 |     await expect(page.getByRole('heading', { name: 'Files' })).toBeVisible()
  143 |     await expect(page.getByRole('button', { name: /Add Folder/i })).toBeVisible()
  144 | 
  145 |     const searchInput = page.getByPlaceholder('Search files...')
  146 |     await searchInput.fill('test')
  147 |     await page.waitForTimeout(500)
  148 |     await searchInput.clear()
  149 | 
  150 |     for (const status of ['all', 'indexed', 'processing', 'pending', 'error']) {
  151 |       await page.getByRole('button', { name: new RegExp(`^${status}$`, 'i') }).click()
  152 |       await page.waitForTimeout(200)
  153 |     }
  154 | 
  155 |     await page.getByRole('button', { name: /Add Folder/i }).click()
  156 |     await page.waitForTimeout(500)
  157 |     await expect(page.getByRole('heading', { name: 'Add Watched Folder' })).toBeVisible()
  158 |     await page.getByPlaceholder(/Documents/).fill('/tmp/test-folder')
  159 |     await page.waitForTimeout(200)
  160 |     await page.getByRole('button', { name: 'Cancel' }).click()
  161 |     await page.waitForTimeout(500)
  162 | 
  163 |     const fileRow = page.getByTestId('file-row').first()
  164 |     if (await fileRow.isVisible()) {
  165 |       await fileRow.click()
  166 |       await page.waitForTimeout(500)
  167 |       await expect(page.getByRole('dialog')).toBeVisible()
  168 |       await page.getByRole('button', { name: 'Close' }).click()
  169 |       await page.waitForTimeout(500)
  170 |     }
  171 | 
  172 |     const reindexBtn = page.getByTestId('file-reindex-button').first()
  173 |     if (await reindexBtn.isVisible()) {
  174 |       await reindexBtn.click({ force: true })
  175 |       await page.waitForTimeout(500)
  176 |     }
  177 |   })
  178 | 
  179 |   test('8. Agents page — stats, agent click, chat panel', async ({ page }) => {
  180 |     await page.goto(`${BASE}/agents`, { waitUntil: 'networkidle' })
  181 |     await page.waitForTimeout(500)
  182 | 
  183 |     await expect(page.getByRole('heading', { name: 'Agents' })).toBeVisible()
  184 |     await expect(page.getByRole('button', { name: 'Refresh' })).toBeVisible()
  185 | 
```