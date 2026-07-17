import { existsSync, statSync } from 'node:fs'
import { join } from 'node:path'

import { runPythonHelper } from './server/python-bridge'
import { repositoryRoot } from './server/repository'

const cvRoot = join(repositoryRoot, 'cv')
const outputRoot = join(repositoryRoot, 'output')

export type CvFormat = 'visual' | 'ats'

export type CvVariantDefinition = {
  slug: string
  name: string
  language: 'English' | 'Lithuanian'
  focus: string
  sourceFilename: string
  pdfStem: string
}

type CvCatalogueV1 = {
  schema: 'cv_catalogue_v1'
  variants: Array<{
    slug: string
    name: string
    language: 'English' | 'Lithuanian'
    focus: string
    source_filename: string
    pdf_stem: string
  }>
}

export type CvFileInfo = {
  format: CvFormat
  label: string
  filename: string
  exists: boolean
  sizeBytes: number
  updatedAt: string | null
  previewUrl: string
  downloadUrl: string
}

export type CvVariant = CvVariantDefinition & {
  sourceExists: boolean
  sourceUpdatedAt: string | null
  files: Record<CvFormat, CvFileInfo>
}

export type CvLibrary = {
  schema: 'career_cv_library_v1'
  generatedAt: string
  counts: {
    variants: number
    expectedPdfs: number
    readyPdfs: number
    missingPdfs: number
  }
  variants: CvVariant[]
}

let definitionsPromise: Promise<readonly CvVariantDefinition[]> | null = null

function validCatalogue(value: unknown): value is CvCatalogueV1 {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const catalogue = value as Partial<CvCatalogueV1>
  if (catalogue.schema !== 'cv_catalogue_v1' || !Array.isArray(catalogue.variants)) return false
  return catalogue.variants.length > 0 && catalogue.variants.every((variant) => (
    Boolean(variant)
    && typeof variant.slug === 'string'
    && typeof variant.name === 'string'
    && (variant.language === 'English' || variant.language === 'Lithuanian')
    && typeof variant.focus === 'string'
    && typeof variant.source_filename === 'string'
    && typeof variant.pdf_stem === 'string'
  ))
}

export async function getCvVariantDefinitions(): Promise<readonly CvVariantDefinition[]> {
  if (!definitionsPromise) {
    definitionsPromise = runPythonHelper<unknown>('cvCatalogue', [], {
      timeoutMs: 15_000,
      maxOutputBytes: 2 * 1024 * 1024,
      errorLabel: 'CV catalogue helper',
    }).then((catalogue) => {
      if (!validCatalogue(catalogue)) throw new Error('CV catalogue helper returned an invalid contract.')
      const seen = new Set<string>()
      return catalogue.variants.map((variant) => {
        if (seen.has(variant.slug)) throw new Error('CV catalogue contains a duplicate variant.')
        seen.add(variant.slug)
        return {
          slug: variant.slug,
          name: variant.name,
          language: variant.language,
          focus: variant.focus,
          sourceFilename: variant.source_filename,
          pdfStem: variant.pdf_stem,
        }
      })
    }).catch((error) => {
      definitionsPromise = null
      throw error
    })
  }
  return definitionsPromise
}

function safeFileStat(path: string): { sizeBytes: number; updatedAt: string } | null {
  if (!existsSync(path)) return null
  try {
    const stat = statSync(path)
    if (!stat.isFile()) return null
    return { sizeBytes: stat.size, updatedAt: stat.mtime.toISOString() }
  } catch {
    return null
  }
}

function pdfFilename(variant: CvVariantDefinition, format: CvFormat): string {
  return `${variant.pdfStem}${format === 'ats' ? '-ats' : ''}.pdf`
}

function fileInfo(variant: CvVariantDefinition, format: CvFormat): CvFileInfo {
  const filename = pdfFilename(variant, format)
  const stat = safeFileStat(join(outputRoot, filename))
  const route = `/api/cvs/${variant.slug}/${format}`
  return {
    format,
    label: format === 'visual' ? 'Visual PDF' : 'ATS PDF',
    filename,
    exists: Boolean(stat),
    sizeBytes: stat?.sizeBytes || 0,
    updatedAt: stat?.updatedAt || null,
    previewUrl: route,
    downloadUrl: `${route}?download=1`,
  }
}

export function isCvFormat(value: unknown): value is CvFormat {
  return value === 'visual' || value === 'ats'
}

export async function getCvVariantDefinition(slug: string): Promise<CvVariantDefinition | null> {
  const definitions = await getCvVariantDefinitions()
  return definitions.find((variant) => variant.slug === slug) || null
}

export async function resolveCvPdf(
  slug: string,
  format: CvFormat,
): Promise<{ path: string; filename: string } | null> {
  const variant = await getCvVariantDefinition(slug)
  if (!variant || !isCvFormat(format)) return null
  const filename = pdfFilename(variant, format)
  return { path: join(outputRoot, filename), filename }
}

export async function getCvLibrary(): Promise<CvLibrary> {
  const definitions = await getCvVariantDefinitions()
  const variants = definitions.map((definition): CvVariant => {
    const sourceStat = safeFileStat(join(cvRoot, definition.sourceFilename))
    return {
      ...definition,
      sourceExists: Boolean(sourceStat),
      sourceUpdatedAt: sourceStat?.updatedAt || null,
      files: {
        visual: fileInfo(definition, 'visual'),
        ats: fileInfo(definition, 'ats'),
      },
    }
  })
  const readyPdfs = variants.reduce(
    (count, variant) => count + Number(variant.files.visual.exists) + Number(variant.files.ats.exists),
    0,
  )
  const expectedPdfs = variants.length * 2
  return {
    schema: 'career_cv_library_v1',
    generatedAt: new Date().toISOString(),
    counts: {
      variants: variants.length,
      expectedPdfs,
      readyPdfs,
      missingPdfs: expectedPdfs - readyPdfs,
    },
    variants,
  }
}
