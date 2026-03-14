"""
Grade-level system for The God Factory University.
Provides K-12, undergraduate, graduate, and doctoral levels.
Extracted as sub-module per DEVELOPMENT.md Rule 5.
"""
from __future__ import annotations


_GRADE_LEVELS = [
    ("K",           "Kindergarten",             0,  "Early learner (ages 5-6)"),
    ("1",           "1st Grade",                1,  "Elementary (ages 6-7)"),
    ("2",           "2nd Grade",                2,  "Elementary (ages 7-8)"),
    ("3",           "3rd Grade",                3,  "Elementary (ages 8-9)"),
    ("4",           "4th Grade",                4,  "Elementary (ages 9-10)"),
    ("5",           "5th Grade",                5,  "Elementary (ages 10-11)"),
    ("6",           "6th Grade",                6,  "Middle school (ages 11-12)"),
    ("7",           "7th Grade",                7,  "Middle school (ages 12-13)"),
    ("8",           "8th Grade",                8,  "Middle school (ages 13-14)"),
    ("9",           "9th Grade (Freshman)",     9,  "High school"),
    ("10",          "10th Grade (Sophomore)",   10, "High school"),
    ("11",          "11th Grade (Junior)",      11, "High school"),
    ("12",          "12th Grade (Senior)",      12, "High school"),
    ("freshman",    "College Freshman",         13, "Undergraduate year 1"),
    ("sophomore",   "College Sophomore",        14, "Undergraduate year 2"),
    ("junior",      "College Junior",           15, "Undergraduate year 3"),
    ("senior",      "College Senior",           16, "Undergraduate year 4"),
    ("masters",     "Master's Student",         17, "Graduate level"),
    ("doctoral",    "Doctoral Candidate",       18, "PhD / professional doctorate"),
    ("postdoc",     "Post-Doctoral",            19, "Post-doctoral research"),
]


def create_tables(tx_func) -> None:
    """Create grade_levels table if it doesn't exist."""
    with tx_func() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS grade_levels (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                order_index INTEGER NOT NULL DEFAULT 0,
                description TEXT
            )
        """)


def seed_grade_levels(tx_func) -> None:
    """Insert standard grade levels if they don't exist yet."""
    with tx_func() as con:
        for gid, name, order_idx, desc in _GRADE_LEVELS:
            con.execute(
                "INSERT OR IGNORE INTO grade_levels (id, name, order_index, description) "
                "VALUES (?, ?, ?, ?)",
                (gid, name, order_idx, desc),
            )


def get_all_levels(tx_func) -> list[dict]:
    """Return all grade levels ordered by order_index."""
    with tx_func() as con:
        rows = con.execute("SELECT * FROM grade_levels ORDER BY order_index").fetchall()
    return [dict(r) for r in rows]


def get_level_by_id(level_id: str, tx_func) -> dict | None:
    with tx_func() as con:
        row = con.execute("SELECT * FROM grade_levels WHERE id=?", (level_id,)).fetchone()
    return dict(row) if row else None
