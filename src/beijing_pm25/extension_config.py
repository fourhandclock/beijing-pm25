"""Stage 3 settings. Stage 3 is exploratory: the test year was already scored in Stage 2."""

from dataclasses import asdict, dataclass
import json
from pathlib import Path

from .config import NUMERIC_VARIABLES


@dataclass(frozen=True)
class Stage3Config:
    primary_station: str = "Wanliu"
    min_valid_hours: int = 18
    primary_hac_lag_days: int = 7
    alpha: float = 0.05
    extreme_training_quantile: float = 0.95
    cluster_variables: tuple[str, ...] = ("PM2.5", "PM10", "SO2", "NO2", "CO", "O3")
    cluster_k_range: tuple[int, int] = (2, 5)

    def __post_init__(self):
        if not self.primary_station.isalnum():
            raise ValueError("primary_station must be an alphanumeric UCI station name.")
        if type(self.min_valid_hours) is not int or not 1 <= self.min_valid_hours <= 24:
            raise ValueError("min_valid_hours must be an integer between 1 and 24.")
        if type(self.primary_hac_lag_days) is not int or not 1 <= self.primary_hac_lag_days <= 90:
            raise ValueError("primary_hac_lag_days must be an integer between 1 and 90.")
        if not 0 < self.alpha < 1 or not 0.5 < self.extreme_training_quantile < 1:
            raise ValueError("alpha must lie in (0, 1) and the extreme quantile in (0.5, 1).")
        if not self.cluster_variables or not set(self.cluster_variables) <= set(NUMERIC_VARIABLES):
            raise ValueError("cluster_variables must be UCI numeric columns.")
        low, high = self.cluster_k_range
        if not 2 <= low <= high <= 11:
            raise ValueError("cluster_k_range must satisfy 2 <= low <= high <= 11.")

    def as_dict(self):
        values = asdict(self)
        values["cluster_variables"] = list(self.cluster_variables)
        values["cluster_k_range"] = list(self.cluster_k_range)
        return values

    @classmethod
    def read(cls, path: Path):
        if not path.is_file():
            raise ValueError(f"Configuration not found: {path}")
        values = json.loads(path.read_text(encoding="utf-8"))
        for key in ("cluster_variables", "cluster_k_range"):
            if key in values:
                values[key] = tuple(values[key])
        return cls(**values)
