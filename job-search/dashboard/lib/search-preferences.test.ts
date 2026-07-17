import { describe, expect, it } from 'vitest'

import { validatePreferenceSuggestion, validateSearchPreferences } from './search-preferences'

const validPreferences = {
  schema: 'career_search_preferences_v1',
  target_roles: ['Customer Operations', 'customer operations'],
  priority_locations: ['Vilnius', 'Remote EU'],
  work_arrangements: ['hybrid', 'remote_eu'],
  minimum_salary_eur_monthly: 3000,
  excluded_keywords: [],
  excluded_companies: [],
  daily_queue_size: 7,
  updated_at: '',
}

describe('search preference validation', () => {
  it('normalizes duplicate text and accepts a queue between five and ten', () => {
    expect(validateSearchPreferences(validPreferences)).toMatchObject({
      target_roles: ['Customer Operations'],
      daily_queue_size: 7,
      work_arrangements: ['hybrid', 'remote_eu'],
    })
  })

  it('rejects oversized queues and unknown fields', () => {
    expect(() => validateSearchPreferences({ ...validPreferences, daily_queue_size: 11 })).toThrow(/between 5 and 10/i)
    expect(() => validateSearchPreferences({ ...validPreferences, secret: 'unexpected' })).toThrow(/unsupported/i)
  })

  it('accepts only bounded, allow-listed human approval suggestions', () => {
    expect(validatePreferenceSuggestion({
      kind: 'add_excluded_company',
      value: 'Example Company',
      label: 'Exclude Example Company',
    })).toEqual({
      kind: 'add_excluded_company',
      value: 'Example Company',
      label: 'Exclude Example Company',
    })
    expect(() => validatePreferenceSuggestion({ kind: 'replace_all_roles', value: 'x' })).toThrow(/type is invalid/i)
  })
})
