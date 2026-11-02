from fastapi.testclient import TestClient

from tools.mock_inference import app

client = TestClient(app)


def body(*ids):
    return {
        "feature_schema_version": "1.0.0",
        "instances": [{"transaction_id": i, "features": {"example_feature_a": 1.0}} for i in ids],
    }


def test_forced_tiers_and_order():
    r = client.post("/predict", json=body("a-OK", "b-REVIEW", "c-HIGH"))
    assert r.status_code == 200
    j = r.json()
    assert [p["risk_tier"] for p in j["predictions"]] == ["APPROVE", "REVIEW", "HIGH_RISK"]
    assert [p["transaction_id"] for p in j["predictions"]] == ["a-OK", "b-REVIEW", "c-HIGH"]
    assert j["model_version"] == "mock-0"


def test_deterministic():
    a = client.post("/predict", json=body("ps-123")).json()["predictions"][0]["fraud_probability"]
    b = client.post("/predict", json=body("ps-123")).json()["predictions"][0]["fraud_probability"]
    assert a == b


def test_422_on_label_leak():
    b = body("x")
    b["instances"][0]["features"]["isFraud"] = "1"  # string -> rejected as non-number
    assert client.post("/predict", json=b).status_code == 422
    b = body("x")
    b["instances"][0]["isFraud"] = 1  # extra key on instance
    assert client.post("/predict", json=b).status_code == 422
