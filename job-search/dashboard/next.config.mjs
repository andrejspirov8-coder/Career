import { dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const dashboardBuiltAt = new Date().toISOString()

/** @type {import('next').NextConfig} */
const nextConfig = {
  poweredByHeader: false,
  env: {
    CAREER_DASHBOARD_BUILT_AT: dashboardBuiltAt,
  },
  turbopack: {
    root: __dirname,
  },
}

export default nextConfig
