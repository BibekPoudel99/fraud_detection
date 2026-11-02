"""shared/features/batch.py - sequential driver for training and Flow C.

Runs the same process_event() the streaming consumer runs, in row order.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .core import (
    CONFIG,
    FEATURE_NAMES,
    PAYSIM_COLUMN_MAP,
    DictStore,
    FeatureConfig,
    StateStore,
    TransactionEvent,
    process_event,
)

if TYPE_CHECKING:
    import pandas as pd


def build_feature_table(
    df: "pd.DataFrame",
    store: StateStore | None = None,
    cfg: FeatureConfig = CONFIG,
    validate: bool = True,
) -> tuple["pd.DataFrame", StateStore]:
    """Features for every scored row of `df`, in ONE chronological pass.

    `df` must hold the PaySim columns in PAYSIM_COLUMN_MAP, in processing order
    (the original CSV order, `step` non-decreasing). Returns a frame indexed by
    the original row index (scored rows only) and the final store, so the ETL can
    snapshot state at the replay-pool boundary.

    validate=False builds events with model_construct (trusted Parquet path only);
    stream, API and upload ingress always validate.
    """
    import pandas as pd  # local import: core.py stays pandas-free for the workers

    missing = [c for c in PAYSIM_COLUMN_MAP if c not in df.columns]
    if missing:
        raise ValueError(f"missing PaySim columns: {missing}")
    if not df["step"].is_monotonic_increasing:  # non-decreasing
        raise ValueError("rows must be in chronological order (step non-decreasing)")

    store = store if store is not None else DictStore()
    make = TransactionEvent if validate else TransactionEvent.model_construct
    src = list(PAYSIM_COLUMN_MAP)
    dst = [PAYSIM_COLUMN_MAP[c] for c in src]

    index: list = []
    rows: list[list[float]] = []
    for idx, *vals in df[src].itertuples(name=None):
        event = make(**dict(zip(dst, vals)))
        feats = process_event(event, store, cfg)
        if feats is not None:
            index.append(idx)
            rows.append(list(feats.values()))
    return pd.DataFrame(rows, index=pd.Index(index), columns=list(FEATURE_NAMES)), store
