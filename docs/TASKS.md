# TASKS.md — Ownership, Sprint 1, and Workflow

*Bibek leads. Tasks are handed out as GitHub Issues; nobody starts a piece of work that isn't an issue. No fixed calendar dates yet — work is ordered by dependency, and dates get attached when the sprint board is created.*

*Last updated: 2 Nov 2026 — added Sprint 1 task 11 and the pointer to the ready-to-paste issue cards.*

Names below: **Bibek (Lead)**, **Member B**, **Member C** — replace B and C with real names once you decide who is stronger at what.

---

## 1. Ownership split

The split follows the architecture's own seams (see CONTRIBUTING.md), so people rarely edit the same files.

| Owner | Area | What they own |
|---|---|---|
| **Bibek (Lead)** | ML, ETL, infrastructure | `notebooks/`, `shared/`, `inference-service/`, `workers/`, Dockerfiles, `docker-compose.yml`, `nginx.conf`, pinned `requirements.txt`, latency logging |
| **Member B** | Backend and security | `core-api/` skeleton, DB models + Alembic (schema owner), auth + sessions, RBAC, Users CRUD, audit-log writer, access-control tests |
| **Member C** | Features and frontend | Jinja2 layout and CSS, login pages, customer pages, Notes CRUD, Watchlist CRUD, then dashboards, WebSocket live view, CSV upload UI, export |

### Bibek — full list
1. EDA notebook on the PaySim Parquet cache
2. Four-way chronological split (train / val / test / replay pool), fixed `random_state`
3. Feature spec (`docs/FEATURE_SPEC.md`) and the single shared feature function in `shared/`
4. Baseline Logistic Regression, then Random Forest, then XGBoost, with the metrics table (precision, recall, F1, PR-AUC, confusion matrix), plus the rule baselines R1–R3 (`docs/FEATURE_SPEC.md` section 6.1)
5. `docs/API_CONTRACT.md` — `/predict` request/response schema (**first deliverable, unblocks B and C**)
6. `inference-service` (loads the model once, `/predict` only)
7. Workers: PaySim replay producer, PaySim fraud consumer (NEPSE workers later, see section 5)
8. Dockerfiles, compose that actually runs, `nginx.conf`
9. Latency timestamps at ingestion and decision-write
10. `model_versions` and `etl_runs` writers

### Member B — full list
1. `core-api` skeleton: app factory, `pydantic-settings` config, async DB session
2. SQLAlchemy 2.0 models for every table, first Alembic migration, ER diagram in `docs/`
3. Auth: login/logout, bcrypt hashing, Redis-backed server-side sessions (opaque session-ID cookie), session regeneration on login, timeout
4. `require_role(...)` dependency and per-user ownership checks
5. Users CRUD (Admin): create, edit, activate/deactivate, **hybrid delete** (hard delete if no activity, soft delete via `deleted_at` otherwise), with search/filter and pagination
6. Audit-log writer (insert-only; update only on the review-status field)
7. Access-control tests: log in as each role and try other roles' URLs, expecting 403

### Member C — full list
1. Jinja2 base template, responsive CSS, role-based navigation, persistent decision-support disclaimer banner
2. Login/registration pages with client-side validation
3. Customer pages: submit a transaction, view own transactions only
4. Investigation Notes CRUD (Analyst own, Admin all) with search and pagination
5. Watchlist / Flagged Accounts CRUD (Admin and Analyst) with search and pagination
6. Later: prediction log listing with filters, analyst review UI, WebSocket live view, CSV upload UI (Flow C), CSV/Excel export and printable report

**Dependency:** C works against mock data and mock templates until B's models and auth merge. B and C both need `docs/API_CONTRACT.md` before they touch anything that calls `inference-service`.

---

## 2. Sprint 1 — in order

Ready-to-paste issue cards for tasks 1–11 (plus a team tooling checklist) are in `docs/SPRINT1_ISSUES.md`.

| # | Task | Owner | Blocked by |
|---|---|---|---|
| 1 | `docs/API_CONTRACT.md` (`/predict` schema) | Bibek | — |
| 2 | `core-api` skeleton, config, async DB session | B | — |
| 3 | Jinja2 base layout, CSS, nav, disclaimer banner | C | — |
| 4 | Dockerfiles + compose runs `postgres`, `redis`, `core-api` | Bibek | 2 (needs an app to build) |
| 5 | SQLAlchemy models + first Alembic migration + ER diagram | B | 2 |
| 6 | EDA + four-way split notebook | Bibek | — |
| 7 | Auth: login/logout, sessions, bcrypt | B | 5 |
| 8 | Login pages | C | 3 (can mock until 7 merges) |
| 9 | `docs/FEATURE_SPEC.md` + shared feature function | Bibek | 6 |
| 10 | `require_role` + ownership checks + access tests | B | 7 |
| 11 | Baseline Logistic Regression + rule baselines R1–R3, metrics table | Bibek | 9 |

Sprint 1 is done when: all three can run `docker-compose up`, log in as each role, and see role-appropriate pages; the baseline model exists with a metrics table (task 11).

---

## 3. How to run it

**Board.** Use GitHub Projects with columns *Backlog / In progress / In review / Done*. Labels by area: `ml`, `etl`, `infra`, `core-api`, `frontend`, `db`, `docs`.

**One issue = one branch = one PR.** Branch naming from CONTRIBUTING.md (`core-api/auth-sessions`). Keep PRs small and merged quickly.

**Task card template** (paste into every issue):

```
Goal:
Acceptance criteria:
- [ ]
- [ ]
Files likely touched:
Depends on (issue #):
How to test:
```

**Review rules.** Branch protection requires one review. A teammate reviews Bibek's PRs too — leading doesn't exempt you, and every member's history counts toward the spec's commit-history requirement (3.8). Each person commits their own work under their own GitHub account.

**Syncs.** A short check-in two or three times a week: what merged, what's blocked, what's next. Bibek assigns the next issue at the end of each one.

**Handing out work.** When you want a task done, write the card, assign it, and label it. Anything vague gets a card before it gets started.

**Tooling checklist (everyone):**
- [ ] Python version pinned (same minor version for all three)
- [ ] Docker Desktop working; `docker-compose up --build` succeeds
- [ ] `.env` copied from `.env.example`
- [ ] `pre-commit` or `ruff` + `black` agreed (optional but cheap)
- [ ] Each person's Git name/email set so commits are attributed correctly

---

## 4. Rules that protect the project

- Nobody pushes to `main`.
- Schema changes only through Alembic migrations, in their own small PR.
- Feature logic is written once in `shared/`; notebooks and workers import it. Never reimplemented.
- Never commit `.env`, raw CSV, Parquet cache or model artifacts.
- Flows A, B and C stay separate in code, docs and the viva.

---

## 5. Pinned open item — NEPSE data source

**Status: undecided.** The hosted NEPSE API returned Cloudflare 522 on `/health`, `/Summary` and `/Floorsheet`, which means the origin server is down.

Options:
1. Self-host `basic-bgnr/NepseUnofficialApi` (timebox 2–3 days; fall back if it fails)
2. Replay historical floorsheets (e.g. `suyogdahal/nepse-data`) as a stand-in for a live feed
3. Retry the hosted API

**Decision checkpoint:** raise this when the PaySim replay producer and consumer (Flow A) are running, or before any Flow B work starts, whichever comes first. README Flow B still says "live" and must be reworded once the choice is made. Flow B does not block anything in Flow A, so it can wait until then.
