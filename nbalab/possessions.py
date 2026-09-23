"""Reconstruct on-court lineups, stints and possessions from play-by-play.

This is the analytical core of the repository: projects 02, 03 and 08 all
depend on knowing exactly which ten players were on the floor for every
event of every game.  The NBA's public play-by-play does not state that
directly, so it has to be rebuilt.

Three details make this harder than it looks, and each is handled explicitly
below:

1. ``actionNumber`` is not chronological.  Events revised by instant replay
   are re-inserted with out-of-band numbers, so a first-quarter free throw
   can carry a higher ``actionNumber`` than the final buzzer.  ``actionId``
   *is* monotonic and is used as the ordering key.

2. Substitution rows identify only the player leaving the floor
   (``personId``); the player entering appears solely as a last name inside
   the free-text description, e.g. ``"SUB: Eason FOR Smith Jr."``.  Names are
   resolved against a per-game roster, and ambiguous surnames are
   disambiguated by requiring the incoming player to currently be off the
   floor.

3. The five players who start a period are never stated.  They are inferred
   by scanning the period: a player belongs to the period-opening lineup if
   his first involvement is either an event of his own or a substitution
   *out* -- that is, anything other than a substitution *in*.

Every reconstruction is validated (each team must have exactly five players
on the floor at all times) and the failure rate is reported rather than
silently swallowed.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

PERIOD_LENGTH = {1: 720.0, 2: 720.0, 3: 720.0, 4: 720.0}
OT_LENGTH = 300.0

_CLOCK_RE = re.compile(r"PT(\d+)M([\d.]+)S")
_SUB_RE = re.compile(r"SUB:\s*(?P<incoming>.+?)\s+FOR\s+(?P<outgoing>.+?)\s*$")


# --------------------------------------------------------------------------
# Clock handling
# --------------------------------------------------------------------------

def parse_clock(clock: str) -> float:
    """``'PT06M40.00S'`` -> ``400.0`` seconds remaining in the period."""
    m = _CLOCK_RE.match(str(clock))
    if not m:
        return np.nan
    return float(m.group(1)) * 60.0 + float(m.group(2))


def period_length(period: int) -> float:
    return PERIOD_LENGTH.get(int(period), OT_LENGTH)


def game_seconds_elapsed(period: pd.Series, clock_remaining: pd.Series) -> pd.Series:
    """Seconds elapsed since tip-off, continuous across periods and overtimes."""
    period = period.astype(int)
    prior = np.where(
        period <= 4,
        (period - 1) * 720.0,
        2880.0 + (period - 5) * OT_LENGTH,
    )
    return prior + (period.map(period_length) - clock_remaining)


# --------------------------------------------------------------------------
# Lineup reconstruction
# --------------------------------------------------------------------------

@dataclass
class ReconstructionReport:
    """Diagnostics for a lineup rebuild, surfaced instead of hidden."""

    games: int = 0
    clean_games: int = 0
    unresolved_subs: int = 0
    period_lineup_repairs: int = 0
    dropped_games: list[int] = field(default_factory=list)
    game_audit: list[dict] = field(default_factory=list)

    @property
    def clean_rate(self) -> float:
        return self.clean_games / self.games if self.games else float("nan")

    def __str__(self) -> str:
        return (
            f"lineup reconstruction: {self.clean_games}/{self.games} games clean "
            f"({self.clean_rate:.2%}), {self.unresolved_subs} unresolved subs, "
            f"{self.period_lineup_repairs} period-lineup repairs, "
            f"{len(self.dropped_games)} games dropped"
        )


def _normalise_name(name: str) -> str:
    """Fold a display name to a comparable key.

    The roster source carries correctly accented names (``Jokić``,
    ``Dončić``, ``Schröder``) while the play-by-play description text is
    ASCII-folded (``Jokic``, ``Doncic``, ``Schroder``).  Decomposing to NFKD
    and dropping combining marks makes the two agree; without this step
    roughly two substitutions per game fail to resolve.
    """
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.strip().lower()
    s = s.replace(".", "").replace("'", "").replace("’", "").replace("-", " ")
    s = re.sub(r"\s+", " ", s)
    return s


def _build_name_index(roster: pd.DataFrame) -> dict[str, list[int]]:
    """Map every plausible textual reference to the person ids it could mean."""
    index: dict[str, list[int]] = {}
    for row in roster.itertuples():
        keys = {
            _normalise_name(row.family_name),
            _normalise_name(row.full_name),
            _normalise_name(f"{str(row.first_name)[:1]} {row.family_name}"),
        }
        for k in keys:
            if k:
                index.setdefault(k, []).append(row.person_id)
    return index


def _resolve_incoming(name: str, name_index: dict[str, list[int]],
                      on_floor: set[int], roster_ids: set[int]) -> int | None:
    """Resolve the free-text incoming player of a substitution to a person id."""
    key = _normalise_name(name)
    candidates = name_index.get(key)
    if not candidates:
        # Fall back to a suffix match ("Smith Jr." vs "Smith").
        for k, ids in name_index.items():
            if k.startswith(key) or key.startswith(k):
                candidates = ids
                break
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    # Ambiguous surname: the incoming player must currently be off the floor.
    off = [c for c in candidates if c not in on_floor and c in roster_ids]
    if len(off) == 1:
        return off[0]
    return None


def _period_opening_lineup(period_events: pd.DataFrame, team_id: int,
                           roster_ids: set[int]) -> set[int]:
    """Infer which five players opened a period for one team.

    A player opened the period if his first involvement in it was anything
    other than being substituted *in*.
    """
    opened: set[int] = set()
    subbed_in: set[int] = set()

    for ev in period_events.itertuples():
        if ev.teamId != team_id:
            continue
        pid = ev.personId
        if ev.actionType == "Substitution":
            # personId on a sub row is the outgoing player.
            if pid in roster_ids and pid not in subbed_in and pid not in opened:
                opened.add(pid)
            incoming = getattr(ev, "incoming_person_id", None)
            if incoming and not pd.isna(incoming):
                subbed_in.add(int(incoming))
        else:
            if pid in roster_ids and pid not in subbed_in and pid not in opened:
                opened.add(pid)
        if len(opened) >= 5:
            break
    return opened


def build_lineups(pbp: pd.DataFrame, rosters: pd.DataFrame,
                  report: ReconstructionReport | None = None) -> pd.DataFrame:
    """Attach the on-floor five for both teams to every play-by-play event.

    Parameters
    ----------
    pbp
        Raw play-by-play for one or more games, in file order.
    rosters
        Output of :func:`nbalab.sources.snapshot.game_rosters` covering the
        same games.

    Returns
    -------
    DataFrame
        ``pbp`` with ``home_lineup`` / ``away_lineup`` columns holding sorted
        tuples of person ids, plus parsed clock and elapsed-time columns.
    """
    report = report if report is not None else ReconstructionReport()

    df = pbp.copy()
    df["clock_remaining"] = df["clock"].map(parse_clock)
    df["seconds_elapsed"] = game_seconds_elapsed(df["period"], df["clock_remaining"])

    # Pre-parse substitution descriptions once.
    is_sub = df["actionType"] == "Substitution"
    sub_names = df.loc[is_sub, "description"].str.extract(_SUB_RE)
    df["sub_incoming_name"] = pd.Series(pd.NA, index=df.index, dtype="object")
    df.loc[is_sub, "sub_incoming_name"] = sub_names["incoming"].astype("object").values

    roster_by_game = {gid: g for gid, g in rosters.groupby("game_id")}

    out_frames = []
    for game_id, game in df.groupby("gameId", sort=False):
        game = game.sort_values("actionId", kind="stable")
        roster = roster_by_game.get(game_id)
        if roster is None:
            report.dropped_games.append(int(game_id))
            continue

        team_ids = sorted(roster["team_id"].unique())
        if len(team_ids) != 2:
            report.dropped_games.append(int(game_id))
            continue

        report.games += 1
        repairs_before = report.period_lineup_repairs
        unresolved_before = report.unresolved_subs
        roster_ids = {t: set(roster.loc[roster.team_id == t, "person_id"])
                      for t in team_ids}
        name_index = {t: _build_name_index(roster[roster.team_id == t])
                      for t in team_ids}
        starters = {
            t: set(roster.loc[(roster.team_id == t) & roster.is_starter, "person_id"])
            for t in team_ids
        }

        # Resolve incoming person ids for every substitution up front.
        incoming_ids = np.full(len(game), np.nan)
        on_floor_guess = {t: set(starters[t]) for t in team_ids}
        positions = {i: k for k, i in enumerate(game.index)}
        for k, ev in enumerate(game.itertuples()):
            if ev.actionType != "Substitution" or ev.teamId not in roster_ids:
                continue
            pid_in = _resolve_incoming(
                ev.sub_incoming_name, name_index[ev.teamId],
                on_floor_guess[ev.teamId], roster_ids[ev.teamId],
            )
            if pid_in is None:
                report.unresolved_subs += 1
            else:
                incoming_ids[k] = pid_in
                on_floor_guess[ev.teamId].discard(ev.personId)
                on_floor_guess[ev.teamId].add(pid_in)
        game = game.assign(incoming_person_id=incoming_ids)

        # Walk the game period by period, maintaining the on-floor sets.
        home_col, away_col = [], []
        home_id = game.loc[game["location"] == "h", "teamId"]
        home_id = int(home_id[home_id > 0].iloc[0]) if len(home_id[home_id > 0]) else team_ids[0]
        away_id = [t for t in team_ids if t != home_id][0]

        on_floor: dict[int, set[int]] = {}
        for period, pev in game.groupby("period", sort=True):
            for t in team_ids:
                inferred = _period_opening_lineup(pev, t, roster_ids[t])
                if len(inferred) != 5:
                    # Repair: start from the previous period's closing five,
                    # then the declared starters, then anyone inferred.
                    base = set(on_floor.get(t, set())) if period > 1 else set(starters[t])
                    candidates = list(inferred) + [p for p in base if p not in inferred]
                    fixed = set(candidates[:5])
                    if len(fixed) < 5:
                        extra = [p for p in starters[t] if p not in fixed]
                        fixed |= set(extra[: 5 - len(fixed)])
                    if len(fixed) != 5:
                        pool = [p for p in roster_ids[t] if p not in fixed]
                        fixed |= set(pool[: 5 - len(fixed)])
                    report.period_lineup_repairs += 1
                    inferred = fixed
                on_floor[t] = set(inferred)

            for ev in pev.itertuples():
                if (ev.actionType == "Substitution" and ev.teamId in on_floor
                        and not pd.isna(ev.incoming_person_id)):
                    on_floor[ev.teamId].discard(ev.personId)
                    on_floor[ev.teamId].add(int(ev.incoming_person_id))
                home_col.append(tuple(sorted(on_floor[home_id])))
                away_col.append(tuple(sorted(on_floor[away_id])))

        game = game.assign(
            home_team_id=home_id,
            away_team_id=away_id,
            home_lineup=home_col,
            away_lineup=away_col,
        )
        clean = (game["home_lineup"].map(len) == 5).all() and \
                (game["away_lineup"].map(len) == 5).all()
        repairs = report.period_lineup_repairs - repairs_before
        unresolved = report.unresolved_subs - unresolved_before
        if clean:
            report.clean_games += 1
        score_bad = any(game[c].ffill().fillna(0).diff().fillna(0).lt(0).any() for c in ["scoreHome", "scoreAway"])
        clock_bad = game.seconds_elapsed.diff().fillna(0).lt(0).any()
        eligible = clean and repairs == 0 and unresolved == 0 and not score_bad and not clock_bad
        game["lineup_eligible"] = eligible
        report.game_audit.append(dict(game_id=int(game_id), clean_size=bool(clean), repairs=repairs, unresolved_subs=unresolved, score_decrease=bool(score_bad), clock_reversal=bool(clock_bad), lineup_eligible=bool(eligible)))
        out_frames.append(game)

    result = pd.concat(out_frames, ignore_index=True) if out_frames else pd.DataFrame()
    log.info("%s", report)
    return result


# --------------------------------------------------------------------------
# Possessions
# --------------------------------------------------------------------------

def mark_possessions(events: pd.DataFrame) -> pd.DataFrame:
    """Assign a possession index to every event.

    A possession ends on a made field goal, a made final free throw, a
    defensive rebound, a turnover, or the end of a period.  Offensive
    rebounds continue the same possession, which is the standard convention
    and keeps possession counts aligned with the league's published pace.
    """
    df = events.copy()

    desc = df["description"].fillna("")
    action = df["actionType"].fillna("")

    made_fg = (action == "Made Shot")
    turnover = (action == "Turnover")
    period_end = desc.str.contains("End of", na=False)

    # A free throw ends the possession only if it is the last of its set and
    # it was made.  Technical free throws never end a possession -- play
    # resumes with whichever team had the ball -- and the sequence marker can
    # carry a qualifier ("Free Throw Flagrant 2 of 2"), so the regex has to
    # tolerate one.
    ft = action == "Free Throw"
    ft_made = ft & ~desc.str.contains("MISS", na=False)
    ft_technical = desc.str.contains("Technical", na=False)
    ft_seq = desc.str.extract(r"Free Throw (?:\w+ )?(\d+) of (\d+)")
    ft_last = ft_seq[0].astype("float") == ft_seq[1].astype("float")
    ft_last = ft_last.fillna(False)
    special = desc.str.contains("Technical|Flagrant|Clear Path|Away From Play|Transition Take", case=False, na=False)
    ft_end = ft_made & ft_last & ~special
    # An and-one remains live until its free throw or following rebound.
    one = ft & ft_seq[0].eq("1") & ft_seq[1].eq("1") & ~special
    keys = ["gameId", "period", "clock", "personId"]
    one_keys = pd.MultiIndex.from_frame(df.loc[one, keys])
    has_one = pd.MultiIndex.from_frame(df[keys]).isin(one_keys)
    made_fg = made_fg & ~has_one

    # Rebound classification.
    #
    # The description text is *not* usable here: "Wallace REBOUND (Off:0
    # Def:1)" reports the rebounder's running season totals, so every single
    # rebound row contains the substring "Def:".  Using it as a marker
    # inflates possession counts by roughly 15 per team per game.
    #
    # The correct test compares the rebounding team against the team that
    # missed the shot: a rebound by the other team is defensive and ends the
    # possession; a rebound by the shooting team is offensive and continues
    # it.
    reb = action == "Rebound"
    missed = (action == "Missed Shot") | (ft & ~ft_made & ft_last & ~special)
    shooting_team = df["teamId"].where(missed).groupby([df["gameId"], df["period"]]).ffill()
    reb_team = df["teamId"].where(df["teamId"] > 0)
    reb_team = reb_team.fillna(df.personId.where(df.personId.ge(1610612737) & df.personId.le(1610612766)))
    def_reb = reb & shooting_team.notna() & reb_team.notna() & (reb_team != shooting_team)

    ends_live = (made_fg | turnover | ft_end | def_reb).fillna(False).astype(bool)

    # The buzzer ends a possession only if one was actually in progress.  A
    # period that ends on a made basket or a defensive rebound has already
    # had its final possession counted; adding the period-end row on top
    # double-counts roughly two possessions per team per game.
    live_event = (
        made_fg | turnover | (ft & ~special) | reb | (action == "Missed Shot")
    ).fillna(False).astype(bool)

    # The segment boundary falls *after* an ending event, so the event that
    # closed a possession belongs to the segment it closed rather than
    # opening the next one.  Without the shift, a period that ends on a made
    # basket sees that basket as "a live event since the last end" and counts
    # the buzzer as an extra possession.
    grouper = [df["gameId"], df["period"]]
    segment = (ends_live.groupby(grouper).shift(fill_value=False)
               .groupby(grouper).cumsum())
    live_since_end = (
        live_event.groupby([df["gameId"], df["period"], segment]).cumsum() > 0
    )
    period_end_counts = period_end & ~ends_live & live_since_end

    ends = ends_live | period_end_counts
    df["possession_end"] = ends.fillna(False).astype(bool).values
    # The possession index increments *after* an ending event.
    df["possession_id"] = (
        df.groupby("gameId")["possession_end"]
        .transform(lambda s: s.shift(fill_value=False).cumsum())
    )
    return df


def build_stints(events: pd.DataFrame) -> pd.DataFrame:
    """Collapse events into stints: spans with an unchanging ten-man lineup.

    Returns one row per stint with points scored by each side, possessions,
    and elapsed seconds -- the unit of analysis for lineup net ratings.
    """
    df = events.copy()
    key = df["home_lineup"].astype(str) + "|" + df["away_lineup"].astype(str)
    df["stint_break"] = (key != key.shift()) | (df["gameId"] != df["gameId"].shift()) | df["period"].ne(df["period"].shift())
    df["stint_id"] = df["stint_break"].cumsum()

    # Points are read off the running score, which is monotonic within a game.
    df["score_home_ff"] = df.groupby("gameId")["scoreHome"].ffill().fillna(0)
    df["score_away_ff"] = df.groupby("gameId")["scoreAway"].ffill().fillna(0)

    df["home_increment"] = df.groupby("gameId").score_home_ff.diff().fillna(df.score_home_ff)
    df["away_increment"] = df.groupby("gameId").score_away_ff.diff().fillna(df.score_away_ff)
    df["duration"] = (df.groupby("gameId").seconds_elapsed.shift(-1) - df.seconds_elapsed).fillna(0).clip(lower=0)
    if "lineup_eligible" not in df: df["lineup_eligible"] = True
    agg = df.groupby("stint_id").agg(
        game_id=("gameId", "first"),
        season=("season", "first"),
        season_type=("season_type", "first"),
        period=("period", "first"),
        home_team_id=("home_team_id", "first"),
        away_team_id=("away_team_id", "first"),
        home_lineup=("home_lineup", "first"),
        away_lineup=("away_lineup", "first"),
        start_seconds=("seconds_elapsed", "first"),
        end_seconds=("seconds_elapsed", "last"),
        score_home_start=("score_home_ff", "first"),
        score_home_end=("score_home_ff", "last"),
        score_away_start=("score_away_ff", "first"),
        score_away_end=("score_away_ff", "last"),
        possessions=("possession_end", "sum"),
        events=("actionId", "size"),
        seconds=("duration", "sum"),
        home_points=("home_increment", "sum"),
        away_points=("away_increment", "sum"),
        lineup_eligible=("lineup_eligible", "all"),
    ).reset_index()

    agg["end_seconds"] = agg["start_seconds"] + agg["seconds"]
    return agg
