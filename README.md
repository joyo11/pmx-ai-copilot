# PMX AI — Project Risk Copilot

**ChatGPT for construction project management.** Continuously monitors your projects and surfaces risk, budget variance, and delays before a manager has to go looking.

Built as a portfolio project targeted at [Group PMX](https://www.grouppmx.com/) and firms like it.

## Structure

```
pmx-ai-copilot/
├── DESIGN.md              # Full product + architecture design doc (read this first)
├── apps/
│   ├── web/               # Next.js 16 frontend (Vercel)
│   └── api/               # FastAPI backend (Render)
├── packages/
│   └── shared/            # Shared TS types
└── docs/                  # Additional design + runbooks
```

## Scope (locked 2026-07-09)

- **Demo project:** one deep hospital-expansion project with full document set, RFIs, budget, meetings, change orders, 15+ risks.
- **Compliance:** portfolio-only, synthetic data.
- **UI:** Claude Design handles polished screens after M1 backend + data model is stable.

## Milestones

| # | Phase | Duration | Ship checkpoint |
|---|---|---|---|
| M0 | Foundation | 2 days | Empty stack deployed, auth green |
| M1 | MVP loop (upload → risk → chat) | 5 days | **Demo-able end-to-end with a real construction PDF** |
| M2 | Depth (P6/MPP, health history, notifications, reports) | 7 days | Full data model + report generator |
| M3 | Polish (meeting AI, Gantt, budget viz, cross-project chat) | 7 days | Feels enterprise |
| M4 | Demo (seed hospital project, landing page, video) | 4 days | Portfolio-ready |

## Getting started

```bash
# after M0 scaffold is committed:
cd apps/web && pnpm install && pnpm dev      # http://localhost:3000
cd apps/api && uv sync && uv run fastapi dev # http://localhost:8000
```
