"""Declared time boundaries and completeness decisions, fixed before inspection."""

from dataclasses import asdict, dataclass
from datetime import date
import json
from pathlib import Path


@dataclass(frozen=True)
class Stage1Config:
    calendar_start: str = "2013-03-01"
    train_end_exclusive: str = "2015-03-01"
    validation_end_exclusive: str = "2016-03-01"
    calendar_end_exclusive: str = "2017-03-01"
    min_valid_hours: int = 18
    station: str = "auto"
    max_acf_lag: int = 30

    def __post_init__(self):
        bounds = [date.fromisoformat(value) for value in (
            self.calendar_start, self.train_end_exclusive,
            self.validation_end_exclusive, self.calendar_end_exclusive,
        )]
        if not all(left < right for left, right in zip(bounds, bounds[1:])):
            raise ValueError("Calendar and split boundaries must be strictly increasing.")
        if type(self.min_valid_hours) is not int or not 1 <= self.min_valid_hours <= 24:
            raise ValueError("min_valid_hours must be an integer between 1 and 24.")
        if type(self.max_acf_lag) is not int or not 1 <= self.max_acf_lag <= 90:
            raise ValueError("max_acf_lag must be an integer between 1 and 90.")
        if not self.station or (self.station != "auto" and not self.station.isalnum()):
            raise ValueError("station must be 'auto' or an alphanumeric UCI station name.")

    def as_dict(self):
        return asdict(self)

    @classmethod
    def read(cls, path: Path):
        if not path.is_file():
            raise ValueError(f"Configuration not found: {path}")
        return cls(**json.loads(path.read_text(encoding="utf-8")))


# Means use each variable's valid hours. Rainfall is a TOTAL and always needs all
# 24 hours; a partial sum is never substituted for a complete daily total.
MEAN_VARIABLES = {
    "PM2.5": "pm25",
    "TEMP": "temperature",
    "PRES": "pressure",
    "WSPM": "wind_speed",
}
CORE_VARIABLES = (*MEAN_VARIABLES, "RAIN")
NUMERIC_VARIABLES = (
    "PM2.5", "PM10", "SO2", "NO2", "CO", "O3",
    "TEMP", "PRES", "DEWP", "RAIN", "WSPM",
)
UNITS = {
    "pm25": "ug/m^3", "temperature": "degrees C", "pressure": "hPa",
    "wind_speed": "m/s", "rainfall": "mm/day",
}
SEASONS = {
    12: "winter", 1: "winter", 2: "winter",
    3: "spring", 4: "spring", 5: "spring",
    6: "summer", 7: "summer", 8: "summer",
    9: "autumn", 10: "autumn", 11: "autumn",
}
