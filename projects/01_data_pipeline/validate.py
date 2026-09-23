"""Reconcile source scores, stint totals, clocks and lineup eligibility."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from nbalab.config import PROCESSED_DIR
from nbalab.io import load_table
from nbalab import viz
HERE=Path(__file__).parent

def main():
    viz.use_theme()
    games=load_table('games');stints=load_table('stints')
    totals=stints.groupby(['season','season_type','game_id']).agg(home_points=('home_points','sum'),away_points=('away_points','sum'),seconds=('seconds','sum'),possessions=('possessions','sum')).reset_index()
    home=games[games.is_home.astype(str).str.lower().eq('true')].rename(columns={'points':'source_home','opp_points':'source_away'})
    check=home.merge(totals,on=['season','season_type','game_id'],how='left',validate='one_to_one')
    check['score_matches']=check.source_home.eq(check.home_points)&check.source_away.eq(check.away_points)
    check['has_reconstruction']=check.home_points.notna()
    check.to_csv(HERE/'game_reconciliation.csv',index=False)
    audits=pd.concat([pd.read_csv(p) for p in sorted(PROCESSED_DIR.glob('audit_*.csv'))],ignore_index=True)
    coverage=audits.groupby(['season','season_type']).agg(reconstructed=('game_id','size'),five_each_side=('clean_size','sum'),eligible=('lineup_eligible','sum'),repairs=('repairs','sum'),unresolved_subs=('unresolved_subs','sum')).reset_index()
    source=home.groupby(['season','season_type']).size().rename('source_games').reset_index()
    coverage=source.merge(coverage,on=['season','season_type'],how='left')
    coverage['eligible_rate']=coverage.eligible/coverage.source_games
    coverage.to_csv(HERE/'reconstruction_quality.csv',index=False)
    audits.to_csv(HERE/'game_eligibility.csv.gz',index=False)
    summary={'source_games':len(home),'reconstructed_games':int(check.has_reconstruction.sum()),'score_matches_in_reconstructed':int(check.loc[check.has_reconstruction,'score_matches'].sum()),'eligible_2025_regular':int(coverage.query("season==2025 and season_type=='regular'").eligible.iloc[0]),'source_2025_regular':int(coverage.query("season==2025 and season_type=='regular'").source_games.iloc[0])}
    (HERE/'summary.json').write_text(json.dumps(summary,indent=2))
    d=coverage[coverage.season_type.eq('regular')]
    fig,ax=plt.subplots(figsize=(9,5))
    x=np.arange(len(d));ax.bar(x-.18,d.five_each_side/d.source_games,width=.36,color=viz.FIELD_COLOR,label='Five players on each side')
    ax.bar(x+.18,d.eligible_rate,width=.36,color=viz.CATEGORICAL[0],label='Eligible for lineup models')
    ax.set_xticks(x,[f'{s}–{str(s+1)[-2:]}' for s in d.season]);ax.set_ylim(0,1.15)
    ax.set_ylabel('Share of source games');ax.legend(loc='lower right')
    viz.annotate(ax,'Five players is a necessary check, not a complete audit','Lineup models also exclude unresolved substitutions, repaired periods and score or clock reversals')
    viz.save(fig,HERE/'figures/validation.png')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
