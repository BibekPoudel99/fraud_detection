# Project Context — Paste This Into a New Chat

*Purpose: give a fresh conversation everything it needs to continue this project without re-explaining background. Paste this file's contents (or upload it alongside README.md and data_loader.py) at the start of a new chat.*

*Last updated: 5 Nov 2026 (EDA notebook run on real data; gate G2 failed, so features 11 to 14 dropped and schema is now 0.2.0; detection-scope wording changed with Bibek's approval; split boundaries saved in `docs/split_boundaries.json`).*

---

## Who / what / where

Bibek, a BIT (Bachelor of Information Technology) student at **Himalayan Whitehouse International College** (affiliated with **Purbanchal University**), Kathmandu, Nepal. Final-year capstone: **Apprentice Project (BIT453CO)**, **Track B — AI/ML Integrated Application**.

## Status: proposal stage is DONE

- **Title: LOCKED** — "Real-Time Financial Transaction Monitoring and Fraud Risk Assessment: An Integrated Decision-Support Platform for Nepal's Digital Payment Ecosystem"
- **Proposal: DEFENDED** with the supervisor.
- **Backend framework confirmed with supervisor: FastAPI only — no Flask.** The spec allows deviation from its listed technologies with supervisor approval; this has been obtained explicitly.
- **Architecture: LOCKED** (see README.md Section 5 — "Locked Architecture Decisions," written in ADR style with rationale, for reuse in the viva).

**The current project is now moving from proposal/design into implementation.** Any new chat should treat the README.md as the source of truth for what's already decided, and focus on helping build it, not re-deciding it, unless Bibek explicitly reopens a decision.

## Deliverables that exist right now (attach/reference these)

1. **`README.md`** — the single authoritative, current project document. Contains: abstract (with precise fraud-detection scope statement), problem statement, literature review (7 verified sources), objectives, a full "Locked Architecture Decisions" section (Section 5) with rationale for each choice, full data-flow diagrams (3 flows: PaySim replay, NEPSE live, batch upload), the Parquet-caching utility (Section 6), datasets with links (Section 7), model selection & imbalance handling (Section 8), evaluation plan, limitations, and two-part future work (near-term + production path). **Read this before answering any project question — it supersedes any earlier draft or earlier chat's description of the architecture.**
2. **`data_loader.py`** — standalone, working Python utility implementing Parquet caching for the PaySim CSV (reads CSV once, caches as Parquet, loads from cache on subsequent runs). Syntax-verified. Ready to drop into the repo as-is; imported via `from data_loader import load_paysim`.
3. **`project-comparison-verified.md`** — historical document from the domain-selection stage (Fraud Detection vs. Agriculture). Superseded by README.md for anything it contradicts; useful only for the reasoning trail behind why fraud detection was chosen.
4. **`docs/API_CONTRACT.md`** — the `/predict` request/response contract between `core-api`/workers and `inference-service` (named feature object, `feature_schema_version` check, tier thresholds returned by the service, error and retry rules, mock server for Members B and C). Draft v1.0, pending review.
5. **`docs/FEATURE_SPEC.md`** — column-by-column feature spec, 12 features (schema 0.2.0; four origin-side chain features dropped after gate G2), FIU-Nepal red-flag mapping (only one of five partly representable), the single shared feature function (`compute_features` / `update_dest_state`), state and priming rules, seven EDA gates with pre-registered decision rules, rule baselines R1–R3. Draft 0.2 (schema `0.2.0`, frozen as `1.0.0` after the real-data parity run, S1-09). Gate results G1 to G7 recorded in section 9.
6. **`docs/SPRINT1_ISSUES.md`** — 12 ready-to-paste GitHub issue cards (S1-00 to S1-11).
7. **Shared code bundle** (`shared/schemas/predict.py`, `shared/features/`, `tools/mock_inference.py`, `tests/`) — written to accompany the two specs; 29 tests pass on synthetic data; the mock-server test has not been run yet. Lands in the repo via issue S1-01.

## Literature — verification status (all confirmed real, do not re-litigate)

| Source | Status |
|---|---|
| FIU-Nepal (2024), *Cyber Enabled Fraud Strategic Analysis Report* | ✅ Verified |
| Shakya (2018), MSc thesis, UNLV | ✅ Verified |
| Pant et al. (2026), Islington Journal of Multidisciplinary Research | ✅ Verified via direct link |
| Gautam (2026), Kathmandu University student paper | ✅ Verified — full PDF read. NOT peer-reviewed; cite as architectural precedent, not performance authority |
| Timalsina et al. (2026), IJST 3(1) | ✅ Verified — small/new journal, supporting evidence only |
| Hajek, Abedin & Sivarajah — XGBoost mobile-payment framework | ✅ Standard precedent |
| BIS Project Hertha | ✅ Standard precedent |

**Process note:** small Nepal journals (IJMR, IJST) and student ResearchGate uploads don't surface reliably via general search — don't re-flag sources as fabricated on search-silence alone if Bibek has supplied a direct link/PDF; verify from what he provides first.

## Datasets — final, confirmed, do not re-litigate

- **PaySim** — https://www.kaggle.com/datasets/ealaxi/paysim1 — the only labeled dataset; carries 100% of supervised training/evaluation. 6,362,620 txns, 8,213 fraud (~0.13%). Fraud label only ever appears on `TRANSFER`/`CASH_OUT` — detection scope is narrowly **account-takeover, transfer-then-cash-out fraud**, not fraud in general. Synthetic, non-Nepalese.
- **NEPSE Floorsheet** — https://github.com/surajrimal07/NepseAPI-Unofficial, hosted at `https://nepseapi.surajrimal.dev` — real, live Nepali stock-trade data. No fraud labels. Used only as a live real-time ingestion demo through a separate statistical anomaly layer — never trains or tests the PaySim classifier (different schema, different domain). **OPEN ITEM (see pinned section below): the hosted API returned Cloudflare 522 on every endpoint Bibek tested, so the data source is undecided.**
- **Ruled out:** Kaggle "Bank and Financial Institutions Dataset of Nepal" — confirmed to be an NRB branch/institution directory, not transaction data.

## Architecture — fully locked, do not re-litigate unless Bibek reopens it

All below are final decisions with rationale documented in README.md Section 5:

- **One framework (FastAPI), two services:** `core-api` (auth, RBAC, CRUD, dashboards, uploads, orchestration) and `inference-service` (loads model once, exposes `/predict` only) — communicating over internal HTTP. This satisfies spec Section 5.4's "server-side endpoint/service the web app calls."
- **Auth: server-side sessions**, not JWT — an opaque random session-ID cookie with all session data in Redis (same Redis used for streaming), `passlib[bcrypt]` for hashing with a compatible `bcrypt` pin. Starlette's built-in `SessionMiddleware` is deliberately **not** used: its docs describe signed cookie-based sessions (data lives in the client's cookie), which cannot be revoked server-side. The store is `starsessions` (Redis) or an equivalent small custom middleware. Chosen because the spec's wording ("session regeneration, timeout, logout") describes session semantics literally. *(Mechanism corrected 2 Nov 2026; the decision itself is unchanged.)*
- **Presentation:** Jinja2-rendered HTML + vanilla JS (Fetch API) + native FastAPI WebSocket for live dashboard push. No separate SPA/React frontend — deliberately, to avoid unnecessary build complexity for a 3-person team.
- **ORM:** SQLAlchemy 2.0 async + `asyncpg`, migrations via Alembic.
- **Validation:** Pydantic v2 schemas reused across three entry points — API requests, CSV upload rows, and stream events — so validation logic is provably identical everywhere.
- **Streaming workers run as separate long-lived processes** (own Docker Compose services), NOT FastAPI `BackgroundTasks` — this is a correctness decision (background tasks are request-lifecycle-bound, unsuitable for indefinite stream consumption), not a style choice.
- **Three data flows, kept explicitly separate everywhere** (diagrams, objectives, evaluation — never conflate these in writing or in the viva):
  - **Flow A** — PaySim replay pool → Redis Streams → feature engineering (chronological order, no leakage) → `inference-service` → decision → logged → analyst review. **Graded, evaluated core.**
  - **Flow B** — NEPSE live floorsheet → same Redis Streams pattern → statistical/rule-based anomaly flags (NOT the PaySim model, no ML). **Architecture-proof only; qualitative evaluation, no ground truth.**
  - **Flow C** — Manual CSV upload → batch scoring via the same trained model as Flow A. **Explicitly NOT part of the real-time claim** — satisfies the spec's compulsory file-upload requirement.
- **PaySim four-way split:** Train (~70%) / Validation (~10–15%) / Test (~10%, source of all reported metrics) / **Replay pool** (~5%, dedicated, held-out, feeds Flow A — kept separate from Test so live-demo numbers and formally-reported numbers come from disjoint data; both pipelines compute features with the same shared function, and primed replay features equal the batch features exactly — `docs/FEATURE_SPEC.md` D6).
- **Chronological replay is mandatory:** replay pool streams in original PaySim `step` order; rolling features computed only from state seen so far in the stream — never precomputed in batch ahead of time (would silently leak future information into a "real-time" feature).
- **Models:** Logistic Regression (baseline, `class_weight='balanced'`) vs. Random Forest (`class_weight='balanced'` or SMOTE on train split only) vs. XGBoost (`scale_pos_weight`) — full rationale and comparison table structure already in README Section 8. **Plus rule baselines R1–R3** as extra comparison rows (R1 = PaySim's own `isFlaggedFraud` rule; R2 = account drained; R3 = drained and amount above 200,000, a figure borrowed from R1, not tuned) — defined in `docs/FEATURE_SPEC.md` section 6.1 and fixed before the test split is read.
- **Scope gate:** only `TRANSFER` and `CASH_OUT` transactions are scored; other types are not sent to `/predict`. Metrics state their denominator (all rows vs. scoped rows).
- **"Real-time" framing — locked, precise language for the report:** *"The prototype performs near-real-time transaction monitoring by ingesting individual transaction events through a streaming layer and producing a fraud-risk decision during the transaction-processing workflow, with end-to-end decision latency measured empirically on the deployed system."* Never claim production throughput, sub-millisecond latency, or uptime SLAs.
- **Detection scope — locked, precise language:** fraud transactions of type TRANSFER and CASH_OUT as labelled by PaySim, which simulates account-takeover fund-draining; the two legs are not linked at the account level in the dataset (EDA gate G2), so the features do not model the chain — not fraud detection in general. (Reworded 5 Nov 2026, approved by Bibek.) NEPSE side is "illustrative market-activity anomaly flagging," never called "fraud detection."
- **Claim wording — locked 2 Nov 2026:** the platform is demonstrated on PaySim's TRANSFER and CASH_OUT fraud labels using synthetic data. Results show the pipeline works; they are not evidence about fraud in Nepali mobile-banking or wallet traffic. Applicability to Nepali traffic needs a real Nepali dataset and a model trained on it (future work, README 11.1 item 6).
- **Title decision already made and closed:** "Real-Time..." kept over "Smart..." — "smart" was rejected as a content-free word inviting an unanswerable viva question; "real-time" is earned and defensible given the architecture above. Do not revisit unless Bibek raises it again.

## Local development utility — built

`data_loader.py` (Section 6 of README, also a standalone file) — reads the PaySim CSV once, writes a local Parquet cache, loads from Parquet on every subsequent run. Development-speed convenience only; explicitly not part of the real-time architecture or model results. **Run successfully against the real CSV:** shape (6362620, 11), dtypes int64 / category / float64 / str / int8.

## Future-work / production path — already drafted (README Section 11.2)

Includes: the verified NRB Regulatory Sandbox pathway (guidelines effective 14 May 2026, real and current, allows licensed institutions/fintechs to pilot AI/ML products under supervision); the push-vs-pull ingestion shift (bank's core banking system pushes events to us vs. our current pull-based replay/poll); synchronous in-line scoring as a distinct future phase with a different latency budget than "near-real-time monitoring"; infrastructure hardening (Kafka/Redpanda cluster, feature store, horizontally scaled inference); schema adaptation to ISO 20022/8583; compliance (STR/SAR reporting format, KYC/AML, data localization); MLOps (model registry, drift detection, canary deployment); SHAP/LIME explainability; active-learning feedback loop from analyst overrides; security hardening (no direct internet exposure, federated IAM, secrets management); scale validation at real bank transaction volumes including seasonal peaks.

## Ruled out / not chosen (closed decisions, don't revisit)

- **Agriculture Yield Forecasting for Nepal** — strong runner-up, grounded in a verified NRB Economic Review paper (Dhakal & Dhungana, 2025). Documented as fallback in `project-comparison-verified.md` only.
- **Credit Risk & Loan Decisioning**, **Open Banking/Financial Intelligence Platform** — evaluated and deprioritized early.
- **Kaggle "Bank and Financial Institutions Dataset of Nepal"** — confirmed not transaction data.
- **Flask** — ruled out once supervisor confirmed FastAPI-only is acceptable.
- **JWT auth, separate SPA frontend, single-service (merged) architecture, FastAPI BackgroundTasks for streaming** — all considered and explicitly rejected in favor of the locked decisions above, with reasoning recorded in README Section 5.

## Progress tracker — what's done vs. what's next

**Done:**
- [x] Domain selected (Fraud Detection over Agriculture) with feasibility analysis
- [x] Literature reviewed and independently verified (7 sources)
- [x] Datasets selected and verified (PaySim + NEPSE), one candidate ruled out (Kaggle branch directory)
- [x] Title locked
- [x] Proposal defended with supervisor
- [x] Backend framework decision confirmed with supervisor (FastAPI only)
- [x] Full architecture locked, with rationale documented (Section 5 of README)
- [x] Detection scope precisely defined (PaySim-labelled TRANSFER and CASH_OUT fraud only; reworded 5 Nov 2026 after G2)
- [x] "Real-time" claim precisely defined and defensible (mechanism + measured-latency framing)
- [x] Parquet-caching data-loading utility built and run successfully on the real PaySim CSV
- [x] GitHub repo created and shared with collaborators; scaffold, CONTRIBUTING.md and `docs/TASKS.md` written
- [x] CRUD, delete, search and pagination decisions locked (README 5.13/5.14)
- [x] `docs/API_CONTRACT.md` drafted (30 Oct 2026)
- [x] `docs/FEATURE_SPEC.md` drafted with shared feature function and tests (30 Oct 2026; baselines added 2 Nov)
- [x] Sprint 1 issue cards written, `docs/SPRINT1_ISSUES.md` (2 Nov 2026)
- [x] Claim wording, scope gate and rule baselines locked (2 Nov 2026)
- [x] Session mechanism corrected in README 5.2 (2 Nov 2026)
- [x] EDA notebook built and run on the real data (5 Nov 2026): G1 to G7 recorded, split saved. **G2 failed: features 11 to 14 dropped, schema 0.2.0.** Finding: base rates differ strongly between splits (replay pool 2.07%); R1 fires on only 16 rows.

**Not yet done — next steps, roughly in order:**
1. **NEPSE data source decision** — see the pinned section below. Non-blocking for Flow A.
2. Merge the contracts and shared code (issue S1-01); run `tests/test_mock_inference.py` on a real machine (never run yet).
3. Full ER diagram / database schema (SQLAlchemy models) for `users`, `roles`, `transactions`, `fraud_predictions`, `model_versions`, `audit_logs`, `etl_runs`, `investigation_notes`, `watchlist` (sessions live in Redis) — issue S1-05.
4. **Next: S1-09.** Run the 0.2.0 feature function on the real data (parity test on the real replay pool, peak memory) and freeze `feature_schema_version` at `1.0.0`. (EDA/split S1-06 is done.)
5. Model training notebook: baseline + Random Forest + XGBoost on PaySim, with the four-way split, imbalance handling per model, rule baselines R1–R3, with-and-without the balance-consistency feature group, and the full evaluation-metrics table (baseline part is S1-11).
6. `inference-service` FastAPI app: load trained model artifact, `/predict` endpoint, Pydantic request/response schemas (`shared/schemas/predict.py`).
7. `core-api` FastAPI app: auth (session + Redis), RBAC, CRUD entities, dashboards (Jinja2), file upload (Flow C), WebSocket push endpoint.
8. Streaming worker processes: PaySim replay producer, PaySim fraud-consumer, NEPSE ingestion producer, NEPSE anomaly-consumer.
9. `docker-compose.yml` wiring all services together (`core-api`, `inference-service`, 4 workers, `postgres`, `redis`, `nginx`).
10. Latency measurement/logging implementation for the real-time claim (timestamps at ingestion and at decision-write).
11. Full APA-formatted proposal/report document (README.md has the content, not yet in submission format).
12. Keep a regular commit history from this point forward (spec Section 3.8 requirement). The repo itself exists already.

## Team and ownership (see `docs/TASKS.md` for the full split and Sprint 1)

- **Bibek — lead.** Owns ML (training, evaluation), the ETL pipeline, `inference-service`, workers, and infrastructure (Docker, compose, nginx). Assigns tasks to the other two as GitHub Issues.
- **Member B — backend and security.** `core-api` skeleton, DB models + Alembic, auth/sessions, RBAC, Users CRUD, audit-log writer, access-control tests.
- **Member C — features and frontend.** Jinja2 layout and CSS, login and customer pages, Notes and Watchlist CRUD, later dashboards, WebSocket view, CSV upload UI, export.
- No fixed dates yet; work started from the day this was written.

## Locked CRUD / list decisions (README 5.13, 5.14)

- **User delete is hybrid:** hard delete for accounts with no activity; soft delete (`deleted_at`, login disabled, record retained, UI says so) for accounts with activity.
- **Search/filter** on the user list, notes list, watchlist and prediction log.
- **Pagination** on those same four lists.
- **Customer role has no CRUD entity.**
- `fraud_predictions`, `audit_logs`, `model_versions` and `etl_runs` stay append-only by design.
- **Self-registration creates Customer accounts only** (default assumed in the Sprint 1 cards; Admin and Analyst accounts are created by an Admin).

## PINNED OPEN ITEM — NEPSE data source (do not let this drop)

Bibek asked to be reminded about NEPSE when it becomes relevant and not to forget it while other work proceeds. **Any assistant reading this file should raise it** when the Flow A workers (PaySim replay producer/consumer) are running, or before any Flow B work begins.

- **State:** the hosted API (`nepseapi.surajrimal.dev`) returned Cloudflare 522 on `/health`, `/Summary` and `/Floorsheet` — origin is down. The official site (nepalstock.com) was suggested as an alternative; scraping it has not been tested.
- **Options:** (1) self-host `basic-bgnr/NepseUnofficialApi`, timeboxed to 2–3 days; (2) replay historical floorsheets (e.g. `suyogdahal/nepse-data`) as a stand-in feed; (3) retry the hosted API.
- **Consequence:** README Flow B still describes a "live" feed and must be reworded once he chooses.

## Working style / preferences established in this project

- Bibek wants **every factual/citation claim independently verified**, not taken on faith — including claims from other AI assistants or earlier drafts. Report verification failures as "unconfirmed," not "fabricated," unless there's strong positive evidence of fabrication — two Nepal-specific papers were nearly wrongly dropped before direct links confirmed them as genuine.
- Prefers **precise, defensible claims over impressive-sounding ones** — e.g., "near-real-time, measured empirically" rather than "real-time" unqualified; narrow, accurate detection-scope language rather than "fraud detection" unqualified.
- Comfortable with genuine technical ambition (event-driven streaming architecture, multi-service FastAPI setup) as long as it's honestly scoped, buildable by a student team, and every design choice has a stated rationale — treat architecture decisions as things to be defended in a viva, not just implemented.
- Once a decision is locked (title, framework, architecture), treat it as closed unless Bibek explicitly reopens it — don't re-litigate settled choices in new chats.
