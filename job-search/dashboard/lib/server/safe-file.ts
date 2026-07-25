import { lstatSync, realpathSync, statSync } from 'node:fs'
import { lstat as lstatAsync, realpath as realpathAsync, stat as statAsync } from 'node:fs/promises'
import { relative, resolve, sep } from 'node:path'

export type SafeFile = {
  path: string
  size: number
  updatedAt: string
  relativePath?: string
}

function isInside(root: string, candidate: string): boolean {
  const boundary = `${root}${sep}`
  return candidate === root || candidate.startsWith(boundary)
}

function allowedExtension(path: string, extensions?: readonly string[]): boolean {
  if (!extensions?.length) return true
  const lower = path.toLowerCase()
  return extensions.some((extension) => lower.endsWith(extension.toLowerCase()))
}

function hasSymlinkBetween(root: string, candidate: string): boolean {
  if (lstatSync(root).isSymbolicLink()) return true
  let current = root
  for (const part of relative(root, candidate).split(sep).filter(Boolean)) {
    current = resolve(current, part)
    if (lstatSync(current).isSymbolicLink()) return true
  }
  return false
}

export function resolveSafeFileSync(
  candidatePath: string,
  rootPath: string,
  maxBytes: number,
  extensions?: readonly string[],
): SafeFile | null {
  try {
    const root = resolve(rootPath)
    const candidate = resolve(candidatePath)
    if (!isInside(root, candidate) || !allowedExtension(candidate, extensions)) return null
    if (hasSymlinkBetween(root, candidate)) return null
    const realRoot = realpathSync(root)
    const actual = realpathSync(candidate)
    if (!isInside(realRoot, actual)) return null
    const details = statSync(actual)
    if (!details.isFile() || details.size > maxBytes) return null
    return { path: actual, size: details.size, updatedAt: details.mtime.toISOString(), relativePath: relative(root, actual) }
  } catch {
    return null
  }
}

export async function resolveSafeFile(
  candidatePath: string,
  rootPath: string,
  maxBytes: number,
  extensions?: readonly string[],
): Promise<SafeFile | null> {
  try {
    const root = resolve(rootPath)
    const candidate = resolve(candidatePath)
    if (!isInside(root, candidate) || !allowedExtension(candidate, extensions)) return null
    let current = root
    if ((await lstatAsync(current)).isSymbolicLink()) return null
    for (const part of relative(root, candidate).split(sep).filter(Boolean)) {
      current = resolve(current, part)
      if ((await lstatAsync(current)).isSymbolicLink()) return null
    }
    const realRoot = await realpathAsync(root)
    const actual = await realpathAsync(candidate)
    if (!isInside(realRoot, actual)) return null
    const details = await statAsync(actual)
    if (!details.isFile() || details.size > maxBytes) return null
    return { path: actual, size: details.size, updatedAt: details.mtime.toISOString(), relativePath: relative(root, actual) }
  } catch {
    return null
  }
}
