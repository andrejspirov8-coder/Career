import { requireDashboardPageAuth } from '@/lib/dashboard-page-auth'
import { getCvLibrary } from '@/lib/cv-data'
import { getCvStudioDocument } from '@/lib/cv-studio'
import { getOpportunityOverview } from '@/lib/opportunity-data'
import CvLibraryConsole from './cv-library-console'

export const dynamic = 'force-dynamic'

export default async function CvLibraryPage({ searchParams }: { searchParams: Promise<{ variant?: string }> }) {
  await requireDashboardPageAuth('/cvs')
  const params = await searchParams
  const library = await getCvLibrary()
  const initialVariant = library.variants.find((variant) => variant.slug === params.variant)?.slug
    || library.variants[0].slug
  const [initialDocument, opportunityOverview] = await Promise.all([
    getCvStudioDocument(initialVariant).catch(() => null),
    getOpportunityOverview(),
  ])
  const opportunityOptions = opportunityOverview.queues.all
    .filter((row) => !['skipped', 'expired'].includes(row.status))
    .sort((left, right) => Number(right.match?.score || 0) - Number(left.match?.score || 0))
    .slice(0, 100)
  return (
    <main className="workspaceMain">
      <CvLibraryConsole
        initialLibrary={library}
        initialDocument={initialDocument}
        initialOpportunities={opportunityOptions}
        initialVariant={initialVariant}
      />
    </main>
  )
}
