"""Compare adjusted plus-minus, rim on/off splits and assigned defensive matchups."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from nbalab import viz
from nbalab.config import SPURS_ID, TRICODE_BY_ID, season_label
from nbalab.io import load_stints, load_table, player_names
from nbalab.ratings import rapm
from nbalab.sources import snapshot as S

from nbalab.possessions import _normalise_name as _fold

log = logging.getLogger("project03")
HERE = Path(__file__).parent
FIG = HERE / "figures"
FIG.mkdir(exist_ok=True)

SEASON = 2025
WEMBY = 1641705
RIM_DISTANCE = 6          # feet; the restricted-area radius is ~4, paint ~8

# Selected frontcourt comparisons; this list does not use betting prices.
COMPARISON_BIGS = {
    "Chet Holmgren": None, "Isaiah Hartenstein": None, "Nikola Jokic": None,
    "Evan Mobley": None, "Karl-Anthony Towns": None, "Jaren Jackson Jr.": None,
    "Alperen Sengun": None, "Rudy Gobert": None, "Jalen Duren": None,
    "Kristaps Porzingis": None,
}


# --------------------------------------------------------------------------
# 1. RAPM
# --------------------------------------------------------------------------

def league_rapm(season: int) -> pd.DataFrame:
    stints = load_stints(seasons=season, season_type="regular")
    log.info("fitting RAPM on %d stints", len(stints))
    out = rapm(stints, min_possessions=400)
    names = player_names()
    out["name"] = out["player_id"].map(names)
    log.info("chosen ridge penalty alpha=%s (cv R^2 %+.4f)",
             out.attrs["alpha"], out.attrs["cv_r2"])
    return out


# --------------------------------------------------------------------------
# 2. Rim deterrence
# --------------------------------------------------------------------------

def _spurs_shots_with_stints(season: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Link opponent attempts to eligible lineups using exact source event IDs."""
    import ast
    from nbalab.config import PROCESSED_DIR
    stints = load_stints(seasons=season, season_type="regular")
    ts = stints[(stints.home_team_id == SPURS_ID) | (stints.away_team_id == SPURS_ID)].copy()
    ts["spurs_lineup"] = np.where(ts.home_team_id == SPURS_ID, ts.home_lineup, ts.away_lineup)
    lookup = {(row.game_id, tuple(row.spurs_lineup)): row.Index for row in ts.itertuples()}
    links = pd.read_csv(PROCESSED_DIR / f"shot_lineups_{season}_regular.csv.gz")
    links = links[links.lineup_eligible.astype(str).str.lower().eq("true")].copy()
    links = links[links.home_team_id.eq(SPURS_ID) | links.away_team_id.eq(SPURS_ID)].copy()
    links["spurs_lineup"] = np.where(links.home_team_id.eq(SPURS_ID), links.home_lineup, links.away_lineup)
    links["spurs_lineup"] = links.spurs_lineup.map(ast.literal_eval)
    links["stint_row"] = [lookup.get((g, tuple(lu))) for g, lu in zip(links.gameId, links.spurs_lineup)]
    shots = load_table("shots")
    shots = shots[shots.season.eq(season) & shots.season_type.eq("regular") & shots.team_id.ne(SPURS_ID)].copy()
    shots = shots.merge(links[["gameId", "actionNumber", "personId", "stint_row"]], left_on=["game_id", "game_event_id", "player_id"], right_on=["gameId", "actionNumber", "personId"], how="inner", validate="one_to_one")
    assert shots.stint_row.notna().all()
    shots["at_rim"] = shots.shot_distance.le(RIM_DISTANCE)
    return shots, ts


def rim_split(shots: pd.DataFrame, team_stints: pd.DataFrame,
              player_id: int) -> dict:
    """On/off rim-defence split for one player, given the pre-joined shots."""
    on_stints = team_stints["spurs_lineup"].map(lambda lu: player_id in lu)
    on_flags = shots["stint_row"].map(on_stints)

    rows = {}
    for label, mask in (("on", on_flags), ("off", ~on_flags.astype(bool))):
        sel = shots[mask.astype(bool)]
        rim = sel[sel["at_rim"]]
        rows[label] = {
            "shots": len(sel),
            "rim_attempts": len(rim),
            "rim_share": len(rim) / max(len(sel), 1),
            "rim_fg_pct": rim["shot_made_flag"].mean() if len(rim) else np.nan,
            "overall_fg_pct": sel["shot_made_flag"].mean() if len(sel) else np.nan,
        }
    rows["diff"] = {k: rows["on"][k] - rows["off"][k]
                    for k in ("rim_share", "rim_fg_pct", "overall_fg_pct")}
    return rows


def rim_control_panel(season: int, players: list[int]) -> pd.DataFrame:
    """Apply one descriptive on/off calculation to every selected rotation player."""
    shots, team_stints = _spurs_shots_with_stints(season)
    names = player_names()
    rows = []
    for pid in players:
        r = rim_split(shots, team_stints, pid)
        rows.append({
            "player_id": pid,
            "name": names.get(pid, pid),
            "rim_share_on": r["on"]["rim_share"],
            "rim_share_off": r["off"]["rim_share"],
            "rim_share_delta": r["diff"]["rim_share"],
            "rim_fg_on": r["on"]["rim_fg_pct"],
            "rim_fg_off": r["off"]["rim_fg_pct"],
            "rim_fg_delta": r["diff"]["rim_fg_pct"],
            "opp_fg_delta": r["diff"]["overall_fg_pct"],
            "shots_on": r["on"]["shots"],
        })
    return pd.DataFrame(rows).sort_values("rim_fg_delta").reset_index(drop=True)


def on_off_rim_defence(season: int, player_id: int) -> dict:
    shots, stints = _spurs_shots_with_stints(season)
    return rim_split(shots, stints, player_id)


# --------------------------------------------------------------------------
# 3. Isolated matchups
# --------------------------------------------------------------------------

def matchup_defence(season: int, min_possessions: int = 150) -> pd.DataFrame:
    """Assigned-matchup rates; help defense and selection remain confounded."""
    frames = []
    for st in ("regular", "playoffs"):
        try:
            frames.append(S.load_matchups(season, st))
        except FileNotFoundError:
            continue
    m = pd.concat(frames, ignore_index=True)

    # The outer player is the scorer; the nested matchup player is the defender.
    g = m.groupby("matchups_person_id").agg(
        partial_possessions=("partial_possessions", "sum"),
        fgm=("matchup_field_goals_made", "sum"),
        fga=("matchup_field_goals_attempted", "sum"),
        fg3m=("matchup_three_pointers_made", "sum"),
        fg3a=("matchup_three_pointers_attempted", "sum"),
        blocks=("matchup_blocks", "sum"),
        help_blocks=("help_blocks", "sum"),
        turnovers=("matchup_turnovers", "sum"),
        points=("player_points", "sum"),
        minutes=("matchup_minutes_sort", "sum"),
    ).reset_index()

    g = g[g["partial_possessions"] >= min_possessions].copy()
    g["opp_fg_pct"] = g["fgm"] / g["fga"].replace(0, np.nan)
    g["opp_efg"] = (g["fgm"] + 0.5 * g["fg3m"]) / g["fga"].replace(0, np.nan)
    g["points_per_100"] = 100 * g["points"] / g["partial_possessions"]
    g["blocks_per_100"] = 100 * g["blocks"] / g["partial_possessions"]
    g["tov_forced_per_100"] = 100 * g["turnovers"] / g["partial_possessions"]

    names = player_names()
    g["name"] = g["matchups_person_id"].map(names)
    return g.rename(columns={"matchups_person_id": "player_id"}).reset_index(drop=True)


# --------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------

def _spurs_rotation(season: int, n: int = 10) -> list[int]:
    """The n Spurs who played the most minutes, by on-court stint time."""
    stints = load_stints(seasons=season, season_type="regular")
    ts = stints[(stints["home_team_id"] == SPURS_ID) |
                (stints["away_team_id"] == SPURS_ID)].copy()
    lineup = np.where(ts["home_team_id"] == SPURS_ID,
                      ts["home_lineup"], ts["away_lineup"])
    mins: dict[int, float] = {}
    for lu, sec in zip(lineup, ts["seconds"]):
        for pid in lu:
            mins[pid] = mins.get(pid, 0.0) + sec / 60.0
    return [p for p, _ in sorted(mins.items(), key=lambda kv: -kv[1])[:n]]


def fig_rim_control(panel: pd.DataFrame) -> None:
    """Wembanyama's rim effect against every teammate's, on the same axes."""
    df = panel.sort_values("rim_fg_delta")
    colors = [viz.HIGHLIGHT if p == WEMBY else viz.FIELD_COLOR
              for p in df["player_id"]]

    fig, axes = plt.subplots(1, 2, figsize=(12, 5.6), sharey=True)
    y = np.arange(len(df))

    for ax, col, title in (
        (axes[0], "rim_share_delta",
         "Change in the share of opponent shots taken at the rim"),
        (axes[1], "rim_fg_delta", "Change in opponent FG% at the rim"),
    ):
        ax.barh(y, 100 * df[col], color=colors, height=0.7)
        ax.axvline(0, color=viz.INK_SECONDARY, linewidth=1)
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("Percentage points, on-court minus off-court")
        for yi, v in enumerate(100 * df[col]):
            ax.text(v + (0.15 if v >= 0 else -0.15), yi, f"{v:+.1f}",
                    va="center", ha="left" if v >= 0 else "right",
                    fontsize=8.5, color=viz.INK_SECONDARY)
        ax.margins(x=0.2)

    axes[0].set_yticks(y)
    axes[0].set_yticklabels(df["name"], fontsize=10)
    for lbl, pid in zip(axes[0].get_yticklabels(), df["player_id"]):
        if pid == WEMBY:
            lbl.set_color(viz.HIGHLIGHT)
            lbl.set_fontweight("bold")

    fig.suptitle("On/off rim splits across San Antonio's rotation",
                 x=0.005, ha="left", fontsize=13, fontweight="semibold")
    fig.text(0.005, 0.925,
             f"Identical on/off calculation for all ten Spurs rotation players · "
             f"{season_label(SEASON)} regular season · negative is better defence",
             fontsize=10, color=viz.INK_SECONDARY, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    viz.save(fig, FIG / "rim_control.png")


def fig_rapm_leaders(r: pd.DataFrame) -> None:
    top = r.nlargest(20, "rapm").sort_values("rapm")
    colors = [viz.HIGHLIGHT if pid == WEMBY else viz.FIELD_COLOR
              for pid in top["player_id"]]

    fig, ax = plt.subplots(figsize=(9, 8))
    y = np.arange(len(top))
    ax.barh(y, top["rapm"], color=colors, height=0.72)
    ax.set_yticks(y)
    ax.set_yticklabels(top["name"], fontsize=9.5)
    for lbl, pid in zip(ax.get_yticklabels(), top["player_id"]):
        if pid == WEMBY:
            lbl.set_color(viz.HIGHLIGHT)
            lbl.set_fontweight("bold")
    for yi, v in enumerate(top["rapm"]):
        ax.text(v + 0.08, yi, f"{v:+.2f}", va="center", fontsize=8.5,
                color=viz.INK_SECONDARY)
    ax.set_xlabel("RAPM (ridge-centered points per 100)")
    viz.annotate(
        ax, "League RAPM leaders, 2025-26",
        "Ridge regression of offensive scoring on the ten players on the "
        "floor · minimum 400 possessions",
    )
    ax.margins(x=0.12)
    viz.save(fig, FIG / "rapm_leaders.png")


def fig_off_def_scatter(r: pd.DataFrame, bigs: list[int]) -> None:
    sel = r[r["player_id"].isin(bigs) | (r["player_id"] == WEMBY)].copy()
    fig, ax = plt.subplots(figsize=(8.5, 7))

    ax.axhline(0, color=viz.GRID, linewidth=1.2)
    ax.axvline(0, color=viz.GRID, linewidth=1.2)
    ax.scatter(r["o_rapm"], r["d_rapm"], s=12, color=viz.FIELD_COLOR,
               alpha=0.45, linewidths=0, label="All qualified players")

    others = sel[sel["player_id"] != WEMBY]
    ax.scatter(others["o_rapm"], others["d_rapm"], s=70,
               color=viz.CATEGORICAL[0], zorder=4, edgecolor=viz.SURFACE,
               linewidth=1.5, label="Contender bigs")
    w = sel[sel["player_id"] == WEMBY]
    ax.scatter(w["o_rapm"], w["d_rapm"], s=170, color=viz.HIGHLIGHT, zorder=6,
               edgecolor=viz.SURFACE, linewidth=2, label="Wembanyama")

    for row in sel.itertuples():
        ax.annotate(row.name, (row.o_rapm, row.d_rapm),
                    textcoords="offset points", xytext=({"Jalen Duren": (10,-12), "Karl-Anthony Towns": (10,-20), "Evan Mobley": (10,24), "Isaiah Hartenstein": (-65,-10)}.get(row.name,(9,4))), fontsize=9,
                    color=viz.HIGHLIGHT if row.player_id == WEMBY else viz.INK_SECONDARY,
                    fontweight="bold" if row.player_id == WEMBY else "normal")

    ax.set_xlabel("Offensive RAPM (per 100)")
    ax.set_ylabel("Defensive RAPM (per 100, positive is better)")
    ax.legend(loc="lower left")
    viz.annotate(
        ax, "Where Wembanyama sits among contending bigs",
        f"{season_label(SEASON)} regular season · both axes are the same "
        "ridge model, so offence and defence are directly comparable",
    )
    viz.save(fig, FIG / "rapm_bigs.png")


def fig_rim(rim: dict) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.6))

    for ax, key, title, fmt in (
        (axes[0], "rim_share",
         f"Share of opponent shots taken within {RIM_DISTANCE} feet", "{:.1%}"),
        (axes[1], "rim_fg_pct",
         f"Opponent FG% within {RIM_DISTANCE} feet", "{:.1%}"),
    ):
        vals = [rim["off"][key], rim["on"][key]]
        bars = ax.bar(["Wembanyama off", "Wembanyama on"], vals,
                      color=[viz.FIELD_COLOR, viz.HIGHLIGHT], width=0.55)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v, fmt.format(v),
                    ha="center", va="bottom", fontsize=11,
                    color=viz.INK, fontweight="semibold")
        ax.set_title(title, fontsize=11)
        ax.set_ylim(0, max(vals) * 1.3)
        ax.set_yticks([])
        ax.grid(False)
        ax.spines["left"].set_visible(False)

    fig.suptitle("Opponent rim attempts with Wembanyama on and off the floor",
                 x=0.005, ha="left", fontsize=13, fontweight="semibold")
    fig.text(0.005, 0.915,
             f"San Antonio opponents, {season_label(SEASON)} regular season · "
             f"{rim['on']['rim_attempts']:,} rim attempts on / "
             f"{rim['off']['rim_attempts']:,} off",
             fontsize=10, color=viz.INK_SECONDARY, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    viz.save(fig, FIG / "rim_deterrence.png")


def fig_matchup(md: pd.DataFrame, bigs: list[int]) -> None:
    sel = md[md["player_id"].isin(bigs + [WEMBY])].copy()
    sel = sel.sort_values("points_per_100")
    colors = [viz.HIGHLIGHT if p == WEMBY else viz.CATEGORICAL[0]
              for p in sel["player_id"]]

    fig, ax = plt.subplots(figsize=(9, 6))
    y = np.arange(len(sel))
    ax.barh(y, sel["points_per_100"], color=colors, height=0.7)
    ax.set_yticks(y)
    ax.set_yticklabels(sel["name"], fontsize=10)
    for lbl, pid in zip(ax.get_yticklabels(), sel["player_id"]):
        if pid == WEMBY:
            lbl.set_color(viz.HIGHLIGHT)
            lbl.set_fontweight("bold")
    for yi, (v, e) in enumerate(zip(sel["points_per_100"], sel["opp_efg"])):
        ax.text(v + 0.4, yi, f"{v:.1f}  (eFG {e:.1%})", va="center",
                fontsize=8.5, color=viz.INK_SECONDARY)
    ax.set_xlabel("Points allowed per 100 partial possessions as primary defender")
    viz.annotate(
        ax, "Opponent scoring in assigned defensive matchups",
        f"{season_label(SEASON)}, regular season and playoffs · only "
        "possessions where tracking names the player as the primary defender",
    )
    ax.margins(x=0.22)
    viz.save(fig, FIG / "matchup_defence.png")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    viz.use_theme()

    names = player_names()
    # Match on accent-folded names: the roster feed spells them Jokic/Sengun
    # in one place and Jokić/Şengün in another.
    folded = {_fold(v): k for k, v in names.items()}
    bigs, missing = [], []
    for n in COMPARISON_BIGS:
        pid = folded.get(_fold(n))
        (bigs.append(pid) if pid is not None else missing.append(n))
    if missing:
        log.warning("benchmark bigs not found in the player index: %s",
                    ", ".join(missing))
    log.info("benchmark bigs resolved: %d of %d", len(bigs), len(COMPARISON_BIGS))

    r = league_rapm(SEASON)
    r.to_csv(HERE / "rapm_2025_26.csv", index=False)

    w = r[r["player_id"] == WEMBY]
    if len(w):
        row = w.iloc[0]
        rank = int((r["rapm"] > row["rapm"]).sum()) + 1
        d_rank = int((r["d_rapm"] > row["d_rapm"]).sum()) + 1
        log.info("\nWembanyama: RAPM %+.2f (rank %d of %d), "
                 "offence %+.2f, defence %+.2f (rank %d)",
                 row["rapm"], rank, len(r), row["o_rapm"], row["d_rapm"], d_rank)

    # Control panel: the same on/off split for every Spurs rotation player.
    rotation = _spurs_rotation(SEASON)
    panel = rim_control_panel(SEASON, rotation)
    panel.to_csv(HERE / "rim_control_panel.csv", index=False)
    log.info("\nOn/off rim defence for the whole rotation (the control):")
    log.info("%s", panel[["name", "rim_share_delta", "rim_fg_delta", "opp_fg_delta"]]
             .assign(**{c: (panel[c] * 100).round(1)
                        for c in ("rim_share_delta", "rim_fg_delta", "opp_fg_delta")})
             .to_string(index=False))

    rim = on_off_rim_defence(SEASON, WEMBY)
    log.info("\nRim defence, Spurs opponents:")
    log.info("  rim attempt share   on %.1f%%  off %.1f%%  (%+.1f pp)",
             100 * rim["on"]["rim_share"], 100 * rim["off"]["rim_share"],
             100 * rim["diff"]["rim_share"])
    log.info("  rim FG%%             on %.1f%%  off %.1f%%  (%+.1f pp)",
             100 * rim["on"]["rim_fg_pct"], 100 * rim["off"]["rim_fg_pct"],
             100 * rim["diff"]["rim_fg_pct"])
    log.info("  overall opp FG%%     on %.1f%%  off %.1f%%  (%+.1f pp)",
             100 * rim["on"]["overall_fg_pct"], 100 * rim["off"]["overall_fg_pct"],
             100 * rim["diff"]["overall_fg_pct"])

    md = matchup_defence(SEASON)
    md.to_csv(HERE / "matchup_defence.csv", index=False)
    wm = md[md["player_id"] == WEMBY]
    if len(wm):
        row = wm.iloc[0]
        log.info("\nAs primary defender: %.1f points allowed per 100 partial "
                 "possessions, opponent eFG %.1f%% over %.0f possessions",
                 row["points_per_100"], 100 * row["opp_efg"],
                 row["partial_possessions"])

    fig_rapm_leaders(r)
    fig_off_def_scatter(r, bigs)
    fig_rim(rim)
    fig_rim_control(panel)
    fig_matchup(md, bigs)

    pd.DataFrame([{
        "rapm": float(w.iloc[0]["rapm"]) if len(w) else np.nan,
        "o_rapm": float(w.iloc[0]["o_rapm"]) if len(w) else np.nan,
        "d_rapm": float(w.iloc[0]["d_rapm"]) if len(w) else np.nan,
        "rim_share_delta": rim["diff"]["rim_share"],
        "rim_fg_delta": rim["diff"]["rim_fg_pct"],
        "matchup_points_per_100": float(wm.iloc[0]["points_per_100"]) if len(wm) else np.nan,
        "ridge_alpha": r.attrs["alpha"],
        "ridge_cv_r2": r.attrs["cv_r2"],
    }]).to_csv(HERE / "summary.csv", index=False)

    log.info("\nwrote 4 figures and 3 tables to %s", HERE)


if __name__ == "__main__":
    main()
