"""Retain the original GLSAR result and audit actual calendar-day spacings.

The paired sensitivity changes only spacing under the same conditional Gaussian
likelihood. This is a training-only correctness audit, not a forecasting extension.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import linalg

from beijing_pm25.ar1_audit import calendar_sensitivity
from stage4_reference import WEATHER, design


ROOT = Path(__file__).resolve().parents[1]


def main():
    daily = pd.read_csv(ROOT/"data/processed/Wanliu_daily.csv", parse_dates=["date"]).set_index("date")
    training = daily.loc[daily["split"].eq("train") & daily["analysis_eligible"]]
    legacy = pd.read_csv(ROOT/"results/stage3/tables/ar1_error_tests.csv")
    alpha = json.loads((ROOT/"config/stage3.json").read_text())["alpha"]
    table = calendar_sensitivity(training, alpha, legacy)
    records = training.reset_index().to_dict(orient="records")
    centers = {name: float(training[name].mean()) for name in WEATHER}
    actual_times = (training.index-training.index[0]).days.to_numpy()
    target = training["pm25"].to_numpy()
    checks = []
    for row in table.loc[table["method"].ne("original_glsar_rows")].to_dict(orient="records"):
        x, _ = design(records, centers, row["model"])
        times = actual_times if row["method"].endswith("calendar") else np.arange(len(training))
        t, rho = times[1:], row["rho"]
        conditional = (rho**np.abs(t[:, None]-t[None, :])-rho**(t[:, None]+t[None, :]))/(1-rho*rho)
        z = x[1:]-(rho**t)[:, None]*x[0]
        y = target[1:]-rho**t*target[0]
        factor = linalg.cho_factor(conditional, lower=True)
        bread = linalg.inv(z.T@linalg.cho_solve(factor, z))
        beta = bread@(z.T@linalg.cho_solve(factor, y))
        error = y-z@beta
        sse = float(error@linalg.cho_solve(factor, error))
        objective = len(t)*np.log(sse/len(t))+2*np.log(np.diag(factor[0])).sum()
        np.testing.assert_allclose(objective, row["conditional_profile_objective"], rtol=1e-10)
        wind = 2  # Intercept, temperature_c, wind_speed_c, rainfall_c, pressure_c.
        np.testing.assert_allclose(beta[wind], row["wind_coefficient"], rtol=1e-9, atol=1e-9)
        checks.append({"method": row["method"], "model": row["model"],
                       "dense_objective_difference": float(objective-row["conditional_profile_objective"]),
                       "dense_wind_coefficient_difference": float(beta[wind]-row["wind_coefficient"])})
    folder = ROOT/"results/stage4/tables"
    folder.mkdir(parents=True, exist_ok=True)
    table.to_csv(folder/"ar1_calendar_sensitivity.csv", index=False, float_format="%.15g")
    decisions = table.pivot(index="hypothesis", columns="method", values="p_value_approx").lt(alpha)
    consistency = bool(decisions.nunique(axis=1).eq(1).all())
    report = {"status": "passed", "training_only": True, "original_glsar_retained": True,
              "conditional_first_observation_treatment_equal": True,
              "qualitative_nominal_decisions_agree": consistency,
              "legacy_and_sensitivity_are_exploratory": True,
              "rho_uncertainty_in_nominal_F_not_fully_accounted_for": True,
              "dense_conditional_covariance_checks": checks,
              "rows": json.loads(table.to_json(orient="records"))}
    destination = ROOT/"reports/verification"
    destination.mkdir(parents=True, exist_ok=True)
    (destination/"ar1_calendar_check.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
    print(table[["method", "model", "rho", "p_value_approx", "p_holm_within_method", "calendar_gaps"]].to_string(index=False))
    print("Nominal decisions unchanged across methods:", consistency)


if __name__ == "__main__":
    main()
