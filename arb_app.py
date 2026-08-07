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
    MONTHS, MONTH_LABELS,
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
st.button("Reset all inputs to defaults", on_click=_reset)
rid = st.session_state.reset_id

baseline = run_model(default_export_inputs(), default_import_inputs())

# ======================================================================
# EXPORT INPUTS
# ======================================================================
st.header("Export drivers")

exp_defaults = default_export_inputs()
exp_df_default = pd.DataFrame(
    [
        {
            "Month": MONTH_LABELS[m],
            "WTI Cushing ($/bbl)": d.wti_cushing,
            "Dated Brent NWE ($/bbl)": d.dated_brent_nwe,
            "Dubai ($/bbl)": d.dubai,
            "SPR Level (kbbl)": d.spr_level,
            "PADD3 Production (kbd)": d.padd3_production,
            "USGC Refinery Runs (kbd)": d.usgc_refinery_runs,
            "Crude Balance Override (kbd)": d.crude_balance_override,
        }
        for m, d in ((m, exp_defaults.months[m]) for m in MONTHS)
    ]
).set_index("Month")

exp_edited = st.data_editor(exp_df_default, key=f"exp_editor_{rid}", width='stretch')

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
st.header("Import drivers")

imp_defaults = default_import_inputs()
imp_df_default = pd.DataFrame(
    [
        {
            "Month": MONTH_LABELS[m],
            "Refinery Runs Forecast (kbd)": d.refinery_runs_forecast,
            "PADD2+3 Production Lag3 (kbd)": d.padd2_padd3_production_lag3,
            "Total Seasonal Index": d.total_seasonal_index,
            "Venezuela Seasonal Factor": d.venezuela_seasonal_factor,
            "Rest-of-LatAm Seasonal Index": d.restlatam_seasonal_index,
        }
        for m, d in ((m, imp_defaults.months[m]) for m in MONTHS)
    ]
).set_index("Month")

imp_edited = st.data_editor(imp_df_default, key=f"imp_editor_{rid}", width='stretch')

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
        override = row["Crude Balance Override (kbd)"]
        override = None if pd.isna(override) else float(override)
        months[m] = ExportMonthInput(
            wti_cushing=float(row["WTI Cushing ($/bbl)"]),
            dated_brent_nwe=float(row["Dated Brent NWE ($/bbl)"]),
            dubai=float(row["Dubai ($/bbl)"]),
            spr_level=float(row["SPR Level (kbbl)"]),
            padd3_production=float(row["PADD3 Production (kbd)"]),
            usgc_refinery_runs=float(row["USGC Refinery Runs (kbd)"]),
            crude_balance_override=override,
        )
    return ExportModelInputs(months=months, **exp_scalars)


def build_import_inputs() -> ImportModelInputs:
    months = {}
    for m in MONTHS:
        row = imp_edited.loc[MONTH_LABELS[m]]
        months[m] = ImportMonthInput(
            refinery_runs_forecast=float(row["Refinery Runs Forecast (kbd)"]),
            padd2_padd3_production_lag3=float(row["PADD2+3 Production Lag3 (kbd)"]),
            total_seasonal_index=float(row["Total Seasonal Index"]),
            venezuela_seasonal_factor=float(row["Venezuela Seasonal Factor"]),
            restlatam_seasonal_index=float(row["Rest-of-LatAm Seasonal Index"]),
        )
    return ImportModelInputs(months=months, **imp_scalars)


result = run_model(build_export_inputs(), build_import_inputs())

# ======================================================================
# RESULTS
# ======================================================================
st.header("Results")

EXP_ROWS = ["Total", "Europe", "AsiaPac", "NorthAmerica", "LatinAmerica",
            "MiddleEast", "Africa", "Unclassified", "SumOfRegions"]
IMP_ROWS = ["Total", "Venezuela", "RestOfLatAm", "MiddleEast", "NorthAmerica",
            "Europe", "Africa", "AsiaPacific", "Unclassified"]


def result_table(section, rows):
    data = {MONTH_LABELS[m]: {r: section[m][r] for r in rows} for m in MONTHS}
    return pd.DataFrame(data).loc[rows]


exp_table = result_table(result["exports"], EXP_ROWS)
imp_table = result_table(result["imports"], IMP_ROWS)

col1, col2 = st.columns(2)
with col1:
    st.subheader("Exports (kbd)")
    st.dataframe(exp_table.style.format("{:,.1f}"), width='stretch')
with col2:
    st.subheader("Imports (kbd)")
    st.dataframe(imp_table.style.format("{:,.1f}"), width='stretch')

fig = go.Figure()
fig.add_trace(go.Scatter(
    x=[MONTH_LABELS[m] for m in MONTHS],
    y=[result["exports"][m]["Total"] for m in MONTHS],
    name="Total Exports", mode="lines+markers",
))
fig.add_trace(go.Scatter(
    x=[MONTH_LABELS[m] for m in MONTHS],
    y=[result["imports"][m]["Total"] for m in MONTHS],
    name="Total Imports", mode="lines+markers",
))
fig.update_layout(title="Total Exports vs. Imports (kbd)", yaxis_title="kbd", height=420)
st.plotly_chart(fig, width='stretch')

st.subheader("Delta vs. baseline (current inputs minus live workbook defaults)")
delta_exp = exp_table - result_table(baseline["exports"], EXP_ROWS)
delta_imp = imp_table - result_table(baseline["imports"], IMP_ROWS)
col3, col4 = st.columns(2)
with col3:
    st.dataframe(delta_exp.style.format("{:+,.1f}"), width='stretch')
with col4:
    st.dataframe(delta_imp.style.format("{:+,.1f}"), width='stretch')

csv = pd.concat(
    [exp_table.add_prefix("Export_"), imp_table.add_prefix("Import_")]
).to_csv().encode("utf-8")
st.download_button("Download results as CSV", csv, "arb_model_results.csv", "text/csv")
