# Release validation

Checked September 10, 2026 using Python 3.12 and R 4.6.1.

## Reproduction performed

The source archives were retrieved from the pinned commit, checked against its Git blob records and assigned SHA-256 checksums. All 65 archives were verified. The missing processed inputs were rebuilt, all five Python studies were run, all R extracts were regenerated and all three R studies were run with native R.

The rebuild produced 454,942 stints, 1,571,217 shot records and 322 team-season-phase summaries. It reconstructed 8,782 of 8,879 source games. Stint points match source final scores in all reconstructed games. For the 2025–26 regular season, 1,136 of 1,230 games pass the stricter lineup eligibility screen. These checks establish internal reconciliation with the source, not independent certification of every event or inferred player assignment.

## Tests and notebooks

All **44 automated tests passed**. They cover possession endings, lineup handling, score conservation, rating estimates, training-only baselines, game-grouped evaluation, defender IDs, rolling fits, fixed playoff paths and published-result reconciliation.

All **eight review notebooks executed without cell errors**, with four executed code cells each. They recalculate selected findings from delivered result tables. They do not claim to refit all models within the notebooks; the full Python and R scripts perform those fits.

## Figures and articles

The release contains eight Markdown articles, eight standalone HTML articles, 28 PNG charts and 18 SVG companions. Every chart was visually reviewed. HTML images are embedded, and local Markdown links and image paths are checked during packaging.

## Reading the results

The optimizer scores 7.94 points per 100 below the normalized training allocation on later lineup outcomes. The rolling forecast has 8.56-win MAE over 120 team-seasons. Shot-model log loss is 0.6366 versus 0.6572 for its training-fitted zone baseline. These are observed evaluation results, including unfavorable ones.

Interpretation limits are part of each article and METHODS.md. Reproduction uses a fixed public-data release; it is not a live feed or an injury-adjusted current forecast. Exact image bytes may vary by platform and plotting backend.
