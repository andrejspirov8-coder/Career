import { describe, expect, it } from 'vitest'

import {
  cvSourceEditError,
  cvSourceWordCount,
  parseCvSource,
  serializeCvSource,
  updateCvSourcePart,
} from './cv-source-editor'

const source = `# Andrej Spirov

contact@example.com | Vilnius

---

## Target Title

Operations Manager

---

## Core Skills

- Operations
- Reporting

---

## Experience

### Area Manager

- Led five stores.
`

describe('CV source editor', () => {
  it('parses a CV into beginner-friendly editable sections and round-trips it', () => {
    const parts = parseCvSource(source)

    expect(parts.map((part) => part.title)).toEqual([
      'Name & contact',
      'Target Title',
      'Core Skills',
      'Experience',
    ])
    expect(serializeCvSource(parts)).toBe(source)
  })

  it('updates one section without changing the others', () => {
    const parts = parseCvSource(source)
    const target = parts.find((part) => part.title === 'Target Title')
    const updated = updateCvSourcePart(parts, target?.id || '', 'Customer Operations Manager')

    expect(serializeCvSource(updated)).toContain('## Target Title\n\nCustomer Operations Manager')
    expect(serializeCvSource(updated)).toContain('### Area Manager')
  })

  it('reports unsafe nested sections and provides stable word counts', () => {
    const parts = parseCvSource(source)
    expect(cvSourceWordCount(source)).toBeGreaterThan(10)
    expect(cvSourceEditError(parts)).toBe('')
    expect(cvSourceEditError(updateCvSourcePart(parts, parts[1].id, 'Title\n## Surprise')))
      .toContain('Do not add a new ## section')
  })
})
