"""Checks for shrinkage estimates and shooting summaries."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nbalab.ratings import (estimate_shrinkage_constant, four_factors,
                            shrink_to_prior)


# --------------------------------------------------------------------------
# Shrinkage
# --------------------------------------------------------------------------

def test_shrinkage_pulls_small_samples_toward_the_prior():
    values = pd.Series([50.0, 50.0])
    weights = pd.Series([10.0, 1000.0])
    out = shrink_to_prior(values, weights, prior=0.0, prior_weight=250.0)
    # The 10-possession observation should be pulled far closer to 0.
    assert out.iloc[0] < out.iloc[1]
    assert out.iloc[0] < 5.0
    assert out.iloc[1] > 35.0


def test_shrinkage_leaves_a_huge_sample_almost_untouched():
    values = pd.Series([12.0])
    weights = pd.Series([1_000_000.0])
    out = shrink_to_prior(values, weights, prior=0.0, prior_weight=250.0)
    assert out.iloc[0] == pytest.approx(12.0, abs=0.01)


def test_shrinkage_of_a_zero_sample_is_the_prior():
    out = shrink_to_prior(pd.Series([99.0]), pd.Series([0.0]),
                          prior=4.0, prior_weight=250.0)
    assert out.iloc[0] == pytest.approx(4.0)


def test_shrinkage_is_monotone_in_sample_size():
    values = pd.Series([30.0] * 5)
    weights = pd.Series([5.0, 25.0, 100.0, 400.0, 1600.0])
    out = shrink_to_prior(values, weights, prior=0.0, prior_weight=250.0)
    assert list(out) == sorted(out)


def test_shrinkage_constant_recovers_a_known_noise_scale():
    """Simulate units with known true spread and check the fit."""
    rng = np.random.default_rng(11)
    n_units = 900
    tau, s = 8.0, 150.0
    sizes = rng.integers(30, 1200, size=n_units).astype(float)
    truth = rng.normal(0.0, tau, size=n_units)
    observed = truth + rng.normal(0.0, s / np.sqrt(sizes))

    est = estimate_shrinkage_constant(pd.Series(observed), pd.Series(sizes),
                                      prior=0.0)
    # Both scales should land within a reasonable band of the truth.
    assert 0.6 * s < est["s"] < 1.6 * s
    assert 0.5 * tau < est["tau"] < 1.8 * tau
    assert 100 < est["k"] < 2000


def test_shrinkage_constant_ignores_garbage_time_outliers():
    """A half-possession unit at +400 must not drive the estimate."""
    rng = np.random.default_rng(3)
    sizes = np.concatenate([rng.integers(200, 900, 300).astype(float),
                            np.array([0.5, 0.5, 1.0, 1.0])])
    values = np.concatenate([rng.normal(0, 9, 300),
                             np.array([400.0, -400.0, 300.0, -300.0])])
    est = estimate_shrinkage_constant(pd.Series(values), pd.Series(sizes),
                                      prior=0.0)
    assert est["tau"] < 30.0


def test_shrinkage_defaults_to_a_fitted_constant():
    rng = np.random.default_rng(5)
    sizes = rng.integers(50, 900, 400).astype(float)
    values = rng.normal(0, 9, 400) + rng.normal(0, 150 / np.sqrt(sizes))
    out = shrink_to_prior(pd.Series(values), pd.Series(sizes))
    assert out.std() < pd.Series(values).std()


# --------------------------------------------------------------------------
# Four factors
# --------------------------------------------------------------------------

def test_effective_field_goal_percentage_counts_threes_correctly():
    shots = pd.DataFrame({
        "team_id": [1, 1, 1, 1],
        "shot_made_flag": [1, 1, 0, 0],
        "shot_attempted_flag": [1, 1, 1, 1],
        "is_three": [True, False, True, False],
    })
    out = four_factors(shots)
    # 2 makes of 4, one of them a three -> (2 + 0.5) / 4
    assert out.loc[0, "efg"] == pytest.approx(0.625)
    assert out.loc[0, "three_rate"] == pytest.approx(0.5)


def test_four_factors_splits_by_team():
    shots = pd.DataFrame({
        "team_id": [1, 1, 2, 2],
        "shot_made_flag": [1, 0, 1, 1],
        "shot_attempted_flag": [1, 1, 1, 1],
        "is_three": [False, False, False, False],
    })
    out = four_factors(shots).set_index("team_id")
    assert out.loc[1, "efg"] == pytest.approx(0.5)
    assert out.loc[2, "efg"] == pytest.approx(1.0)
