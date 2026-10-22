# Visual design and reproducibility

The October 2026 AI-assisted visual pass replaces the flagship chart with a consistent editorial design: direct labels, restrained teal/orange contrast, explicit units, source references and uncertainty where available. It does not change the underlying result tables or imply new data collection.

From the repository root, after installing its declared dependencies:

```sh
python -m tools.feature_charts
```

The existing full figure pipeline also uses the new design. PNGs are 2,520 pixels wide; SVGs preserve vectors and selectable text. Titles and captions are part of each exported figure. Color is supplemented by labels, marker shape or position. Intervals retain their original meaning; the shot map uses unsmoothed five-foot cells and a symmetric frequency scale.

The style helper is deliberately vendored here so that this repository runs independently of the rest of the portfolio. It has no model-fitting logic. No plotting assets imitate another person's authorship, and no endorsement is implied. Data sources retain their existing rights and terms.

Figures are regenerated from committed tables. This checks the presentation layer, not the original data provider or every earlier processing step. See the root validation notes for remaining rebuild limitations.
