'use client'

import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'

import type { SetupChecklist } from '@/lib/setup-checklist-types'

export default function SetupWizard({ initial }: { initial: SetupChecklist | null }) {
  const [checklist, setChecklist] = useState(initial)
  const [dismissed, setDismissed] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const response = await fetch('/api/setup-checklist', { cache: 'no-store' })
      const payload = (await response.json()) as { ok?: boolean; data?: SetupChecklist }
      if (payload.ok && payload.data) setChecklist(payload.data)
    } catch {
      /* keep current state */
    }
  }, [])

  useEffect(() => {
    const stored = window.sessionStorage.getItem('setup-wizard-dismissed')
    if (stored === 'true') setDismissed(true)
  }, [])

  if (!checklist || checklist.complete || dismissed) return null

  return (
    <section className="setupWizard" aria-labelledby="setup-wizard-title">
      <div className="setupWizardHeader">
        <div>
          <div className="eyebrow">Quick start</div>
          <h2 id="setup-wizard-title">Set up your workspace</h2>
          <p className="muted">{checklist.done_count} of {checklist.total} steps done</p>
        </div>
        <button className="setupWizardDismiss" onClick={() => { setDismissed(true); window.sessionStorage.setItem('setup-wizard-dismissed', 'true') }} type="button" aria-label="Dismiss setup wizard">
          ✕
        </button>
      </div>
      <div className="setupWizardProgress" aria-label={`${checklist.done_count} of ${checklist.total} steps complete`}>
        <div className="setupWizardTrack">
          <span style={{ width: `${Math.round((checklist.done_count / checklist.total) * 100)}%` }} />
        </div>
      </div>
      <ol className="setupWizardSteps">
        {checklist.steps.map((step) => (
          <li key={step.id} className={`setupWizardStep ${step.done ? 'done' : ''}`}>
            <span className="setupStepIndicator" aria-hidden="true">{step.done ? '✓' : String(checklist.steps.indexOf(step) + 1)}</span>
            <div className="setupStepContent">
              <strong>{step.label}</strong>
              <small>{step.detail}</small>
            </div>
            {step.done ? (
              <span className="setupStepDone">Done</span>
            ) : (
              <Link className="setupStepAction" href={step.href} onClick={() => refresh()}>Configure</Link>
            )}
          </li>
        ))}
      </ol>
    </section>
  )
}
