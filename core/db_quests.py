"""
Weekly quest logic for The God Factory University.
Extracted from database.py for modularity (DEVELOPMENT.md Rule 5).
"""
from __future__ import annotations

from datetime import datetime, timedelta


_QUEST_TEMPLATES = [
    ("complete_3_lectures", "Complete 3 Lectures", "Finish 3 lectures this week", 3, 100),
    ("earn_200_xp", "Earn 200 XP", "Accumulate 200 XP this week", 200, 75),
    ("submit_assignment", "Submit an Assignment", "Turn in at least 1 assignment", 1, 50),
]


def _current_week_start() -> str:
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    return monday.strftime("%Y-%m-%d")


def seed_weekly_quests(tx_func) -> None:
    week = _current_week_start()
    with tx_func() as con:
        existing = con.execute(
            "SELECT id FROM quests WHERE week_start=?", (week,)
        ).fetchall()
    if existing:
        return
    with tx_func() as con:
        for qid, title, desc, target, xp in _QUEST_TEMPLATES:
            con.execute(
                "INSERT OR IGNORE INTO quests (id,title,description,target,progress,xp_reward,week_start) "
                "VALUES (?,?,?,?,0,?,?)",
                (f"{qid}_{week}", title, desc, target, xp, week),
            )


def get_active_quests(tx_func) -> list[dict]:
    week = _current_week_start()
    with tx_func() as con:
        rows = con.execute(
            "SELECT * FROM quests WHERE week_start=? ORDER BY id", (week,)
        ).fetchall()
    return [dict(r) for r in rows]


def update_quest_progress(quest_prefix: str, tx_func, add_xp_func, increment: int = 1) -> None:
    week = _current_week_start()
    qid = f"{quest_prefix}_{week}"
    with tx_func() as con:
        row = con.execute(
            "SELECT progress, target, completed, xp_reward FROM quests WHERE id=?", (qid,)
        ).fetchone()
    if not row or row["completed"]:
        return
    new_progress = min(row["progress"] + increment, row["target"])
    completed = 1 if new_progress >= row["target"] else 0
    with tx_func() as con:
        con.execute(
            "UPDATE quests SET progress=?, completed=? WHERE id=?",
            (new_progress, completed, qid),
        )
    if completed:
        add_xp_func(row["xp_reward"], f"Quest complete: {quest_prefix}", "quest")
