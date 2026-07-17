'use client'

import Link from 'next/link'

import type { CvLibrary } from '../../lib/cv-data'
import type { CvJobComparison } from '../../lib/cv-studio-types'

export function formatBytes(bytes: number): string {
  if (!bytes) return 'Not generated'
  return `${(bytes / 1024).toFixed(0)} KB`
}

export function formatDate(value: string | null): string {
  if (!value) return 'Not generated'
  return new Date(value).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })
}

export function CvPreview({
  file,
  label,
  previewRevision,
  variantName,
}: {
  file: CvLibrary['variants'][number]['files']['visual']
  label: string
  previewRevision: string
  variantName: string
}) {
  return (
    <article className="cvPreviewDocument">
      <div>
        <span>{label}</span>
        <small>{formatBytes(file.sizeBytes)} · {formatDate(file.updatedAt)}</small>
      </div>
      {file.exists ? (
        <iframe
          className="pdfPreview"
          key={`${file.previewUrl}-${previewRevision}`}
          src={`${file.previewUrl}?revision=${encodeURIComponent(previewRevision)}`}
          title={`${variantName} ${label} preview`}
        />
      ) : (
        <div className="pdfEmptyState">
          <strong>This PDF has not been generated.</strong>
          <span>Rebuild this CV and the preview will appear here.</span>
        </div>
      )}
    </article>
  )
}

export function ComparisonResult({ comparison }: { comparison: CvJobComparison }) {
  return (
    <div className="cvComparisonResult">
      <div className="cvComparisonHeading">
        <span>
          <strong>{comparison.opportunity.title}</strong>
          <small>{comparison.opportunity.company} {comparison.opportunity.location ? `· ${comparison.opportunity.location}` : ''}</small>
        </span>
        <span className={comparison.is_recommended ? 'recommended' : ''}>
          {comparison.is_recommended ? 'Recommended CV' : `Recommended: ${comparison.recommended_variant.replaceAll('-', ' ')}`}
        </span>
      </div>
      <div className="cvComparisonScore">
        <div><strong>{comparison.score.toFixed(1)}</strong><span>keyword score</span></div>
        <div><strong>{comparison.rank}/{comparison.variant_count}</strong><span>CV rank</span></div>
      </div>
      <ComparisonTerms title="Matching phrases" terms={comparison.keyword_hits} empty="No configured matching phrase was found." />
      <div className="cvGapList">
        <h3>Possible wording gaps</h3>
        {comparison.keyword_gaps.length ? (
          <div>{comparison.keyword_gaps.map((gap) => <span key={gap.keyword}>{gap.keyword}<small>×{gap.count}</small></span>)}</div>
        ) : <p>No prominent lexical gap was found.</p>}
        <small>Add wording only when it is true and interview-defensible.</small>
      </div>
      {comparison.negative_hits.length ? <ComparisonTerms title="Possible mismatch signals" terms={comparison.negative_hits} empty="" warning /> : null}
      <Link className="textButton" href={`/opportunities?opportunity=${encodeURIComponent(comparison.opportunity.opportunity_id)}`}>Open full opportunity evidence →</Link>
    </div>
  )
}

function ComparisonTerms({
  title,
  terms,
  empty,
  warning = false,
}: {
  title: string
  terms: string[]
  empty: string
  warning?: boolean
}) {
  return (
    <div className={`cvComparisonTerms ${warning ? 'warning' : ''}`}>
      <h3>{title}</h3>
      {terms.length ? <div>{terms.map((term) => <span key={term}>{term}</span>)}</div> : <p>{empty}</p>}
    </div>
  )
}
