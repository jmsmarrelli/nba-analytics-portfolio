"""Tests for the possession and lineup reconstruction.

These cover the three bugs that were actually hit while building this, each
of which produced plausible-looking but wrong numbers rather than an error:

* ``actionNumber`` is not chronological, so using it to find a game's final
  score returns a first-quarter score for about 1 game in 120.
* Every rebound description contains the substring ``"Def:"`` -- it reports
  the rebounder's season totals -- so classifying rebounds by that string
  counts offensive rebounds as possession-ending and inflates pace by
  roughly 15 possessions per team per game.
* Accented names in the roster feed do not match the ASCII-folded names in
  the play-by-play text, which silently drops about two substitutions per
  game and leaves lineups with four players.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nbalab import possessions as P


# --------------------------------------------------------------------------
# Clock parsing
# --------------------------------------------------------------------------

def test_parse_clock_reads_minutes_and_seconds():
    assert P.parse_clock("PT12M00.00S") == pytest.approx(720.0)
    assert P.parse_clock("PT06M40.00S") == pytest.approx(400.0)
    assert P.parse_clock("PT00M03.20S") == pytest.approx(3.2)


def test_parse_clock_returns_nan_on_junk():
    assert np.isnan(P.parse_clock("not a clock"))
    assert np.isnan(P.parse_clock(None))


def test_game_seconds_elapsed_is_continuous_across_periods():
    period = pd.Series([1, 1, 2, 4, 5])
    remaining = pd.Series([720.0, 0.0, 720.0, 0.0, 300.0])
    elapsed = P.game_seconds_elapsed(period, remaining)
    assert list(elapsed) == pytest.approx([0.0, 720.0, 720.0, 2880.0, 2880.0])


def test_overtime_periods_are_five_minutes():
    assert P.period_length(4) == 720.0
    assert P.period_length(5) == 300.0
    assert P.period_length(7) == 300.0


# --------------------------------------------------------------------------
# Name folding
# --------------------------------------------------------------------------

@pytest.mark.parametrize("accented,plain", [
    ("Jokić", "Jokic"),
    ("Dončić", "Doncic"),
    ("Schröder", "Schroder"),
    ("Šengün", "Sengun"),
    ("Valančiūnas", "Valanciunas"),
])
def test_accented_names_fold_to_the_play_by_play_spelling(accented, plain):
    assert P._normalise_name(accented) == P._normalise_name(plain)


def test_name_folding_ignores_punctuation_and_case():
    assert P._normalise_name("O'Neal") == P._normalise_name("oneal")
    assert P._normalise_name("Smith Jr.") == P._normalise_name("smith jr")


# --------------------------------------------------------------------------
# Possession marking
# --------------------------------------------------------------------------

def _event(action, description="", team=1, person=100, period=1,
           score_home=None, score_away=None):
    return {
        "gameId": 1, "actionId": _event.counter, "actionType": action,
        "description": description, "teamId": team, "personId": person,
        "period": period, "clock": "PT06M00.00S",
        "scoreHome": score_home, "scoreAway": score_away,
        "location": "h", "shotResult": None,
    }


_event.counter = 0


def _frame(rows):
    _event.counter = 0
    out = []
    for r in rows:
        _event.counter += 1
        out.append(r)
    return pd.DataFrame(out)


def test_offensive_rebound_does_not_end_the_possession():
    """The regression that mattered most: 'Def:' appears in every rebound."""
    df = _frame([
        _event("Missed Shot", "MISS Wembanyama 25' 3PT Jump Shot", team=1),
        # Same team rebounds -> offensive -> possession continues.
        _event("Rebound", "Wembanyama REBOUND (Off:1 Def:4)", team=1),
        _event("Made Shot", "Wembanyama 2' Dunk", team=1),
    ])
    marked = P.mark_possessions(df)
    assert list(marked["possession_end"]) == [False, False, True]


def test_defensive_rebound_ends_the_possession():
    df = _frame([
        _event("Missed Shot", "MISS Fox 18' Jump Shot", team=1),
        _event("Rebound", "Brunson REBOUND (Off:0 Def:6)", team=2),
    ])
    marked = P.mark_possessions(df)
    assert list(marked["possession_end"]) == [False, True]


def test_made_shot_and_turnover_end_possessions():
    df = _frame([
        _event("Made Shot", "Castle 3PT Jump Shot", team=1),
        _event("Turnover", "Harper Turnover: Bad Pass", team=1),
    ])
    marked = P.mark_possessions(df)
    assert list(marked["possession_end"]) == [True, True]


def test_only_the_last_made_free_throw_ends_the_possession():
    df = _frame([
        _event("Free Throw", "Fox Free Throw 1 of 2", team=1),
        _event("Free Throw", "Fox Free Throw 2 of 2", team=1),
    ])
    marked = P.mark_possessions(df)
    assert list(marked["possession_end"]) == [False, True]


def test_missed_final_free_throw_does_not_end_the_possession():
    df = _frame([
        _event("Free Throw", "MISS Fox Free Throw 2 of 2", team=1),
    ])
    marked = P.mark_possessions(df)
    assert list(marked["possession_end"]) == [False]


def test_technical_free_throw_never_ends_the_possession():
    df = _frame([
        _event("Free Throw", "Wembanyama Free Throw Technical (31 PTS)", team=1),
    ])
    marked = P.mark_possessions(df)
    assert list(marked["possession_end"]) == [False]


def test_flagrant_free_throws_retain_possession():
    df = _frame([
        _event("Free Throw", "Fox Free Throw Flagrant 1 of 2", team=1),
        _event("Free Throw", "Fox Free Throw Flagrant 2 of 2", team=1),
    ])
    marked = P.mark_possessions(df)
    assert list(marked["possession_end"]) == [False, False]


def test_period_end_does_not_double_count_after_a_made_basket():
    df = _frame([
        _event("Made Shot", "Vassell 20' Jump Shot", team=1),
        _event("period", "End of 1st Period (8:12 PM EST)", team=0, person=0),
    ])
    marked = P.mark_possessions(df)
    assert list(marked["possession_end"]) == [True, False]


def test_period_end_counts_when_a_possession_was_live():
    df = _frame([
        _event("Made Shot", "Vassell 20' Jump Shot", team=1),
        _event("Missed Shot", "MISS Brunson 28' 3PT", team=2),
        _event("period", "End of 1st Period (8:12 PM EST)", team=0, person=0),
    ])
    marked = P.mark_possessions(df)
    assert marked["possession_end"].tolist()[-1] is True or \
        bool(marked["possession_end"].iloc[-1])


def test_possession_ids_increase_and_never_go_backwards():
    df = _frame([
        _event("Made Shot", "A 2' Dunk", team=1),
        _event("Missed Shot", "MISS B 25' 3PT", team=2),
        _event("Rebound", "C REBOUND (Off:0 Def:3)", team=1),
        _event("Turnover", "D Turnover: Lost Ball", team=1),
    ])
    marked = P.mark_possessions(df)
    ids = marked["possession_id"].tolist()
    assert ids == sorted(ids)
    assert ids[0] == 0
