import { configDefaults, defineConfig } from 'vitest/config'
import { resolve } from 'path'

export default defineConfig({
  resolve: {
    alias: {
      '@': resolve(__dirname, '.'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./lib/__tests__/setup.ts'],
    exclude: [
      ...configDefaults.exclude,
      'e2e/**',
      'playwright-report/**',
      'test-results/**',
    ],
  },
})
