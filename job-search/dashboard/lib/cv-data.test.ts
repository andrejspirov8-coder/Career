import { describe, expect, it } from 'vitest'

import { getCvLibrary, getCvVariantDefinition, isCvFormat, resolveCvPdf } from './cv-data'

describe('CV library', () => {
  it('indexes six source variants and twelve expected PDFs', async () => {
    const library = await getCvLibrary()

    expect(library.counts.variants).toBe(6)
    expect(library.counts.expectedPdfs).toBe(12)
    expect(library.variants.every((variant) => variant.sourceExists)).toBe(true)
  })

  it('maps only known variants and formats to server-owned PDF paths', async () => {
    const visual = await resolveCvPdf('operations-management', 'visual')

    expect(visual?.filename).toBe('andrej-spirov-cv-operations-management.pdf')
    expect(await resolveCvPdf('../../state/automation', 'visual')).toBeNull()
    expect(await getCvVariantDefinition('missing')).toBeNull()
    expect(isCvFormat('html')).toBe(false)
  })
})
