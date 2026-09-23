"""Regression checks for the corrections made during publication review."""
from pathlib import Path
import importlib.util
import numpy as np
import pandas as pd
from nbalab import possessions as P
from nbalab.config import TEAMS
ROOT=Path(__file__).resolve().parents[1]

def module(folder):
    spec=importlib.util.spec_from_file_location(folder,ROOT/'projects'/folder/'analysis.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def events(actions,descriptions,teams=None):
    n=len(actions)
    return pd.DataFrame(dict(gameId=[1]*n,period=[1]*n,clock=['PT01M00S']*n,personId=[10]*n,teamId=teams or [1]*n,actionId=range(n),actionType=actions,description=descriptions))

def test_and_one_counts_one_ending():
    d=events(['Made Shot','Foul','Free Throw'],['A Layup','B Shooting Foul','A Free Throw 1 of 1'])
    assert P.mark_possessions(d).possession_end.tolist()==[False,False,True]

def test_missed_and_one_waits_for_rebound():
    d=events(['Made Shot','Free Throw','Rebound'],['A Layup','MISS A Free Throw 1 of 1','B REBOUND'],[1,1,2])
    assert P.mark_possessions(d).possession_end.tolist()==[False,False,True]

def test_stints_keep_periods_points_and_time():
    d=events(['period','Made Shot','Substitution','Made Shot','period','period','Made Shot'],['']*7)
    d['period']=[1,1,1,1,1,2,2];d['season']=2025;d['season_type']='regular'
    d['home_lineup']=[(1,2,3,4,5)]*2+[(1,2,3,4,6)]*5;d['away_lineup']=[(11,12,13,14,15)]*7
    d['home_team_id']=1;d['away_team_id']=2;d['seconds_elapsed']=[0,10,12,15,720,720,735]
    d['scoreHome']=[0,2,2,4,4,4,6];d['scoreAway']=0;d['possession_end']=[False,True,False,True,False,False,True]
    out=P.build_stints(d)
    assert out.home_points.sum()==6
    assert out.seconds.sum()==735
    assert set(out.period)=={1,2}
    assert out.loc[out.period.eq(2),'home_points'].sum()==2

def test_shot_baseline_uses_training_rates():
    m=module('05_shot_quality')
    test=pd.DataFrame({c:[1,1,1,1] for c in m.NUMERIC+m.CATEGORICAL})
    test['shot_zone_basic']=['Rim']*4;test['shot_made_flag']=[1,0,1,0]
    train=pd.DataFrame({'shot_zone_basic':['Rim']*4,'shot_made_flag':[1,1,1,0]})
    class Model:
        def predict_proba(self,x):return np.tile([.4,.6],(len(x),1))
    v=m.evaluate(Model(),test,train)
    np.testing.assert_allclose(v['baseline_predictions'],.75)

def test_matchup_grouping_uses_nested_defender(monkeypatch):
    m=module('03_wemby_impact')
    fields=['partial_possessions','matchup_field_goals_made','matchup_field_goals_attempted','matchup_three_pointers_made','matchup_three_pointers_attempted','matchup_blocks','help_blocks','matchup_turnovers','player_points','matchup_minutes_sort']
    d=pd.DataFrame({c:[1.,1.] for c in fields})
    d['person_id']=[10,11];d['matchups_person_id']=[20,20];d['player_points']=[2,3]
    monkeypatch.setattr(m.S,'load_matchups',lambda season,st:d if st=='regular' else d.iloc[:0])
    monkeypatch.setattr(m,'player_names',lambda:pd.Series({20:'Defender'}))
    got=m.matchup_defence(2025,min_possessions=0)
    assert got.player_id.tolist()==[20]
    assert got.points.iloc[0]==5

def test_fixed_bracket_pairs():
    m=module('04_season_simulator');calls=[]
    def series(a,b):calls.append((a,b));return True
    winner,last=m.conference_bracket(list(range(8)),series)
    assert calls==[(0,7),(3,4),(1,6),(2,5),(0,3),(1,2),(0,1)]
    assert winner==0 and last==[0,1]

def test_synthetic_schedule_has_82_games_per_team():
    m=module('04_season_simulator');a=m.build_schedule([t.team_id for t in TEAMS])
    assert len(a)==1230 and np.all(a[:,0]!=a[:,1])
    assert pd.Series(a.ravel()).value_counts().eq(82).all()

def test_series_probability_symmetry():
    m=module('04_season_simulator')
    assert np.isclose(m._series_probability(.5,.5),.5)
    assert np.isclose(m._series_probability(1.,1.),1.)
    assert np.isclose(m._series_probability(0.,0.),0.)

def test_rolling_backtest_does_not_use_target_outcomes():
    m=module('04_season_simulator');rng=np.random.default_rng(5)
    rows=[]
    for season in range(2019,2025):
        for t in range(30):
            net=(t-15)/3+rng.normal()
            rows.append(dict(team_id=t,season=season,season_type='regular',net_rating=net,wins=41+2*net+rng.normal(),games=82))
    d=pd.DataFrame(rows);a=m.backtest(d)
    first=a.target_season.min();d.loc[d.season.eq(first),'net_rating']+=40;d.loc[d.season.eq(first),'wins']+=10
    b=m.backtest(d)
    np.testing.assert_allclose(a.loc[a.target_season.eq(first),'pred_wins'],b.loc[b.target_season.eq(first),'pred_wins'])
    assert (a.train_through<a.target_season).all()
