# UI Rules for Clinician-First Design

This project prioritizes speed of scanning and low cognitive load over visual flair.

## 1) Navigation Is Predictable
- Use a single sidebar background color.
- Inactive nav items stay flat: no glow, no gradients, no shadows, no borders.
- Active nav item must be obvious:
  - full-width highlight
  - 4-6px left accent bar
  - high-contrast text/icon
- Keep nav labels quieter than page content headings.

## 2) Color Hierarchy Is Strict
- Navigation color is reserved for navigation only.
- Status colors are reserved for status only:
  - green = success/compliant/active
  - yellow = pending/review
  - red = error/overdue/alert
  - blue = informational
- Use grayscale for backgrounds, dividers, and inactive UI.

## 3) Typography Drives Priority
- Page titles are the strongest text on screen.
- Section headers are consistent and clearly separated.
- Navigation text is smaller and less prominent than content headers.

## 4) Icons Support, Not Decorate
- Icon tone follows text tone.
- Inactive icons are muted.
- Active icons can be emphasized, but not louder than label text.
- Do not mix icon styles in the same navigation group.

## 5) Cards Stay Quiet
- Prefer whitespace to heavy borders.
- Avoid excessive shadows.
- Keep corner radius moderate and consistent.
- Use type and layout to create emphasis, not color noise.

## 6) Accessibility and Fatigue
- Maintain readable contrast in all states.
- Never use color as the only signal; pair with text or icon.
- Avoid visual effects that increase fatigue in long sessions.
- Apply the same hierarchy rules in dark mode.

## 7) Do Not Reintroduce
- Sidebar gradients and glow effects.
- Multiple navigation accent colors.
- Status colors inside navigation.
- Decorative shadows as a default surface treatment.
