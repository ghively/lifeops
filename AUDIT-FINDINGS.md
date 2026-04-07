# Audit Findings — 2026-04-07

## CRITICAL Bugs

### C1: Access token never persisted to localStorage (INFINITE LOOP ROOT CAUSE)
**File:** `frontend/src/stores/auth.ts`
**Lines:** 52-58 (login), 72-78 (register), 147-156 (refreshAccessToken)

The auth store keeps `accessToken` in Zustand memory only. The `partialize` config at line 168 only persists `user` and `isAuthenticated` — NOT `accessToken` or `refreshToken`. 

After page refresh:
1. Zustand hydrates: `isAuthenticated: true`, `accessToken: null`
2. Request interceptor reads `localStorage.getItem('access_token')` → null
3. All API calls go out without auth → 401
4. Interceptor tries to refresh using `localStorage.getItem('refresh_token')` → null (was never set by initialize)
5. Redirects to /login, but ProtectedRoute sees `isAuthenticated: true` from Zustand → renders app
6. React Query fires all queries → 401 loop

**Fix:** Write `access_token` to localStorage on login/register/refresh, and read it back on initialize.

### C2: Dead dependencies break frontend build
**File:** `frontend/package.json`
**Lines:** 42-44

`y-protocols`, `y-websocket`, and `yjs` are listed as direct dependencies but are NOT imported anywhere in `src/`. The latest `y-protocols@1.0.7` has a broken `exports` field (missing `"."` specifier), causing Vite build to fail.

**Fix:** Remove all three packages from package.json.

### C3: /api/v1/auth/refresh not in AUTH_WHITELIST
**File:** `backend/app/main.py`
**Line:** 188

The auth enforcement middleware blocks the refresh token endpoint, preventing token renewal. This was already fixed in commit 7d03c86.

**Status:** ✅ FIXED

### C4: React Query retries 401 responses
**File:** `frontend/src/App.tsx`
**Line:** 26

Already fixed — retry function now returns false on 401.

**Status:** ✅ FIXED

## HIGH Bugs

### H1: initialize() sets isAuthenticated before verifying token
**File:** `frontend/src/stores/auth.ts`
**Lines:** 158-165

`initialize()` sets `isAuthenticated: true` based solely on the presence of a refresh_token in localStorage. It doesn't verify the token is valid. If the refresh token is expired/invalid, the app shows the main UI briefly before the 401 redirect kicks in — causing a flash.

**Fix:** Set `isAuthenticated: false` initially, only set to true after successful refreshUser().

### H2: refreshAccessToken doesn't store refresh_token to localStorage
**File:** `frontend/src/stores/auth.ts`
**Lines:** 147-156

After a successful token refresh, the new refresh_token is stored in Zustand state but NOT written to localStorage. On next page refresh, localStorage still has the old (now invalid) refresh token.

**Fix:** Add `localStorage.setItem('refresh_token', response.refresh_token)` in refreshAccessToken.

### H3: WebSocket connects before auth is verified
**File:** `frontend/src/App.tsx`
**Lines:** 46-47

`connect()` is called in useEffect on mount, before auth is verified. The WebSocket tries to connect with a null access_token (from localStorage), fails, then retries — adding to the request storm.

**Fix:** Only connect WebSocket after auth is confirmed.

## MEDIUM Bugs

### M1: refreshUser race condition
**File:** `frontend/src/stores/auth.ts`
**Lines:** 100-127

`refreshUser()` and the axios interceptor both try to refresh tokens independently. If refreshUser() fires first (on app load via initialize()), it may conflict with the interceptor's refresh attempt on the first 401'd query. Both call the refresh endpoint simultaneously.

**Fix:** Let the interceptor handle all token refresh. refreshUser() should just call getMe() and let the interceptor handle 401.

### M2: Logout doesn't clear Zustand persisted state
**File:** `frontend/src/stores/auth.ts`
**Lines:** 82-93

logout() clears runtime state but Zustand's persist middleware will rehydrate `user` and `isAuthenticated` from storage on next load. The logout function should call the persist API to clear storage.

**Fix:** Use `useAuthStore.persist.clearStorage()` in logout.

### M3: Frontend nginx doesn't proxy /auth paths
**File:** `frontend/nginx.conf`
**Lines:** 73-82

The `/api/` location block proxies to backend, which covers `/api/v1/auth/refresh`. This is actually fine. No fix needed.

**Status:** ✅ NOT A BUG

## LOW Bugs

### L1: Unused `getApiBaseUrl` function
**File:** `frontend/src/services/api.ts`
**Line:** 441

`getApiBaseUrl()` is defined but only used by `chatWithAgent()` and `websocketApi.getUrl()`. Could be cleaner but not a bug.

### L2: BroadcastChannel may not be supported in all browsers
**File:** `frontend/src/services/api.ts`
**Lines:** 6-11

Already handled with typeof check. Not a bug.

**Status:** ✅ NOT A BUG
