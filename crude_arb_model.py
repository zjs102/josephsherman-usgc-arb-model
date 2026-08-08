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
  - Total imports = Refinery Runs forecast x trailing 12-month Imports-as-%-of-Runs
    ratio x a month's seasonal index, PLUS whatever your edits move Venezuela and
    Rest-of-LatAm away from their default-input values (see RECONCILIATION below).
  - Venezuela and Rest-of-LatAm are built bottom-up (Venezuela: flat/steady
    anchor x its own seasonal factor; Rest-of-LatAm: regression on PADD2+PADD3
    production, lag 3mo, x its own seasonal index).
  - RECONCILIATION: the live workbook's top-down total and the two bottom-up
    regressions never agree exactly on their own -- there's a persistent historical
    gap. That gap is FROZEN at its default-inputs value and split PROPORTIONALLY
    by each region's current size (see run_import_model docstring for why: this
    replaces the live workbook's original 50/50-of-the-live-gap split, which had
    the side effect of forcing Venezuela to silently move opposite Rest-of-LatAm
    any time you changed a Rest-of-LatAm driver like production, netting to zero
    change in Total). Under this design your edits show up as real changes in
    Total, and a driver moving one region only echoes a small proportional amount
    in the other -- both move the same direction instead of offsetting.
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

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Dict, Optional
import copy

MONTHS = ["2026-08", "2026-09", "2026-10", "2026-11", "2026-12"]
MONTH_LABELS = {"2026-08": "Aug-2026", "2026-09": "Sep-2026", "2026-10": "Oct-2026",
                "2026-11": "Nov-2026", "2026-12": "Dec-2026"}


def _shift_month(ym: str, delta_months: int) -> str:
    dt = datetime.strptime(ym, "%Y-%m")
    total = dt.year * 12 + (dt.month - 1) + delta_months
    y, m = divmod(total, 12)
    return f"{y:04d}-{m + 1:02d}"


# Import Drivers' PADD2/PADD3 Production columns are lagged 3 months -- e.g. the "Aug-2026" row's
# production figure is actually May-2026's production. This maps each import month to the calendar
# month its production figure actually comes from, and to a display label, so that relationship is
# explicit in the UI instead of implied by a generic "Lag3" column name.
IMPORT_PADD_SOURCE_MONTH = {m: _shift_month(m, -3) for m in MONTHS}
IMPORT_PADD_SOURCE_MONTH_LABEL = {
    m: datetime.strptime(src, "%Y-%m").strftime("%b-%Y") for m, src in IMPORT_PADD_SOURCE_MONTH.items()
}

# ======================================================================
# HISTORICAL ACTUALS (Jan-2021 to Jul-2026) -- for charting only, not model inputs.
# Pulled directly from Export_Drivers / Import_Drivers "Total" columns (the same
# n=67 window the live regressions are fit on). Aug-Dec 2026 in the charts is the
# model's own forecast output, not stored here.
# ======================================================================

HISTORICAL_MONTHS = [f"{y}-{m:02d}" for y in range(2021, 2026) for m in range(1, 13)] \
    + [f"2026-{m:02d}" for m in range(1, 8)]
HISTORICAL_MONTH_LABELS = {ym: datetime.strptime(ym, "%Y-%m").strftime("%b-%Y") for ym in HISTORICAL_MONTHS}

HISTORICAL_EXPORTS_TOTAL = [
    3100.69806955366, 2121.12000455382, 2668.79569585422, 3019.0046165113, 2617.54516890505,
    3059.93355234454, 2477.5172648706, 2567.88619533275, 2544.70728282489, 2633.40745232582,
    3160.50608864146, 3246.59279845501, 3182.95303481636, 3100.56114320362, 3070.17668666292,
    3142.36188886366, 3185.30083037876, 3253.77654064193, 3321.0695181719, 3363.24599106242,
    3726.37800000377, 3755.44934274827, 3794.35858084262, 3588.82574978651, 3353.53615280652,
    3880.46380568942, 4463.60150941657, 3962.32260480344, 3827.16353911247, 3796.13384842689,
    3822.62329616387, 4050.72015997707, 4292.36135842297, 4134.97247893385, 4211.21355605133,
    4388.09496915994, 3779.8030489877, 4361.06047681059, 4310.92899832555, 3761.39922496954,
    4189.96443071543, 3909.69202781187, 4202.49565886405, 3739.93079138823, 3544.14445262819,
    3647.67832642668, 4098.33433865472, 3717.48954871888, 3881.19253915656, 3928.87776256343,
    3883.70729794344, 3674.53894954712, 3535.94382655397, 3629.80855703569, 3098.51141082216,
    3898.53024576136, 4305.12942228719, 4292.41544004032, 3596.09937607176, 3724.37952895528,
    3912.7485553066, 3847.06104458838, 3911.77843318506, 5132.18941177482, 5588.42751956065,
    4669.15077493611, 3585.74699438743,
]

HISTORICAL_IMPORTS_TOTAL = [
    1118.36635845716, 794.474848440275, 1078.32182497515, 1084.74093842716, 1114.56562476901,
    1217.72689248345, 1384.48962336472, 1188.40241104265, 1363.70269197603, 1107.15360648709,
    1079.88674793521, 897.563066682766, 1165.26202046205, 1113.99742854573, 1192.78081986382,
    1141.03484576022, 1282.76952249158, 1196.9528396503, 1478.73428368584, 1130.25866156118,
    983.256836657184, 1057.82783258626, 859.78528373021, 1047.81518864674, 1218.65553148362,
    1228.55602078189, 1184.13259748501, 1099.29555589241, 1157.87033955218, 1304.75382834562,
    1417.41988805233, 1361.12887937509, 1326.1015418632, 1016.89080947691, 1120.2570142395,
    1323.00894271064, 1110.53298779414, 1099.0319135662, 1092.17014757296, 1272.14995998632,
    1396.64684111612, 1277.13146479834, 1170.77508737105, 1084.50578209097, 1222.80008738644,
    1164.56257623986, 1199.44482358025, 1171.22534011288, 1070.81091743928, 1025.67849309797,
    1099.71653649836, 1128.2990649358, 1146.48276937844, 1041.6944791607, 1067.96012544155,
    1050.66473051418, 857.38894658043, 843.786333674085, 924.818655326557, 912.109196062181,
    1081.40312810135, 1192.62088634034, 1311.12573548429, 1027.76419248581, 1096.91168272053,
    1055.46505496561, 1087.85625452883,
]

HISTORICAL_EXPORTS_EUROPE = [
    803.749561006729, 737.506003399554, 759.16892773521, 1161.86581989044, 1089.99940409117,
    1006.12905349463, 982.420330469488, 1178.36225831225, 1097.72542955737, 1238.19817582102,
    1190.09032167978, 1168.91077504, 1227.39541196464, 1277.45122004803, 1226.00412818528,
    1487.58389925904, 1485.23236477623, 1467.18168054933, 1391.6202111741, 1472.13365368624,
    1624.9964305325, 1613.39058467705, 1451.4258015158, 1697.94131659492, 1559.62393060286,
    1553.61806302408, 2031.18733586004, 1497.0348595978, 1890.99235416714, 1958.16452005915,
    2020.46900155121, 1811.32617754435, 1884.10441588731, 1935.44327734191, 1850.11517901115,
    2340.42859337334, 2080.07268910889, 2170.53543443949, 1666.97886783937, 1814.2707939565,
    1749.47647979105, 1446.43983932469, 2131.35568568339, 1853.27725811656, 1730.13031229539,
    1989.57490477582, 2093.91981414029, 1971.89790144122, 1970.28350184919, 1329.39365058,
    1543.70052645512, 1881.31497924677, 1393.50440103118, 1832.88228682417, 1506.86255869129,
    1826.41423397929, 1602.34522296225, 2005.72517427493, 1782.90953428356, 1930.89329938973,
    2178.67934186587, 1983.84707008493, 1757.30278557652, 2218.28372664567, 2566.23987596656,
    1698.38027104471, 1632.48074221807,
]

HISTORICAL_EXPORTS_ASIAPAC = [
    1786.06343947578, 988.110007169486, 1405.05043788951, 1484.0911422904, 1078.98501651471,
    1558.4173997965, 1105.57873328206, 1000.59107378895, 997.413430716373, 957.318323437602,
    1516.4635267513, 1546.74102900043, 1597.86059194868, 1491.92696523559, 1162.8476390983,
    1150.55349075052, 1244.76171894679, 1205.27273142782, 1479.08293060454, 1430.85387648025,
    1696.72397313077, 1697.10287470111, 1774.46131441526, 1428.87152702783, 1278.24695188171,
    1877.66743902545, 1769.38796470718, 2080.77719205664, 1503.75392938162, 1324.36659615789,
    1310.48379133062, 1789.98854706654, 1940.00076316368, 1850.33230590968, 1868.75670153109,
    1594.2064473683, 1268.32061631703, 1638.73061906029, 1988.95724131993, 1561.80477727886,
    1935.25853140268, 1857.54153738485, 1512.48912699722, 1355.27383471469, 1426.21399948298,
    1034.89128153734, 1492.90705609819, 1289.56006893876, 1434.21021881987, 1806.74158744575,
    1818.44332747779, 1282.47586652099, 1528.67372668821, 957.019185389861, 912.176862250084,
    1339.16836286964, 2032.79277024014, 1658.06601350974, 1399.33051046635, 1244.0064932758,
    1107.60036767392, 1247.46594988585, 1567.25211141332, 2262.65719546991, 2526.95476203892,
    2229.81423463803, 1163.17797704809,
]

HISTORICAL_IMPORTS_VENEZUELA = [
    0, 0, 0, 0, 0,
    0, 0, 0, 0, 0,
    0, 0, 0, 0, 0,
    0, 0, 0, 0, 0,
    0, 0, 0, 0, 39.0751377321415,
    59.4655741145901, 119.066702487476, 135.178858101664, 169.569157917929, 137.180613378134,
    135.92081599214, 127.668190904191, 141.419094481132, 151.098776138804, 112.468889024469,
    146.706284898431, 139.841177819377, 153.536915559748, 148.589482588617, 194.968099129092,
    133.108014734307, 192.377017954684, 250.515637656025, 243.3961726665, 189.036082336975,
    283.023018089312, 202.881959754018, 258.445410825369, 269.414676112393, 215.204981332292,
    250.414164750794, 176.174115794155, 114.094323176108, 77.1385303522147, 0,
    39.0430637561779, 102.101146863093, 121.39383906562, 144.428747872734, 136.073303319034,
    177.600296457033, 268.114115314332, 407.671207172706, 413.795307340062, 479.187493632835,
    636.772010510693, 641.639751063154,
]

HISTORICAL_IMPORTS_RESTOFLATAM = [
    752.826491740677, 540.409959519677, 595.634289149856, 659.762828016243, 671.347940694716,
    726.016893592549, 794.072192376169, 761.480189643064, 825.495510228384, 614.62538405634,
    663.956768873993, 494.397071236954, 723.101654518439, 610.722828624857, 773.00019344211,
    720.079717059161, 871.163937358925, 737.397597166567, 919.785481749677, 687.580724392614,
    679.047926050278, 711.848735006487, 602.819596282219, 652.950283328575, 835.617028286475,
    733.30778172668, 789.029529504111, 611.252334830099, 765.666738282585, 919.479488822902,
    948.289211089959, 891.006362183971, 833.789925358819, 718.736700474534, 785.80016139654,
    918.325440195945, 641.649082419101, 615.028799632814, 565.39478716326, 683.291627696048,
    759.895195929934, 739.960569177538, 614.892490296901, 580.942782952658, 622.194661670042,
    622.531805796702, 621.670305322081, 522.088406615071, 505.914032106804, 554.01511180902,
    540.39310058099, 723.655803073579, 698.81379245082, 646.983287344335, 649.124995031557,
    727.589823922434, 470.774617427514, 467.413130563908, 478.574766663752, 440.386400918248,
    463.685468242817, 421.395042245513, 455.199389734172, 313.20520569882, 375.237596072544,
    185.958236915779, 367.13341831627,
]


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


def _raw_export_model(inputs: ExportModelInputs) -> Dict[str, Dict[str, float]]:
    """The live workbook's three independent LINEST regressions (Total, Europe, AsiaPac) plus the
    five flat regions, with NO reconciliation applied. Total is NOT the sum of these regions --
    each is its own separately-fit equation over the same historical data, and their forecasts
    don't automatically agree (see run_export_model for the reconciliation applied on top)."""
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

        results[m] = {
            "Total": total, "Europe": europe, "AsiaPac": asiapac,
            "NorthAmerica": na, "LatinAmerica": latam, "MiddleEast": mideast,
            "Africa": africa, "Unclassified": unclass,
            "_balance_used": balance_used, "_balance_lag1": balance_lag1,
            "_dubai_spread_contemp": dubai_spread_contemp, "_dubai_spread_lag1": dubai_spread_lag1,
            "_brent_spread_contemp": brent_spread_contemp, "_spr_drawdown": spr_drawdown,
        }

        prev_balance_used = balance_used
        prev_dubai_spread_contemp = dubai_spread_contemp
        prev_spr_level = mi.spr_level

    return results


def run_export_model(inputs: ExportModelInputs, baseline_inputs: Optional[ExportModelInputs] = None
                      ) -> Dict[str, Dict[str, float]]:
    """Returns, per month: Total, Europe, AsiaPac (post-reconciliation), NA, LatAm, MidEast,
    Africa, Unclassified, plus the pre-reconciliation figures and the frozen historical gap, for
    transparency.

    RECONCILIATION DESIGN (mirrors the import model's fix). Total, Europe, and AsiaPac are three
    SEPARATE LINEST regressions fit independently on the same historical data -- they were never
    designed to sum to each other, and at the live workbook's own defaults they don't: Total can
    differ from Europe + AsiaPac + the five flat regions by anywhere from 0.3% to nearly 10%,
    month to month. (The original code's "SumOfRegions" figure looked consistent with Total only
    because it mistakenly added Total to itself on top of the real regional sum -- that double
    -counting bug is removed here.)

    This version freezes that historical gap at its value under the default inputs -- both the
    default month drivers AND the default regression coefficients -- and splits the frozen amount
    PROPORTIONALLY across ALL SEVEN regions (Europe, AsiaPac, and the five flat regions) by their
    current size each month, not just the two regressed ones. This spreads the adjustment instead
    of concentrating it on Europe/AsiaPac, and treats every region symmetrically: each has a
    "current raw value" (its own regression output for Europe/AsiaPac, its own flat constant for
    the rest), and the fixed historical residual is allocated across all of them by relative size.
    Total itself stays exactly its own independent regression output PLUS whatever your edits move
    ANY region away from its default value -- so Total and the seven regions always sum exactly,
    for any inputs, without inventing an unsupported economic relationship (e.g. routing
    crude-balance sensitivity into Europe specifically, which the data does not support -- see the
    regression test earlier in this conversation).

    Side effect: because the live workbook's regions never reconciled to Total in the first place,
    the baseline (default-inputs) regional figures below differ from the raw LINEST/flat outputs by
    a proportional share of the frozen gap -- sometimes a few percent, up to roughly 10% in the
    largest-gap month for the two regressed regions, much smaller for the flat regions since they're
    a small share of the total. Total is unaffected and still matches the workbook exactly at
    baseline.
    """
    if baseline_inputs is None:
        baseline_inputs = default_export_inputs()

    raw_current = _raw_export_model(inputs)
    raw_baseline = raw_current if inputs is baseline_inputs else _raw_export_model(baseline_inputs)

    region_keys = ["Europe", "AsiaPac", "NorthAmerica", "LatinAmerica", "MiddleEast", "Africa", "Unclassified"]

    results = {}
    for m in MONTHS:
        rc, rb = raw_current[m], raw_baseline[m]

        pretaper_current = {k: rc[k] for k in region_keys}
        pretaper_baseline_sum = sum(rb[k] for k in region_keys)

        frozen_gap = rc["Total"] - pretaper_baseline_sum

        combined_pretaper = sum(pretaper_current.values())
        if combined_pretaper != 0:
            final = {k: v + frozen_gap * (v / combined_pretaper) for k, v in pretaper_current.items()}
        else:
            share = frozen_gap / len(region_keys)
            final = {k: v + share for k, v in pretaper_current.items()}

        total = sum(final.values())

        results[m] = {
            "Total": total, **final,
            "_pretaper": pretaper_current, "_frozen_gap": frozen_gap,
            "_balance_used": rc["_balance_used"], "_balance_lag1": rc["_balance_lag1"],
            "_dubai_spread_contemp": rc["_dubai_spread_contemp"], "_dubai_spread_lag1": rc["_dubai_spread_lag1"],
            "_brent_spread_contemp": rc["_brent_spread_contemp"], "_spr_drawdown": rc["_spr_drawdown"],
        }

    return results


# ======================================================================
# IMPORT MODEL
# ======================================================================

@dataclass
class ImportMonthInput:
    """One month's editable import-model inputs."""
    refinery_runs_forecast: float       # kbd -- drives the top-down total
    padd2_production_lag3: float        # kbd -- editable; combined with padd3 below for the Rest-of-LatAm regression
    padd3_production_lag3: float        # kbd -- editable; for Nov/Dec this is OVERWRITTEN by Export Drivers'
                                         # Aug/Sep PADD3 Production at run time (see run_model) -- same physical
                                         # series, lag 3 months, so a single edit drives both models
    total_seasonal_index: float         # ratio-to-13mo-centered-MA index for the top-down total
    venezuela_seasonal_factor: float    # Venezuela's own applied factor (Aug-Dec renormalized to 1.0)
    restlatam_seasonal_index: float     # Rest-of-LatAm's own 12-month-normalized index

    @property
    def padd2_padd3_production_lag3(self) -> float:
        """PADD2+PADD3 combined production, lag 3mo -- a FORMULA (padd2 + padd3), not an
        independent input. This is what the Rest-of-LatAm regression actually uses."""
        return self.padd2_production_lag3 + self.padd3_production_lag3


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
    """Live Aug-Dec 2026 refinery-runs forecast, PADD2/PADD3 lag3 production (split), and seasonal
    indices pulled from the workbook. PADD2/PADD3 lag3 source months: Aug->May, Sep->Jun, Oct->Jul,
    Nov->Aug, Dec->Sep (2026). Nov/Dec's padd3_production_lag3 here is just the historical starting
    point -- run_model() overwrites it with Export Drivers' Aug/Sep PADD3 Production live."""
    months = {
        "2026-08": ImportMonthInput(refinery_runs_forecast=10050.6721163138,
                                     padd2_production_lag3=1757.0, padd3_production_lag3=10201.0,
                                     total_seasonal_index=1.00456634451037, venezuela_seasonal_factor=0.93843200807292,
                                     restlatam_seasonal_index=1.05775429966797),
        "2026-09": ImportMonthInput(refinery_runs_forecast=9199.11778920685,
                                     padd2_production_lag3=1746.7034, padd3_production_lag3=10222.5937,
                                     total_seasonal_index=1.02944746292457, venezuela_seasonal_factor=0.967343235526544,
                                     restlatam_seasonal_index=0.960525750459174),
        "2026-10": ImportMonthInput(refinery_runs_forecast=9813.33447665122,
                                     padd2_production_lag3=1738.7040, padd3_production_lag3=10238.1474,
                                     total_seasonal_index=0.931656029277475, venezuela_seasonal_factor=1.00062282247969,
                                     restlatam_seasonal_index=0.894749221770264),
        "2026-11": ImportMonthInput(refinery_runs_forecast=9143.76984182102,
                                     padd2_production_lag3=1731.5672, padd3_production_lag3=10258.0910,
                                     total_seasonal_index=0.879799097552715, venezuela_seasonal_factor=1.02261363927956,
                                     restlatam_seasonal_index=0.988154826847248),
        "2026-12": ImportMonthInput(refinery_runs_forecast=9901.26012535112,
                                     padd2_production_lag3=1723.4303, padd3_production_lag3=10288.3790,
                                     total_seasonal_index=0.912040362300326, venezuela_seasonal_factor=1.07098829464129,
                                     restlatam_seasonal_index=0.949555405796262),
    }
    return ImportModelInputs(months=months)


def run_import_model(inputs: ImportModelInputs, baseline_inputs: Optional[ImportModelInputs] = None
                      ) -> Dict[str, Dict[str, float]]:
    """Returns, per month: Total, Venezuela, RestOfLatAm (both post-reconciliation), MiddleEast,
    NorthAmerica, Europe, Africa, AsiaPac, Unclassified, plus the pre-reconciliation figures and
    the frozen historical gap, for transparency.

    RECONCILIATION DESIGN. The top-down, Runs-based total and the two bottom-up regressions
    (Venezuela, Rest-of-LatAm) rarely agree exactly -- historically there's a persistent gap
    between them. The original design (matching the live workbook) recomputed that gap live from
    whatever Venezuela/RestOfLatAm currently produced and split it 50/50, which had a side effect:
    moving ONE region's driver (e.g. PADD2+PADD3 production, which feeds Rest-of-LatAm) silently
    forced the OTHER region (Venezuela) to move the opposite direction by the same amount, purely
    to keep the pair summing to a fixed number -- with zero net change to Total. That's a
    reconciliation artifact, not an economic relationship.

    This version instead FREEZES the historical gap at its value under the default inputs (so it
    no longer reacts to your edits), and splits that frozen amount PROPORTIONALLY by each region's
    current size rather than always 50/50. Two consequences: (1) a genuine change to production, a
    seasonal factor, or the runs forecast now shows up as a real change in Total imports, instead
    of netting to zero; (2) when a driver moves one region, the other only echoes a small,
    size-proportional share of the frozen gap -- both regions move the same direction when a
    real driver moves them, rather than one auto-offsetting the other.

    Side effect: because the live workbook's own reconciliation is a fixed 50/50 split rather than
    proportional, the baseline (default-inputs) Venezuela/RestOfLatAm figures below differ very
    slightly (well under 1%) from the published workbook values, even though Total still matches
    the workbook exactly at baseline.
    """
    if baseline_inputs is None:
        baseline_inputs = default_import_inputs()

    results = {}

    for m in MONTHS:
        mi = inputs.months[m]
        base_mi = baseline_inputs.months[m]

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

        # Same formulas, evaluated ENTIRELY at baseline_inputs -- both the default month drivers
        # AND the default coefficients/flat-region levels. This must be a true constant, untouched
        # by ANY current edit (whether a per-month driver or an advanced-panel coefficient),
        # otherwise that edit's effect gets silently absorbed by the other region instead of
        # reaching Total -- freezing only the month values (and not the coefficients) was exactly
        # that bug for venezuela_anchor_jul/restlatam_intercept/restlatam_slope edits.
        venezuela_pretaper_base = baseline_inputs.venezuela_anchor_jul * base_mi.venezuela_seasonal_factor
        restlatam_pretaper_base = ((baseline_inputs.restlatam_intercept
                                     + baseline_inputs.restlatam_slope * base_mi.padd2_padd3_production_lag3)
                                    * base_mi.restlatam_seasonal_index)
        other_sum_base = (baseline_inputs.middle_east_flat + baseline_inputs.north_america_flat
                           + baseline_inputs.europe_flat + baseline_inputs.africa_flat
                           + baseline_inputs.asiapac_flat + baseline_inputs.unclassified_flat)

        frozen_gap = top_down_total - (venezuela_pretaper_base + restlatam_pretaper_base + other_sum_base)

        combined_pretaper = venezuela_pretaper + restlatam_pretaper
        if combined_pretaper != 0:
            venezuela = venezuela_pretaper + frozen_gap * (venezuela_pretaper / combined_pretaper)
            restlatam = restlatam_pretaper + frozen_gap * (restlatam_pretaper / combined_pretaper)
        else:
            venezuela = venezuela_pretaper + frozen_gap / 2
            restlatam = restlatam_pretaper + frozen_gap / 2

        total = venezuela + restlatam + other_sum

        results[m] = {
            "Total": total, "Venezuela": venezuela, "RestOfLatAm": restlatam,
            "MiddleEast": mideast, "NorthAmerica": na, "Europe": europe, "Africa": africa,
            "AsiaPacific": asiapac, "Unclassified": unclass,
            "_venezuela_pretaper": venezuela_pretaper, "_restlatam_pretaper": restlatam_pretaper,
            "_frozen_gap": frozen_gap,
        }

    return results


# ======================================================================
# COMBINED RUN + REPORTING
# ======================================================================

# Import month -> the Export month whose contemporaneous PADD3 Production IS that import month's
# PADD3 Production, lag 3mo (same physical series) -- derived from IMPORT_PADD_SOURCE_MONTH so the
# two mappings can't drift apart. Aug/Sep/Oct 2026 import rows lag back to May/Jun/Jul 2026, outside
# this model's Aug-Dec editable window on either side, so those three stay independently editable
# with no live source to link to; only source months that are themselves in MONTHS get linked.
EXPORT_TO_IMPORT_PADD3_LAG3_LINKS = {
    import_month: source_month
    for import_month, source_month in IMPORT_PADD_SOURCE_MONTH.items()
    if source_month in MONTHS
}


# USGC Refinery Runs is the same physical series in both models, and -- unlike PADD3 Production --
# with NO lag: Export Drivers' month M "USGC Refinery Runs" and Import Drivers' month M "Refinery
# Runs Forecast" are identical at the live workbook's defaults, for all five months.
EXPORT_TO_IMPORT_REFINERY_RUNS_LINKS = {m: m for m in MONTHS}


def _apply_export_to_import_linkage(export_inputs: ExportModelInputs,
                                     import_inputs: ImportModelInputs) -> ImportModelInputs:
    """PADD3 Production and USGC Refinery Runs are both the same physical series in each model.
    Rather than requiring the same number to be entered twice (and risking the two drifting apart),
    Export Drivers' values are carried straight into Import Drivers' corresponding fields here, so a
    single edit drives both models consistently:
      - PADD3 Production: Export's Aug/Sep -> Import's Nov/Dec PADD3 Production Lag3 (3mo lag).
      - USGC Refinery Runs: Export's month M -> Import's month M Refinery Runs Forecast (no lag,
        all five months)."""
    new_months = dict(import_inputs.months)
    for import_month, export_month in EXPORT_TO_IMPORT_PADD3_LAG3_LINKS.items():
        new_months[import_month] = replace(
            new_months[import_month],
            padd3_production_lag3=export_inputs.months[export_month].padd3_production,
        )
    for import_month, export_month in EXPORT_TO_IMPORT_REFINERY_RUNS_LINKS.items():
        new_months[import_month] = replace(
            new_months[import_month],
            refinery_runs_forecast=export_inputs.months[export_month].usgc_refinery_runs,
        )
    return replace(import_inputs, months=new_months)


def run_model(export_inputs: ExportModelInputs, import_inputs: ImportModelInputs) -> Dict[str, Dict]:
    linked_import_inputs = _apply_export_to_import_linkage(export_inputs, import_inputs)
    return {
        "exports": run_export_model(export_inputs),
        "imports": run_import_model(linked_import_inputs),
    }


def print_results(result: Dict[str, Dict], title: str = "USGC Crude Export & Import Forecast") -> None:
    exp, imp = result["exports"], result["imports"]
    print(f"\n{title}")
    print("=" * len(title))

    print(f"\n{'EXPORTS (kbd)':<14}" + "".join(f"{MONTH_LABELS[m]:>12}" for m in MONTHS))
    for row in ["Total", "Europe", "AsiaPac", "NorthAmerica", "LatinAmerica", "MiddleEast", "Africa", "Unclassified"]:
        print(f"{row:<14}" + "".join(f"{exp[m][row]:>12,.1f}" for m in MONTHS))

    print(f"\n{'IMPORTS (kbd)':<14}" + "".join(f"{MONTH_LABELS[m]:>12}" for m in MONTHS))
    for row in ["Total", "Venezuela", "RestOfLatAm", "MiddleEast", "NorthAmerica", "Europe", "Africa", "AsiaPacific", "Unclassified"]:
        print(f"{row:<14}" + "".join(f"{imp[m][row]:>12,.1f}" for m in MONTHS))

    imp_range = [imp[m]["Total"] for m in MONTHS]
    print(f"\nTotal exports (model), Aug-Dec range: {min(exp[m]['Total'] for m in MONTHS):,.0f} - "
          f"{max(exp[m]['Total'] for m in MONTHS):,.0f} kbd")
    print(f"Total imports (top-down), Aug-Dec range: {min(imp_range):,.0f} - {max(imp_range):,.0f} kbd")


# ======================================================================
# SELF-TEST: confirms the baseline (unmodified) run matches the live workbook
# ======================================================================

def _self_test():
    live_total_exports = [4222.43945610835, 3801.36863090811, 4275.615899902, 4034.09203275285, 4513.64352056882]
    live_imports_total = [1165.41744384255, 1093.09561561852, 1055.30983450713, 928.574136236755, 1042.34698326816]
    # Reference-only (NOT asserted): the live workbook's own raw, un-reconciled LINEST outputs for
    # Europe/AsiaPac and its 50/50-split Venezuela/RestOfLatAm. This model reconciles Europe/AsiaPac
    # to Total (see run_export_model docstring) and splits the import gap proportionally instead of
    # 50/50 (see run_import_model docstring), so these differ by design -- Total matches exactly
    # in both cases.
    live_europe_raw_reference = [1934.28237134572, 2175.32566055695, 2208.32293942643, 2243.5439705337, 2194.86916421322]
    live_asiapac_raw_reference = [1676.57976090821, 1361.47880409209, 1635.10314415806, 1457.76712348492, 1768.41763750344]
    live_venezuela_50_50_reference = [554.627197439652, 553.563097082926, 562.65717804753, 484.508492834111, 569.019401394041]
    live_restlatam_50_50_reference = [486.087400670386, 414.829672803086, 367.949810727084, 319.362797670132, 348.624736141609]

    result = run_model(default_export_inputs(), default_import_inputs())
    exp, imp = result["exports"], result["imports"]

    checks = [
        ("Total exports", [exp[m]["Total"] for m in MONTHS], live_total_exports),
        ("Total imports", [imp[m]["Total"] for m in MONTHS], live_imports_total),
    ]
    all_ok = True
    for name, computed, live in checks:
        max_diff = max(abs(c - l) for c, l in zip(computed, live))
        status = "OK" if max_diff < 0.01 else "MISMATCH"
        if max_diff >= 0.01:
            all_ok = False
        print(f"  [{status}] {name}: max diff vs. live workbook = {max_diff:.6f} kbd")

    for name, computed, ref, note in [
        ("Europe exports", [exp[m]["Europe"] for m in MONTHS], live_europe_raw_reference,
         "reconciled to Total by design"),
        ("Asia-Pacific exports", [exp[m]["AsiaPac"] for m in MONTHS], live_asiapac_raw_reference,
         "reconciled to Total by design"),
        ("Venezuela imports", [imp[m]["Venezuela"] for m in MONTHS], live_venezuela_50_50_reference,
         "proportional split by design"),
        ("Rest-of-LatAm imports", [imp[m]["RestOfLatAm"] for m in MONTHS], live_restlatam_50_50_reference,
         "proportional split by design"),
    ]:
        max_diff = max(abs(c - l) for c, l in zip(computed, ref))
        print(f"  [INFO]      {name}: max diff vs. live workbook's raw figure = {max_diff:.2f} kbd "
              f"(expected -- {note}, Total is unaffected)")

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
