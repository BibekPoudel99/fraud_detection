# SPRINT1_ISSUES.md — ready-to-paste GitHub issue cards

Each card below is one GitHub issue. Copy everything from its `###` title down to the next `---`. Title goes in the issue title; the rest goes in the body. Set the assignee and labels shown, then link the branch in the PR.

**Card IDs.** `S1-xx` is a placeholder. After you create the issues, replace each `S1-xx` in "Depends on" with the real `#number` GitHub gives it.

**Paths.** I wrote paths as `core-api/app/...`, `notebooks/...` etc. from README and TASKS. If your scaffold names differ, adjust the paths, not the content.

**Commands** are PowerShell (Windows). On macOS/Linux use `curl` instead of `Invoke-RestMethod` and `source .venv/bin/activate`.

## Assumptions baked into the cards (change them before pasting if you disagree)

1. **Registration:** self-registration creates a **Customer** account only. Analyst and Admin accounts are created by an Admin through Users CRUD. (README doesn't say; this is the safe default.)
2. **Sessions:** the browser holds only a random session-ID cookie; session data lives in Redis. README 5.2 was corrected to match (Starlette's `SessionMiddleware` keeps its data in a signed cookie, so it is not used).
3. **S1-11 is new.** TASKS.md says Sprint 1 is done when "the baseline model exists with a metrics table", but none of the ten Sprint 1 rows produces it.
4. **No label in the operational database.** The `transactions` table has no `isFraud` column, so the label cannot leak into the live path.

## Order and dependencies

```
S1-00 tooling (all)
S1-01 contracts + shared code (Bibek)       -> unblocks everyone
S1-02 core-api skeleton (B) --> S1-04 Docker/compose (Bibek)
        \--> S1-05 DB models + Alembic (B) --> S1-07 auth (B) --> S1-10 roles + access tests (B)
S1-03 Jinja2 layout (C) --> S1-08 login pages (C)  (mock until S1-07 merges)
S1-06 EDA + split (Bibek) --> S1-09 feature function on real data (Bibek) --> S1-11 baseline models (Bibek)
```

Start in parallel on day one: S1-00, S1-01, S1-02, S1-03, S1-06.

---

### S1-00 Team tooling and environment checklist

**Assignee:** each of the three (one checklist, three people tick their own)  **Labels:** `infra`, `docs`  **Branch:** none (no code)

**Goal:** all three machines run the same Python minor version and the stack tooling, so "works on my machine" problems don't eat Sprint 1.

**Acceptance criteria**
- [ ] Same Python minor version for all three; the version is written in `.python-version` (or README) in a small PR.
- [ ] Docker Desktop runs; `docker compose version` prints a version.
- [ ] `git config user.name` and `user.email` match your GitHub account (commits are attributed to you).
- [ ] You can clone the repo, create `.venv`, activate it, and `pip install` the pinned `requirements.txt` without errors.
- [ ] `.env` is copied from `.env.example` and is **not** tracked by git (`git status` doesn't list it).
- [ ] The team agrees on `ruff` and `black` (or none); decision noted in CONTRIBUTING.md.

**Files likely touched:** `.python-version`, `CONTRIBUTING.md`.

**Depends on:** none.

**How to test:**
```powershell
python --version
docker compose version
git config user.name; git config user.email
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
git status   # .env must not appear
```
Comment on the issue with the output of the first three lines.

---

### S1-01 Merge the contracts and shared code

**Assignee:** Bibek (reviewer: Member B or C)  **Labels:** `docs`, `ml`  **Branch:** `docs/contracts-and-shared-code`

**Goal:** the `/predict` contract, the feature spec and the shared code land on `main`, so B and C can build against a mock of `inference-service` while the real one doesn't exist yet.

**Acceptance criteria**
- [ ] `docs/API_CONTRACT.md` and `docs/FEATURE_SPEC.md` are on `main`.
- [ ] `shared/schemas/predict.py`, `shared/features/core.py`, `shared/features/batch.py`, `tools/mock_inference.py` and `tests/` are on `main`, with `__init__.py` in `shared/`, `shared/schemas/`, `shared/features/` and `tools/`.
- [ ] `requirements.txt` pins exact versions of what the tests need (`pydantic`, `pandas`, `fastapi`, `uvicorn`, `httpx`, `pytest`).
- [ ] **The reviewer** runs the tests and the mock on their own machine and comments the result.
- [ ] `tests/test_mock_inference.py` passes (it was not run when the files were written, because FastAPI could not be installed in the sandbox).

**Files likely touched:** `docs/`, `shared/`, `tools/`, `tests/`, `requirements.txt`.

**Depends on:** none.

**How to test:**
```powershell
pip install -r requirements.txt
python -m pytest
$env:PYTHONPATH = "."
uvicorn tools.mock_inference:app --port 8001
# in a second terminal:
$body = '{"feature_schema_version":"1.0.0","instances":[{"transaction_id":"demo-HIGH","features":{"f":1}}]}'
Invoke-RestMethod -Method Post -Uri http://localhost:8001/predict -ContentType "application/json" -Body $body
```
Expect `risk_tier` = `HIGH_RISK` and `model_version` = `mock-0`.

---

### S1-02 core-api skeleton: app factory, settings, async DB session

**Assignee:** Member B  **Labels:** `core-api`  **Branch:** `core-api/skeleton`

**Goal:** a running `core-api` that every other piece can plug into: configuration from `.env`, an async database session, and one health route.

**Acceptance criteria**
- [ ] `create_app()` app factory; run with `uvicorn app.main:create_app --factory`.
- [ ] `Settings` class using `pydantic-settings` reading `.env`: database URL, Redis URL, session secret key, inference-service base URL, session idle timeout. Missing required values stop startup with a clear error naming the variable.
- [ ] `.env.example` lists every variable with a **placeholder** value; `.env` is in `.gitignore`.
- [ ] Async SQLAlchemy engine and a `get_db` dependency yielding an `AsyncSession` (asyncpg driver).
- [ ] `GET /health` returns 200 and checks the database with a trivial query; returns 503 if the database is unreachable.
- [ ] Folder layout for later work exists as empty packages: `routers/`, `models/`, `schemas/`, `services/`, `templates/`, `static/`.
- [ ] No secrets anywhere in the diff.

**Files likely touched:** `core-api/app/main.py`, `config.py`, `db.py`, `deps.py`, `core-api/requirements` (or the root file), `.env.example`.

**Depends on:** none (needs a local Postgres; until S1-04 merges, run one with `docker run`).

**How to test:**
```powershell
docker run --name pg-dev -e POSTGRES_PASSWORD=dev -p 5432:5432 -d postgres:16
# set DATABASE_URL in .env, then:
uvicorn app.main:create_app --factory --port 8000
Invoke-RestMethod http://localhost:8000/health
# remove DATABASE_URL from .env -> startup must fail naming DATABASE_URL
docker stop pg-dev   # /health must now return 503
```

---

### S1-03 Jinja2 base layout, responsive CSS, role navigation, disclaimer banner

**Assignee:** Member C  **Labels:** `frontend`  **Branch:** `frontend/base-layout`

**Goal:** one base template every page extends, so every screen gets the same layout, role-appropriate navigation, and the required decision-support disclaimer.

**Acceptance criteria**
- [ ] `base.html` with header, nav, content block, footer, flash-message area; static CSS and JS mounted at `/static`.
- [ ] Responsive: no horizontal scroll at 360 px or 1280 px wide; nav collapses on narrow screens.
- [ ] Nav items depend on a `current_user.role` value in the template context (Admin, Fraud Analyst, Customer, anonymous). **This is display only; real access control is S1-10.** Add a comment in the template saying so.
- [ ] A reusable `partials/disclaimer.html` with the exact text from README 5.17: *"This is a probability-based decision-support estimate, not a fraud determination. All flagged transactions require human review before action is taken."* Any template that shows a prediction includes it.
- [ ] Works without the database: a small throwaway page (`templates/_preview.html` plus a dev-only route, or a static HTML file) renders the layout with dummy users for each role.
- [ ] Semantic HTML, form labels, visible keyboard focus.

**Files likely touched:** `core-api/app/templates/base.html`, `partials/`, `core-api/app/static/css/`, `static/js/`.

**Depends on:** none (use your own tiny FastAPI stub until S1-02 merges).

**How to test:** render the preview for each of the four dummy roles; check the nav items; use the browser's device toolbar at 360 px and 1280 px; attach one screenshot per width to the PR.

---

### S1-04 Dockerfile(s) and docker-compose running postgres, redis, core-api

**Assignee:** Bibek  **Labels:** `infra`  **Branch:** `infra/compose-core`

**Goal:** `docker compose up --build` starts a working stack on any teammate's machine from a clean clone.

**Acceptance criteria**
- [ ] `core-api/Dockerfile` (slim Python image, non-root user, installs from the pinned requirements).
- [ ] `docker-compose.yml` with `postgres`, `redis`, `core-api`; named volume for Postgres data; healthchecks on `postgres` and `redis`; `core-api` uses `depends_on: condition: service_healthy`.
- [ ] Configuration comes from `.env` (no secrets in the compose file or the images).
- [ ] `core-api` is reachable on the published port and `/health` returns 200.
- [ ] Data survives `docker compose down` and `up` (volume check).
- [ ] CONTRIBUTING.md "Running the stack locally" is updated to match what actually runs (compose v2 syntax: `docker compose`).
- [ ] **A teammate has run it on their own machine** and commented the result.

**Files likely touched:** `core-api/Dockerfile`, `docker-compose.yml`, `.env.example`, `CONTRIBUTING.md`, `.dockerignore`.

**Depends on:** S1-02 (needs an app to build).

**How to test:**
```powershell
git clone <repo> fresh-clone; cd fresh-clone
Copy-Item .env.example .env
docker compose up --build -d
docker compose ps                 # all healthy
Invoke-RestMethod http://localhost:8000/health
docker compose down; docker compose up -d   # data volume still there
```

---

### S1-05 SQLAlchemy 2.0 models, first Alembic migration, ER diagram

**Assignee:** Member B (schema owner)  **Labels:** `db`, `core-api`  **Branch:** `db/models-and-first-migration`

**Goal:** every table the platform needs, as async SQLAlchemy models plus one reviewed Alembic migration, with the append-only tables protected and the ER diagram written down.

**Acceptance criteria**
- [ ] Models exist for: `roles`, `users`, `transactions`, `fraud_predictions`, `model_versions`, `audit_logs`, `etl_runs`, `investigation_notes`, `watchlist`. (Sessions live in Redis, not here.)
- [ ] `users`: unique email, `password_hash`, `role_id`, `is_active`, `deleted_at` (soft delete), timestamps.
- [ ] `transactions`: `transaction_id` (string, primary key, up to 64 chars, matching `docs/API_CONTRACT.md`), `step`, `type`, `amount`, `name_orig`, `oldbalance_org`, `newbalance_orig`, `name_dest`, `oldbalance_dest`, `newbalance_dest`, `source` (`replay` / `batch_upload` / `customer_submit`), nullable owner user. **No `isFraud` / label column.**
- [ ] `fraud_predictions`: foreign keys to `transactions` and `model_versions`; `fraud_probability`, `risk_tier` (`APPROVE` / `REVIEW` / `HIGH_RISK`), the two thresholds used, `features` (JSONB), `inference_ms`, and **two timestamps for the latency measurement**: `event_ingested_at` and `decision_written_at`. **Unique on `(transaction_id, model_version)`.**
- [ ] `model_versions`: version string (primary key), algorithm, hyperparameters (JSONB), library versions (JSONB), `feature_schema_version`, thresholds, metrics (JSONB), artifact path, created timestamp.
- [ ] `audit_logs`: links to a prediction and an actor; `review_status` is the **only** column that may ever be updated.
- [ ] `fraud_predictions`, `audit_logs`, `model_versions`, `etl_runs` have no update or delete code path (`audit_logs.review_status` excepted). Stretch: revoke UPDATE/DELETE from the application DB role, or add triggers, and show it in the PR.
- [ ] `investigation_notes` and `watchlist` match README 5.13 (notes linked to a transaction and an author; watchlist with account, status, reason, who added it).
- [ ] `alembic upgrade head` on an empty database creates everything; `alembic downgrade base` removes it.
- [ ] A dev-only seed script creates the three roles and one user per role; passwords come from the environment, never hard-coded.
- [ ] `docs/ER_DIAGRAM.md` with a Mermaid ER diagram matching the migration.
- [ ] Field names for prediction fields match `docs/API_CONTRACT.md` section 5.

**Files likely touched:** `core-api/app/models/*.py`, `core-api/alembic/`, `core-api/scripts/seed_dev.py`, `docs/ER_DIAGRAM.md`.

**Depends on:** S1-02.

**How to test:**
```powershell
alembic upgrade head
# psql / any client: list tables, check unique (transaction_id, model_version)
alembic downgrade base; alembic upgrade head
python scripts/seed_dev.py
python -m pytest tests/test_models.py   # inserting a duplicate (transaction_id, model_version) must fail
```
The schema is also a shared file: this PR contains **only** models and the migration (CONTRIBUTING.md rule).

---

### S1-06 EDA notebook and four-way chronological split

**Assignee:** Bibek  **Labels:** `ml`, `etl`  **Branch:** `ml/eda-and-split`

**Goal:** answer the seven EDA gates in `docs/FEATURE_SPEC.md` section 7 with real numbers, and cut the PaySim data into train / validation / test / replay pool in chronological order.

**Acceptance criteria**
- [ ] `notebooks/01_eda_and_split.ipynb` runs top to bottom from the Parquet cache.
- [ ] Gates G1 to G7 each have their question, the computed numbers and the decision taken (using the rule written in the spec). **Label-conditioned gates (G2, G7) are computed on the train split only**; the cutoffs in the notebook's first cell are set before the first run and committed.
- [ ] The split is by **row position in the original order** (about 70 / 15 / 10 / 5 percent, README 7.1), each cut snapped to the start of a `step`, with the exact boundary row indexes saved to `docs/split_boundaries.json` (small file, committed).
- [ ] Asserted in the notebook: `step` is non-decreasing across the whole frame; the four ranges are contiguous, ordered and do not overlap; every row belongs to exactly one split.
- [ ] A table of row count, fraud count and fraud rate per split, **both over all rows and over `TRANSFER` + `CASH_OUT` only** (gate G6).
- [ ] The notebook never fits anything on validation, test or replay data.
- [ ] Gate results pasted into `docs/FEATURE_SPEC.md` section 9.

**Files likely touched:** `notebooks/01_eda_and_split.ipynb`, `docs/split_boundaries.json`, `docs/FEATURE_SPEC.md`.

**Depends on:** none (uses `data_loader.py` and the existing Parquet cache).

**How to test:** restart the kernel and run all cells twice; `docs/split_boundaries.json` must be identical both times.

---

### S1-07 Auth: login, logout, Redis-backed server-side sessions, bcrypt

**Assignee:** Member B  **Labels:** `core-api`  **Branch:** `core-api/auth-sessions`

**Goal:** login and logout with real server-side sessions: the cookie is only an opaque ID, the data is in Redis, and the three spec behaviours (regeneration on login, timeout, proper logout) are demonstrably true.

**Acceptance criteria**
- [ ] The session cookie holds **only a random session ID** (`HttpOnly`, `SameSite=Lax`, `Secure` switchable by a setting for HTTPS). Session data (user id, role) is in Redis under that ID with a TTL.
- [ ] **Do not use Starlette's built-in `SessionMiddleware`**: it stores the data in the cookie. Use `starsessions` with its Redis store (it has `regenerate_session_id`), or a small custom middleware. Record the choice and why in the PR description (viva material).
- [ ] **Regeneration:** a new session ID is issued on successful login; the old ID no longer works (test).
- [ ] **Timeout:** idle timeout comes from settings (default documented in `.env.example`); an expired session is rejected (test with a very short timeout).
- [ ] **Logout:** deletes the Redis key and clears the cookie; replaying the old cookie fails (test).
- [ ] Passwords hashed with bcrypt. `passlib 1.7.4` is reported to break with `bcrypt` 4.1 and newer (`AttributeError`/`ValueError`), so pin a compatible version (reports suggest `bcrypt==4.0.1`) or call `bcrypt` directly; **verify with the login test** and record the pin in `requirements.txt`.
- [ ] Wrong password and unknown email give the same generic error. Inactive and soft-deleted users cannot log in.
- [ ] State-changing requests are protected against CSRF (SameSite plus a token or an Origin check); describe the approach in the PR.
- [ ] Self-registration route creates a **Customer** only.
- [ ] `GET /whoami` returns the current user's id and role, or 401 (used by tests and the nav).
- [ ] Tests run against Redis (compose Redis or a fake) and cover every behaviour above.

**Files likely touched:** `core-api/app/routers/auth.py`, `services/auth.py`, `services/sessions.py`, `core-api/tests/test_auth.py`, `requirements.txt`.

**Depends on:** S1-05 (users table).

**How to test:**
```powershell
python -m pytest tests/test_auth.py
# manual: log in, copy the cookie value, log out, then replay the old cookie with
Invoke-RestMethod http://localhost:8000/whoami -Headers @{Cookie="session=<old value>"}   # expect 401
docker compose exec redis redis-cli keys "*"    # the session key exists after login, gone after logout
```

---

### S1-08 Login and registration pages

**Assignee:** Member C  **Labels:** `frontend`  **Branch:** `frontend/login-pages`

**Goal:** login and registration pages that give instant client-side feedback and use an asynchronous (Fetch) request, as the spec's scripting requirements ask.

**Acceptance criteria**
- [ ] `login.html` and `register.html` extend `base.html` (S1-03).
- [ ] Client-side validation before sending: required fields, email format, password rules agreed with B; messages shown next to the field.
- [ ] Form submits with `fetch`; success redirects by role (Admin, Fraud Analyst, Customer landing pages can be placeholders); failures (401, 422, 500) show a readable message without a page reload.
- [ ] Registration creates a Customer only; the page does not offer a role choice.
- [ ] Logout control in the nav.
- [ ] Works at 360 px; labelled inputs; no password shown in URL, console or page source.
- [ ] While S1-07 isn't merged, runs against a mock endpoint; switching to the real one is a one-line change noted in the PR.

**Files likely touched:** `core-api/app/templates/login.html`, `register.html`, `static/js/auth.js`.

**Depends on:** S1-03 (can mock until S1-07 merges).

**How to test:** submit empty, malformed and valid forms; check each error message; run once against the mock and once against the real endpoint after S1-07 merges; attach screenshots at both widths.

---

### S1-09 Run the shared feature function on the real data and freeze the schema

**Assignee:** Bibek  **Labels:** `ml`, `etl`  **Branch:** `ml/features-real-data`

**Goal:** prove on the real PaySim data that training and streaming features are identical, measure the cost, and freeze `feature_schema_version` at `1.0.0`.

**Acceptance criteria**
- [ ] Peak memory and run time measured on the first 1M real rows, then on the full pass; numbers written in `docs/FEATURE_SPEC.md` section 6.
- [ ] Features for all scored rows are cached as `data/cache/features_v<version>.parquet` (gitignored).
- [ ] **Parity on real data:** state primed at the replay-pool boundary for the recipient accounts of the replay pool reproduces the batch features with a maximum absolute difference of exactly `0.0`.
- [ ] The same parity test passes against the **real Redis-backed store** once it exists (until then, against the JSON stand-in).
- [x] Gate G2 failed (5 Nov 2026): features 11 to 14 were dropped; the schema is now `0.2.0` with 12 features, already changed in `FEATURE_SPEC.md` and `shared/features/` together. Priming needs recipient accounts only.
- [ ] `FEATURE_SCHEMA_VERSION` set to `1.0.0` and gate results filled in.

**Files likely touched:** `shared/features/`, `docs/FEATURE_SPEC.md`, `notebooks/02_features.ipynb`, `tests/`.

**Depends on:** S1-06.

**How to test:** run `python -m pytest`, then the real-data parity cell in `notebooks/02_features.ipynb`; the printed maximum difference must be `0.0`.

---

### S1-10 `require_role`, ownership checks and access-control tests

**Assignee:** Member B  **Labels:** `core-api`  **Branch:** `core-api/rbac-and-access-tests`

**Goal:** server-side role enforcement on every protected route, proven by a test that tries each role against each route, so the hand-test an examiner will do (log in as Customer, edit the URL) is already automated.

**Acceptance criteria**
- [ ] `require_role(*roles)` dependency: no session gives 401 (HTML routes redirect to login, JSON routes return 401); wrong role gives 403.
- [ ] Ownership helper: a Customer can read only transactions whose owner is their own user id; another customer's id gives 403 or 404 (pick one, document it).
- [ ] A user deactivated or soft-deleted while logged in is rejected on the next request.
- [ ] Stub protected routes exist so tests have something to hit: `/admin/users`, `/analyst/predictions`, `/customer/transactions` (minimal pages).
- [ ] **Table-driven test:** every route × {anonymous, customer, analyst, admin} with the expected status. The test **fails if any non-public route is missing from the table**, so new routes can't be added unprotected.
- [ ] Permission matrix matches README 5.10.

**Files likely touched:** `core-api/app/deps.py`, `routers/`, `core-api/tests/test_access_control.py`.

**Depends on:** S1-07.

**How to test:**
```powershell
python -m pytest tests/test_access_control.py -v
# manual: log in as Customer, open /admin/users in the browser -> 403
```

---

### S1-11 Baseline models and the metrics table (Logistic Regression + rule baselines)

**Assignee:** Bibek  **Labels:** `ml`  **Branch:** `ml/baseline-models`

**Goal:** the first real results: a Logistic Regression baseline and the three rule baselines on the same test rows, with and without the balance-consistency feature group. (Added because TASKS.md says Sprint 1 ends with "a baseline model with a metrics table" but no Sprint 1 row produces it.)

**Acceptance criteria**
- [ ] `notebooks/03_baseline_models.ipynb` trains Logistic Regression (`class_weight='balanced'`, fixed `random_state`) on the train split only; the scaler is fitted on train only and saved inside the artifact (FEATURE_SPEC D9).
- [ ] Hyperparameters chosen on the validation split. **The test split is evaluated once, at the end.**
- [ ] Rule baselines R1, R2, R3 exactly as defined in `docs/FEATURE_SPEC.md` section 6.1, computed on the same test rows.
- [ ] Results table: precision, recall, F1, PR-AUC (models only), confusion matrix; one version with all features and one **without the balance-consistency group**.
- [ ] Every metric states its denominator (all rows vs `TRANSFER` + `CASH_OUT`) **and the fraud base rate of the split it was computed on** (rates differ strongly between splits, so PR-AUC and precision are not comparable across them).
- [ ] R1 is reported as supplied; it fires on only 16 rows in the whole dataset, so expect near-zero recall.
- [ ] The artifact stores: feature names in order, `feature_schema_version`, the two tier thresholds (chosen on validation), library versions, `random_state`.
- [ ] Artifacts in `data/models/` (gitignored); the table and a short interpretation committed under `docs/results/`.

**Files likely touched:** `notebooks/03_baseline_models.ipynb`, `docs/results/baseline_metrics.md`, `shared/` (only if a feature bug is found, via its own PR).

**Depends on:** S1-09.

**How to test:** restart and run all; the metrics table reproduces exactly (fixed seed). A teammate checks that no test-split row is used before the final evaluation cell.

---

## Sprint 1 is done when

- All three run `docker compose up --build` and reach `/health` (S1-04).
- You can log in as Admin, Analyst and Customer and each sees only their own pages (S1-07, S1-08, S1-10).
- The baseline model exists with a metrics table (S1-11).

**Your pinned reminder:** the NEPSE data-source decision is still open. It comes up when the Flow A workers run, which is after Sprint 1.
