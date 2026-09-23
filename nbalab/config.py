"""Central configuration: paths, season definitions, team metadata.

Every module in ``nbalab`` resolves file locations through this module so that
the repository can be relocated (or pointed at a different data snapshot)
by changing a single environment variable, ``NBALAB_DATA``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent

DATA_ROOT = Path(os.environ.get("NBALAB_DATA", REPO_ROOT / "data")).resolve()
RAW_DIR = DATA_ROOT / "raw" / "snapshot"
PROCESSED_DIR = DATA_ROOT / "processed"
FIGURE_DIR = REPO_ROOT / "docs" / "figures"

for _d in (PROCESSED_DIR, FIGURE_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------
# Seasons
# --------------------------------------------------------------------------
# The snapshot labels a season by its *start* year: 2025 == the 2025-26
# season.

CURRENT_SEASON = 2025            # 2025-26, the most recent completed season
UPCOMING_SEASON = 2026           # 2026-27, the season being projected
SNAPSHOT_SEASONS = [2019, 2020, 2021, 2022, 2023, 2024, 2025]


def season_label(season: int) -> str:
    """2025 -> '2025-26'."""
    return f"{season}-{str(season + 1)[-2:]}"


# --------------------------------------------------------------------------
# Teams
# --------------------------------------------------------------------------

SPURS_ID = 1610612759
SPURS_TRICODE = "SAS"


@dataclass(frozen=True)
class Team:
    team_id: int
    tricode: str
    name: str
    conference: str


TEAMS: tuple[Team, ...] = (
    Team(1610612737, "ATL", "Atlanta Hawks", "East"),
    Team(1610612738, "BOS", "Boston Celtics", "East"),
    Team(1610612751, "BKN", "Brooklyn Nets", "East"),
    Team(1610612766, "CHA", "Charlotte Hornets", "East"),
    Team(1610612741, "CHI", "Chicago Bulls", "East"),
    Team(1610612739, "CLE", "Cleveland Cavaliers", "East"),
    Team(1610612742, "DAL", "Dallas Mavericks", "West"),
    Team(1610612743, "DEN", "Denver Nuggets", "West"),
    Team(1610612765, "DET", "Detroit Pistons", "East"),
    Team(1610612744, "GSW", "Golden State Warriors", "West"),
    Team(1610612745, "HOU", "Houston Rockets", "West"),
    Team(1610612754, "IND", "Indiana Pacers", "East"),
    Team(1610612746, "LAC", "LA Clippers", "West"),
    Team(1610612747, "LAL", "Los Angeles Lakers", "West"),
    Team(1610612763, "MEM", "Memphis Grizzlies", "West"),
    Team(1610612748, "MIA", "Miami Heat", "East"),
    Team(1610612749, "MIL", "Milwaukee Bucks", "East"),
    Team(1610612750, "MIN", "Minnesota Timberwolves", "West"),
    Team(1610612740, "NOP", "New Orleans Pelicans", "West"),
    Team(1610612752, "NYK", "New York Knicks", "East"),
    Team(1610612760, "OKC", "Oklahoma City Thunder", "West"),
    Team(1610612753, "ORL", "Orlando Magic", "East"),
    Team(1610612755, "PHI", "Philadelphia 76ers", "East"),
    Team(1610612756, "PHX", "Phoenix Suns", "West"),
    Team(1610612757, "POR", "Portland Trail Blazers", "West"),
    Team(1610612758, "SAC", "Sacramento Kings", "West"),
    Team(SPURS_ID, SPURS_TRICODE, "San Antonio Spurs", "West"),
    Team(1610612761, "TOR", "Toronto Raptors", "East"),
    Team(1610612762, "UTA", "Utah Jazz", "West"),
    Team(1610612764, "WAS", "Washington Wizards", "East"),
)

TEAM_BY_ID = {t.team_id: t for t in TEAMS}
TEAM_BY_TRICODE = {t.tricode: t for t in TEAMS}
TRICODE_BY_ID = {t.team_id: t.tricode for t in TEAMS}
NAME_BY_ID = {t.team_id: t.name for t in TEAMS}
CONFERENCE_BY_ID = {t.team_id: t.conference for t in TEAMS}


# --------------------------------------------------------------------------
# Analysis constants
# --------------------------------------------------------------------------

# Possession-ending event families, used by the possession parser.
LEAGUE_AVG_PACE_FALLBACK = 99.0
