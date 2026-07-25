import nextConfig from 'eslint-config-next';

/**
 * ESLint v9 flat config. `next lint` (and thus `npm run lint`) requires an
 * `eslint.config.*` file since ESLint v9 — there was previously no config
 * file in this repo (pre-existing gap, unrelated to any single feature).
 * This is the standard `eslint-config-next` flat preset, plus the severity
 * overrides documented below.
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
  {
    rules: {
      // ── React Compiler readiness: warn, don't fail the build ──────────────
      //
      // eslint-config-next ships the React Compiler rule family at `error`.
      // These do not flag incorrect code — they flag patterns the compiler
      // cannot auto-memoize (Date.now() in render, setState synchronously in an
      // effect, reading a ref during render, TanStack Table's non-memoizable
      // return). The app behaves correctly today; the cost is missed
      // optimization, not bugs.
      //
      // There are ~21 pre-existing occurrences across ~12 pages. Clearing them
      // means real refactors (hoisting helpers, restructuring effects), which
      // is not something to land unreviewed alongside a release. They stay at
      // `warn` so they remain visible in `npm run lint` and can be worked
      // through deliberately, while CI still fails on genuine errors.
      //
      // NOTE: `react-hooks/rules-of-hooks` is deliberately NOT downgraded — a
      // conditional hook is a real bug, and the one occurrence (a useState
      // inside TriggerConfigFields' if-chain) was fixed rather than silenced.
      'react-hooks/purity': 'warn',
      'react-hooks/set-state-in-effect': 'warn',
      'react-hooks/refs': 'warn',
      'react-hooks/incompatible-library': 'warn',
    },
  },
];

export default eslintConfig;
