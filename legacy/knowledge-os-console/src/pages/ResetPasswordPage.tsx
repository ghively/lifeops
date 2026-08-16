import { useState, useRef, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Mail, Lock, ArrowLeft, CheckCircle2, AlertCircle } from 'lucide-react'
import { authApi } from '@/services/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'

type Step = 'request' | 'confirm' | 'success'

export function ResetPasswordPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState<Step>('request')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [devToken, setDevToken] = useState('')
  const redirectTimerRef = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    return () => {
      if (redirectTimerRef.current) clearTimeout(redirectTimerRef.current)
    }
  }, [])

  // Request step
  const [email, setEmail] = useState('')

  // Confirm step
  const [token, setToken] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  const handleRequestReset = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsLoading(true)
    setError('')

    try {
      const response = await authApi.requestPasswordReset(email)

      // In development, the token is returned in the response
      if (response._dev_token) {
        setDevToken(response._dev_token)
        console.log('Password reset token (development):', response._dev_token)
      }

      setStep('confirm')
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to request password reset'
      setError(message)
    } finally {
      setIsLoading(false)
    }
  }

  const handleConfirmReset = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (newPassword.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }

    if (newPassword !== confirmPassword) {
      setError('Passwords do not match')
      return
    }

    setIsLoading(true)

    try {
      await authApi.confirmPasswordReset(token, newPassword)
      setStep('success')

      // Redirect to login after 3 seconds
      redirectTimerRef.current = setTimeout(() => {
        navigate('/login')
      }, 3000)
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to reset password'
      setError(message)
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1">
          <CardTitle className="text-2xl font-bold text-center">
            {step === 'success' ? 'Password reset successful' : 'Reset your password'}
          </CardTitle>
          <CardDescription className="text-center">
            {step === 'request' && 'Enter your email to receive a password reset link'}
            {step === 'confirm' && 'Enter the reset token and your new password'}
            {step === 'success' && 'You can now log in with your new password'}
          </CardDescription>
        </CardHeader>

        <CardContent>
          {step === 'request' && (
            <form onSubmit={handleRequestReset} className="space-y-4">
              {error && (
                <div className="flex items-center gap-2 p-3 text-sm text-destructive bg-destructive/10 rounded-md">
                  <AlertCircle className="h-4 w-4 flex-shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <div className="relative">
                  <Mail className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="email"
                    type="email"
                    placeholder="name@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="pl-9"
                    required
                    disabled={isLoading}
                  />
                </div>
              </div>

              <Button type="submit" className="w-full" disabled={isLoading}>
                {isLoading ? 'Sending...' : 'Send reset link'}
              </Button>
            </form>
          )}

          {step === 'confirm' && (
            <form onSubmit={handleConfirmReset} className="space-y-4">
              {error && (
                <div className="flex items-center gap-2 p-3 text-sm text-destructive bg-destructive/10 rounded-md">
                  <AlertCircle className="h-4 w-4 flex-shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              {devToken && (
                <div className="p-3 text-sm bg-blue-50 text-blue-900 dark:bg-blue-900/20 dark:text-blue-100 rounded-md">
                  <p className="font-medium mb-1">Development Mode:</p>
                  <p className="text-xs break-all font-mono">{devToken}</p>
                  <button
                    type="button"
                    onClick={() => setToken(devToken)}
                    className="mt-2 text-xs underline"
                  >
                    Use this token
                  </button>
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="token">Reset Token</Label>
                <Input
                  id="token"
                  type="text"
                  placeholder="Enter the token from your email"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  required
                  disabled={isLoading}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="new-password">New Password</Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="new-password"
                    type="password"
                    placeholder="Min. 8 characters"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    className="pl-9"
                    minLength={8}
                    required
                    disabled={isLoading}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="confirm-password">Confirm New Password</Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="confirm-password"
                    type="password"
                    placeholder="Confirm your new password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className="pl-9"
                    required
                    disabled={isLoading}
                  />
                </div>
              </div>

              <Button type="submit" className="w-full" disabled={isLoading}>
                {isLoading ? 'Resetting...' : 'Reset password'}
              </Button>
            </form>
          )}

          {step === 'success' && (
            <div className="flex flex-col items-center justify-center py-6 space-y-4">
              <div className="rounded-full bg-green-100 dark:bg-green-900/20 p-3">
                <CheckCircle2 className="h-8 w-8 text-green-600 dark:text-green-400" />
              </div>
              <p className="text-center text-muted-foreground">
                Your password has been reset successfully. Redirecting to login...
              </p>
            </div>
          )}
        </CardContent>

        <CardFooter>
          <Link
            to="/login"
            className="flex items-center gap-2 text-sm text-muted-foreground hover:text-primary transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to login
          </Link>
        </CardFooter>
      </Card>
    </div>
  )
}
