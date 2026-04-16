# Nordés — OSINT Enrichment Frontend

## What This Is

A web frontend for the Nordés OSINT enrichment pipeline. Debt recovery agents input debtor data (name, email, phone, address) or import a CSV batch, select which enrichment modules to run, and watch the pipeline execute in real-time via a live log stream and an expanding node graph. Each node in the graph represents an enrichment module; hovering shows a quick summary, clicking expands to full detail. Designed for both hackathon demo impact and real-world debt collector use.

## Core Value

A collector can go from "I have a name and email" to "I see every enrichment module discovering data in real-time" in under 30 seconds — with full transparency into what was found and where.

## Requirements

### Validated

- ✓ Backend enrichment pipeline with 19 modules — existing
- ✓ Signal-based data model (Context, Signal, ModuleResult) — existing
- ✓ Wave-based module scheduling with dependency resolution — existing
- ✓ Per-module result caching — existing
- ✓ JSON audit log output per run — existing
- ✓ LLM-generated summary — existing

### Active

- [ ] Input screen with Name, Email, Phone, Address form fields
- [ ] CSV import for batch case queuing (multiple rows, sequential/parallel execution)
- [ ] Module selector with toggles per module, "MAX" mode (all enabled) as default
- [ ] Live run screen with two panels: log stream + node graph
- [ ] WebSocket connection for real-time pipeline updates
- [ ] Expanding node graph (React Flow) — each node = a module, appears/animates as the pipeline progresses
- [ ] Progressive detail on graph nodes: hover = quick summary, click = full module output
- [ ] Polkadot futuristic minimal dark aesthetic (Tailwind + shadcn/ui)
- [ ] Dossier summary view after run completion (deferred — depends on module summary not yet built)

### Out of Scope

- Dossier/results page design — blocked on module summary feature not yet in backend
- User authentication/login — not needed for hackathon, can add later
- Mobile-first responsive design — desktop-focused for collector workstations
- Backend API changes — frontend consumes existing endpoints + new WebSocket

## Context

- This is a 24h hackathon project (Vexor × Project Europe, Barcelona). Demo impact matters.
- Backend is fully functional with 19 enrichment modules, wave-based scheduling, and JSON log output.
- Mock data available at `backend/logs/C004/20260416T030206Z.json` for development.
- Backend needs a new WebSocket endpoint to stream module completions in real-time.
- The expanding node graph should feel like Obsidian's graph view — organic, animated, nodes appearing as modules complete.
- Batch CSV import queues multiple cases for sequential execution.

## Constraints

- **Tech stack**: React + Vite, React Flow, Tailwind CSS + shadcn/ui, TypeScript
- **Real-time**: WebSocket for live module completion streaming
- **Timeline**: Hackathon — must ship fast, polish over perfection
- **Backend dependency**: Frontend must work with mock data while backend WebSocket endpoint is being built

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| React + Vite over Next.js | No SSR needed, faster dev cycle for SPA | — Pending |
| React Flow for node graph | Best React lib for interactive node diagrams, handles Obsidian-style expanding graphs | — Pending |
| WebSocket over SSE/polling | True real-time feel, bidirectional if needed later | — Pending |
| shadcn/ui + Tailwind | Component quality + full styling control, polkadot futuristic aesthetic | — Pending |
| Defer dossier view | Depends on backend module summary not yet built | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-16 after initialization*
