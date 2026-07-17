import type { CvEditorPart } from './cv-studio-types'

function partId(title: string, index: number): string {
  const slug = title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
  return `${slug || 'section'}-${index}`
}

function cleanPartContent(value: string): string {
  return value
    .replace(/^\s*\n/, '')
    .replace(/\n\s*---\s*$/m, '')
    .trim()
}

export function parseCvSource(content: string): CvEditorPart[] {
  const normalized = content.replace(/\r\n?/g, '\n')
  const matches = [...normalized.matchAll(/^## ([^\n]+)$/gm)]
  if (!matches.length) {
    return [{ id: 'name-contact-0', title: 'Name & contact', heading: null, content: normalized.trim() }]
  }

  const header = normalized.slice(0, matches[0].index).replace(/\n\s*---\s*$/, '').trim()
  const parts: CvEditorPart[] = [
    { id: 'name-contact-0', title: 'Name & contact', heading: null, content: header },
  ]
  matches.forEach((match, index) => {
    const start = (match.index || 0) + match[0].length
    const end = matches[index + 1]?.index ?? normalized.length
    const title = match[1].trim()
    parts.push({
      id: partId(title, index + 1),
      title,
      heading: title,
      content: cleanPartContent(normalized.slice(start, end)),
    })
  })
  return parts
}

export function serializeCvSource(parts: readonly CvEditorPart[]): string {
  if (!parts.length) return ''
  const [header, ...sections] = parts
  const blocks = [
    header.content.trim(),
    ...sections.map((part) => `## ${part.heading || part.title}\n\n${part.content.trim()}`),
  ]
  return `${blocks.join('\n\n---\n\n').trim()}\n`
}

export function updateCvSourcePart(
  parts: readonly CvEditorPart[],
  partIdToUpdate: string,
  content: string,
): CvEditorPart[] {
  return parts.map((part) => part.id === partIdToUpdate ? { ...part, content } : part)
}

export function cvSourceWordCount(content: string): number {
  return content.trim() ? content.trim().split(/\s+/).length : 0
}

export function cvSourceEditError(parts: readonly CvEditorPart[]): string {
  if (!parts.length || !parts[0].content.trim().startsWith('# ')) {
    return 'Name and contact must start with “# Name”.'
  }
  const empty = parts.find((part) => !part.content.trim())
  if (empty) return `${empty.title} cannot be empty.`
  const extraHeading = parts.find((part) => /^## /m.test(part.content))
  if (extraHeading) return `Do not add a new ## section inside ${extraHeading.title}.`
  return ''
}
