"""
Utility for loading the PaySim dataset with local Parquet caching.

On first run, reads the raw PaySim CSV and writes a Parquet copy
alongside it. On every subsequent run, loads directly from the
Parquet file, which is dramatically faster than re-parsing a
~470MB / 6.3M-row CSV on every iteration during development.

This is a development-speed convenience only — it has no effect
on model results, evaluation, or the real-time pipeline, and is
separate from the project's real-time architecture entirely.

Usage:
    from data_loader import load_paysim
    df = load_paysim()

Download the raw CSV first from:
    https://www.kaggle.com/datasets/ealaxi/paysim1
and place it at data/raw/paysim.csv (or pass a custom path).

Requires: pandas, pyarrow
    pip install pandas pyarrow
"""

from pathlib import Path
import logging

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_CSV_PATH = Path("data/raw/paysim.csv")
DEFAULT_PARQUET_PATH = Path("D:/Projects/fraud_detection/data/cache/paysim.parquet")


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

    Raises
    ------
    FileNotFoundError
        If no Parquet cache exists and the raw CSV is not found either.
    """
    parquet_path.parent.mkdir(parents=True, exist_ok=True)

    if parquet_path.exists() and not force_rebuild:
        logger.info("Loading PaySim from Parquet cache: %s", parquet_path)
        return pd.read_parquet(parquet_path)

    if not csv_path.exists():
        raise FileNotFoundError(
            f"Raw PaySim CSV not found at {csv_path}. Download it from "
            f"https://www.kaggle.com/datasets/ealaxi/paysim1 and place "
            f"it at this path before running this loader (or pass a "
            f"custom csv_path)."
        )

    logger.info("No Parquet cache found. Reading CSV: %s (slow — one-time cost)", csv_path)
    df = pd.read_csv(csv_path)

    # Dtype tightening — reduces Parquet size and speeds up every
    # subsequent load. Safe because 'type' has low cardinality and
    # the fraud flags are strictly 0/1.
    if "type" in df.columns:
        df["type"] = df["type"].astype("category")
    for col in ("isFraud", "isFlaggedFraud"):
        if col in df.columns:
            df[col] = df[col].astype("int8")

    logger.info("Writing Parquet cache: %s", parquet_path)
    df.to_parquet(parquet_path, engine="pyarrow", index=False)

    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _df = load_paysim()
    print(_df.shape)
    print(_df.dtypes)
