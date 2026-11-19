"""The six islands: one point each (roughly the island's centre), used for the weather
history and, through the dbt seed `seeds/islands.csv`, for the storm passages."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Island:
    name: str
    lat: float
    lon: float


ISLANDS: tuple[Island, ...] = (
    Island("Guadeloupe", 16.25, -61.55),
    Island("Martinique", 14.64, -61.02),
    Island("Saint-Barthelemy", 17.90, -62.83),
    Island("Saint-Martin", 18.07, -63.06),
    Island("Dominica", 15.42, -61.35),
    Island("Saint Lucia", 13.91, -60.98),
)
