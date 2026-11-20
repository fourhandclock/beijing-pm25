"""Training diagnostics, validation comparison, and the frozen test evaluation."""

import os

import numpy as np
import pandas as pd
from scipy import stats


def make_model_figures(root, training, development, influences, acf, residual_calendar,
                       slopes, test_predictions, config):
    os.environ.setdefault("MPLCONFIGDIR", str(root / ".mplconfig"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    destination = root / "results" / "stage2" / "figures"
    destination.mkdir(parents=True, exist_ok=True)
    outputs = []
    colours = {"M1": "#166b8c", "M2": "#bc672f", "M3": "#40836e"}

    def save(fig, name):
        for extension in ("png", "svg"):
            path = destination / f"{name}.{extension}"
            fig.savefig(path, dpi=180, bbox_inches="tight", metadata={"Creator": "Beijing PM2.5 Stage 2"})
            outputs.append(path)
        plt.close(fig)

    with plt.rc_context({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.titlepad": 12}):
        columns = ["pm25", "temperature", "wind_speed", "rainfall", "pressure"]
        labels = ["PM2.5", "Temperature", "Wind speed", "Rainfall", "Pressure"]
        correlation = training[columns].corr()
        fig, ax = plt.subplots(figsize=(7, 6), layout="constrained")
        colour = ax.imshow(correlation, vmin=-1, vmax=1, cmap="RdBu_r")
        ax.set_xticks(range(5), labels, rotation=30, ha="right")
        ax.set_yticks(range(5), labels)
        for y in range(5):
            for x in range(5):
                value = correlation.iloc[y, x]
                ax.text(x, y, f"{value:.2f}", ha="center", va="center",
                        color="white" if abs(value) > 0.65 else "black")
        fig.colorbar(colour, ax=ax, label="Pearson correlation")
        ax.set_title("Eligible training days: marginal correlations\nConditional regression associations can differ", fontsize=11)
        save(fig, "training_correlations")

        for name, result in development.models.items():
            part = influences.loc[influences["model"].eq(name)]
            fig, axes = plt.subplots(2, 2, figsize=(11, 7.5), layout="constrained")
            axes[0, 0].scatter(part["fitted"], part["residual"], s=12, alpha=0.45, color=colours[name])
            axes[0, 0].axhline(0, color="#777777", lw=0.8)
            axes[0, 0].set(xlabel="Fitted PM2.5 (µg/m³)", ylabel="Residual (observed − fitted)", title="Residual versus fitted")
            theoretical, ordered = stats.probplot(part["internally_studentized_residual"], fit=False)
            axes[0, 1].scatter(theoretical, ordered, s=12, alpha=0.65, color=colours[name])
            limit = [min(theoretical), max(theoretical)]
            axes[0, 1].plot(limit, limit, ls="--", color="#777777", lw=1)
            axes[0, 1].set(xlabel="Standard-normal theoretical quantile", ylabel="Internally studentized residual",
                           title="Normal Q–Q (reference line y = x)")
            axes[1, 0].scatter(part["fitted"], np.sqrt(np.abs(part["internally_studentized_residual"])),
                               s=12, alpha=0.45, color=colours[name])
            axes[1, 0].set(xlabel="Fitted PM2.5 (µg/m³)", ylabel="√|internally studentized residual|", title="Scale–location")
            axes[1, 1].vlines(part["date"], 0, part["cooks_distance"], color=colours[name], lw=0.9)
            axes[1, 1].axhline(4 / len(part), color="#b35425", ls="--", label="4/n screening guide")
            axes[1, 1].set(xlabel="Training date", ylabel="Cook's distance", title="Influence: observations retained")
            axes[1, 1].tick_params(axis="x", rotation=20, labelsize=8)
            axes[1, 1].legend(fontsize=8)
            fig.suptitle(f"{name}: training residual diagnostics (n = {len(part)})", fontsize=13)
            save(fig, f"{name.lower()}_residual_diagnostics")

        fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True, layout="constrained")
        for ax, (name, part) in zip(axes, residual_calendar.groupby("model", sort=True)):
            ax.plot(part["date"], part["residual"], color=colours[name], lw=0.8)
            ax.axhline(0, color="#777777", lw=0.8)
            ax.set_ylabel(f"{name} residual\n(µg/m³)")
            ax.grid(alpha=0.15)
        axes[0].set_title("Training residual time series on the full daily calendar")
        axes[-1].set_xlabel("Local civil date; gaps remain missing")
        save(fig, "training_residual_time_series")

        fig, axes = plt.subplots(1, 3, figsize=(12, 3.8), sharey=True, layout="constrained")
        for ax, (name, part) in zip(axes, acf.groupby("model", sort=True)):
            ax.axhline(0, color="#777777", lw=0.8)
            ax.vlines(part["lag_days"], 0, part["correlation"], color=colours[name])
            ax.scatter(part["lag_days"], part["correlation"], color=colours[name], s=12)
            ax.set(title=name, xlabel="Calendar-day lag", ylim=(-1, 1))
        axes[0].set_ylabel("Paired residual correlation")
        fig.suptitle("Training residual ACF: missing dates retained; descriptive, without white-noise bands", fontsize=11)
        save(fig, "training_residual_acf")

        fig, ax = plt.subplots(figsize=(8, 4.5), layout="constrained")
        y = np.arange(len(slopes))
        values = slopes["pm25_change_per_1_mps_wind"]
        ax.errorbar(values, y, xerr=np.vstack([values - slopes["hac_ci_lower"], slopes["hac_ci_upper"] - values]),
                    fmt="o", color=colours["M3"], capsize=4)
        ax.axvline(0, color="#777777", ls="--", lw=0.9)
        ax.set_yticks(y, slopes["season"].str.title())
        ax.invert_yaxis()
        ax.set_xlabel("Adjusted PM2.5 change (µg/m³) per 1 m/s higher wind speed")
        ax.set_title(f"M3 seasonal wind associations\n{100 * (1 - config.alpha):g}% individual HAC intervals, {config.primary_hac_lag_days}-day bandwidth")
        save(fig, "m3_seasonal_wind_associations")

        selection = development.selection
        fig, ax = plt.subplots(figsize=(7.5, 4), layout="constrained")
        bars = ax.bar(selection["model"], selection["mae"], color=[
            "#166b8c" if selected else "#b4c1ca" for selected in selection["selected"]
        ])
        ax.bar_label(bars, fmt="%.2f", padding=4)
        ax.set_ylim(0, float(selection["mae"].max()) * 1.18)
        ax.set_ylabel("Validation MAE (µg/m³)")
        ax.set_title(f"Validation-only selection: {development.selected_model}\nSimpler models preferred within {100 * config.simplicity_tolerance_fraction:g}% of minimum MAE", fontsize=11)
        save(fig, "validation_model_comparison")

        chosen = test_predictions.loc[test_predictions["model"].eq(development.selected_model)]
        grid = pd.date_range(chosen["date"].min(), chosen["date"].max(), freq="D")
        calendar = chosen.set_index("date").reindex(grid)
        fig, axes = plt.subplots(2, 1, figsize=(10.5, 7.5), layout="constrained")
        axes[0].plot(calendar.index, calendar["observed"], lw=1, color="#333333", label="Observed")
        axes[0].plot(calendar.index, calendar["predicted"], lw=1, color="#166b8c", label=f"Frozen {development.selected_model}")
        axes[0].axhline(development.training_mean, ls="--", lw=0.9, color="#bc672f", label="Training mean baseline")
        axes[0].axhline(development.threshold, ls=":", lw=0.9, color="#8d6888", label="Training daily 95th percentile")
        axes[0].set(ylabel="Daily PM2.5 (µg/m³)", title="Final chronological test: contemporaneous estimates")
        axes[0].legend(ncol=2, fontsize=8)
        axes[1].scatter(chosen["observed"], chosen["predicted"], s=16, alpha=0.5, color="#166b8c")
        limit = [min(0.0, float(chosen["predicted"].min())), max(float(chosen["observed"].max()), float(chosen["predicted"].max()))]
        axes[1].plot(limit, limit, ls="--", color="#777777", lw=1)
        axes[1].set(xlabel="Observed PM2.5 (µg/m³)", ylabel="Frozen estimate (µg/m³)", title="Observed versus estimated; diagonal is perfect agreement")
        save(fig, "frozen_test_estimates")
    return outputs
