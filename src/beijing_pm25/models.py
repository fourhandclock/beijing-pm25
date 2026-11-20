"""Common-sample OLS, training-only centering, and validation-only selection."""

from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm

from .model_config import Stage2Config


WEATHER = ("temperature", "wind_speed", "rainfall", "pressure")
SEASONS = ("winter", "spring", "summer", "autumn")
MODELS = ("M1", "M2", "M3")


def design_matrix(frame, centers, model):
    if model not in MODELS:
        raise ValueError(f"Unknown model: {model}")
    if not frame["season"].isin(SEASONS).all():
        raise ValueError("Unexpected season label in model data.")
    design = pd.DataFrame({"Intercept": 1.0}, index=frame.index)
    for name in WEATHER:
        design[name + "_c"] = frame[name].astype(float) - centers[name]
    if model != "M1":
        for season in SEASONS[1:]:
            design["season_" + season] = frame["season"].eq(season).astype(float)
    if model == "M3":
        for season in SEASONS[1:]:
            design["wind_x_" + season] = design["wind_speed_c"] * design["season_" + season]
    if not np.isfinite(design.to_numpy()).all():
        raise ValueError("Model inputs must be finite complete observations.")
    return design


def _require_partition(frame, expected):
    if frame.empty or not frame["split"].eq(expected).all():
        raise ValueError(f"Expected a nonempty {expected}-only partition.")
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError("Model observations must have unique, increasing daily dates.")
    if not frame.index.equals(frame.index.normalize()):
        raise ValueError("Model timestamps must be daily civil dates.")
    if not np.isfinite(frame["pm25"]).all() or frame["pm25"].lt(0).any():
        raise ValueError("The original-scale response must be finite and nonnegative.")
    if "analysis_eligible" in frame and not frame["analysis_eligible"].all():
        raise ValueError("Only the declared analysis-eligible observations can enter a model.")


def fit_candidates(training):
    _require_partition(training, "train")
    centers = {name: float(training[name].mean()) for name in WEATHER}
    fitted = {}
    for name in MODELS:
        design = design_matrix(training, centers, name)
        n, p = design.shape
        if n <= p or np.linalg.matrix_rank(design.to_numpy()) != p:
            raise ValueError(f"{name} has an insufficient or rank-deficient training design.")
        fitted[name] = sm.OLS(training["pm25"].astype(float), design, missing="raise").fit()
    return fitted, centers


def prediction_rows(frame, model_name, values, threshold):
    predicted = np.asarray(values, dtype=float)
    if predicted.shape != (len(frame),) or not np.isfinite(predicted).all():
        raise ValueError("Predictions must be finite and match the evaluation dates.")
    observed = frame["pm25"].to_numpy(dtype=float)
    return pd.DataFrame({
        "date": frame.index, "split": frame["split"].to_numpy(), "model": model_name,
        "season": frame["season"].to_numpy(), "observed": observed,
        "predicted": predicted, "signed_error": predicted - observed,
        "high_pollution_day": observed >= threshold,
    })


def score_predictions(predictions):
    rows = []
    for (split, model), group in predictions.groupby(["split", "model"], sort=False):
        for subgroup, part in (("all", group),
                               ("high", group.loc[group["high_pollution_day"]]),
                               ("below_cutoff", group.loc[~group["high_pollution_day"]])):
            error = part["signed_error"].to_numpy()
            rows.append({
                "split": split, "model": model, "subgroup": subgroup, "n": len(part),
                "mae": float(np.abs(error).mean()) if len(part) else np.nan,
                "rmse": float(np.sqrt(np.mean(error ** 2))) if len(part) else np.nan,
                "mean_signed_error": float(error.mean()) if len(part) else np.nan,
                "mean_observed": part["observed"].mean(), "mean_predicted": part["predicted"].mean(),
                "negative_predictions": int(part["predicted"].lt(0).sum()),
            })
    return pd.DataFrame(rows)


def choose_validation_model(validation_scores, parameter_counts, tolerance_fraction=0.01):
    if not validation_scores["split"].eq("validation").all():
        raise ValueError("Model selection accepts validation scores only.")
    table = validation_scores.loc[
        validation_scores["subgroup"].eq("all") & validation_scores["model"].isin(MODELS)
    ].copy()
    if set(table["model"]) != set(MODELS) or len(table) != 3 or not np.isfinite(table["mae"]).all():
        raise ValueError("Selection needs one finite overall validation MAE for each candidate.")
    if table["n"].nunique() != 1:
        raise ValueError("Compare validation models on an identical sample.")
    table["parameters"] = table["model"].map(parameter_counts)
    limit = float(table["mae"].min()) * (1 + tolerance_fraction)
    table["within_simplicity_band"] = table["mae"].le(limit + 1e-12)
    eligible = table.loc[table["within_simplicity_band"]].sort_values(["parameters", "mae", "model"])
    chosen = str(eligible.iloc[0]["model"])
    table["selected"] = table["model"].eq(chosen)
    return chosen, table.sort_values("model").reset_index(drop=True)


@dataclass
class Development:
    models: dict
    centers: dict
    threshold: float
    training_mean: float
    selected_model: str
    selection: pd.DataFrame
    predictions: pd.DataFrame


def develop_models(training, validation, config: Stage2Config):
    """Deliberately has no test-data argument."""
    _require_partition(validation, "validation")
    _require_partition(training, "train")
    if training.index.max() >= validation.index.min():
        raise ValueError("Training must strictly precede validation.")
    fitted, centers = fit_candidates(training)
    threshold = float(training["pm25"].quantile(config.extreme_training_quantile))
    baseline = float(training["pm25"].mean())
    predictions = []
    for frame in (training, validation):
        for name, result in fitted.items():
            values = result.predict(design_matrix(frame, centers, name))
            predictions.append(prediction_rows(frame, name, values, threshold))
        predictions.append(prediction_rows(frame, "training_mean", np.full(len(frame), baseline), threshold))
    predictions = pd.concat(predictions, ignore_index=True)
    scores = score_predictions(predictions.loc[predictions["split"].eq("validation")])
    chosen, selection = choose_validation_model(
        scores, {name: len(result.params) for name, result in fitted.items()},
        config.simplicity_tolerance_fraction,
    )
    return Development(fitted, centers, threshold, baseline, chosen, selection, predictions)


def frozen_specification(development: Development, config: Stage2Config):
    result = development.models[development.selected_model]
    return {
        "selected_model": development.selected_model, "response_scale": config.response_scale,
        "coefficients": {key: float(value) for key, value in result.params.items()},
        "columns": list(result.params.index), "training_centers": development.centers,
        "training_mean_baseline": development.training_mean,
        "high_pollution_training_cutoff": development.threshold,
        "high_pollution_quantile": config.extreme_training_quantile,
        "high_pollution_rule": "observed daily PM2.5 >= eligible training quantile",
        "training_observations": int(result.nobs),
        "training_first_fitted_date": result.model.data.row_labels.min().date().isoformat(),
        "training_last_fitted_date": result.model.data.row_labels.max().date().isoformat(),
        "configuration": config.as_dict(),
        "selection_rule": f"Lowest validation MAE, preferring fewer parameters within {100 * config.simplicity_tolerance_fraction:g}% of the best",
        "test_used_for_selection": False, "refitted_on_validation": False,
        "negative_predictions_clipped": False,
    }


def evaluate_frozen(test, frozen):
    _require_partition(test, "test")
    if test.index.min() <= pd.Timestamp(frozen["training_last_fitted_date"]):
        raise ValueError("Final evaluation must follow all fitted observations.")
    name = frozen["selected_model"]
    design = design_matrix(test, frozen["training_centers"], name)
    if list(design.columns) != frozen["columns"]:
        raise ValueError("Frozen coefficient/design columns disagree.")
    coefficients = np.array([frozen["coefficients"][column] for column in design.columns])
    threshold = frozen["high_pollution_training_cutoff"]
    return pd.concat([
        prediction_rows(test, name, design.to_numpy() @ coefficients, threshold),
        prediction_rows(test, "training_mean", np.full(len(test), frozen["training_mean_baseline"]), threshold),
    ], ignore_index=True)
