# Phase 1 UI Discipline (No Logic/DOM Changes)

This plan introduces design tokens + presentational wrappers while preserving business logic, routing, state, and DOM hierarchy.

## Deliverables Included

- Global tokens: `frontend/app/tokens.css`
- Global load point: `frontend/app/layout.tsx`
- Theme bridge for existing Tailwind utilities: `frontend/app/globals.css`
- Presentational wrappers: `frontend/src/components/presentation/ui-wrappers.tsx`
- Example tokenized refactor: `frontend/app/(app)/_components/MetricCard.tsx`

## Example Wrapper Usage

```tsx
import { BadgeUI, ButtonUI, PanelUI, TableUI } from "@/components/presentation/ui-wrappers";

export function Example() {
  return (
    <PanelUI>
      <div className="flex items-center justify-between">
        <BadgeUI className="ui-status-info">Informational</BadgeUI>
        <ButtonUI variant="secondary" onClick={() => {}}>
          Save
        </ButtonUI>
      </div>
      <TableUI>{/* existing table rows/cells */}</TableUI>
    </PanelUI>
  );
}
```

## Example Token Refactor (Real Change in Repo)

From:

```tsx
<Card className="bg-white shadow-sm">
  <CardHeader className="pb-1">
    <CardTitle className="text-xs text-slate-500">...</CardTitle>
  </CardHeader>
</Card>
```

To:

```tsx
<Card className="border border-[var(--neutral-border)] bg-[var(--neutral-panel)] shadow-[var(--shadow-1)]">
  <CardHeader className="pb-[var(--space-4)]">
    <CardTitle className="text-[length:var(--font-size-12)] text-[var(--neutral-muted)]">...</CardTitle>
  </CardHeader>
</Card>
```

## Token Categories

`tokens.css` includes:

- Neutrals: `--neutral-background`, `--neutral-panel`, `--neutral-text`, `--neutral-muted`, `--neutral-border`
- Semantic status:
  - `--status-critical`
  - `--status-attention`
  - `--status-stable`
  - `--status-informational`
- Spacing: `--space-4`, `--space-8`, `--space-12`, `--space-16`, `--space-24`, `--space-32`, `--space-48`
- Radius scale, typography scale, shadow scale, z-index layers
- Compatibility aliases for existing `--ui-*` usage to avoid breakage

## Safe Rollout Plan (PR-by-PR)

### PR 1: Token Foundation

- Add `tokens.css`
- Load in root layout
- Add Tailwind token bridge in `globals.css`
- Keep all existing classes and route logic unchanged

Checklist:

- [ ] No page-level JSX structure changed
- [ ] No JS selectors or `data-testid` removed
- [ ] Existing snapshots still render

### PR 2: Shared Presentational Wrappers

- Add `ButtonUI`, `PanelUI`, `BadgeUI`, `TableUI`
- Wrappers only merge classes and forward props/events
- No internal state/effects

Checklist:

- [ ] Wrapper props are pass-through
- [ ] No changes to API calls, reducers, hooks, stores
- [ ] No side effects introduced

### PR 3: Incremental Token Refactors

- Migrate shared components first (`components/ui/*`)
- Migrate low-risk dashboard modules next
- Keep DOM structure stable; only class/token substitutions

Checklist:

- [ ] Replace hard-coded color classes with token-backed classes/vars
- [ ] Replace ad-hoc spacing with token spacing
- [ ] Verify keyboard/focus behavior unchanged

### PR 4: Visual Regression Gates

- Add Storybook stories for wrappers + high-use components
- Add Playwright screenshot tests for key pages
- Enforce CI failures on visual or test drift

Checklist:

- [ ] CI fails on test failure
- [ ] CI fails when Chromatic visual diffs are unreviewed
- [ ] Baseline update process documented

## Visual Regression Setup

## 1) Storybook + Chromatic

Install:

```bash
npm --prefix frontend install -D storybook @storybook/nextjs chromatic
npx storybook@latest init --builder webpack5 --type react --yes --package-manager npm
```

Recommended scripts in `frontend/package.json`:

```json
{
  "scripts": {
    "storybook": "storybook dev -p 6006",
    "build-storybook": "storybook build",
    "chromatic": "chromatic --exit-zero-on-changes=false"
  }
}
```

Chromatic:

- Set secret: `CHROMATIC_PROJECT_TOKEN`
- Use `--exit-zero-on-changes=false` so unreviewed diffs fail PR checks

## 2) Playwright Screenshot Tests

Use existing command:

```bash
npm --prefix frontend run test:visual
```

Update baselines intentionally:

```bash
npm --prefix frontend run test:visual:update
```

Suggested key pages for screenshot tests:

- `/login`
- `/directory`
- `/call-center`
- `/admin-center`

## 3) CI (GitHub Actions + Render Deploy Gate)

Create workflow `.github/workflows/frontend-visual.yml`:

```yaml
name: Frontend Visual Regression

on:
  pull_request:
    paths:
      - "frontend/**"
      - ".github/workflows/frontend-visual.yml"

jobs:
  visual-regression:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npm run lint
      - run: npx playwright install --with-deps chromium
      - run: npm run test:visual
      - run: npm run build-storybook
      - run: npm run chromatic -- --project-token=${{ secrets.CHROMATIC_PROJECT_TOKEN }}
```

Render integration:

- In Render settings, enable deploy gate on required GitHub checks.
- Mark this workflow check as required before deploy.

## Safe Refactor Rules (Every PR)

- Do not change backend routes, auth, or tenant scoping.
- Do not change DOM hierarchy unless explicitly approved in later phases.
- Do not remove legacy classes referenced by JavaScript.
- Do not add behavior/state changes in presentational PRs.
- Always run `lint` + visual tests before merge.
