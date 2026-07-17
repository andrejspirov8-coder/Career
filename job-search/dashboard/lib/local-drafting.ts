import type { LocalDraftResult, LocalDraftType, LocalDraftingStatus } from './local-drafting-types'
import { isOpportunityId } from './opportunity-shared'
import { runPythonHelper } from './server/python-bridge'

const modelPattern = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$/

export function isLocalDraftType(value: unknown): value is LocalDraftType {
  return value === 'cover_letter' || value === 'follow_up'
}

export function isLocalModelName(value: unknown): value is string {
  return typeof value === 'string' && modelPattern.test(value) && !value.includes('://')
}

function executeHelper<T>(command: 'status' | 'save-settings' | 'draft', input?: Record<string, unknown>): Promise<T> {
  return runPythonHelper<T>('localDrafting', [command], {
    input,
    timeoutMs: command === 'draft' ? 150_000 : 15_000,
    maxOutputBytes: 2 * 1024 * 1024,
    errorLabel: command === 'draft' ? 'The local draft' : 'Local drafting status',
  })
}

export function getLocalDraftingStatus(): Promise<LocalDraftingStatus> {
  return executeHelper<LocalDraftingStatus>('status')
}

export function saveLocalDraftingSettings(enabled: boolean, model: string): Promise<LocalDraftingStatus> {
  if (typeof enabled !== 'boolean' || !isLocalModelName(model)) throw new Error('Invalid local drafting settings.')
  return executeHelper<LocalDraftingStatus>('save-settings', { enabled, model })
}

export function generateLocalDraft(input: {
  opportunityId: string
  draftType: LocalDraftType
  instructions: string
}): Promise<LocalDraftResult> {
  if (!isOpportunityId(input.opportunityId)) throw new Error('Choose a valid opportunity.')
  if (!isLocalDraftType(input.draftType)) throw new Error('Choose a valid draft type.')
  if (typeof input.instructions !== 'string' || input.instructions.length > 1000) {
    throw new Error('Draft instructions must be 1,000 characters or fewer.')
  }
  return executeHelper<LocalDraftResult>('draft', {
    opportunity_id: input.opportunityId,
    draft_type: input.draftType,
    instructions: input.instructions,
  })
}
