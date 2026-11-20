"""Standalone scientific figures from training observations only."""

import os
from pathlib import Path

import numpy as np
import pandas as pd

from .config import CORE_VARIABLES, Stage1Config


def make_figures(project_root: Path, daily, ranking, missingness, acf, config: Stage1Config):
    # Keep all cache writes inside the project, including in a headless sandbox.
    os.environ.setdefault("MPLCONFIGDIR", str(project_root / ".mplconfig"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    destination = project_root / "results" / "figures"
    destination.mkdir(parents=True, exist_ok=True)
    outputs = []
    training = daily.loc[daily["split"].eq("train")]
    eligible = training.loc[training["analysis_eligible"]]
    station = str(daily["station"].iloc[0])

    def save(fig, name):
        for extension in ("png", "svg"):
            path = destination / f"{name}.{extension}"
            fig.savefig(path, dpi=180, bbox_inches="tight", metadata={"Creator": "Beijing PM2.5 Stage 1"})
            outputs.append(path)
        plt.close(fig)

    with plt.rc_context({"font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.titlepad": 12}):
        fig, ax = plt.subplots(figsize=(9, 5.5), layout="constrained")
        ordered = ranking.iloc[::-1]
        colours = ["#166b8c" if item == station else "#a9b9c3" for item in ordered["station"]]
        bars = ax.barh(ordered["station"], ordered["training_analysis_days"], color=colours)
        ax.bar_label(bars, padding=4, fontsize=9)
        ax.set_xlim(0, max(len(training), int(ordered["training_analysis_days"].max())) * 1.12)
        ax.set_xlabel("Eligible training days")
        ax.set_title("Station selection by training completeness")
        ax.grid(axis="x", alpha=0.15)
        ax.set_axisbelow(True)
        save(fig, "station_training_completeness")

        missing = missingness.loc[
            missingness["scope"].eq("train") & missingness["variable"].isin(CORE_VARIABLES)
        ].pivot(index="station", columns="variable", values="unusable_fraction")
        missing = missing.reindex(index=ranking["station"], columns=list(CORE_VARIABLES)) * 100
        fig, ax = plt.subplots(figsize=(8.5, 6), layout="constrained")
        colour = ax.imshow(missing.to_numpy(), cmap="YlOrRd", aspect="auto",
                           vmin=0, vmax=max(1.0, float(missing.to_numpy().max())))
        ax.set_xticks(range(len(missing.columns)), missing.columns)
        ax.set_yticks(range(len(missing)), missing.index)
        for y in range(len(missing)):
            for x in range(len(missing.columns)):
                value = missing.iloc[y, x]
                label = "<0.1%" if 0 < value < 0.1 else f"{value:.1f}%"
                ax.text(x, y, label, ha="center", va="center", fontsize=9,
                        color="white" if value > colour.get_clim()[1] * 0.6 else "black")
        fig.colorbar(colour, ax=ax, label="Unusable hourly values (%)")
        ax.set_title("Missing or invalid values in the training interval")
        save(fig, "hourly_training_missingness")

        fig, axes = plt.subplots(2, 1, figsize=(10, 5.8), sharex=True,
                                 height_ratios=(3, 1), layout="constrained")
        axes[0].plot(training.index, training["pm25"], lw=0.85, color="#166b8c")
        axes[0].set_ylabel("Daily PM2.5 (µg/m³)")
        axes[0].set_title(f"{station}: daily response in the training interval")
        axes[1].plot(training.index, training["n_pm25"], lw=0.8, color="#536b78")
        axes[1].axhline(config.min_valid_hours, color="#b35425", ls="--", lw=1,
                       label=f"{config.min_valid_hours}-hour minimum")
        axes[1].set_ylim(-0.5, 25)
        axes[1].set_ylabel("Valid hours")
        axes[1].set_xlabel("Local civil date (timezone assumed; no conversion)")
        axes[1].legend(loc="lower right", fontsize=8)
        for axis in axes:
            axis.grid(alpha=0.15)
        save(fig, "training_daily_series")

        fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout="constrained")
        values = eligible["pm25"]
        axes[0].hist(values, bins=30, color="#166b8c", edgecolor="white")
        axes[0].set_xlabel("Daily PM2.5 (µg/m³)")
        axes[1].hist(np.log1p(values), bins=30, color="#418b72", edgecolor="white")
        axes[1].set_xlabel("log(1 + daily PM2.5)")
        for axis in axes:
            axis.set_ylabel("Training days")
        fig.suptitle(f"{station}: response distributions (n = {len(values)} eligible training days)\n"
                     "Descriptive comparison; a model response scale has not been chosen", fontsize=11)
        save(fig, "training_response_distribution")

        seasons = ["winter", "spring", "summer", "autumn"]
        samples = [eligible.loc[eligible["season"].eq(season), "pm25"].to_numpy() for season in seasons]
        labels = [f"{season.title()}\nn = {len(sample)}" for season, sample in zip(seasons, samples)]
        fig, ax = plt.subplots(figsize=(8, 4.5), layout="constrained")
        ax.boxplot(samples, tick_labels=labels, showfliers=True,
                   medianprops={"color": "#b35425", "linewidth": 1.5})
        ax.set_ylabel("Daily PM2.5 (µg/m³)")
        ax.set_title(f"{station}: seasonal distributions in eligible training days")
        ax.grid(axis="y", alpha=0.15)
        save(fig, "training_seasonal_distribution")

        fig, ax = plt.subplots(figsize=(8.5, 4), layout="constrained")
        ax.axhline(0, color="#5a6670", lw=0.8)
        ax.vlines(acf["lag_days"], 0, acf["correlation"], color="#166b8c", lw=1.5)
        ax.scatter(acf["lag_days"], acf["correlation"], color="#166b8c", s=18)
        ax.set_ylim(-1.05, 1.05)
        ax.set_xlabel("Calendar-day lag")
        ax.set_ylabel("Paired-day correlation")
        ax.set_title(f"{station}: descriptive training response autocorrelation\n"
                     "Missing dates retained; no independence test or confidence bands", fontsize=11)
        save(fig, "training_calendar_acf")
    return outputs
