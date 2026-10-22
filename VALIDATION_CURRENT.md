# Current validation — October 22, 2026

## Connected GitHub review — October 22, 2026

GitHub integration access is verified for `jmsmarrelli`, including repository push permission. The remote `main` commit matched the preserved local base before preparing this review. The completed overhaul is preserved on `feat/portfolio-review-2026-10-22`; publication uses the connected GitHub API because shell Git cannot resolve `github.com`. Original local commits remain intact; the API publication carries their complete final file tree in a review commit based on the verified remote main.

The owner authorizes feature branches and draft pull requests. Merging into `main` requires separate owner approval. Repository visibility, profile settings and Pages deployment configuration are unchanged. Cross-repository links target `main` for eventual publication; review the individual draft PRs until those changes are approved and merged. Merge the navigation hub after its linked study changes.

Fresh Python test rerun: **44 passed in 24.11s**. The rerun uses the existing Python 3.14 environment, not a fresh Python 3.12 install.

Flagship PNG/SVG exports were rebuilt from saved inputs in this continuation; numerical CSV/JSON inputs remained unchanged. This validates the presentation layer, not a new raw-data fit.

## What changed

Original issue: The Wembanyama article framed a total-impact coefficient as a defensive finding; development units were unclear.

Implemented: Separated total RAPM from rim and matchup indicators; labeled development steps in RAPM points per 100; reran all three R analyses and rebuilt eight HTML articles.

## Evidence and limits

44 Python tests passed.

44 Python checks pass. Five Python study refits and notebook execution still require source data. Optimizer results remain unfavorable.

Test/runtime checks used an existing Python 3.14.7 environment (NumPy 2.5.2, pandas 3.0.5, SciPy 1.18.1, scikit-learn 1.9.0, matplotlib 3.11.1, pytest 9.1.1). The older studies specify Python 3.12 and different NumPy/pandas pins. A fresh installation of that pinned environment was not possible offline and is a release gate. R execution used R 4.6.1 with an existing package library. Earlier validation files and executed notebooks describe earlier runs and were preserved; notebooks were not re-executed in this review.

HTML now uses the pinned CommonMark renderer `markdown-it-py==4.2.0` with tables; local and CI use the same renderer. This replaces an unavailable local Python-Markdown package. Generated result CSVs retain full precision; readable article tables round for display only. The seven-project Quarto collection uses its separate Pandoc fallback.

## Earlier local review and publication record

Changes are local to `audit/2026-10-22-portfolio`. No push, merge, repository visibility change or public release occurred. The local PR draft records the intended summary. Publication requires a reachable authenticated GitHub connection and the owner's approval. Read [PROVENANCE.md](PROVENANCE.md) before describing personal authorship or validation in an application.


## Earlier October 22 visual and publication follow-up

The flagship figure pipeline now exports an editorial PNG/SVG design from the same saved results; a new decision brief distinguishes evidence, proposed action and limitations. The five affected research repositories passed 102 tests in total in this follow-up (6 research offline, 15 Spurs research, 18 game management, 19 Western scouting, 44 NBA portfolio). The two raw-input research tests remain deselected, with their earlier failures documented. All 152 fingerprinted CSV/JSON/gzip inputs across those repositories remained byte-identical. Twelve flagship PNG/SVG exports were checked for deterministic regeneration. No additional model fit or data retrieval is implied.

The latest owner instruction authorizes feature branches and pull requests, but requires separate approval for any default-branch merge. Do not change repository visibility. The owner reports that GitHub is connected through ChatGPT; no GitHub repository or PR tools were exposed to this session when checked, so access and remote state remain unverified. Shell networking is still restricted. No further authentication attempt was made.
