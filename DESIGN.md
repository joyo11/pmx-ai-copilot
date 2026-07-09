# PMX AI — Project Risk Copilot

**Tagline:** ChatGPT for construction project management. Continuously monitors your projects and surfaces risk, budget variance, and delays before a manager has to go looking.

**Target buyer:** Group PMX (project management consulting for construction, infrastructure, healthcare, transportation, education, commercial). Internal-tool candidate they could buy or build.

**Primary user:** Project Manager / Senior PM / Program Manager
**Secondary users:** Construction Manager, Executive, Owner Rep

---

## 1. Product Vision

Managers today spend 30-40% of their week reading spreadsheets, RFI logs, schedules, meeting notes, and email chains just to answer three questions: *Is this project healthy? What's going wrong? What do I need to act on today?*

PMX AI answers those three questions on the landing page, then lets a PM drill into the reasoning through chat or generated reports. Every insight is grounded in the actual project documents (RAG), with citations.

**Wedge:** We don't compete with Procore or Primavera P6. We ingest their exports (and everything else — Excel, PDFs, DOCX, transcripts) and turn them into a risk-first executive layer above them.

---

## 2. Product Architecture (Systems View)

```
┌─────────────────────────────────────────────────────────────┐
│                    Next.js Frontend (Vercel)                │
│  Dashboard · Chat · Uploads · Reports · Risk · Schedule     │
└────────────────────┬────────────────────────────────────────┘
                     │ REST + SSE (streaming)
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                FastAPI Backend (Render/Fly.io)              │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐    │
│  │ API layer    │ │ Auth (Clerk) │ │ Background jobs  │    │
│  │ (routers)    │ │  middleware  │ │ (RQ or Celery)   │    │
│  └──────┬───────┘ └──────────────┘ └────────┬─────────┘    │
│         │                                    │              │
│  ┌──────▼──────────────────────────────────▼─────────┐     │
│  │              Domain services                      │     │
│  │  • Ingestion    • Risk engine   • Report gen      │     │
│  │  • Chat/RAG     • Health score  • Notifications   │     │
│  │  • Meeting AI   • RFI classifier                  │     │
│  └──────┬──────────────────────────┬────────────────┘     │
│         │                          │                        │
└─────────┼──────────────────────────┼────────────────────────┘
          │                          │
          ▼                          ▼
┌──────────────────────┐  ┌──────────────────────────────────┐
│  Postgres (Neon)     │  │  LLM + Embeddings                │
│  • projects          │  │  • Claude Sonnet 4.6 (chat, risk)│
│  • documents         │  │  • OpenAI text-embedding-3-large │
│  • chunks + pgvector │  │  • Structured output via tools   │
│  • risks, rfis, etc. │  │                                  │
│  • events (audit)    │  │  Object storage: S3-compatible   │
└──────────────────────┘  └──────────────────────────────────┘
```

**Why this shape:**
- **Postgres + pgvector** instead of a separate vector DB. Simpler ops, one database, transactional guarantees on chunk↔risk↔citation joins. Proven at 10M+ vector scale.
- **FastAPI**, not Next.js API routes for the backend. Doc-heavy AI workloads (PDF parsing, batch embedding, long-running risk scans) belong in Python next to PyMuPDF/pandas. Frontend stays Next.js for the UX polish.
- **Streaming everywhere possible** — chat responses stream via SSE, long uploads stream progress via SSE, so the UI never blocks on a "processing…" spinner.
- **Background jobs** (RQ on Redis, or Celery) for ingestion + nightly risk-recompute. API stays fast; heavy work is async.

---

## 3. Information Architecture

**Nav structure (left rail):**

```
┌─ Dashboard          ← landing after login
├─ Projects           ← list view, filter by health/status
│    └─ {project}
│        ├─ Overview     (health score, quick stats)
│        ├─ Risks        (risk engine output)
│        ├─ Documents    (uploaded files)
│        ├─ Chat         (RAG chat scoped to project)
│        ├─ Schedule     (Gantt + AI slip analysis)
│        ├─ Budget       (spend, forecast, burn)
│        ├─ RFIs         (Smart RFI Assistant)
│        ├─ Meetings     (meeting intelligence)
│        ├─ Reports      (executive report generator)
│        └─ Settings
├─ Chat (global)      ← ask across all projects
├─ Reports            ← library of generated reports
├─ Notifications      ← alert center
└─ Settings           ← org, team, API keys, integrations
```

**Key IA decisions:**
- **Dashboard is portfolio-level, not project-level.** Executives land here. PMs pin projects they own to the top.
- **Two chats:** global chat (cross-project) and per-project chat (scoped RAG). The scope indicator is always visible.
- **Documents are project-scoped by default.** Cross-project search is opt-in (query composer toggle).

---

## 4. Database Schema

Postgres 15+ with pgvector 0.7+. Multi-tenant from day one (row-level tenant_id on every table).

```sql
-- =========================================================
-- Tenancy + Users (Clerk owns identity; we mirror what we need)
-- =========================================================
CREATE TABLE organizations (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clerk_org_id  TEXT UNIQUE NOT NULL,
  name          TEXT NOT NULL,
  created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE users (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clerk_user_id TEXT UNIQUE NOT NULL,
  org_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  email         TEXT NOT NULL,
  name          TEXT,
  role          TEXT NOT NULL CHECK (role IN
                  ('project_manager','senior_pm','program_manager',
                   'construction_manager','executive','owner_rep')),
  created_at    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON users (org_id);

-- =========================================================
-- Projects (the core aggregate)
-- =========================================================
CREATE TABLE projects (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id            UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  name              TEXT NOT NULL,
  client            TEXT,                          -- owner org name
  sector            TEXT,                          -- healthcare, infra, edu, ...
  location          TEXT,
  start_date        DATE,
  planned_end_date  DATE,
  forecast_end_date DATE,                          -- AI-updated
  budget_total_cents BIGINT,
  budget_spent_cents BIGINT DEFAULT 0,
  status            TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active','on_hold','closed','archived')),
  health_score      SMALLINT,                      -- 0-100, nullable until first calc
  health_computed_at TIMESTAMPTZ,
  metadata          JSONB DEFAULT '{}',            -- ad-hoc fields per project
  created_at        TIMESTAMPTZ DEFAULT now(),
  updated_at        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON projects (org_id, status);
CREATE INDEX ON projects (org_id, health_score);

CREATE TABLE project_members (
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role       TEXT NOT NULL,                        -- pm, owner_rep, viewer
  PRIMARY KEY (project_id, user_id)
);

-- =========================================================
-- Documents + chunks (RAG substrate)
-- =========================================================
CREATE TABLE documents (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id   UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  uploaded_by  UUID NOT NULL REFERENCES users(id),
  kind         TEXT NOT NULL CHECK (kind IN
                 ('schedule_p6','schedule_mpp','budget_xlsx','rfi_log',
                  'meeting_notes','daily_report','change_order',
                  'pdf_generic','docx_generic','transcript')),
  filename     TEXT NOT NULL,
  storage_uri  TEXT NOT NULL,                     -- s3://... or file://
  bytes        BIGINT,
  status       TEXT NOT NULL DEFAULT 'uploaded'
               CHECK (status IN ('uploaded','extracting','embedding','ready','failed')),
  extracted_text_uri TEXT,                        -- raw extracted text blob
  metadata     JSONB DEFAULT '{}',                -- page count, sheet names, etc.
  uploaded_at  TIMESTAMPTZ DEFAULT now(),
  processed_at TIMESTAMPTZ,
  error        TEXT
);
CREATE INDEX ON documents (project_id, kind);
CREATE INDEX ON documents (status) WHERE status != 'ready';

CREATE TABLE document_chunks (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id  UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  project_id   UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE, -- denormalized for fast filter
  chunk_index  INT NOT NULL,
  text         TEXT NOT NULL,
  page         INT,                               -- pdf page or excel row range
  section      TEXT,                              -- heading / sheet name
  embedding    vector(3072),                      -- text-embedding-3-large
  created_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON document_chunks USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
CREATE INDEX ON document_chunks (project_id);

-- =========================================================
-- Structured extractions (populated by ingestion + LLM)
-- =========================================================
CREATE TABLE schedule_tasks (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id     UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  source_doc_id  UUID REFERENCES documents(id) ON DELETE SET NULL,
  external_id    TEXT,                            -- WBS code from P6/MPP
  name           TEXT NOT NULL,
  planned_start  DATE,
  planned_finish DATE,
  actual_start   DATE,
  actual_finish  DATE,
  percent_done   NUMERIC(5,2),
  predecessors   TEXT[],                          -- external_ids
  is_critical    BOOLEAN DEFAULT false,
  slip_days      INT DEFAULT 0                    -- planned_finish - forecast_finish
);
CREATE INDEX ON schedule_tasks (project_id, is_critical);

CREATE TABLE budget_lines (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id     UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  source_doc_id  UUID REFERENCES documents(id) ON DELETE SET NULL,
  category       TEXT,                            -- concrete, labor, permits, ...
  budgeted_cents BIGINT,
  actual_cents   BIGINT,
  forecast_cents BIGINT,
  period         DATE                             -- month bucket
);
CREATE INDEX ON budget_lines (project_id, period);

CREATE TABLE rfis (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id     UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  source_doc_id  UUID REFERENCES documents(id) ON DELETE SET NULL,
  number         TEXT,
  subject        TEXT,
  discipline     TEXT CHECK (discipline IN
                   ('electrical','mechanical','civil','architectural',
                    'structural','plumbing','other')),
  submitted_date DATE,
  due_date       DATE,
  answered_date  DATE,
  status         TEXT CHECK (status IN ('open','answered','overdue','closed')),
  ai_delay_risk  NUMERIC(3,2),                    -- 0..1, likelihood this delays project
  ai_reasoning   TEXT
);
CREATE INDEX ON rfis (project_id, status);

CREATE TABLE change_orders (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id     UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  source_doc_id  UUID REFERENCES documents(id) ON DELETE SET NULL,
  number         TEXT,
  description    TEXT,
  amount_cents   BIGINT,
  submitted_date DATE,
  status         TEXT CHECK (status IN ('pending','approved','rejected'))
);

CREATE TABLE meetings (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id     UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  source_doc_id  UUID REFERENCES documents(id) ON DELETE SET NULL,
  meeting_date   DATE,
  summary        TEXT,                            -- AI-generated
  decisions      JSONB,                           -- [{text, made_by}]
  action_items   JSONB                            -- [{text, owner, due_date, done}]
);

-- =========================================================
-- Risk engine output
-- =========================================================
CREATE TABLE risks (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id     UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  category       TEXT NOT NULL CHECK (category IN
                   ('schedule','budget','operational','communication','compliance')),
  title          TEXT NOT NULL,
  description    TEXT NOT NULL,
  severity       SMALLINT NOT NULL CHECK (severity BETWEEN 1 AND 5),
  likelihood     NUMERIC(3,2) NOT NULL,           -- 0..1
  business_impact TEXT NOT NULL,
  recommended_action TEXT NOT NULL,
  confidence     NUMERIC(3,2) NOT NULL,
  status         TEXT DEFAULT 'open' CHECK (status IN ('open','acknowledged','mitigated','resolved')),
  detected_at    TIMESTAMPTZ DEFAULT now(),
  resolved_at    TIMESTAMPTZ,
  citations      JSONB                            -- [{document_id, chunk_id, page}]
);
CREATE INDEX ON risks (project_id, status, severity DESC);

-- Health score history (for trending)
CREATE TABLE health_snapshots (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id     UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  score          SMALLINT NOT NULL,
  factors        JSONB NOT NULL,                  -- {budget_variance: -0.08, ...}
  reasoning      TEXT,                            -- human-readable
  computed_at    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON health_snapshots (project_id, computed_at DESC);

-- =========================================================
-- Chat, reports, notifications
-- =========================================================
CREATE TABLE chat_sessions (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  project_id   UUID REFERENCES projects(id) ON DELETE SET NULL,  -- null = global
  title        TEXT,
  created_at   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE chat_messages (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id   UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
  role         TEXT NOT NULL CHECK (role IN ('user','assistant','tool')),
  content      TEXT NOT NULL,
  citations    JSONB,                             -- [{document_id, chunk_id, page}]
  tool_calls   JSONB,
  created_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON chat_messages (session_id, created_at);

CREATE TABLE reports (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id   UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  generated_by UUID NOT NULL REFERENCES users(id),
  kind         TEXT NOT NULL DEFAULT 'executive'
               CHECK (kind IN ('executive','weekly','monthly','risk_only')),
  content_md   TEXT NOT NULL,                     -- source of truth
  pdf_uri      TEXT,
  docx_uri     TEXT,
  generated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE notifications (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  project_id   UUID REFERENCES projects(id) ON DELETE CASCADE,
  kind         TEXT NOT NULL,                     -- risk_new, budget_threshold, rfi_overdue, ...
  title        TEXT NOT NULL,
  body         TEXT,
  severity     TEXT CHECK (severity IN ('info','warning','critical')),
  read_at      TIMESTAMPTZ,
  created_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON notifications (user_id, read_at, created_at DESC);

-- Audit trail (compliance)
CREATE TABLE events (
  id           BIGSERIAL PRIMARY KEY,
  org_id       UUID NOT NULL,
  user_id      UUID,
  project_id   UUID,
  kind         TEXT NOT NULL,                     -- doc.uploaded, risk.detected, ...
  payload      JSONB,
  created_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON events (org_id, created_at DESC);
```

---

## 5. API Design

REST with SSE for streaming. Versioned under `/v1`. Auth via Clerk JWT in `Authorization: Bearer`.

```
Auth (handled by Clerk on frontend, verified server-side)
  Middleware injects: org_id, user_id, role

Organizations
  GET    /v1/me                     → current user + org + role

Projects
  GET    /v1/projects               → list (filters: status, health<, sector)
  POST   /v1/projects               → create
  GET    /v1/projects/{id}          → detail
  PATCH  /v1/projects/{id}          → update
  DELETE /v1/projects/{id}          → archive
  GET    /v1/projects/{id}/health   → current score + factors + reasoning
  GET    /v1/projects/{id}/health/history → snapshots for trend chart
  POST   /v1/projects/{id}/health/recompute → force recompute (returns 202 + job_id)

Documents
  POST   /v1/projects/{id}/documents  → multipart upload
    body: file, kind (optional; auto-detected)
    returns: {document_id, upload_status_stream_url}
  GET    /v1/projects/{id}/documents  → list
  GET    /v1/documents/{id}           → detail (status, extracted preview)
  GET    /v1/documents/{id}/stream    → SSE: extraction + embedding progress
  DELETE /v1/documents/{id}

Risks
  GET    /v1/projects/{id}/risks    → list (filter by category, severity, status)
  GET    /v1/risks/{id}             → detail + citations
  PATCH  /v1/risks/{id}             → change status (acknowledge/mitigate/resolve)
  POST   /v1/projects/{id}/risks/scan → trigger risk scan (async, returns job_id)

Structured data (read-only views for now)
  GET    /v1/projects/{id}/schedule    → tasks + critical path + slip analysis
  GET    /v1/projects/{id}/budget      → lines, burn rate, forecast
  GET    /v1/projects/{id}/rfis        → RFIs with AI delay-risk score
  GET    /v1/projects/{id}/change-orders
  GET    /v1/projects/{id}/meetings

Chat (streaming)
  POST   /v1/chat/sessions          → create session (project_id optional)
  GET    /v1/chat/sessions          → list user's sessions
  GET    /v1/chat/sessions/{id}     → messages history
  POST   /v1/chat/sessions/{id}/messages
    body: {content}
    returns: SSE stream of assistant tokens + citations + tool calls

Reports
  POST   /v1/projects/{id}/reports    → generate report
    body: {kind, template_overrides?}
    returns: {report_id, stream_url}
  GET    /v1/reports/{id}             → metadata + markdown
  GET    /v1/reports/{id}/pdf         → download
  GET    /v1/reports/{id}/docx        → download

Meetings
  POST   /v1/projects/{id}/meetings/analyze  → upload transcript, get summary+actions

RFIs
  POST   /v1/projects/{id}/rfis/classify → batch classify by discipline + delay-risk

Notifications
  GET    /v1/notifications              → unread + recent
  PATCH  /v1/notifications/{id}         → mark read
  POST   /v1/notifications/settings     → thresholds (budget %, RFI age, etc.)

Dashboard aggregate
  GET    /v1/dashboard                  → the landing-page rollup (see §6.1)
```

**Streaming convention:** SSE events `token`, `citation`, `tool_call`, `done`, `error`. Server sends `event: token\ndata: {"text": "..."}\n\n`.

**Idempotency:** POST endpoints that create resources accept `Idempotency-Key` header.

---

## 6. User Flows

### 6.1 First-time PM onboarding
1. SSO via Clerk → org created if new → role set to `project_manager`
2. Empty state on Dashboard: "Create your first project."
3. Create project → land on project Overview with empty state: "Upload your schedule to get started."
4. Upload P6 XER export → SSE shows extraction → embedding → "Ready in 42s"
5. Risk engine auto-runs on first ingest → 3 risks appear → toast "Health score: 82. Click to see why."
6. PM clicks health card → drawer opens with factors + reasoning + top 3 risks.
7. PM clicks "Ask about this project" → project-scoped chat opens.

### 6.2 Daily "what needs my attention" flow
1. Login → Dashboard.
2. Top card: "3 projects need attention" — Project Bravo (critical), Alpha (at-risk), Gamma (budget).
3. Click Bravo → project Overview → red risk badge.
4. Click risk → detail drawer → citations link back to specific PDF page.
5. PM clicks "Ask why" → chat pre-loaded with context question.

### 6.3 Upload → insight loop
1. PM drags Excel budget into Upload Center on project.
2. SSE: extracting → parsing sheets → detected 47 line items → embedding → recomputing risks.
3. On completion, notification: "Budget updated. Forecast now exceeds plan by 6.2%."
4. New risk appears on Risks tab, tied to the specific rows.

### 6.4 Executive report generation
1. PM clicks Reports → New → picks "Weekly executive" template.
2. Modal: which project(s), date range, sections to include.
3. Generate → progress bar → preview markdown side-by-side with sources.
4. Export PDF or DOCX. Reports saved to library.

### 6.5 Cross-project chat
1. Global chat: "Which of my projects has the biggest schedule slip this month?"
2. AI runs tool call → queries `schedule_tasks` → answers with cite-linked list.
3. Follow-up: "Draft an email to the Bravo team about the concrete delay."
4. AI drafts email, cites the source RFI + meeting notes.

---

## 7. UI Wireframe Notes (verbal — Claude Design will render)

Design target: **Linear + Notion + Vercel** feel. Dark mode primary. Grouppmx.com aesthetic — clean, corporate, no clip art. High information density but strong hierarchy.

**Dashboard (portfolio landing)**
- Top: 4 hero stat cards (Active, At Risk, Total Budget, Avg Health).
- Middle: two columns.
  - Left: "Needs your attention" — list of 3-6 projects with health badges + one-line reason.
  - Right: "Recent AI alerts" — timeline of last 24h.
- Bottom: sparkline strip — health-score trend for each project.
- Global "Ask PMX AI" input persistent at bottom (Cmd+K opens).

**Project Overview**
- Top: project name + status pill + health score (large circular gauge).
- Reasoning card next to gauge: 4-5 bulleted factors.
- Second row: 4 mini cards — Budget, Schedule, Open RFIs, Open Risks.
- Third row: tabbed timeline (Documents added / Risks detected / Reports generated).

**Risks tab**
- Filter chips: category, severity, status.
- Table with severity color-coded left border. Row expands into detail drawer showing:
  - Full description, business impact, recommended action, confidence.
  - Citations — each links to source doc page with the highlighted region.
  - Actions: Acknowledge · Mitigate · Resolve.

**Chat**
- Split screen: conversation left, "Sources" panel right (grows as citations arrive).
- Streaming tokens with cursor. Citation footnotes clickable → opens source panel.

**Schedule Intelligence**
- Interactive Gantt (react-gantt or custom D3). Critical path bold red.
- Overlay: AI-predicted slip zones as translucent yellow bars.
- Side panel: "Why is this task slipping?" — LLM reasoning + linked docs.

**Budget Analytics**
- Combined chart: budget vs actual bars, forecast line, threshold band.
- Category breakdown donut.
- Cost overrun prediction card with confidence interval.

**Notifications**
- Inline drawer, grouped by project. Severity-colored dots. Mark-all-read.

Component library: **shadcn/ui** for primitives, **Recharts** for standard charts, **Framer Motion** for transitions (subtle, not showy).

---

## 8. Development Roadmap

**Milestone 0 — Foundation (Days 1-2)**
- Monorepo scaffold: `apps/web` (Next.js 16), `apps/api` (FastAPI), `packages/shared` (types).
- Postgres + pgvector on Neon. Migrations via Alembic.
- Clerk auth working end-to-end.
- CI: GitHub Actions running lint + type check + tests.
- Deploy skeleton: Vercel for web, Render for API. Health check green.

**Milestone 1 — MVP loop: upload → risk → chat (Days 3-7)**
- Project CRUD.
- Document upload (PDF + Excel + DOCX first; P6 + MPP in M2).
- Extraction pipeline: PyMuPDF, python-docx, openpyxl.
- Chunking + embedding (OpenAI text-embedding-3-large).
- Basic risk engine: rules layer + LLM layer (Claude Sonnet 4.6) producing structured `risks` rows with citations.
- Project-scoped chat with RAG + streaming.
- Executive Dashboard + Project Overview UI (with real data).
- **Ship checkpoint:** demo-able end-to-end with a real construction PDF.

**Milestone 2 — Depth (Days 8-14)**
- P6 XER + MPP parsers → `schedule_tasks`.
- Excel budget parser → `budget_lines`.
- RFI log parser + Smart RFI Assistant classification.
- Health score computation + history.
- Notifications engine + thresholds.
- Executive Report Generator (markdown → PDF via WeasyPrint, DOCX via python-docx).

**Milestone 3 — Polish + intelligence (Days 15-21)**
- Meeting Intelligence (transcript → summary + actions).
- Gantt visualization + slip overlay.
- Budget analytics charts.
- Cross-project global chat with tool-calling over structured data.
- Onboarding empty states + tour.
- Perf: hnsw index tuning, chunk cache.

**Milestone 4 — Demo-ready (Days 22-25)**
- Seed data: 3 realistic sample projects (Hospital expansion, Highway resurfacing, School build).
- Landing page + screenshots.
- Demo video walkthrough.
- README + case study writeup for portfolio site.

---

## 9. Tech Stack (final)

| Layer | Choice | Why |
|---|---|---|
| Frontend | Next.js 16 App Router, TS, Tailwind, shadcn/ui, Recharts | Matches your existing stack, ships fast |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2 | Best AI/doc-parsing ergonomics |
| Async jobs | RQ + Redis (start simple; Celery if we outgrow) | Fewer moving parts than Celery |
| DB | Postgres 15 + pgvector 0.7 (Neon) | One store, transactional, proven |
| LLM | Claude Sonnet 4.6 (primary), Claude Haiku 4.5 (classification), GPT-5 fallback | Sonnet for reasoning, Haiku for cheap batch, GPT for parity |
| Embeddings | OpenAI text-embedding-3-large (3072-dim) | Best quality/cost right now |
| Doc parsing | PyMuPDF (PDF), python-docx, openpyxl, `xerparser` (P6), `mpxj` via JVM sidecar or a cloud parser (MPP) |
| Auth | Clerk | Fast, multi-org, cheap for portfolio |
| Object storage | Cloudflare R2 (S3-compatible, cheap egress) | R2 > S3 for portfolio budgets |
| Deploy | Vercel (web), Render (api + worker), Neon (db), Upstash Redis | All free-tier friendly |
| Observability | Sentry + Logfire (Pydantic team's tool, great for FastAPI) | Cheap, good |

---

## 10. Deployment Plan

- **Vercel** for `apps/web` — auto-deploy on push to `main`, preview branches for PRs.
- **Render** for `apps/api` — Docker deploy, one web service + one worker service.
- **Neon** for Postgres — branch per PR (Neon supports DB branching, useful for preview envs).
- **Upstash** for Redis (RQ queue).
- **Cloudflare R2** for uploaded documents.
- **Secrets** — Vercel env, Render env. Never commit.
- **DB migrations** — Alembic; run on Render pre-deploy hook.
- **Rollback** — Vercel one-click; Render redeploys previous image.

---

## 11. Key Design Decisions & Trade-offs

| Decision | Chose | Rejected | Why |
|---|---|---|---|
| Vector store | pgvector on Postgres | Pinecone, Weaviate | One DB, transactional joins with structured tables, cheaper |
| Chunk size | ~1000 tokens, 100 overlap | 512 or 2000 | Balances retrieval precision with LLM context reads |
| Risk detection | Hybrid rules + LLM | Pure LLM | Determinism on the numeric facts (budget %, overdue days), LLM for interpretation |
| Streaming | SSE, not WebSocket | WS | SSE simpler, fits one-way tokens, plays nice with Render/Vercel |
| Auth | Clerk | Auth.js self-host | Faster to ship; multi-org built in |
| Backend lang | Python | Node | PyMuPDF, pandas, mpxj — construction file formats live in Python |
| MPP parsing | JVM sidecar (`mpxj`) or paid API | Pure Python | No good pure-Python MPP parser exists; ship JVM sidecar in M2 |
| Report output | Markdown source, render PDF via WeasyPrint | LaTeX | WeasyPrint = HTML/CSS familiarity + acceptable output |

---

## 12. Metrics for "did we build the right thing"

- **Time to first insight** — upload doc to first risk detected. Target: under 90s.
- **Chat groundedness** — % of assistant answers with at least one citation. Target: 95%+.
- **Health score explainability** — a PM can read the factors and reconstruct why. Target: qual test with 3 PMs.
- **Report generation time** — target under 30s.
- **Demo conversion** — can a stranger watch a 3-min video and say "I get what this does"? Target: yes.

---

## 13. Open Questions (before writing code)

1. **Scope of M1 demo data** — do we build one realistic hospital-expansion sample project end-to-end, or ship with three light samples? *Recommendation: one deep + two shallow.*
2. **Compliance / data residency** — is any of this touching real PHI or FERPA-covered project data? *Assumption: portfolio demo, no real client data.*
3. **Group PMX specific hook** — do we want to add a slide/section framed to their sectors specifically (they call out healthcare, transportation, education)? *Recommendation: yes, seed the demo with one project per sector.*
4. **Claude Design UI handoff timing** — we build the design doc + backend + minimal UI first; then hand the Figma-equivalent-to-code moment to Claude Design once the data model is stable. Confirm.

---

**Status:** Design complete, ready to scaffold.
**Next artifact:** monorepo scaffold + M0 (foundation) — pending your go.
