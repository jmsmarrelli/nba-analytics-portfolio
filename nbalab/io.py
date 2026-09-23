"""Storage helpers.

The processed-data layer prefers Parquet but degrades gracefully to gzipped
CSV when ``pyarrow`` is unavailable, so the repository runs in minimal
environments without a code change.  ``load_table`` and ``save_table`` are the
only functions the rest of the codebase should use to touch
``data/processed``.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .config import PROCESSED_DIR

log = logging.getLogger(__name__)

try:  # pragma: no cover - environment dependent
    import pyarrow  # noqa: F401

    PARQUET_AVAILABLE = True
except ImportError:  # pragma: no cover
    PARQUET_AVAILABLE = False


def _paths(name: str) -> tuple[Path, Path]:
    return PROCESSED_DIR / f"{name}.parquet", PROCESSED_DIR / f"{name}.csv.gz"


def save_table(df: pd.DataFrame, name: str) -> Path:
    """Persist ``df`` under ``data/processed/<name>``."""
    parquet_path, csv_path = _paths(name)
    if PARQUET_AVAILABLE:
        df.to_parquet(parquet_path, index=False)
        log.info("wrote %s (%d rows) -> %s", name, len(df), parquet_path.name)
        return parquet_path
    df.to_csv(csv_path, index=False, compression="gzip")
    log.info("wrote %s (%d rows) -> %s", name, len(df), csv_path.name)
    return csv_path


def load_table(name: str) -> pd.DataFrame:
    """Read a processed table, whichever format it was written in."""
    parquet_path, csv_path = _paths(name)
    if parquet_path.exists():
        return pd.read_parquet(parquet_path)
    if csv_path.exists():
        return pd.read_csv(csv_path)
    raise FileNotFoundError(
        f"Processed table {name!r} not found. Run `make data` (or "
        f"`python -m nbalab.pipeline build`) to generate it."
    )


def table_exists(name: str) -> bool:
    return any(p.exists() for p in _paths(name))


def load_stints(seasons: list[int] | int | None = None,
                season_type: str | None = None, eligible_only: bool = True) -> pd.DataFrame:
    """Load the stint table with lineup columns parsed back into tuples.

    A CSV round-trip turns the lineup tuples into their string repr, so they
    are parsed here rather than at every call site.  Parquet preserves the
    object type and skips the parse.
    """
    import ast

    df = load_table("stints")
    if eligible_only and "lineup_eligible" in df:
        df = df[df.lineup_eligible.astype(str).str.lower().eq("true")]
    if seasons is not None:
        wanted = [seasons] if isinstance(seasons, int) else list(seasons)
        df = df[df["season"].isin(wanted)]
    if season_type is not None:
        df = df[df["season_type"] == season_type]

    df = df.copy()
    for col in ("home_lineup", "away_lineup"):
        if len(df) and isinstance(df[col].iloc[0], str):
            df[col] = df[col].map(ast.literal_eval)
    return df.reset_index(drop=True)


def player_names(ids=None) -> pd.Series:
    """Map person id -> display name."""
    p = load_table("players").set_index("player_id")["player_name"]
    return p if ids is None else p.reindex(list(ids))
