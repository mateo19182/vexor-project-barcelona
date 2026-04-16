# UI-SPEC: Phase 1 — Foundation & Design System

**Phase:** 1 — Foundation & Design System
**Requirement:** UIX-01
**Date:** 2026-04-16
**Status:** Draft

---

## Design Tokens

### Colors

All colors are defined as CSS custom properties on `:root` and surfaced as Tailwind config extensions. shadcn/ui semantic tokens map to these primitives.

#### Backgrounds


| Token                 | Hex       | Usage                                                 |
| --------------------- | --------- | ----------------------------------------------------- |
| `--color-bg-base`     | `#080B12` | Page root background — near-black with blue undertone |
| `--color-bg-surface`  | `#0E1320` | Card / panel surfaces — one step up from base         |
| `--color-bg-elevated` | `#141925` | Modals, popovers, tooltips — slightly lighter         |
| `--color-bg-overlay`  | `#1A2133` | Hover state backgrounds, selected rows                |


#### Borders


| Token                    | Hex       | Usage                                          |
| ------------------------ | --------- | ---------------------------------------------- |
| `--color-border-subtle`  | `#1E2A3A` | Default card borders, dividers                 |
| `--color-border-default` | `#263345` | Input borders, panel separators                |
| `--color-border-strong`  | `#344560` | Focus rings before neon kick-in, active states |


#### Text


| Token                    | Hex       | Usage                            |
| ------------------------ | --------- | -------------------------------- |
| `--color-text-primary`   | `#E8EDF5` | Main body text, labels           |
| `--color-text-secondary` | `#8A9BB8` | Muted labels, meta, placeholders |
| `--color-text-tertiary`  | `#4A5A72` | Disabled text, timestamps        |
| `--color-text-inverse`   | `#080B12` | Text on neon/bright surfaces     |


#### Accent / Neon


| Token                      | Hex       | Tailwind class   | Usage                                                  |
| -------------------------- | --------- | ---------------- | ------------------------------------------------------ |
| `--color-accent-primary`   | `#00E5FF` | `accent-cyan`    | Primary neon — borders, focus rings, active indicators |
| `--color-accent-secondary` | `#7C3AED` | `accent-violet`  | Secondary accent — module type badges, graph edges     |
| `--color-accent-tertiary`  | `#10B981` | `accent-emerald` | Success / ok states                                    |
| `--color-accent-warm`      | `#F59E0B` | `accent-amber`   | Warning states                                         |


#### Status Colors


| Status    | Hex       | Background (10% opacity) | Usage                          |
| --------- | --------- | ------------------------ | ------------------------------ |
| `ok`      | `#10B981` | `#10B98119`              | Module completed with findings |
| `no_data` | `#8A9BB8` | `#8A9BB819`              | Module returned nothing        |
| `skipped` | `#4A5A72` | `#4A5A7219`              | Module was disabled or skipped |
| `error`   | `#EF4444` | `#EF444419`              | Module threw an error          |
| `running` | `#00E5FF` | `#00E5FF19`              | Module currently executing     |


### Typography

**Font family:** `Inter` (primary) + `JetBrains Mono` (code/signal values)

Load via Google Fonts:

```
Inter: 400, 500, 600
JetBrains Mono: 400, 500
```

Tailwind config:

```js
fontFamily: {
  sans: ['Inter', 'system-ui', 'sans-serif'],
  mono: ['JetBrains Mono', 'Menlo', 'monospace'],
}
```

#### Type Scale


| Token       | Size               | Weight | Line Height | Usage                        |
| ----------- | ------------------ | ------ | ----------- | ---------------------------- |
| `text-xs`   | `11px / 0.6875rem` | 400    | `1.5`       | Timestamps, tertiary labels  |
| `text-sm`   | `13px / 0.8125rem` | 400    | `1.5`       | Secondary body, badges       |
| `text-base` | `15px / 0.9375rem` | 400    | `1.6`       | Primary body, input text     |
| `text-lg`   | `17px / 1.0625rem` | 500    | `1.5`       | Card titles, section headers |
| `text-xl`   | `20px / 1.25rem`   | 600    | `1.4`       | Page sub-headers             |
| `text-2xl`  | `24px / 1.5rem`    | 600    | `1.3`       | Page titles                  |
| `text-3xl`  | `30px / 1.875rem`  | 600    | `1.2`       | Hero headings                |


Letter spacing: `-0.01em` on `text-xl` and above for a tight, technical feel.

### Spacing

Base unit: `4px`. All spacing is multiples of `4`.


| Scale | Value  | Tailwind |
| ----- | ------ | -------- |
| `1`   | `4px`  | `p-1`    |
| `2`   | `8px`  | `p-2`    |
| `3`   | `12px` | `p-3`    |
| `4`   | `16px` | `p-4`    |
| `5`   | `20px` | `p-5`    |
| `6`   | `24px` | `p-6`    |
| `8`   | `32px` | `p-8`    |
| `10`  | `40px` | `p-10`   |
| `12`  | `48px` | `p-12`   |
| `16`  | `64px` | `p-16`   |


Standard gaps:

- Between form fields: `gap-4` (16px)
- Between cards in a grid: `gap-4` (16px)
- Between section blocks: `gap-8` (32px)
- Sidebar width: `240px`
- Panel inner padding: `p-6` (24px)

### Borders & Radius

#### Border Widths


| Use                      | Width | Class                 |
| ------------------------ | ----- | --------------------- |
| Default card / panel     | `1px` | `border`              |
| Active / focused element | `1px` | `border` + neon color |
| Accent highlight bar     | `2px` | `border-2`            |
| Graph node border        | `1px` | `border`              |


#### Radius Scale


| Token          | Value    | Usage                           |
| -------------- | -------- | ------------------------------- |
| `rounded-sm`   | `4px`    | Badges, small chips             |
| `rounded`      | `6px`    | Inputs, buttons                 |
| `rounded-md`   | `8px`    | Cards, panels                   |
| `rounded-lg`   | `12px`   | Modals, drawers                 |
| `rounded-full` | `9999px` | Toggle switches, avatar circles |


#### Dividers

- Standard divider: `1px solid #1E2A3A` — `border-b border-border-subtle`
- Section separator inside panels: `border-t border-[#1E2A3A] my-6`

### Shadows & Effects

#### Shadow Scale


| Token       | Value                        | Usage                        |
| ----------- | ---------------------------- | ---------------------------- |
| `shadow-sm` | `0 1px 3px rgba(0,0,0,0.4)`  | Subtle depth on cards        |
| `shadow-md` | `0 4px 16px rgba(0,0,0,0.5)` | Elevated surfaces, dropdowns |
| `shadow-lg` | `0 8px 32px rgba(0,0,0,0.6)` | Modals, side drawers         |


#### Glow Effects (neon accents)

Defined as Tailwind utilities via `@layer utilities`:

```css
.glow-cyan {
  box-shadow: 0 0 0 1px #00E5FF, 0 0 12px rgba(0, 229, 255, 0.25);
}
.glow-cyan-sm {
  box-shadow: 0 0 8px rgba(0, 229, 255, 0.2);
}
.glow-violet {
  box-shadow: 0 0 0 1px #7C3AED, 0 0 12px rgba(124, 58, 237, 0.25);
}
.glow-ok {
  box-shadow: 0 0 8px rgba(16, 185, 129, 0.3);
}
.glow-error {
  box-shadow: 0 0 8px rgba(239, 68, 68, 0.3);
}
```

Apply `.glow-cyan` on focused inputs and active nav items. Apply `.glow-cyan-sm` on card hover.

#### Backdrop Blur

- Modals / popovers backdrop: `backdrop-blur-sm` (`blur(4px)`) over a `bg-black/50` overlay
- Floating nav or tooltip: `backdrop-blur-md` (`blur(12px)`) + `bg-bg-surface/80`

---

## Component Contracts

### App Shell

**Structure:** Top navigation bar + full-height content area. No persistent sidebar in v1 (sidebar added in later phases if needed).

```
┌─────────────────────────────────────────────────────┐
│ TopNav (h-14, bg-bg-surface, border-b border-subtle) │
├─────────────────────────────────────────────────────┤
│                                                      │
│  <main> — flex-1, overflow-y-auto                   │
│  Routes render here                                  │
│                                                      │
└─────────────────────────────────────────────────────┘
```

**TopNav contents:**

- Left: Logotype — `NORDÉS` in `text-lg font-semibold text-text-primary` + a `2px` left border in `--color-accent-primary` (`border-l-2 border-accent-cyan pl-3`)
- Right: nav links — `text-sm text-text-secondary hover:text-text-primary transition-colors`
- Background: `bg-bg-surface border-b border-border-subtle`
- Height: `h-14` (56px), `sticky top-0 z-50`

**Root layout:** `min-h-screen bg-bg-base text-text-primary flex flex-col`

### Button Variants

All buttons: `inline-flex items-center justify-center gap-2 font-medium rounded transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-cyan focus-visible:ring-offset-2 focus-visible:ring-offset-bg-base`

#### Primary

```
bg-accent-cyan text-text-inverse hover:bg-cyan-300 active:bg-cyan-400
px-4 py-2 text-sm font-semibold
```

Glow on hover: `hover:shadow-[0_0_16px_rgba(0,229,255,0.4)]`

#### Secondary

```
bg-transparent border border-border-default text-text-primary
hover:border-accent-cyan hover:text-accent-cyan
px-4 py-2 text-sm
```

#### Ghost

```
bg-transparent text-text-secondary hover:text-text-primary hover:bg-bg-overlay
px-4 py-2 text-sm
```

#### Destructive

```
bg-transparent border border-red-500/40 text-red-400
hover:border-red-500 hover:bg-red-500/10
px-4 py-2 text-sm
```

#### Disabled state (all variants)

```
opacity-40 cursor-not-allowed pointer-events-none
```

#### Size variants


| Size           | Classes                 |
| -------------- | ----------------------- |
| `sm`           | `px-3 py-1.5 text-xs`   |
| `md` (default) | `px-4 py-2 text-sm`     |
| `lg`           | `px-6 py-2.5 text-base` |


### Card

```css
.card {
  @apply bg-bg-surface border border-border-subtle rounded-md p-6;
  @apply transition-all duration-200;
}
.card:hover {
  @apply border-border-default shadow-[0_0_8px_rgba(0,229,255,0.08)];
}
```

- Background: `bg-bg-surface` (`#0E1320`)
- Border: `border border-border-subtle` → `border-[#1E2A3A]`
- Radius: `rounded-md` (8px)
- Padding: `p-6` (24px)
- Hover: border steps up to `border-border-default`, subtle cyan ambient glow

**Card header pattern:**

```
<div class="flex items-center gap-3 mb-4">
  <span class="text-lg font-semibold text-text-primary">Title</span>
  <Badge />
</div>
```

### Badge / Status Indicator

Used for module statuses: `ok`, `no_data`, `skipped`, `error`, `running`.

Base: `inline-flex items-center gap-1.5 px-2 py-0.5 rounded-sm text-xs font-medium`


| Status    | Text color | Background          | Border                         | Dot                          |
| --------- | ---------- | ------------------- | ------------------------------ | ---------------------------- |
| `ok`      | `#10B981`  | `bg-emerald-500/10` | `border border-emerald-500/20` | `bg-emerald-500`             |
| `no_data` | `#8A9BB8`  | `bg-slate-500/10`   | `border border-slate-500/20`   | `bg-slate-500`               |
| `skipped` | `#4A5A72`  | `bg-slate-700/20`   | `border border-slate-700/30`   | `bg-slate-600`               |
| `error`   | `#EF4444`  | `bg-red-500/10`     | `border border-red-500/20`     | `bg-red-500`                 |
| `running` | `#00E5FF`  | `bg-cyan-500/10`    | `border border-cyan-500/20`    | animated pulse `bg-cyan-400` |


Dot size: `w-1.5 h-1.5 rounded-full`
Running dot: add `animate-pulse`

Example Tailwind for `ok`:

```
inline-flex items-center gap-1.5 px-2 py-0.5 rounded-sm text-xs font-medium
text-emerald-400 bg-emerald-500/10 border border-emerald-500/20
```

### Input Fields

Base input: `w-full bg-bg-elevated border border-border-default rounded text-text-primary text-base placeholder:text-text-tertiary`

```
px-4 py-2.5
transition-colors duration-150
focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan/30
```

- Default border: `#263345`
- Focus border: `#00E5FF` with subtle ring `rgba(0,229,255,0.2)`
- Error state: `border-red-500 focus:border-red-500 focus:ring-red-500/20`
- Disabled: `opacity-40 cursor-not-allowed bg-bg-surface`

**Label:** `block text-sm font-medium text-text-secondary mb-1.5`

**Error message:** `mt-1.5 text-xs text-red-400`

**Field wrapper:** `flex flex-col gap-0` (label + input + error stacked)

### Toggle Switch

Used in Phase 3 module selection. Define now for consistency.

```
relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2
transition-colors duration-200 ease-in-out
focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-cyan focus-visible:ring-offset-2 focus-visible:ring-offset-bg-base
```

States:

- **ON:** `bg-accent-cyan border-transparent` — thumb slides right
- **OFF:** `bg-bg-overlay border-border-default` — thumb at left

Thumb: `pointer-events-none h-4 w-4 rounded-full bg-white shadow-md transition-transform duration-200`

- ON: `translate-x-4`
- OFF: `translate-x-0`

---

## Layout Contracts

### Page Structure

```
max-w: none (full bleed background)
content max-w: 1440px, auto margins (mx-auto)
page padding: px-8 (32px left/right)
```

Standard page wrapper: `mx-auto max-w-[1440px] px-8 py-8`

**Input screen:** centered column, `max-w-2xl mx-auto`
**Run screen (Phase 4+):** full-width two-panel split — no max-width restriction

### Responsive Breakpoints

Desktop-focused. Define breakpoints but don't build mobile layouts in Phase 1.


| Breakpoint | Min-width | Notes                                                |
| ---------- | --------- | ---------------------------------------------------- |
| `sm`       | `640px`   | Minimum supported viewport                           |
| `md`       | `768px`   | Tablet (not optimized)                               |
| `lg`       | `1024px`  | Entry desktop                                        |
| `xl`       | `1280px`  | **Primary target** — 1280×800 collector workstations |
| `2xl`      | `1536px`  | Secondary — 1920×1080 widescreen                     |


At `xl` and below: two-panel run screen maintains 50/50 split.
At `2xl`: log panel `40%`, graph panel `60%`.

---

## Animation Contracts

### Transitions

Default transition: `transition-all duration-150 ease-in-out`


| Use case                      | Duration | Easing                           | Tailwind                            |
| ----------------------------- | -------- | -------------------------------- | ----------------------------------- |
| Color / border changes        | `150ms`  | `ease-in-out`                    | `transition-colors duration-150`    |
| Opacity fades                 | `200ms`  | `ease-in-out`                    | `transition-opacity duration-200`   |
| Transform (hover lift, scale) | `200ms`  | `ease-out`                       | `transition-transform duration-200` |
| Panel/drawer slide            | `300ms`  | `cubic-bezier(0.16,1,0.3,1)`     | custom via `style` prop             |
| Node graph entrance (Phase 6) | `400ms`  | `cubic-bezier(0.34,1.56,0.64,1)` | spring-ish, defined in framer/CSS   |


Global CSS var for reuse:

```css
--transition-base: 150ms ease-in-out;
--transition-smooth: 300ms cubic-bezier(0.16, 1, 0.3, 1);
--transition-spring: 400ms cubic-bezier(0.34, 1.56, 0.64, 1);
```

### Micro-interactions

**Hover effects:**

- Buttons: color shift + subtle brightness — no transform needed (keeps professional feel)
- Cards: border lightens + `shadow-[0_0_8px_rgba(0,229,255,0.08)]` ambient glow
- Nav links: `text-text-secondary → text-text-primary` color slide

**Focus rings:**

- All interactive elements: `focus-visible:ring-2 focus-visible:ring-accent-cyan focus-visible:ring-offset-2 focus-visible:ring-offset-bg-base`
- Ring color: `#00E5FF` at 100% opacity — crisp, neon
- Offset background: `#080B12` so the ring floats cleanly

**Loading states:**

- Spinner: `animate-spin` on a `border-2 border-border-default border-t-accent-cyan rounded-full w-4 h-4`
- Skeleton: `animate-pulse bg-bg-overlay rounded` blocks at expected content dimensions
- Button loading: replace label with spinner, disable pointer events

---

## Background Pattern

### Polkadot Grid

The signature background texture. Applied on `<body>` or the root `#root` div, behind all content.

**CSS approach — radial gradient dot grid:**

```css
.bg-polkadot {
  background-color: #080B12;
  background-image: radial-gradient(
    circle,
    rgba(0, 229, 255, 0.08) 1px,
    transparent 1px
  );
  background-size: 24px 24px;
}
```

- Dot color: `rgba(0, 229, 255, 0.08)` — cyan at 8% opacity, barely visible
- Dot size: `1px` radius (2px diameter)
- Grid spacing: `24px × 24px`
- Background color beneath: `#080B12`

**Tailwind utility (defined in `@layer utilities`):**

```css
@layer utilities {
  .bg-polkadot {
    background-color: #080B12;
    background-image: radial-gradient(circle, rgba(0, 229, 255, 0.08) 1px, transparent 1px);
    background-size: 24px 24px;
  }
}
```

Apply as: `className="bg-polkadot"` on the root `<div id="root">` wrapper.

**Panels and cards** sit on top with `bg-bg-surface` (`#0E1320`) which is opaque — the dot grid only shows through the base page background, not inside panels. This creates a layered depth effect.

**Variant — denser grid** (for use in hero sections if needed):

```css
background-size: 16px 16px; /* tighter dots */
background-image: radial-gradient(circle, rgba(0, 229, 255, 0.06) 1px, transparent 1px);
```

---

## Routing Structure

### Routes

Using React Router v6 (`BrowserRouter` + `Routes`).


| Path          | Component     | Description                                                      |
| ------------- | ------------- | ---------------------------------------------------------------- |
| `/`           | `<HomePage>`  | Redirect to `/new` or landing — in Phase 1 renders a placeholder |
| `/new`        | `<InputPage>` | Case input form — Phase 2 target                                 |
| `/run/:runId` | `<RunPage>`   | Live run view — Phase 4 target                                   |


**Phase 1 implementation:** all routes render placeholder `<div>` with the app shell, a heading, and a `<Badge>` component — enough to validate the theme is applied correctly and routing works.

**Router setup in `main.tsx`:**

```tsx
<BrowserRouter>
  <Routes>
    <Route path="/" element={<Navigate to="/new" replace />} />
    <Route path="/new" element={<InputPage />} />
    <Route path="/run/:runId" element={<RunPage />} />
  </Routes>
</BrowserRouter>
```

**AppShell wrapper:** Routes render inside `<AppShell>` which provides the `TopNav` and `<main>` content area.

---

## Implementation Notes

### Tailwind Configuration (`tailwind.config.ts`)

```ts
import type { Config } from 'tailwindcss'

export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Backgrounds
        'bg-base':     '#080B12',
        'bg-surface':  '#0E1320',
        'bg-elevated': '#141925',
        'bg-overlay':  '#1A2133',
        // Borders
        'border-subtle':  '#1E2A3A',
        'border-default': '#263345',
        'border-strong':  '#344560',
        // Text
        'text-primary':   '#E8EDF5',
        'text-secondary': '#8A9BB8',
        'text-tertiary':  '#4A5A72',
        'text-inverse':   '#080B12',
        // Accents
        'accent-cyan':    '#00E5FF',
        'accent-violet':  '#7C3AED',
        'accent-emerald': '#10B981',
        'accent-amber':   '#F59E0B',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Menlo', 'monospace'],
      },
      ringColor: {
        DEFAULT: '#00E5FF',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
} satisfies Config
```

### CSS Variables (`src/index.css`)

Map design tokens to CSS custom properties for shadcn/ui compatibility:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 220 50% 4%;        /* #080B12 */
    --foreground: 214 40% 93%;       /* #E8EDF5 */
    --card: 220 45% 8%;              /* #0E1320 */
    --card-foreground: 214 40% 93%;
    --border: 218 38% 17%;           /* #1E2A3A */
    --input: 218 35% 21%;            /* #263345 */
    --ring: 187 100% 50%;            /* #00E5FF */
    --primary: 187 100% 50%;         /* #00E5FF — cyan */
    --primary-foreground: 220 50% 4%;
    --secondary: 218 38% 17%;
    --secondary-foreground: 214 40% 93%;
    --muted: 218 35% 21%;
    --muted-foreground: 213 22% 56%; /* #8A9BB8 */
    --accent: 260 70% 56%;           /* #7C3AED — violet */
    --accent-foreground: 214 40% 93%;
    --destructive: 0 72% 59%;        /* #EF4444 */
    --destructive-foreground: 0 0% 100%;
    --radius: 0.5rem;                /* 8px base */
  }
}
```

### shadcn/ui Setup

Init with: `npx shadcn-ui@latest init`

- Style: `New York` (sharper, less rounded — fits the technical aesthetic)
- Base color: `Neutral` (we override everything via CSS vars)
- CSS variables: `Yes`

Components to install in Phase 1:

```bash
npx shadcn-ui@latest add button card badge input
```

Toggle added in Phase 3:

```bash
npx shadcn-ui@latest add switch
```

### Dark Mode Strategy

Force dark mode via `class` strategy. Add `dark` class to `<html>` element unconditionally (no light mode in v1):

```tsx
// main.tsx
document.documentElement.classList.add('dark')
```

### File Structure for Tokens

```
src/
  styles/
    index.css        ← @tailwind directives + CSS vars + @layer utilities (polkadot, glows)
  lib/
    tokens.ts        ← Re-export design token constants for use in JS (e.g. React Flow node colors)
```

`tokens.ts` exports:

```ts
export const colors = {
  bgBase: '#080B12',
  bgSurface: '#0E1320',
  accentCyan: '#00E5FF',
  accentViolet: '#7C3AED',
  borderSubtle: '#1E2A3A',
  // ... status colors for React Flow nodes
  statusOk: '#10B981',
  statusError: '#EF4444',
  statusSkipped: '#4A5A72',
  statusNoData: '#8A9BB8',
  statusRunning: '#00E5FF',
} as const
```

This ensures React Flow node styling (Phase 4+) uses the same palette as Tailwind/CSS.

---

*UI-SPEC authored: 2026-04-16 | Phase 1 — Foundation & Design System*