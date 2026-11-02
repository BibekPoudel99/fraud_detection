# Real-Time Financial Transaction Monitoring and Fraud Risk Assessment
### An Integrated Decision-Support Platform for Nepal's Digital Payment Ecosystem

**Apprentice Project (BIT453CO) — Track B: AI/ML Integrated Application**
Department of Information Technology, Himalayan Whitehouse International College (Purbanchal University)

**Status: Title locked. Proposal defended. Architecture locked (this document).**

---

## 1. Abstract

Nepal's digital payment ecosystem — led by platforms such as eSewa and IME Pay, and accelerated by NRB's QR-interoperability initiatives — has grown rapidly, with mobile banking transaction volume growing by over 40% year-on-year in 2024. Nepal Rastra Bank's Financial Intelligence Unit (FIU-Nepal) has documented that a majority of fraud-related suspicious transaction reports received through 2024 were cyber-enabled, and has explicitly recommended risk-based, real-time transaction monitoring. Recent Nepal-specific research (Gautam, 2026; Pant et al., 2026; Timalsina et al., 2026) confirms growing academic interest in AI-based fraud detection for Nepal, but each contribution is either a standalone model, a conceptual readiness framework, or an early-stage architecture — none is packaged as a complete, auditable, multi-tier web application with human review and persistent prediction logging.

This project designs and implements such a system: a role-based, three-tier transaction-monitoring platform, built entirely on FastAPI, that trains and compares supervised machine-learning models on a labeled transaction dataset (PaySim), exposes the best model through a real-time, event-driven inference pipeline with measured end-to-end latency, logs every prediction for auditability, and routes suspicious transactions to a human fraud analyst for review. A batch/on-demand upload pathway allows an analyst to score an uploaded transaction file outside the live stream. A secondary, architecturally-separate module demonstrates the same real-time ingestion pipeline operating on a genuine live Nepali data source — the NEPSE stock exchange floorsheet — using lightweight statistical anomaly detection, to validate that the streaming architecture functions on real external data rather than only on replayed historical records.

**Detection scope, stated precisely:** this system detects **account-takeover-style fund-draining fraud, evidenced by a transfer-then-cash-out pattern** — the specific pattern PaySim's `isFraud` label represents (labels only ever appear on `TRANSFER` and `CASH_OUT` transactions), which corresponds closely to a red flag FIU-Nepal explicitly documents ("transfers followed by immediate withdrawals"). It does not detect card-present fraud, merchant/POS fraud, loan fraud, money-laundering networks, or synthetic identity fraud.

---

## 2. Problem Statement

The rapid growth of digital payments in Nepal has increased the volume and complexity of transaction data that financial institutions must monitor for fraud. FIU-Nepal's *Cyber Enabled Fraud Strategic Analysis Report (2024)* documents specific behavioral red flags in Nepal's fraud landscape — multiple accounts opened under one identity, rapid transactions shortly after account opening, transfer-then-immediate-withdrawal patterns, transaction behavior inconsistent with the account holder's economic profile, and geographic/device anomalies — and explicitly recommends that payment-system participants adopt risk-based, real-time transaction monitoring.

Existing responses fall into two categories, both limited. Static rule-based engines are interpretable but rigid, generating high false-positive rates as transaction volume and diversity scale (Gautam, 2026). Isolated machine-learning models, where studied (Shakya, 2018; Timalsina et al., 2026), are more adaptive but are evaluated as standalone classifiers, disconnected from an auditable, human-reviewed operational system. Pant et al. (2026) further argue that global AI fraud-detection approaches cannot be transferred to Nepal without addressing data fragmentation, limited data maturity, and weak explainability practices — meaning a Nepal-appropriate system must prioritize transparency and human oversight, not just predictive accuracy.

**There remains a need for an integrated, auditable, multi-tier application** that combines transaction ingestion, machine-learning risk scoring, human analyst review, persistent prediction logging, and model versioning within a single working prototype — rather than a notebook, a conceptual framework, or an isolated classifier.

---

## 3. Literature Review — Aggregated & Verified

All sources below were independently verified (existence, authorship, and claims checked against the original source or publisher) before inclusion.

| # | Source | Context | Approach / Contribution | Gap this project addresses |
|---|---|---|---|---|
| 1 | **FIU-Nepal (2024)**, *Cyber Enabled Fraud Strategic Analysis Report*, Nepal Rastra Bank | Nepal — official regulator | Analyzes cyber-enabled fraud STR/SARs; identifies behavioral red flags; recommends real-time risk-based monitoring | Domain knowledge only — no system, no model, no application |
| 2 | **Shakya (2018)**, *Application of Machine Learning Techniques in Credit Card Fraud Detection*, MSc thesis, UNLV (Nepali author) | Nepali researcher; global credit-card dataset | Compares Logistic Regression, Random Forest, XGBoost; addresses severe class imbalance; argues for cost-sensitive evaluation | Offline classification only — no real-time system, no Nepal data |
| 3 | **Pant et al. (2026)**, *AI Fraud Detection and Financial Trust in Nepal's SME Payment Ecosystem: A Readiness Framework*, Islington Journal of Multidisciplinary Research | Nepal | Argues global AI fraud approaches assume data quality/interoperability/explainability conditions Nepal does not yet have | Conceptual/readiness study — no operational detection platform |
| 4 | **Gautam (2026)**, *Lightweight Multi-Agent Fraud Detection Framework for Digital Payments in Nepal*, Kathmandu University (student paper, not peer-reviewed) | Nepal digital-payment ecosystem | Five cooperative agents (Velocity, Geo, Behavior/Isolation Forest, Graph-inspired Risk, Synthesis); context-aware weighting; 4-tier OTP interlock; proposes Kafka+Redis production architecture | Evaluated only on 8,500 synthetic transactions, heuristic weights; explicitly calls for real transaction data as future work; no audit database, RBAC, or human-review application |
| 5 | **Timalsina, Sapkota, Rai & Ghimire (2026)**, *Enhanced Credit Card Fraud Detection*, IJST 3(1) | Nepal-authored | Behavioral features + SMOTE-ENN + LSTM/AdaBoost ensembles | Model-focused only — no application layer |
| 6 | **Hajek, Abedin & Sivarajah (2022/2023)**, XGBoost-based mobile-payment fraud framework | International, 6M+ transactions | Precedent for XGBoost + imbalance-aware methods at scale | Not Nepal-specific — technical precedent only |
| 7 | **BIS Project Hertha**, BIS & Bank of England | International — real-time payments | Institutional AI/analytics investigation into real-time payment financial-crime patterns | Institutional research prototype, not a student application |

### Research gap

> Existing Nepal-focused work provides official fraud typologies (FIU-Nepal), a readiness/transferability critique (Pant et al.), model-only classification studies (Shakya; Timalsina et al.), and one early-stage synthetic-data multi-agent architecture (Gautam). None combines transaction ingestion, ML-based risk scoring evaluated against ground-truth labels, persistent audit logging, model versioning, and human-analyst review within one deployable multi-tier application — which is precisely what this project delivers.

---

## 4. Objectives

1. Design and implement a secure three-tier web application — presentation, application/business logic, and PostgreSQL data tier — built entirely on **FastAPI**, with role-based access control across three roles: **Admin**, **Fraud Analyst**, and **Customer**.
2. Build a reproducible ETL and feature-engineering pipeline on the PaySim dataset, with behavioral features informed by FIU-Nepal's documented red flags.
3. Train and compare a baseline (Logistic Regression) against Random Forest and XGBoost for fraud classification under severe class imbalance, using a documented, leakage-free train/validation/test/replay-pool split.
4. Evaluate all models using precision, recall, F1-score, PR-AUC, and a confusion matrix; present a full model-comparison table.
5. Expose the best-performing model through a dedicated **inference microservice** (a second FastAPI service), called from the main application over internal HTTP, returning a fraud probability per transaction.
6. Build a Tier-2 real-time ingestion layer (Redis Streams, run as dedicated long-lived worker processes) that processes transaction events individually, in chronological order, computing rolling features only from stream state seen so far — and measure and report actual end-to-end decision latency.
7. Integrate the NEPSE floorsheet as a second, live Nepali data source through the same streaming pattern, scored by a lightweight statistical anomaly layer — architecturally and evaluatively separate from the PaySim classifier.
8. Build a batch/on-demand prediction pathway (CSV upload, validated, cached via a local Parquet layer for development performance).
9. Log every PaySim-model prediction in the relational database for full auditability, with session-based authentication satisfying the spec's login/logout/session-timeout requirements.
10. Build a fraud-analyst review workflow and an admin dashboard with live updates over WebSocket.
11. Honestly document system limitations throughout.

---

## 5. Locked Architecture Decisions

This section documents the concrete technical decisions made once the supervisor confirmed FastAPI may be used as the sole backend framework (no Flask). Each decision states the choice, the reasoning, and the main alternative considered — written this way deliberately, so it doubles as viva-defense material.

### 5.1 One framework, two services

**Decision:** the entire backend is FastAPI. Rather than one monolithic app, it runs as **two separate FastAPI services**:
- **`core-api`** — auth, RBAC, CRUD, dashboards, file upload, streaming orchestration.
- **`inference-service`** — loads the trained model artifact once at startup, exposes a single `/predict` endpoint, does nothing else.

**Why two services instead of one:** this directly satisfies the spec's Section 5.4 wording — "inference must be exposed through a server-side endpoint or service that the web application calls" — as a literal, demonstrable architecture rather than an internal function call inside one app. It also matches real production practice discussed in Section 9.2 (inference services scale and deploy independently of the main application, since model updates and traffic patterns differ from the rest of the app). Both services being FastAPI means one shared set of libraries, one shared Pydantic schema definitions package, and no framework-switching overhead — the "why two frameworks" complexity from the earlier Flask+FastAPI design is gone; this is "one framework, two processes," which is simpler.

**Alternative considered and rejected:** a single FastAPI app with inference as an internal module. Simpler to build, but weaker for the architecture diagram and doesn't demonstrate the client-calls-a-server-side-service pattern as concretely.

### 5.2 Authentication: server-side sessions, not JWT

**Decision:** session-based authentication, with session data stored in **Redis** (the same Redis instance already used for streaming — one piece of infrastructure serving two purposes), using Starlette's `SessionMiddleware` with a Redis-backed session store.

**Why:** the spec's security section explicitly requires "session regeneration on login, session timeout, and proper logout" — language that describes traditional server-side sessions specifically, not stateless tokens. JWT would require extra work to simulate the same guarantees (server-side revocation lists, refresh-token rotation) just to satisfy wording that server-side sessions already satisfy natively. Reusing Redis for sessions avoids introducing a third piece of infrastructure.

**Alternative considered and rejected:** JWT-based auth. More common in "pure API" FastAPI tutorials, but a worse fit for this spec's literal session-behavior requirements, and adds complexity (token refresh, revocation) without benefit here since there's no separate mobile client or third-party API consumer that would justify statelessness.

### 5.3 Presentation layer: server-rendered + Fetch/WebSocket, not a separate SPA

**Decision:** FastAPI serves HTML via `Jinja2Templates` for the role-based dashboards and forms; JavaScript (Fetch API) handles form submission, validation, and dynamic updates; a native **FastAPI WebSocket endpoint** pushes live updates to the Fraud Analyst / Admin dashboards as new predictions are logged.

**Why:** satisfies the spec's client-side scripting requirements (DOM manipulation, at least one async request, responsive layout) without the added build tooling and complexity of a separate React/Vue frontend, which would be extra overhead for a 3-person team on a fixed timeline. FastAPI's native WebSocket support (via Starlette) is a genuine advantage here — no extra library needed, unlike Flask which would require `Flask-SocketIO`.

**Alternative considered and rejected:** a fully separate JS frontend (React) consuming a pure JSON API. More modern-looking, but real added cost (build pipeline, CORS configuration, state management) for no requirement that actually needs it.

### 5.4 Data access: SQLAlchemy 2.0 (async) + Alembic

**Decision:** SQLAlchemy 2.0's async ORM with the `asyncpg` driver for PostgreSQL, migrations managed via Alembic.

**Why:** matches FastAPI's async-first design end to end (no blocking DB calls inside async route handlers), and Alembic gives you versioned, reviewable schema migrations — directly useful for demonstrating disciplined development process alongside your Git commit history (spec Section 3.8).

### 5.5 Validation: Pydantic v2, reused across three entry points

**Decision:** the same Pydantic schema classes validate (a) incoming API request bodies, (b) each row of an uploaded CSV in the batch-upload pathway, and (c) each transaction event pulled off a Redis Stream before feature engineering runs.

**Why:** one validation definition, three places it's enforced — avoids subtly different validation logic between the live stream, the batch upload, and the API, which would otherwise be an easy source of inconsistent behavior (and an easy question in the viva: "does your uploaded file get the same validation as a live transaction?" — the answer is now unambiguously yes).

### 5.6 Streaming consumers run as dedicated worker processes, not FastAPI background tasks

**Decision:** Redis Streams producers/consumers (PaySim replay producer, PaySim fraud-scoring consumer, NEPSE ingestion producer, NEPSE anomaly consumer) run as **separate long-lived Python processes**, started as their own Docker Compose services — not as FastAPI `BackgroundTasks`, which are tied to a request's lifecycle and unsuitable for continuous, indefinite stream consumption.

**Why:** this is a correctness issue, not a style preference — a FastAPI background task runs only in the context of a request/response cycle and is not designed for a process that needs to run forever, independently, and keep working even if no one is currently hitting the API. Running consumers as their own services is also what makes the "measured end-to-end latency" claim honest: the consumer is genuinely always listening, not spun up opportunistically.

### 5.7 Password hashing

**Decision:** `passlib` with the `bcrypt` scheme — unchanged from the original plan, framework-independent.

### 5.8 Updated architecture diagram

```
                              PRESENTATION TIER
                 Browser — Jinja2-rendered HTML + JS (Fetch/WebSocket)
                 Role-based dashboards: Admin | Fraud Analyst | Customer
                                      │
                                      ▼
                                   Nginx
                              (reverse proxy)
                                      │
                                      ▼
                     APPLICATION (BUSINESS LOGIC) TIER — all FastAPI
          ┌─────────────────────────────────────────────────────────┐
          │                     core-api  (FastAPI)                  │
          │  Session auth (Redis-backed) · RBAC · Routing             │
          │  Server-side validation (Pydantic) · CRUD                 │
          │  File upload handling · WebSocket push to dashboard       │
          └───────────────┬─────────────────────────┬─────────────────┘
                           │                         │  (internal HTTP)
                           ▼                         ▼
                     PostgreSQL              inference-service (FastAPI)
                    (DATA TIER, via              loads model.pkl once
                     SQLAlchemy async)           /predict endpoint only
              users, roles, txns,
              fraud_predictions,
              model_versions,
              audit_logs, etl_runs
                           ▲
                           │
              ┌────────────┴────────────┐
              │      Redis (shared)       │
              │  - Session store           │
              │  - Streams: transactions.  │
              │    paysim, transactions.   │
              │    nepse                   │
              └────────────┬────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
  worker: paysim      worker: paysim      worker: nepse
  replay producer      fraud consumer      ingestion + anomaly
  (asyncio, timed,     (feature eng. →     consumer (statistical
   chronological)       calls inference-    rules, no ML model)
                         service)
```

### 5.9 Data flows (unchanged in logic, updated in tech)

**Flow A — PaySim replay pool → supervised fraud scoring (core, real-time).** Replay worker (asyncio) → Redis Stream `transactions.paysim` → fraud-consumer worker (feature engineering, chronological, no leakage) → HTTP call to `inference-service` `/predict` → decision → write to `fraud_predictions` via `core-api`'s DB layer → WebSocket push to Fraud Analyst dashboard → review/override → `audit_logs`.

**Flow B — NEPSE live feed → statistical anomaly flagging (architecture-proof, real-time).** NEPSE ingestion worker (REST poll/WebSocket subscribe to `nepseapi.surajrimal.dev`) → Redis Stream `transactions.nepse` → anomaly-consumer worker (rolling z-scores, rule-based, no shared schema with PaySim) → anomaly flag → separate, clearly labeled "Market Activity" panel on Admin dashboard.

**Flow C — Manual CSV upload → batch scoring (on-demand, NOT real-time).** Analyst/Admin uploads CSV via `core-api` → Pydantic-row validation, graceful error handling → batch feature engineering → HTTP call to `inference-service` `/predict` (same model as Flow A) → scored report, tagged `source: batch_upload` if logged.

### 5.10 Roles and permission matrix

| Feature / Operation | Admin | Fraud Analyst | Customer |
|---|---|---|---|
| Manage user accounts | Yes | No | No |
| View/override fraud predictions | Yes | Yes | No |
| Submit a transaction | Yes | No | Yes |
| View own transactions only | No | No | Yes |
| View NEPSE live anomaly panel | Yes | Yes | No |
| Generate reports / view model logs | Yes | Yes | No |
| Upload transaction batch (CSV) | Yes | Yes | No |

### 5.11 Full technology stack (locked)

| Layer | Technology | Notes |
|---|---|---|
| Presentation | Jinja2 templates, HTML5/CSS3, JavaScript (Fetch API + native WebSocket) | Supervisor-approved single-framework decision means no separate frontend build |
| Reverse proxy | Nginx | |
| Application | **FastAPI** (`core-api`) | Confirmed with supervisor — replaces Flask entirely |
| Inference | **FastAPI** (`inference-service`), separate process | Loads model artifact once; never retrains per request |
| Auth | Starlette `SessionMiddleware`, Redis-backed session store, `passlib[bcrypt]` | Satisfies literal session-timeout/regeneration/logout spec wording |
| ORM / migrations | SQLAlchemy 2.0 (async, `asyncpg`), Alembic | Async end-to-end, versioned schema |
| Validation | Pydantic v2 | Shared across API requests, CSV rows, and stream events |
| Real-time bus | Redis Streams (`XADD`/`XREADGROUP`) | Also doubles as the session store (Section 5.2) |
| Stream workers | Standalone Python processes, own Docker Compose services | Not FastAPI background tasks — see Section 5.6 |
| Database | PostgreSQL | RDBMS per spec requirement |
| ML | scikit-learn (Logistic Regression, Random Forest), XGBoost | Baseline + 2 models, `scale_pos_weight` / `class_weight='balanced'` for imbalance |
| Model artifact | `.pkl` / `.joblib`, versioned | Loaded by `inference-service` at startup |
| Data caching (dev) | Local Parquet cache over the raw PaySim CSV (Section 6) | Development-speed only, no effect on results |
| Containerization | Docker / docker-compose | `core-api`, `inference-service`, 4 worker services, `postgres`, `redis`, `nginx` |
| Version control | Git, commits from day one | Notebooks committed alongside application code |

### 5.12 Access control enforcement — closing a specific spec test

Section 3.5 explicitly requires role checks enforced server-side, not simulated by hiding UI elements — and this is typically tested by hand (an examiner logs in as Customer, then edits the URL to try reaching an Analyst-only route). **Locked mechanism:** every protected route in `core-api` carries a FastAPI dependency, e.g. `Depends(require_role("analyst"))`, checked on every request before the handler runs — never inferred from what the frontend chose to render. The same dependency pattern enforces "Customer can view only their own transactions" (a per-user, not just per-role, restriction) by comparing the session's `user_id` against the requested resource's owner.

### 5.13 CRUD entities — chosen deliberately, not defaulted

Two of this project's most important tables — `fraud_predictions` and `audit_logs` — must be **append-only** to satisfy the project's own auditability claim; allowing arbitrary delete on these would undermine the "auditable prediction history" the whole design argues for. So the three CRUD entities satisfying Section 3.6 are chosen separately from these:

| Entity | Roles with full CRUD | Purpose |
|---|---|---|
| **Users** | Admin | Account management — create, edit (role, password reset, activate/deactivate), delete (see the delete rule below) |
| **Investigation Notes** | Fraud Analyst (own notes), Admin (all) | Case notes attached to a flagged transaction — create/edit/delete freely, since these are working notes, not the audit trail itself |
| **Watchlist / Flagged Accounts** | Admin, Fraud Analyst | Accounts placed under heightened scrutiny — full CRUD as accounts are added, updated, and removed from watch status |

`fraud_predictions`, `audit_logs`, `model_versions`, and `etl_runs` remain insert-only (with `audit_logs` additionally update-only on its review-status field) by design — an intentional choice, stated explicitly in the report, not an oversight.

**User delete rule (locked, hybrid):** because `fraud_predictions` and `audit_logs` reference users, a blanket hard delete would either break foreign keys or erase the audit trail. So:

- **Account with no activity** (no predictions, notes, watchlist entries or audit rows tied to it) → **hard delete**, row removed.
- **Account with activity** → **soft delete**: `deleted_at` is set, login is disabled, the record is retained, and the Admin UI states plainly that the account was deactivated rather than erased.

**Customer role:** has no CRUD entity of its own. Customers submit transactions and view their own results only (ownership-checked per 5.12).

### 5.14 Search/filter, pagination, and reporting

- **Search/filter:** on the transaction/prediction listing (Fraud Analyst and Admin dashboards) — by date range, risk tier (APPROVE/REVIEW/HIGH RISK), transaction ID, or flagged account. Also on the **user list** (name/email, role, status), the **investigation notes list** (text, author, linked transaction) and the **watchlist** (account, status, date added).
- **Pagination:** on the prediction log, the user list, the notes list and the watchlist (server-side, page-size capped).
- **Report/export:** Admin dashboard provides a filtered CSV/Excel export of predictions and a printable summary report (prediction counts, fraud rate, model-performance snapshot over a selected date range).

### 5.15 Secrets management

All credentials (database URL, Redis URL, session secret key, NEPSE API base URL) load via `pydantic-settings` from a `.env` file. `.env` is in `.gitignore` from the first commit; a `.env.example` with placeholder values is committed instead, so the repo never contains real secrets at any point in its history.

### 5.16 Reproducibility

Per spec Section 5.2: `random_state` is fixed and identical across every train/val/test/replay split and every model; a pinned `requirements.txt` (exact versions, not ranges) is committed alongside the training notebooks; each entry in the `model_versions` table stores the model's hyperparameters and library versions at training time, not just a filename — so any reported result can be traced back to the exact configuration that produced it.

### 5.17 Responsible-use disclaimer and sharpened bias statement

Per spec Section 5.5: every screen displaying a fraud prediction (Analyst dashboard, Admin dashboard, batch-upload report) carries a fixed, visible disclaimer: *"This is a probability-based decision-support estimate, not a fraud determination. All flagged transactions require human review before action is taken."* This is a UI requirement, implemented as a persistent banner component, not just report language.

**Bias statement, sharpened beyond "synthetic, not Nepalese":** PaySim's underlying simulation is modeled on mobile-money behavioral patterns from an African market context — meaning transaction timing norms, typical amount distributions, and velocity baselines may not transfer even qualitatively to Nepali usage patterns, independent of the synthetic-vs-real distinction alone. This more specific framing is used in Section 10.

---

## 6. Local Development Utility: Parquet Caching for PaySim

PaySim ships as a single ~470MB CSV (6,362,620 rows). Re-parsing this CSV on every run during iterative development (feature engineering, model experiments) is slow and adds friction with no benefit — this utility reads the CSV once, writes a Parquet copy, and every subsequent load reads the much faster Parquet file instead.

**This is a development-speed convenience only.** It does not affect model results, evaluation, or the real-time pipeline, and is separate from the "real-time" architecture entirely — it only touches the offline training/notebook workflow.

```python
# data_loader.py
"""
Utility for loading the PaySim dataset with local Parquet caching.

On first run, reads the raw PaySim CSV and writes a Parquet copy
alongside it. On every subsequent run, loads directly from the
Parquet file, which is dramatically faster than re-parsing a
~470MB / 6.3M-row CSV on every iteration during development.

This is a development-speed convenience only — it has no effect
on model results, evaluation, or the real-time pipeline.
"""

from pathlib import Path
import logging

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_CSV_PATH = Path("data/raw/paysim.csv")
DEFAULT_PARQUET_PATH = Path("data/cache/paysim.parquet")


def load_paysim(
    csv_path: Path = DEFAULT_CSV_PATH,
    parquet_path: Path = DEFAULT_PARQUET_PATH,
    force_rebuild: bool = False,
) -> pd.DataFrame:
    """
    Load the PaySim dataset, using a local Parquet cache when available.

    Parameters
    ----------
    csv_path : Path
        Path to the original PaySim CSV, as downloaded from Kaggle
        (https://www.kaggle.com/datasets/ealaxi/paysim1).
    parquet_path : Path
        Path where the Parquet cache is stored/read.
    force_rebuild : bool
        If True, ignore any existing Parquet cache and rebuild it
        from the CSV (use this if the raw CSV changes).

    Returns
    -------
    pd.DataFrame
        The loaded PaySim dataset.
    """
    parquet_path.parent.mkdir(parents=True, exist_ok=True)

    if parquet_path.exists() and not force_rebuild:
        logger.info(f"Loading PaySim from Parquet cache: {parquet_path}")
        return pd.read_parquet(parquet_path)

    if not csv_path.exists():
        raise FileNotFoundError(
            f"Raw PaySim CSV not found at {csv_path}. Download it from "
            f"https://www.kaggle.com/datasets/ealaxi/paysim1 and place "
            f"it at this path before running this loader."
        )

    logger.info(f"No Parquet cache found. Reading CSV: {csv_path} (slow — one-time cost)")
    df = pd.read_csv(csv_path)

    # Dtype tightening — reduces Parquet size and speeds up every
    # subsequent load. Safe because 'type' has low cardinality and
    # the fraud flags are strictly 0/1.
    if "type" in df.columns:
        df["type"] = df["type"].astype("category")
    for col in ("isFraud", "isFlaggedFraud"):
        if col in df.columns:
            df[col] = df[col].astype("int8")

    logger.info(f"Writing Parquet cache: {parquet_path}")
    df.to_parquet(parquet_path, engine="pyarrow", index=False)

    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _df = load_paysim()
    print(_df.shape)
    print(_df.dtypes)
```

Requires `pyarrow` (`pip install pyarrow`). This file lives alongside the training notebooks, imported at the top of each: `from data_loader import load_paysim`.

---

## 7. Datasets

| Dataset | Link | Role | Records | Labels |
|---|---|---|---|---|
| **PaySim** | https://www.kaggle.com/datasets/ealaxi/paysim1 | Supervised training + evaluation + replay pool (train/val/test/replay 4-way split) | 6,362,620 txns, 11 cols | Yes — 8,213 fraud (~0.13%), on `TRANSFER`/`CASH_OUT` only |
| **NEPSE Floorsheet** | https://github.com/surajrimal07/NepseAPI-Unofficial · hosted: `https://nepseapi.surajrimal.dev` | Live real-time ingestion demo only — never trains/tests the PaySim classifier | Live/streaming | None — no fraud/manipulation ground truth |

### 7.1 PaySim — four-way split

| Split | Purpose | Approx. share |
|---|---|---|
| Train | Model fitting | ~70% |
| Validation | Hyperparameter tuning | ~10–15% |
| **Test** | Formal, one-time evaluation — source of all reported precision/recall/F1/PR-AUC/confusion-matrix figures | ~10% |
| **Replay pool** | Held out, never touched during training/tuning — feeds the live streaming demo and manual-upload sample files | ~5% |

**Chronological replay requirement:** the replay pool streams in original `step` order, so rolling features are computed only from stream state accumulated so far — never precomputed in a batch operation ahead of time, which would leak future information into a supposedly real-time feature.

### 7.2 Manual upload — Flow C, batch/on-demand, not real-time

Satisfies the spec's compulsory file-upload requirement (Section 3.6). Uploaded CSVs are validated (schema, type, size) using the same Pydantic models as the live pipeline (Section 5.5), with graceful error handling. Kept explicitly labeled as batch, never folded into the real-time claim.

---

## 8. Model Selection & Imbalance Handling

| Model | Role | Imbalance handling |
|---|---|---|
| Logistic Regression | Baseline — establishes the floor every other model must beat | `class_weight='balanced'` |
| Random Forest | Model 1 — non-linear feature interactions, free feature importances | `class_weight='balanced'` or SMOTE fitted on training split only |
| XGBoost | Model 2 — strongest expected performer on severely imbalanced tabular data; matches the approach used in the PaySim-adjacent literature (Hajek et al.) | `scale_pos_weight` (ratio of legitimate:fraud in training set) |

Whichever imbalance method is used per model must be documented and reproducible (random seed, library versions) per spec Section 5.2.

**Why not deep learning (e.g., LSTM, as Timalsina et al. used):** tree-based gradient boosting typically matches or exceeds deep learning on tabular, single-transaction classification; LSTM's advantage is sequential/session-level modeling, which is a legitimate future-work direction (paired with concept-drift monitoring) rather than a core requirement here.

---

## 9. Evaluation Plan

- **Fraud classifier (PaySim):** precision, recall, F1, PR-AUC, confusion matrix, per-class metrics; full model comparison table — computed solely on the PaySim test split.
- **Real-time layer:** measured end-to-end latency (event received → decision written to DB), reported as "near-real-time," not benchmark-grade throughput.
- **NEPSE anomaly layer:** qualitative case-study evaluation only — no ground truth exists.
- **Batch upload pathway:** functional/usability testing only (reuses the same trained model as Flow A).

## 10. Limitations

- PaySim is synthetic, mobile-money-modeled data — not Nepalese financial data. More specifically, its underlying simulation is modeled on mobile-money behavior in an African market context, so timing norms, amount distributions, and velocity baselines may not transfer even qualitatively to Nepali usage patterns, independent of the synthetic-vs-real distinction alone.
- Detection scope is narrow by design: transfer-then-cash-out account-takeover fraud only, not fraud in general.
- The NEPSE anomaly module has no confirmed fraud/manipulation labels.
- The unofficial NEPSE API is third-party, rate-limited, "educational use only" — mitigated via local caching.
- "Real-time" means measured near-real-time event processing at student-project scale, not production banking-grade throughput or latency guarantees.
- All predictions are decision-support estimates requiring human review, not autonomous fraud determinations — enforced via a persistent UI disclaimer (Section 5.17), per the spec's responsible-use requirement.

## 11. Future Work

### 11.1 Near-term technical extensions
1. Calibration against real Nepalese transaction data via institutional collaboration.
2. Learned (not heuristic) feature weighting.
3. Upgrading the NEPSE module to an unsupervised model (Isolation Forest) trained on historical floorsheet data.
4. Concept-drift / behavioral-drift monitoring.
5. Cost-sensitive decisioning.

### 11.2 Path to production-grade banking deployment

**Regulatory pathway (verified, current):** NRB's Payment Systems Department finalized *Guidelines on the Regulatory Sandbox*, effective 14 May 2026 — licensed banks, payment providers, and fintechs may trial AI/ML financial products under live conditions with temporary regulatory relief, supervised cycles up to ~12 months. This is the concrete pathway to piloting this system with a real institution's real, consented data.

**Ingestion model — the biggest architectural shift.** This prototype *pulls* data (replay from file, poll/subscribe to NEPSE). Production means the bank's core banking system or payment switch *pushes* transaction events to us — we become a downstream consumer of their event bus, not an external fetcher. This requires horizontally scaled, partition-based consumer groups (multiple instances processing different accounts in parallel) rather than this prototype's single consumer process, since a production feed cannot be paused or rate-limited on our schedule.

**Position in the transaction path.** This prototype is inherently post-hoc: score after the transaction, flag, route to analyst review. A bank wanting to actually block fraud before money moves needs the inference service sitting *inside* the payment authorization call itself, under a hard shared timeout (often a few hundred milliseconds across the entire call chain) — a genuinely different latency budget and failure-mode design than "near-real-time monitoring," not just a faster version of it.

**Infrastructure hardening.** Clustered/replicated broker (Kafka cluster or Redpanda, already anticipated as the upgrade path from Redis Streams); horizontally scaled `inference-service` behind a load balancer; a dedicated feature store (e.g., Feast) to formalize the same training/serving consistency discipline already built into this prototype's chronological-replay design; circuit breakers and dead-letter queues.

**Schema adaptation.** Real banking data likely arrives as ISO 20022 or ISO 8583, or a proprietary core-banking format — requiring a transformation/adapter layer and full model retraining, since real feature distributions and fraud base rates differ from PaySim.

**Compliance.** STR/SAR-compatible output for FIU-Nepal reporting; KYC/AML linkage; NRB ICT/security directive alignment; data localization; formal retention/deletion policy.

**MLOps.** Model registry (formalizing the existing `model_versions` table), automated/drift-triggered retraining, canary/shadow deployment before cutover.

**Explainability.** SHAP/LIME per-prediction explanations — directly addresses the explainability gap Pant et al. (2026) identify as a barrier to AI adoption in Nepal's financial sector.

**Human-in-the-loop feedback.** Closing the loop from `audit_logs` — confirmed analyst overrides become new labeled training examples (active learning).

**Security & access.** TLS everywhere, encryption at rest, secrets management (Vault/cloud KMS, not `.env` files), no direct internet exposure (internal network only), federated auth into the bank's existing IAM/SSO rather than a separately managed account system, penetration testing before go-live.

**Scale validation.** Load-testing at real bank transaction volumes (including seasonal peaks — e.g., Dashain/Tihar), targeting honest p99 latency figures under that load.

---

*This README is the authoritative, current source of truth for the project's architecture and decisions. All cited sources have been independently verified as of this version.*
