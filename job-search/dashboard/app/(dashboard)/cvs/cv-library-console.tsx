'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'

import {
  ComparisonResult,
  CvPreview,
  formatDate,
} from '@/features/cvs/cv-components'
import type { AutomationRun } from '@/lib/automation-data'
import {
  cvSourceEditError,
  cvSourceWordCount,
  parseCvSource,
  serializeCvSource,
  updateCvSourcePart,
} from '@/lib/cv-source-editor'
import type {
  CvEditorPart,
  CvJobComparison,
  CvStudioDocument,
  CvStudioMutationResult,
} from '@/lib/cv-studio-types'
import type { CvLibrary } from '@/lib/cv-data'
import type { OpportunityOverview, OpportunitySummary } from '@/lib/opportunity-data'
import type { ApiResponse } from '@/lib/api-response'
type StudioBusy = 'load' | 'save' | 'rebuild' | 'restore' | 'rebuild_all' | null


function versionReason(reason: string): string {
  if (reason === 'before_save') return 'Before edit'
  if (reason === 'before_restore') return 'Before restore'
  return reason.replaceAll('_', ' ')
}

function activeRun(run: AutomationRun | null): boolean {
  return Boolean(run && !['succeeded', 'partial', 'failed', 'cancelled'].includes(run.status))
}

export default function CvLibraryConsole({
  initialLibrary,
  initialDocument,
  initialOpportunities,
  initialVariant,
}: {
  initialLibrary: CvLibrary
  initialDocument: CvStudioDocument | null
  initialOpportunities: OpportunitySummary[]
  initialVariant: string
}) {
  const [library, setLibrary] = useState(initialLibrary)
  const [selectedSlug, setSelectedSlug] = useState(initialVariant)
  const [document, setDocument] = useState<CvStudioDocument | null>(initialDocument)
  const [parts, setParts] = useState<CvEditorPart[]>(() => parseCvSource(initialDocument?.content || ''))
  const [selectedPartId, setSelectedPartId] = useState(() => (
    parseCvSource(initialDocument?.content || '').find((part) => part.title === 'Professional Summary')?.id
    || parseCvSource(initialDocument?.content || '')[0]?.id
    || ''
  ))
  const [busy, setBusy] = useState<StudioBusy>(null)
  const [buildRun, setBuildRun] = useState<AutomationRun | null>(null)
  const [error, setError] = useState(initialDocument ? '' : 'The CV source could not be loaded.')
  const [notice, setNotice] = useState('')
  const [previewRevision, setPreviewRevision] = useState(() => String(Date.now()))
  const [opportunityId, setOpportunityId] = useState('')
  const [comparison, setComparison] = useState<CvJobComparison | null>(null)
  const [comparisonBusy, setComparisonBusy] = useState(false)
  const [comparisonError, setComparisonError] = useState('')
  const [opportunities, setOpportunities] = useState(initialOpportunities)
  const [hydrated, setHydrated] = useState(false)

  const selected = useMemo(
    () => library.variants.find((variant) => variant.slug === selectedSlug) || library.variants[0],
    [library.variants, selectedSlug],
  )
  const selectedPart = useMemo(
    () => parts.find((part) => part.id === selectedPartId) || parts[0] || null,
    [parts, selectedPartId],
  )
  const currentSource = useMemo(() => serializeCvSource(parts), [parts])
  const dirty = Boolean(document && currentSource !== document.content)
  const editError = cvSourceEditError(parts)

  useEffect(() => {
    setHydrated(true)
    setPreviewRevision(String(Date.now()))
  }, [])

  useEffect(() => {
    const params = new URLSearchParams()
    if (selectedSlug) params.set('variant', selectedSlug)
    window.history.replaceState(null, '', `${window.location.pathname}?${params.toString()}`)
  }, [selectedSlug])

  useEffect(() => {
    function warnBeforeLeaving(event: BeforeUnloadEvent) {
      if (!dirty) return
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warnBeforeLeaving)
    return () => window.removeEventListener('beforeunload', warnBeforeLeaving)
  }, [dirty])

  useEffect(() => {
    void fetch('/api/opportunities/overview', { cache: 'no-store' })
      .then(async (response) => {
        const next = (await response.json()) as OpportunityOverview
        if (!response.ok || !next.queues?.all) return
        setOpportunities(next.queues.all
          .filter((row) => !['skipped', 'expired'].includes(row.status))
          .sort((left, right) => Number(right.match?.score || 0) - Number(left.match?.score || 0))
          .slice(0, 100))
      })
      .catch(() => {
        // Keep the server-provided list if a short refresh fails.
      })
  }, [])

  async function refreshLibrary() {
    const response = await fetch('/api/cvs/overview', { cache: 'no-store' })
    const payload = (await response.json()) as ApiResponse<CvLibrary>
    if (!response.ok || !payload.ok || !payload.data) {
      throw new Error(payload.error || 'CV library could not be refreshed.')
    }
    setLibrary(payload.data)
  }

  function installDocument(next: CvStudioDocument, preferredTitle = '') {
    const nextParts = parseCvSource(next.content)
    const nextSelected = nextParts.find((part) => part.title === preferredTitle)
      || nextParts.find((part) => part.title === 'Professional Summary')
      || nextParts[0]
    setDocument(next)
    setParts(nextParts)
    setSelectedPartId(nextSelected?.id || '')
  }

  async function loadDocument(slug: string) {
    setBusy('load')
    setError('')
    setNotice('')
    try {
      const response = await fetch(`/api/cvs/studio/${encodeURIComponent(slug)}`, { cache: 'no-store' })
      const payload = (await response.json()) as ApiResponse<CvStudioDocument>
      if (!response.ok || !payload.ok || !payload.data) {
        throw new Error(payload.error || 'CV source could not be loaded.')
      }
      installDocument(payload.data)
    } catch (loadError) {
      setDocument(null)
      setParts([])
      setError(loadError instanceof Error ? loadError.message : 'CV source could not be loaded.')
    } finally {
      setBusy(null)
    }
  }

  async function chooseVariant(slug: string) {
    if (slug === selectedSlug) return
    if (dirty && !window.confirm('Discard the unsaved CV edits and open another variant?')) return
    setSelectedSlug(slug)
    setComparison(null)
    setComparisonError('')
    await loadDocument(slug)
    if (opportunityId) await loadComparison(slug, opportunityId)
  }

  async function postStudioAction(
    action: 'save_rebuild' | 'rebuild_selected' | 'restore_version',
    input: { content?: string; versionId?: string } = {},
  ): Promise<CvStudioMutationResult> {
    const response = await fetch(`/api/cvs/studio/${encodeURIComponent(selectedSlug)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, ...input }),
    })
    const payload = (await response.json()) as ApiResponse<CvStudioMutationResult>
    if (!response.ok || !payload.ok || !payload.data) {
      throw new Error(payload.error || 'CV Studio update failed.')
    }
    return payload.data
  }

  async function saveAndRebuild() {
    if (!document || editError) return
    const preferredTitle = selectedPart?.title || ''
    setBusy('save')
    setError('')
    setNotice('')
    try {
      const result = await postStudioAction('save_rebuild', { content: currentSource })
      installDocument(result.document, preferredTitle)
      await refreshLibrary()
      setPreviewRevision(String(Date.now()))
      setNotice(result.changed
        ? 'Saved and rebuilt this visual and ATS CV. The previous source is available below.'
        : 'No text changed. This visual and ATS CV were rebuilt from the current source.')
      if (opportunityId) await loadComparison(selectedSlug, opportunityId)
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'CV Studio update failed.')
    } finally {
      setBusy(null)
    }
  }

  async function rebuildSelected() {
    if (!document || dirty) return
    setBusy('rebuild')
    setError('')
    setNotice('')
    try {
      const result = await postStudioAction('rebuild_selected')
      installDocument(result.document, selectedPart?.title || '')
      await refreshLibrary()
      setPreviewRevision(String(Date.now()))
      setNotice('Rebuilt only this visual and ATS CV.')
    } catch (buildError) {
      setError(buildError instanceof Error ? buildError.message : 'This CV could not be rebuilt.')
    } finally {
      setBusy(null)
    }
  }

  async function restoreVersion(versionId: string) {
    if (dirty || !window.confirm('Restore this source version and rebuild only this CV? The current saved source will be kept as another recovery point.')) return
    setBusy('restore')
    setError('')
    setNotice('')
    try {
      const result = await postStudioAction('restore_version', { versionId })
      installDocument(result.document)
      await refreshLibrary()
      setPreviewRevision(String(Date.now()))
      setNotice('The earlier source was restored and both PDFs were rebuilt.')
      if (opportunityId) await loadComparison(selectedSlug, opportunityId)
    } catch (restoreError) {
      setError(restoreError instanceof Error ? restoreError.message : 'The CV version could not be restored.')
    } finally {
      setBusy(null)
    }
  }

  function resetEdits() {
    if (!document) return
    installDocument(document, selectedPart?.title || '')
    setNotice('Unsaved edits were reset. No file was changed.')
    setError('')
  }

  async function loadComparison(slug: string, selectedOpportunityId: string) {
    if (!selectedOpportunityId) {
      setComparison(null)
      setComparisonError('')
      return
    }
    setComparisonBusy(true)
    setComparisonError('')
    try {
      const response = await fetch(
        `/api/cvs/studio/${encodeURIComponent(slug)}/compare?opportunity=${encodeURIComponent(selectedOpportunityId)}`,
        { cache: 'no-store' },
      )
      const payload = (await response.json()) as ApiResponse<CvJobComparison>
      if (!response.ok || !payload.ok || !payload.data) {
        throw new Error(payload.error || 'CV comparison could not be loaded.')
      }
      setComparison(payload.data)
    } catch (compareError) {
      setComparison(null)
      setComparisonError(compareError instanceof Error ? compareError.message : 'CV comparison could not be loaded.')
    } finally {
      setComparisonBusy(false)
    }
  }

  useEffect(() => {
    if (!buildRun || !activeRun(buildRun)) return
    const interval = window.setInterval(async () => {
      try {
        const response = await fetch(`/api/automation/runs/${buildRun.run_id}`, { cache: 'no-store' })
        const payload = (await response.json()) as ApiResponse<AutomationRun>
        if (!response.ok || !payload.ok || !payload.data) return
        setBuildRun(payload.data)
        if (!activeRun(payload.data)) {
          await refreshLibrary()
          setPreviewRevision(String(Date.now()))
          setNotice(payload.data.status === 'succeeded'
            ? 'All twelve CV PDFs were rebuilt.'
            : payload.data.error || 'The full CV build finished with an issue.')
          setBusy(null)
        }
      } catch {
        // A later poll can recover from a short local service interruption.
      }
    }, 2500)
    return () => window.clearInterval(interval)
  }, [buildRun])

  async function rebuildAll() {
    if (dirty) return
    setBusy('rebuild_all')
    setError('')
    setNotice('')
    try {
      const response = await fetch('/api/cvs/actions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'rebuild_all' }),
      })
      const payload = (await response.json()) as ApiResponse<{ run?: AutomationRun; created?: boolean }>
      if (!response.ok || !payload.ok || !payload.data?.run) {
        throw new Error(payload.error || 'The full CV build could not be started.')
      }
      setBuildRun(payload.data.run)
      setNotice(payload.data.created === false
        ? 'A full CV build is already running.'
        : 'The full CV build is queued. You can stay on this page.')
      if (!activeRun(payload.data.run)) {
        await refreshLibrary()
        setPreviewRevision(String(Date.now()))
        setBusy(null)
      }
    } catch (buildError) {
      setBusy(null)
      setError(buildError instanceof Error ? buildError.message : 'The full CV build could not be started.')
    }
  }

  return (
    <>
      <div className="workspaceHeading cvStudioHeading">
        <div>
          <div className="eyebrow">Private document workspace</div>
          <h1>CV Studio</h1>
          <p className="muted">Edit one source, compare it with a job, and review both finished formats before using it.</p>
        </div>
        <div className="libraryReadiness">
          <strong>{library.counts.readyPdfs}/{library.counts.expectedPdfs}</strong>
          <span>PDFs ready</span>
        </div>
      </div>

      {error ? <div className="banner" role="alert">{error}</div> : null}
      {notice ? <div className="noticeBanner" role="status">{notice}</div> : null}

      <section className="controlStrip cvControlStrip" aria-label="CV Studio actions" data-ready={hydrated ? 'true' : 'false'}>
        <button className="primaryAction" disabled={!hydrated || Boolean(busy) || !document || Boolean(editError)} onClick={saveAndRebuild} type="button">
          <span>{busy === 'save' ? 'Saving and building…' : dirty ? 'Save & rebuild this CV' : 'Rebuild this CV'}</span>
          <small>{dirty ? 'Creates a recovery version first' : 'Visual, ATS, and Canva text only for this variant'}</small>
        </button>
        <button className="quietAction" disabled={!hydrated || Boolean(busy) || !document || dirty} onClick={rebuildSelected} type="button">
          <span>{busy === 'rebuild' ? 'Building selected CV…' : 'Rebuild selected only'}</span>
          <small>{dirty ? 'Save or reset your edits first' : 'Leaves the other ten PDFs untouched'}</small>
        </button>
        <button className="quietAction" disabled={!hydrated || Boolean(busy) || dirty || activeRun(buildRun)} onClick={rebuildAll} type="button">
          <span>{activeRun(buildRun) ? `Building all… ${buildRun?.progress || 0}%` : 'Rebuild all twelve PDFs'}</span>
          <small>Use after shared design or profile changes</small>
        </button>
      </section>

      <div className="cvStudioShell">
        <aside className="workspacePanel cvVariantList" aria-labelledby="variant-list-title">
          <div className="panelHeading">
            <div>
              <h2 id="variant-list-title">Variants</h2>
              <p>{library.counts.variants} editable sources</p>
            </div>
          </div>
          <div className="variantRows">
            {library.variants.map((variant) => {
              const ready = Number(variant.files.visual.exists) + Number(variant.files.ats.exists)
              return (
                <button
                  className={`variantRow ${selected?.slug === variant.slug ? 'selected' : ''}`}
                  disabled={!hydrated || busy === 'load'}
                  key={variant.slug}
                  onClick={() => chooseVariant(variant.slug)}
                  type="button"
                >
                  <span>
                    <strong>{variant.name}</strong>
                    <small>{variant.language} · {ready}/2 PDFs</small>
                  </span>
                  <span className={`fileState ${ready === 2 ? 'ready' : ''}`}>{ready === 2 ? 'Ready' : 'Needs build'}</span>
                </button>
              )
            })}
          </div>
          <Link className="cvRunHistoryLink" href="/automation">View build history</Link>
        </aside>

        <div className="cvStudioMain">
          {document && selected ? (
            <>
              <section className="cvStudioIdentity" aria-label="Selected CV">
                <div>
                  <div className="eyebrow">{selected.language}</div>
                  <h2>{selected.name}</h2>
                  <p>{selected.focus}</p>
                </div>
                <div className={`editState ${dirty ? 'dirty' : ''}`}>
                  <span aria-hidden="true" />
                  <strong>{dirty ? 'Unsaved edits' : 'Saved locally'}</strong>
                </div>
              </section>

              <div className="cvStudioWorkGrid">
                <section className="workspacePanel cvEditorPanel" aria-labelledby="cv-editor-title">
                  <div className="panelHeading">
                    <div>
                      <div className="eyebrow">Source editor</div>
                      <h2 id="cv-editor-title">Edit by section</h2>
                      <p>Change only facts you can explain confidently in an interview.</p>
                    </div>
                    {dirty ? <button className="textButton" disabled={!hydrated || Boolean(busy)} onClick={resetEdits} type="button">Reset edits</button> : null}
                  </div>
                  <div className="cvEditorGrid">
                    <div className="cvSectionList" aria-label="CV sections">
                      {parts.map((part) => (
                        <button className={selectedPart?.id === part.id ? 'active' : ''} disabled={!hydrated || Boolean(busy)} key={part.id} onClick={() => setSelectedPartId(part.id)} type="button">
                          <span>{part.title}</span>
                          <small>{cvSourceWordCount(part.content)} words</small>
                        </button>
                      ))}
                    </div>
                    {selectedPart ? (
                      <div className="cvSectionEditor">
                        <label htmlFor="cv-section-content">{selectedPart.title}</label>
                        <textarea
                          id="cv-section-content"
                          disabled={!hydrated || Boolean(busy)}
                          maxLength={100000}
                          onChange={(event) => setParts((current) => updateCvSourcePart(current, selectedPart.id, event.target.value))}
                          rows={selectedPart.title === 'Experience' ? 22 : 12}
                          spellCheck
                          value={selectedPart.content}
                        />
                        <div className="cvEditorMeta">
                          <span>{cvSourceWordCount(selectedPart.content)} words · {currentSource.length.toLocaleString()} source characters</span>
                          <span>{selectedPart.title === 'Experience' ? 'Keep role headings as ### and bullets as -' : 'Plain text and - bullets are supported'}</span>
                        </div>
                        {editError ? <p className="errorText" role="alert">{editError}</p> : null}
                      </div>
                    ) : null}
                  </div>
                </section>

                <section className="workspacePanel cvComparePanel" aria-labelledby="cv-compare-title">
                  <div className="panelHeading">
                    <div>
                      <div className="eyebrow">Job comparison</div>
                      <h2 id="cv-compare-title">Check this CV against a role</h2>
                      <p>Uses the saved CV and the same local matching rules as Opportunities.</p>
                    </div>
                  </div>
                  <label className="cvOpportunityPicker">
                    Opportunity
                    <select
                      disabled={!hydrated || comparisonBusy || Boolean(busy)}
                      value={opportunityId}
                      onChange={(event) => {
                        const nextId = event.target.value
                        setOpportunityId(nextId)
                        void loadComparison(selectedSlug, nextId)
                      }}
                    >
                      <option value="">Choose a saved job</option>
                      {opportunities.map((opportunity) => (
                        <option key={opportunity.opportunity_id} value={opportunity.opportunity_id}>
                          {opportunity.title || 'Untitled role'} — {opportunity.company || 'Unknown company'}
                        </option>
                      ))}
                    </select>
                  </label>
                  {dirty && opportunityId ? <div className="cvCompareNotice">Save and rebuild to include your unsaved edits in this comparison.</div> : null}
                  {comparisonBusy ? <div className="cvCompareEmpty">Comparing the saved CV…</div> : null}
                  {comparisonError ? <div className="errorText" role="alert">{comparisonError}</div> : null}
                  {!comparisonBusy && !comparisonError && comparison ? <ComparisonResult comparison={comparison} /> : null}
                  {!comparisonBusy && !comparisonError && !comparison ? (
                    <div className="cvCompareEmpty">Choose a saved opportunity to see matching phrases, gaps, and the recommended variant.</div>
                  ) : null}
                </section>
              </div>

              <section className="workspacePanel cvPreviewWorkspace" aria-labelledby="cv-preview-title">
                <div className="panelHeading cvPreviewHeading">
                  <div>
                    <div className="eyebrow">Finished documents</div>
                    <h2 id="cv-preview-title">Visual and ATS preview</h2>
                    <p>Review both files side by side before downloading or applying.</p>
                  </div>
                  <div className="cvPreviewDownloads">
                    {selected.files.visual.exists ? <a className="buttonLink" href={selected.files.visual.downloadUrl}>Download visual</a> : null}
                    {selected.files.ats.exists ? <a className="buttonLink" href={selected.files.ats.downloadUrl}>Download ATS</a> : null}
                  </div>
                </div>
                <div className="cvPreviewGrid">
                  <CvPreview
                    file={selected.files.visual}
                    label="Visual PDF"
                    previewRevision={previewRevision}
                    variantName={selected.name}
                  />
                  <CvPreview
                    file={selected.files.ats}
                    label="ATS PDF"
                    previewRevision={previewRevision}
                    variantName={selected.name}
                  />
                </div>
                <div className="sourceLine">
                  <span>Protected source</span>
                  <code>cv/{document.source_filename}</code>
                  <span>Updated {formatDate(document.source_updated_at)}</span>
                </div>
              </section>

              <section className="workspacePanel cvVersionPanel" aria-labelledby="cv-version-title">
                <div className="panelHeading">
                  <div>
                    <div className="eyebrow">Recovery</div>
                    <h2 id="cv-version-title">Source history</h2>
                    <p>A private snapshot is created before every saved edit or restore.</p>
                  </div>
                  <span className="versionCount">{document.versions.length} shown</span>
                </div>
                {document.versions.length ? (
                  <div className="cvVersionList">
                    {document.versions.map((version) => (
                      <div key={version.version_id}>
                        <span>
                          <strong>{versionReason(version.reason)}</strong>
                          <small>{formatDate(version.created_at)} · {version.word_count} words · {version.content_hash.slice(0, 8)}</small>
                        </span>
                        <button className="button secondary" disabled={!hydrated || Boolean(busy) || dirty} onClick={() => restoreVersion(version.version_id)} type="button">
                          {busy === 'restore' ? 'Restoring…' : 'Restore'}
                        </button>
                      </div>
                    ))}
                  </div>
                ) : <div className="emptyState">No earlier source versions yet. The first saved edit will create one automatically.</div>}
              </section>
            </>
          ) : (
            <section className="workspacePanel emptyState cvStudioUnavailable">
              <strong>CV editing is temporarily unavailable.</strong>
              <span>The existing PDF library is still safe. Try loading this source again.</span>
              <button className="button" disabled={!hydrated || Boolean(busy)} onClick={() => loadDocument(selectedSlug)} type="button">Try again</button>
            </section>
          )}
        </div>
      </div>
    </>
  )
}
