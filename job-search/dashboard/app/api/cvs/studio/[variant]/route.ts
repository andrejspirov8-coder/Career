import {
  getCvStudioDocument,
  isCvStudioContent,
  isCvStudioVersionId,
  rebuildCvStudioVariant,
  restoreCvStudioVersion,
  saveCvStudioDocument,
} from '../../../../../lib/cv-studio'
import { getCvVariantDefinition } from '../../../../../lib/cv-data'
import {
  dashboardAuthErrorResponse,
  dashboardJsonResponse,
  dashboardMutationAuthErrorResponse,
} from '../../../../../lib/server/auth'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(
  request: Request,
  { params }: { params: Promise<{ variant: string }> },
) {
  const authError = dashboardAuthErrorResponse(request)
  if (authError) return authError
  const { variant } = await params
  if (!await getCvVariantDefinition(variant)) {
    return dashboardJsonResponse({ ok: false, error: 'Unknown CV variant.' }, { status: 404 })
  }
  try {
    return dashboardJsonResponse({ ok: true, data: await getCvStudioDocument(variant) })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'CV source could not be loaded.'
    return dashboardJsonResponse({ ok: false, error: message }, { status: 422 })
  }
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ variant: string }> },
) {
  const authError = dashboardMutationAuthErrorResponse(request)
  if (authError) return authError
  const { variant } = await params
  if (!await getCvVariantDefinition(variant)) {
    return dashboardJsonResponse({ ok: false, error: 'Unknown CV variant.' }, { status: 404 })
  }

  let body: { action?: unknown; content?: unknown; versionId?: unknown }
  try {
    body = (await request.json()) as typeof body
  } catch {
    return dashboardJsonResponse({ ok: false, error: 'Invalid CV Studio request.' }, { status: 400 })
  }

  try {
    if (body.action === 'save_rebuild') {
      if (!isCvStudioContent(body.content)) {
        return dashboardJsonResponse(
          { ok: false, error: 'CV content must be between 1 and 100,000 characters.' },
          { status: 400 },
        )
      }
      return dashboardJsonResponse({ ok: true, data: await saveCvStudioDocument(variant, body.content) })
    }
    if (body.action === 'rebuild_selected') {
      return dashboardJsonResponse({ ok: true, data: await rebuildCvStudioVariant(variant) })
    }
    if (body.action === 'restore_version') {
      if (!isCvStudioVersionId(body.versionId)) {
        return dashboardJsonResponse({ ok: false, error: 'Choose a valid CV version.' }, { status: 400 })
      }
      return dashboardJsonResponse({ ok: true, data: await restoreCvStudioVersion(variant, body.versionId) })
    }
    return dashboardJsonResponse({ ok: false, error: 'Unsupported CV Studio action.' }, { status: 400 })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'CV Studio update failed.'
    return dashboardJsonResponse({ ok: false, error: message }, { status: 422 })
  }
}
