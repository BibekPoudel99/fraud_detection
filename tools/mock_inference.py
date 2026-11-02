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
