"""What the consumption endpoint says about the day so far.

`GET /magellan/setups/<setupId>/consumptions?periodicity=daily` answers for
the setup, not for a device : one series per thing measured, each a list of
days. Everything here is read off one account's answer, an ACI HYB water
heater's ; see docs/decisions.md for what is known and what is not.

Plain Python with no Home Assistant import, so a test can read it alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field

ELECTRICITY = 1
WATER = 4

# The unit code each series has been seen with. A series arriving in another
# unit is left out rather than shown under a unit it does not have.
KWH = 1
LITRES = 2
UNIT_OF = {ELECTRICITY: KWH, WATER: LITRES}

# The tariff period of an electricity day, settled by price. Water reads 0.
PEAK = 1
OFFPEAK = 2

# Only 101 has been seen, on an account billed in euros.
CURRENCIES = {101: "EUR"}


@dataclass
class Day:
    """One series' latest day, per tariff period."""

    date: int
    quantity: dict[int, float] = field(default_factory=dict)
    cost: dict[int, float] = field(default_factory=dict)
    currency: str | None = None
    # Every tariff period the series has used on any day it carries, which is
    # what says whether a peak/off-peak split is worth an entity at all.
    modes: set[int] = field(default_factory=set)

    def total(self, what: str) -> float:
        """The whole day, every tariff period added up."""
        return round(sum(getattr(self, what).values()), 3)

    def of_mode(self, what: str, mode: int) -> float:
        """One tariff period ; a period the day does not report used nothing."""
        return round(getattr(self, what).get(mode, 0), 3)


def latest_days(payload) -> dict[int, Day]:
    """The most recent day of every series this integration can read.

    Keyed by series type. Two series of one type -- two appliances, say --
    are added together, on the latest day either reports. An empty field on a
    day that is reported reads as zero, as it does in the app.
    """
    if not isinstance(payload, list):
        return {}

    periods_by_type: dict[int, list[tuple[dict, dict]]] = {}
    for series in payload:
        if not isinstance(series, dict):
            continue

        kind = series.get("type")
        if UNIT_OF.get(kind) is None or series.get("unit") != UNIT_OF[kind]:
            continue

        periods = series.get("consumptionPeriods")
        if not isinstance(periods, list):
            continue

        periods_by_type.setdefault(kind, []).extend(
            (series, period)
            for period in periods
            if isinstance(period, dict) and isinstance(period.get("date"), int)
        )

    days: dict[int, Day] = {}
    for kind, periods in periods_by_type.items():
        if not periods:
            continue

        day = Day(date=max(period["date"] for _, period in periods))
        for series, period in periods:
            mode = period.get("mode") or 0
            day.modes.add(mode)
            if period["date"] != day.date:
                continue

            for what, key in (("quantity", "consumedQuantity"), ("cost", "cost")):
                value = period.get(key)
                if isinstance(value, int | float):
                    bucket = getattr(day, what)
                    bucket[mode] = bucket.get(mode, 0) + value

            day.currency = day.currency or CURRENCIES.get(series.get("currency"))

        days[kind] = day

    return days
