"""Build the curated analysis tables from the raw snapshot.

Run as ``python -m nbalab.pipeline build`` (or ``make data``).  Each stage is
idempotent and skippable, so a partially-built cache can be topped up without
recomputing everything.

Stages
------
``players``    person id -> name, debut season, experience
``games``      one row per (game, team) with score, opponent, home flag
``teams``      season-level team ratings: offence, defence, net, pace
``stints``     every span with an unchanging ten-man lineup
``shots``      shot attempts with coordinates and zone labels
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

import numpy as np
import pandas as pd

from . import possessions as P
from .config import SNAPSHOT_SEASONS, season_label, PROCESSED_DIR
from .io import save_table, table_exists, load_table
from .sources import snapshot as S

log = logging.getLogger("nbalab.pipeline")

SEASON_TYPES = ("regular", "playoffs")


# --------------------------------------------------------------------------
# Stages
# --------------------------------------------------------------------------

def build_players(seasons: list[int]) -> pd.DataFrame:
    """Player index with debut season, derived from shot logs.

    Experience is measured as seasons since first recorded appearance.  The
    snapshot starts in 1996-97, so players who debuted earlier are
    left-censored; the ``debut_censored`` flag marks them so that ageing
    curves can exclude them.
    """
    frames = []
    for season in S.available_seasons("shotdetail"):
        for st in SEASON_TYPES:
            try:
                s = S.load_shots(season, st)
            except FileNotFoundError:
                continue
            frames.append(
                s[["player_id", "player_name", "team_id"]]
                .drop_duplicates()
                .assign(season=season)
            )
    df = pd.concat(frames, ignore_index=True)

    idx = df.groupby("player_id").agg(
        first_season=("season", "min"),
        last_season=("season", "max"),
        n_seasons=("season", "nunique"),
    ).reset_index()
    names = (df.sort_values("season").groupby("player_id")["player_name"]
             .last().rename("player_name"))
    idx = idx.merge(names, on="player_id")
    idx["debut_censored"] = idx["first_season"] <= df["season"].min()
    return idx


def build_games(seasons: list[int]) -> pd.DataFrame:
    frames = []
    for season in seasons:
        for st in SEASON_TYPES:
            try:
                frames.append(S.team_game_index(season, st))
            except FileNotFoundError:
                log.warning("no %s data for %s", st, season_label(season))
    return pd.concat(frames, ignore_index=True)


def build_stints(seasons: list[int]) -> pd.DataFrame:
    """Reconstruct lineups and collapse to stints for every season."""
    frames = []
    for season in seasons:
        for st in SEASON_TYPES:
            try:
                pbp = S.load_pbp(season, st)
                rosters = S.game_rosters(season, st)
            except FileNotFoundError:
                continue
            t0 = time.time()
            report = P.ReconstructionReport()
            events = P.build_lineups(pbp, rosters, report)
            if events.empty:
                continue
            events = P.mark_possessions(events)
            stints = P.build_stints(events)
            pd.DataFrame(report.game_audit).assign(season=season, season_type=st).to_csv(PROCESSED_DIR / f"audit_{season}_{st}.csv", index=False)
            links = events[events.actionType.isin(["Made Shot", "Missed Shot"])][["gameId", "actionNumber", "personId", "home_team_id", "away_team_id", "home_lineup", "away_lineup", "lineup_eligible"]]
            links.to_csv(PROCESSED_DIR / f"shot_lineups_{season}_{st}.csv.gz", index=False)
            stints["lineup_clean_rate"] = report.clean_rate
            frames.append(stints)
            log.info(
                "%s %s: %d stints in %.0fs (%s)",
                season_label(season), st, len(stints), time.time() - t0, report,
            )
    return pd.concat(frames, ignore_index=True)


def build_teams(seasons: list[int]) -> pd.DataFrame:
    """Season-level team ratings computed from the stint table.

    Offensive and defensive ratings are points per 100 possessions, derived
    from the same reconstruction the lineup work uses, so every downstream
    number traces back to one consistent possession definition.
    """
    stints = load_table("stints")
    rows = []
    for (season, season_type), g in stints.groupby(["season", "season_type"]):
        home = g.groupby("home_team_id").agg(
            pts=("home_points", "sum"), opp=("away_points", "sum"),
            poss=("possessions", "sum"), secs=("seconds", "sum"),
        )
        away = g.groupby("away_team_id").agg(
            pts=("away_points", "sum"), opp=("home_points", "sum"),
            poss=("possessions", "sum"), secs=("seconds", "sum"),
        )
        tot = home.add(away, fill_value=0)
        tot.index.name = "team_id"
        tot = tot.reset_index()
        # Each stint's possession count covers both teams.
        tot["team_poss"] = tot["poss"] / 2.0
        tot["off_rating"] = 100.0 * tot["pts"] / tot["team_poss"]
        tot["def_rating"] = 100.0 * tot["opp"] / tot["team_poss"]
        tot["net_rating"] = tot["off_rating"] - tot["def_rating"]
        tot["season"] = season
        tot["season_type"] = season_type
        rows.append(tot)

    teams = pd.concat(rows, ignore_index=True)

    games = load_table("games")
    rec = games.groupby(["season", "season_type", "team_id"]).agg(
        games=("won", "size"), wins=("won", "sum"),
        points=("points", "sum"), opp_points=("opp_points", "sum"),
    ).reset_index()
    rec["losses"] = rec["games"] - rec["wins"]
    rec["point_diff"] = (rec["points"] - rec["opp_points"]) / rec["games"]

    out = teams.merge(rec, on=["season", "season_type", "team_id"], how="left")
    out["pace"] = 48.0 * 60.0 * out["team_poss"] / out["secs"]
    return out


def build_shots(seasons: list[int]) -> pd.DataFrame:
    frames = []
    for season in seasons:
        for st in SEASON_TYPES:
            try:
                s = S.load_shots(season, st)
            except FileNotFoundError:
                continue
            keep = [
                "game_id", "game_event_id", "game_date", "season", "season_type", "player_id",
                "player_name", "team_id", "team_name", "period",
                "minutes_remaining", "seconds_remaining", "action_type",
                "shot_type", "shot_zone_basic", "shot_zone_area",
                "shot_zone_range", "shot_distance", "loc_x", "loc_y",
                "shot_attempted_flag", "shot_made_flag",
            ]
            frames.append(s[keep])
    df = pd.concat(frames, ignore_index=True)
    df["is_three"] = df["shot_type"].str.startswith("3PT")
    df["points_if_made"] = np.where(df["is_three"], 3, 2)
    df["seconds_left_period"] = (
        df["minutes_remaining"] * 60 + df["seconds_remaining"]
    )
    return df


STAGES = {
    "players": build_players,
    "games": build_games,
    "stints": build_stints,
    "teams": build_teams,
    "shots": build_shots,
}

# `teams` reads the stint and game tables, so ordering matters.
STAGE_ORDER = ["players", "games", "stints", "teams", "shots"]


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def run(stages: list[str], seasons: list[int], force: bool = False) -> None:
    for name in stages:
        if not force and table_exists(name):
            log.info("skip %s (already built; pass --force to rebuild)", name)
            continue
        log.info("building %s ...", name)
        t0 = time.time()
        df = STAGES[name](seasons)
        save_table(df, name)
        log.info("  %s: %d rows in %.0fs", name, len(df), time.time() - t0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nbalab.pipeline")
    parser.add_argument("command", choices=["build", "list"])
    parser.add_argument("--stages", nargs="*", default=STAGE_ORDER,
                        choices=STAGE_ORDER)
    parser.add_argument("--seasons", nargs="*", type=int, default=SNAPSHOT_SEASONS)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.command == "list":
        for name in STAGE_ORDER:
            print(f"{name:10s} {'built' if table_exists(name) else '-'}")
        return 0

    ordered = [s for s in STAGE_ORDER if s in args.stages]
    run(ordered, args.seasons, force=args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
