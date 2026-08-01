import { defineConfig, globalIgnores } from 'eslint/config'
import nextVitals from 'eslint-config-next/core-web-vitals'
import nextTs from 'eslint-config-next/typescript'

export default defineConfig([
  globalIgnores(['.next/**', 'node_modules/**', 'playwright-report/**', 'test-results/**', 'lib/generated/**']),
  {
    ...nextVitals[0],
    rules: {
      ...nextVitals[0].rules,
      'react-hooks/set-state-in-effect': 'off',
      'react-hooks/purity': 'off',
    },
  },
  ...nextVitals.slice(1),
  ...nextTs,
])
