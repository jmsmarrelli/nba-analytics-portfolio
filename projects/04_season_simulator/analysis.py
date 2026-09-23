"""Historical carry-over baseline with rolling evaluation and a fixed playoff bracket."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from nbalab import viz
from nbalab.config import CONFERENCE_BY_ID, SPURS_ID, TEAM_BY_TRICODE, TRICODE_BY_ID, season_label
from nbalab.io import load_table
HERE = Path(__file__).parent
FIG = HERE / "figures"
FIG.mkdir(exist_ok=True)
BASE_SEASON = 2025
TARGET_SEASON = 2026
N_SIMS = 20000
SEED = 20262027
_HOME_PATTERN = (True, True, False, False, True, False, True)

def fit_carryover(teams: pd.DataFrame) -> dict:
    """Regress each team's net rating on the previous season's."""
    reg = teams[teams["season_type"] == "regular"]
    wide = reg.pivot(index="team_id", columns="season", values="net_rating")
    xs, ys = [], []
    for s in sorted(wide.columns)[:-1]:
        nxt = s + 1
        if nxt not in wide.columns:
            continue
        m = wide[s].notna() & wide[nxt].notna()
        xs.extend(wide.loc[m, s])
        ys.extend(wide.loc[m, nxt])
    xs, ys = np.array(xs), np.array(ys)
    slope, intercept = np.polyfit(xs, ys, 1)
    resid = ys - (slope * xs + intercept)
    return {"slope": float(slope), "intercept": float(intercept),
            "resid_sd": float(resid.std(ddof=2)), "n": len(xs),
            "r": float(np.corrcoef(xs, ys)[0, 1])}

def fit_game_noise(games: pd.DataFrame, teams: pd.DataFrame) -> dict:
    """Standard deviation of a single game's margin around expectation."""
    reg = games[games["season_type"] == "regular"].copy()
    net = (teams[teams["season_type"] == "regular"]
           .set_index(["season", "team_id"])["net_rating"])
    reg["own"] = list(zip(reg["season"], reg["team_id"]))
    reg["opp"] = list(zip(reg["season"], reg["opponent_id"]))
    reg["own_net"] = reg["own"].map(net)
    reg["opp_net"] = reg["opp"].map(net)
    reg = reg.dropna(subset=["own_net", "opp_net"])
    reg["margin"] = reg["points"] - reg["opp_points"]
    reg["expected"] = reg["own_net"] - reg["opp_net"]

    home = reg[reg["is_home"]]
    hca = float((home["margin"] - home["expected"]).mean())
    resid = reg["margin"] - reg["expected"] - np.where(reg["is_home"], hca, -hca)
    return {"hca": hca, "sd": float(resid.std())}

def build_schedule(team_ids: list[int]) -> np.ndarray:
    """An exactly-82-game schedule with the NBA's conference structure.

    Each team plays 30 inter-conference games (two against each of the 15
    teams in the other conference, one home and one away) and 52
    intra-conference games: four against ten opponents and three against the
    other four.  Which four get the short series is decided by a circulant
    pairing -- team ``i`` plays teams ``i +/- 1`` and ``i +/- 2`` three times --
    which is symmetric by construction, so both sides of every matchup agree
    on how often they meet.

    Getting this exactly right matters: an approximate schedule that gives
    teams 79 or 84 games shifts every win projection and quietly breaks the
    comparison against a real 82-game season.
    """
    east = [t for t in team_ids if CONFERENCE_BY_ID[t] == "East"]
    west = [t for t in team_ids if CONFERENCE_BY_ID[t] == "West"]

    games: list[tuple[int, int]] = []
    for group in (east, west):
        n = len(group)
        for i, a in enumerate(group):
            for j in range(i + 1, n):
                b = group[j]
                gap = min((j - i) % n, (i - j) % n)
                if gap <= 2:                      # three-game series
                    games += [(a, b), (b, a), (a, b) if (i + j) % 2 else (b, a)]
                else:                             # four-game series
                    games += [(a, b), (b, a), (a, b), (b, a)]
    for a in east:
        for b in west:
            games += [(a, b), (b, a)]

    sched = np.array(games)
    counts = pd.Series(np.concatenate([sched[:, 0], sched[:, 1]])).value_counts()
    if not (counts == 82).all():
        raise AssertionError(
            f"schedule is not 82 games per team: {sorted(counts.unique())}")
    return sched

def _game(true: np.ndarray, a: int, b: int, rng: np.random.Generator,
          game_sd: float, hca: float) -> bool:
    """True if ``a`` wins a single game hosted by ``a``."""
    return (true[a] - true[b] + hca + rng.normal(0.0, game_sd)) > 0

def _series_probability(p_home: float, p_away: float) -> float:
    """Probability the home team wins a best-of-seven under 2-2-1-1-1.

    Computed by dynamic programming over the seven scheduled games rather
    than simulated game by game.  Across twenty thousand seasons the bracket
    involves millions of individual games; evaluating each one with its own
    random draw dominates the runtime and adds nothing, because only the
    series outcome is ever used.
    """
    # state[(wins_a, wins_b)] -> probability
    state = {(0, 0): 1.0}
    for is_home in _HOME_PATTERN:
        p = p_home if is_home else p_away
        nxt: dict[tuple[int, int], float] = {}
        for (wa, wb), prob in state.items():
            if wa == 4 or wb == 4:
                nxt[(wa, wb)] = nxt.get((wa, wb), 0.0) + prob
                continue
            nxt[(wa + 1, wb)] = nxt.get((wa + 1, wb), 0.0) + prob * p
            nxt[(wa, wb + 1)] = nxt.get((wa, wb + 1), 0.0) + prob * (1 - p)
        state = nxt
    return sum(prob for (wa, _), prob in state.items() if wa == 4)

def _series(true: np.ndarray, a: int, b: int, rng: np.random.Generator,
            game_sd: float, hca: float) -> bool:
    """Best-of-seven with 2-2-1-1-1 home advantage to ``a``."""
    from math import erf, sqrt
    diff = true[a] - true[b]
    p_home = 0.5 * (1 + erf((diff + hca) / (game_sd * sqrt(2))))
    p_away = 0.5 * (1 + erf((diff - hca) / (game_sd * sqrt(2))))
    return rng.random() < _series_probability(p_home, p_away)

def fig_projection(proj: pd.DataFrame) -> None:
    """Projected wins with an uncertainty interval, ordered by projection."""
    df = proj.sort_values("proj_wins", ascending=True)
    colors = [viz.HIGHLIGHT if t == SPURS_ID else
              (viz.CATEGORICAL[0] if CONFERENCE_BY_ID[t] == "West" else viz.FIELD_COLOR)
              for t in df["team_id"]]

    fig, ax = plt.subplots(figsize=(9.5, 10))
    y = np.arange(len(df))
    ax.hlines(y, df["wins_p10"], df["wins_p90"], color=viz.GRID, linewidth=6)
    ax.scatter(df["proj_wins"], y, s=52, color=colors, zorder=4,
               edgecolor=viz.SURFACE, linewidth=1.4)
    ax.set_yticks(y)
    ax.set_yticklabels(df["tricode"], fontsize=9)
    for lbl, t in zip(ax.get_yticklabels(), df["team_id"]):
        if t == SPURS_ID:
            lbl.set_color(viz.HIGHLIGHT); lbl.set_fontweight("bold")
    for yi, (m, lo, hi) in enumerate(zip(df["proj_wins"], df["wins_p10"], df["wins_p90"])):
        ax.text(hi + 0.8, yi, f"{m:.0f}", va="center", fontsize=8.5,
                color=viz.INK_SECONDARY)
    ax.axvline(41, color=viz.INK_MUTED, linewidth=1, linestyle=":")
    ax.set_xlabel(f"Projected wins, {season_label(TARGET_SEASON)}  ·  bar spans the 10th-90th percentile")

    from matplotlib.lines import Line2D
    ax.legend(handles=[
        Line2D([], [], marker="o", linestyle="", color=viz.HIGHLIGHT, label="Spurs"),
        Line2D([], [], marker="o", linestyle="", color=viz.CATEGORICAL[0], label="West"),
        Line2D([], [], marker="o", linestyle="", color=viz.FIELD_COLOR, label="East"),
    ], loc="lower right")
    viz.annotate(ax, f"Projected standings, {season_label(TARGET_SEASON)}",
                 f"{N_SIMS:,} simulated seasons · historical carry-over baseline; no roster or availability updates")
    viz.save(fig, FIG / "projected_wins.png")

def fig_spurs_distribution(sim: dict, proj: pd.DataFrame,
                           team_ids: list[int]) -> None:
    idx = {t: i for i, t in enumerate(team_ids)}
    wins = sim["wins"][:, idx[SPURS_ID]]
    okc = sim["wins"][:, idx[TEAM_BY_TRICODE["OKC"].team_id]]

    fig, ax = plt.subplots(figsize=(9.5, 5))
    bins = np.arange(wins.min() - 1, wins.max() + 2) - 0.5
    ax.hist(okc, bins=bins, color=viz.FIELD_COLOR, alpha=0.85,
            label="Oklahoma City")
    ax.hist(wins, bins=bins, color=viz.HIGHLIGHT, alpha=0.8, label="San Antonio")
    ax.axvline(62, color=viz.INK_SECONDARY, linewidth=1.6, linestyle="--")
    ax.text(62, ax.get_ylim()[1] * 0.93, "  Spurs' 2025-26 total (62)",
            fontsize=9, color=viz.INK_SECONDARY)
    ax.set_xlabel(f"Wins, {season_label(TARGET_SEASON)}")
    ax.set_ylabel("Simulated seasons")
    ax.legend(loc="upper left")
    viz.annotate(ax, "Spurs and Thunder baseline win distributions",
                 f"{N_SIMS:,} simulations · uncertainty in next-season strength and game results")
    viz.save(fig, FIG / "spurs_vs_okc.png")

def fit_wins_model(teams):
    reg = teams[teams.season_type.eq("regular")]
    slope, intercept = np.polyfit(reg.net_rating, 82 * reg.wins / reg.games, 1)
    return dict(slope=float(slope), intercept=float(intercept))


def backtest(teams):
    reg = teams[teams.season_type.eq("regular")]
    rows = []
    for season in sorted(reg.season.unique())[2:-1]:
        history = reg[reg.season.le(season)]
        carry = fit_carryover(history)
        wins = fit_wins_model(history)
        base = history[history.season.eq(season)].set_index("team_id")
        later = reg[reg.season.eq(season+1)].set_index("team_id")
        for team in base.index.intersection(later.index):
            pred_net = carry["slope"] * base.loc[team,"net_rating"] + carry["intercept"]
            prediction = wins["slope"] * pred_net + wins["intercept"]
            actual = 82 * later.loc[team,"wins"] / later.loc[team,"games"]
            sd = np.hypot(wins["slope"] * carry["resid_sd"], 4.5)
            rows.append(dict(train_through=season, target_season=season+1, team_id=team, pred_wins=prediction, actual_wins=actual, error=actual-prediction, sd_wins=sd, z=(actual-prediction)/sd, in_80=abs(actual-prediction)<1.2815516*sd))
    return pd.DataFrame(rows)


def conference_bracket(bracket, series):
    """Fixed path: 1/8 meets 4/5; 2/7 meets 3/6. Higher seed hosts."""
    rank = {team:i for i,team in enumerate(bracket)}
    def play(a,b):
        if rank[a]>rank[b]: a,b=b,a
        return a if series(a,b) else b
    first = [play(bracket[a], bracket[b]) for a,b in [(0,7),(3,4),(1,6),(2,5)]]
    last = [play(first[0],first[1]), play(first[2],first[3])]
    return play(*last),last


def simulate(strength, sd_team, schedule, team_ids, game_sd, hca, n_sims, rng):
    index = {t:i for i,t in enumerate(team_ids)}
    home = np.array([index[t] for t in schedule[:,0]])
    away = np.array([index[t] for t in schedule[:,1]])
    conf = np.array([CONFERENCE_BY_ID[t] for t in team_ids])
    out = {k:np.zeros(len(team_ids)) for k in ["playoff","conf_final","finals","title","top_seed"]}
    wins_out = np.zeros((n_sims,len(team_ids)))
    for run in range(n_sims):
        true = strength + rng.normal(0,sd_team)
        hw = true[home]-true[away]+hca+rng.normal(0,game_sd,len(home))>0
        wins = np.bincount(np.concatenate([home[hw],away[~hw]]), minlength=len(team_ids))
        wins_out[run] = wins
        champions=[]
        for c in ["East","West"]:
            idx=np.where(conf==c)[0]
            order=idx[np.lexsort((rng.random(len(idx)),-wins[idx]))]
            out["top_seed"][order[0]]+=1
            seven,eight,nine,ten=order[6:10]
            w78=seven if _game(true,seven,eight,rng,game_sd,hca) else eight
            l78=eight if w78==seven else seven
            w910=nine if _game(true,nine,ten,rng,game_sd,hca) else ten
            w8=l78 if _game(true,l78,w910,rng,game_sd,hca) else w910
            bracket=list(order[:6])+[w78,w8]
            out["playoff"][bracket]+=1
            champ,last=conference_bracket(bracket,lambda a,b:_series(true,a,b,rng,game_sd,hca))
            out["conf_final"][last]+=1
            out["finals"][champ]+=1
            champions.append(champ)
        a,b=champions
        if wins[b]>wins[a] or (wins[b]==wins[a] and rng.random()<.5):a,b=b,a
        winner=a if _series(true,a,b,rng,game_sd,hca) else b
        out["title"][winner]+=1
    return {"wins":wins_out,**{k:v/n_sims for k,v in out.items()}}


def main():
    viz.use_theme()
    teams=load_table("teams");games=load_table("games")
    carry=fit_carryover(teams);noise=fit_game_noise(games,teams)
    bt=backtest(teams);bt.to_csv(HERE/"backtest.csv",index=False)
    base=teams[teams.season.eq(BASE_SEASON)&teams.season_type.eq("regular")].copy()
    base["proj_net"]=carry["slope"]*base.net_rating+carry["intercept"]
    base["tricode"]=base.team_id.map(TRICODE_BY_ID)
    ids=base.team_id.tolist();schedule=build_schedule(ids)
    sim=simulate(base.proj_net.to_numpy(),np.full(len(base),carry["resid_sd"]),schedule,ids,noise["sd"],noise["hca"],N_SIMS,np.random.default_rng(SEED))
    base["proj_wins"]=sim["wins"].mean(axis=0)
    base["wins_p10"]=np.quantile(sim["wins"],.1,axis=0)
    base["wins_p90"]=np.quantile(sim["wins"],.9,axis=0)
    for k in ["playoff","conf_final","finals","title","top_seed"]:base[k]=sim[k]
    base.to_csv(HERE/"projection_2026_27.csv",index=False)
    pd.DataFrame(schedule,columns=["home","away"]).to_csv(HERE/"synthetic_schedule.csv",index=False)
    summary={"carryover":carry,"game_noise":noise,"simulations":N_SIMS,"backtest_rows":len(bt),"backtest_mae":bt.error.abs().mean(),"backtest_bias":bt.error.mean(),"backtest_80_coverage":bt.in_80.mean(),"seed":SEED,"roster_adjustments":False}
    (HERE/"summary.json").write_text(json.dumps(summary,indent=2))
    fig_projection(base)
    fig_spurs_distribution(sim,base,ids)
    fig,ax=plt.subplots(figsize=(9,6))
    ax.scatter(bt.pred_wins,bt.actual_wins,s=25,alpha=.6,color=viz.CATEGORICAL[0])
    ax.plot([10,75],[10,75],color=viz.GRID)
    ax.set_xlabel("Predicted wins per 82 games");ax.set_ylabel("Observed wins per 82 games")
    viz.annotate(ax,"Rolling forecasts against later seasons",f"{len(bt)} held-out team-seasons; 80% interval coverage {bt.in_80.mean():.1%}")
    viz.save(fig,FIG/"rolling_backtest.png")
    print(json.dumps(summary,indent=2))

if __name__=="__main__":main()
