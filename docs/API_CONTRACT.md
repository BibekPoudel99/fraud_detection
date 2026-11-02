# API_CONTRACT.md — `inference-service` `/predict`

**Status:** Draft v1.0, for review by all three members. **Owner:** Bibek. **Changes:** PR only, see section 11.
**Who builds against this:** workers (Flow A) and `core-api` (Flow C) as clients; Bibek as the server. Member B and Member C can build against the mock in section 10 before the real service exists.

This contract fixes the shape of the one call between `core-api`/workers and `inference-service` (README 5.1). It does **not** list the model's feature names; those belong to `docs/FEATURE_SPEC.md` (not yet written) and reach this contract through `feature_schema_version` (section 2).

---

## 1. Decisions and rationale

| # | Decision | Why (viva-ready) | Alternative rejected |
|---|---|---|---|
| 1 | **`/predict` receives engineered features, not raw transactions.** | Rolling features need per-account state (Redis in the stream, a dataframe in batch). Keeping that in the worker/`core-api` keeps `inference-service` stateless, so it can be restarted or scaled without losing anything, and matches README 5.9 (feature engineering happens *before* the `/predict` call in Flows A and C). | Sending raw rows and engineering inside the service: it would need its own copy of the state, or a second implementation of the features. |
| 2 | **Features travel as a named object (`{"name": value}`), not a positional array.** | The service checks names against the list stored in the model artifact, so a reordered or renamed column fails loudly instead of silently scoring the wrong inputs. This is the main training/serving-skew guard. | A positional `[float, ...]`: smaller, but a column-order bug produces plausible-looking wrong scores. |
| 3 | **`feature_schema_version` is sent with every request and checked.** | Lets the model artifact, the shared feature function and the callers move together; a stale caller gets a clear 409, not a quietly wrong score. | Trusting that everyone deployed together. |
| 4 | **Strict validation, unknown fields forbidden (`extra="forbid"`), numbers only, no NaN/Infinity.** | A request carrying `isFraud` (the label) or any other stray key is rejected, so label leakage cannot slip in through the API. Missing values must be imputed by the shared feature function, deterministically, not guessed by the service. | Lenient coercion (`"5"` → 5.0): hides upstream bugs. |
| 5 | **One endpoint, `instances` is a list (1 to 500).** | Keeps the locked "`/predict` only" surface (README 5.1) while letting Flow C score a file without one HTTP call per row. Flow A sends a list of one. | A separate `/predict/batch`: a second endpoint, i.e. a change to a locked decision. |
| 6 | **The service returns the risk tier, using thresholds stored with the model artifact.** | The thresholds are tuned on the validation split together with the model, so they must version together. Computing the tier in `core-api` would let the two drift apart. The response echoes the thresholds used, so every logged prediction is self-explanatory. | Tier computed by each caller from config. |
| 7 | **Every response carries `model_version`.** | It is the key into `model_versions` (README 5.16) and gets stored with each row in `fraud_predictions`, so any logged prediction traces to the exact artifact and hyperparameters. | Inferring the version from deployment time. |
| 8 | **The system assigns `transaction_id`; the model never sees identifiers.** | PaySim has no transaction ID column (its 11 columns are `step`, `type`, `amount`, `nameOrig`, `oldbalanceOrg`, `newbalanceOrig`, `nameDest`, `oldbalanceDest`, `newbalanceDest`, `isFraud`, `isFlaggedFraud`). The ID exists only to correlate request and response. Suggested scheme for the replay producer: derive it from the row's position in the original CSV, e.g. `ps-4821907`, so replays are reproducible and duplicates detectable. Flow C: `batch-<upload_id>-<row>`. | Random UUIDs for replay: work, but a re-run produces different IDs for the same row. |
| 9 | **`inference_ms` is the service's own processing time, not the end-to-end latency.** | The latency claim (README 9) is event received → decision written, measured by timestamps in the worker. `inference_ms` lets the report break that figure into stages (queue wait, feature engineering, HTTP, inference, DB write) instead of quoting one opaque number. | Reusing `inference_ms` as "the latency": it would understate the real figure. |

## 2. Where the pieces sit

```
worker / core-api                                   inference-service
─────────────────                                   ─────────────────
raw PaySim event
   │  shared/features (one function, stateful
   │  part reads Redis in Flow A)           
   ▼
{feature_name: number, ...}  ── POST /predict ──►  check version + names
                                                    artifact.predict_proba
                                                    thresholds → risk_tier
fraud_predictions row  ◄──── predictions ─────────  (stateless, no DB, no Redis)
```

- **Shared feature function** (`shared/`, owned by Bibek): all deterministic feature logic, imported identically by the notebooks, the workers and `core-api`'s batch path. Defined in `docs/FEATURE_SPEC.md`.
- **Model artifact** (`.joblib`, loaded once at startup): the fitted estimator *plus* any fitted preprocessing (for example the scaler for Logistic Regression), the ordered `feature_names`, the `feature_schema_version`, the `model_version` and the tier thresholds. Fitted parameters belong in the artifact because they are learned from the training split; stateless feature logic belongs in the shared function. No preprocessing code is duplicated in `inference-service`.
- `inference-service` touches no database and no Redis. The caller writes to `fraud_predictions`.

## 3. Endpoint

| | |
|---|---|
| Method / path | `POST /predict` |
| Content type | `application/json` |
| Reachable from | Docker Compose internal network only. **Not** routed through Nginx and never exposed to the browser. Browsers talk to `core-api`; `core-api` and the workers talk to this. |
| Idempotent | Yes. Same request + same `model_version` gives the same response, so retries are safe. |

## 4. Request

| Field | Type | Rules |
|---|---|---|
| `feature_schema_version` | string, `MAJOR.MINOR.PATCH` | Must equal the artifact's version, else 409. |
| `instances` | array, 1 to 500 items | No two items may share a `transaction_id`. |
| `instances[].transaction_id` | string, 1 to 64 chars | Pattern `^[A-Za-z0-9._:-]+$`. Echoed in the response. |
| `instances[].features` | object, name → number | Names must be exactly the artifact's `feature_names` (no missing, no extra). Values are JSON numbers: no strings, booleans, null, NaN or Infinity. |

Any other field anywhere in the body is rejected (422). **The label (`isFraud`) must never be sent.**

```json
{
  "feature_schema_version": "1.0.0",
  "instances": [
    {
      "transaction_id": "ps-4821907",
      "features": {
        "example_feature_a": 181.0,
        "example_feature_b": 0,
        "example_feature_c": 1
      }
    }
  ]
}
```

The three feature names above are **placeholders**. The real ones come from `docs/FEATURE_SPEC.md`.

## 5. Response (200)

| Field | Type | Meaning |
|---|---|---|
| `model_version` | string | Matches `model_versions`. Store it with the prediction. |
| `feature_schema_version` | string | Echo of the artifact's version. |
| `thresholds` | `{review, high_risk}` | The cut-offs used for `risk_tier`, each in [0, 1], `review < high_risk`. |
| `predictions[]` | array, same order as the request | One item per instance. Match on `transaction_id`; do not rely on order alone. |
| `predictions[].fraud_probability` | float in [0, 1] | The model's `predict_proba` for the fraud class. See section 6. |
| `predictions[].risk_tier` | `APPROVE` \| `REVIEW` \| `HIGH_RISK` | Derived from the thresholds. |
| `inference_ms` | float ≥ 0 | Time inside the service for the whole request (not per instance). |

```json
{
  "model_version": "xgb-0001",
  "feature_schema_version": "1.0.0",
  "thresholds": { "review": 0.30, "high_risk": 0.80 },
  "predictions": [
    { "transaction_id": "ps-4821907", "fraud_probability": 0.9731, "risk_tier": "HIGH_RISK" }
  ],
  "inference_ms": 3.4
}
```

The numbers in this example are illustrative, not results. Real threshold values are produced by training (section 12).

## 6. Semantics callers must respect

- **Tier rule:** `p < review` → `APPROVE`; `review ≤ p < high_risk` → `REVIEW`; `p ≥ high_risk` → `HIGH_RISK`. `tier_for()` in the schema module is the single implementation.
- **UI wording:** the enum is `HIGH_RISK`; the UI displays "HIGH RISK" (README 5.14 wording). Do not store the display string.
- **`fraud_probability` is the model's raw output, not a calibrated probability.** README 8 trains with `class_weight='balanced'` / `scale_pos_weight`, which shifts the scores upward relative to the true ~0.13% base rate. Treat it as a ranking score. The UI disclaimer (README 5.17) already frames outputs as estimates; do not present the number as "a 97% chance of fraud". If we calibrate later (e.g. on the validation split), the field name and shape stay the same.
- **Batch size:** the cap is 500 instances, a starting value chosen to bound request size and worst-case latency. Re-tune after measuring. `core-api` splits larger uploads into chunks of at most 500.
- **One response, one model:** every instance in a response is scored by the same `model_version`.

## 7. Errors

| Status | When | Body | Retry? |
|---|---|---|---|
| 422 | Malformed or invalid request (wrong type, NaN, unknown field, empty list, over 500, duplicate IDs, bad ID or version format) | FastAPI's standard validation body (`{"detail": [...]}`) | No. Fix the caller. |
| 409 | `feature_schema_version` differs from the artifact's, **or** the names in `features` don't match the artifact's `feature_names` | `ErrorResponse` with `code: FEATURE_SCHEMA_MISMATCH`, `expected_feature_schema_version`, and `missing_features` / `unexpected_features`. `message` names the first offending `transaction_id`. | No. This is a deployment or shared-function bug. |
| 503 | Model artifact not loaded (still starting, or failed to load) | `ErrorResponse`, `code: MODEL_NOT_LOADED` | Yes, with backoff. |
| 500 | Unexpected error | `ErrorResponse`, `code: INTERNAL_ERROR` | Yes, limited. |

## 8. Client behaviour (workers and `core-api`)

These are requirements on callers, so a failed call can never silently drop a transaction:

1. **Timeout:** set an explicit client timeout (starting value 2 s, configurable via `pydantic-settings`; re-tune once real latency is measured).
2. **Retryable** (connection error, timeout, 500, 503): retry with exponential backoff, a small fixed number of attempts. In Flow A, do **not** `XACK` the stream message until the prediction is written, so an unfinished message stays in the pending list and is not lost.
3. **Not retryable** (422, 409): never retry, since the same request cannot succeed. In Flow A, move the event to a dead-letter stream with the error body and acknowledge it, so one bad event cannot block the consumer group.
4. **Exhausted retries:** dead-letter the same way and log it. Never drop silently.
5. **Duplicates:** retries and redeliveries can process an event twice. Member B's schema should make writes idempotent, for example a unique constraint on `(transaction_id, model_version)` in `fraud_predictions`.

## 9. Flow mapping

| Flow | Calls `/predict`? | Shape |
|---|---|---|
| A: PaySim replay | Yes (fraud consumer worker) | One instance per call. |
| B: NEPSE anomaly | **No.** Statistical rules, no ML, different schema. | n/a |
| C: CSV batch upload | Yes (`core-api`) | Chunks of up to 500 instances, tagged `source: batch_upload` when logged. |

## 10. Mock for Member B and Member C

Put these two files in the repo and everyone can develop against the real contract today. The mock returns **fake** probabilities and mock-only thresholds (0.30 / 0.80). Ending a `transaction_id` in `-OK`, `-REVIEW` or `-HIGH` forces `APPROVE`, `REVIEW` or `HIGH_RISK`, which lets the frontend build all three states. Do not run it in the final demo.

Run from the repo root in PowerShell with the `.venv` active:

```powershell
$env:PYTHONPATH = "."
uvicorn tools.mock_inference:app --port 8001
```

Try it:

```powershell
$body = '{"feature_schema_version":"1.0.0","instances":[{"transaction_id":"demo-HIGH","features":{"f":1}}]}'
Invoke-RestMethod -Method Post -Uri http://localhost:8001/predict -ContentType "application/json" -Body $body
```

(The mock accepts any feature names; the real service enforces the artifact's list, so expect 409s once the real service arrives if the shared function disagrees with the model.)

**`shared/schemas/predict.py`** — the normative definition. Needs `__init__.py` in `shared/` and `shared/schemas/`.

```python
"""shared/schemas/predict.py - normative /predict contract (Pydantic v2).

Imported by inference-service (server), by the workers and core-api (clients).
Nobody redefines these models; change them only through a PR that updates
docs/API_CONTRACT.md in the same commit.
"""

from enum import StrEnum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    model_validator,
)

MAX_INSTANCES_PER_REQUEST = 500  # starting value, see API_CONTRACT.md section 6

# JSON numbers only: accepts 5 and 5.0, rejects "5", true, null, NaN, Infinity.
FiniteNumber = Annotated[StrictInt | StrictFloat, Field(allow_inf_nan=False)]

TransactionId = Annotated[
    str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
]
SemVer = Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]


class RiskTier(StrEnum):
    APPROVE = "APPROVE"
    REVIEW = "REVIEW"
    HIGH_RISK = "HIGH_RISK"


class PredictInstance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    transaction_id: TransactionId
    # Keys are defined by docs/FEATURE_SPEC.md; the authoritative list is the
    # one stored inside the loaded model artifact (checked at request time).
    features: dict[str, FiniteNumber] = Field(min_length=1)


class PredictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    feature_schema_version: SemVer
    instances: list[PredictInstance] = Field(
        min_length=1, max_length=MAX_INSTANCES_PER_REQUEST
    )

    @model_validator(mode="after")
    def _unique_transaction_ids(self) -> "PredictRequest":
        ids = [i.transaction_id for i in self.instances]
        if len(ids) != len(set(ids)):
            raise ValueError("transaction_id values must be unique within a request")
        return self


class Thresholds(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    review: float = Field(ge=0, le=1)
    high_risk: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _ordered(self) -> "Thresholds":
        if not self.review < self.high_risk:
            raise ValueError("review threshold must be below high_risk threshold")
        return self


def tier_for(p: float, t: Thresholds) -> RiskTier:
    """p < review -> APPROVE; review <= p < high_risk -> REVIEW; else HIGH_RISK."""
    if p >= t.high_risk:
        return RiskTier.HIGH_RISK
    if p >= t.review:
        return RiskTier.REVIEW
    return RiskTier.APPROVE


class Prediction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    transaction_id: TransactionId
    fraud_probability: float = Field(ge=0, le=1)
    risk_tier: RiskTier


class PredictResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_version: str = Field(min_length=1, max_length=64)
    feature_schema_version: SemVer
    thresholds: Thresholds
    predictions: list[Prediction] = Field(min_length=1)
    inference_ms: float = Field(ge=0)


class ErrorCode(StrEnum):
    FEATURE_SCHEMA_MISMATCH = "FEATURE_SCHEMA_MISMATCH"
    MODEL_NOT_LOADED = "MODEL_NOT_LOADED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorResponse(BaseModel):
    """Body for 409 / 503 / 500. (422 uses FastAPI's standard validation body.)"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: ErrorCode
    message: str
    expected_feature_schema_version: SemVer | None = None
    missing_features: list[str] | None = None
    unexpected_features: list[str] | None = None
```

**`tools/mock_inference.py`**

```python
"""tools/mock_inference.py - stand-in for inference-service, NOT a model.

Lets core-api and frontend work build against the /predict contract before the
real service exists. Probabilities are fake; the thresholds below are mock-only.

Run from the repo root (PowerShell, .venv active):
    $env:PYTHONPATH = "."
    uvicorn tools.mock_inference:app --port 8001

Force a tier by ending the transaction_id with a suffix:
    ...-OK -> APPROVE (0.01)   ...-REVIEW -> REVIEW (0.50)   ...-HIGH -> HIGH_RISK (0.97)
Any other id gets a stable pseudo-random probability derived from the id.
"""

import hashlib
import time

from fastapi import FastAPI

from shared.schemas.predict import (
    Prediction,
    PredictRequest,
    PredictResponse,
    Thresholds,
    tier_for,
)

app = FastAPI(title="mock inference-service (not a model)")

MOCK_THRESHOLDS = Thresholds(review=0.30, high_risk=0.80)  # mock-only values
FORCED = {"-OK": 0.01, "-REVIEW": 0.50, "-HIGH": 0.97}


def _fake_probability(transaction_id: str) -> float:
    for suffix, p in FORCED.items():
        if transaction_id.endswith(suffix):
            return p
    digest = hashlib.sha1(transaction_id.encode()).hexdigest()
    return (int(digest, 16) % 10_000) / 10_000


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest) -> PredictResponse:
    t0 = time.perf_counter()
    predictions = []
    for inst in req.instances:
        p = _fake_probability(inst.transaction_id)
        predictions.append(
            Prediction(
                transaction_id=inst.transaction_id,
                fraud_probability=p,
                risk_tier=tier_for(p, MOCK_THRESHOLDS),
            )
        )
    return PredictResponse(
        model_version="mock-0",
        feature_schema_version=req.feature_schema_version,
        thresholds=MOCK_THRESHOLDS,
        predictions=predictions,
        inference_ms=(time.perf_counter() - t0) * 1000,
    )
```

## 11. Change policy

- This file and `shared/schemas/predict.py` change **in the same PR**, and all three members review it.
- **Non-breaking** (new optional response field, new error code): merge, announce in the sync.
- **Breaking** (renamed or removed field, changed meaning, new required request field): bump the contract in the PR title, update the mock in the same PR, and tell Member B and C before merging. Feature-list changes are separate: they bump `feature_schema_version` via `docs/FEATURE_SPEC.md`.

## 12. Open items (cannot be filled in yet)

| Item | Resolved by |
|---|---|
| The real feature names and their order | `docs/FEATURE_SPEC.md` (next deliverable) |
| Threshold values (`review`, `high_risk`) | Model training on the validation split |
| Whether to calibrate scores | After the first metrics table |
| Client timeout and the 500 cap | After the first latency measurements |

## 13. Proposed additions not in README (your call)

Neither changes a locked decision, but neither was explicitly decided, so they are flagged rather than assumed.

1. **`GET /health`** on `inference-service`: returns 200 once the model is loaded, 503 before. Docker Compose healthchecks and `depends_on: condition: service_healthy` need something to poll. README says "`/predict` only", which I read as "only model functionality", but you may read it more strictly.
2. **Shared secret between services:** a header such as `X-Internal-Token`, value from `.env` via `pydantic-settings`, checked by `inference-service`. The network is already internal, so this is defence in depth, and a cheap answer to "what stops another container calling `/predict`?" in the viva.
