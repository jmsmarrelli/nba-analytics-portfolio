# Shared methods

## Source freeze

Archive commit `e829d4678be1e075f99e5d41a1c5f97089be446b` is fixed for this release. The three source families are play-by-play, shots and matchups. Analysis seasons run from 2019–20 through 2025–26, including playoffs where stated. Earlier shot logs, back to 1996–97, support first-observed-season estimates. A season suffix denotes its starting year. First shot-log appearance is a proxy for debut; players present at the beginning of coverage are treated as left-censored.

## Reconstruction and eligibility

Events follow `actionId`; shot joins retain `actionNumber` as a separate identifier. Player names are normalized within a per-game roster. Inferred opening lineups can require a repair, which is recorded rather than treated as reliable evidence. Player-lineup models require five players per side throughout, no period repairs, no unresolved substitutions and no score decrease or reversed clock. These tests are necessary screens, not independent certification of every inferred identity.

Stints break on lineup, game and period changes. Points sum event score increments; duration sums the intervals to following events. Both include boundaries that were previously lost by subtracting a stint’s first event from its last. Non-lineup score accounting can retain reconstructed games that fail player eligibility. Unreconstructed games are reported separately.

The possession parser counts ordinary changes of control and avoids separately ending an and-one basket and its free throw. Retained-possession special free throws do not create ordinary endings. Rebounds compare the rebounding team with the last shooting team within the period. Stint exposure uses half the combined count of team endings. It approximates team possessions, especially in short stints, and is not an official possession feed.

## Ratings and allocation

Lineup rates shrink toward a team prior. A variance decomposition estimates the noise and signal components; explicit fallback values are used if components cannot be estimated positively. Descriptive full-sample shrinkage and training-only allocation fits are separate. The allocation uses actual dates, training-only eligibility and a 48-minute normalization for both alternatives. Later lineup rates are observational outcomes, not counterfactual responses to an intervention.

RAPM fits offensive scoring rates with separate offensive and defensive player terms. Qualified players are selected by their modeled exposure. Ridge penalties are compared using five game-grouped folds, keeping both perspectives of every stint together. The selected-fold score is a tuning diagnostic, not an independent evaluation of the final selected model. The coefficients are centered by the ridge fit and have no replacement-player interpretation. Eligibility thresholds differ across the impact and development studies, so their ratings need not be numerically identical.

On/off rim analysis joins shots to exact event/player IDs in the reconstructed feed. It defines near-rim attempts as recorded distance at most six feet. Matchup summaries group by the nested matchup player, who is the defender; the outer player is the scorer. The [endpoint documentation](https://github.com/swar/nba_api/blob/master/docs/nba_api/stats/endpoints/boxscorematchupsv3.md) distinguishes offensive and defensive player fields. Assigned matchups do not remove help defense or assignment selection.

## Forecasting

The season model is a historical carry-over baseline. Rolling evaluation trains only through the year preceding each target; historical wins are normalized to 82 games. The interval combines estimated carry-over variation with a fixed 4.5-win allowance for within-season variation. The 120-row evaluation covers win totals, not the calibration of title probabilities.

Simulation uses a synthetic 82-game slate, independent strength draws, game noise and home advantage estimated from historical data. It omits actual scheduling, travel, rest, current roster moves and player availability. Standings ties are random. The playoff path is fixed: 1/8 connects to 4/5, and 2/7 to 3/6, consistent with the [NBA bracket structure](https://cdn.nba.com/teams/uploads/sites/1610612760/2024/04/2024FinalGuide.pdf). Higher seed hosts within a conference; Finals home court uses simulated regular-season wins with random tie resolution.

## Shot context

The classifier trains on six seasons and evaluates the seventh. Its zone-rate baseline is estimated from training outcomes. Early stopping uses a training-season validation subset; no current-season outcome enters that fit. Features include recorded action labels and period time, but no shooter identity, contest distance or shot clock. The analysis is retrospective and conditioned on an attempt. Residuals cannot establish isolated shooting skill, causal shot creation or future regression.

## R studies

The development study weights consecutive-season deltas by the smaller minutes sample and compares their cumulative path with a player fixed-effects natural spline. A 400-player-bootstrap procedure yields 80% intervals for the mean curve and its steps. Those intervals do not include individual next-season uncertainty or refitting upstream rating models. Experience is not age; calendar effects, changing roles and survivorship remain concerns.

Style PCA standardizes seven current-season tempo/location features. Ward clustering uses the same feature space with a chosen four-cluster cut. Earlier seasons are projected into that retrospective basis. Cluster membership alone does not establish historical convergence, tactical similarity or matchup success.

Finals quarter totals are scoring-accounting outputs. The five-game resampling draws observed stints with replacement within a game, altering frequency, playing time and scoring composition. Ties receive a random winner. The output is not a seven-game series probability or a test of whether the observed champion was deserved. The [NBA Finals schedule](https://cdn-uat.nba.com/news/2026-nba-finals-schedule) provides an external record of the game results.

## Scope

The collection is exploratory. Most player and team displays are point estimates without intervals, not significance claims. No model here identifies a causal coaching intervention. Event links support follow-up review; no film has been coded. Contemporary availability and roster decisions require information outside this historical release.
