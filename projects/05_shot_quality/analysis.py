"""Estimate field-goal conversion from recorded location, shot type and period context."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.calibration import calibration_curve
from sklearn.metrics import roc_auc_score, brier_score_loss, log_loss

from nbalab import viz
from nbalab.config import SPURS_ID, TRICODE_BY_ID, season_label
from nbalab.io import load_table
from nbalab.possessions import _normalise_name as _fold

log = logging.getLogger("project05")
HERE = Path(__file__).parent
FIG = HERE / "figures"
FIG.mkdir(exist_ok=True)

TRAIN_SEASONS = [2019, 2020, 2021, 2022, 2023, 2024]
TEST_SEASON = 2025
WEMBY = 1641705

CONTENDERS = ["SAS", "OKC", "NYK", "BOS", "DET", "HOU", "CLE", "DEN", "MIN"]

NUMERIC = ["shot_distance", "loc_x", "loc_y", "period", "seconds_left_period",
           "is_three", "abs_x", "angle"]
CATEGORICAL = ["action_type", "shot_zone_basic", "shot_zone_area",
               "shot_zone_range"]


def prepare(shots: pd.DataFrame) -> pd.DataFrame:
    df = shots.copy()
    df["abs_x"] = df["loc_x"].abs()
    # Angle from the centre of the rim, which distinguishes corner threes from
    # the same distance above the break.
    df["angle"] = np.degrees(np.arctan2(df["loc_y"].clip(lower=0) + 1e-6,
                                        df["abs_x"] + 1e-6))
    for c in CATEGORICAL:
        df[c] = df[c].astype("category")
    return df


def fit_model(train: pd.DataFrame) -> HistGradientBoostingClassifier:
    model = HistGradientBoostingClassifier(
        max_iter=400,
        learning_rate=0.06,
        max_leaf_nodes=63,
        min_samples_leaf=200,
        l2_regularization=1.0,
        categorical_features=[len(NUMERIC) + i for i in range(len(CATEGORICAL))],
        early_stopping=True,
        validation_fraction=0.1,
        random_state=7,
    )
    X = train[NUMERIC + CATEGORICAL]
    y = train["shot_made_flag"].astype(int)
    model.fit(X, y)
    return model


def evaluate(model, test: pd.DataFrame, train: pd.DataFrame) -> dict:
    X = test[NUMERIC + CATEGORICAL]
    y = test["shot_made_flag"].astype(int)
    p = model.predict_proba(X)[:, 1]

    # A baseline that knows only the shot zone -- the model has to beat this
    # to have earned anything.
    zone_rate = test.shot_zone_basic.map(train.groupby("shot_zone_basic", observed=True).shot_made_flag.mean()).astype(float).fillna(train.shot_made_flag.mean())
    return {
        "auc": roc_auc_score(y, p),
        "brier": brier_score_loss(y, p),
        "log_loss": log_loss(y, p),
        "baseline_auc": roc_auc_score(y, zone_rate),
        "baseline_brier": brier_score_loss(y, zone_rate),
        "baseline_log_loss": log_loss(y, zone_rate),
        "baseline_predictions": zone_rate.to_numpy(),
        "predictions": p,
    }


# --------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------

def fig_calibration(y: np.ndarray, p: np.ndarray, metrics: dict) -> None:
    from tools.feature_charts import render_calibration
    with plt.rc_context():
        render_calibration(y, p, metrics)


def fig_quality_vs_making(team_summary: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9, 7.2))
    xm = team_summary["expected_pps"].mean()
    ym = team_summary["making_per_100"].mean()
    ax.axvline(xm, color=viz.GRID, linewidth=1.2)
    ax.axhline(ym, color=viz.GRID, linewidth=1.2)

    for row in team_summary.itertuples():
        is_spurs = row.team_id == SPURS_ID
        contender = row.tricode in CONTENDERS
        color = (viz.HIGHLIGHT if is_spurs else
                 viz.CATEGORICAL[0] if contender else viz.FIELD_COLOR)
        ax.scatter(row.expected_pps, row.making_per_100,
                   s=170 if is_spurs else (86 if contender else 46),
                   color=color, zorder=6 if is_spurs else 4,
                   edgecolor=viz.SURFACE, linewidth=1.5)
        if contender:
            ax.annotate(row.tricode, (row.expected_pps, row.making_per_100),
                        textcoords="offset points", xytext=((-32,-13) if row.tricode=="SAS" else (9,3)),
                        fontsize=9.5, color=viz.HIGHLIGHT if is_spurs else viz.INK_SECONDARY,
                        fontweight="bold" if is_spurs else "normal")

    ax.set_xlabel("Expected FG points per attempt")
    ax.set_ylabel("Actual minus expected FG points per 100 attempts")
    ax.text(ax.get_xlim()[1], ym + 0.4, "above model expectation",
            fontsize=9, color=viz.INK_MUTED, ha="right")
    viz.annotate(
        ax, "Location and recorded shot type versus field-goal conversion",
        f"{season_label(TEST_SEASON)} regular season · every team · "
        "quality is what the model expected, making is what actually happened",
    )
    viz.save(fig, FIG / "quality_vs_making.png")


def fig_spurs_shot_profile(shots: pd.DataFrame) -> None:
    """Where San Antonio's shots came from, against the league."""
    spurs = shots[shots["team_id"] == SPURS_ID]
    zones = (spurs["shot_zone_basic"].value_counts(normalize=True)
             .rename("Spurs").to_frame())
    zones["League"] = shots["shot_zone_basic"].value_counts(normalize=True)
    zones = zones.dropna().sort_values("Spurs")
    zones["diff"] = zones["Spurs"] - zones["League"]

    fig, ax = plt.subplots(figsize=(9.5, 5.6))
    y = np.arange(len(zones))
    height = 0.38
    ax.barh(y + height / 2 + 0.01, 100 * zones["Spurs"], height=height,
            color=viz.HIGHLIGHT, label="San Antonio")
    ax.barh(y - height / 2 - 0.01, 100 * zones["League"], height=height,
            color=viz.FIELD_COLOR, label="League average")
    ax.set_yticks(y)
    ax.set_yticklabels(zones.index, fontsize=10)
    ax.set_xlabel("Share of the team's field-goal attempts (%)")
    ax.legend(loc="lower right")
    viz.annotate(ax, "San Antonio's shot diet",
                 f"{season_label(TEST_SEASON)} regular season")
    viz.save(fig, FIG / "spurs_shot_profile.png")


def fig_player_scatter(player_summary: pd.DataFrame) -> None:
    df = player_summary[player_summary["attempts"] >= 400].copy()
    fig, ax = plt.subplots(figsize=(9, 7.2))
    ax.axvline(df["expected_pps"].mean(), color=viz.GRID, linewidth=1.2)
    ax.axhline(0, color=viz.GRID, linewidth=1.2)
    ax.scatter(df["expected_pps"], df["making_per_100"], s=26,
               color=viz.FIELD_COLOR, alpha=0.6, linewidths=0)

    spurs = df[df["is_spur"]]
    ax.scatter(spurs["expected_pps"], spurs["making_per_100"], s=110,
               color=viz.CATEGORICAL[0], zorder=4, edgecolor=viz.SURFACE,
               linewidth=1.5)
    w = df[df["player_id"] == WEMBY]
    ax.scatter(w["expected_pps"], w["making_per_100"], s=200,
               color=viz.HIGHLIGHT, zorder=6, edgecolor=viz.SURFACE, linewidth=2)
    for row in spurs.itertuples():
        ax.annotate(row.player_name.split()[-1],
                    (row.expected_pps, row.making_per_100),
                    textcoords="offset points", xytext=(9, 3), fontsize=9,
                    color=viz.HIGHLIGHT if row.player_id == WEMBY else viz.INK_SECONDARY,
                    fontweight="bold" if row.player_id == WEMBY else "normal")

    ax.set_xlabel("Expected FG points per attempt")
    ax.set_ylabel("Actual minus expected FG points per 100 attempts")
    viz.annotate(
        ax, "San Antonio's shooters against the league",
        f"{season_label(TEST_SEASON)} regular season · minimum 400 attempts",
    )
    viz.save(fig, FIG / "player_quality_making.png")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    viz.use_theme()

    shots = load_table("shots")
    shots = shots[shots["season_type"] == "regular"]
    shots = prepare(shots)

    train = shots[shots["season"].isin(TRAIN_SEASONS)]
    test = shots[shots["season"] == TEST_SEASON].copy()
    log.info("training on %d shots, testing on %d", len(train), len(test))

    model = fit_model(train)
    metrics = evaluate(model, test, train)
    log.info("\nHeld-out performance on %s:", season_label(TEST_SEASON))
    log.info("  AUC        %.4f   (zone-only baseline %.4f)",
             metrics["auc"], metrics["baseline_auc"])
    log.info("  Brier      %.4f   (zone-only baseline %.4f)",
             metrics["brier"], metrics["baseline_brier"])
    log.info("  log loss   %.4f", metrics["log_loss"])

    test["p_make"] = metrics["predictions"]
    test["baseline"] = metrics["baseline_predictions"]
    test[["game_id", "game_event_id", "shot_made_flag", "p_make", "baseline"]].to_csv(HERE / "evaluation_rows.csv.gz", index=False)
    test["expected_points"] = test["p_make"] * test["points_if_made"]
    test["actual_points"] = test["shot_made_flag"] * test["points_if_made"]
    test["making"] = test["actual_points"] - test["expected_points"]

    fig_calibration(test["shot_made_flag"].to_numpy().astype(int),
                    test["p_make"].to_numpy(), metrics)

    team_summary = test.groupby("team_id").agg(
        attempts=("p_make", "size"),
        expected_points=("expected_points", "sum"),
        actual_points=("actual_points", "sum"),
    ).reset_index()
    team_summary["expected_pps"] = team_summary["expected_points"] / team_summary["attempts"]
    team_summary["actual_pps"] = team_summary["actual_points"] / team_summary["attempts"]
    team_summary["making_per_100"] = 100 * (
        team_summary["actual_pps"] - team_summary["expected_pps"])
    team_summary["tricode"] = team_summary["team_id"].map(TRICODE_BY_ID)
    team_summary = team_summary.sort_values("making_per_100", ascending=False)
    team_summary.to_csv(HERE / "team_shot_quality.csv", index=False)

    log.info("\nTeam shot quality and shot making, %s:", season_label(TEST_SEASON))
    log.info("%s", team_summary.head(10)[
        ["tricode", "attempts", "expected_pps", "actual_pps", "making_per_100"]
    ].round(3).to_string(index=False))
    spurs_row = team_summary[team_summary["team_id"] == SPURS_ID].iloc[0]
    log.info("\nSan Antonio: %.3f expected points per shot (rank %d of 30), "
             "%+.2f per 100 in making (rank %d)",
             spurs_row["expected_pps"],
             int((team_summary["expected_pps"] > spurs_row["expected_pps"]).sum()) + 1,
             spurs_row["making_per_100"],
             int((team_summary["making_per_100"] > spurs_row["making_per_100"]).sum()) + 1)

    player_summary = test.groupby(["player_id", "player_name"]).agg(
        attempts=("p_make", "size"),
        expected_points=("expected_points", "sum"),
        actual_points=("actual_points", "sum"),
        team_id=("team_id", lambda s: s.mode().iloc[0]),
    ).reset_index()
    player_summary["expected_pps"] = (
        player_summary["expected_points"] / player_summary["attempts"])
    player_summary["making_per_100"] = 100 * (
        player_summary["actual_points"] - player_summary["expected_points"]
    ) / player_summary["attempts"]
    player_summary["is_spur"] = player_summary["team_id"] == SPURS_ID
    player_summary.to_csv(HERE / "player_shot_quality.csv", index=False)

    qualified = player_summary[player_summary["attempts"] >= 400]
    log.info("\nBest shot-makers, %s (minimum 400 attempts):", season_label(TEST_SEASON))
    log.info("%s", qualified.nlargest(10, "making_per_100")[
        ["player_name", "attempts", "expected_pps", "making_per_100"]
    ].round(3).to_string(index=False))

    w = player_summary[player_summary["player_id"] == WEMBY]
    if len(w):
        row = w.iloc[0]
        log.info("\nWembanyama: %d attempts, %.3f expected points per shot, "
                 "%+.2f per 100 in making",
                 row["attempts"], row["expected_pps"], row["making_per_100"])

    fig_quality_vs_making(team_summary)
    fig_spurs_shot_profile(test)
    fig_player_scatter(player_summary)

    pd.DataFrame([{
        "auc": metrics["auc"], "baseline_auc": metrics["baseline_auc"],
        "brier": metrics["brier"], "baseline_brier": metrics["baseline_brier"],
        "log_loss": metrics["log_loss"], "baseline_log_loss": metrics["baseline_log_loss"],
        "train_shots": len(train), "test_shots": len(test),
        "spurs_expected_pps": spurs_row["expected_pps"],
        "spurs_making_per_100": spurs_row["making_per_100"],
    }]).to_csv(HERE / "summary.csv", index=False)
    log.info("\nwrote 4 figures and 3 tables to %s", HERE)


if __name__ == "__main__":
    main()
