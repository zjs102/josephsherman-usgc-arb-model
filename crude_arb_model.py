"""
USGC Crude Import/Export ARB Model -- Python replica
======================================================

A faithful, editable replica of the Aug-2026 to Dec-2026 export and import
volume forecasts in "USGC Crude Import Export ARB Model.xlsx" (Export_Drivers
and Import_Drivers tabs). Every input the live Excel model treats as an
assumption or a market input is exposed here as a plain, editable field --
change one value and re-run to see how U.S. Gulf Coast crude exports and
imports respond.

WHAT'S REPLICATED
------------------
Exports (Export_Drivers, Section 3-4):
  - Total exports    = f(crude balance lag1, WTI-Dubai spread lag1, SPR level, SPR MoM drawdown)
  - Europe exports    = f(WTI-Dated Brent NWE spread contemporaneous, SPR level)
  - Asia-Pacific exp. = f(crude balance lag1, WTI-Dubai spread lag1, SPR level, SPR MoM drawdown)
  - All three are live Excel LINEST (least-squares) fits, Jan-2021 to Jul-2026 (n=67).
  - North America, Latin America, Middle East, Africa, Unclassified are NOT
    regressed in the source model -- they're forecast as a flat trailing
    12-month average level, which is reproduced here as constants you can edit.

Imports (Import_Drivers, Section 4/6/7):
  - Total imports (top-down, AUTHORITATIVE) = Refinery Runs forecast x trailing
    12-month Imports-as-%-of-Runs ratio x a month's seasonal index.
  - Venezuela and Rest-of-LatAm are built bottom-up (Venezuela: flat/steady
    anchor x its own seasonal factor; Rest-of-LatAm: regression on PADD2+PADD3
    production, lag 3mo, x its own seasonal index), then TAPERED -- the gap
    between their pre-taper sum and the top-down total is split 50/50 between
    the two so the regional detail reconciles exactly to the top-down total.
  - Middle East is a flat policy assumption (0 kbd, Strait of Hormuz).
  - North America, Europe, Africa, Asia-Pacific, Unclassified are flat
    trailing-12-month averages (not seasonally adjusted in the source model).

WHAT'S NOT INCLUDED
--------------------
Netback/ARB spread economics (Export_ARB, Import_ARB -- the $/bbl trade-idea
margins) and port-level splits are out of scope here; this script covers
crude VOLUMES only (the two numbers the user asked to be able to flex:
"US Exports and Imports of crude").

USAGE
-----
    from crude_arb_model import default_export_inputs, default_import_inputs, run_model

    exp_in = default_export_inputs()
    imp_in = default_import_inputs()

    # Amend any single input -- e.g. a higher October WTI price:
    exp_in.months["2026-10"].wti_cushing = 88.00

    # Or ease the Aug-Sep SPR release path:
    imp_in_result_before = run_model(exp_in, imp_in)
    exp_in.months["2026-08"].spr_level = 300000  # was 294750

    result = run_model(exp_in, imp_in)
    print_results(result)

Running this file directly (`python crude_arb_model.py`) prints the baseline
forecast (matches the live workbook to the cent), then a worked example of
changing one input and showing exactly which downstream months move and by
how much.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional
import copy

MONTHS = ["2026-08", "2026-09", "2026-10", "2026-11", "2026-12"]
MONTH_LABELS = {"2026-08": "Aug-2026", "2026-09": "Sep-2026", "2026-10": "Oct-2026",
                "2026-11": "Nov-2026", "2026-12": "Dec-2026"}


# ======================================================================
# EXPORT MODEL
# ======================================================================

@dataclass
class ExportMonthInput:
    """One month's editable export-model inputs. All prices in $/bbl, SPR in kbbl, production/runs in kbd."""
    wti_cushing: float
    dated_brent_nwe: float
    dubai: float
    spr_level: float                          # end-of-month SPR level, kbbl
    padd3_production: float                   # kbd
    usgc_refinery_runs: float                 # kbd
    crude_balance_override: Optional[float] = None  # kbd -- set to override PADD3 prod minus runs directly


@dataclass
class ExportModelInputs:
    months: Dict[str, ExportMonthInput]

    # --- Anchors: Jul-2026 actual values, needed only to compute Aug-2026's lagged terms ---
    # (Sep-Dec's lagged terms cascade automatically from your own Aug-Nov inputs -- see run_export_model.)
    anchor_balance_used_jul: float = 1132.43674214163
    anchor_spr_level_jul: float = 304750.0
    # NOTE on this one: in the live workbook, Aug's "Dubai spread lag 1mo" cell references Jul's own
    # lag1 column (not Jul's contemporaneous spread) -- i.e. it's a fixed historical constant, not
    # derived from Jul's WTI/Dubai quote. Reproduced here exactly as the live model computes it so the
    # baseline matches to the cent; Sep-Dec lag1 terms DO cascade from your own contemporaneous inputs.
    anchor_dubai_spread_lag1_aug: float = -1.9024

    # --- Live regression coefficients (LINEST fit, Jan-2021 to Jul-2026, n=67) ---
    total_const: float = 4921.68497656695
    total_balance_coef: float = 0.258843059688362
    total_spread_coef: float = 28.384621919571
    total_spr_level_coef: float = -0.00351369731207961
    total_spr_drawdown_coef: float = 0.00972922757771951

    europe_const: float = 2853.71980289495
    europe_spread_coef: float = 14.8349048552228
    europe_spr_level_coef: float = -0.0029767541244122

    asiapac_const: float = 1464.06167791427
    asiapac_balance_coef: float = 0.227464654597912
    asiapac_spread_coef: float = 14.2285034192767
    asiapac_spr_level_coef: float = -0.00039709808977175
    asiapac_spr_drawdown_coef: float = 0.00990417174537695

    # --- Non-regressed regions: flat trailing 12-month average (Aug-2025 to Jul-2026), kbd ---
    # Same level applies to every forecast month in the source model -- edit freely.
    north_america_flat: float = 279.101651241356
    latin_america_flat: float = 206.970254813809
    middle_east_flat: float = 1.80420218152245
    africa_flat: float = 76.0429290347478
    unclassified_flat: float = 61.2366893979942


def default_export_inputs() -> ExportModelInputs:
    """Live Aug-Dec 2026 forward-curve / production-forecast values pulled from the workbook."""
    months = {
        "2026-08": ExportMonthInput(wti_cushing=91.0962, dated_brent_nwe=88.2624, dubai=81.5568,
                                     spr_level=294750.0, padd3_production=10258.0910464672,
                                     usgc_refinery_runs=10050.6721163138),
        "2026-09": ExportMonthInput(wti_cushing=85.15, dated_brent_nwe=96.558, dubai=87.7045,
                                     spr_level=284750.0, padd3_production=10288.3790450259,
                                     usgc_refinery_runs=9199.11778920685),
        "2026-10": ExportMonthInput(wti_cushing=80.9127, dated_brent_nwe=94.545, dubai=80.2093,
                                     spr_level=284750.0, padd3_production=10326.7657002614,
                                     usgc_refinery_runs=9813.33447665122),
        "2026-11": ExportMonthInput(wti_cushing=75.3635, dated_brent_nwe=91.37, dubai=84.9975,
                                     spr_level=284750.0, padd3_production=10376.2788626443,
                                     usgc_refinery_runs=9143.76984182102),
        "2026-12": ExportMonthInput(wti_cushing=74.5632, dated_brent_nwe=87.2886, dubai=77.6582,
                                     spr_level=284750.0, padd3_production=10395.6004968016,
                                     usgc_refinery_runs=9901.26012535112),
    }
    return ExportModelInputs(months=months)


def run_export_model(inputs: ExportModelInputs) -> Dict[str, Dict[str, float]]:
    """Returns, per month: Total, Europe, AsiaPac, NA, LatAm, MidEast, Africa, Unclassified,
    SumOfRegions, plus the intermediate balance/spread/drawdown terms for transparency."""
    results = {}
    prev_balance_used = inputs.anchor_balance_used_jul
    prev_dubai_spread_contemp = None  # set after Aug using Aug's own contemp; Aug uses the fixed anchor
    prev_spr_level = inputs.anchor_spr_level_jul

    for i, m in enumerate(MONTHS):
        mi = inputs.months[m]

        balance_calc = mi.padd3_production - mi.usgc_refinery_runs
        balance_used = mi.crude_balance_override if mi.crude_balance_override is not None else balance_calc
        balance_lag1 = prev_balance_used

        dubai_spread_contemp = mi.dubai - mi.wti_cushing
        dubai_spread_lag1 = inputs.anchor_dubai_spread_lag1_aug if i == 0 else prev_dubai_spread_contemp

        brent_spread_contemp = mi.dated_brent_nwe - mi.wti_cushing

        spr_drawdown = prev_spr_level - mi.spr_level

        total = (inputs.total_const
                 + inputs.total_balance_coef * balance_lag1
                 + inputs.total_spread_coef * dubai_spread_lag1
                 + inputs.total_spr_level_coef * mi.spr_level
                 + inputs.total_spr_drawdown_coef * spr_drawdown)

        europe = (inputs.europe_const
                  + inputs.europe_spread_coef * brent_spread_contemp
                  + inputs.europe_spr_level_coef * mi.spr_level)

        asiapac = (inputs.asiapac_const
                   + inputs.asiapac_balance_coef * balance_lag1
                   + inputs.asiapac_spread_coef * dubai_spread_lag1
                   + inputs.asiapac_spr_level_coef * mi.spr_level
                   + inputs.asiapac_spr_drawdown_coef * spr_drawdown)

        na = inputs.north_america_flat
        latam = inputs.latin_america_flat
        mideast = inputs.middle_east_flat
        africa = inputs.africa_flat
        unclass = inputs.unclassified_flat
        sum_regions = total + europe + asiapac + na + latam + mideast + africa + unclass

        results[m] = {
            "Total": total, "Europe": europe, "AsiaPac": asiapac,
            "NorthAmerica": na, "LatinAmerica": latam, "MiddleEast": mideast,
            "Africa": africa, "Unclassified": unclass, "SumOfRegions": sum_regions,
            "_balance_used": balance_used, "_balance_lag1": balance_lag1,
            "_dubai_spread_contemp": dubai_spread_contemp, "_dubai_spread_lag1": dubai_spread_lag1,
            "_brent_spread_contemp": brent_spread_contemp, "_spr_drawdown": spr_drawdown,
        }

        prev_balance_used = balance_used
        prev_dubai_spread_contemp = dubai_spread_contemp
        prev_spr_level = mi.spr_level

    return results


# ======================================================================
# IMPORT MODEL
# ======================================================================

@dataclass
class ImportMonthInput:
    """One month's editable import-model inputs."""
    refinery_runs_forecast: float       # kbd -- drives the top-down total
    padd2_padd3_production_lag3: float  # kbd -- drives the Rest-of-LatAm regression
    total_seasonal_index: float         # ratio-to-13mo-centered-MA index for the top-down total
    venezuela_seasonal_factor: float    # Venezuela's own applied factor (Aug-Dec renormalized to 1.0)
    restlatam_seasonal_index: float     # Rest-of-LatAm's own 12-month-normalized index


@dataclass
class ImportModelInputs:
    months: Dict[str, ImportMonthInput]

    # --- Top-down total: Runs forecast x trailing-12mo ratio x seasonal index ---
    runs_ratio: float = 0.115427100109644   # trailing 12-month Imports-as-%-of-Runs (Aug-2025 to Jul-2026)

    # --- Venezuela: flat/steady anchor (Jul-2026 actual) x its own seasonal factor, then taper ---
    venezuela_anchor_jul: float = 641.639751063154

    # --- Rest-of-LatAm regression: Intercept + Slope x PADD2+PADD3 production (lag 3mo) ---
    restlatam_intercept: float = 3364.22474593265
    restlatam_slope: float = -0.239150697238133

    # --- Flat regions, kbd (Middle East is a policy assumption; the rest are trailing 12mo averages) ---
    middle_east_flat: float = 0.0
    north_america_flat: float = 26.2468890265621
    europe_flat: float = 20.6515651234351
    africa_flat: float = 28.321144806045
    asiapac_flat: float = 0.0
    unclassified_flat: float = 49.48324677647


def default_import_inputs() -> ImportModelInputs:
    """Live Aug-Dec 2026 refinery-runs forecast, PADD2+PADD3 lag3 production, and seasonal
    indices pulled from the workbook."""
    months = {
        "2026-08": ImportMonthInput(refinery_runs_forecast=10050.6721163138, padd2_padd3_production_lag3=11958.0,
                                     total_seasonal_index=1.00456634451037, venezuela_seasonal_factor=0.93843200807292,
                                     restlatam_seasonal_index=1.05775429966797),
        "2026-09": ImportMonthInput(refinery_runs_forecast=9199.11778920685, padd2_padd3_production_lag3=11969.297058751,
                                     total_seasonal_index=1.02944746292457, venezuela_seasonal_factor=0.967343235526544,
                                     restlatam_seasonal_index=0.960525750459174),
        "2026-10": ImportMonthInput(refinery_runs_forecast=9813.33447665122, padd2_padd3_production_lag3=11976.8513725349,
                                     total_seasonal_index=0.931656029277475, venezuela_seasonal_factor=1.00062282247969,
                                     restlatam_seasonal_index=0.894749221770264),
        "2026-11": ImportMonthInput(refinery_runs_forecast=9143.76984182102, padd2_padd3_production_lag3=11989.6582774382,
                                     total_seasonal_index=0.879799097552715, venezuela_seasonal_factor=1.02261363927956,
                                     restlatam_seasonal_index=0.988154826847248),
        "2026-12": ImportMonthInput(refinery_runs_forecast=9901.26012535112, padd2_padd3_production_lag3=12011.8093500412,
                                     total_seasonal_index=0.912040362300326, venezuela_seasonal_factor=1.07098829464129,
                                     restlatam_seasonal_index=0.949555405796262),
    }
    return ImportModelInputs(months=months)


def run_import_model(inputs: ImportModelInputs) -> Dict[str, Dict[str, float]]:
    """Returns, per month: Total (top-down, authoritative), Venezuela, RestOfLatAm (both post-taper),
    MiddleEast, NorthAmerica, Europe, Africa, AsiaPac, Unclassified, plus the pre-taper values and
    the gap that got split, for transparency."""
    results = {}

    for m in MONTHS:
        mi = inputs.months[m]

        top_down_total = mi.refinery_runs_forecast * inputs.runs_ratio * mi.total_seasonal_index

        venezuela_pretaper = inputs.venezuela_anchor_jul * mi.venezuela_seasonal_factor
        restlatam_pretaper = ((inputs.restlatam_intercept + inputs.restlatam_slope * mi.padd2_padd3_production_lag3)
                               * mi.restlatam_seasonal_index)

        mideast = inputs.middle_east_flat
        na = inputs.north_america_flat
        europe = inputs.europe_flat
        africa = inputs.africa_flat
        asiapac = inputs.asiapac_flat
        unclass = inputs.unclassified_flat
        other_sum = mideast + na + europe + africa + asiapac + unclass

        gap = top_down_total - (venezuela_pretaper + restlatam_pretaper + other_sum)
        venezuela = venezuela_pretaper + gap / 2
        restlatam = restlatam_pretaper + gap / 2

        total_check = venezuela + restlatam + other_sum  # should equal top_down_total by construction

        results[m] = {
            "Total": top_down_total, "Venezuela": venezuela, "RestOfLatAm": restlatam,
            "MiddleEast": mideast, "NorthAmerica": na, "Europe": europe, "Africa": africa,
            "AsiaPacific": asiapac, "Unclassified": unclass,
            "_venezuela_pretaper": venezuela_pretaper, "_restlatam_pretaper": restlatam_pretaper,
            "_taper_gap": gap, "_reconciliation_check": top_down_total - total_check,
        }

    return results


# ======================================================================
# COMBINED RUN + REPORTING
# ======================================================================

def run_model(export_inputs: ExportModelInputs, import_inputs: ImportModelInputs) -> Dict[str, Dict]:
    return {
        "exports": run_export_model(export_inputs),
        "imports": run_import_model(import_inputs),
    }


def print_results(result: Dict[str, Dict], title: str = "USGC Crude Export & Import Forecast") -> None:
    exp, imp = result["exports"], result["imports"]
    print(f"\n{title}")
    print("=" * len(title))

    print(f"\n{'EXPORTS (kbd)':<14}" + "".join(f"{MONTH_LABELS[m]:>12}" for m in MONTHS))
    for row in ["Total", "Europe", "AsiaPac", "NorthAmerica", "LatinAmerica", "MiddleEast", "Africa", "Unclassified", "SumOfRegions"]:
        print(f"{row:<14}" + "".join(f"{exp[m][row]:>12,.1f}" for m in MONTHS))

    print(f"\n{'IMPORTS (kbd)':<14}" + "".join(f"{MONTH_LABELS[m]:>12}" for m in MONTHS))
    for row in ["Total", "Venezuela", "RestOfLatAm", "MiddleEast", "NorthAmerica", "Europe", "Africa", "AsiaPacific", "Unclassified"]:
        print(f"{row:<14}" + "".join(f"{imp[m][row]:>12,.1f}" for m in MONTHS))

    exp_range = [exp[m]["Total"] + exp[m]["Europe"] + exp[m]["AsiaPac"] + exp[m]["NorthAmerica"]
                 + exp[m]["LatinAmerica"] + exp[m]["MiddleEast"] + exp[m]["Africa"] + exp[m]["Unclassified"]
                 for m in MONTHS]
    # NOTE: exp[m]["Total"] above is the standalone Total-model regression output, which does NOT equal
    # the sum of regions (see SumOfRegions row) -- both are shown because the live workbook shows both.
    imp_range = [imp[m]["Total"] for m in MONTHS]
    print(f"\nTotal exports (model), Aug-Dec range: {min(exp[m]['Total'] for m in MONTHS):,.0f} - "
          f"{max(exp[m]['Total'] for m in MONTHS):,.0f} kbd")
    print(f"Total imports (top-down), Aug-Dec range: {min(imp_range):,.0f} - {max(imp_range):,.0f} kbd")


# ======================================================================
# SELF-TEST: confirms the baseline (unmodified) run matches the live workbook
# ======================================================================

def _self_test():
    live_total_exports = [4222.43945610835, 3801.36863090811, 4275.615899902, 4034.09203275285, 4513.64352056882]
    live_europe = [1934.28237134572, 2175.32566055695, 2208.32293942643, 2243.5439705337, 2194.86916421322]
    live_asiapac = [1676.57976090821, 1361.47880409209, 1635.10314415806, 1457.76712348492, 1768.41763750344]
    live_imports_total = [1165.41744384255, 1093.09561561852, 1055.30983450713, 928.574136236755, 1042.34698326816]
    live_venezuela = [554.627197439652, 553.563097082926, 562.65717804753, 484.508492834111, 569.019401394041]
    live_restlatam = [486.087400670386, 414.829672803086, 367.949810727084, 319.362797670132, 348.624736141609]

    result = run_model(default_export_inputs(), default_import_inputs())
    exp, imp = result["exports"], result["imports"]

    checks = [
        ("Total exports", [exp[m]["Total"] for m in MONTHS], live_total_exports),
        ("Europe exports", [exp[m]["Europe"] for m in MONTHS], live_europe),
        ("Asia-Pacific exports", [exp[m]["AsiaPac"] for m in MONTHS], live_asiapac),
        ("Total imports", [imp[m]["Total"] for m in MONTHS], live_imports_total),
        ("Venezuela imports", [imp[m]["Venezuela"] for m in MONTHS], live_venezuela),
        ("Rest-of-LatAm imports", [imp[m]["RestOfLatAm"] for m in MONTHS], live_restlatam),
    ]
    all_ok = True
    for name, computed, live in checks:
        max_diff = max(abs(c - l) for c, l in zip(computed, live))
        status = "OK" if max_diff < 0.01 else "MISMATCH"
        if max_diff >= 0.01:
            all_ok = False
        print(f"  [{status}] {name}: max diff vs. live workbook = {max_diff:.6f} kbd")
    print("\nSelf-test:", "ALL PASSED -- matches the live workbook to the cent." if all_ok else "FAILED -- see mismatches above.")
    return all_ok


# ======================================================================
# DEMO
# ======================================================================

if __name__ == "__main__":
    print("Validating against the live workbook (unmodified defaults)...")
    _self_test()

    baseline = run_model(default_export_inputs(), default_import_inputs())
    print_results(baseline, title="BASELINE (live workbook defaults)")

    # ---- Worked example: amend individual inputs, see the outputs respond ----
    print("\n\nWORKED EXAMPLE: tighten the SPR release path (no Sep drawdown) and bump the")
    print("October WTI price by $5/bbl -- both are single-field edits.")

    exp_in = default_export_inputs()
    imp_in = default_import_inputs()

    # 1) Suppose September's SPR level doesn't fall as far (less release than currently forecast).
    #    This changes: Sep's own SPR-level term, Sep's SPR drawdown (level_Aug - level_Sep), AND
    #    October's SPR drawdown (level_Sep - level_Oct) -- a genuinely downstream effect.
    exp_in.months["2026-09"].spr_level = 294750.0  # was 284750.0 -- no release in September

    # 2) Suppose WTI Cushing prints $5/bbl higher in October than the current forward curve.
    #    This changes October's Dubai spread and Brent spread directly, AND (via the lag1 chain)
    #    November's Dubai-spread-lag1 term.
    exp_in.months["2026-10"].wti_cushing += 5.0

    amended = run_model(exp_in, imp_in)
    print_results(amended, title="AMENDED (Sep SPR held flat, Oct WTI +$5/bbl)")

    print("\nDelta vs. baseline (Total exports, kbd):")
    for m in MONTHS:
        b = baseline["exports"][m]["Total"]
        a = amended["exports"][m]["Total"]
        print(f"  {MONTH_LABELS[m]}: {a - b:+.1f}  (baseline {b:,.1f} -> amended {a:,.1f})")
