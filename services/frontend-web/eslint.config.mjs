import nextConfig from 'eslint-config-next';

/**
 * ESLint v9 flat config. `next lint` (and thus `npm run lint`) requires an
 * `eslint.config.*` file since ESLint v9 — there was previously no config
 * file in this repo (pre-existing gap, unrelated to any single feature).
 * This is the standard `eslint-config-next` flat preset with no
 * project-specific overrides.
 */
const eslintConfig = [
  ...nextConfig,
  {
    ignores: [
      'node_modules/**',
      '.next/**',
      'out/**',
      'coverage/**',
    ],
  },
];

export default eslintConfig;
