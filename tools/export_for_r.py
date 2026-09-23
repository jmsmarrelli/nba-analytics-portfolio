"""Write plain-CSV extracts for the R projects.

The R side deliberately depends on nothing but base R, so the heavy lifting --
reconstructing lineups, fitting RAPM, joining shots to stints -- happens once
here in Python and lands as small, tidy CSV files.  That keeps the R scripts
about statistics and graphics rather than data engineering, and it means they
run under a bare ``Rscript`` with no installation step.

Run: ``python tools/export_for_r.py``
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nbalab.config import (CONFERENCE_BY_ID, NAME_BY_ID, SPURS_ID,
                           TRICODE_BY_ID, season_label)
from nbalab.io import load_stints, load_table
from nbalab.ratings import rapm

log = logging.getLogger("export_for_r")
OUT = Path(__file__).resolve().parent.parent / "data" / "r_extracts"
OUT.mkdir(parents=True, exist_ok=True)

SEASONS = [2019, 2020, 2021, 2022, 2023, 2024, 2025]
FINALS_GAMES = list(range(42500401, 42500408))   # 2026 Finals, games 1-7


def write(df: pd.DataFrame, name: str) -> None:
    path = OUT / f"{name}.csv"
    df.to_csv(path, index=False)
    log.info("wrote %-28s %6d rows  %s", name, len(df), path.name)


# --------------------------------------------------------------------------

def export_player_seasons() -> None:
    """Player-season RAPM with experience, for the development curves."""
    players = load_table("players").set_index("player_id")
    frames = []
    for s in SEASONS:
        st = load_stints(seasons=s, season_type="regular")
        r = rapm(st, min_possessions=500)
        r["season"] = s
        frames.append(r)
        log.info("  RAPM fitted for %s: %d players", season_label(s), len(r))
    df = pd.concat(frames, ignore_index=True)

    df = df.join(players[["player_name", "first_season", "debut_censored"]],
                 on="player_id")
    df["experience"] = df["season"] - df["first_season"]
    df = df[df["player_name"].notna()]

    # Minutes give each observation a weight.
    mins = []
    for s in SEASONS:
        st = load_stints(seasons=s, season_type="regular")
        acc: dict[int, float] = {}
        for col in ("home_lineup", "away_lineup"):
            for lu, sec in zip(st[col], st["seconds"]):
                for pid in lu:
                    acc[pid] = acc.get(pid, 0.0) + sec / 60.0
        mins.append(pd.DataFrame({"player_id": list(acc), "season": s,
                                  "minutes": list(acc.values())}))
    df = df.merge(pd.concat(mins, ignore_index=True),
                  on=["player_id", "season"], how="left")

    cols = ["player_id", "player_name", "season", "experience",
            "debut_censored", "minutes", "o_rapm", "d_rapm", "rapm"]
    write(df[cols].sort_values(["player_id", "season"]), "player_seasons")


def export_team_style() -> None:
    """Team-season style profile: how a team plays, not how well."""
    shots = load_table("shots")
    shots = shots[shots["season_type"] == "regular"]
    teams = load_table("teams")
    teams = teams[teams["season_type"] == "regular"]

    rows = []
    for (season, team_id), g in shots.groupby(["season", "team_id"]):
        att = len(g)
        rim = (g["shot_distance"] <= 4).sum()
        short_mid = g["shot_distance"].between(5, 15).sum()
        long_mid = g["shot_distance"].between(16, 21).sum()
        three = g["is_three"].sum()
        corner = ((g["shot_zone_basic"] == "Left Corner 3") |
                  (g["shot_zone_basic"] == "Right Corner 3")).sum()
        rows.append({
            "season": season, "team_id": team_id,
            "attempts": att,
            "rim_rate": rim / att,
            "short_mid_rate": short_mid / att,
            "long_mid_rate": long_mid / att,
            "three_rate": three / att,
            "corner_three_share": corner / max(three, 1),
            "avg_shot_distance": g["shot_distance"].mean(),
            "efg": (g["shot_made_flag"].sum()
                    + 0.5 * g.loc[g["is_three"], "shot_made_flag"].sum()) / att,
        })
    style = pd.DataFrame(rows)
    style = style.merge(
        teams[["season", "team_id", "off_rating", "def_rating", "net_rating",
               "pace", "wins", "losses"]],
        on=["season", "team_id"], how="left")
    style["tricode"] = style["team_id"].map(TRICODE_BY_ID)
    style["team_name"] = style["team_id"].map(NAME_BY_ID)
    style["conference"] = style["team_id"].map(CONFERENCE_BY_ID)
    write(style, "team_style")


def export_finals() -> None:
    """Everything needed for the 2026 Finals postmortem."""
    stints = load_stints(seasons=2025, season_type="playoffs", eligible_only=False)
    finals = stints[stints["game_id"].isin(FINALS_GAMES)].copy()
    if finals.empty:
        log.warning("no Finals stints found -- check the game id range")
        return

    finals["spurs_is_home"] = finals["home_team_id"] == SPURS_ID
    finals["spurs_lineup"] = np.where(finals["spurs_is_home"],
                                      finals["home_lineup"],
                                      finals["away_lineup"])
    finals["opp_lineup"] = np.where(finals["spurs_is_home"],
                                    finals["away_lineup"],
                                    finals["home_lineup"])
    finals["spurs_points"] = np.where(finals["spurs_is_home"],
                                      finals["home_points"], finals["away_points"])
    finals["opp_points"] = np.where(finals["spurs_is_home"],
                                    finals["away_points"], finals["home_points"])
    finals["team_possessions"] = finals["possessions"] / 2.0
    finals["game_number"] = finals["game_id"] - 42500400

    names = load_table("players").set_index("player_id")["player_name"]
    finals["spurs_lineup_names"] = finals["spurs_lineup"].map(
        lambda lu: "|".join(str(names.get(p, p)) for p in lu))

    cols = ["game_id", "game_number", "period", "start_seconds", "end_seconds",
            "seconds", "team_possessions", "spurs_points", "opp_points",
            "spurs_lineup_names"]
    write(finals[cols].sort_values(["game_id", "start_seconds"]), "finals_stints")

    # Shot-level detail for the same games, with a rough quality proxy.
    shots = load_table("shots")
    fs = shots[shots["game_id"].isin(FINALS_GAMES)].copy()
    fs["is_spurs"] = fs["team_id"] == SPURS_ID
    fs["game_number"] = fs["game_id"] - 42500400
    fs["zone"] = np.select(
        [fs["shot_distance"] <= 4,
         fs["shot_distance"].between(5, 15),
         fs["shot_distance"].between(16, 21),
         fs["is_three"]],
        ["rim", "short mid", "long mid", "three"], default="other")
    cols = ["game_id", "game_number", "period", "seconds_left_period",
            "player_id", "player_name", "team_id", "is_spurs", "zone",
            "shot_distance", "is_three", "shot_made_flag", "points_if_made"]
    write(fs[cols], "finals_shots")

    # Series-long per-player lines for the Spurs.
    spurs_shots = fs[fs["is_spurs"]]
    per_game = spurs_shots.groupby(
        ["game_number", "player_id", "player_name"]).agg(
        attempts=("shot_made_flag", "size"),
        makes=("shot_made_flag", "sum"),
        points=("points_if_made", lambda s: 0),
    ).reset_index()
    pts = (spurs_shots.assign(pts=spurs_shots["shot_made_flag"]
                              * spurs_shots["points_if_made"])
           .groupby(["game_number", "player_id"])["pts"].sum())
    per_game["points"] = per_game.set_index(
        ["game_number", "player_id"]).index.map(pts)
    write(per_game, "finals_player_games")


def export_spurs_lineups() -> None:
    """Spurs five-man units across the full 2025-26 season."""
    rows = []
    for st in ("regular", "playoffs"):
        stints = load_stints(seasons=2025, season_type=st)
        for side, own, pts, opp in (("home", "home_team_id", "home_points", "away_points"),
                                    ("away", "away_team_id", "away_points", "home_points")):
            part = stints[stints[own] == SPURS_ID]
            if part.empty:
                continue
            lineup_col = "home_lineup" if side == "home" else "away_lineup"
            rows.append(pd.DataFrame({
                "lineup": part[lineup_col].values,
                "points": part[pts].values,
                "opp_points": part[opp].values,
                "possessions": part["possessions"].values / 2.0,
                "seconds": part["seconds"].values,
                "season_type": st,
            }))
    df = pd.concat(rows, ignore_index=True)
    names = load_table("players").set_index("player_id")["player_name"]
    agg = df.groupby([df["lineup"].map(tuple), "season_type"]).agg(
        points=("points", "sum"), opp_points=("opp_points", "sum"),
        possessions=("possessions", "sum"), seconds=("seconds", "sum"),
    ).reset_index()
    agg.columns = ["lineup", "season_type", "points", "opp_points",
                   "possessions", "seconds"]
    agg["lineup_names"] = agg["lineup"].map(
        lambda lu: "|".join(str(names.get(p, p)) for p in lu))
    agg["minutes"] = agg["seconds"] / 60.0
    agg = agg[agg["possessions"] > 0]
    agg["net_rating"] = 100 * (agg["points"] - agg["opp_points"]) / agg["possessions"]
    write(agg.drop(columns=["lineup"]), "spurs_lineups")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log.info("writing R extracts to %s\n", OUT)
    export_team_style()
    export_finals()
    export_spurs_lineups()
    export_player_seasons()
    log.info("\ndone")


if __name__ == "__main__":
    main()
