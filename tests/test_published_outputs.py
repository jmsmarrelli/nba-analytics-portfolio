from pathlib import Path
import json
import numpy as np
import pandas as pd
from sklearn.metrics import log_loss
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'projects'

def test_stint_scores_reconcile_for_every_reconstructed_game():
    d=pd.read_csv(P/'01_data_pipeline/game_reconciliation.csv')
    assert d.loc[d.has_reconstruction,'score_matches'].all()
    assert d.game_id.nunique()==len(d)

def test_optimizer_scores_reproduce_from_allocations():
    r=P/'02_lineup_optimizer';d=pd.read_csv(r/'allocation_evaluation.csv');s=pd.read_csv(r/'summary.csv').iloc[0]
    assert np.isclose(d.optimized_minutes.sum(),48)
    assert np.isclose(d.baseline_minutes.sum(),48)
    assert np.isclose(np.average(d.holdout_rating,weights=d.optimized_minutes),s.optimised_holdout)
    assert np.isclose(np.average(d.holdout_rating,weights=d.baseline_minutes),s.actual_holdout)

def test_rapm_offense_and_defense_add_to_total():
    d=pd.read_csv(P/'03_wemby_impact/rapm_2025_26.csv')
    assert np.allclose(d.o_rapm+d.d_rapm,d.rapm)
    assert not d.player_id.duplicated().any()

def test_shot_validation_matches_frozen_predictions():
    r=P/'05_shot_quality';d=pd.read_csv(r/'evaluation_rows.csv.gz');s=pd.read_csv(r/'summary.csv').iloc[0]
    assert np.isclose(log_loss(d.shot_made_flag,d.p_make),s.log_loss)
    assert np.isclose(log_loss(d.shot_made_flag,d.baseline),s.baseline_log_loss)
    assert not d.duplicated(['game_id','game_event_id']).any()

def test_simulated_bracket_probabilities_conserve_berths():
    d=pd.read_csv(P/'04_season_simulator/projection_2026_27.csv')
    for col,total in [('title',1),('finals',2),('conf_final',4),('playoff',16),('top_seed',2)]:
        assert d[col].between(0,1).all()
        assert np.isclose(d[col].sum(),total)

def test_r_outputs_reconcile():
    r=P/'08_finals_postmortem_R';games=pd.read_csv(r/'game_summary.csv');q=pd.read_csv(r/'quarter_summary.csv');b=pd.read_csv(r/'series_resample.csv')
    assert games.spurs_points.sum()==q.spurs_points.sum()
    assert games.opp_points.sum()==q.opp_points.sum()
    assert np.isclose(b.probability.sum(),1)
    d=pd.read_csv(P/'06_development_curves_R/spurs_core_projection.csv')
    assert np.allclose(d.rapm+d.expected_step,d.projected_rapm)
    assert (d.step_lo<=d.step_hi).all()
