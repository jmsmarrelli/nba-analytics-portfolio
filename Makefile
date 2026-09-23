.PHONY: fetch data projects r extracts test reports notebooks all
PYTHON ?= python3
RSCRIPT ?= Rscript
export PYTHONPATH := .
export OMP_NUM_THREADS := 4
fetch:
	$(PYTHON) tools/fetch_snapshot.py
data:
	$(PYTHON) -m nbalab.pipeline build
projects: data
	$(PYTHON) projects/01_data_pipeline/validate.py
	$(PYTHON) projects/02_lineup_optimizer/analysis.py
	$(PYTHON) projects/03_wemby_impact/analysis.py
	$(PYTHON) projects/04_season_simulator/analysis.py
	$(PYTHON) projects/05_shot_quality/analysis.py
extracts: data
	$(PYTHON) tools/export_for_r.py
r: extracts
	$(RSCRIPT) projects/06_development_curves_R/analysis.R
	$(RSCRIPT) projects/07_contender_style_R/analysis.R
	$(RSCRIPT) projects/08_finals_postmortem_R/analysis.R
test:
	$(PYTHON) -m pytest tests -q
reports:
	$(PYTHON) tools/publish.py
notebooks:
	$(PYTHON) tools/notebooks.py
all: projects r test reports notebooks
