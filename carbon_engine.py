"""
carbon_engine.py
Deterministic CO2 calculation engine for the Carbon Footprint Platform.
"""

import sqlite3
from datetime import datetime, date
from typing import Optional

# ── Emission factors ────────────────────────────────────────────────────────
EMISSION_FACTORS: dict[str, float] = {
    # Travel (kg CO2 per km)
    "car":        0.21,
    "bike":       0.05,
    "bus":        0.08,
    "flight":     0.255,
    # Food (kg CO2 per meal)
    "non_veg":    2.5,
    "veg":        0.5,
    # Electricity (kg CO2 per kWh)
    "electricity": 0.82,
}

VALID_ACTIVITY_TYPES = set(EMISSION_FACTORS.keys())


def calculate_co2(activity_type: str, quantity: float) -> float:
    """Return CO2 (kg) emitted for the given activity and quantity.

    Args:
        activity_type: One of the keys in EMISSION_FACTORS.
        quantity:      km driven / meals eaten / kWh consumed – must be > 0.

    Returns:
        CO2 in kg, rounded to 4 decimal places.

    Raises:
        ValueError: For unknown activity types or non-positive quantities.
    """
    if activity_type not in EMISSION_FACTORS:
        raise ValueError(
            f"Unknown activity type '{activity_type}'. "
            f"Valid types: {sorted(VALID_ACTIVITY_TYPES)}"
        )
    if quantity <= 0:
        raise ValueError(f"Quantity must be positive, got {quantity}.")

    return round(EMISSION_FACTORS[activity_type] * quantity, 4)


def get_daily_total(user_id: int, db_path: str = "carbon.db",
                    for_date: Optional[date] = None) -> float:
    """Sum of CO2 (kg) logged by *user_id* for *for_date* (defaults to today).

    Args:
        user_id:  The authenticated user's primary key.
        db_path:  Path to the SQLite database file.
        for_date: The calendar date to aggregate; defaults to today.

    Returns:
        Total CO2 in kg, rounded to 4 decimal places.
    """
    if for_date is None:
        for_date = date.today()

    day_str = for_date.isoformat()          # "YYYY-MM-DD"

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT COALESCE(SUM(co2_kg), 0) AS total
            FROM   activities
            WHERE  user_id   = ?
              AND  DATE(timestamp) = ?
            """,
            (user_id, day_str),
        )
        row = cur.fetchone()

    return round(float(row["total"]), 4)


def get_weekly_total(user_id: int, db_path: str = "carbon.db") -> float:
    """Sum of CO2 (kg) logged by *user_id* over the last 7 days."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT COALESCE(SUM(co2_kg), 0) AS total
            FROM   activities
            WHERE  user_id   = ?
              AND  timestamp >= DATE('now', '-6 days')
            """,
            (user_id,),
        )
        row = cur.fetchone()

    return round(float(row["total"]), 4)


def get_category_breakdown(user_id: int, db_path: str = "carbon.db") -> dict:
    """Return CO2 totals grouped by broad category for the last 7 days.

    Returns a dict like:
        {"travel": 12.5, "food": 4.0, "electricity": 6.56}
    """
    travel_types      = ("car", "bike", "bus", "flight")
    food_types        = ("veg", "non_veg")
    electricity_types = ("electricity",)

    def _sum_for(types: tuple, conn: sqlite3.Connection) -> float:
        placeholders = ",".join("?" * len(types))
        cur = conn.execute(
            f"""
            SELECT COALESCE(SUM(co2_kg), 0) AS total
            FROM   activities
            WHERE  user_id      = ?
              AND  activity_type IN ({placeholders})
              AND  timestamp    >= DATE('now', '-6 days')
            """,
            (user_id, *types),
        )
        return round(float(cur.fetchone()[0]), 4)

    with sqlite3.connect(db_path) as conn:
        return {
            "travel":      _sum_for(travel_types, conn),
            "food":        _sum_for(food_types, conn),
            "electricity": _sum_for(electricity_types, conn),
        }


def get_daily_trend(user_id: int, db_path: str = "carbon.db") -> list[dict]:
    """Return per-day CO2 totals for the last 7 days (oldest first).

    Each dict: {"day": "YYYY-MM-DD", "total": float}
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT DATE(timestamp)          AS day,
                   ROUND(SUM(co2_kg), 4)   AS total
            FROM   activities
            WHERE  user_id   = ?
              AND  timestamp >= DATE('now', '-6 days')
            GROUP  BY DATE(timestamp)
            ORDER  BY DATE(timestamp) ASC
            """,
            (user_id,),
        )
        return [dict(row) for row in cur.fetchall()]
