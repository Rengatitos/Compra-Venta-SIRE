import js from '@eslint/js';
import jsxA11y from 'eslint-plugin-jsx-a11y';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['dist', 'coverage'] },
  {
    files: ['**/*.{ts,tsx}'],
    extends: [js.configs.recommended, ...tseslint.configs.recommendedTypeChecked],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
      parserOptions: {
        project: ['./tsconfig.app.json', './tsconfig.node.json'],
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
      'jsx-a11y': jsxA11y,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      ...jsxA11y.flatConfigs.strict.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      // Una región con scroll debe ser enfocable para poder recorrerla con el
      // teclado (regla scrollable-region-focusable de axe). La regla por defecto
      // solo lo admite en tabpanel, así que se añaden los roles que usamos.
      'jsx-a11y/no-noninteractive-tabindex': [
        'error',
        { tags: [], roles: ['tabpanel', 'group', 'region'], allowExpressionValues: true },
      ],
      '@typescript-eslint/consistent-type-imports': 'error',
      // Un argumento prefijado con _ se declara para cumplir una firma sin
      // usarlo (por ejemplo useDocumentTitle, que ignora el título recibido).
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrors: 'all' },
      ],
      '@typescript-eslint/no-unnecessary-condition': 'off',
      'no-restricted-globals': [
        'error',
        { name: 'fetch', message: 'Usa el cliente de src/lib/http.ts.' },
      ],
      'no-restricted-properties': [
        'error',
        { object: 'window', property: 'fetch', message: 'Usa el cliente de src/lib/http.ts.' },
      ],
    },
  },
  {
    files: ['src/lib/http.ts', 'src/test/**/*.ts'],
    rules: { 'no-restricted-globals': 'off', 'no-restricted-properties': 'off' },
  },
);
