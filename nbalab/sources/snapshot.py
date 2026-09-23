"""Readers for the raw, immutable data snapshot.

The snapshot is the offline backend.  It contains three families of files,
one per season, sourced from ``stats.nba.com`` endpoints:

``shotdetail_<season>.csv``   every field-goal attempt with court coordinates
``nbastatsv3_<season>.csv``   full play-by-play, including substitutions
``matchups_<season>.csv``     player-vs-player defensive matchup possessions

Each family also has a ``_po_`` playoff variant.  Season labels use the start
year, so ``2025`` is the 2025-26 season.
"""

from __future__ import annotations

import logging
from functools import lru_cache

import pandas as pd

from ..config import RAW_DIR

log = logging.getLogger(__name__)

SEASON_TYPES = {"regular": "", "playoffs": "po_"}


def _path(family: str, season: int, season_type: str = "regular"):
    if season_type not in SEASON_TYPES:
        raise ValueError(
            f"season_type must be one of {sorted(SEASON_TYPES)}, got {season_type!r}"
        )
    return RAW_DIR / f"{family}_{SEASON_TYPES[season_type]}{season}.csv"


def available_seasons(family: str = "shotdetail") -> list[int]:
    """Season start-years present in the snapshot for a given family."""
    seasons = set()
    for p in RAW_DIR.glob(f"{family}_*.csv"):
        stem = p.stem.replace(f"{family}_", "").replace("po_", "")
        if stem.isdigit():
            seasons.add(int(stem))
    return sorted(seasons)


def load_shots(season: int, season_type: str = "regular") -> pd.DataFrame:
    """Shot-level data with a parsed date and a tidy column set."""
    df = pd.read_csv(_path("shotdetail", season, season_type))
    df = df.rename(columns=str.lower)
    df["game_date"] = pd.to_datetime(df["game_date"], format="%Y%m%d")
    df["season"] = season
    df["season_type"] = season_type
    return df


def load_pbp(season: int, season_type: str = "regular",
             usecols: list[str] | None = None) -> pd.DataFrame:
    """Play-by-play events in chronological order within each game."""
    df = pd.read_csv(_path("nbastatsv3", season, season_type), usecols=usecols)
    df["season"] = season
    df["season_type"] = season_type
    return df


def load_matchups(season: int, season_type: str = "regular") -> pd.DataFrame:
    """Player-vs-player matchup possessions."""
    df = pd.read_csv(_path("matchups", season, season_type))
    df["season"] = season
    df["season_type"] = season_type
    return df


@lru_cache(maxsize=32)
def game_rosters(season: int, season_type: str = "regular") -> pd.DataFrame:
    """One row per (game, team, player) with a starter flag.

    Derived from the matchups file, which is the only snapshot source that
    reliably ties a player id to a team *within a specific game* -- essential
    for resolving the last-name-only references in substitution text.  The
    ``position`` field is populated only for starters, which gives us the
    starting five for free.
    """
    m = load_matchups(season, season_type)
    cols = ["game_id", "team_id", "team_tricode", "person_id",
            "first_name", "family_name", "position"]
    r = m[cols].drop_duplicates(subset=["game_id", "team_id", "person_id"])
    r = r.copy()
    r["is_starter"] = r["position"].notna()
    r["full_name"] = r["first_name"].fillna("") + " " + r["family_name"].fillna("")
    r["full_name"] = r["full_name"].str.strip()
    return r.reset_index(drop=True)


def team_game_index(season: int, season_type: str = "regular") -> pd.DataFrame:
    """One row per (game, team) with opponent, home flag and final score."""
    pbp = load_pbp(
        season, season_type,
        usecols=["gameId", "teamId", "scoreHome", "scoreAway", "location",
                 "actionNumber", "actionId"],
    )
    # Replay revisions can move actionNumber out of chronological order.
    # Use the last actionId score; score corrections can reduce a total.
    finals = (
        pbp.sort_values(["gameId", "actionId"]).groupby("gameId")[["scoreHome", "scoreAway"]]
        .last()
        .reset_index()
    )

    # Home/away team ids come from the location flag on team events.
    sides = (
        pbp[pbp["teamId"] > 0][["gameId", "teamId", "location"]]
        .dropna()
        .drop_duplicates()
    )
    home = (sides[sides["location"] == "h"]
            .drop_duplicates("gameId")
            .rename(columns={"teamId": "home_team_id"})[["gameId", "home_team_id"]])
    away = (sides[sides["location"] == "v"]
            .drop_duplicates("gameId")
            .rename(columns={"teamId": "away_team_id"})[["gameId", "away_team_id"]])

    g = finals.merge(home, on="gameId").merge(away, on="gameId")

    rows = []
    for side, team_col, opp_col, pts_col, opp_pts_col, is_home in (
        ("home", "home_team_id", "away_team_id", "scoreHome", "scoreAway", True),
        ("away", "away_team_id", "home_team_id", "scoreAway", "scoreHome", False),
    ):
        part = g[["gameId", team_col, opp_col, pts_col, opp_pts_col]].copy()
        part.columns = ["game_id", "team_id", "opponent_id", "points", "opp_points"]
        part["is_home"] = is_home
        rows.append(part)

    out = pd.concat(rows, ignore_index=True)
    out["won"] = out["points"] > out["opp_points"]
    out["season"] = season
    out["season_type"] = season_type
    return out.sort_values(["game_id", "is_home"]).reset_index(drop=True)
