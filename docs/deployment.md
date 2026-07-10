# Deployment

PMX AI ships as two independently deployed apps:

| App          | Host   | URL                                    | Trigger              |
|--------------|--------|----------------------------------------|----------------------|
| `apps/web`   | Vercel | https://pmx-ai-copilot.vercel.app      | push to `main`       |
| `apps/api`   | Render | https://pmx-api.onrender.com (TBC)     | push to `main`       |

Continuous integration for both apps runs in GitHub Actions (`.github/workflows/ci.yml`).

---

## 1. Vercel (web)

**Project:** `pmx-ai-copilot`, linked to GitHub repo `joyo11/pmx-ai-copilot`.

**Settings (one-time, dashboard):**

- Root Directory: `apps/web`
- Framework Preset: Next.js
- Install Command: `pnpm install --frozen-lockfile`
- Build Command: `pnpm build`
- Output Directory: `.next` (default)
- Production Branch: `main`

**Required env vars (Project Settings → Environment Variables):**

| Key                                   | Value / Notes                                         |
|---------------------------------------|-------------------------------------------------------|
| `NEXT_PUBLIC_API_URL`                 | `https://pmx-api.onrender.com`                        |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`   | from Clerk dashboard (M0.4)                           |
| `CLERK_SECRET_KEY`                    | from Clerk dashboard (M0.4)                           |

Missing keys during M0.5 are fine; they land as the milestones that need them close out.

### Fixing "auto-deploy on push didn't fire"

Root causes, in order of likelihood:

1. **Vercel GitHub App is not installed on the `joyo11` account.** Vercel needs
   the GitHub App (not just the OAuth login) to receive push webhooks. Install
   or reauthorize it at
   <https://vercel.com/docs/deployments/git/vercel-for-github>, granting access
   to the `pmx-ai-copilot` repo. This is a dashboard-only action.
2. **Production Branch is not `main`.** Project Settings → Git → Production
   Branch must be `main`. If it says `master` or a stale branch, pushes to
   `main` will only create preview deployments and never promote.
3. **Ignored Build Step is set.** Project Settings → Git → Ignored Build Step.
   If a script is present, it may be exiting `0` and skipping the build. Clear
   it, or set it to `bash -c 'git diff HEAD^ HEAD --quiet -- apps/web || exit 1'`
   so pushes that touch the web app always deploy.
4. **Root Directory is wrong.** If Root Directory is `.` instead of `apps/web`,
   Vercel builds the wrong package and may fail silently on monorepo changes.

To verify after fixing: push a whitespace-only change to `apps/web/README.md`
and confirm a new deployment appears in the Vercel dashboard within ~30s.

---

## 2. Render (api)

**Provisioning:** blueprint-driven from `render.yaml` at repo root.

**One-time setup:**

1. Render dashboard → **Blueprints** → **New Blueprint Instance**.
2. Connect the `joyo11/pmx-ai-copilot` repo, branch `main`.
3. Render parses `render.yaml` and creates the `pmx-api` web service.
4. Fill the secrets marked `sync: false` (see table below).
5. Click **Apply**. First build runs `pip install uv && uv sync --frozen`,
   start command is `uv run pmx-api`.

Blueprint spec reference: <https://render.com/docs/blueprint-spec>.

**Env vars declared in `render.yaml`:**

| Key                        | Source           | Notes                                                       |
|----------------------------|------------------|-------------------------------------------------------------|
| `ENVIRONMENT`              | blueprint        | `production`                                                |
| `LOG_LEVEL`                | blueprint        | `INFO`                                                      |
| `CORS_ALLOW_ORIGINS`       | blueprint        | `https://pmx-ai-copilot.vercel.app`                         |
| `LOGFIRE_SEND_TO_LOGFIRE`  | blueprint        | `true`                                                      |
| `HOST`                     | blueprint        | `0.0.0.0` (Render requirement)                              |
| `PORT`                     | Render-injected  | Render sets this automatically; declared for clarity        |
| `DATABASE_URL`             | dashboard secret | Neon pooled connection string (M0.3)                        |
| `ANTHROPIC_API_KEY`        | dashboard secret | Claude API                                                  |
| `OPENAI_API_KEY`           | dashboard secret | embeddings                                                  |
| `CLERK_JWT_ISSUER`         | dashboard secret | e.g. `https://<slug>.clerk.accounts.dev` (M0.4)             |
| `LOGFIRE_TOKEN`            | dashboard secret | write token from Logfire project settings                   |

**Health check:** Render pings `/v1/health`. The service must return 200 within
the health-check timeout for a deploy to be considered live.

**Rollback:** Render dashboard → service → Deploys → **Rollback** on any prior
green deploy.

---

## 3. Neon (Postgres)

Wired up in M0.3, but the deployment steps are:

1. <https://console.neon.tech> → **New Project**. Region: US East (matches Render).
2. Copy the **pooled** connection string (Neon offers pooled + direct — API
   uses pooled for HTTP request lifetimes).
3. Set `DATABASE_URL` in Render (production) and in `apps/api/.env` (local).
4. Enable pgvector once per database:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
   Run via the Neon SQL editor, or `psql "$DATABASE_URL" -c 'CREATE EXTENSION IF NOT EXISTS vector;'`.
5. Alembic migrations run in a Render pre-deploy hook (added in M0.3).

Neon's DB branching means we can point preview deploys at ephemeral DB branches
later; not needed for M0.

---

## 4. Clerk (auth)

Wired up in M0.4, but the deployment steps are:

1. <https://dashboard.clerk.com> → **Create Application**. Choose email +
   Google as sign-in methods.
2. From **API Keys**, copy:
   - Publishable Key → Vercel env `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`.
   - Secret Key → Vercel env `CLERK_SECRET_KEY`.
3. From **JWT Templates**, create or note the default template. Copy the
   **Issuer URL** (looks like `https://<slug>.clerk.accounts.dev`) →
   Render env `CLERK_JWT_ISSUER`. The API verifies JWTs against JWKS at
   `<issuer>/.well-known/jwks.json`.
4. In Clerk → **Domains**, add `https://pmx-ai-copilot.vercel.app` as an
   allowed origin.

---

## 5. Push-to-deploy flow

Once the above one-time steps are done:

```
git push origin main
   │
   ├─► GitHub Actions runs `ci.yml` (web + api jobs in parallel)
   ├─► Vercel builds & deploys `apps/web`
   └─► Render builds & deploys `apps/api`
```

CI failures do not block Vercel/Render — they deploy on push, not on green CI.
Treat CI red as "revert or hotfix" signal, not as a gate. (Adding
required-checks gating is a follow-up once the pipeline is stable.)

---

## 6. Deferred to M1

- **Upstash Redis** — RQ queue for background jobs (ingestion, risk
  scoring). Provision at <https://upstash.com>, add `REDIS_URL` to Render.
- **Cloudflare R2** — object storage for uploaded documents. Provision at
  <https://dash.cloudflare.com>, add `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`,
  `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` to Render.

Neither is needed to serve the M0 stack.
