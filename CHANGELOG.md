# Changelog

Corrections made between the first working version of these studies and this release.

| Area | Correction |
| --- | --- |
| Lineup inputs | Exclude unresolved or repaired games from player-lineup models; retain explicit eligibility records. |
| Stints | Preserve scoring increments, time between events and period boundaries. |
| Possessions | Keep and-ones together and avoid ordinary endings for retained-possession special free throws. |
| Shot-to-lineup join | Use source event and player IDs instead of ambiguous displayed-clock intervals. |
| Defensive matchups | Aggregate by the nested defender ID; the outer record belongs to the scorer. |
| RAPM evaluation | Group folds by game, including both sides of each stint; remove replacement-level language. |
| Rotation exercise | Select the player pool and most-used unit on training data; split by dates; normalize both minute allocations consistently. |
| Shot baseline | Estimate zone make rates from training outcomes rather than the test season. |
| Forecast evaluation | Use rolling historical fits and normalize shortened seasons to 82 games. |
| Playoff simulation | Follow fixed bracket paths and avoid true-strength tie breaks. |
| Forecast scope | Remove unsourced odds and transaction adjustments; publish a clearly labeled historical baseline. |
| Development interpretation | Distinguish elapsed experience, mean-curve uncertainty and individual forecasting uncertainty. |
| Finals interpretation | Describe stint resampling as a sensitivity exercise, not reordered possessions or a seven-game win probability. |

The separate scouting-sheet project also corrects offensive-rebound percentage to use opponent defensive rebounds and adds defensive panels.
