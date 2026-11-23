"""Build the academic report and presentation from generated analysis tables.

No fitting or model selection occurs here. One content definition drives each
document's editable and PDF versions. Optional dependencies are pinned in
requirements-submission.lock; the scientific lock remains unchanged.
"""

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".mplconfig"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from PIL import Image as PILImage
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Pt
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (Image, PageBreak, Paragraph, SimpleDocTemplate,
                               Spacer, Table, TableStyle)


OUT = ROOT / "submission"
FIG = OUT / "figures"
TITLE = "Beyond R²: Seasonal Effects, Residual Dependence, and Model Adequacy in Beijing PM2.5 Regression"
NAVY, TEAL, AMBER, INK, MUTED, PALE = "15324D", "087F8C", "B76B15", "233747", "536779", "EDF3F6"
AI = ("OpenAI Codex and Anthropic Claude assisted code and drafting. Codex assisted "
      "verification and editorial refinement. Numerical claims are tied to generated "
      "artifacts. The submitter remains responsible for interpretation and course-policy compliance.")
REFS = [
    ("Chen, S. (2017). Beijing Multi-Site Air Quality [Dataset]. UCI Machine Learning Repository. CC BY 4.0.",
     "https://doi.org/10.24432/C5RK5G"),
    ("Duan, N. (1983). Smearing Estimate: A Nonparametric Retransformation Method. Journal of the American Statistical Association, 78(383), 605–610.",
     "https://doi.org/10.1080/01621459.1983.10478017"),
    ("Statsmodels. Regression F-test documentation.",
     "https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.RegressionResults.compare_f_test.html"),
    ("UCI. Beijing Multi-Site Air Quality: dataset documentation.",
     "https://archive.ics.uci.edu/dataset/501/beijing+multi+site+air+quality+data"),
]
INPUTS, CLAIMS, FRAMES = {}, {}, {}
S2 = "results/stage2/tables/"
S3 = "results/stage3/tables/"
S4 = "results/stage4/tables/"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source(name):
    INPUTS[name] = sha(ROOT / name)
    return ROOT / name


def frame(name):
    if name not in FRAMES:
        FRAMES[name] = pd.read_csv(source(name))
    return FRAMES[name]


def number(name, column, where, fmt=".3f"):
    data = frame(name)
    selected = pd.Series(True, index=data.index)
    for key, value in where.items():
        selected &= data[key].eq(value)
    if selected.sum() != 1:
        raise ValueError(f"A document claim must identify one row: {name}, {where}")
    value = float(data.loc[selected, column].iloc[0])
    if not np.isfinite(value):
        raise ValueError(f"Nonfinite document claim: {name}/{column}")
    key = json.dumps([name, column, where, fmt], sort_keys=True)
    CLAIMS[key] = {"source": name, "column": column, "where": where,
                   "value": value, "format": fmt, "display": format(value, fmt)}
    return format(value, fmt)


def score(model="M3", column="mae", split="test", group="all", fmt=".3f", stage=2):
    return number((S2+"performance.csv") if stage == 2 else (S3+"model_comparison_scores.csv"),
                  column, {"split": split, "model": model, "subgroup": group}, fmt)


def logit(column, fmt=".3f"):
    return number(S3+"smog_logistic_performance.csv", column,
                  {"split": "test", "cutoff_rule": "validation_max_f1"}, fmt)


def figures():
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 14,
                         "axes.labelsize": 15, "axes.titlesize": 17,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.prop_cycle": plt.cycler(color=["#"+TEAL, "#"+AMBER, "#"+NAVY]),
                         "figure.dpi": 170, "savefig.facecolor": "white"})

    def save(fig, name):
        fig.savefig(FIG / (name+".png"), dpi=180, bbox_inches="tight")
        plt.close(fig)

    acf = frame(S2+"training_residual_acf.csv").query("model == 'M3'")
    fig, ax = plt.subplots(figsize=(10, 4.1), layout="constrained")
    ax.vlines(acf.lag_days, 0, acf.correlation, linewidth=3, color="#"+TEAL)
    ax.scatter(acf.lag_days, acf.correlation, color="#"+TEAL, s=32)
    ax.axhline(0, color="#"+MUTED, linewidth=0.8)
    ax.set(xlabel="Calendar lag (days)", ylabel="Paired-day residual correlation",
           title="M3 retains substantial day-to-day residual dependence", ylim=(-0.18, 0.6))
    ax.text(0.98, 0.88, f"Lag 1: r = {number(S2+'training_residual_acf.csv', 'correlation', {'model':'M3','lag_days':1})}\n"
            f"{number(S2+'training_residual_acf.csv', 'paired_days', {'model':'M3','lag_days':1}, '.0f')} observed date pairs",
            transform=ax.transAxes, ha="right", color="#"+NAVY)
    save(fig, "residual_dependence")

    residuals = frame(S2+"training_influence.csv").query("model == 'M3'")
    fig, axes = plt.subplots(1, 2, figsize=(11.8, 4.5), layout="constrained")
    axes[0].scatter(residuals.fitted, residuals.residual, s=14, alpha=0.5, color="#"+TEAL)
    axes[0].axhline(0, color="#"+MUTED, linewidth=1)
    axes[0].set(xlabel="Fitted PM2.5 (µg/m³)", ylabel="Residual (µg/m³)", title="Unequal spread and large positive errors")
    (theory, ordered), (slope, intercept, _) = stats.probplot(residuals.residual)
    axes[1].scatter(theory, ordered, s=14, color="#"+TEAL, alpha=0.7)
    axes[1].plot(theory, intercept+slope*theory, color="#"+AMBER)
    axes[1].set(xlabel="Normal theoretical quantile", ylabel="Ordered residual (µg/m³)", title="Normal Q–Q: upper-tail departure")
    save(fig, "residual_shape")

    predictions = frame(S2+"predictions.csv").query("split == 'test' and model == 'M3'").copy()
    predictions.index = pd.to_datetime(predictions.date)
    predictions = predictions.reindex(pd.date_range("2016-03-01", "2017-02-28"))
    fig, ax = plt.subplots(figsize=(10.5, 4.1), layout="constrained")
    ax.plot(predictions.index, predictions.observed, label="Observed", color="#"+NAVY, lw=1.2)
    ax.plot(predictions.index, predictions.predicted, label="Frozen M3 estimate", color="#"+TEAL, lw=1.2)
    ax.axhline(0, color="#"+MUTED, lw=0.5)
    ax.set(ylabel="Daily PM2.5 (µg/m³)", xlabel="Test dates, March 2016–February 2017",
           title="A lower average error still leaves severe high-day underestimation")
    ax.legend(frameon=False, loc="upper left", ncol=2, fontsize=12)
    save(fig, "frozen_test")

    models = ["M3", "M3_log", "M3_lag", "M3_met", "M3_log_lag_met"]
    labels = ["M3 refit", "Log M3", "+ Previous-day PM2.5", "+ Extra weather", "Log + lag + extra weather"]
    data = frame(S3+"model_comparison_scores.csv")
    fig, ax = plt.subplots(figsize=(10, 4.8), layout="constrained")
    for offset, split, label, color in [(-0.18, "validation", "Validation (n=354)", TEAL),
                                        (0.18, "test", "Reused test year (n=355)", AMBER)]:
        values = [data.loc[data.model.eq(m)&data.split.eq(split)&data.subgroup.eq("all"), "mae"].iloc[0] for m in models]
        bars = ax.barh(np.arange(5)+offset, values, height=0.33, label=label, color="#"+color)
        ax.bar_label(bars, fmt="%.1f", padding=4, fontsize=12)
    ax.set_yticks(np.arange(5), labels)
    ax.invert_yaxis()
    ax.set(xlabel="MAE on the original concentration scale (µg/m³)", xlim=(0, 61),
           title="Exploratory comparisons use one common sample")
    ax.legend(frameon=False, loc="lower right", fontsize=11)
    save(fig, "extension_mae")

    stations = frame(S3+"station_replication.csv").sort_values("m2_wind_coefficient")
    fig, ax = plt.subplots(figsize=(10, 5.2), layout="constrained")
    x = stations.m2_wind_coefficient
    ax.errorbar(x, np.arange(12), xerr=[x-stations.m2_wind_hac_ci_lower, stations.m2_wind_hac_ci_upper-x],
                fmt="o", color="#"+TEAL, capsize=3)
    ax.set_yticks(np.arange(12), stations.station)
    ax.axvline(0, color="#"+MUTED, lw=1)
    ax.set(xlabel="M2 wind association (µg/m³ per m/s), individual 95% HAC interval",
           title="Negative adjusted wind associations at all 12 stations")
    save(fig, "station_wind")

    clusters = frame(S3+"station_clusters.csv").sort_values(["cluster", "pm25"])
    pollutants = ["pm25", "pm10", "so2", "no2", "co", "o3"]
    fig, ax = plt.subplots(figsize=(9, 5.6), layout="constrained")
    im = ax.imshow(clusters[[p+"_z" for p in pollutants]], aspect="auto", cmap="RdBu_r", vmin=-2.5, vmax=2.5)
    ax.set_xticks(range(6), ["PM2.5", "PM10", "SO₂", "NO₂", "CO", "O₃"])
    ax.set_yticks(range(12), [f"{r.station}  [{r.cluster}]" for r in clusters.itertuples()])
    ax.axhline(3.5, color="white", lw=3)
    ax.set_title("Training pollutant profiles; bracketed values are cluster labels")
    fig.colorbar(im, ax=ax, label="Across-station z-score (sample SD)", shrink=0.9)
    save(fig, "station_profiles")

    slopes = frame(S2+"m3_seasonal_wind_slopes.csv")
    # Read the named columns rather than computing new coefficient intervals.
    xcol = "pm25_change_per_1_mps_wind"
    low = "hac_ci_lower"
    high = "hac_ci_upper"
    fig, ax = plt.subplots(figsize=(10, 3.7), layout="constrained")
    x = slopes[xcol]
    ax.errorbar(x, range(4), xerr=[x-slopes[low], slopes[high]-x], fmt="o", color="#"+TEAL, capsize=4)
    ax.set_yticks(range(4), slopes.season.str.capitalize())
    ax.axvline(0, color="#"+MUTED, lw=1)
    ax.set(xlabel="M3 wind slope (µg/m³ per m/s), individual 95% HAC interval",
           title="The summer interval includes zero; joint evidence is weaker after adjustment")
    save(fig, "seasonal_wind")


def content():
    """Canonical prose/tables and slide content; all empirical numbers read files."""
    frozen = json.loads(source("results/stage2/frozen_model.json").read_text())
    source("results/stage1_run.json")
    source("results/stage2/run.json")
    source("results/stage3/run.json")
    source("reports/stage4/statistical_audit.md")
    source("reports/reproducibility.md")
    source("data/raw/provenance.json")
    ntrain = str(frozen["training_observations"])
    nval = str(frozen["validation_observations"])
    ntest = score(column="n", fmt=".0f")
    cutoff = f"{frozen['high_pollution_training_cutoff']:.3f}"
    rho = number(S2+"training_residual_acf.csv", "correlation", {"model":"M3", "lag_days":1})
    r2 = number(S2+"model_fit.csv", "r_squared", {"model":"M3"})
    hp = number(S2+"hac_joint_tests.csv", "p_holm_primary", {"hypothesis":"H1_season", "hac_lag_calendar_days":7}, ".4f")

    def p(text): return {"kind":"p", "text":text}
    def h(text): return {"kind":"h", "text":text}
    def image(name, caption): return {"kind":"image", "name":name, "caption":caption}
    def table(headers, rows): return {"kind":"table", "headers":headers, "rows":rows}

    fit_rows = [[m, number(S2+"model_fit.csv", "parameters", {"model":m}, ".0f"),
                 number(S2+"model_fit.csv", "r_squared", {"model":m}),
                 number(S2+"model_fit.csv", "adjusted_r_squared", {"model":m}),
                 number(S2+"model_fit.csv", "sse", {"model":m}, ".1f")] for m in ("M1", "M2", "M3")]
    tests = []
    for hypothesis, label in [("H1_season", "H1: add season"), ("H2_wind_by_season", "H2: wind × season")]:
        tests.append([label, number(S2+"nested_anova.csv", "f_statistic", {"hypothesis":hypothesis}),
                      number(S2+"nested_anova.csv", "p_value_iid", {"hypothesis":hypothesis}, ".4f"),
                      number(S2+"hac_joint_tests.csv", "p_value_hac", {"hypothesis":hypothesis,"hac_lag_calendar_days":7}, ".4f"),
                      number(S2+"hac_joint_tests.csv", "p_holm_primary", {"hypothesis":hypothesis,"hac_lag_calendar_days":7}, ".4f")])
    coefficients = []
    for term, label in [("temperature_c","Temperature (°C)"), ("wind_speed_c","Wind (m/s)"),
                        ("rainfall_c","Rain (mm/day)"), ("pressure_c","Pressure (hPa)")]:
        coefficients.append([label, number(S2+"coefficients.csv","estimate",{"model":"M2","term":term}),
                             "["+number(S2+"coefficients.csv","hac_ci_lower",{"model":"M2","term":term})+", "+
                             number(S2+"coefficients.csv","hac_ci_upper",{"model":"M2","term":term})+"]"])
    validation = [[m, number(S2+"validation_selection.csv", "mae", {"model":m}),
                   number(S2+"validation_selection.csv", "rmse", {"model":m})] for m in ("M1","M2","M3")]
    errors = [["M3", score(), score(column="rmse"), score(column="mean_signed_error")],
              ["Training mean", score("training_mean"), score("training_mean","rmse"), score("training_mean","mean_signed_error")],
              ["M3: high days only", score(group="high"), score(column="rmse",group="high"), score(column="mean_signed_error",group="high")]]
    ext_names = [("M3","M3 refit"),("M3_log","Log M3"),("M3_lag","M3 + prior PM2.5"),
                 ("M3_met","M3 + extra weather"),("M3_log_lag_met","Log + lag + weather")]
    extensions = [[label, score(m, split="validation", fmt=".1f", stage=3), score(m, fmt=".1f", stage=3),
                   score(m,column="rmse",fmt=".1f",stage=3)] for m,label in ext_names]
    ar_rows = []
    for method,label in [("original_glsar_rows","Original GLSAR rows"),("conditional_ml_rows","Likelihood rows"),
                          ("conditional_ml_calendar","Likelihood calendar")]:
        ar_rows.append([label, number(S4+"ar1_calendar_sensitivity.csv","rho",{"method":method,"model":"M2"}),
                        number(S4+"ar1_calendar_sensitivity.csv","p_value_approx",{"method":method,"model":"M2"},".4f"),
                        number(S4+"ar1_calendar_sensitivity.csv","p_value_approx",{"method":method,"model":"M3"},".4f")])
    stations = frame(S3+"station_replication.csv")
    h1 = int(stations.h1_holm_p.lt(.05).sum())
    h2 = int(stations.h2_holm_p.lt(.05).sum())
    wins = int(stations.test_m3_mae.lt(stations.test_baseline_mae).sum())
    groups = frame(S3+"station_clusters.csv")
    group1 = ", ".join(groups.loc[groups.cluster.eq(1),"station"].sort_values())
    group2 = ", ".join(groups.loc[groups.cluster.eq(2),"station"].sort_values())

    pages = [
        {"title":"Abstract", "blocks":[
            p(f"This study asks whether weather and season adequately describe daily PM2.5 at Beijing's Wanliu station. Three nested multiple regressions are compared using ANOVA, calendar-aware HAC joint tests and residual diagnostics. The original confirmatory analysis uses {ntrain} training, {nval} validation and {ntest} test days from the UCI Beijing Multi-Site Air Quality dataset."),
            p(f"The fixed validation rule selects the wind-interaction model M3. Its test MAE is {score()} µg/m³, compared with {score('training_mean')} for the training-mean baseline. Yet its training R² of {r2} coexists with residual lag-one correlation {rho}, high-day underestimation and negative estimates. Both planned joint hypotheses have Holm-adjusted p = {hp}; neither rejects at 5%."),
            p("These results separate improved fit from adequate errors and stable inference. Later log-response, lag and weather extensions provide exploratory comparisons on a different common sample. All models use observed same-day weather, so their errors describe contemporaneous estimation rather than advance forecasting."),
            h("Research question"),
            p("After adjustment for temperature, wind speed, rainfall and pressure, do seasonal offsets and season-specific wind associations add information about daily PM2.5? What do the residuals reveal about the adequacy of that regression description?"),
            p("Stage 2 supplies the original confirmatory investigation, with its protocol fixed before fitting. Stage 3 was developed after the original test year had been inspected. Its findings, including cross-station and classification analyses, therefore support interpretation without providing new confirmation."),
            p("Keywords: multiple regression; nested-model ANOVA; HAC covariance; residual dependence; PM2.5.")
        ]},
        {"title":"1. Data and study design", "blocks":[
            p("The UCI dataset contains 420,768 hourly records at 12 Beijing stations, March 2013–February 2017. Meteorology is matched from nearby weather stations [1,4]. Wanliu is selected by eligible training-day count, then valid training PM2.5 hours and alphabetical name. Future coverage and concentration levels do not enter selection."),
            p("A complete 1,461-day calendar preserves unavailable dates. Daily means require 18 valid hours for PM2.5, temperature, pressure and wind speed. Rain totals require all 24 hourly amounts; an analysis day also needs 18 hours with all five fields jointly observed. Means can use different valid-hour subsets. Missing outcomes are not imputed; valid zeros, negative temperatures and high positive concentrations are retained."),
            p("Table 1 summarizes the chronological partitions. Their 1,441 eligible days exclude 20 dates; keeping the complete calendar prevents lag calculations from joining observations across those gaps."),
            table(["Partition","Dates (end exclusive)","Eligible / calendar days"],
                  [["Training","2013-03-01 to 2015-03-01",ntrain+" / 730"],
                   ["Validation","2015-03-01 to 2016-03-01",nval+" / 366"],
                   ["Test","2016-03-01 to 2017-03-01",ntest+" / 365"]]),
            p("Weather and PM2.5 are aggregated on the same local civil dates, assumed Asia/Shanghai because the source gives no explicit timezone. Rain values are interpreted as hourly interval amounts. Completeness filtering and these measurement assumptions limit the interpretation of the retained sample."),
            p("Centering constants, the mean baseline and the high-day threshold are estimated from training data only. Validation MAE selects a specification before frozen test scoring. The eligible training daily 95th percentile is "+cutoff+" µg/m³; days at or above it are classified as high. This is a study quantile, not a regulatory or health category.")
        ]},
        {"title":"2. Multiple regression and joint inference", "blocks":[
            p("Let Y be daily PM2.5 (µg/m³). T, W, R and P denote training-mean-centered temperature (°C), wind speed (m/s), rainfall (mm/day) and pressure (hPa). Winter is the reference season; Ss denotes the spring, summer or autumn indicator. The nested specifications are:"),
            p("M1: E(Y | X) = β₀ + βT T + βW W + βR R + βP P.\nM2 adds Σ γs Ss; M3 adds Σ δs (W × Ss)."),
            p("Table 2 shows the common-sample training fits. Every design has full rank. Centering preserves fitted values while making seasonal offsets refer to the training mean wind speed; numerical conditioning is assessed separately from coefficient uncertainty."),
            table(["Model","Parameters","R²","Adjusted R²","SSE"],fit_rows),
            p("H1 tests the three seasonal terms jointly in M2 (M1 versus M2). H2 tests the three wind interactions jointly in M3 (M2 versus M3). With q = 3 added parameters, nested-model ANOVA uses F = [(SSErestricted − SSEfull) / q] / [SSEfull / (n − pfull)]. Its exact reference assumes an appropriate linear mean and independent, homoscedastic Gaussian errors [3]."),
            p("Table 3 contrasts the ordinary F results with primary robust inference. Calendar HAC uses Bartlett-weight score products at actual date separations, zero scores at omitted positions and the n/(n−p) correction. The primary bandwidth is seven days; 14/30-day sensitivities are documented separately. Joint Wald tests use an asymptotic χ²(3) reference; Holm adjustment covers the two primary hypotheses."),
            table(["Question","F","Classical p","7-day HAC p","Holm p"],tests),
            p("Seasonal indicators reduce SSE and give a small classical H1 p-value, but neither primary joint test rejects after Holm adjustment. This is insufficient evidence against those joint nulls at 5%, not proof that seasonal structure is absent. The distinction matters because the residuals challenge the iid assumptions underlying conventional ANOVA calibration.")
        ]},
        {"title":"3. Interpreting the weather associations", "blocks":[
            p("Table 4 gives M2's weather coefficients and individual 95% HAC intervals. Each coefficient is a fitted concentration difference per unit higher predictor, conditional on the other listed weather variables and season."),
            table(["M2 predictor (one unit)","Difference (µg/m³)","Individual 95% HAC interval"],coefficients),
            p("For wind, the estimated association is "+coefficients[1][1]+" µg/m³ per m/s, with interval "+coefficients[1][2]+". The adjustment is descriptive: it does not identify the effect of an intervention on wind. Conditional temperature or pressure coefficients likewise should not be equated with marginal correlations."),
            p("Figure 1 shows M3's seasonal wind slopes. Winter uses the base wind coefficient; the other slopes add the relevant interaction. Their intervals use the full linear-contrast covariance. Summer's interval includes zero, despite a negative point estimate."),
            image("seasonal_wind","Figure 1. Seasonal wind associations in training M3, with individual 7-calendar-day HAC intervals. Source: m3_seasonal_wind_slopes.csv."),
            p("These individual intervals are not simultaneous statements about all seasons. Interpretation of the planned seasonal blocks remains tied to the joint tests in Table 3.")
        ]},
        {"title":"4. Residual adequacy beyond R²", "blocks":[
            p(f"R² rises from {fit_rows[0][2]} in M1 to {r2} in M3, but Figure 2 shows substantial remaining serial structure. M3's lag-one residual correlation is {rho}, based on 719 adjacent-calendar-day pairs. Daily aggregation has not produced independent errors."),
            image("residual_dependence","Figure 2. M3 training residual correlations at calendar-day lags. Pair counts vary by lag; missing daily positions remain explicit."),
            p("Figure 3 adds two different checks. The residual-versus-fitted plot shows changing spread and large positive errors; the normal Q–Q plot shows an upper-tail departure. A Q–Q plot assesses distributional shape, not temporal independence."),
            image("residual_shape","Figure 3. M3 training residual spread and normal Q–Q plot. No flagged observation is removed."),
            p("Serial auxiliary, Koenker/Breusch–Pagan and Jarque–Bera diagnostics support this assessment, with reference-distribution assumptions that remain vulnerable to dependence and missingness. The serial regression uses seven calendar-day lags and complete auxiliary rows. Forty observations exceed Cook's-distance screening value 4/n; flags prompt inspection, not deletion.")
        ]},
        {"title":"5. Validation selection and frozen test estimates", "blocks":[
            p("The fixed rule minimizes validation MAE, preferring fewer parameters among candidates within 1% of the minimum. Table 5 selects M3; M2 is only 1.11% above the minimum, just outside the tolerance. The narrow margin should temper claims of model superiority."),
            table(["Candidate","Validation MAE","Validation RMSE"],validation),
            p("Table 6 reports the original frozen test evaluation in µg/m³. Coefficients, training centers, the baseline and the high-day cutoff are persisted before scoring. There is no validation/test refit or negative-estimate clipping."),
            table(["Test evaluation","MAE","RMSE","Mean estimate − observation"],errors),
            p(f"M3 improves average error across {ntest} dates, yet overall bias is positive while high-day bias is negative. The high-day row contains only {score(column='n',group='high',fmt='.0f')} observations. Figure 4 shows missed concentration peaks; {score(column='negative_predictions',fmt='.0f')} negative test estimates also expose a physical limitation of unrestricted linear regression."),
            image("frozen_test","Figure 4. Observed test concentrations and frozen M3 same-day estimates. Missing dates break the lines."),
            p("Dependence prevents a naive independent-day confidence interval for the error difference; none is asserted. The frozen evaluation is reproduced without retuning it or restoring the test year's unseen status.")
        ]},
        {"title":"6. Exploratory temporal and weather extensions", "blocks":[
            p("Stage 3 explores log1p responses, previous-day PM2.5, dew point and wind vectors. Table 7 compares five candidates on 721 training, 354 validation and 355 test dates. Its common-sample M3 refit and training quantile do not replace the frozen evaluation."),
            table(["Common-sample model","Validation MAE","Test MAE*","Test RMSE*"],extensions),
            p("*The original test year had already been inspected. The combined model is selected by validation MAE within this exploratory set; lower errors on these dates are not independent confirmation. Errors are compared in original units, while R² values on original and log responses are not directly comparable."),
            p("For a log fit, s = mean(exp(training residual)) and the original-unit estimate is exp(linear predictor) × s − 1 [2]. The factors are "+number(S3+"model_comparison_fits.csv","smearing_factor",{"model":"M3_log"})+" and "+number(S3+"model_comparison_fits.csv","smearing_factor",{"model":"M3_log_lag_met"})+". A common factor can misestimate conditional means when residual distributions vary. The formula bounds estimates above −1, not zero; nonnegative estimates are an empirical result here."),
            p("Lags are constructed before filtering on the complete calendar. An unavailable prior PM2.5 day makes its lag missing. Actual earlier validation/test outcomes become available to later same-day estimates, so this is a rolling estimation task rather than an open-loop forecast."),
            h("AR(1) calendar-gap sensitivity"),
            p("Original GLSAR compresses retained rows, treating five two-day gaps as one step. Table 8 holds conditional-likelihood estimation and first-observation treatment fixed while comparing row versus actual-calendar transitions ρᵈ with gap-adjusted innovation variance."),
            table(["Method","M2 ρ","H1 nominal p","H2 nominal p"],ar_rows),
            p("Nominal decisions, including within-method Holm, are unchanged. The plug-in F reference omits uncertainty in fitted ρ. Stationary Gaussian AR(1) is a working assumption; these exploratory results do not override primary HAC/Holm inference.")
        ]},
        {"title":"7. Cross-station consistency and classification", "blocks":[
            p(f"Figure 5 compares M2 wind associations at all 12 stations, each using its own eligible dates, training centers and cutoff. All individual intervals lie below zero. H1/H2 pass within-station Holm adjustment at {h1}/{h2} sites; this does not correct the full family of 24 tests. Stations share pollution and weather, so their agreement is not independent replication."),
            image("station_wind","Figure 5. Station-specific M2 wind associations with individual 7-day HAC intervals. Source: station_replication.csv."),
            p(f"M3 improves test MAE over its station training-mean baseline at {wins}/12 sites; Gucheng is the exception. The cross-station patterns are exploratory descriptions of this historical network."),
            h("High-day classification"),
            p(f"An M2 logistic model uses the training daily 95th percentile ({cutoff} µg/m³) to define its outcome. Validation F1 selects probability cutoff {logit('cutoff','.4f')}, with higher-cutoff tie breaking. On {ntest} test days, including {logit('smog_days','.0f')} high days, TP/FP/FN/TN are {logit('true_positive','.0f')}/{logit('false_positive','.0f')}/{logit('false_negative','.0f')}/{logit('true_negative','.0f')}."),
            p(f"AUC is {logit('auc')}, recall {logit('recall')} and precision {logit('precision')}; a 0.5 cutoff detects no high days. Good ranking therefore coexists with many false alarms. Rare events and serial dependence limit precision, and nominal odds-ratio intervals assume independence. The class is a statistical quantile, not a health standard.")
        ]},
        {"title":"8. Clustering, limitations and conclusions", "blocks":[
            p("Figure 6 summarizes six pollutant-specific training means, standardized across stations with sample SD. The largest Ward merge-height gap for k=2…5 selects two groups. The lower mean-PM2.5 group contains "+group1+"; the remaining eight stations form the other group. Pollutants can use different qualified dates; geographic meaning and new-period cluster stability have not been established."),
            image("station_profiles","Figure 6. Existing verified training pollutant profiles; brackets identify descriptive Ward groups, not administrative or causal categories."),
            h("Limits of the evidence"),
            p("The study is observational and limited to four historical years in one city. Omitted emissions, transport and boundary-layer information, nearest-station weather, selective completeness and temporal shifts can affect the associations. HAC cannot repair an inadequate conditional mean. Individual intervals and station-wise tests do not supply simultaneous protection across the exploratory analyses."),
            h("Conclusion"),
            p("Seasonal terms reduce SSE, but adjusted joint evidence and residual diagnostics give a more cautious assessment than training fit alone. M3 lowers average same-day test error while missing severe episodes and permitting negative estimates. Exploratory temporal/weather features improve errors on these dates. A defensible next step is an unseen period, prespecified rules and an explicit account of covariates available when an estimate is issued.")
        ]},
        {"title":"9. Reproducibility and references", "blocks":[
            p("The original UCI archive, chronological configurations, fixed environment and prefit protocol identify the investigation. Training parameters, dated predictions and per-run hashes are retained. Numerical claims in this report are read from generated artifacts and linked to their source rows in submission/build_manifest.json."),
            p("The repository's reproduction runner regenerates the analysis and documents. Independent aggregation, QR/HAC, logistic and direct Ward implementations check the calculations; a dense conditional covariance checks AR(1) sensitivity. Agreement is computational verification, not independent scientific replication. Detailed commands and evidence are in reports/reproducibility.md and reports/stage5_refinement.md."),
            h("References"),
            *[{"kind":"reference","number":i,"label":label,"url":url}
              for i,(label,url) in enumerate(REFS,1)],
            {"kind":"links","text":"Further method documentation", "items":[
                ("Bartlett HAC covariance","https://www.statsmodels.org/stable/generated/statsmodels.stats.sandwich_covariance.cov_hac.html"),
                ("Iterative GLSAR","https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.GLSAR.html")]},
            h("AI assistance"),p(AI)
        ]}
    ]

    slides = [
        dict(title="Beyond R²",section="BEIJING PM2.5 REGRESSION",layout="title",
             subtitle=TITLE.split(": ",1)[1],
             lines=["Multiple regression · ANOVA · residual adequacy", "Daily observations · March 2013–February 2017"],
             statement="What structure remains after adjusting for weather and season?",
             notes="Introduce a statistical adequacy investigation using UCI observations. Weather is measured on the same day as the response: this is contemporaneous estimation, not an advance-forecast benchmark. The original confirmatory regressions are distinguished from exploratory work developed after the test year was viewed."),
        dict(title="Does season add information beyond weather?",section="RESEARCH QUESTION",layout="questions",
             cards=[("H1 · Seasonal offsets","Do three seasonal terms add information after weather adjustment?"),
                    ("H2 · Wind interactions","Does the conditional wind association differ by season?"),
                    ("Model adequacy","Do residual patterns support the assumptions behind inference?")],
             notes="H1 compares M1 with M2; H2 compares M2 with M3. The third question concerns the errors, not another search for favorable p-values. Season can represent omitted processes, so seasonal coefficients describe conditional association rather than a causal mechanism."),
        dict(title="Daily data, chronological evaluation",section="DATA & DESIGN",layout="timeline",
             partitions=[("Training","Mar 2013–Feb 2015",ntrain,"730"),
                         ("Validation","Mar 2015–Feb 2016",nval,"366"),
                         ("Test","Mar 2016–Feb 2017",ntest,"365")],
             lines=["Wanliu selected by training completeness from 12 UCI stations.",
                    "Daily means: ≥18 valid hours; rainfall totals: 24 hours.",
                    "Also require 18 jointly observed core hours; preserve calendar gaps."],
             notes="The source contains 420,768 hourly station records. Wanliu retains 1,441 of 1,461 calendar dates. Each mean uses its own valid hours; there is no target imputation or outcome-based trimming. Centers and quantile thresholds use training data only. Local time and rainfall-amount assumptions are documented in the report."),
        dict(title="Three nested multiple regressions",section="CONFIRMATORY REGRESSION",layout="models",
             table=(["Model","Predictors added","Parameters","Training R²"],
                    [["M1","Temperature, wind, rain, pressure","5",fit_rows[0][2]],
                     ["M2","M1 + 3 seasonal indicators","8",fit_rows[1][2]],
                     ["M3","M2 + 3 season × wind terms","11",fit_rows[2][2]]]),
             lines=["Training-only centering · winter reference · original concentration scale",
                    "M2 wind: "+number(S2+"coefficients.csv","estimate",{"model":"M2","term":"wind_speed_c"},".1f")+" µg/m³ per m/s, conditional on other weather and season."],
             notes="Each added block has three parameters. In M3, seasonal offsets apply at the training mean wind speed and the base wind coefficient is the winter slope. Every design is full rank; conditioning is separate from statistical uncertainty. The wind coefficient is an observational association, not an intervention effect."),
        dict(title="Classical ANOVA and robust inference",section="PLANNED JOINT TESTS",layout="inference",
             table=(["Question","F","Classical p","HAC p","Holm p"],tests),
             statement=f"Both adjusted p-values = {hp}",
             lines=["Neither primary joint hypothesis rejects at 5%.",
                    "Seven-calendar-day Bartlett HAC · joint χ²(3) Wald · two-test Holm family"],
             equation="F = (SSE reduction / added df) / full-model residual mean square",
             notes="Classical F uses an iid, constant-variance Gaussian reference for exact calibration. HAC retains actual calendar separations and uses n/(n−p). Its Wald reference is asymptotic. The 14/30-day bandwidth checks are descriptive sensitivities. Failure to reject is not proof that seasonal structure is absent."),
        dict(title="Residual dependence remains",section="MODEL ADEQUACY",layout="figure",
             figure="residual_dependence",caption=f"M3 training R² {r2} · lag-one residual r {rho} · 719 adjacent-date pairs",
             notes="The first-lag correlation is substantial after weather and season adjustment. Missing calendar positions are retained and pair counts vary by lag. Daily aggregation has not made the errors independent. Read the magnitude and pattern rather than treating an auxiliary p-value as an independence certificate."),
        dict(title="Residual spread and distributional shape",section="MODEL ADEQUACY",layout="figure",
             figure="residual_shape",caption="Training M3 · unequal spread and upper-tail departure · no flagged day deleted",
             notes="The scatter and Q–Q plot address different aspects of adequacy. The Q–Q plot does not test independence. Serial, Koenker/Breusch–Pagan and influence diagnostics have calibration assumptions under dependence. Forty M3 observations exceed the Cook's-distance screening guide, which does not establish that they are errors."),
        dict(title="Average gain, high-day failure",section="FROZEN TEST EVALUATION",layout="evaluation",
             figure="frozen_test",metrics=[("M3 MAE",score()),("Baseline MAE",score('training_mean')),
                                            ("High-day signed error",score(column='mean_signed_error',group='high'))],
             caption="µg/m³ · 357 test days · 17 high days · 3 negative estimates retained",
             notes="The fixed validation rule chooses M3, with M2 only 1.11% above the minimum. Overall signed error is positive, but high-day error is strongly negative. The high-day cutoff is "+cutoff+" µg/m³, learned from training. There is no clipping or test-year refit; dependent errors preclude a naive independent-day interval for performance differences."),
        dict(title="Exploratory temporal and weather extensions",section="SUPPORTING ANALYSES · EXPLORATORY",layout="figure",
             figure="extension_mae",caption="721 train / 354 validation / 355 test · M3 refit on the common sample",
             notes="The five candidates share dates. Extra weather is dew point and two wind-vector components; the lag is the previous calendar day's observed PM2.5. Log estimates use a training-only smearing factor times exp(linear predictor), minus one. This does not guarantee nonnegativity. The viewed test year supplies descriptive comparisons, not independent confirmation."),
        dict(title="AR(1) sensitivity to five short gaps",section="SUPPORTING ANALYSES · EXPLORATORY",layout="ar1",
             table=(["Method","M2 ρ","H1 nominal p","H2 nominal p"],ar_rows),
             lines=["Paired likelihood fits change only row versus calendar spacing.",
                    "Transitions use ρᵈ with gap-adjusted innovation variance.",
                    "Nominal decisions agree; estimated-ρ uncertainty remains approximate."],
             notes="Original GLSAR compresses rows across five two-day training gaps. The paired check holds estimation and first-observation treatment fixed. A separate dense covariance verifies wind coefficients and profile objectives. Nominal H1/H2 conclusions remain unchanged, including within-method Holm adjustment. This does not validate stationary Gaussian AR(1) or override the primary HAC/Holm result."),
        dict(title="Cross-station consistency",section="SUPPORTING ANALYSES · EXPLORATORY",layout="figure",
             figure="station_wind",caption=f"Within-station Holm: H1 {h1}/12, H2 {h2}/12 · not a full 24-test correction",
             notes=f"Each station has its own eligible dates, centers and cutoff. All M2 wind intervals lie below zero. Seasonal findings vary; M3 beats the training-mean baseline at {wins}/12 sites, except Gucheng. Shared pollution and weather make these dependent sites, not independent replications."),
        dict(title="High recall brings many false alarms",section="SUPPORTING ANALYSES · EXPLORATORY",layout="classification",
             confusion=[logit('true_positive','.0f'),logit('false_positive','.0f'),
                        logit('false_negative','.0f'),logit('true_negative','.0f')],
             metrics=[("Validation-F1 cutoff",logit('cutoff','.4f')),("Test AUC",logit('auc')),
                      ("Recall / precision",logit('recall')+" / "+logit('precision'))],
             caption=f"High day: PM2.5 ≥{cutoff} µg/m³ (training 95th percentile) · 17 test high days · not a health standard",
             notes="The concentration threshold is the training daily 95th percentile. Validation F1 selects the probability cutoff, breaking ties toward a higher value; test labels do not select it. A 0.5 cutoff detects none. AUC describes ranking, while this table shows the selected cutoff's burden. Rare, dependent events limit precision; odds-ratio intervals assume independence."),
        dict(title="Two groups of training pollutant profiles",section="SUPPORTING ANALYSES · EXPLORATORY",layout="clusters",
             figure="station_profiles",lines=["Ward grouping", "Six pollutant means", "Across-station z-scores", "Two groups; no geographic classification"],
             caption="Pollutant-specific eligible dates · new-period cluster stability untested",
             notes="The existing verified heatmap displays the standardized training profiles and cluster labels. The largest merge-height gap for k=2…5 chooses two groups. The lower mean-PM2.5 group contains "+group1+". Group labels describe this period; they do not identify validated geographic or risk classes."),
        dict(title="Limits of the evidence",section="INTERPRETATION",layout="limits",
             cards=[("Study design","One city, four historical years; missingness and omitted drivers can affect associations."),
                    ("Statistical inference","Residual dependence remains; individual intervals and station-wise tests are not simultaneous protection."),
                    ("Evaluation","Observed same-day weather and a reused exploratory test year limit claims about future prediction.")],
             notes="Mention spatially matched weather, emissions/transport and boundary-layer information. HAC cannot repair an inadequate conditional mean. A common smearing factor can miss varying conditional error distributions. Cross-station consistency and separate implementation checks do not establish causal effects or independent scientific replication."),
        dict(title="Model adequacy requires more than explained variance",section="CONCLUSIONS",layout="conclusion",
             lines=["Seasonal terms reduce SSE; adjusted joint evidence is insufficient at 5%.",
                    "M3 lowers average error while retaining serial structure and high-day failure.",
                    "Next: an unseen period, prespecified rules and explicit covariate availability."],
             notes="Return to the question: fit reduction, inference and error behavior must be considered together. Smaller errors for exploratory temporal/weather models motivate further study without confirming them. A new evaluation should define the information available when an estimate is issued and avoid retuning on the current test year."),
        dict(title="References and assistance",section="SOURCES",layout="references",
             references=REFS,disclosure=AI,
             notes="Full references and attribution appear in the report, including UCI's CC BY 4.0 license and Duan's retransformation method. Empirical numbers are this project's generated results. AI assistance is disclosed; the submitter remains responsible for interpretation and course-policy compliance. Numerical verification is not independent scientific replication.")
    ]
    return pages, slides


def setup_fonts():
    font_dir = Path(matplotlib.get_data_path()) / "fonts/ttf"
    pdfmetrics.registerFont(TTFont("DejaVu", str(font_dir/"DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(font_dir/"DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold", italic="DejaVu", boldItalic="DejaVu-Bold")


def build_report(pages):
    styles = {
        "p": ParagraphStyle("Body", fontName="DejaVu", fontSize=10.1, leading=15, spaceAfter=10, allowWidows=0, allowOrphans=0, textColor=colors.HexColor("#"+INK)),
        "h": ParagraphStyle("Heading", fontName="DejaVu-Bold", fontSize=16, leading=21, spaceAfter=12, keepWithNext=True, textColor=colors.HexColor("#"+NAVY)),
        "caption": ParagraphStyle("Caption", fontName="DejaVu", fontSize=8.4, leading=11.5, spaceAfter=10, textColor=colors.HexColor("#"+MUTED)),
        "cell": ParagraphStyle("Cell", fontName="DejaVu", fontSize=8.5, leading=11.5, textColor=colors.HexColor("#"+INK)),
        "head": ParagraphStyle("Head", fontName="DejaVu-Bold", fontSize=8.5, leading=11.5, textColor=colors.white),
        "title": ParagraphStyle("Title", fontName="DejaVu-Bold", fontSize=24, leading=31, spaceAfter=19, textColor=colors.HexColor("#"+NAVY)),
    }
    story, markdown = [], ["# "+TITLE, ""]
    story += [Spacer(1, 9*mm), Paragraph(escape(TITLE), styles["title"]),
              Paragraph("Multiple regression · ANOVA · residual adequacy", styles["p"]), Spacer(1, 5*mm)]
    for i, page in enumerate(pages):
        if i:
            story.append(PageBreak())
        story.append(Paragraph(escape(page["title"]), styles["h"]))
        markdown += ["## "+page["title"], ""]
        for block in page["blocks"]:
            kind = block["kind"]
            if kind in ("p", "h"):
                story.append(Paragraph(escape(block["text"]), styles[kind]))
                markdown += [("### " if kind == "h" else "")+block["text"], ""]
            elif kind == "image":
                filename = "figures/"+block["name"]+".png"
                with PILImage.open(OUT/filename) as image:
                    width, height = image.size
                story.append(Image(str(OUT/filename), width=174*mm, height=174*mm*height/width))
                story.append(Paragraph(escape(block["caption"]), styles["caption"]))
                markdown += [f"![{block['caption']}]({filename})", ""]
            elif kind == "reference":
                label, url = block["label"], block["url"]
                link_label = ("DOI: "+url.removeprefix("https://doi.org/") if "doi.org/" in url else
                              "Official method documentation" if "statsmodels.org" in url else "Dataset documentation")
                story.append(Paragraph(f"[{block['number']}] {escape(label)} "
                                       f'<link href="{escape(url)}" color="#{TEAL}">{escape(link_label)}</link>',styles["p"]))
                markdown += [f"[{block['number']}] {label} [{link_label}]({url})", ""]
            elif kind == "links":
                links = " · ".join(f'<link href="{escape(url)}" color="#{TEAL}">{escape(label)}</link>'
                                   for label,url in block["items"])
                story.append(Paragraph(escape(block["text"])+": "+links,styles["p"]))
                markdown += [block["text"]+": "+" · ".join(f"[{label}]({url})" for label,url in block["items"]), ""]
            else:
                rows = [block["headers"], *block["rows"]]
                cells = [[Paragraph(escape(str(cell)), styles["head" if r==0 else "cell"]) for cell in row]
                         for r,row in enumerate(rows)]
                # Wider first column for descriptive labels; equal numerical columns.
                n = len(rows[0])
                ratios = ([.25,.42,.33] if n==3 and "Partition" in rows[0] else
                          [.29]+[.71/(n-1)]*(n-1))
                table = Table(cells, colWidths=[174*mm*v for v in ratios], repeatRows=1, hAlign="LEFT")
                table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#"+NAVY)),
                    ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.HexColor("#"+PALE),colors.white]),
                    ("VALIGN",(0,0),(-1,-1),"TOP"),("TOPPADDING",(0,0),(-1,-1),7),
                    ("BOTTOMPADDING",(0,0),(-1,-1),7),("LEFTPADDING",(0,0),(-1,-1),7),
                    ("LINEBELOW",(0,-1),(-1,-1),.5,colors.HexColor("#CEDAE2"))]))
                story += [table, Spacer(1, 11)]
                markdown += ["| "+" | ".join(block["headers"])+" |", "| "+" | ".join(["---"]*n)+" |",
                             *["| "+" | ".join(map(str,row))+" |" for row in block["rows"]], ""]

    def footer(c, doc):
        c.saveState()
        c.setStrokeColor(colors.HexColor("#CEDAE2"))
        c.line(18*mm,17*mm,192*mm,17*mm)
        c.setFont("DejaVu",7.5)
        c.setFillColor(colors.HexColor("#"+MUTED))
        c.drawString(18*mm,12*mm,"Beyond R² · Beijing PM2.5")
        c.drawRightString(192*mm,12*mm,str(doc.page))
        c.restoreState()

    doc = SimpleDocTemplate(str(OUT/"report.pdf"), pagesize=A4, rightMargin=18*mm,
                            leftMargin=18*mm, topMargin=18*mm, bottomMargin=23*mm,
                            title=TITLE, author="", subject="Regression, ANOVA and model adequacy")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    (OUT/"report.md").write_text("\n".join(markdown), encoding="utf-8")


def slide_elements(slides):
    """Shared point geometry for PDF and editable slides; layouts follow content."""
    all_elements = []
    for i,s in enumerate(slides):
        elements = []

        def rect(x,y,w,h,color):
            elements.append(dict(kind="rect",x=x,y=y,w=w,h=h,color=color))

        def text(value,x,y,w,h,size=22,color=INK,bold=False,url=None):
            item=dict(kind="text",text=value,x=x,y=y,w=w,h=h,size=size,color=color,bold=bold)
            if url:
                item["url"]=url
            elements.append(item)

        def picture(name,x,y,w,h):
            path=FIG/(name+".png")
            with PILImage.open(path) as im:
                iw,ih=im.size
            scale=min(w/iw,h/ih)
            width,height=iw*scale,ih*scale
            elements.append(dict(kind="image",path=str(path.relative_to(ROOT)),
                                 x=x+(w-width)/2,y=y+(h-height)/2,w=width,h=height))

        def tabular(headers,rows,widths,y=142,row_height=54):
            for r,row in enumerate([headers,*rows]):
                x=40
                for j,cell in enumerate(row):
                    rect(x,y+r*row_height,widths[j],row_height,
                         NAVY if r==0 else PALE if r%2 else "FFFFFF")
                    text(str(cell),x+10,y+r*row_height+13,widths[j]-20,row_height-15,
                         16.5 if r==0 else 20,"FFFFFF" if r==0 else INK,r==0)
                    x+=widths[j]

        layout=s["layout"]
        rect(0,0,960,540,"FFFFFF")
        rect(40,23,35,3,TEAL)
        text(s["section"],86,17,820,22,11,TEAL,True)
        text("Beijing PM2.5",40,524,700,14,9,MUTED)
        text(f"{i+1:02d} / {len(slides):02d}",863,524,65,14,9,MUTED)
        if layout=="title":
            text(s["title"],40,96,880,80,52,NAVY,True)
            text(s["subtitle"],43,192,860,117,29,NAVY,True)
            for j,line in enumerate(s["lines"]):
                text(line,44,354+j*38,870,34,20,MUTED)
            text(s["statement"],44,452,870,51,23,TEAL)
            all_elements.append(elements)
            continue

        text(s["title"],40,58,880,70,28 if len(s["title"])>52 else 30,NAVY,True)
        if layout=="questions":
            for j,(heading,body) in enumerate(s["cards"]):
                x=40+j*300
                rect(x,157,280,282,PALE)
                rect(x,157,280,3,TEAL)
                text(heading,x+18,181,244,64,21,NAVY,True)
                text(body,x+18,264,244,149,22)
        elif layout=="timeline":
            for j,(label,dates,eligible,calendar) in enumerate(s["partitions"]):
                x=40+j*300
                rect(x,142,280,196,PALE)
                text(label,x+16,155,248,29,20,NAVY,True)
                text(eligible,x+16,194,248,60,44,TEAL,True)
                text("eligible days / "+calendar+" calendar",x+16,258,248,25,15,MUTED)
                text(dates,x+16,297,248,29,17)
            for j,line in enumerate(s["lines"]):
                text(line,40,367+j*42,880,39,20)
        elif layout=="models":
            tabular(*s["table"],[80,470,160,170])
            text(s["lines"][0],40,392,880,35,18,MUTED)
            text(s["lines"][1],40,440,880,54,20,TEAL)
        elif layout=="inference":
            tabular(*s["table"],[280,120,160,160,160],y=140,row_height=58)
            text(s["equation"],40,340,880,45,18,MUTED)
            text(s["statement"],40,407,880,45,28,TEAL,True)
            text(s["lines"][0],40,462,880,31,21)
            text(s["lines"][1],40,499,880,22,13.5,MUTED)
        elif layout=="figure":
            picture(s["figure"],40,130,880,350)
            text(s["caption"],40,493,880,30,14.5,MUTED)
        elif layout=="evaluation":
            picture(s["figure"],40,130,880,295)
            for j,(label,value) in enumerate(s["metrics"]):
                x=40+j*300
                text(label,x,432,280,24,15.5,MUTED)
                text(value,x,457,280,40,29,TEAL if j<2 else AMBER,True)
            text(s["caption"],40,499,880,24,14,MUTED)
        elif layout=="ar1":
            tabular(*s["table"],[330,130,210,210])
            for j,line in enumerate(s["lines"]):
                text(line,40,383+j*42,880,39,19)
        elif layout=="classification":
            x0,y0,cw,ch=192,178,170,110
            for j,label in enumerate(["Observed high","Observed below"]):
                text(label,x0+j*cw,137,cw,35,17,NAVY,True)
            for j,label in enumerate(["Predicted high","Predicted below"]):
                text(label,40,y0+j*ch+36,139,49,17,NAVY)
            for j,(tag,value) in enumerate(zip(["TP","FP","FN","TN"],s["confusion"])):
                x,y=x0+(j%2)*cw,y0+(j//2)*ch
                rect(x+2,y+2,cw-4,ch-4,"E7F3F1" if j in (0,3) else "FAF0E3")
                text(tag,x+18,y+13,cw-36,22,13,MUTED)
                text(value,x+18,y+41,cw-36,54,40,NAVY,True)
            for j,(label,value) in enumerate(s["metrics"]):
                y=151+j*95
                text(label,650,y,270,28,17,MUTED)
                text(value,650,y+35,270,48,28 if len(value)>10 else 35,TEAL,True)
            text(s["caption"],40,461,880,49,15.5,MUTED)
        elif layout=="clusters":
            picture(s["figure"],24,130,646,367)
            text(s["lines"][0],704,167,216,59,23,TEAL,True)
            for j,line in enumerate(s["lines"][1:]):
                text(line,704,240+j*74,216,65,19)
            text(s["caption"],40,500,880,22,13.5,MUTED)
        elif layout=="limits":
            for j,(heading,body) in enumerate(s["cards"]):
                y=151+j*111
                text(f"0{j+1}",40,y,55,38,26,TEAL,True)
                text(heading,110,y+2,163,64,22,NAVY,True)
                text(body,300,y+2,620,82,22)
        elif layout=="conclusion":
            for j,line in enumerate(s["lines"]):
                y=160+j*114
                rect(41,y+2,4,76,TEAL)
                text(line,69,y,838,94,26,NAVY,j==0)
        elif layout=="references":
            y=139
            for j,(label,url) in enumerate(s["references"],1):
                link=("DOI: "+url.removeprefix("https://doi.org/") if "doi.org/" in url else
                      "Official documentation" if "statsmodels.org" in url else "Dataset documentation")
                value=f"[{j}] {label}\n{link}"
                lines=wrapped_lines(value,"DejaVu",16.5,552)
                height=len(lines)*16.5*1.15+5
                text(value,40,y,552,height,16.5,url=url)
                y+=height+15
            rect(626,142,1,321,"D4DFE6")
            text("AI assistance",657,143,263,35,22,TEAL,True)
            text(s["disclosure"],657,196,263,284,19)
            text("Full references, source tables and reproduction instructions accompany the report.",40,494,880,23,13.5,MUTED)
        else:
            raise ValueError(f"Unknown slide layout: {layout}")
        all_elements.append(elements)
    return all_elements


def wrapped_lines(text, font, size, width):
    lines = []
    for original in text.split("\n"):
        line = ""
        for word in original.split():
            candidate = (line+" "+word).strip()
            if line and pdfmetrics.stringWidth(candidate,font,size)>width:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
    return lines


def build_slides(slides):
    prs = Presentation()
    prs.slide_width, prs.slide_height = Pt(960), Pt(540)
    prs.core_properties.title = TITLE
    prs.core_properties.author = ""
    prs.core_properties.subject = "Multiple regression, ANOVA and residual adequacy"
    pdf = canvas.Canvas(str(OUT/"slides.pdf"), pagesize=(960,540), invariant=1)
    pdf.setTitle(TITLE)
    pdf.setAuthor("")
    elements = slide_elements(slides)
    notes = ["# Presentation speaker notes", "", TITLE, "",
             "Slides use generated analysis tables. Stage 2 is the prespecified core; Stage 3 and the AR(1) sensitivity are exploratory.",""]
    for i,(s,items) in enumerate(zip(slides,elements)):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        slide.notes_slide.notes_text_frame.text = s["notes"]
        notes += [f"## {i+1}. {s['title']}","",s["notes"],""]
        for item in items:
            x,y,w,h = (item[k] for k in ("x","y","w","h"))
            kind = item["kind"]
            if kind=="rect":
                shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,Pt(x),Pt(y),Pt(w),Pt(h))
                shape.fill.solid()
                shape.fill.fore_color.rgb = RGBColor.from_string(item["color"])
                shape.line.fill.background()
                pdf.setFillColor(colors.HexColor("#"+item["color"]))
                pdf.rect(x,540-y-h,w,h,stroke=0,fill=1)
            elif kind=="image":
                slide.shapes.add_picture(str(ROOT/item["path"]),Pt(x),Pt(y),width=Pt(w),height=Pt(h))
                pdf.drawImage(str(ROOT/item["path"]),x,540-y-h,w,h)
            else:
                shape = slide.shapes.add_textbox(Pt(x),Pt(y),Pt(w),Pt(h))
                tf = shape.text_frame
                tf.word_wrap = True
                tf.margin_left=tf.margin_right=tf.margin_top=tf.margin_bottom=0
                font = "DejaVu-Bold" if item["bold"] else "DejaVu"
                size = item["size"]
                lines = wrapped_lines(item["text"],font,size,w)
                if len(lines)*size*1.15 > h+3:
                    raise ValueError(f"Slide {i+1} text exceeds its box: {item['text']}")
                for j,line in enumerate(lines):
                    para = tf.paragraphs[0] if j==0 else tf.add_paragraph()
                    para.text=line
                    para.font.name="DejaVu Sans"
                    para.font.size=Pt(size)
                    para.font.bold=item["bold"]
                    para.font.color.rgb=RGBColor.from_string(item["color"])
                    if item.get("url"):
                        para.runs[0].hyperlink.address=item["url"]
                    para.line_spacing=1.15
                    para.space_after=Pt(0)
                pdf.setFillColor(colors.HexColor("#"+item["color"]))
                pdf.setFont(font,size)
                for j,line in enumerate(lines):
                    pdf.drawString(x,540-y-size-j*size*1.15,line)
                if item.get("url"):
                    pdf.linkURL(item["url"],(x,540-y-h,x+w,540-y),relative=0)
        pdf.showPage()
    pdf.save()
    prs.save(str(OUT/"slides.pptx"))
    (OUT/"speaker_notes.md").write_text("\n".join(notes),encoding="utf-8")
    (OUT/"slide_content.json").write_text(json.dumps({"title":TITLE,
             "slides":slides,"elements":elements},indent=2,ensure_ascii=False)+"\n",encoding="utf-8")


def main():
    FIG.mkdir(parents=True,exist_ok=True)
    setup_fonts()
    figures()
    pages,slides = content()
    build_report(pages)
    build_slides(slides)
    for name in ("scripts/build_submission.py","scripts/check_submission.py","requirements.lock", "requirements-submission.lock"):
        source(name)
    outputs = ["submission/report.md","submission/report.pdf","submission/slides.pdf",
               "submission/slides.pptx","submission/speaker_notes.md","submission/slide_content.json"]
    outputs += [str(p.relative_to(ROOT)) for p in sorted(FIG.glob("*.png"))]
    manifest = {"title":TITLE,"neutral_title_pages":True,"references":REFS,
                "stage2_frozen_model":frozen_reference(), "stage3_is_exploratory":True,
                "input_sha256":INPUTS,"output_sha256":{p:sha(ROOT/p) for p in outputs},
                "numerical_claims":list(CLAIMS.values()),"slide_count":len(slides),
                "environment":{n:importlib.metadata.version(n) for n in
                               ("numpy","pandas","matplotlib","scipy","reportlab","python-pptx","PyMuPDF")},
                "rendering_note":"PDF slides are directly rendered from the same content and geometry as PPTX. Native PowerPoint rendering requires an Office-compatible viewer and is not asserted by this build."}
    (OUT/"build_manifest.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(f"Built report, {len(slides)} slides, notes and {len(CLAIMS)} source-linked numerical claims in submission/.")


def frozen_reference():
    return {"source":"results/stage2/frozen_model.json", "sha256":sha(ROOT/"results/stage2/frozen_model.json"),
            "retuned":False,"test_refitted":False,"negative_estimates_clipped":False}


if __name__=="__main__":
    main()
