"""shared/features/core.py - the ONE feature function (docs/FEATURE_SPEC.md).

Imported identically by the training notebooks, the Flow A fraud consumer and
core-api's Flow C batch path. Nobody re-implements any of this.

Structural leakage guard: compute_features() is read-only and sees only state
built from EARLIER events; update_dest_state() runs AFTER scoring. The event
model has no label field, so isFraud cannot reach the features.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

FEATURE_SCHEMA_VERSION = "0.1.0"  # draft; becomes 1.0.0 when frozen after the EDA gates


@dataclass(frozen=True)
class FeatureConfig:
    window_steps: int = 24  # PaySim: 1 step = 1 hour, so 24 steps = one day
    ratio_clip: float = 10.0  # upper bound for ratio features (linear-model stability)


CONFIG = FeatureConfig()

# Detection scope (README): transfer-then-cash-out. Only these types are scored.
SCORED_TYPES = frozenset({"TRANSFER", "CASH_OUT"})

FEATURE_NAMES: tuple[str, ...] = (
    # stateless, from the current row
    "type_is_transfer",
    "log_amount",
    "log_orig_balance_before",
    "amount_to_orig_balance",
    "orig_balance_zero",
    "orig_drained",
    # balance-consistency group (simulator-artefact risk, ablation required)
    "orig_balance_error",
    "dest_balance_error",
    "dest_old_balance_zero",
    "dest_new_balance_zero",
    # stateful: transfer-then-cash-out chain, origin side
    "orig_inbound_transfer_count_24h",
    "log_orig_inbound_transfer_sum_24h",
    "steps_since_orig_last_inbound_transfer",
    "amount_to_orig_inbound_sum",
    # stateful: recipient side
    "dest_inbound_transfer_count_24h",
    "dest_has_prior_inbound_transfer",
)

BALANCE_CONSISTENCY_GROUP = (
    "orig_balance_error",
    "dest_balance_error",
    "dest_old_balance_zero",
    "dest_new_balance_zero",
)

PAYSIM_COLUMN_MAP = {
    "step": "step",
    "type": "type",
    "amount": "amount",
    "nameOrig": "name_orig",
    "oldbalanceOrg": "oldbalance_org",
    "newbalanceOrig": "newbalance_orig",
    "nameDest": "name_dest",
    "oldbalanceDest": "oldbalance_dest",
    "newbalanceDest": "newbalance_dest",
}  # isFraud and isFlaggedFraud are deliberately absent


class TransactionEvent(BaseModel):
    """One transaction as the feature function sees it. No label field, by design."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step: int = Field(ge=0)
    type: Literal["CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"]
    amount: float = Field(ge=0, allow_inf_nan=False)
    name_orig: str = Field(min_length=1)
    oldbalance_org: float = Field(allow_inf_nan=False)
    newbalance_orig: float = Field(allow_inf_nan=False)
    name_dest: str = Field(min_length=1)
    oldbalance_dest: float = Field(allow_inf_nan=False)
    newbalance_dest: float = Field(allow_inf_nan=False)


@dataclass(frozen=True)
class AccountState:
    """Per-account memory: TRANSFER credits received inside the window + a lifetime count."""

    inbound: tuple[tuple[int, float], ...] = ()  # (step, amount), oldest first
    inbound_total: int = 0  # lifetime count of inbound TRANSFERs, never pruned


EMPTY_STATE = AccountState()


class StateStore(Protocol):
    def get(self, name: str) -> AccountState: ...  # EMPTY_STATE if unknown; must not create
    def put(self, name: str, state: AccountState) -> None: ...


class DictStore:
    """In-memory store: training, tests, Flow C."""

    def __init__(self) -> None:
        self.data: dict[str, AccountState] = {}

    def get(self, name: str) -> AccountState:
        return self.data.get(name, EMPTY_STATE)

    def put(self, name: str, state: AccountState) -> None:
        self.data[name] = state


def _log1p_nonneg(x: float) -> float:
    return math.log1p(max(x, 0.0))


def _signed_log1p(x: float) -> float:
    return math.copysign(math.log1p(abs(x)), x)


def _in_window(state: AccountState, step: int, window: int) -> list[tuple[int, float]]:
    return [(s, a) for s, a in state.inbound if step - s < window]


def compute_features(
    e: TransactionEvent,
    orig: AccountState,
    dest: AccountState,
    cfg: FeatureConfig = CONFIG,
) -> dict[str, float]:
    """Read-only. `orig`/`dest` are the states BEFORE this event. Only scored types."""
    if e.type not in SCORED_TYPES:
        raise ValueError(f"type {e.type!r} is out of detection scope; do not score it")

    w = cfg.window_steps
    o_win = _in_window(orig, e.step, w)
    o_count = len(o_win)
    o_sum = sum(a for _, a in o_win)
    o_since = float(min(e.step - s for s, _ in o_win)) if o_win else float(w)
    d_count = len(_in_window(dest, e.step, w))

    def ratio(num: float, den: float) -> float:
        return min(num / den, cfg.ratio_clip) if den > 0 else 0.0

    values = {
        "type_is_transfer": 1.0 if e.type == "TRANSFER" else 0.0,
        "log_amount": _log1p_nonneg(e.amount),
        "log_orig_balance_before": _log1p_nonneg(e.oldbalance_org),
        "amount_to_orig_balance": ratio(e.amount, e.oldbalance_org),
        "orig_balance_zero": 1.0 if e.oldbalance_org == 0 else 0.0,
        "orig_drained": 1.0 if (e.oldbalance_org > 0 and e.newbalance_orig == 0) else 0.0,
        "orig_balance_error": _signed_log1p(e.oldbalance_org - e.amount - e.newbalance_orig),
        "dest_balance_error": _signed_log1p(e.oldbalance_dest + e.amount - e.newbalance_dest),
        "dest_old_balance_zero": 1.0 if e.oldbalance_dest == 0 else 0.0,
        "dest_new_balance_zero": 1.0 if e.newbalance_dest == 0 else 0.0,
        "orig_inbound_transfer_count_24h": float(o_count),
        "log_orig_inbound_transfer_sum_24h": _log1p_nonneg(o_sum),
        "steps_since_orig_last_inbound_transfer": o_since,
        "amount_to_orig_inbound_sum": ratio(e.amount, o_sum),
        "dest_inbound_transfer_count_24h": float(d_count),
        "dest_has_prior_inbound_transfer": 1.0 if dest.inbound_total > 0 else 0.0,
    }
    return {name: values[name] for name in FEATURE_NAMES}  # fixed order


def update_dest_state(
    e: TransactionEvent, dest: AccountState, cfg: FeatureConfig = CONFIG
) -> AccountState:
    """State AFTER the event. Only a TRANSFER changes anything (credit to the recipient)."""
    if e.type != "TRANSFER":
        return dest
    kept = tuple((s, a) for s, a in dest.inbound if e.step - s < cfg.window_steps)
    return AccountState(inbound=kept + ((e.step, e.amount),), inbound_total=dest.inbound_total + 1)


def process_event(
    e: TransactionEvent, store: StateStore, cfg: FeatureConfig = CONFIG
) -> dict[str, float] | None:
    """Score-then-update. Returns features for scored types, else None.

    Used verbatim by the training pass, the Flow A consumer and Flow C.
    """
    orig = store.get(e.name_orig)
    dest = store.get(e.name_dest)  # same object as `orig` for a self-transfer; both read BEFORE update
    features = compute_features(e, orig, dest, cfg) if e.type in SCORED_TYPES else None
    new_dest = update_dest_state(e, dest, cfg)
    if new_dest is not dest:
        store.put(e.name_dest, new_dest)
    return features
