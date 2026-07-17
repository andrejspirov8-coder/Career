import { getCvLibrary } from './cv-data'
import type { GlobalSearchResponse, GlobalSearchResult } from './global-search-types'
import { getOpportunityOverview } from './opportunity-data'
import { getRecruiterOverview, type RecruiterQueueRow } from './recruiter-data'

function includesQuery(values: Array<string | undefined>, query: string) {
  return values.some((value) => (value || '').toLocaleLowerCase().includes(query))
}

function uniqueRecruiters(rows: RecruiterQueueRow[]) {
  const byUrl = new Map<string, RecruiterQueueRow>()
  for (const row of rows) {
    if (row.profile_url && !byUrl.has(row.profile_url)) byUrl.set(row.profile_url, row)
  }
  return Array.from(byUrl.values())
}

export async function buildGlobalSearch(rawQuery: string): Promise<GlobalSearchResponse> {
  const query = rawQuery.trim().toLocaleLowerCase()
  const [opportunities, recruiters, cvs] = await Promise.all([
    getOpportunityOverview(),
    getRecruiterOverview().catch(() => null),
    getCvLibrary(),
  ])
  const results: GlobalSearchResult[] = []

  for (const row of opportunities.queues.all) {
    if (!includesQuery([row.title, row.company, row.location, row.match?.role_track], query)) continue
    results.push({
      kind: 'opportunity',
      id: row.opportunity_id,
      title: row.title || row.company || 'Saved opportunity',
      subtitle: [row.company, row.location].filter(Boolean).join(' · ') || 'Opportunity',
      href: `/opportunities?opportunity=${encodeURIComponent(row.opportunity_id)}&view=stage_${encodeURIComponent(row.stage)}`,
    })
    if (results.filter((item) => item.kind === 'opportunity').length >= 6) break
  }

  if (recruiters) {
    const recruiterRows = uniqueRecruiters([
      ...recruiters.queues.auto_send,
      ...recruiters.queues.review,
      ...recruiters.queues.skipped,
      ...recruiters.queues.sent,
    ])
    for (const row of recruiterRows) {
      if (!includesQuery([row.name, row.company, row.headline, row.persona], query)) continue
      results.push({
        kind: 'recruiter',
        id: row.profile_url,
        title: row.name || 'Recruiter profile',
        subtitle: [row.company, row.persona].filter(Boolean).join(' · ') || 'Recruiter',
        href: `/recruiters?q=${encodeURIComponent(row.name || row.company || row.profile_url)}`,
      })
      if (results.filter((item) => item.kind === 'recruiter').length >= 4) break
    }
  }

  for (const variant of cvs.variants) {
    if (!includesQuery([variant.name, variant.focus, variant.language, variant.slug], query)) continue
    results.push({
      kind: 'cv',
      id: variant.slug,
      title: variant.name,
      subtitle: `${variant.language} · CV variant`,
      href: `/cvs?variant=${encodeURIComponent(variant.slug)}`,
    })
    if (results.filter((item) => item.kind === 'cv').length >= 3) break
  }

  return { query: rawQuery.trim(), results }
}
