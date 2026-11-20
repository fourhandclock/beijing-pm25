"""Training-only descriptive statistics; never fit or select a response model."""

import numpy as np
import pandas as pd


def response_summary(training_hourly: pd.Series, training_daily: pd.DataFrame):
    subsets = {
        "hourly_training": training_hourly,
        "daily_pm25_qualified_training": training_daily["pm25"],
        "daily_analysis_eligible_training": training_daily.loc[training_daily["analysis_eligible"], "pm25"],
    }
    rows = []
    for subset, values in subsets.items():
        valid = values.dropna()
        for scale, sample in (("original", valid), ("log1p", np.log1p(valid))):
            row = {
                "subset": subset, "scale": scale, "n": len(sample),
                "mean": sample.mean(), "std": sample.std(ddof=1),
                "skewness": sample.skew(), "min": sample.min(), "max": sample.max(),
            }
            for quantile in (0.01, 0.05, 0.25, 0.50, 0.75, 0.95, 0.99):
                row[f"q{round(quantile * 100):02d}"] = sample.quantile(quantile)
            rows.append(row)
    return pd.DataFrame(rows)


def calendar_acf(daily_pm25: pd.Series, max_lag=30):
    """Pairwise descriptive correlations at calendar-day lags, keeping gaps.

    Unlike dropping missing days before an ACF, shift() on the complete daily
    calendar cannot turn adjacent observed records into adjacent calendar days.
    No white-noise confidence intervals or significance tests are asserted.
    """
    if not isinstance(daily_pm25.index, pd.DatetimeIndex):
        raise ValueError("ACF input must have a complete, unique daily DatetimeIndex.")
    expected = pd.date_range(daily_pm25.index.min(), daily_pm25.index.max(), freq="D")
    if not daily_pm25.index.equals(expected):
        raise ValueError("ACF input must retain every calendar day, including missing days.")
    rows = []
    for lag in range(1, max_lag + 1):
        previous = daily_pm25.shift(lag)
        paired = pd.concat([daily_pm25, previous], axis=1).dropna()
        correlation = float("nan")
        if len(paired) >= 3 and (paired.std(ddof=1) > 0).all():
            correlation = float(np.corrcoef(paired.iloc[:, 0], paired.iloc[:, 1])[0, 1])
        rows.append({"lag_days": lag, "paired_days": len(paired), "correlation": correlation})
    return pd.DataFrame(rows)
