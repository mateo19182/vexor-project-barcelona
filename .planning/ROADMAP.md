# Roadmap: Nordés Frontend

**Created:** 2026-04-16
**Phases:** 6
**Requirements covered:** 13/13

## Overview

| # | Phase | Goal | Requirements | Success Criteria |
|---|-------|------|--------------|------------------|
| 1 | Foundation & Design System | Scaffold the app with the dark futuristic theme and routing skeleton | UIX-01 | 3 |
| 2 | Case Input | Collector can enter debtor data and submit a case | INP-01, INP-02 | 3 |
| 3 | Module Selection | Collector can choose which enrichment modules to run | MOD-01, MOD-02, MOD-03 | 3 |
| 4 | Live Run View Layout | Two-panel run screen renders with log stream and node graph side by side | UIX-03, RUN-01, RUN-02 | 4 |
| 5 | Real-Time Pipeline Streaming | WebSocket connects and drives live updates to the log and graph | RUN-05 | 3 |
| 6 | Node Graph Interactivity & Polish | Nodes animate in, hover shows summary, click expands full output | RUN-03, RUN-04, UIX-02 | 4 |

---

## Phase 1: Foundation & Design System

**Goal:** Scaffold the React + Vite app, apply the Polkadot futuristic dark theme with Tailwind and shadcn/ui, and establish routing so all future phases have a consistent visual baseline.
**Requirements:** UIX-01
**Depends on:** None
**UI hint:** yes

### Success Criteria

1. `npm run dev` starts with zero errors and renders the app shell in a browser.
2. The dark background, neon accent colour palette, and Polkadot-inspired typography are visible on a placeholder home screen.
3. shadcn/ui components (Button, Card, Badge) render correctly with the custom theme tokens.

---

## Phase 2: Case Input

**Goal:** Collector can enter a debtor's Name, Email, Phone, and Address into a validated form and submit it to trigger enrichment.
**Requirements:** INP-01, INP-02
**Depends on:** Phase 1
**UI hint:** yes

### Success Criteria

1. The input screen renders four fields: Name, Email, Phone, Address.
2. Submitting with Name empty shows an inline validation error and blocks the request.
3. A valid form submission calls `POST /enrich` (or mock) and navigates to the run screen.

---

## Phase 3: Module Selection

**Goal:** Before submitting a case, the collector can see all available enrichment modules, start with all enabled (MAX mode), and selectively disable individual ones.
**Requirements:** MOD-01, MOD-02, MOD-03
**Depends on:** Phase 2
**UI hint:** yes

### Success Criteria

1. All 19 backend modules are listed with toggle switches, fetched from `GET /modules`.
2. On first load, every toggle is ON (MAX mode default).
3. Disabling a module removes it from the `only` param sent to `/enrich`; re-enabling restores it.

---

## Phase 4: Live Run View Layout

**Goal:** Establish the two-panel run screen — scrolling log stream on the left and static React Flow canvas on the right — wired to static/mock data so layout is fully testable before WebSocket lands.
**Requirements:** UIX-03, RUN-01, RUN-02
**Depends on:** Phase 3
**UI hint:** yes

### Success Criteria

1. The run screen renders a persistent two-panel split: log panel left, graph panel right.
2. Log entries appear as a scrolling list; new entries auto-scroll to the bottom.
3. React Flow canvas renders placeholder nodes for each module with correct labels and positions.
4. The layout holds correctly at 1280 × 800 and 1920 × 1080 viewport widths.

---

## Phase 5: Real-Time Pipeline Streaming

**Goal:** Connect to the backend WebSocket (or replay mock events) so that module completion events drive live log lines and node appearances in real time during an active run.
**Requirements:** RUN-05
**Depends on:** Phase 4
**UI hint:** no

### Success Criteria

1. On run submission the client opens a WebSocket connection (or activates mock replay) and begins receiving events.
2. Each `module_completed` event appends a timestamped log line to the left panel within 200 ms.
3. A module node appears on the React Flow graph the moment its completion event arrives — the graph grows progressively, never all-at-once.

---

## Phase 6: Node Graph Interactivity & Polish

**Goal:** Make the expanding node graph feel alive — nodes animate in organically, hovering a node surfaces a quick summary, and clicking it opens full module output — completing the core UX loop.
**Requirements:** RUN-03, RUN-04, UIX-02
**Depends on:** Phase 5
**UI hint:** yes

### Success Criteria

1. Nodes enter the canvas with a smooth fade-and-scale animation (no hard pops).
2. Hovering any node shows a tooltip/popover with module status and signal count.
3. Clicking a node opens a side drawer or modal with full module output: signals, facts, and gaps.
4. The graph self-arranges edges organically as new nodes appear, without layout thrashing.
