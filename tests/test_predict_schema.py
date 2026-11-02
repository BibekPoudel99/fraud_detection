import json
import pytest
from pydantic import ValidationError

from shared.schemas.predict import (
    PredictRequest, PredictResponse, Thresholds, RiskTier, tier_for,
    ErrorResponse, MAX_INSTANCES_PER_REQUEST,
)

GOOD = {
    "feature_schema_version": "1.0.0",
    "instances": [
        {"transaction_id": "7f3c2a9e-0b1d-4c55-9a52-2f6d1e8b4a10",
         "features": {"example_feature_a": 181.0, "example_feature_b": 0, "example_feature_c": 1}}
    ],
}


def req(**over):
    d = json.loads(json.dumps(GOOD))
    d.update(over)
    return d


def test_good_request_ok():
    r = PredictRequest.model_validate(GOOD)
    assert r.instances[0].features["example_feature_b"] == 0


@pytest.mark.parametrize("bad", ["5", True, None, [1], {"a": 1}])
def test_non_numbers_rejected(bad):
    d = req()
    d["instances"][0]["features"]["example_feature_a"] = bad
    with pytest.raises(ValidationError):
        PredictRequest.model_validate(d)


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "-Infinity"])
def test_nan_inf_rejected_via_json(raw):
    text = json.dumps(GOOD).replace("181.0", raw)
    with pytest.raises(ValidationError):
        PredictRequest.model_validate_json(text)


def test_label_leak_rejected():
    d = req()
    d["instances"][0]["isFraud"] = 1
    with pytest.raises(ValidationError):
        PredictRequest.model_validate(d)


def test_extra_top_level_rejected():
    with pytest.raises(ValidationError):
        PredictRequest.model_validate(req(foo=1))


def test_empty_and_oversize():
    with pytest.raises(ValidationError):
        PredictRequest.model_validate(req(instances=[]))
    inst = lambda i: {"transaction_id": f"t{i}", "features": {"f": 1.0}}
    PredictRequest.model_validate(req(instances=[inst(i) for i in range(MAX_INSTANCES_PER_REQUEST)]))
    with pytest.raises(ValidationError):
        PredictRequest.model_validate(req(instances=[inst(i) for i in range(MAX_INSTANCES_PER_REQUEST + 1)]))


def test_duplicate_ids_rejected():
    one = GOOD["instances"][0]
    with pytest.raises(ValidationError):
        PredictRequest.model_validate(req(instances=[one, one]))


def test_bad_ids_and_version():
    d = req(); d["instances"][0]["transaction_id"] = "has space"
    with pytest.raises(ValidationError):
        PredictRequest.model_validate(d)
    with pytest.raises(ValidationError):
        PredictRequest.model_validate(req(feature_schema_version="1.0"))


def test_tiers_and_thresholds():
    t = Thresholds(review=0.3, high_risk=0.8)
    assert tier_for(0.0, t) is RiskTier.APPROVE
    assert tier_for(0.2999, t) is RiskTier.APPROVE
    assert tier_for(0.3, t) is RiskTier.REVIEW
    assert tier_for(0.7999, t) is RiskTier.REVIEW
    assert tier_for(0.8, t) is RiskTier.HIGH_RISK
    assert tier_for(1.0, t) is RiskTier.HIGH_RISK
    with pytest.raises(ValidationError):
        Thresholds(review=0.8, high_risk=0.3)
    with pytest.raises(ValidationError):
        Thresholds(review=0.5, high_risk=0.5)


def test_response_roundtrip_and_bounds():
    resp = {
        "model_version": "xgb-0001",
        "feature_schema_version": "1.0.0",
        "thresholds": {"review": 0.3, "high_risk": 0.8},
        "predictions": [{"transaction_id": "t1", "fraud_probability": 0.9731, "risk_tier": "HIGH_RISK"}],
        "inference_ms": 3.4,
    }
    PredictResponse.model_validate(resp)
    resp["predictions"][0]["fraud_probability"] = 1.2
    with pytest.raises(ValidationError):
        PredictResponse.model_validate(resp)


def test_error_body():
    ErrorResponse.model_validate({
        "code": "FEATURE_SCHEMA_MISMATCH", "message": "x",
        "expected_feature_schema_version": "1.0.0",
        "missing_features": ["a"], "unexpected_features": ["b"],
    })
