# UI Standards

## Foundation
- Use an 8px spacing system for layout and component rhythm.
- Keep page content in consistent max-width containers with clear section spacing.
- Prefer predictable, reusable primitives over one-off styles.

## Typography
- One page title (`h1`) per screen.
- Section titles (`h2`) and card headers (`h3`) should follow a consistent size scale.
- Body text should prioritize readability over density.

## Component Patterns
- Buttons: `primary`, `secondary`, `ghost`, `danger` variants with consistent disabled/loading states.
- Cards: title, optional subtitle, content area, optional actions row.
- Tabs: persistent placement and consistent active/inactive treatment.
- Badges/chips: used for status, roles, service labels, and alerts.

## States
- Every data panel should implement:
  - loading (skeleton or spinner)
  - empty state with next action guidance
  - error state with actionable recovery text
- Forms should have inline validation and clear submit feedback (toast or inline banner).

## Navigation
- Patient chart uses breadcrumbs + sticky patient header.
- Quick actions remain visible and context-aware.
- Avoid hidden critical actions in overflow menus when screen width allows direct access.

## Accessibility
- Maintain keyboard navigation across tabs, forms, and modals.
- Ensure visible focus states and semantic labels.
- Keep color contrast at accessible levels for text and status indicators.

## EHR-Specific Behavior
- Never block core chart navigation behind non-critical modals.
- Display chart-critical warnings (missing requirements, unsigned notes) near top-level chart context.
- Preserve user-entered draft data where safe during tab switches.
