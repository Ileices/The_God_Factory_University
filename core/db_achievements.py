"""
Achievement definitions, seeding, and trigger logic for The God Factory University.
Extracted from database.py for modularity (DEVELOPMENT.md Rule 5).
"""
from __future__ import annotations

import time


_ACHIEVEMENT_DEFS = [
    ("first_lecture",   "Awakening",        "Complete your first lecture",          "progress", 50),
    ("ten_lectures",    "Apprentice Path",  "Complete 10 lectures",                 "progress", 200),
    ("first_quiz",      "Trial Taker",      "Submit your first assignment",         "academic", 75),
    ("perfect_score",   "Flawless",        "Score 100% on any assignment",         "academic", 150),
    ("speed_reader",    "Swift Scholar",    "Complete a lecture in one session",    "efficiency", 100),
    ("xp_1000",         "Rising Star",      "Earn 1000 XP",                         "xp",       100),
    ("xp_5000",         "Transcendent Adept",     "Earn 5000 XP",                         "xp",       250),
    ("degree_cert",     "Certified",        "Earn Certificate eligibility",         "degree",   500),
    ("degree_assoc",    "Associate",        "Earn Associate eligibility",           "degree",   1000),
    ("degree_bachelor", "Bachelor",         "Earn Bachelor eligibility",            "degree",   2000),
    ("degree_master",   "Grand Scholar",    "Earn Master eligibility",              "degree",   5000),
    ("degree_doctor",   "Doctorate",        "Earn Doctorate eligibility",           "degree",   10000),
    ("night_owl",       "Night Owl",        "Study after midnight",                 "habit",    75),
    ("bulk_import",     "Archivist",        "Import a bulk JSON curriculum",        "system",   100),
    ("professor_query", "The Asking",       "Query the Professor AI 10 times",      "llm",      100),
    ("video_render",    "Projector",        "Render your first lecture video",      "media",    150),
    ("batch_render",    "Dreamweaver",      "Batch render 5 or more lectures",      "media",    300),
]


def seed_achievements(tx_func, add_xp_func=None) -> None:
    """Insert achievement rows if they don't exist yet.

    Args:
        tx_func: The ``tx()`` context-manager from database.py.
    """
    with tx_func() as con:
        for aid, title, desc, cat, xp in _ACHIEVEMENT_DEFS:
            con.execute(
                "INSERT OR IGNORE INTO achievements (id,title,description,category,xp_reward) VALUES (?,?,?,?,?)",
                (aid, title, desc, cat, xp),
            )


def unlock_achievement(achievement_id: str, tx_func, add_xp_func) -> bool:
    """Unlock an achievement if it hasn't been unlocked yet.

    Args:
        achievement_id: The ID of the achievement to unlock.
        tx_func: The ``tx()`` context-manager from database.py.
        add_xp_func: The ``add_xp()`` function from database.py.
    """
    with tx_func() as con:
        row = con.execute("SELECT unlocked_at FROM achievements WHERE id=?", (achievement_id,)).fetchone()
        if not row or row["unlocked_at"]:
            return False
        con.execute(
            "UPDATE achievements SET unlocked_at=? WHERE id=?", (time.time(), achievement_id)
        )
        reward = con.execute("SELECT xp_reward FROM achievements WHERE id=?", (achievement_id,)).fetchone()
    if reward:
        add_xp_func(reward["xp_reward"], f"Achievement: {achievement_id}", "achievement")
    return True


def get_achievements(tx_func) -> list[dict]:
    with tx_func() as con:
        rows = con.execute("SELECT * FROM achievements ORDER BY category, id").fetchall()
    return [dict(r) for r in rows]


def check_achievements_xp(total_xp: int, unlock_func) -> None:
    if total_xp >= 1000:
        unlock_func("xp_1000")
    if total_xp >= 5000:
        unlock_func("xp_5000")


def check_achievements_degrees(eligible_degrees_func, unlock_func) -> None:
    """Check all degree-tier achievements after grade/credit changes."""
    earned = eligible_degrees_func()
    _DEGREE_MAP = {
        "Certificate": "degree_cert",
        "Associate": "degree_assoc",
        "Bachelor": "degree_bachelor",
        "Master": "degree_master",
        "Doctorate": "degree_doctor",
    }
    for deg in earned:
        aid = _DEGREE_MAP.get(deg)
        if aid:
            unlock_func(aid)
