/**
 * Placeholder for navigation entries whose phase has not landed yet.
 *
 * The LifeOps navigation is fixed by BUILD_SPEC section 10, and hiding half of
 * it until the matching phase ships would make the Console feel like it keeps
 * changing shape. Showing the destination and naming its phase is more honest
 * than a blank screen that looks broken.
 */

import { Link } from 'react-router-dom'
import { Construction } from 'lucide-react'

export function ComingInPhasePage({
  title,
  phase,
  description,
}: {
  title: string
  phase: number
  description: string
}) {
  return (
    <div className="mx-auto max-w-2xl p-8">
      <div className="rounded-lg border border-dashed border-border/60 px-6 py-10 text-center">
        <Construction className="mx-auto h-8 w-8 text-muted-foreground" />
        <h1 className="mt-4 text-xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-2 text-sm text-muted-foreground">{description}</p>
        <p className="mt-4 text-xs uppercase tracking-widest text-muted-foreground">
          Arrives in phase {phase}
        </p>
        <Link
          to="/"
          className="mt-6 inline-block text-sm text-foreground underline underline-offset-4"
        >
          Back to Today
        </Link>
      </div>
    </div>
  )
}
