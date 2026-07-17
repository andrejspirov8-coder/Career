import { describe, expect, it } from 'vitest'
import { safeLinkedInProfileUrl } from './recruiter-links'

describe('safeLinkedInProfileUrl', () => {
  it('keeps LinkedIn profile links and removes tracking data', () => {
    expect(safeLinkedInProfileUrl('https://www.linkedin.com/in/safe-profile/?trk=dashboard#contact')).toBe(
      'https://www.linkedin.com/in/safe-profile/',
    )
    expect(safeLinkedInProfileUrl('https://lt.linkedin.com/in/safe-profile')).toBe(
      'https://lt.linkedin.com/in/safe-profile',
    )
  })

  it('rejects non-profile, non-HTTPS, credential, and lookalike links', () => {
    expect(safeLinkedInProfileUrl('javascript:alert(1)')).toBeNull()
    expect(safeLinkedInProfileUrl('http://www.linkedin.com/in/insecure')).toBeNull()
    expect(safeLinkedInProfileUrl('https://linkedin.example/in/lookalike')).toBeNull()
    expect(safeLinkedInProfileUrl('https://user:pass@www.linkedin.com/in/credential')).toBeNull()
    expect(safeLinkedInProfileUrl('https://www.linkedin.com/jobs/view/123')).toBeNull()
  })
})
