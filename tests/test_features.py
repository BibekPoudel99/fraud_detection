import json
import math
import random

import pandas as pd
import pytest
from pydantic import ValidationError

from shared.features import (
    CONFIG,
    FEATURE_NAMES,
    AccountState,
    DictStore,
    TransactionEvent,
    build_feature_table,
    compute_features,
    process_event,
)
from shared.features.core import PAYSIM_COLUMN_MAP


def ev(step, type_, amount, orig, dest, ob=1000.0, nb=None, od=0.0, nd=None):
    nb = ob - amount if nb is None else nb
    nd = od + amount if nd is None else nd
    return TransactionEvent(
        step=step, type=type_, amount=amount, name_orig=orig, oldbalance_org=ob,
        newbalance_orig=nb, name_dest=dest, oldbalance_dest=od, newbalance_dest=nd,
    )


def synth_df(n, seed=0, accounts=300):
    rng = random.Random(seed)
    rows, step = [], 1
    types = ["TRANSFER", "CASH_OUT", "PAYMENT", "CASH_IN", "DEBIT"]
    for _ in range(n):
        step += rng.choice([0, 0, 0, 1, 2])
        t = rng.choice(types)
        o, d = f"C{rng.randrange(accounts)}", f"C{rng.randrange(accounts)}"
        ob = rng.choice([0.0, rng.uniform(1, 5e5)])
        amt = rng.uniform(0, 3e5)
        nb = max(ob - amt, 0.0) if rng.random() < 0.8 else ob
        od = rng.choice([0.0, rng.uniform(1, 5e5)])
        nd = od + amt if rng.random() < 0.8 else 0.0
        rows.append(dict(step=step, type=t, amount=amt, nameOrig=o, oldbalanceOrg=ob,
                         newbalanceOrig=nb, nameDest=d, oldbalanceDest=od, newbalanceDest=nd,
                         isFraud=rng.random() < 0.01, isFlaggedFraud=0))
    return pd.DataFrame(rows)


def row_events(df):
    for r in df.itertuples(index=False):
        yield TransactionEvent(**{PAYSIM_COLUMN_MAP[c]: getattr(r, c) for c in PAYSIM_COLUMN_MAP})


# 1. hand-computed transfer-then-cash-out chain ------------------------------------
def test_chain_hand_computed():
    s = DictStore()
    f1 = process_event(ev(1, "TRANSFER", 100.0, "A", "B", ob=100.0, nb=0.0), s)
    assert f1["dest_has_prior_inbound_transfer"] == 0.0
    assert f1["orig_inbound_transfer_count_24h"] == 0.0
    assert f1["steps_since_orig_last_inbound_transfer"] == CONFIG.window_steps
    assert f1["orig_drained"] == 1.0 and f1["amount_to_orig_balance"] == 1.0
    f2 = process_event(ev(3, "CASH_OUT", 100.0, "B", "X", ob=100.0, nb=0.0), s)
    assert f2["orig_inbound_transfer_count_24h"] == 1.0
    assert f2["steps_since_orig_last_inbound_transfer"] == 2.0
    assert f2["amount_to_orig_inbound_sum"] == 1.0
    assert f2["log_orig_inbound_transfer_sum_24h"] == pytest.approx(math.log1p(100.0))
    assert f2["type_is_transfer"] == 0.0


# 2. window boundary ---------------------------------------------------------------
@pytest.mark.parametrize("step,expected", [(1 + 23, 1.0), (1 + 24, 0.0)])
def test_window_boundary(step, expected):
    s = DictStore()
    process_event(ev(1, "TRANSFER", 50.0, "A", "B"), s)
    f = process_event(ev(step, "CASH_OUT", 50.0, "B", "X"), s)
    assert f["orig_inbound_transfer_count_24h"] == expected


# 3. no future leakage: prefix invariance ------------------------------------------
def test_prefix_invariance_and_future_edits():
    df = synth_df(2000, seed=1)
    full, _ = build_feature_table(df)
    k = 1200
    prefix, _ = build_feature_table(df.iloc[:k])
    pd.testing.assert_frame_equal(full.loc[prefix.index], prefix)
    mutated = df.copy()
    mutated.loc[k:, ["amount", "oldbalanceDest", "newbalanceDest"]] *= 7.0
    mutated.loc[k:, "nameDest"] = "C1"
    after, _ = build_feature_table(mutated)
    pd.testing.assert_frame_equal(after.loc[prefix.index], prefix)


# 4. label can never influence features --------------------------------------------
def test_label_independent():
    df = synth_df(1500, seed=2)
    a, _ = build_feature_table(df)
    flipped = df.copy()
    flipped["isFraud"] = ~flipped["isFraud"]
    flipped["isFlaggedFraud"] = 1
    b, _ = build_feature_table(flipped)
    pd.testing.assert_frame_equal(a, b)
    with pytest.raises(ValidationError):
        TransactionEvent(**{**ev(1, "TRANSFER", 1.0, "A", "B").model_dump(), "isFraud": 1})


# 5. batch vs streaming-with-serialising-store parity (Redis stand-in) ---------------
class JsonStore:
    """Round-trips every state through JSON text, as a Redis-backed store would."""

    def __init__(self):
        self.raw = {}

    def get(self, name):
        if name not in self.raw:
            return AccountState()
        d = json.loads(self.raw[name])
        return AccountState(tuple((s, a) for s, a in d["inbound"]), d["total"])

    def put(self, name, st):
        self.raw[name] = json.dumps({"inbound": list(st.inbound), "total": st.inbound_total})


def test_json_store_parity_exact():
    df = synth_df(3000, seed=3)
    batch, _ = build_feature_table(df)
    store, rows, idx = JsonStore(), [], []
    for i, e in zip(df.index, row_events(df)):
        f = process_event(e, store)
        if f is not None:
            idx.append(i)
            rows.append(list(f.values()))
    stream = pd.DataFrame(rows, index=pd.Index(idx), columns=list(FEATURE_NAMES))
    pd.testing.assert_frame_equal(batch, stream, check_exact=True)


# 6. priming at the replay boundary reproduces batch features exactly ---------------
def test_primed_replay_equals_batch():
    df = synth_df(4000, seed=4)
    cut = 3800
    full, _ = build_feature_table(df)
    _, head_store = build_feature_table(df.iloc[:cut])
    tail = df.iloc[cut:]
    needed = set(tail["nameOrig"]) | set(tail["nameDest"])
    primed = DictStore()
    for name in needed:  # snapshot ONLY accounts that appear in the replay pool
        primed.put(name, head_store.get(name))
    tail_feats, _ = build_feature_table(tail, store=primed)
    pd.testing.assert_frame_equal(full.loc[tail_feats.index], tail_feats, check_exact=True)


# 7. basic invariants ----------------------------------------------------------------
def test_finite_names_scope_order():
    df = synth_df(3000, seed=5)
    feats, _ = build_feature_table(df)
    assert list(feats.columns) == list(FEATURE_NAMES)
    assert feats.notna().all().all()
    assert (feats.abs() < float("inf")).all().all()
    assert set(df.loc[feats.index, "type"]) <= {"TRANSFER", "CASH_OUT"}
    n_scoped = df["type"].isin(["TRANSFER", "CASH_OUT"]).sum()
    assert len(feats) == n_scoped
    assert feats["amount_to_orig_balance"].max() <= CONFIG.ratio_clip
    assert feats["amount_to_orig_inbound_sum"].max() <= CONFIG.ratio_clip


def test_out_of_order_rejected():
    df = synth_df(100, seed=6)
    df.loc[50, "step"] = 0
    with pytest.raises(ValueError):
        build_feature_table(df)


def test_out_of_scope_not_scorable():
    e = ev(1, "PAYMENT", 5.0, "A", "M1")
    with pytest.raises(ValueError):
        compute_features(e, AccountState(), AccountState())
    assert process_event(e, DictStore()) is None


def test_self_transfer_reads_state_before_update():
    s = DictStore()
    f = process_event(ev(1, "TRANSFER", 10.0, "A", "A"), s)
    assert f["orig_inbound_transfer_count_24h"] == 0.0  # own credit not visible to itself
    f2 = process_event(ev(2, "CASH_OUT", 10.0, "A", "X"), s)
    assert f2["orig_inbound_transfer_count_24h"] == 1.0


def test_event_rejects_nan():
    with pytest.raises(ValidationError):
        TransactionEvent(step=1, type="TRANSFER", amount=float("nan"), name_orig="A",
                         oldbalance_org=1, newbalance_orig=0, name_dest="B",
                         oldbalance_dest=0, newbalance_dest=1)
