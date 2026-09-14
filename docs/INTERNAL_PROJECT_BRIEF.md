# NexivoReach — Internal Project Brief

**Audience:** founders, interviewers, new engineers  
**Status:** private / internal — do not paste into public READMEs or customer decks without redacting ops details  
**Last updated:** 2026-09-14

---

## 1. One-line idea

NexivoReach helps B2B sellers (manufacturers, exporters, private-label suppliers) turn “who should I sell to?” into a shortlist of real buyer accounts, then draft and send outreach — with a human still approving every email.

---

## 2. Problem we solve

Today a seller’s workflow looks like:

1. Google for buyers in a market  
2. Open dozens of sites, skip directories / factories / junk  
3. Guess which accounts actually fit the catalog  
4. Hunt for emails  
5. Write cold emails one by one  

That is slow, noisy, and hard to repeat across markets. NexivoReach compresses steps 1–4 into a **hunt**, and step 5 into **prepare → human send via the seller’s own Gmail**.

**Not trying to be:** an autonomous spam bot, a full CRM, or a LinkedIn scraper.

---

## 3. Who it’s for

| Persona | Need |
|---------|------|
| Apparel / hardgoods exporters | Find importers, brands, wholesalers by product + place |
| Private-label / OEM sellers | Find brands that source, not peer factories |
| Small sales teams | Multi-company workspaces, Sheets backup, daily caps |
| Admin / operator | Invite-only access, suspend users, support tickets |

Default posture: **invite-only Google sign-in**, daily quotas, Sheets required before hunting.

---

## 4. Core product loop

```text
Google login (invite)
  → Workspace: company brief (+ optional catalog scrape/upload)
  → Connect Google Sheets (required for hunt / catalog extract)
  → Connect Gmail (required to send)
  → Find buyers (hunt) → Leads shortlist (~20 strong + ~20 average)
  → Prepare outreach → human approve → send via Gmail
  → Optional: sync replies, Sheets sync / restore
```

### Surfaces

| Area | Job |
|------|-----|
| **Workspace** | Company context, catalog, ICP markets/categories, Connect |
| **Find buyers** | Natural-language hunt (“belt importers in Nevada”) |
| **Leads** | Queue, Fit / Intent / priority, review drawer |
| **Outreach** | Draft inbox, prepare & send, reply sync |
| **Activity** | Agent decision log for a hunt |
| **Support / Admin** | Tickets, invites, caps, suspension |

---

## 5. Technology stack

| Layer | Choice |
|-------|--------|
| Frontend | React 19 + TypeScript + Vite + Tailwind |
| Backend | FastAPI + Uvicorn |
| ORM / models | SQLModel (SQLAlchemy + Pydantic) |
| Auth | Google OAuth → JWT session cookie |
| DB | SQLite (local) / Postgres (production, e.g. Render) |
| Search | Serper (primary) → Brave → Tavily → DuckDuckGo |
| Scrape | httpx + BeautifulSoup (+ optional Cloudflare Worker proxy) |
| AI | Gemini (preferred) or Groq; template/heuristic fallback |
| Email | Gmail API (`gmail.send` + `gmail.readonly`) |
| Spreadsheet | Google Sheets + Drive (`drive.file`) per-user OAuth |
| Deploy | Docker, Render (`render.yaml`), optional Caddy TLS |

### Monorepo layout (high level)

```text
frontend/     SPA (hash routing inside App.tsx)
backend/app/
  api/            HTTP routers
  agents/         hunt planner, SERP filter, qualify, outreach
  tools/          web_search, contact_finder
  providers/      Gemini / Groq / Fallback
  integrations/   gmail, sheets, sheets_oauth
  models/         SQLModel tables
  services/       access quotas, notifications
infra/            Cloudflare scrape worker
```

---

## 6. Architecture

### 6.1 Request shape

```text
Browser (React SPA, cookies)
    │  /api/*
    ▼
FastAPI
    ├── Auth / OAuth callbacks
    ├── Discovery (hunt)
    ├── Prospects / Outreach
    ├── Sheets / Products / ICP / Companies
    └── Admin / Support / Notifications
         │
         ├── SQLModel → SQLite or Postgres
         ├── Serper / Brave / Tavily / DDG
         ├── httpx scrapes (optional proxy)
         ├── Gemini or Groq
         └── Google Gmail + Sheets APIs
```

Production often serves the built SPA from the same FastAPI process (`STATIC_DIR`), so one container / one port is enough (Render-friendly).

### 6.2 Lead hunt pipeline (critical path)

Designed for **speed + authentic shortlists**, not “scrape the whole internet.”

1. **Infer seller profile** — OEM / wholesale / SaaS / service, geo, maps on/off (`search_planner.py`)  
2. **Wave 1 searches** — capped query set (≈10), merge unique company URLs  
3. **SERP classify** — drop directories, listicles, jobs, wrong-geo, peer factories when hunting buyers  
4. **Wave 2** — only if wave 1 is thin (relevant count below threshold); fewer refined queries  
5. **Homepage scrape** — batched httpx fetches, shared client, early exit once enough live sites  
6. **Heuristic qualify** — Fit vs Intent with evidence snippets (`qualify.py`) — **not** an LLM on the hunt path  
7. **Shortlist** — ~20 strong + ~20 average; persist to DB  
8. **Contacts** — homepage mailto seeds during hunt; deeper contact crawl in **background**  
9. **Sheets sync** — background after hunt  

**Why heuristics for qualify?** Hunt latency and cost. LLM qualify is available as provider methods for other flows, but the live Discover path must stay network-bound (search + scrape), not LLM-bound.

### 6.3 Outreach path

Prepare uses LLM (or templates) → light QC → human edits To/subject/body → Gmail send with the user’s OAuth token. Reply polling uses `gmail.readonly`.

### 6.4 Multi-tenancy & access

- Users → multiple companies (`Business`)  
- Daily UTC quotas: hunt / extract / prepare / send  
- Invite allowlist + optional admin emails  
- Suspended users get an appeal / support path  

---

## 7. Why this tech (and not the obvious alternative)

| Decision | We chose | Alternative | Why this |
|----------|----------|-------------|----------|
| Backend | FastAPI | Nest / Django / Express | Fast async I/O for parallel search+scrape; Python ecosystem for scraping/AI; small team velocity |
| Frontend | React + Vite | Next.js | App is an authenticated SPA behind cookies; no SEO need; simpler deploy as static assets on the API |
| Routing | Hash / history state | React Router | One shell app, fewer deps; routes are product areas not public pages |
| Qualify | Heuristics | LLM-per-lead | Cost + latency; hunt can touch dozens of sites; Fit/Intent rules are auditable |
| Scrape | httpx + BS4 | Playwright / Puppeteer | Most B2B sites are server-rendered enough for homepage text; headless browsers are slow, fragile, and get banned harder |
| Search | Serper-first cascade | Single Google CSE only | Serper ≈ Google quality; cascade survives key outages / empty results |
| Maps | Serper Places when useful | Always-on Maps | Maps doubles latency; only for local motions (gyms, clinics, etc.) |
| AI | Gemini or Groq + fallback | One vendor only | Keys/models churn; templates keep outreach working offline |
| Sheets | Per-user OAuth workbook | Central service-account sheet | Users own their data; Drive `file` scope is safer than full Drive |
| Gmail | User OAuth send | SMTP / SendGrid | Sends from the seller’s real mailbox → higher trust, fewer deliverability fights |
| DB | Postgres in prod | Mongo / Firestore | Relational fit for users↔companies↔prospects; SQLModel stays close to Pydantic |
| Auth | Google + invite | Magic links / password | Target users already live in Google; invite-only reduces abuse while OAuth app is in Testing |
| Deploy | Docker + Render | Pure Vercel + separate API | One image can ship API+SPA; Postgres addon matches statefulness |

---

## 8. Important know-how (ops & product)

### OAuth / Gmail

- Login scopes ≠ Gmail scopes. Sign-in alone cannot send mail.  
- Need **Gmail API enabled** + consent screen scopes `gmail.send` and `gmail.readonly`.  
- Refresh tokens die (revoke, re-consent, client secret rotate). UI must not say “Ready” if send is impossible.  
- On refresh `invalid_grant`, clear Gmail tokens and force reconnect.  
- Prefer **Disconnect → Connect Gmail** after scope or secret changes.

### Sheets gate

- Hunt and catalog extract intentionally **require** Sheets connected.  
- Sheets is sync/backup/restore, not the primary DB — but product policy uses it as a “connected workspace” gate.

### Hunt quality vs speed

- Volume target: **20–30+ authentic leads**, not 200 junk domains.  
- SERP filter + homepage Fit score matter more than raw SERP count.  
- Contact emails often arrive **after** the hunt returns (background job). Don’t claim “email found on contact page” if only homepage seeds ran.

### Quotas & abuse

- Daily caps protect Serper/Gemini/Gmail spend.  
- Admins can raise caps or bypass.  
- Invite-only + Google test users while the Cloud project is in Testing mode.

### Scraping reality

- Some hosts firewall cloud IPs (CSF / Imunify360). Optional Cloudflare Worker proxy helps.  
- Keep concurrency moderate; catalog scrape is more aggressive than hunt homepage fetch.

### Local vs prod data

- SQLite on ephemeral hosts loses data. Production needs `DATABASE_URL` Postgres.  
- Never commit secrets; use `.env` / Render env.

### Honest UI

- Don’t show Gmail “Ready” without send capability.  
- Don’t invent hunt ETAs (“15s left”) — show elapsed / phase language.  
- Don’t claim Maps ran when maps is off.

---

## 9. Data model (mental map)

| Entity | Role |
|--------|------|
| `User` | Google identity, Gmail/Sheets tokens, plan, suspension |
| `Business` | Company workspace (brief, markets, sheet id) |
| `ProductItem` | Catalog rows |
| `ICPConfig` | Buyer types / countries / notes |
| `ProspectRecord` | Lead + Fit/Intent + draft + contacts + stage |
| `AgentRunRecord` | Hunt decision log |
| `UsageDaily` | Per-user UTC counters |
| `InviteAllowlist` / `SupportTicket` / `Notification` | Access & ops |

---

## 10. Common tricky questions (and solid answers)

### Product / strategy

**Q: Isn’t this just Apollo / ZoomInfo with a thinner database?**  
A: Those sell a prebuilt contact graph. We sell a **seller-specific hunt**: product + motion + place → live web shortlist + Fit/Intent evidence + outbound from *their* Gmail. Different data asset, different workflow.

**Q: Why human-in-the-loop send?**  
A: Deliverability, trust, and liability. Auto-send cold email at scale burns domains and invites compliance risk. We draft; humans approve.

**Q: Why require Sheets?**  
A: Gives every workspace a durable, user-owned export/backup and a clear “workspace is set up” gate. Primary store remains our DB.

**Q: How do you avoid junk leads?**  
A: Multi-stage filter — query design by seller motion, SERP classifier (directories/jobs/factories/geo), homepage qualify with evidence, strong vs average buckets instead of dumping raw SERP.

### Technical

**Q: Why not LLM-qualify every site?**  
A: Parallel scrapes already dominate latency. Per-lead LLM would multiply cost and time; heuristics are deterministic and logged.

**Q: Why not Playwright?**  
A: Homepage text for B2B qualify rarely needs a full browser. Playwright costs CPU, cold starts, and ban risk. We escalate via proxy when needed, not headless Chrome by default.

**Q: What if Serper is down?**  
A: Cascade to Brave → Tavily → DuckDuckGo. Quality drops, hunt still runs.

**Q: How is multi-company isolation enforced?**  
A: Prospects/products/ICP keyed by `business_id`; API resolves active company for the session user.

**Q: Where do refresh tokens live?**  
A: On the `User` row (Gmail / Sheets fields). Access tokens are short-lived; refresh failure clears Gmail and asks reconnect.

**Q: Why JWT cookie instead of Bearer in localStorage?**  
A: HttpOnly cookie reduces XSS token theft for a same-site SPA; CSRF mitigated with SameSite and same-origin API.

**Q: SQLite in production?**  
A: No for Render. Ephemeral filesystem. Postgres via `DATABASE_URL`.

**Q: How do you prevent one user from exhausting search APIs?**  
A: Daily hunt/extract/prepare/send quotas + invite-only signup.

### Security / compliance

**Q: Do you store customer passwords?**  
A: No — Google OAuth only.

**Q: Can you read a user’s entire Drive?**  
A: No — Sheets path uses `drive.file` (files the app creates/opens), not full Drive.

**Q: GDPR / data deletion?**  
A: Leads and tokens live in our DB under the user; disconnect clears Gmail/Sheets tokens; full account deletion is an ops procedure (document if you productize further).

### Failure modes (interview gold)

**Q: Gmail shows connected but send fails with 403 insufficient scopes.**  
A: Token lacks `gmail.send` (partial consent or consent screen missing scopes). Verify via tokeninfo; force reconnect; enable Gmail API.

**Q: Send fails with token refresh 400.**  
A: Dead refresh token (`invalid_grant`). Clear tokens, disconnect/reconnect, confirm client id/secret match.

**Q: Hunt returns leads with no emails.**  
A: Expected initially — deep contact crawl is background. Refresh leads / wait for fill job.

**Q: Hunt is slow.**  
A: Dominated by search waves + homepage GETs. Mitigations: fewer queries, skip wave 2 when enough relevant hits, batched scrape with early exit, Serper timeout discipline.

**Q: Catalog scrape incomplete on large Shopify/Woo stores.**  
A: Dedicated cascade (platform APIs → sitemaps → paginated HTML) with budgets; not the same path as hunt homepage fetch.

### Design / UX

**Q: Why hash routing?**  
A: Simple SPA behind one origin; deep links via `#leads` / `#outreach` without a separate router package.

**Q: Why dark mode as a toggle, not default?**  
A: Sales work is often daytime; brand direction favors light; toggle for preference without forcing neon “AI SaaS” defaults.

---

## 11. What “good” looks like in a demo

1. Invite a Google account, sign in  
2. Create/select a company with a clear brief + 1–2 markets  
3. Connect Sheets (and Gmail for send)  
4. Hunt: e.g. `hoodie wholesalers in Texas` → tens of leads in under ~1 minute  
5. Open Leads: show Fit / Intent / why-this-prospect evidence  
6. Prepare outreach → edit To → send one email from their Gmail  
7. Show Activity log steps (plan → search → classify → fetch → qualify)

---

## 12. Known limitations (be honest)

- Not a replacement for a paid contact database on every industry  
- Some sites block datacenter IPs; emails may lag behind the hunt  
- OAuth Testing mode limits who can connect Google  
- Heuristic qualify can mis-rank edge cases (wrong language sites, thin brochureware)  
- README may lag product (Sheets gating, heuristic hunt path) — trust the code

---

## 13. Glossary

| Term | Meaning |
|------|---------|
| **Hunt** | One Find-buyers run |
| **Fit** | How well the account matches ICP / offer |
| **Intent** | Buying / sourcing signals on the site |
| **Strong / Average** | Shortlist buckets after qualify |
| **Workspace connect** | Combined Gmail + Sheets consent |
| **Prepare** | Generate/refresh outreach drafts (quota) |

---

## 14. Suggested reading order for engineers

1. `README.md` (intent)  
2. `backend/app/main.py` (route map)  
3. `backend/app/agents/prospecting_agent.py` (hunt)  
4. `backend/app/agents/qualify.py` + `serp_classifier.py`  
5. `backend/app/api/discovery.py` + `outreach.py`  
6. `backend/app/integrations/gmail.py` + `auth.py`  
7. `frontend/src/App.tsx` + `FindBuyersPanel.tsx` + `SettingsView.tsx`

---

*End of internal brief. Keep secrets in env managers only — never in this file.*
