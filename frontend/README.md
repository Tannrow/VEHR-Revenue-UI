# VEHR Frontend

## Local Development

```bash
npm install
npm run dev
```

App URL: `http://localhost:3000`

## Design Tokens (Phase 1)

- Global token file: `app/tokens.css`
- Root load point: `app/layout.tsx`
- Tailwind token bridge + global utility styles: `app/globals.css`
- Presentational wrappers: `src/components/presentation/ui-wrappers.tsx`
- Rollout + CI guidance: `docs/design-system-phase1.md`

## Visual Tests

Run visual regression tests:

```bash
npm run test:visual
```

Update screenshot baselines intentionally:

```bash
npm run test:visual:update
```

## Storybook + Chromatic (Recommended)

Setup instructions and CI workflow template are documented in:

`docs/design-system-phase1.md`
