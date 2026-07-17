import type {
  CvJobComparison,
  CvStudioDocument,
  CvStudioMutationResult,
} from './cv-studio-types'
import { getCvVariantDefinition } from './cv-data'
import { isOpportunityId } from './opportunity-shared'
import { runPythonHelper } from './server/python-bridge'

const versionIdPattern = /^\d{8}T\d{6}Z-[a-f0-9]{12}$/
const maxSourceCharacters = 100_000

type CvStudioCommand = 'get' | 'save' | 'rebuild' | 'restore' | 'compare'

export function isCvStudioVersionId(value: unknown): value is string {
  return typeof value === 'string' && versionIdPattern.test(value)
}

export function isCvStudioContent(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0 && value.length <= maxSourceCharacters
}

function executeHelper<T>(
  command: CvStudioCommand,
  variant: string,
  options: { input?: Record<string, unknown>; versionId?: string; opportunityId?: string } = {},
): Promise<T> {
  const args = [command, '--variant', variant]
  if (options.versionId) args.push('--version-id', options.versionId)
  if (options.opportunityId) args.push('--opportunity-id', options.opportunityId)
  return runPythonHelper<T>('cvStudio', args, {
    input: options.input,
    timeoutMs: ['save', 'rebuild', 'restore'].includes(command) ? 150_000 : 30_000,
    maxOutputBytes: 2 * 1024 * 1024,
    errorLabel: 'The CV Studio action',
  })
}

async function requireVariant(variant: string): Promise<void> {
  if (!await getCvVariantDefinition(variant)) throw new Error('Choose a known CV variant.')
}

export async function getCvStudioDocument(variant: string): Promise<CvStudioDocument> {
  await requireVariant(variant)
  return executeHelper<CvStudioDocument>('get', variant)
}

export async function saveCvStudioDocument(variant: string, content: string): Promise<CvStudioMutationResult> {
  await requireVariant(variant)
  if (!isCvStudioContent(content)) throw new Error('CV content must be between 1 and 100,000 characters.')
  return executeHelper<CvStudioMutationResult>('save', variant, { input: { content } })
}

export async function rebuildCvStudioVariant(variant: string): Promise<CvStudioMutationResult> {
  await requireVariant(variant)
  return executeHelper<CvStudioMutationResult>('rebuild', variant)
}

export async function restoreCvStudioVersion(variant: string, versionId: string): Promise<CvStudioMutationResult> {
  await requireVariant(variant)
  if (!isCvStudioVersionId(versionId)) throw new Error('Choose a valid CV version.')
  return executeHelper<CvStudioMutationResult>('restore', variant, { versionId })
}

export async function compareCvWithOpportunity(variant: string, opportunityId: string): Promise<CvJobComparison> {
  await requireVariant(variant)
  if (!isOpportunityId(opportunityId)) throw new Error('Choose a valid opportunity.')
  return executeHelper<CvJobComparison>('compare', variant, { opportunityId })
}
