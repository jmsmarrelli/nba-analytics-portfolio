"""Build and execute notebooks that review the included result tables."""
from pathlib import Path
import os, sys, json
import nbformat as nb
from nbclient import NotebookClient
ROOT = Path(__file__).resolve().parents[1]


def execute(jobs):
    os.environ.setdefault("OMP_NUM_THREADS", "4")
    cache = ROOT / ".cache"
    cache.mkdir(exist_ok=True)
    for key, folder in [("JUPYTER_RUNTIME_DIR", "runtime"), ("IPYTHONDIR", "ipython"), ("MPLCONFIGDIR", "matplotlib")]:
        path = cache / folder
        path.mkdir(exist_ok=True)
        os.environ[key] = str(path)
    spec = cache / "jupyter/kernels/review"
    spec.mkdir(parents=True, exist_ok=True)
    (spec / "kernel.json").write_text(json.dumps({"argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"], "display_name": "Python 3", "language": "python"}))
    os.environ["JUPYTER_PATH"] = str(cache / "jupyter")
    (ROOT / "notebooks").mkdir(exist_ok=True)
    for stem, title, code, table, figures, limits in jobs:
        book = nb.v4.new_notebook(metadata={"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"}, "language_info": {"name": "python", "version": "3.12"}})
        setup = "from pathlib import Path\nimport numpy as np\nimport pandas as pd\nimport json\nfrom IPython.display import display, Image\nroot = Path.cwd()\nif root.name == 'notebooks':\n    root = root.parent\np = root / 'projects' / " + repr(stem)
        book.cells = [
            nb.v4.new_markdown_cell("# " + title + "\n\nJoseph Smarrelli · September 2026\n\nThis notebook recalculates selected findings from the included derived tables. It does not refit the underlying models. See the repository README for the complete source-data build and the accompanying article for interpretation."),
            nb.v4.new_code_cell(setup),
            nb.v4.new_markdown_cell("## Recalculate the result\nThe assertions check that the article’s reported quantities agree with the delivered tables."),
            nb.v4.new_code_cell(code),
            nb.v4.new_markdown_cell("## Inspect the estimates"),
            nb.v4.new_code_cell(table),
            nb.v4.new_markdown_cell("## Figures"),
            nb.v4.new_code_cell("\n".join("display(Image(filename=str(root / " + repr(f) + ")))" for f in figures)),
            nb.v4.new_markdown_cell("## Interpretation limits\n" + limits),
        ]
        NotebookClient(book, timeout=300, kernel_name="review", resources={"metadata": {"path": str(ROOT)}}).execute()
        for cell in book.cells:
            cell.metadata.pop("execution", None)
        path = ROOT / "notebooks" / (stem + ".ipynb")
        nb.write(book, path)
        print(path.name, "executed", flush=True)

JOBS = [('01_data_pipeline',
  'When a lineup reconstruction is ready to use',
  "d = pd.read_csv(p / 'game_reconciliation.csv')\n"
  'reconstructed = d.loc[d.has_reconstruction]\n'
  'assert reconstructed.score_matches.all()\n'
  'assert not d.game_id.duplicated().any()\n'
  "display(pd.Series({'source_games': len(d), 'reconstructed_games': len(reconstructed), "
  "'reconciled_games': reconstructed.score_matches.sum()}))",
  "display(pd.read_csv(p / 'reconstruction_quality.csv'))",
  ['projects/01_data_pipeline/figures/validation.png'],
  'Scoring agreement does not certify player identities. Use the separate eligibility audit before '
  'fitting lineup models.'),
 ('02_lineup_optimizer',
  'A rotation optimizer can lose to the allocation it replaces',
  "d = pd.read_csv(p / 'allocation_evaluation.csv')\n"
  "s = pd.read_csv(p / 'summary.csv').iloc[0]\n"
  'assert np.isclose(d.optimized_minutes.sum(), 48)\n'
  'assert np.isclose(d.baseline_minutes.sum(), 48)\n'
  'optimized = np.average(d.holdout_rating, weights=d.optimized_minutes)\n'
  'baseline = np.average(d.holdout_rating, weights=d.baseline_minutes)\n'
  'assert np.isclose(optimized, s.optimised_holdout)\n'
  'assert np.isclose(baseline, s.actual_holdout)\n'
  "display(pd.Series({'optimized_holdout_rating': optimized, 'training_allocation_holdout_rating': "
  "baseline, 'difference': optimized - baseline}))",
  "display(pd.read_csv(p / 'minute_reallocation.csv'))",
  ['projects/02_lineup_optimizer/figures/minute_reallocation.png',
   'projects/02_lineup_optimizer/figures/null_test.png'],
  'The allocation uses training-period ratings and observed lineups. Later observational ratings '
  'do not identify the effect of actually changing a rotation. The optimized allocation loses this '
  'comparison.'),
 ('03_wemby_impact',
  'Three views of Wembanyama’s defensive season',
  "d = pd.read_csv(p / 'rapm_2025_26.csv')\n"
  'assert np.allclose(d.o_rapm + d.d_rapm, d.rapm)\n'
  "rim = pd.read_csv(p / 'rim_control_panel.csv')\n"
  'assert np.allclose(rim.rim_share_on - rim.rim_share_off, rim.rim_share_delta)\n'
  'assert np.allclose(rim.rim_fg_on - rim.rim_fg_off, rim.rim_fg_delta)\n'
  'display(rim.loc[rim.player_id.eq(1641705)])',
  "display(d.sort_values('d_rapm', ascending=False).head(12))",
  ['projects/03_wemby_impact/figures/rapm_bigs.png',
   'projects/03_wemby_impact/figures/rim_deterrence.png'],
  'RAPM adjusts for listed players, not every game condition. Its game-grouped validation score is '
  'a tuning diagnostic. Rim comparisons are observational. Matchup totals use the defender field.'),
 ('04_season_simulator',
  'A historical baseline for the next season',
  "d = pd.read_csv(p / 'backtest.csv')\n"
  "s = json.loads((p / 'summary.json').read_text())\n"
  'assert (d.train_through < d.target_season).all()\n'
  'mae = (d.actual_wins - d.pred_wins).abs().mean()\n'
  "assert np.isclose(mae, s['backtest_mae'])\n"
  "assert np.isclose(d.in_80.mean(), s['backtest_80_coverage'])\n"
  "projection = pd.read_csv(p / 'projection_2026_27.csv')\n"
  "for col, total in [('title', 1), ('finals', 2), ('conf_final', 4), ('playoff', 16), "
  "('top_seed', 2)]:\n"
  '    assert np.isclose(projection[col].sum(), total)\n'
  "display(pd.Series({'rolling_win_MAE': mae, '80_percent_interval_coverage': d.in_80.mean(), "
  "'held_out_team_seasons': len(d)}))",
  'display(projection)',
  ['projects/04_season_simulator/figures/projected_wins.png',
   'projects/04_season_simulator/figures/rolling_backtest.png'],
  'This is a historical carry-over baseline on a synthetic schedule. It makes no transaction, '
  'injury or market-price adjustment. Fixed-bracket probabilities are conditional on those '
  'assumptions.'),
 ('05_shot_quality',
  'Separating recorded shot context from conversion',
  'from sklearn.metrics import log_loss, roc_auc_score, brier_score_loss\n'
  "d = pd.read_csv(p / 'evaluation_rows.csv.gz')\n"
  "s = pd.read_csv(p / 'summary.csv').iloc[0]\n"
  "assert not d.duplicated(['game_id', 'game_event_id']).any()\n"
  'model_loss = log_loss(d.shot_made_flag, d.p_make)\n'
  'baseline_loss = log_loss(d.shot_made_flag, d.baseline)\n'
  'assert np.isclose(model_loss, s.log_loss)\n'
  'assert np.isclose(baseline_loss, s.baseline_log_loss)\n'
  "display(pd.DataFrame({'model': [model_loss, roc_auc_score(d.shot_made_flag, d.p_make), "
  "brier_score_loss(d.shot_made_flag, d.p_make)], 'zone_baseline': [baseline_loss, "
  'roc_auc_score(d.shot_made_flag, d.baseline), brier_score_loss(d.shot_made_flag, d.baseline)]}, '
  "index=['log_loss', 'AUC', 'Brier']))",
  "display(pd.read_csv(p / 'team_shot_quality.csv'))",
  ['projects/05_shot_quality/figures/calibration.png',
   'projects/05_shot_quality/figures/quality_vs_making.png'],
  'The model conditions on recorded attempts and action labels. It includes heaves and does not '
  'observe shot contests, tracking, shooter ability or shots a player declined to take.'),
 ('06_development_curves_R',
  'What an experience curve can tell the Spurs',
  "d = pd.read_csv(p / 'spurs_core_projection.csv')\n"
  'assert np.allclose(d.rapm + d.expected_step, d.projected_rapm)\n'
  'assert (d.step_lo <= d.step_hi).all()\n'
  'display(d)',
  "display(pd.read_csv(p / 'development_curve.csv'))",
  ['projects/06_development_curves_R/figures/development_curve.png',
   'projects/06_development_curves_R/figures/spurs_core_projection.png'],
  'The curve estimates a population mean from observed careers. Its bootstrap interval describes '
  'the mean step, not the full uncertainty of an individual player forecast. The underlying model '
  'is fitted by the accompanying R script.'),
 ('07_contender_style_R',
  'Where the contenders sit in shot-location space',
  "d = pd.read_csv(p / 'style_scores.csv')\n"
  'assert len(d) == 30 and d.tricode.nunique() == 30\n'
  "sas_cluster = d.loc[d.tricode.eq('SAS'), 'cluster'].iloc[0]\n"
  "display(d.loc[d.cluster.eq(sas_cluster), ['tricode', 'PC1', 'PC2', 'net_rating']])\n"
  "neighbors = pd.read_csv(p / 'spurs_style_neighbours.csv')\n"
  'assert neighbors.distance.ge(0).all()\n'
  'assert neighbors.distance.is_monotonic_increasing\n'
  'display(neighbors.head(10))',
  "display(pd.read_csv(p / 'pca_loadings.csv'))",
  ['projects/07_contender_style_R/figures/style_space.png',
   'projects/07_contender_style_R/figures/league_drift.png'],
  'Distances describe the selected standardized shot-location features. Four clusters are a '
  'modeling choice, not an inferred number of NBA systems. The historical projection uses the '
  'current-season basis and is descriptive.'),
 ('08_finals_postmortem_R',
  'The first-quarter lead and the rest of the Finals',
  "games = pd.read_csv(p / 'game_summary.csv')\n"
  "quarters = pd.read_csv(p / 'quarter_summary.csv')\n"
  'assert games.spurs_points.sum() == quarters.spurs_points.sum()\n'
  'assert games.opp_points.sum() == quarters.opp_points.sum()\n'
  "resamples = pd.read_csv(p / 'series_resample.csv')\n"
  'assert np.isclose(resamples.probability.sum(), 1)\n'
  "display(pd.Series({'Spurs_points': games.spurs_points.sum(), 'opponent_points': "
  "games.opp_points.sum(), 'margin': games.spurs_points.sum() - games.opp_points.sum()}))\n"
  'display(quarters)',
  'display(games)\ndisplay(resamples)',
  ['projects/08_finals_postmortem_R/figures/quarter_margins.png',
   'projects/08_finals_postmortem_R/figures/series_resample.png'],
  'Resampling observed stints with replacement changes their frequency, playing time and '
  'composition. It does not estimate a seven-game series win probability or certify lineup '
  'identities in the Finals games.')]

if __name__ == "__main__":
    execute(JOBS)
