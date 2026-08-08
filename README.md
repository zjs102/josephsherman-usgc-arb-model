# USGC Crude Import/Export ARB Model — Quick Guide

A live, editable web version of the USGC Crude Import/Export ARB Model. Change any input and the export/import forecasts, tables, and charts update immediately.

**Live app:** your `*.streamlit.app` URL (find it at [share.streamlit.io](https://share.streamlit.io) if you don't have it handy).

**Run it locally:**
```bash
python -m streamlit run arb_app.py
```

---

## The three pages

- **Export drivers** — edit export-side inputs (prices, SPR level, PADD3 production, refinery runs). Shows its own export totals, delta vs. baseline, and seasonal charts. Usable on its own.
- **Import drivers** — edit import-side inputs (refinery runs forecast, PADD2/PADD3 production, seasonal indices). Same self-contained layout for imports.
- **Combined results** — both sides together, side by side, for comparing exports and imports in one view.

Editing an input on either driver page immediately updates that page's own results **and** the Combined results page — everything reads from the same live calculation.

---

## Key things to know

**1. Baseline vs. Scenario, on every chart**
Each seasonal chart shows one line per year (2021–2025), plus 2026 split into three segments:
- **Solid black** — actual 2026 data (Jan–Jul).
- **Dotted black, "2026 (baseline)"** — the live workbook's default forecast (Aug–Dec). This never moves, no matter what you edit — it's your fixed reference point.
- **Dotted red, "2026 (scenario)"** — reflects your *current* inputs. This line only appears once you've actually changed something from baseline; if your inputs match baseline, it's hidden (the two lines would just overlap).

**2. Some fields are linked between Export and Import drivers**
A few inputs are the *same physical number* in both models, just used differently:
- **PADD3 Production**: Export Drivers' Aug/Sep values are the same series as Import Drivers' Nov/Dec "PADD3 Production M-3" (a 3-month lag). Edit either cell and the other updates automatically.
- **USGC Refinery Runs**: Export Drivers' value for any month is the same as Import Drivers' "Refinery Runs Forecast" for that same month (no lag). Edit either side, both update.

You'll see a hover tooltip (ⓘ) on these columns explaining the link. Aug/Sep/Oct's "PADD3 Production M-3" on the Import side isn't linked — those reference May/Jun/Jul, which fall outside this model's editable window, so they stay independently editable.

**3. "PADD2+3 Production M-3" is a formula, not an input**
Shown as a read-only row under the Import drivers table — it's always PADD2 + PADD3, calculated live from the two editable columns above it.

**4. Advanced coefficients (collapsed by default)**
Each driver page has an "anchors & regression coefficients (advanced)" expander. These are the underlying regression constants pulled from the live workbook — you generally shouldn't need to touch these for normal scenario testing; they're there for deeper what-if analysis (e.g., testing a different fitted relationship).

**5. "Reset to baseline"**
The button at the top wipes every edit — on both driver pages and in the advanced panels — back to the live workbook's default values in one click.

**6. Delta vs. baseline tables**
Under each results table, shows exactly how far your current inputs have moved the forecast away from baseline, month by month.

**7. Downloading results**
Each page has its own CSV download button (export-only, import-only, or combined).

---

## A note on the model's math

- **Total always equals the sum of its regions**, for both exports and imports, for any inputs you enter — not just at baseline. Total, Europe, and AsiaPac (exports) — or Total, Venezuela, and Rest-of-LatAm (imports) — are independently-fit regressions that don't naturally sum to each other; a reconciliation step spreads any gap proportionally across all regions so the total line and the detailed breakdown never disagree.
- Because of that reconciliation, editing **any** input can nudge multiple regions at once, even ones whose own formula doesn't use that input directly (e.g., changing Dubai price can move Europe's published number slightly, even though Europe's regression doesn't use Dubai spread) — that's the reconciliation sharing a genuine change in the Total across every region by size, not a bug.
- Full technical detail on every formula, coefficient, and the reconciliation design is documented in the docstrings inside `crude_arb_model.py`.
