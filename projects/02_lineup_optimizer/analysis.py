"""Evaluate Spurs lineups with shrinkage and a constrained allocation exercise."""

from __future__ import annotations

import logging
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.optimize import linprog

from nbalab import viz
from nbalab.config import SPURS_ID, season_label
from nbalab.io import load_stints, player_names, load_table
from nbalab.ratings import shrink_to_prior, estimate_shrinkage_constant

log = logging.getLogger("project02")
HERE = Path(__file__).parent
FIG = HERE / "figures"
FIG.mkdir(exist_ok=True)

SEASON = 2025
MIN_POSSESSIONS = 25          # floor for a lineup to enter the optimiser
GAME_MINUTES = 48.0
PLAYER_MINUTE_CAP = 36.0      # a defensible ceiling for a full season
LINEUP_MINUTE_CAP = 12.0      # no single unit may dominate the night
STARTER_FLOOR_MINUTES = 8.0   # the starting five must play at least this long
TRAIN_FRACTION = 0.6          # first 60% of the regular season fits the model


# --------------------------------------------------------------------------
# Lineup aggregation
# --------------------------------------------------------------------------

def spurs_stint_rows(stints: pd.DataFrame) -> pd.DataFrame:
    """Every Spurs stint, oriented so the Spurs are always the offence."""
    rows = []
    for side, own, pts, opp_pts in (
        ("home", "home_team_id", "home_points", "away_points"),
        ("away", "away_team_id", "away_points", "home_points"),
    ):
        part = stints[stints[own] == SPURS_ID]
        if part.empty:
            continue
        lineup_col = "home_lineup" if side == "home" else "away_lineup"
        rows.append(pd.DataFrame({
            "game_id": part["game_id"].values,
            "lineup": part[lineup_col].values,
            "points": part[pts].values,
            "opp_points": part[opp_pts].values,
            "possessions": part["possessions"].values / 2.0,
            "seconds": part["seconds"].values,
            "season_type": part["season_type"].values,
        }))
    return pd.concat(rows, ignore_index=True)


def spurs_lineups(stints: pd.DataFrame) -> pd.DataFrame:
    """Collapse stints into one row per Spurs five-man unit."""
    df = spurs_stint_rows(stints) if "home_lineup" in stints.columns else stints

    agg = df.groupby("lineup").agg(
        points=("points", "sum"),
        opp_points=("opp_points", "sum"),
        possessions=("possessions", "sum"),
        seconds=("seconds", "sum"),
    ).reset_index()
    agg["minutes"] = agg["seconds"] / 60.0
    agg = agg[agg["possessions"] > 0].copy()
    agg["off_rating"] = 100 * agg["points"] / agg["possessions"]
    agg["def_rating"] = 100 * agg["opp_points"] / agg["possessions"]
    agg["net_rating"] = agg["off_rating"] - agg["def_rating"]
    return agg.sort_values("possessions", ascending=False).reset_index(drop=True)


def player_on_court(lineups: pd.DataFrame) -> pd.DataFrame:
    """Per-player on-court totals derived from the lineup table."""
    acc = defaultdict(lambda: {"poss": 0.0, "pts": 0.0, "opp": 0.0, "sec": 0.0})
    for r in lineups.itertuples():
        for pid in r.lineup:
            a = acc[pid]
            a["poss"] += r.possessions
            a["pts"] += r.points
            a["opp"] += r.opp_points
            a["sec"] += r.seconds
    out = pd.DataFrame([
        {"player_id": pid, "possessions": v["poss"], "points": v["pts"],
         "opp_points": v["opp"], "minutes": v["sec"] / 60.0}
        for pid, v in acc.items()
    ])
    out["on_net"] = 100 * (out["points"] - out["opp_points"]) / out["possessions"]

    total_poss = lineups["possessions"].sum()
    total_pts = lineups["points"].sum()
    total_opp = lineups["opp_points"].sum()
    off_poss = total_poss - out["possessions"]
    out["off_net"] = 100 * (
        (total_pts - out["points"]) - (total_opp - out["opp_points"])
    ) / off_poss.replace(0, np.nan)
    out["on_off"] = out["on_net"] - out["off_net"]
    return out.sort_values("minutes", ascending=False).reset_index(drop=True)


def pair_synergy(lineups: pd.DataFrame, players: pd.DataFrame,
                 min_possessions: int = 100) -> pd.DataFrame:
    """Two-man net rating relative to the additive expectation.

    A duo's expected joint effect is taken as the sum of the two players'
    individual on-court net ratings minus the team baseline (so the team
    effect is not counted twice).  Synergy is the residual.
    """
    team_net = 100 * (lineups["points"].sum() - lineups["opp_points"].sum()) \
        / lineups["possessions"].sum()
    solo = players.set_index("player_id")["on_net"]

    acc = defaultdict(lambda: {"poss": 0.0, "pts": 0.0, "opp": 0.0})
    for r in lineups.itertuples():
        for a, b in combinations(sorted(r.lineup), 2):
            k = (a, b)
            acc[k]["poss"] += r.possessions
            acc[k]["pts"] += r.points
            acc[k]["opp"] += r.opp_points

    rows = []
    for (a, b), v in acc.items():
        if v["poss"] < min_possessions or a not in solo or b not in solo:
            continue
        actual = 100 * (v["pts"] - v["opp"]) / v["poss"]
        expected = solo[a] + solo[b] - team_net
        rows.append({"player_a": a, "player_b": b, "possessions": v["poss"],
                     "actual_net": actual, "expected_net": expected,
                     "synergy": actual - expected})
    return pd.DataFrame(rows).sort_values("synergy", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------
# Optimisation
# --------------------------------------------------------------------------

def optimise_minutes(lineups: pd.DataFrame, rotation: list[int],
                     starters: tuple[int, ...] | None = None,
                     minute_cap: float = PLAYER_MINUTE_CAP,
                     lineup_cap: float = LINEUP_MINUTE_CAP,
                     minutes_to_allocate: float = GAME_MINUTES,
                     n_games: int = 82) -> pd.DataFrame:
    """Linear program over lineup minutes.

    Decision variables
        ``m_j`` -- minutes assigned to lineup ``j`` (all five members must be
        in the rotation).

    Objective
        maximise ``sum_j net_j * m_j`` using the shrunk net ratings.

    Constraints
        * ``sum_j m_j == 48`` -- exactly one lineup is on the floor at a time.
        * for each player, ``sum_{j : p in j} m_j <= minute_cap``.
        * no single unit plays more than ``lineup_cap`` minutes, because a
          solution that runs one five-man unit for 30 minutes a night is not
          a rotation.
        * the starting unit plays at least ``STARTER_FLOOR_MINUTES``.

    The point of the exercise is not to claim a coach should follow the
    solution literally -- it ignores fatigue, foul trouble and opponent
    matchups -- but to bound how much net rating was plausibly on the table.
    Crucially, the ratings fed in here come from the *training* half of the
    season and the result is scored on the held-out half; optimising and
    evaluating on the same data produces a number like +35 per 100, which is
    an artefact rather than a finding.
    """
    pool = set(rotation)
    cand = lineups[lineups["lineup"].map(lambda lu: set(lu) <= pool)].copy()
    cand = cand[cand["possessions"] >= MIN_POSSESSIONS].reset_index(drop=True)
    if cand.empty:
        raise ValueError("no candidate lineups meet the possession floor")

    n = len(cand)
    c = -cand["net_shrunk"].to_numpy()          # linprog minimises

    A_eq = np.ones((1, n))
    b_eq = np.array([minutes_to_allocate])

    A_ub, b_ub = [], []
    for pid in rotation:
        row = cand["lineup"].map(lambda lu: 1.0 if pid in lu else 0.0).to_numpy()
        A_ub.append(row)
        b_ub.append(minute_cap)

    if starters is not None:
        key = tuple(sorted(starters))
        row = cand["lineup"].map(lambda lu: -1.0 if tuple(sorted(lu)) == key else 0.0)
        if row.abs().sum() > 0:
            A_ub.append(row.to_numpy())
            b_ub.append(-STARTER_FLOOR_MINUTES)

    res = linprog(c, A_ub=np.array(A_ub), b_ub=np.array(b_ub),
                  A_eq=A_eq, b_eq=b_eq, bounds=(0, lineup_cap),
                  method="highs")
    if not res.success:
        raise RuntimeError(f"LP failed: {res.message}")

    cand["optimal_minutes"] = res.x
    cand["actual_minutes_per_game"] = cand["minutes"] / max(n_games, 1)
    return cand.sort_values("optimal_minutes", ascending=False).reset_index(drop=True)


def holdout_ratings(test: pd.DataFrame) -> pd.Series:
    """Shrunk holdout net rating per lineup, keyed by lineup tuple.

    The holdout half of a season is short, so raw per-unit rates there are
    themselves mostly noise.  Shrinking them toward the holdout team mean
    lowers the variance of the evaluation without biasing it: the shrinkage
    depends only on holdout data, and the *selection* being graded was made
    on training data, so the two are independent.
    """
    prior = 100 * (test["points"].sum() - test["opp_points"].sum()) / test["possessions"].sum()
    est = estimate_shrinkage_constant(test["net_rating"], test["possessions"], prior)
    shrunk = shrink_to_prior(test["net_rating"], test["possessions"],
                             prior=prior, prior_weight=est["k"])
    return pd.Series(shrunk.values, index=test["lineup"].map(tuple))


def evaluate_allocation(allocation: pd.Series, lineup_key: pd.Series,
                        truth: pd.Series, fallback: float) -> tuple[float, float]:
    """Score a minute allocation against out-of-sample lineup performance.

    Units never seen in the holdout are scored at ``fallback`` (the holdout
    team mean) rather than dropped, so allocations are compared over the same
    48 minutes regardless of which units each one happens to favour --
    dropping them would quietly reward an allocation for concentrating
    minutes in units the holdout happened to cover.
    """
    keys = lineup_key.map(tuple)
    rated = keys.map(truth)
    coverage = float(allocation[rated.notna()].sum() / allocation.sum())
    rated = rated.fillna(fallback)
    value = float((rated * allocation).sum() / allocation.sum())
    return value, coverage


def null_distribution(train: pd.DataFrame, rotation: list[int],
                      starters: tuple[int, ...], test_ratings: pd.Series,
                      fallback: float, n_games: int, n_draws: int = 200,
                      seed: int = 0) -> np.ndarray:
    """How well would the optimiser do if its inputs were pure noise?

    The training net ratings are shuffled across units and the same linear
    program is re-solved, then scored on the same holdout.  This isolates the
    one thing worth knowing: whether optimising on *signal* beats optimising
    on a ranking that contains none.  Any allocation that concentrates
    minutes in a handful of units will look good or bad partly by luck, and
    this measures exactly how much luck is available.
    """
    rng = np.random.default_rng(seed)
    shuffled = train.copy()
    values = train["net_shrunk"].to_numpy()
    out = []
    for _ in range(n_draws):
        shuffled["net_shrunk"] = rng.permutation(values)
        try:
            opt = optimise_minutes(shuffled, rotation, starters, n_games=n_games)
        except (ValueError, RuntimeError):
            continue
        v, _ = evaluate_allocation(opt["optimal_minutes"], opt["lineup"],
                                   test_ratings, fallback)
        out.append(v)
    return np.array(out)


# --------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------

def display_name(value):
    parts=str(value).split()
    return " ".join(parts[-2:]) if parts[-1] in ["Jr.", "II", "III", "IV"] else parts[-1]

def fig_lineup_ratings(lineups: pd.DataFrame, names: pd.Series) -> None:
    top = lineups[lineups["possessions"] >= 100].nlargest(10, "net_shrunk")
    bot = lineups[lineups["possessions"] >= 100].nsmallest(10, "net_shrunk")
    show = pd.concat([top, bot]).drop_duplicates("lineup").sort_values("net_shrunk")

    labels = [" / ".join(display_name(names.get(p,p)) for p in lu)
              for lu in show["lineup"]]
    colors = [viz.CATEGORICAL[0] if v >= 0 else viz.CATEGORICAL[7]
              for v in show["net_shrunk"]]

    fig, ax = plt.subplots(figsize=(10, 8))
    y = np.arange(len(show))
    ax.barh(y, show["net_shrunk"], color=colors, height=0.72)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8.5)
    ax.axvline(0, color=viz.INK_SECONDARY, linewidth=1)
    ax.set_xlabel("Net rating per 100 possessions (shrunk)")
    for yi, (v, p) in enumerate(zip(show["net_shrunk"], show["possessions"])):
        ax.text(v + (0.4 if v >= 0 else -0.4), yi, f"{v:+.1f}",
                va="center", ha="left" if v >= 0 else "right",
                fontsize=8.5, color=viz.INK_SECONDARY)
    viz.annotate(
        ax, "San Antonio's best and worst five-man units",
        f"{season_label(SEASON)}, regular season and playoffs · minimum 100 possessions · "
        "ratings shrunk toward the team mean",
    )
    ax.margins(x=0.14)
    viz.save(fig, FIG / "lineup_ratings.png")


def fig_minute_reallocation(opt: pd.DataFrame, rotation: list[int],
                            names: pd.Series) -> pd.DataFrame:
    """Per-player minutes under the optimum versus what actually happened."""
    rows = []
    for pid in rotation:
        mask = opt["lineup"].map(lambda lu: pid in lu)
        rows.append({
            "player_id": pid,
            "optimal": float(opt.loc[mask, "optimal_minutes"].sum()),
            "actual": float(opt.loc[mask, "baseline_minutes"].sum()),
        })
    df = pd.DataFrame(rows)
    df["name"] = df["player_id"].map(names)
    df["delta"] = df["optimal"] - df["actual"]
    df = df.sort_values("delta")

    fig, ax = plt.subplots(figsize=(9, 6.5))
    y = np.arange(len(df))
    colors = [viz.CATEGORICAL[0] if d >= 0 else viz.CATEGORICAL[1] for d in df["delta"]]
    ax.barh(y, df["delta"], color=colors, height=0.7)
    ax.set_yticks(y)
    ax.set_yticklabels(df["name"], fontsize=10)
    ax.axvline(0, color=viz.INK_SECONDARY, linewidth=1)
    ax.set_xlabel("Change in minutes per game under the optimised rotation")
    for yi, d in enumerate(df["delta"]):
        ax.text(d + (0.2 if d >= 0 else -0.2), yi, f"{d:+.1f}", va="center",
                ha="left" if d >= 0 else "right", fontsize=9,
                color=viz.INK_SECONDARY)
    viz.annotate(
        ax, "Player minutes: optimized versus normalized training allocation",
        "Linear program over five-man units · 36-minute per-player cap · "
        f"{season_label(SEASON)} lineup ratings",
    )
    ax.margins(x=0.18)
    viz.save(fig, FIG / "minute_reallocation.png")
    return df


def fig_synergy(pairs: pd.DataFrame, names: pd.Series) -> None:
    show = pd.concat([pairs.head(8), pairs.tail(8)]).sort_values("synergy")
    labels = [f"{display_name(names.get(a,a))} + {display_name(names.get(b,b))}"
              for a, b in zip(show["player_a"], show["player_b"])]
    colors = [viz.CATEGORICAL[2] if v >= 0 else viz.CATEGORICAL[1]
              for v in show["synergy"]]

    fig, ax = plt.subplots(figsize=(9, 7))
    y = np.arange(len(show))
    ax.barh(y, show["synergy"], color=colors, height=0.7)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    ax.axvline(0, color=viz.INK_SECONDARY, linewidth=1)
    ax.set_xlabel("Net rating above the additive expectation (per 100)")
    for yi, v in enumerate(show["synergy"]):
        ax.text(v + (0.15 if v >= 0 else -0.15), yi, f"{v:+.1f}", va="center",
                ha="left" if v >= 0 else "right", fontsize=8.5,
                color=viz.INK_SECONDARY)
    viz.annotate(
        ax, "Two-man ratings relative to an additive on-court reference",
        "Synergy = observed duo net rating minus the additive expectation · "
        "minimum 100 shared possessions",
    )
    ax.margins(x=0.2)
    viz.save(fig, FIG / "pair_synergy.png")


def fig_shrinkage(lineups: pd.DataFrame) -> None:
    """Show what shrinkage does: raw ratings against sample size, then shrunk."""
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.8), sharey=True)
    prior = lineups.attrs["prior"]
    s = lineups.attrs["s"]

    n = np.linspace(5, lineups["possessions"].max(), 300)
    band = 1.96 * s / np.sqrt(n)

    for ax, col, title in (
        (axes[0], "net_rating", "Raw net rating"),
        (axes[1], "net_shrunk", "After empirical-Bayes shrinkage"),
    ):
        ax.scatter(lineups["possessions"], lineups[col], s=14, alpha=0.55,
                   color=viz.CATEGORICAL[0], linewidths=0)
        ax.axhline(prior, color=viz.INK_SECONDARY, linewidth=1.2, zorder=3)
        ax.set_xscale("log")
        ax.set_xlabel("Possessions played by the unit (log scale)")
        ax.set_title(title, fontsize=11.5)
        ax.set_ylim(-120, 120)

    axes[0].plot(n, prior + band, color=viz.CATEGORICAL[1], linewidth=1.6,
                 linestyle="--", zorder=4)
    axes[0].plot(n, prior - band, color=viz.CATEGORICAL[1], linewidth=1.6,
                 linestyle="--", zorder=4)
    axes[0].text(n[120], prior + band[120] + 6,
                 "95% band expected from noise alone", fontsize=8.5,
                 color=viz.CATEGORICAL[1])
    axes[0].set_ylabel("Net rating per 100 possessions")

    fig.suptitle("Small-sample lineups say almost nothing until they are shrunk",
                 x=0.005, ha="left", fontsize=13, fontweight="semibold")
    fig.text(0.005, 0.925,
             f"San Antonio, {season_label(SEASON)} · every five-man unit · "
             f"half-weight reached at k = {lineups.attrs['k']:.0f} possessions",
             fontsize=10, color=viz.INK_SECONDARY, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    viz.save(fig, FIG / "shrinkage.png")


def fig_null(null_gain: np.ndarray, observed: float) -> None:
    """The result that matters: signal versus a shuffled-ratings null."""
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.hist(null_gain, bins=28, color=viz.FIELD_COLOR, edgecolor=viz.SURFACE,
            linewidth=1.2)
    ax.axvline(0, color=viz.INK_SECONDARY, linewidth=1.2)
    ax.axvline(observed, color=viz.CATEGORICAL[1], linewidth=2.4, zorder=5)
    ax.annotate(
        f"optimised on real ratings\n{observed:+.1f} per 100",
        xy=(observed, ax.get_ylim()[1] * 0.72),
        xytext=(observed + 0.6, ax.get_ylim()[1] * 0.86),
        fontsize=9.5, color=viz.CATEGORICAL[1],
        arrowprops=dict(arrowstyle="-", color=viz.CATEGORICAL[1], linewidth=1.2),
    )
    ax.text(null_gain.mean(), ax.get_ylim()[1] * 0.95,
            "optimised on shuffled ratings", fontsize=9.5,
            color=viz.INK_SECONDARY, ha="center")
    ax.set_xlabel("Holdout score gain over the training allocation (per 100 possessions)")
    ax.set_ylabel("Draws")
    viz.annotate(
        ax, "Does the rotation optimiser beat luck?",
        "Fixed constraints and holdout; compare observed ratings with 200 shuffled rankings",
    )
    viz.save(fig, FIG / "null_test.png")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    viz.use_theme()

    stints = load_stints(seasons=SEASON)
    rows = spurs_stint_rows(stints)

    # --- chronological split ------------------------------------------------
    dates = load_table("shots").groupby("game_id").game_date.min()
    reg = rows.loc[rows.season_type.eq("regular"), "game_id"].unique()
    reg_games = dates.reindex(reg).sort_values().index.tolist()
    cut = int(len(reg_games) * TRAIN_FRACTION)
    train_rows = rows[rows.game_id.isin(reg_games[:cut])]
    test_rows = rows[rows.game_id.isin(reg_games[cut:])]
    n_train_games = train_rows["game_id"].nunique()
    n_test_games = test_rows["game_id"].nunique()

    lineups = spurs_lineups(rows)                 # full season, for description
    train = spurs_lineups(train_rows)
    test = spurs_lineups(test_rows)

    log.info("Spurs five-man units observed: %d over %.0f minutes",
             len(lineups), lineups["minutes"].sum())
    log.info("Split: %d training games / %d holdout games",
             n_train_games, n_test_games)

    names = player_names()

    def add_shrunk(df: pd.DataFrame) -> pd.DataFrame:
        prior = 100 * (df["points"].sum() - df["opp_points"].sum()) / df["possessions"].sum()
        est = estimate_shrinkage_constant(df["net_rating"], df["possessions"], prior)
        df = df.copy()
        df["net_shrunk"] = shrink_to_prior(
            df["net_rating"], df["possessions"], prior=prior, prior_weight=est["k"],
        )
        # Keep only scalars in .attrs -- pandas compares attrs when
        # concatenating, and a DataFrame in there raises.
        df.attrs.update({k: v for k, v in est.items() if np.isscalar(v)})
        df.attrs["prior"] = prior
        return df

    lineups = add_shrunk(lineups)
    train = add_shrunk(train)

    log.info("\nShrinkage fitted on the full season: "
             "true spread tau = %.1f, noise scale s = %.0f, "
             "half-weight at k = %.0f possessions",
             lineups.attrs["tau"], lineups.attrs["s"], lineups.attrs["k"])

    players = player_on_court(lineups)
    players["name"] = players["player_id"].map(names)

    rotation = player_on_court(train).nlargest(10, "minutes")["player_id"].tolist()
    starters = tuple(train.nlargest(1, "possessions")["lineup"].iloc[0])

    log.info("\nRotation players by minutes:\n%s",
             players.head(12)[["name", "minutes", "on_net", "on_off"]]
             .round(2).to_string(index=False))

    pairs = pair_synergy(lineups, players)

    # --- optimise on train, score on holdout --------------------------------
    opt = optimise_minutes(train, rotation, starters, n_games=n_train_games)

    test_prior = train.attrs["prior"]
    test_ratings = holdout_ratings(test)

    test_net, coverage = evaluate_allocation(
        opt["optimal_minutes"], opt["lineup"], test_ratings, test_prior)
    actual_alloc = opt["minutes"] / max(n_train_games, 1)
    actual_alloc = actual_alloc * GAME_MINUTES / actual_alloc.sum()
    opt["baseline_minutes"] = actual_alloc
    actual_net, _ = evaluate_allocation(
        actual_alloc, opt["lineup"], test_ratings, test_prior)

    in_sample = float((opt["net_shrunk"] * opt["optimal_minutes"]).sum() / GAME_MINUTES)
    team_net = lineups.attrs["prior"]

    null = null_distribution(train, rotation, starters, test_ratings,
                             test_prior, n_train_games)
    headroom = test_net - actual_net
    null_gain = null - actual_net
    pctile = float((null_gain < headroom).mean() * 100) if len(null_gain) else float("nan")

    log.info("\n%s", "-" * 68)
    log.info("Team net rating, as played (full season)        %+7.2f", team_net)
    log.info("Optimiser's own estimate (in sample)            %+7.2f  <- optimistic",
             in_sample)
    log.info("%s", "-" * 68)
    log.info("Scored on held-out games, same candidate units:")
    log.info("  optimised allocation                          %+7.2f  (%.0f%% of units seen again)",
             test_net, 100 * coverage)
    log.info("  actual allocation                             %+7.2f", actual_net)
    log.info("  difference                                    %+7.2f per 100", headroom)
    log.info("Null: same LP on shuffled ratings, %d draws", len(null))
    log.info("  null gain mean %+.2f, sd %.2f, 95th pct %+.2f",
             null_gain.mean(), null_gain.std(), np.percentile(null_gain, 95))
    log.info("  observed gain sits at the %.0fth percentile of the null", pctile)
    log.info("%s", "-" * 68)

    fig_lineup_ratings(lineups, names)
    deltas = fig_minute_reallocation(opt, rotation, names)
    fig_synergy(pairs, names)
    fig_shrinkage(lineups)
    fig_null(null_gain, headroom)

    summary = pd.DataFrame([{
        "team_net_as_played": team_net,
        "optimiser_in_sample": in_sample,
        "optimised_holdout": test_net,
        "actual_holdout": actual_net,
        "headroom": headroom,
        "null_gain_mean": float(null_gain.mean()),
        "null_gain_sd": float(null_gain.std()),
        "headroom_percentile_vs_null": pctile,
        "holdout_coverage": coverage,
        "tau": lineups.attrs["tau"],
        "shrinkage_k": lineups.attrs["k"],
        "train_games": n_train_games,
        "test_games": n_test_games,
    }])
    summary.to_csv(HERE / "summary.csv", index=False)
    evaluation = pd.DataFrame({"lineup":opt.lineup.map(str), "optimized_minutes":opt.optimal_minutes, "baseline_minutes":actual_alloc, "holdout_rating":opt.lineup.map(tuple).map(test_ratings).fillna(test_prior)})
    evaluation.to_csv(HERE / "allocation_evaluation.csv", index=False)
    pd.DataFrame({"gain":null_gain}).to_csv(HERE / "null_draws.csv", index=False)

    lineups.assign(
        names=lineups["lineup"].map(lambda lu: " / ".join(str(names.get(p, p)) for p in lu))
    ).to_csv(HERE / "spurs_lineups.csv", index=False)
    deltas.to_csv(HERE / "minute_reallocation.csv", index=False)
    pairs.assign(
        a=pairs["player_a"].map(names), b=pairs["player_b"].map(names)
    ).to_csv(HERE / "pair_synergy.csv", index=False)

    log.info("\nwrote 3 figures and 3 tables to %s", HERE)


if __name__ == "__main__":
    main()
