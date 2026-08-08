"""
USGC Crude Import/Export ARB Model -- interactive web app
===========================================================

A Streamlit front-end over crude_arb_model.py. Every input the underlying
model exposes is editable here, pre-filled with the live workbook's current
values as the default. Change any cell or number and the output tables/chart
below update immediately.

Run with:
    streamlit run arb_app.py
"""

from dataclasses import fields
import sys
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crude_arb_model import (
    MONTHS, MONTH_LABELS, EXPORT_TO_IMPORT_PADD3_LAG3_LINKS, EXPORT_TO_IMPORT_REFINERY_RUNS_LINKS,
    HISTORICAL_MONTHS, HISTORICAL_EXPORTS_TOTAL, HISTORICAL_IMPORTS_TOTAL,
    HISTORICAL_EXPORTS_EUROPE, HISTORICAL_EXPORTS_ASIAPAC,
    HISTORICAL_IMPORTS_VENEZUELA, HISTORICAL_IMPORTS_RESTOFLATAM,
    ExportMonthInput, ExportModelInputs,
    ImportMonthInput, ImportModelInputs,
    default_export_inputs, default_import_inputs, run_model,
)

st.set_page_config(page_title="USGC Crude ARB Model", layout="wide")

if "reset_id" not in st.session_state:
    st.session_state.reset_id = 0


def _reset():
    st.session_state.reset_id += 1


st.title("USGC Crude Import/Export ARB Model")
st.caption(
    "Editable replica of the Export_Drivers / Import_Drivers tabs. "
    "Defaults below are the live workbook's current Aug-Dec 2026 forecast -- "
    "edit any value to see exports and imports respond."
)
st.button("Reset to baseline", on_click=_reset)
rid = st.session_state.reset_id

baseline = run_model(default_export_inputs(), default_import_inputs())

exp_defaults = default_export_inputs()
imp_defaults = default_import_inputs()

# ---- Two-way PADD3 Production sync setup (must exist before either table is built below).
# Export Drivers' Aug/Sep PADD3 Production IS Import Drivers' Nov/Dec PADD3 Production M-3 --
# same physical series, 3-month lag. padd3_sync holds the current canonical value for each linked
# pair (keyed by import month); both tables are SEEDED from it, so editing either side and forcing
# a rerun redraws both consistently -- st.data_editor does not repaint an existing cell just
# because its backing session state changed, so the value must be fed back through the seed data.
EXPORT_TO_IMPORT_PADD3_LINK_REVERSE = {exp_m: imp_m for imp_m, exp_m in EXPORT_TO_IMPORT_PADD3_LAG3_LINKS.items()}
PADD3_EXPORT_COL = "PADD3 Production (kbd)"
PADD2_M3_COL = "PADD2 Production M-3 (kbd)"
PADD3_M3_COL = "PADD3 Production M-3 (kbd)"

padd3_sync_key = f"padd3_sync_{rid}"
if padd3_sync_key not in st.session_state:
    st.session_state[padd3_sync_key] = {
        imp_m: float(exp_defaults.months[exp_m].padd3_production)
        for imp_m, exp_m in EXPORT_TO_IMPORT_PADD3_LAG3_LINKS.items()
    }
padd3_sync = st.session_state[padd3_sync_key]

# ---- Two-way USGC Refinery Runs sync setup. Unlike PADD3 Production, Refinery Runs has NO lag --
# Export's month M "USGC Refinery Runs" IS Import's month M "Refinery Runs Forecast", for all five
# months -- so this links keyed by month directly, no reverse-mapping needed.
RUNS_EXPORT_COL = "USGC Refinery Runs (kbd)"
RUNS_IMPORT_COL = "Refinery Runs Forecast (kbd)"

runs_sync_key = f"runs_sync_{rid}"
if runs_sync_key not in st.session_state:
    st.session_state[runs_sync_key] = {m: float(exp_defaults.months[m].usgc_refinery_runs) for m in MONTHS}
runs_sync = st.session_state[runs_sync_key]

exp_editor_key = f"exp_editor_{rid}"
imp_editor_key = f"imp_editor_{rid}"
exp_row_pos = {MONTH_LABELS[m]: i for i, m in enumerate(MONTHS)}
imp_row_pos = {MONTH_LABELS[m]: i for i, m in enumerate(MONTHS)}

tab_export, tab_import, tab_results, tab_howto = st.tabs(
    ["Export drivers", "Import drivers", "Combined results", "How To"]
)

with tab_howto:
    readme_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "README.md")
    with open(readme_path, "r", encoding="utf-8") as f:
        st.markdown(f.read())

# ======================================================================
# EXPORT INPUTS
# ======================================================================
with tab_export:
    exp_df_default = pd.DataFrame(
        [
            {
                "Month": MONTH_LABELS[m],
                "WTI Cushing ($/bbl)": d.wti_cushing,
                "Dated Brent NWE ($/bbl)": d.dated_brent_nwe,
                "Dubai ($/bbl)": d.dubai,
                "SPR Level (kbbl)": d.spr_level,
                PADD3_EXPORT_COL: (
                    padd3_sync[EXPORT_TO_IMPORT_PADD3_LINK_REVERSE[m]]
                    if m in EXPORT_TO_IMPORT_PADD3_LINK_REVERSE else d.padd3_production
                ),
                RUNS_EXPORT_COL: runs_sync[m],
            }
            for m, d in ((m, exp_defaults.months[m]) for m in MONTHS)
        ]
    ).set_index("Month")

    exp_edited = st.data_editor(
        exp_df_default,
        key=exp_editor_key,
        width='stretch',
        column_config={
            "WTI Cushing ($/bbl)": st.column_config.NumberColumn(format="%.2f"),
            "Dated Brent NWE ($/bbl)": st.column_config.NumberColumn(format="%.2f"),
            "Dubai ($/bbl)": st.column_config.NumberColumn(format="%.2f"),
            PADD3_EXPORT_COL: st.column_config.NumberColumn(
                format="%.0f",
                help="Aug-2026 and Sep-2026 here are linked live to Import Drivers' Nov-2026 and "
                     "Dec-2026 PADD3 Production M-3 (same series, 3-month lag) -- edit either one and "
                     "both update.",
            ),
            RUNS_EXPORT_COL: st.column_config.NumberColumn(
                format="%.0f",
                help="Linked live to Import Drivers' Refinery Runs Forecast for the same month (same "
                     "series, no lag) -- edit either one and both update.",
            ),
        },
    )
    st.caption(
        "Crude balance (used by the Total and Asia-Pacific regressions) is always "
        "PADD3 Production minus USGC Refinery Runs — it isn't a separate input."
    )

    with st.expander("Export model -- anchors & regression coefficients (advanced)"):
        exp_scalar_fields = [f for f in fields(ExportModelInputs) if f.name != "months"]
        exp_scalars = {}
        cols = st.columns(3)
        for i, f in enumerate(exp_scalar_fields):
            with cols[i % 3]:
                exp_scalars[f.name] = st.number_input(
                    f.name, value=float(getattr(exp_defaults, f.name)),
                    key=f"exp_scalar_{f.name}_{rid}", format="%.6f",
                )

# ======================================================================
# IMPORT INPUTS
# ======================================================================
with tab_import:
    imp_df_default = pd.DataFrame(
        [
            {
                "Month": MONTH_LABELS[m],
                RUNS_IMPORT_COL: runs_sync[m],
                PADD2_M3_COL: d.padd2_production_lag3,
                PADD3_M3_COL: padd3_sync[m] if m in padd3_sync else d.padd3_production_lag3,
                "Total Seasonal Index": d.total_seasonal_index,
                "Venezuela Seasonal Factor": d.venezuela_seasonal_factor,
                "Rest-of-LatAm Seasonal Index": d.restlatam_seasonal_index,
            }
            for m, d in ((m, imp_defaults.months[m]) for m in MONTHS)
        ]
    ).set_index("Month")

    imp_edited = st.data_editor(
        imp_df_default,
        key=imp_editor_key,
        width='stretch',
        column_config={
            RUNS_IMPORT_COL: st.column_config.NumberColumn(
                format="%.0f",
                help="Linked live to Export Drivers' USGC Refinery Runs for the same month (same "
                     "series, no lag) -- edit either one and both update.",
            ),
            PADD2_M3_COL: st.column_config.NumberColumn(
                format="%.0f",
                help="Production from the month 3 months prior to this row -- e.g. the Aug-2026 row "
                     "shows May-2026's PADD2 production, not Aug-2026's.",
            ),
            PADD3_M3_COL: st.column_config.NumberColumn(
                format="%.0f",
                help="Production from the month 3 months prior to this row -- e.g. the Aug-2026 row "
                     "shows May-2026's PADD3 production, not Aug-2026's. For Nov-2026 and Dec-2026, "
                     "this is the same series as Export Drivers' Aug-2026 and Sep-2026 PADD3 "
                     "Production -- edit either one and both update together.",
            ),
        },
    )

    # ---- Two-way sync: detect which side changed since the last run, update the shared canonical
    # value, and CLEAR (not set) any stale edited_rows override on the other table's cell so its
    # next render picks up the new seed value -- data_editor won't repaint a cell just because
    # session state changed, only when the seed data it re-reads on rerun actually differs.
    def sync_linked_column(links, sync_dict, exp_col, imp_col):
        needs_rerun = False
        for imp_m, exp_m in links.items():
            imp_label, exp_label = MONTH_LABELS[imp_m], MONTH_LABELS[exp_m]
            exp_val = float(exp_edited.loc[exp_label, exp_col])
            imp_val = float(imp_edited.loc[imp_label, imp_col])
            last = sync_dict[imp_m]

            if abs(exp_val - last) > 1e-9 and abs(exp_val - imp_val) > 1e-9:
                sync_dict[imp_m] = exp_val
                st.session_state[imp_editor_key].get("edited_rows", {}).get(imp_row_pos[imp_label], {}).pop(imp_col, None)
                needs_rerun = True
            elif abs(imp_val - last) > 1e-9 and abs(imp_val - exp_val) > 1e-9:
                sync_dict[imp_m] = imp_val
                st.session_state[exp_editor_key].get("edited_rows", {}).get(exp_row_pos[exp_label], {}).pop(exp_col, None)
                needs_rerun = True
        return needs_rerun


    needs_rerun = sync_linked_column(EXPORT_TO_IMPORT_PADD3_LAG3_LINKS, padd3_sync, PADD3_EXPORT_COL, PADD3_M3_COL)
    needs_rerun = sync_linked_column(EXPORT_TO_IMPORT_REFINERY_RUNS_LINKS, runs_sync, RUNS_EXPORT_COL, RUNS_IMPORT_COL) or needs_rerun

    if needs_rerun:
        st.rerun()

    linked_months = {MONTH_LABELS[imp_m]: MONTH_LABELS[exp_m] for imp_m, exp_m in EXPORT_TO_IMPORT_PADD3_LAG3_LINKS.items()}
    combined_padd_df = pd.DataFrame({
        "PADD2+3 Production M-3 (kbd, = PADD2 + PADD3)": imp_edited[PADD2_M3_COL] + imp_edited[PADD3_M3_COL],
    })
    st.dataframe(combined_padd_df.T.style.format("{:,.0f}"), width='stretch')
    st.caption(
        "PADD2+3 Production M-3 is a formula (PADD2 + PADD3 above), not an independent input. "
        + ", ".join(f"{imp_m} here <-> {exp_m} in Export Drivers" for imp_m, exp_m in linked_months.items())
        + " are the same PADD3 production series, 3 months apart -- edit either one and both update. "
        "Refinery Runs Forecast here is also linked to Export Drivers' USGC Refinery Runs, month for "
        "month with no lag, for all five months -- edit either one and both update."
    )

    with st.expander("Import model -- anchors & regression coefficients (advanced)"):
        imp_scalar_fields = [f for f in fields(ImportModelInputs) if f.name != "months"]
        imp_scalars = {}
        cols = st.columns(3)
        for i, f in enumerate(imp_scalar_fields):
            with cols[i % 3]:
                imp_scalars[f.name] = st.number_input(
                    f.name, value=float(getattr(imp_defaults, f.name)),
                    key=f"imp_scalar_{f.name}_{rid}", format="%.6f",
                )

# ======================================================================
# BUILD INPUTS FROM EDITED TABLES AND RUN
# ======================================================================


def build_export_inputs() -> ExportModelInputs:
    months = {}
    for m in MONTHS:
        row = exp_edited.loc[MONTH_LABELS[m]]
        months[m] = ExportMonthInput(
            wti_cushing=float(row["WTI Cushing ($/bbl)"]),
            dated_brent_nwe=float(row["Dated Brent NWE ($/bbl)"]),
            dubai=float(row["Dubai ($/bbl)"]),
            spr_level=float(row["SPR Level (kbbl)"]),
            padd3_production=float(row["PADD3 Production (kbd)"]),
            usgc_refinery_runs=float(row["USGC Refinery Runs (kbd)"]),
        )
    return ExportModelInputs(months=months, **exp_scalars)


def build_import_inputs() -> ImportModelInputs:
    months = {}
    for m in MONTHS:
        row = imp_edited.loc[MONTH_LABELS[m]]
        months[m] = ImportMonthInput(
            refinery_runs_forecast=float(row["Refinery Runs Forecast (kbd)"]),
            padd2_production_lag3=float(row[PADD2_M3_COL]),
            padd3_production_lag3=float(row[PADD3_M3_COL]),
            total_seasonal_index=float(row["Total Seasonal Index"]),
            venezuela_seasonal_factor=float(row["Venezuela Seasonal Factor"]),
            restlatam_seasonal_index=float(row["Rest-of-LatAm Seasonal Index"]),
        )
    return ImportModelInputs(months=months, **imp_scalars)


result = run_model(build_export_inputs(), build_import_inputs())

# ======================================================================
# SHARED RESULT/CHART HELPERS -- used by the export page, import page, AND combined results
# ======================================================================
EXP_ROWS = ["Total", "Europe", "AsiaPac", "NorthAmerica", "LatinAmerica",
            "MiddleEast", "Africa", "Unclassified"]
IMP_ROWS = ["Total", "Venezuela", "RestOfLatAm", "MiddleEast", "NorthAmerica",
            "Europe", "Africa", "AsiaPacific", "Unclassified"]

MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def result_table(section, rows):
    data = {MONTH_LABELS[m]: {r: section[m][r] for r in rows} for m in MONTHS}
    return pd.DataFrame(data).loc[rows]


def by_year(hist_values):
    years = {}
    for ym, v in zip(HISTORICAL_MONTHS, hist_values):
        y, m = ym.split("-")
        years.setdefault(int(y), {})[int(m)] = v
    return years


def seasonal_by_year_chart(hist_values, result_section, baseline_section, field, title):
    """Baseline (dotted black) always reflects the live workbook's default inputs, unaffected by
    anything edited above. Scenario (dotted red) reflects the current inputs -- the two overlap
    exactly when nothing has been changed from baseline, and diverge to show the effect of edits."""
    years = by_year(hist_values)
    scenario_by_month = {int(m.split("-")[1]): result_section[m][field] for m in MONTHS}
    baseline_by_month = {int(m.split("-")[1]): baseline_section[m][field] for m in MONTHS}

    fig = go.Figure()
    for year in range(2021, 2026):
        fig.add_trace(go.Scatter(
            x=MONTH_ABBR, y=[years[year][m] for m in range(1, 13)],
            name=str(year), mode="lines+markers",
        ))

    actual_2026 = [years[2026][m] for m in range(1, 8)]
    baseline_2026 = [baseline_by_month[m] for m in range(8, 13)]
    scenario_2026 = [scenario_by_month[m] for m in range(8, 13)]

    fig.add_trace(go.Scatter(
        x=MONTH_ABBR[:7], y=actual_2026,
        name="2026", mode="lines+markers", legendgroup="2026", line=dict(color="black"),
    ))
    fig.add_trace(go.Scatter(
        x=MONTH_ABBR[6:12], y=[actual_2026[-1]] + baseline_2026,
        name="2026 (baseline)", mode="lines+markers", legendgroup="2026",
        line=dict(color="black", dash="dot"),
    ))
    if any(abs(s - b) > 1e-6 for s, b in zip(scenario_2026, baseline_2026)):
        fig.add_trace(go.Scatter(
            x=MONTH_ABBR[6:12], y=[actual_2026[-1]] + scenario_2026,
            name="2026 (scenario)", mode="lines+markers", legendgroup="2026",
            line=dict(color="crimson", dash="dot"),
        ))

    fig.update_layout(title=title, xaxis_title="Month", yaxis_title="kbd", height=420)
    return fig


exp_table = result_table(result["exports"], EXP_ROWS)
imp_table = result_table(result["imports"], IMP_ROWS)
delta_exp = exp_table - result_table(baseline["exports"], EXP_ROWS)
delta_imp = imp_table - result_table(baseline["imports"], IMP_ROWS)

SEASONAL_CAPTION = ("Each line is one year, Jan-Dec. 2026 turns dotted from Aug onward -- black is "
                    "the live workbook's baseline forecast (fixed, unaffected by your edits), red is "
                    "the scenario forecast driven by your current inputs above. They overlap exactly "
                    "when nothing has changed from baseline.")

# ======================================================================
# EXPORT PAGE -- its own totals, delta, and seasonal charts (usable standalone)
# ======================================================================
with tab_export:
    st.header("Export totals (kbd)")
    st.dataframe(exp_table.style.format("{:,.1f}"), width='stretch')

    st.subheader("Delta vs. baseline (current inputs minus live workbook defaults)")
    st.dataframe(delta_exp.style.format("{:+,.1f}"), width='stretch')

    st.header("Seasonal trend: actuals vs. forecast")
    st.caption(SEASONAL_CAPTION)
    st.plotly_chart(
        seasonal_by_year_chart(HISTORICAL_EXPORTS_TOTAL, result["exports"], baseline["exports"], "Total",
                                "Total exports (kbd)"),
        width='stretch', key="chart_exp_page_total",
    )
    col_exp1, col_exp2 = st.columns(2)
    with col_exp1:
        st.plotly_chart(
            seasonal_by_year_chart(HISTORICAL_EXPORTS_EUROPE, result["exports"], baseline["exports"], "Europe",
                                    "Europe exports (kbd)"),
            width='stretch', key="chart_exp_page_europe",
        )
    with col_exp2:
        st.plotly_chart(
            seasonal_by_year_chart(HISTORICAL_EXPORTS_ASIAPAC, result["exports"], baseline["exports"], "AsiaPac",
                                    "Asia-Pacific exports (kbd)"),
            width='stretch', key="chart_exp_page_asiapac",
        )

    st.download_button(
        "Download export results as CSV", exp_table.to_csv().encode("utf-8"),
        "arb_model_exports.csv", "text/csv", key="dl_exp",
    )

# ======================================================================
# IMPORT PAGE -- its own totals, delta, and seasonal charts (usable standalone)
# ======================================================================
with tab_import:
    st.header("Import totals (kbd)")
    st.dataframe(imp_table.style.format("{:,.1f}"), width='stretch')

    st.subheader("Delta vs. baseline (current inputs minus live workbook defaults)")
    st.dataframe(delta_imp.style.format("{:+,.1f}"), width='stretch')

    st.header("Seasonal trend: actuals vs. forecast")
    st.caption(SEASONAL_CAPTION)
    st.plotly_chart(
        seasonal_by_year_chart(HISTORICAL_IMPORTS_TOTAL, result["imports"], baseline["imports"], "Total",
                                "Total imports (kbd)"),
        width='stretch', key="chart_imp_page_total",
    )
    col_imp1, col_imp2 = st.columns(2)
    with col_imp1:
        st.plotly_chart(
            seasonal_by_year_chart(HISTORICAL_IMPORTS_VENEZUELA, result["imports"], baseline["imports"], "Venezuela",
                                    "Venezuela imports (kbd)"),
            width='stretch', key="chart_imp_page_venezuela",
        )
    with col_imp2:
        st.plotly_chart(
            seasonal_by_year_chart(HISTORICAL_IMPORTS_RESTOFLATAM, result["imports"], baseline["imports"], "RestOfLatAm",
                                    "Rest-of-LatAm imports (kbd)"),
            width='stretch', key="chart_imp_page_restlatam",
        )

    st.download_button(
        "Download import results as CSV", imp_table.to_csv().encode("utf-8"),
        "arb_model_imports.csv", "text/csv", key="dl_imp",
    )

# ======================================================================
# COMBINED RESULTS -- exports and imports together, side by side
# ======================================================================
with tab_results:
    st.header("Exports and imports (kbd)")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Exports")
        st.dataframe(exp_table.style.format("{:,.1f}"), width='stretch')
    with col2:
        st.subheader("Imports")
        st.dataframe(imp_table.style.format("{:,.1f}"), width='stretch')

    st.subheader("Delta vs. baseline (current inputs minus live workbook defaults)")
    col3, col4 = st.columns(2)
    with col3:
        st.dataframe(delta_exp.style.format("{:+,.1f}"), width='stretch')
    with col4:
        st.dataframe(delta_imp.style.format("{:+,.1f}"), width='stretch')

    st.header("Seasonal trend: actuals vs. forecast")
    st.caption(SEASONAL_CAPTION)

    st.subheader("Exports")
    col_e1, col_e2 = st.columns(2)
    with col_e1:
        st.plotly_chart(
            seasonal_by_year_chart(HISTORICAL_EXPORTS_TOTAL, result["exports"], baseline["exports"], "Total",
                                    "Total exports (kbd)"),
            width='stretch', key="chart_combined_exp_total",
        )
        st.plotly_chart(
            seasonal_by_year_chart(HISTORICAL_EXPORTS_EUROPE, result["exports"], baseline["exports"], "Europe",
                                    "Europe exports (kbd)"),
            width='stretch', key="chart_combined_exp_europe",
        )
    with col_e2:
        st.plotly_chart(
            seasonal_by_year_chart(HISTORICAL_EXPORTS_ASIAPAC, result["exports"], baseline["exports"], "AsiaPac",
                                    "Asia-Pacific exports (kbd)"),
            width='stretch', key="chart_combined_exp_asiapac",
        )

    st.subheader("Imports")
    col_i1, col_i2 = st.columns(2)
    with col_i1:
        st.plotly_chart(
            seasonal_by_year_chart(HISTORICAL_IMPORTS_TOTAL, result["imports"], baseline["imports"], "Total",
                                    "Total imports (kbd)"),
            width='stretch', key="chart_combined_imp_total",
        )
        st.plotly_chart(
            seasonal_by_year_chart(HISTORICAL_IMPORTS_VENEZUELA, result["imports"], baseline["imports"], "Venezuela",
                                    "Venezuela imports (kbd)"),
            width='stretch', key="chart_combined_imp_venezuela",
        )
    with col_i2:
        st.plotly_chart(
            seasonal_by_year_chart(HISTORICAL_IMPORTS_RESTOFLATAM, result["imports"], baseline["imports"], "RestOfLatAm",
                                    "Rest-of-LatAm imports (kbd)"),
            width='stretch', key="chart_combined_imp_restlatam",
        )

    csv = pd.concat(
        [exp_table.add_prefix("Export_"), imp_table.add_prefix("Import_")]
    ).to_csv().encode("utf-8")
    st.download_button("Download combined results as CSV", csv, "arb_model_results.csv", "text/csv", key="dl_combined")
