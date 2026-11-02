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
