'use client'

import { useCallback, useEffect, useState } from 'react'
import type { WeeklyRoiSummary } from '@/lib/roi-types'
import { ErrorBanner } from '@/lib/ui/error-banner'

function percentage(value: number) {
  return `${Math.round(Math.max(0, value) * 100)}%`
}

export function RoiPanel() {
  const [roi, setRoi] = useState<WeeklyRoiSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(true)

  const loadRoi = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await globalThis.fetch('/api/insights/roi', { cache: 'no-store' })
      const payload = await res.json() as { ok?: boolean; data?: WeeklyRoiSummary; error?: string }
      if (!res.ok || !payload.ok || !payload.data) throw new Error(payload.error || 'Failed to load ROI')
      setRoi(payload.data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load weekly ROI')
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => { void loadRoi() }, [loadRoi])

  if (error) return <ErrorBanner message={error} onRetry={loadRoi} />

  return (
    <section className="workspacePanel roiPanel">
      <div className="panelHeading">
        <div>
          <div className="eyebrow">Weekly ROI</div>
          <h2>Application impact</h2>
          <p className="muted">What is converting and what needs attention.</p>
        </div>
        {busy ? <span className="loadingSpinner" role="status" aria-label="Loading ROI" /> : null}
      </div>
      {roi ? (
        <>
          <div className="roiGrid">
            <div className="roiMetric">
              <span className="roiValue">{roi.applications.submitted}</span>
              <span className="roiLabel">Applications submitted</span>
            </div>
            <div className="roiMetric">
              <span className="roiValue">{roi.applications.interviews}</span>
              <span className="roiLabel">Interviews</span>
            </div>
            <div className="roiMetric">
              <span className="roiValue">{percentage(roi.applications.interview_rate)}</span>
              <span className="roiLabel">Interview rate</span>
            </div>
            <div className="roiMetric">
              <span className="roiValue">{roi.applications.missing_outcome}</span>
              <span className="roiLabel">Missing outcomes</span>
            </div>
          </div>
          {roi.applications.best_sources.length ? (
            <details className="roiDetails">
              <summary>Best sources (by interview rate)</summary>
              <div className="roiSourceList">
                {roi.applications.best_sources.map((source) => (
                  <div key={source.source} className="roiSourceRow">
                    <span>{source.source.replaceAll('_', ' ').replace(/\b\w/g, (l) => l.toUpperCase())}</span>
                    <span className="muted">{source.submitted} submitted · {percentage(source.interview_rate)}</span>
                  </div>
                ))}
              </div>
            </details>
          ) : null}
          {roi.recruiters.sent ? (
            <details className="roiDetails">
              <summary>Recruiter outreach ({roi.recruiters.sent} sent)</summary>
              <div className="roiGrid roiSmall">
                <div><span className="muted">Missing accepted:</span> {roi.recruiters.missing_accepted_at}</div>
                <div><span className="muted">Missing reply:</span> {roi.recruiters.missing_reply_at}</div>
                <div><span className="muted">Missing interview:</span> {roi.recruiters.missing_interview_at}</div>
              </div>
            </details>
          ) : null}
          <p className="roiAction">{roi.next_roi_action}</p>
        </>
      ) : busy ? null : (
        <div className="emptyState">Weekly ROI data is not yet available.</div>
      )}
    </section>
  )
}
