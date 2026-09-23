"""Shared shrinkage, game-grouped ridge ratings and shooting-rate calculations."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Shrinkage
# --------------------------------------------------------------------------

def estimate_shrinkage_constant(values: pd.Series, weights: pd.Series,
                                prior: float, n_bins: int = 12,
                                min_sample: float = 20.0) -> dict:
    """Empirical-Bayes estimate of how hard to shrink, fitted from the data.

    For a rate measured over ``n`` possessions the observed variance around
    the true value decomposes as

        Var(y_i) = tau^2 + s^2 / n_i

    where ``tau^2`` is the genuine spread of unit quality and ``s^2`` is the
    per-possession noise scale.  The two terms are estimated separately --
    ``s^2`` from the slope of within-bin variance against ``1 / n``, and
    ``tau^2`` from a moment identity over the well-sampled units -- for
    reasons documented at each step below.  The shrinkage constant is then
    ``k = s^2 / tau^2``, the number of possessions at which a unit's own
    sample and the prior deserve equal weight.

    This matters more than it might appear.  A five-man lineup that plays 28
    possessions has a sampling standard deviation of roughly 23 points per
    100; without a defensible ``k``, a 28-possession unit that happened to go
    +45 will outrank a 900-possession unit that went +9, and any optimiser
    built on those numbers will chase noise.
    """
    values = pd.Series(values).astype(float).reset_index(drop=True)
    weights = pd.Series(weights).astype(float).reset_index(drop=True)
    mask = weights > 0
    values, weights = values[mask], weights[mask]

    # Bin by sample size on a log scale so each bin spans a similar ratio.
    order = weights.rank(method="first")
    bins = pd.qcut(order, min(n_bins, max(2, len(values) // 8)),
                   labels=False, duplicates="drop")

    rows = []
    for b, idx in pd.Series(bins).groupby(bins):
        sel = values.iloc[idx.index]
        w = weights.iloc[idx.index]
        if len(sel) < 4:
            continue
        rows.append({
            "inv_n": float((1.0 / w).mean()),
            "var": float(((sel - prior) ** 2).mean()),
            "count": len(sel),
        })
    fit = pd.DataFrame(rows)
    if len(fit) < 3:
        return {"tau2": np.nan, "s2": np.nan, "k": 400.0, "fit": fit}

    # --- noise scale -------------------------------------------------------
    # Regress bin variance on 1/n through the origin's slope term.  The
    # intercept of this fit is *not* usable as tau^2: the small-sample bins
    # have enormous leverage and the relationship is only asymptotically
    # linear, which biases the intercept upward by an order of magnitude.
    # The slope, however, is well identified and recovers the analytic
    # value: a per-possession margin standard deviation of ~1.5 points
    # implies s = 150 on a per-100 scale.
    X = np.column_stack([np.ones(len(fit)), fit["inv_n"].to_numpy()])
    W = np.diag(fit["count"].to_numpy().astype(float))
    beta = np.linalg.lstsq(np.sqrt(W) @ X, np.sqrt(W) @ fit["var"].to_numpy(),
                           rcond=None)[0]
    s2 = float(beta[1])
    if not np.isfinite(s2) or s2 <= 0:
        s2 = 150.0 ** 2

    # --- signal scale ------------------------------------------------------
    # Method of moments over every unit at once, which avoids binning
    # entirely:
    #     sum_i n_i (y_i - prior)^2  =  tau^2 * sum_i n_i  +  K * s^2
    # so tau^2 follows by subtracting the expected noise contribution.
    #
    # The identity holds on any subset, and it needs to be applied to one:
    # a unit that played half a possession and went +400 contributes a term
    # of order 10^5 to the left-hand side, so a handful of garbage-time
    # stints dominate the estimate.  Restricting to units above
    # ``min_sample`` possessions makes it stable -- on Spurs lineup data the
    # estimate sits at tau ~ 9-10 for every threshold from 20 to 100, and
    # only runs away below 20.
    keep = weights >= min_sample
    if keep.sum() < 8:
        keep = weights >= weights.quantile(0.75)
    v_est, w_est = values[keep], weights[keep]

    n_total = float(w_est.sum())
    k_units = float(len(v_est))
    observed = float((w_est * (v_est - prior) ** 2).sum())
    tau2 = (observed - k_units * s2) / n_total if n_total > 0 else np.nan

    if not np.isfinite(tau2) or tau2 <= 0:
        tau2 = 49.0     # a 7-point true spread, the usual order of magnitude

    return {"tau2": tau2, "s2": s2, "k": s2 / tau2, "fit": fit,
            "tau": float(np.sqrt(tau2)), "s": float(np.sqrt(s2))}


def shrink_to_prior(values: pd.Series, weights: pd.Series,
                    prior: float | None = None,
                    prior_weight: float | None = None) -> pd.Series:
    """Shrink noisy per-unit rates toward a prior.

    ``prior_weight`` is the sample size at which an estimate is weighted
    equally between its own observation and the prior.  When it is not
    supplied it is fitted from the data by
    :func:`estimate_shrinkage_constant`.

    Parameters
    ----------
    values
        Observed rate for each unit (e.g. net rating per 100 possessions).
    weights
        Sample size behind each observation (e.g. possessions played).
    """
    values = pd.Series(values).astype(float)
    weights = pd.Series(weights).astype(float).clip(lower=0)

    if prior is None:
        prior = float(np.average(values, weights=weights))

    if prior_weight is None:
        prior_weight = estimate_shrinkage_constant(values, weights, prior)["k"]

    k = float(prior_weight)
    return (values * weights + prior * k) / (weights + k)


# --------------------------------------------------------------------------
# RAPM
# --------------------------------------------------------------------------

def build_rapm_design(stints: pd.DataFrame,
                      min_possessions: int = 0) -> tuple[sparse.csr_matrix, np.ndarray, np.ndarray, list[int]]:
    """Turn a stint table into the RAPM design matrix.

    Each stint appears twice, once from each offensive perspective.
    Offensive and defensive players enter separate column blocks with +1
    indicators. The target is points per 100 estimated team possessions.
    The defensive coefficient is negated when reporting defensive RAPM.
    """
    rows = []
    for side, pts_col, opp_col, lineup_col, opp_lineup_col in (
        ("home", "home_points", "away_points", "home_lineup", "away_lineup"),
        ("away", "away_points", "home_points", "away_lineup", "home_lineup"),
    ):
        part = stints[[pts_col, opp_col, lineup_col, opp_lineup_col, "possessions"]].copy()
        part.columns = ["points", "opp_points", "off_lineup", "def_lineup", "possessions"]
        rows.append(part)
    df = pd.concat(rows, ignore_index=True)

    # Possession counts on a stint cover both teams.
    df["team_poss"] = df["possessions"] / 2.0
    df = df[df["team_poss"] > 0].reset_index(drop=True)

    players = sorted({p for lu in df["off_lineup"] for p in lu} |
                     {p for lu in df["def_lineup"] for p in lu})
    if min_possessions > 0:
        counts: dict[int, float] = {}
        for lu, n in zip(df["off_lineup"], df["team_poss"]):
            for p in lu:
                counts[p] = counts.get(p, 0.0) + n
        players = [p for p in players if counts.get(p, 0.0) >= min_possessions]

    col = {p: i for i, p in enumerate(players)}
    n_players = len(players)

    indptr = [0]
    indices: list[int] = []
    data: list[float] = []
    for off, dfn in zip(df["off_lineup"], df["def_lineup"]):
        for p in off:
            if p in col:
                indices.append(col[p])
                data.append(1.0)
        for p in dfn:
            if p in col:
                indices.append(col[p] + n_players)
                data.append(1.0)
        indptr.append(len(indices))

    X = sparse.csr_matrix(
        (data, indices, indptr), shape=(len(df), 2 * n_players)
    )
    y = (100.0 * df["points"] / df["team_poss"]).to_numpy()
    w = df["team_poss"].to_numpy()
    return X, y, w, players


def rapm(stints: pd.DataFrame, alphas: tuple[float, ...] = (500, 1000, 2000, 4000, 8000),
         min_possessions: int = 200, seed: int = 0) -> pd.DataFrame:
    """Fit RAPM, choosing the ridge penalty by cross-validation.

    Returns one row per player with offensive, defensive and total ratings in
    points per 100 possessions relative to a ridge-centered baseline.
    Defensive rating is sign-flipped so that positive is always good.
    """
    X, y, w, players = build_rapm_design(stints, min_possessions)
    n = len(players)
    log.info("RAPM design: %d stint-sides x %d player terms", X.shape[0], X.shape[1])

    best_alpha, best_score = None, -np.inf
    kf = GroupKFold(n_splits=5)
    eligible = stints[stints.possessions.gt(0)]
    groups = np.tile(eligible.game_id.to_numpy(), 2)
    for alpha in alphas:
        scores = []
        for tr, te in kf.split(np.arange(X.shape[0]), groups=groups):
            model = Ridge(alpha=alpha, fit_intercept=True, solver="sparse_cg")
            model.fit(X[tr], y[tr], sample_weight=w[tr])
            pred = model.predict(X[te])
            resid = np.average((y[te] - pred) ** 2, weights=w[te])
            base = np.average((y[te] - np.average(y[tr], weights=w[tr])) ** 2,
                              weights=w[te])
            scores.append(1 - resid / base)
        score = float(np.mean(scores))
        log.info("  alpha=%-6g  cv R^2=%+.5f", alpha, score)
        if score > best_score:
            best_alpha, best_score = alpha, score

    model = Ridge(alpha=best_alpha, fit_intercept=True, solver="sparse_cg")
    model.fit(X, y, sample_weight=w)
    coef = model.coef_

    out = pd.DataFrame({
        "player_id": players,
        "o_rapm": coef[:n],
        "d_rapm": -coef[n:],          # flip so positive = good defence
    })
    out["rapm"] = out["o_rapm"] + out["d_rapm"]
    out.attrs["alpha"] = best_alpha
    out.attrs["cv_r2"] = best_score
    out.attrs["cv_unit"] = "game"
    return out.sort_values("rapm", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------
# Four factors
# --------------------------------------------------------------------------

def four_factors(shots: pd.DataFrame) -> pd.DataFrame:
    """Effective field-goal percentage and three-point rate by team.

    This helper reports shooting summaries only. Turnovers, rebounds and
    free throws require additional event data.
    """
    g = shots.groupby("team_id")
    made = g["shot_made_flag"].sum()
    att = g["shot_attempted_flag"].sum()
    threes_made = shots[shots["is_three"]].groupby("team_id")["shot_made_flag"].sum()
    threes_att = shots[shots["is_three"]].groupby("team_id")["shot_attempted_flag"].sum()

    out = pd.DataFrame({
        "fga": att,
        "fgm": made,
        "fg3a": threes_att,
        "fg3m": threes_made,
    }).fillna(0)
    out["efg"] = (out["fgm"] + 0.5 * out["fg3m"]) / out["fga"]
    out["three_rate"] = out["fg3a"] / out["fga"]
    out["fg3_pct"] = out["fg3m"] / out["fg3a"]
    return out.reset_index()
