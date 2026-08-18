/**
 * Console login (BUILD_SPEC section 90, SECURITY.md).
 *
 * Shown by App whenever LifeOps Core answers a request with 401 — i.e. only
 * when the server has authentication enabled and this browser holds no valid
 * token. When auth is disabled server-side this screen never renders.
 *
 * The password goes to `POST /auth/login` and nowhere else; the returned
 * token is stored by `lib/auth.ts` and attached to later requests by the
 * axios interceptor. The password itself is never persisted or logged.
 */

import { useState, type FormEvent } from 'react'
import { ShieldCheck } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { setToken } from '@/lib/auth'
import { authApi, errorMessage } from '@/services/lifeops'

export function LoginPage() {
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (!password || pending) return
    setPending(true)
    setError(null)
    try {
      const response = await authApi.login(password)
      if (response.token) {
        setToken(response.token)
      } else {
        // Auth was disabled server-side between render and submit; a reload
        // skips the login screen entirely. Storing a missing token would
        // persist the literal string "undefined" as a credential.
        window.location.reload()
      }
      // Flipping the auth store re-renders App with the real shell; there is
      // nothing to navigate to explicitly.
    } catch (err) {
      setError(errorMessage(err))
      setPending(false)
    }
  }

  return (
    <div className="flex h-screen items-center justify-center bg-background text-foreground">
      <form
        onSubmit={(event) => void onSubmit(event)}
        className="w-full max-w-sm space-y-5 rounded-lg border border-border/60 bg-card p-8"
      >
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5" />
          <h1 className="text-lg font-semibold tracking-tight">LifeOps</h1>
        </div>

        <p className="text-sm text-muted-foreground">
          This LifeOps Core requires a password. Enter it to open the Console.
        </p>

        <div className="space-y-2">
          <Label htmlFor="lifeops-password">Password</Label>
          <Input
            id="lifeops-password"
            type="password"
            autoComplete="current-password"
            autoFocus
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>

        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}

        <Button type="submit" className="w-full" disabled={pending || !password}>
          {pending ? 'Signing in…' : 'Sign in'}
        </Button>
      </form>
    </div>
  )
}
