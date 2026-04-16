---
status: issues_found
phase: 01-foundation-design-system
depth: standard
files_reviewed: 22
findings:
  critical: 1
  warning: 4
  info: 3
  total: 8
---

# Code Review: Phase 01 — Foundation & Design System

## Summary
The scaffold is solid for a hackathon baseline: routing, layout, and design tokens are coherent and consistent. Eight issues were found — one critical (non-null assertion on a potentially absent DOM element), four warnings around accessibility, type safety, and CSS duplication, and three informational items.

## Findings

### critical-1: Non-null assertion on `getElementById` with no error boundary
- **File:** `frontend/src/main.tsx:9`
- **Severity:** critical
- **Description:** `document.getElementById('root')!` uses a non-null assertion to silence TypeScript. If `index.html` is ever modified to rename or remove the `#root` div, the app silently crashes with an unreadable `TypeError: Cannot read properties of null`. There is no surrounding error boundary or guard.
- **Suggestion:** Add a null check and fail loudly: `const root = document.getElementById('root'); if (!root) throw new Error('Root element #root not found in DOM'); createRoot(root).render(...)`.

### warning-1: `runId` rendered without sanitisation or validation
- **File:** `frontend/src/pages/RunPage.tsx:16`
- **Severity:** warning
- **Description:** `{runId}` from `useParams()` is rendered directly inside a `<Badge>`. While React escapes text by default (no XSS), the value is fully user-controlled via the URL and may be arbitrarily long or contain unexpected characters (e.g. Unicode, emoji, RTL markers). No length limit or format validation is applied before rendering.
- **Suggestion:** Validate that `runId` matches an expected pattern (e.g. `^[a-z0-9_-]{1,64}$`) and render a fallback or redirect to `/` if it does not match.

### warning-2: Missing `aria-current` on active nav link
- **File:** `frontend/src/components/layout/TopNav.tsx:23-35`
- **Severity:** warning
- **Description:** The active navigation link is styled differently but never receives `aria-current="page"`. Screen readers cannot distinguish the active route from inactive ones.
- **Suggestion:** Add `aria-current={location.pathname === link.to ? 'page' : undefined}` to the `<Link>` element.

### warning-3: Input label has no `htmlFor` / `id` association
- **File:** `frontend/src/pages/HomePage.tsx:60-65`
- **Severity:** warning
- **Description:** The `<label>` element renders "Sample input" but is not associated with the `<Input>` component — neither via `htmlFor`+`id` nor by wrapping. This breaks assistive-technology label announcements.
- **Suggestion:** Add `id="sample-input"` to `<Input>` and `htmlFor="sample-input"` to `<label>`, or wrap the input inside the label element.

### warning-4: Design token duplication between CSS variables and Tailwind config
- **File:** `frontend/src/index.css` and `frontend/tailwind.config.ts`
- **Severity:** warning
- **Description:** All design tokens (background colours, border colours, text colours, accents) are defined twice: once as raw CSS custom properties in `index.css` (`--color-bg-base`, etc.) and again as Tailwind colour extensions in `tailwind.config.ts`. Changes to one source must be manually mirrored to the other, creating a maintenance hazard. The same values also appear a third time in `frontend/src/lib/tokens.ts`.
- **Suggestion:** Make Tailwind the single source of truth by using `var(--color-*)` references inside `tailwind.config.ts`, or eliminate the CSS custom property definitions that are not consumed by shadcn/ui variables and drive everything from the Tailwind config (which is already the authoring surface).

### info-1: `dark` class added imperatively instead of declaratively
- **File:** `frontend/src/main.tsx:7`
- **Severity:** info
- **Description:** `document.documentElement.classList.add('dark')` is called at module evaluation time. This works for a forced-dark-only app but will need to be replaced with a proper theme-provider when light mode or system-preference support is added. There is no comment explaining the intent.
- **Suggestion:** Add a brief comment — `// Force dark mode; replace with ThemeProvider when light mode is supported` — so future contributors know this is intentional.

### info-2: `tailwind.config.ts` uses `require()` for a plugin in an ESM context
- **File:** `frontend/tailwind.config.ts:38`
- **Severity:** info
- **Description:** `plugins: [require('tailwindcss-animate')]` mixes CommonJS `require()` into a TypeScript ESM file. Vite and modern tooling handle this fine today, but it is inconsistent with the rest of the project's ESM style and may cause issues if the build pipeline becomes stricter.
- **Suggestion:** Use the ESM import: add `import tailwindAnimate from 'tailwindcss-animate'` at the top and reference `plugins: [tailwindAnimate]`.

### info-3: `tokens.ts` is unreferenced dead code
- **File:** `frontend/src/lib/tokens.ts`
- **Severity:** info
- **Description:** `tokens.ts` exports a `colors` object, but no file in the project imports it. The design tokens it defines are consumed exclusively through Tailwind class names and CSS custom properties. It will accumulate drift from the other two token sources with no tooling to catch it.
- **Suggestion:** Either delete the file (since Tailwind classes and CSS variables cover all use cases) or wire it as the canonical source by generating the Tailwind config from it. If kept, add a comment documenting its intended role.
