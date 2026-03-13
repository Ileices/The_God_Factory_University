"""
GPA, grade scale, degree tracks, and credit calculation for Arcane University.
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
    "Certificate":  {"min_credits": 15,  "min_gpa": 2.0},
    "Associate":    {"min_credits": 60,  "min_gpa": 2.0},
    "Bachelor":     {"min_credits": 120, "min_gpa": 2.0},
    "Master":       {"min_credits": 150, "min_gpa": 3.0},
    "Doctorate":    {"min_credits": 180, "min_gpa": 3.5},
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


def credits_earned(tx_func) -> int:
    with tx_func() as con:
        row = con.execute(
            """SELECT SUM(c.credits) as total
               FROM courses c
               WHERE c.id IN (
                   SELECT DISTINCT l.course_id FROM lectures l
                   JOIN progress p ON p.lecture_id = l.id
                   WHERE p.status='completed'
               )""",
        ).fetchone()
    return int(row["total"] or 0)


def eligible_degrees(tx_func, gpa: float | None = None, credits: int | None = None) -> list[str]:
    _gpa, count = compute_gpa(tx_func)
    if gpa is None:
        gpa = _gpa
    if credits is None:
        credits = credits_earned(tx_func)
    return [
        d for d, req in DEGREE_TRACKS.items()
        if credits >= req["min_credits"] and gpa >= req["min_gpa"] and count > 0
    ]
