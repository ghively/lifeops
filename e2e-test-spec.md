# E2E Playwright Test Spec — Knowledge OS Frontend Walkthrough

## Setup
- Base URL: http://localhost:3010
- Test account: email=e2euser@test.com, password=password123
- If account doesn't exist, register it first via API before starting UI tests
- Use Playwright with Chromium
- Install Playwright if not already: `npx playwright install chromium`
- Use `npx playwright test` to run
- Take screenshots on failures
- Use `page.waitForTimeout(500)` between navigation for SPA routing

## Test Flow (sequential — one test file, ordered steps)

### 1. Auth: Register Page
- Navigate to `/register`
- Verify: form visible with email, username, display name, password, confirm password fields
- Click "Sign in" link → verify switches to login mode
- Click "Sign up" link → verify switches back to register mode
- Fill email (unique per run, e.g. `e2e-reg-${Date.now()}@test.com`), username, password (8+ chars), confirm
- Submit → should redirect to `/` (or show error if email taken — handle gracefully)

### 2. Auth: Login Page
- Navigate to `/login`
- Verify: form visible with email + password fields
- Click "Forgot password?" → verify navigates to `/reset-password`
- Go back to `/login`
- Fill email=e2euser@test.com, password=password123
- Submit → verify redirect to `/`

### 3. Auth: Reset Password Page
- Navigate to `/reset-password`
- Verify: email input + "Send reset link" button visible
- Fill email=e2euser@test.com
- Click "Send reset link" → should advance to confirm step (shows token field)
- Verify: token input, new password, confirm password fields visible

### 4. Dashboard (Home / OutlinerPage without ID)
- At `/` — verify welcome screen shows:
  - "Welcome to Knowledge OS" heading
  - "Create Your First Page" button
- Click "Create Your First Page" → verify navigates to `/object/{id}`

### 5. Object/Note Editor (OutlinerPage with ID)
- On the newly created page:
- **Title**: Click the title → verify it becomes editable input → type new title → press Enter or click away → verify title saves
- **Editor Toolbar**: Verify toolbar buttons exist (Type, Heading, Todo, List, Quote, Code)
- **Type paragraph**: Type text in the editor → verify it appears
- **Slash commands**: Type `/todo` followed by space → verify block converts to todo
- **Slash commands**: Type `/heading` followed by space → verify block converts to heading
- **Todo checkbox**: Click the checkbox on a todo block → verify it toggles checked/unchecked
- **Add block**: Click "Add a block" button → verify new empty paragraph added
- **Back button**: Click "Back" breadcrumb → verify navigates to `/`
- **Share button**: Click Share icon (ghost button) → no crash
- **More button**: Click MoreHorizontal icon → no crash
- **Wiki links**: Type `[[test link]]` in editor → verify renders as styled link
- **Block refs**: Type `((some-id))` in editor → verify renders as styled ref

### 6. Tasks Page
- Navigate to `/tasks`
- Verify: header "Tasks", task count, "New Task" button
- **Create task**: Click "New Task" → verify new task appears in list
- **Inline create**: Type in "Create a task inline..." input → press Enter → verify task created
- **Status filters**: Click each status filter (All, To Do, In Progress, Blocked, In Review, Done) → verify filter active state
- **Priority filters**: Click each priority filter → verify filter active state
- **Task selection**: Click a task → verify details panel on right shows task info
- **Open Note**: In details panel, click "Open Note" → verify navigates to object page
- **Back to tasks**: Navigate back to `/tasks`

### 7. Files Page
- Navigate to `/files`
- Verify: header "Files", file count, "Add Folder" button
- **Search**: Type in search box → verify files filter
- **Status filters**: Click each status filter (all, indexed, processing, pending, error)
- **Add Folder dialog**: Click "Add Folder" → verify dialog opens with path input + Cancel/Add buttons → Click Cancel
- **File click**: If files exist, click one → verify details dialog opens with file info → Close
- **Reindex**: If files exist, hover over file → click reindex (refresh) icon → no crash

### 8. Agents Page
- Navigate to `/agents`
- Verify: header "Agents", agent count, Refresh button
- **Stats**: Verify 4 stat cards (Total, Working, Idle, Offline)
- **Agent click**: If agents exist, click one → verify chat panel opens
- **Chat panel**: If chat open, verify panel has input field → type message → no crash
- **Close chat**: Close chat panel
- **Refresh**: Click Refresh button → verify loading state

### 9. Search Page
- Navigate to `/search`
- Verify: search input, Search button, Semantic/Exact toggle
- **Semantic search**: Type a query → click Search → verify results or "No results" message
- **Exact search**: Click "Exact Match" toggle → search again → verify results
- **Result click**: If results exist, click one → verify navigation

### 10. Settings Page
- Navigate to `/settings`
- Verify: all sections visible (OpenClaw Integration, Watched Folders, Backup & Export, Indexing)

#### 10a. OpenClaw Integration
- Toggle "Enable OpenClaw" checkbox → verify toggles
- Clear Gateway URL input → type new URL → verify input updates
- Clear Gateway Token → type test token → verify

#### 10b. Watched Folders
- Click "Add Folder" → verify dialog opens with path input + recursive checkbox
- Type a path → toggle recursive checkbox → click Cancel
- If folders exist, verify they display path, recursive status, file count
- If folders exist, click trash icon on one → verify folder removed

#### 10c. Backup & Export
- Toggle "Qdrant Snapshots" checkbox → verify
- Toggle "Markdown Export" checkbox → verify
- Toggle "Git Sync" checkbox → verify Git Repo URL field appears
- Click download icon next to Qdrant Snapshots → no crash (triggers backup)
- Click download icon next to Markdown Export → no crash

#### 10d. Indexing
- Toggle "Auto-index" checkbox → verify
- Edit embedding model input → verify

#### 10e. Save
- Click "Save Changes" → verify button shows loading state

### 11. Sidebar Navigation
- Verify sidebar shows nav links (Home, Tasks, Files, Agents, Search, Settings)
- Click each nav link → verify correct page loads
- Click sidebar toggle (collapse) → verify sidebar collapses
- Click sidebar toggle again → verify sidebar expands

### 12. Header
- **Search bar**: Type query in header search → press Enter → verify navigates to `/search?q=...`
- **Notifications bell**: Click bell icon → no crash
- **Settings gear**: Click gear icon → verify navigates to `/settings`

### 13. Auth: Logout
- Find and click logout/user menu → verify redirects to `/login`

## Error Handling Checks (throughout)
- No React errors in console (error #310, etc.)
- No unhandled promise rejections
- No WebSocket errors (collaboration should connect without errors)
- Take screenshot on ANY failure
- Report which step failed

## Output
- Single Playwright test file: `frontend/e2e/walkthrough.spec.ts`
- Playwright config: `frontend/playwright.config.ts`
- Run with: `cd frontend && npx playwright test`
- Screenshots saved to: `frontend/e2e/screenshots/`
