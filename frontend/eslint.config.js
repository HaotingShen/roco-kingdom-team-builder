import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { globalIgnores } from 'eslint/config'

export default tseslint.config([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs['recommended-latest'],
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    rules: {
      // Downgrade to warn: any types are used intentionally in many API/dynamic data patterns
      '@typescript-eslint/no-explicit-any': 'warn',
      // Downgrade to warn: fast-refresh export issue is a dev-tooling concern, not a runtime bug
      'react-refresh/only-export-components': 'warn',
      // Allow unused vars if prefixed with _ (intentionally ignored)
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      // Control characters in regex are intentional in the username validator
      'no-control-regex': 'warn',
    },
  },
])
