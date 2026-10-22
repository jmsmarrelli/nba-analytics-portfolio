# Basketball statistics portfolio

[Read the basketball decision brief](reports/00_decision_brief.md) · [Visual design and rebuild](tools/VISUALS.md)

Joseph Smarrelli · September 2026

Eight studies of NBA lineup data, player impact, forecasting, shot context, development, playing style and the 2026 Finals. The package contains finished articles, regenerated figures, Python and R source, review notebooks, derived tables and a pinned source manifest.

## Read the studies

- [When a lineup reconstruction is ready to use](reports/01_data_pipeline.md)
- [A rotation optimizer can lose to the allocation it replaces](reports/02_lineup_optimizer.md)
- [Three views of Wembanyama’s defensive season](reports/03_wemby_impact.md)
- [A historical baseline for the next season](reports/04_season_simulator.md)
- [Separating recorded shot context from conversion](reports/05_shot_quality.md)
- [What an experience curve can tell the Spurs](reports/06_development_curves_R.md)
- [Where the contenders sit in shot-location space](reports/07_contender_style_R.md)
- [The first-quarter lead and the rest of the Finals](reports/08_finals_postmortem_R.md)

## Reproduce

Python 3.12 and R 4.6.1 were used for this release. The R analyses require only standard R libraries. From this repository’s root:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
make fetch PYTHON=python
make all PYTHON=python
```

The download retrieves 65 pinned archives, about 158 MiB compressed, and verifies SHA-256 hashes before extracting the expected CSV member. Raw and processed caches are excluded from the distribution. The complete build reconstructs the missing analysis inputs before running the projects. Existing processed tables are reused; pass `--force` to `python -m nbalab.pipeline build` after changing reconstruction code.

For a quick check of the included results:

```sh
python -m pytest tests -q
Rscript projects/06_development_curves_R/analysis.R
Rscript projects/07_contender_style_R/analysis.R
Rscript projects/08_finals_postmortem_R/analysis.R
```

The small R extracts are included, so these three runs do not require a raw download. The notebooks recalculate selected results and checks from delivered tables; the source scripts perform the complete model fits. They are different levels of reproduction, documented in each notebook.

## How to read the findings

The rotation exercise does not show a successful improvement. The defensive study adjusts for listed players but makes no claim to isolate a causal effect. The simulator is a historical carry-over baseline with rolling evaluation and a fixed playoff bracket. The shot model conditions on recorded attempts. The development curve estimates a population mean, and the Finals resampling is a sensitivity exercise.

These limits define what the projects measure. None is represented as work deployed by an NBA team, a current injury-adjusted forecast or completed film coding.

See [METHODS.md](METHODS.md), [VALIDATION.md](VALIDATION.md), [CHANGELOG.md](CHANGELOG.md) and [data/README.md](data/README.md).

## Sources and rights

Input records come from the [versioned public NBA archive](https://github.com/shufinskiy/nba_data/tree/e829d4678be1e075f99e5d41a1c5f97089be446b). The source manifest identifies each archive, URL and checksum. Code and documentation use the included MIT license; original data remain subject to their owners’ terms.

## Current review

See [current validation](VALIDATION_CURRENT.md) for executed checks and unresolved rebuild requirements, and [provenance](PROVENANCE.md) for AI assistance. [Portfolio navigation](https://github.com/jmsmarrelli/basketball-analytics).
