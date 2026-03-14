"""
GPA, grade scale, degree tracks, and credit calculation for The God Factory University.
Extracted from database.py for modularity (DEVELOPMENT.md Rule 5).
"""
from __future__ import annotations


GRADE_SCALE = [
    ("A+", 97, 4.0), ("A", 93, 4.0), ("A-", 90, 3.7),
    ("B+", 87, 3.3), ("B", 83, 3.0), ("B-", 80, 2.7),
    ("C+", 77, 2.3), ("C", 73, 2.0), ("C-", 70, 1.7),
    ("D", 60, 1.0), ("F", 0, 0.0),
]


DEGREE_TRACKS = {
    "Certificate":  {"min_credits": 15,  "min_gpa": 2.0, "min_hours": 675},
    "Associate":    {"min_credits": 60,  "min_gpa": 2.0, "min_hours": 2700},
    "Bachelor":     {"min_credits": 120, "min_gpa": 2.0, "min_hours": 5400},
    "Master":       {"min_credits": 150, "min_gpa": 3.0, "min_hours": 6750},
    "Doctorate":    {"min_credits": 180, "min_gpa": 3.5, "min_hours": 8100},
}


def score_to_grade(score: float) -> tuple[str, float]:
    for letter, threshold, points in GRADE_SCALE:
        if score >= threshold:
            return letter, points
    return "F", 0.0


def compute_gpa(tx_func) -> tuple[float, int]:
    with tx_func() as con:
        rows = con.execute("SELECT score, max_score FROM assignments WHERE submitted_at IS NOT NULL").fetchall()
    if not rows:
        return 0.0, 0
    total_points = 0.0
    count = 0
    for r in rows:
        if r["score"] is not None and r["max_score"] and r["max_score"] > 0:
            pct = (r["score"] / r["max_score"]) * 100
            _, points = score_to_grade(pct)
            total_points += points
            count += 1
    return (round(total_points / count, 2) if count else 0.0), count


def credits_earned(tx_func) -> float:
    """Credits earned from completed course sub-trees.

    Uses credit_hours-based calculation when available (hours / 45 = credits),
    falling back to flat course credits for legacy data.
    Returns float for fractional credit tracking.
    """
    with tx_func() as con:
        # New: credit-hours based (sum hours logged across completed courses)
        hour_row = con.execute(
            """SELECT COALESCE(SUM(c.credit_hours), 0) AS total_hours
               FROM courses c
               WHERE c.id IN (
                   SELECT DISTINCT l.course_id FROM lectures l
                   JOIN progress p ON p.lecture_id = l.id
                   WHERE p.status='completed'
               ) AND c.credit_hours > 0""",
        ).fetchone()
        hours_credits = (hour_row["total_hours"] or 0) / 45.0

        # Legacy: flat credits for courses without credit_hours tracking
        flat_row = con.execute(
            """SELECT COALESCE(SUM(c.credits), 0) AS total
               FROM courses c
               WHERE c.id IN (
                   SELECT DISTINCT l.course_id FROM lectures l
                   JOIN progress p ON p.lecture_id = l.id
                   WHERE p.status='completed'
               ) AND (c.credit_hours IS NULL OR c.credit_hours = 0)""",
        ).fetchone()
        flat_credits = float(flat_row["total"] or 0)

    return round(flat_credits + hours_credits, 2)


def eligible_degrees(tx_func, gpa: float | None = None, credits: float | None = None) -> list[str]:
    _gpa, count = compute_gpa(tx_func)
    if gpa is None:
        gpa = _gpa
    if credits is None:
        credits = credits_earned(tx_func)
    return [
        d for d, req in DEGREE_TRACKS.items()
        if credits >= req["min_credits"] and gpa >= req["min_gpa"] and count > 0
    ]


def time_to_degree_estimate(tx_func, target_degree: str = "Bachelor") -> dict | None:
    """Estimate remaining time to a degree based on current study rate."""
    track = DEGREE_TRACKS.get(target_degree)
    if not track:
        return None
    credits = credits_earned(tx_func)
    gpa, _ = compute_gpa(tx_func)
    needed_credits = max(track["min_credits"] - credits, 0)
    needed_hours = needed_credits * 45

    # Calculate study rate: credits earned per day since enrollment
    with tx_func() as con:
        row = con.execute(
            "SELECT MIN(logged_at) AS first FROM study_hours_log"
        ).fetchone()
    import time as _time
    first_log = row["first"] if row and row["first"] else None
    days_active = ((_time.time() - first_log) / 86400.0) if first_log else 0

    if days_active > 0 and credits > 0:
        rate_credits_per_day = credits / days_active
        est_days = needed_credits / rate_credits_per_day if rate_credits_per_day > 0 else 0
    else:
        rate_credits_per_day = 0
        est_days = 0

    return {
        "target": target_degree,
        "credits_earned": round(credits, 2),
        "credits_needed": round(needed_credits, 2),
        "hours_needed": round(needed_hours, 1),
        "days_active": round(days_active, 0),
        "rate_credits_per_day": round(rate_credits_per_day, 4),
        "est_days_remaining": round(est_days, 0),
        "gpa_met": gpa >= track["min_gpa"],
    }
