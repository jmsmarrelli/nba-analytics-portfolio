"""Render held-out shot-model evidence without requiring a fresh model fit."""
from pathlib import Path
import numpy as np
import pandas as pd
from matplotlib.ticker import PercentFormatter
from sklearn.calibration import calibration_curve
from sklearn.metrics import log_loss, brier_score_loss
from .chart_style import canvas, finish, stat, note, tidy, TEAL, ORANGE, MUTED, GRID

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "projects/05_shot_quality"


def render_calibration(y, p, metrics):
    frac, pred = calibration_curve(y, p, n_bins=20, strategy="quantile")
    fig = canvas("05 / Shot-context model", "A shot model has to earn its extra complexity",
                 "Trained on 2019–20 through 2024–25 · tested on the held-out 2025–26 season", 9)
    ax = fig.add_axes([.09, .255, .41, .48])
    ax.plot([0, 1], [0, 1], color=GRID, lw=1.5, ls="--", label="Perfect calibration")
    ax.plot(pred, frac, color=TEAL, lw=2, marker="o", ms=6,
            markeredgecolor="white", markeredgewidth=1, label="20 equal-count bins")
    ax.set(xlim=(0,1), ylim=(0,1), xlabel="Predicted make probability", ylabel="Observed make rate")
    ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    tidy(ax, axis="both")
    ax.legend(frameon=False, loc="upper left", fontsize=10)
    stat(fig, .60, .69, f"{len(y):,}", "held-out field-goal attempts")
    fig.text(.60, .565, "LOWER LOG LOSS IS BETTER", fontsize=10, weight="bold", color=MUTED)
    stat(fig, .60, .49, f"{metrics['log_loss']:.4f}", "Shot-context model", color=TEAL)
    stat(fig, .80, .49, f"{metrics['baseline_log_loss']:.4f}", "Zone-only baseline", color=ORANGE)
    gain = 100*(metrics["baseline_log_loss"]-metrics["log_loss"])/metrics["baseline_log_loss"]
    note(fig, .60, .38, f"{gain:.1f}% relative reduction in log loss", "The model improves on a simpler comparison in this held-out season. Aggregate calibration can still hide errors by player, team or shot type.", width=47)
    finish(fig, HERE / "figures/calibration",
           "Source: projects/05_shot_quality/evaluation_rows.csv.gz and summary.csv · Calibration connects quantile-bin means, not individual shots.",
           "Recorded location, action type and clock context. No defender distance or openness; expected points are a descriptive baseline.")


def main():
    d = pd.read_csv(HERE / "evaluation_rows.csv.gz")
    metrics = pd.read_csv(HERE / "summary.csv").iloc[0].to_dict()
    # Verify that the display is grounded in the saved evaluation rows.
    for label, p in [("", d.p_make), ("baseline_", d.baseline)]:
        np.testing.assert_allclose(log_loss(d.shot_made_flag, p), metrics[label+"log_loss"], rtol=1e-8)
        np.testing.assert_allclose(brier_score_loss(d.shot_made_flag, p), metrics[label+"brier"], rtol=1e-8)
    if len(d) != metrics["test_shots"]:
        raise ValueError("Evaluation row count does not match summary")
    render_calibration(d.shot_made_flag, d.p_make, metrics)


if __name__ == "__main__":
    main()
