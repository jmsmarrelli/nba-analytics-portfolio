# Data files

`source_manifest.json` lists the pinned raw archives. They are fetched into `data/raw/snapshot/`; the processed cache is built locally and excluded from the GitHub package.

## Included extracts

- `r_extracts/player_seasons.csv`: player, season, first-observed experience, censored-debut flag, eligible minutes and offensive/defensive/total ridge ratings.
- `r_extracts/team_style.csv`: team-season tempo and shot-location features, with contextual team ratings and records.
- `r_extracts/finals_stints.csv`: game/quarter scoring, approximate exposure and duration. Player names are retained for traceability; two games have unresolved lineup records and are used only for scoring here.
- `r_extracts/finals_shots.csv`: attempts, locations, shot values and make indicators in the Finals.
- `r_extracts/finals_player_games.csv`: per-player field-goal lines; `points` excludes free throws.
- `r_extracts/spurs_lineups.csv`: eligible five-man totals and descriptive rates.

Each project directory contains its result tables. The pipeline project supplies per-game reconciliation and eligibility. The allocation project supplies candidate weights, later ratings and shuffled draws. The shot project supplies outcomes and frozen model/baseline predictions. Simulation includes its synthetic schedule and rolling forecasts.

Game/event IDs are integers. External NBA viewers may require game IDs padded to ten digits. Shot coordinates are in tenths of feet; elapsed and remaining clocks are in seconds. Model residuals and percentages are defined in the articles rather than assumed to match official NBA metrics.
