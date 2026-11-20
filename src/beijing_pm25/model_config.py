"""The Stage 2 protocol is declared before fitting, never inferred from test scores."""

from dataclasses import asdict, dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class Stage2Config:
    response_scale: str = "original"
    reference_season: str = "winter"
    primary_hac_lag_days: int = 7
    hac_lag_days: tuple[int, ...] = (7, 14, 30)
    serial_test_lag_days: int = 7
    residual_acf_lag_days: int = 30
    alpha: float = 0.05
    selection_metric: str = "mae"
    simplicity_tolerance_fraction: float = 0.01
    extreme_training_quantile: float = 0.95

    def __post_init__(self):
        if self.response_scale != "original" or self.reference_season != "winter":
            raise ValueError("This stage implements the declared original-scale response and winter reference only.")
        if self.selection_metric != "mae":
            raise ValueError("The declared selection metric is validation MAE.")
        if not self.hac_lag_days or len(set(self.hac_lag_days)) != len(self.hac_lag_days):
            raise ValueError("Specify distinct HAC calendar-day lags.")
        for lag in (*self.hac_lag_days, self.primary_hac_lag_days,
                    self.serial_test_lag_days, self.residual_acf_lag_days):
            if type(lag) is not int or not 1 <= lag <= 90:
                raise ValueError("All lag counts must be integers between 1 and 90 days.")
        if self.primary_hac_lag_days not in self.hac_lag_days:
            raise ValueError("The primary HAC lag must be included among the covariance lags.")
        if not 0 < self.alpha < 1:
            raise ValueError("alpha must lie between zero and one.")
        if not 0 <= self.simplicity_tolerance_fraction <= 0.1:
            raise ValueError("The relative simplicity tolerance must lie between 0 and 0.1.")
        if not 0.5 < self.extreme_training_quantile < 1:
            raise ValueError("The high-response training quantile must lie between 0.5 and 1.")

    def as_dict(self):
        values = asdict(self)
        values["hac_lag_days"] = list(values["hac_lag_days"])
        return values

    @classmethod
    def read(cls, path: Path):
        values = json.loads(path.read_text(encoding="utf-8"))
        if "hac_lag_days" in values:
            values["hac_lag_days"] = tuple(values["hac_lag_days"])
        return cls(**values)
