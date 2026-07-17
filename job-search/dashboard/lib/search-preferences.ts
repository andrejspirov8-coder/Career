import {
  type PreferenceSuggestion,
  type SearchPreferences,
  type WorkArrangement,
  workArrangementValues,
} from './search-preference-types'
import { runPythonHelper } from './server/python-bridge'

export type { PreferenceSuggestion, SearchPreferences, WorkArrangement } from './search-preference-types'

const preferenceKeys = new Set([
  'schema',
  'target_roles',
  'priority_locations',
  'work_arrangements',
  'minimum_salary_eur_monthly',
  'excluded_keywords',
  'excluded_companies',
  'daily_queue_size',
  'updated_at',
])

function cleanTextList(value: unknown, name: string, limit: number): string[] {
  if (!Array.isArray(value) || value.length > limit) {
    throw new Error(`${name} must be a list with at most ${limit} items.`)
  }
  const cleaned: string[] = []
  const seen = new Set<string>()
  for (const item of value) {
    if (typeof item !== 'string') throw new Error(`${name} may contain text only.`)
    const text = item.trim().replace(/\s+/g, ' ')
    if (!text) continue
    if (text.length > 80) throw new Error(`${name} items must be 80 characters or fewer.`)
    const identity = text.toLocaleLowerCase()
    if (!seen.has(identity)) {
      seen.add(identity)
      cleaned.push(text)
    }
  }
  return cleaned
}

export function validateSearchPreferences(value: unknown): SearchPreferences {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Search preferences must be an object.')
  }
  const input = value as Record<string, unknown>
  const unknownKeys = Object.keys(input).filter((key) => !preferenceKeys.has(key))
  if (unknownKeys.length) throw new Error(`Unsupported search preference: ${unknownKeys[0]}.`)

  const workArrangements = input.work_arrangements
  if (
    !Array.isArray(workArrangements) ||
    !workArrangements.length ||
    workArrangements.length > workArrangementValues.length ||
    workArrangements.some((item) => !workArrangementValues.includes(item as WorkArrangement))
  ) {
    throw new Error('Choose at least one valid work arrangement.')
  }

  const queueSize = input.daily_queue_size
  if (!Number.isInteger(queueSize) || Number(queueSize) < 5 || Number(queueSize) > 10) {
    throw new Error('Daily queue size must be between 5 and 10.')
  }

  const salary = input.minimum_salary_eur_monthly
  if (salary !== null && (!Number.isInteger(salary) || Number(salary) < 0 || Number(salary) > 100_000)) {
    throw new Error('Minimum salary must be a whole monthly EUR amount between 0 and 100,000.')
  }

  return {
    schema: 'career_search_preferences_v1',
    target_roles: cleanTextList(input.target_roles, 'Target roles', 20),
    priority_locations: cleanTextList(input.priority_locations, 'Priority locations', 20),
    work_arrangements: Array.from(new Set(workArrangements)) as WorkArrangement[],
    minimum_salary_eur_monthly: salary === null ? null : Number(salary),
    excluded_keywords: cleanTextList(input.excluded_keywords, 'Excluded keywords', 50),
    excluded_companies: cleanTextList(input.excluded_companies, 'Excluded companies', 50),
    daily_queue_size: Number(queueSize),
    updated_at: typeof input.updated_at === 'string' ? input.updated_at : '',
  }
}

async function runPreferenceHelper(args: string[]): Promise<SearchPreferences> {
  const data = await runPythonHelper<unknown>('searchPreferences', args, {
    timeoutMs: 30_000,
    maxOutputBytes: 1024 * 1024,
    errorLabel: 'Search preference helper',
  })
  return validateSearchPreferences(data)
}

export async function getSearchPreferences(): Promise<SearchPreferences> {
  return runPreferenceHelper(['show'])
}

export async function saveSearchPreferences(value: unknown): Promise<SearchPreferences> {
  const preferences = validateSearchPreferences(value)
  return runPreferenceHelper(['save', '--json', JSON.stringify(preferences)])
}

export function validatePreferenceSuggestion(value: unknown): PreferenceSuggestion {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Preference suggestion is invalid.')
  }
  const input = value as Record<string, unknown>
  if (input.kind !== 'add_excluded_company' && input.kind !== 'add_excluded_keyword') {
    throw new Error('Preference suggestion type is invalid.')
  }
  if (typeof input.value !== 'string' || !input.value.trim() || input.value.trim().length > 80) {
    throw new Error('Preference suggestion value is invalid.')
  }
  return {
    kind: input.kind,
    value: input.value.trim(),
    label: typeof input.label === 'string' && input.label.length <= 160 ? input.label : 'Apply suggestion',
  }
}

export async function applyPreferenceSuggestion(value: unknown): Promise<SearchPreferences> {
  const suggestion = validatePreferenceSuggestion(value)
  const current = await getSearchPreferences()
  const field = suggestion.kind === 'add_excluded_company' ? 'excluded_companies' : 'excluded_keywords'
  return saveSearchPreferences({
    ...current,
    [field]: [...current[field], suggestion.value],
  })
}
