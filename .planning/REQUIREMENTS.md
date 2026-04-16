# Requirements: Nordés Frontend

**Defined:** 2026-04-16
**Core Value:** A collector can go from "I have a name and email" to "I see every enrichment module discovering data in real-time" in under 30 seconds

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Input

- [ ] **INP-01**: User can enter a case via form with Name, Email, Phone, and Address fields
- [ ] **INP-02**: Form validates required fields before submission

### Module Selection

- [ ] **MOD-01**: User sees all available enrichment modules with toggle switches
- [ ] **MOD-02**: MAX mode is the default — all modules enabled on load
- [ ] **MOD-03**: User can deactivate individual modules before running a case

### Live Run View

- [ ] **RUN-01**: User sees real-time log stream from the backend during pipeline execution
- [ ] **RUN-02**: User sees a React Flow node graph that expands as modules complete
- [ ] **RUN-03**: Hovering a graph node shows a quick summary (module status + signal count)
- [ ] **RUN-04**: Clicking a graph node expands to full module output (signals, facts, gaps)
- [ ] **RUN-05**: WebSocket connection streams module completion events from backend in real-time

### UI/UX

- [ ] **UIX-01**: Polkadot futuristic minimal dark theme built with Tailwind CSS + shadcn/ui
- [ ] **UIX-02**: Smooth animations on node graph expansion — organic Obsidian-style feel
- [ ] **UIX-03**: Two-panel layout on run screen: log stream (left) + node graph (right)

## v2 Requirements

### Input

- **INP-03**: User can import a CSV file to batch-queue multiple cases
- **INP-04**: User can see previously run cases and their results (case history)

### Results

- **RES-01**: Dossier summary view after run completion (depends on backend module summary)

### Module Selection

- **MOD-04**: User can save custom module presets (e.g. "Quick scan", "Deep dive")

### Run View

- **RUN-06**: Overall progress bar/percentage indicator during pipeline execution
- **RUN-07**: Module status badges on each node (ok / no_data / skipped / error)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Backend refactoring or changes | Frontend-only scope — backend consumed as-is |
| User authentication / login | Not needed for hackathon; add later if productized |
| Mobile-responsive design | Desktop-focused for collector workstations |
| Dossier page design | Blocked on backend module summary feature not yet built |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INP-01 | Phase 2 — Case Input | Pending |
| INP-02 | Phase 2 — Case Input | Pending |
| MOD-01 | Phase 3 — Module Selection | Pending |
| MOD-02 | Phase 3 — Module Selection | Pending |
| MOD-03 | Phase 3 — Module Selection | Pending |
| RUN-01 | Phase 4 — Live Run View Layout | Pending |
| RUN-02 | Phase 4 — Live Run View Layout | Pending |
| RUN-03 | Phase 6 — Node Graph Interactivity & Polish | Pending |
| RUN-04 | Phase 6 — Node Graph Interactivity & Polish | Pending |
| RUN-05 | Phase 5 — Real-Time Pipeline Streaming | Pending |
| UIX-01 | Phase 1 — Foundation & Design System | Pending |
| UIX-02 | Phase 6 — Node Graph Interactivity & Polish | Pending |
| UIX-03 | Phase 4 — Live Run View Layout | Pending |

**Coverage:**
- v1 requirements: 13 total
- Mapped to phases: 13
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-16*
*Last updated: 2026-04-16 after initial definition*
