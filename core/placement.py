"""
Placement testing engine for The God Factory University.
Adaptive difficulty, AI-generated questions, and grade-level recommendation.
"""
from __future__ import annotations

import json
import time
import uuid


def create_tables(tx_func) -> None:
    """Create placement-related tables."""
    with tx_func() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS placement_tests (
                id          TEXT PRIMARY KEY,
                subject_id  TEXT,
                grade_level TEXT,
                started_at  REAL,
                finished_at REAL,
                status      TEXT DEFAULT 'in_progress',
                result_json TEXT
            );

            CREATE TABLE IF NOT EXISTS placement_questions (
                id           TEXT PRIMARY KEY,
                test_id      TEXT NOT NULL,
                question     TEXT NOT NULL,
                choices_json TEXT,
                correct_answer TEXT,
                difficulty   INTEGER DEFAULT 5,
                order_index  INTEGER DEFAULT 0,
                FOREIGN KEY (test_id) REFERENCES placement_tests(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS placement_results (
                id          TEXT PRIMARY KEY,
                test_id     TEXT NOT NULL,
                question_id TEXT NOT NULL,
                answer      TEXT,
                correct     INTEGER DEFAULT 0,
                time_taken_s REAL DEFAULT 0,
                FOREIGN KEY (test_id) REFERENCES placement_tests(id) ON DELETE CASCADE
            );
        """)


def start_test(subject_id: str, tx_func) -> str:
    """Create a new placement test and return its ID."""
    test_id = f"pt_{uuid.uuid4().hex[:12]}"
    with tx_func() as con:
        con.execute(
            "INSERT INTO placement_tests (id, subject_id, started_at) VALUES (?, ?, ?)",
            (test_id, subject_id, time.time()),
        )
    return test_id


def add_question(test_id: str, question: str, choices: list[str],
                 correct_answer: str, difficulty: int, order_index: int, tx_func) -> str:
    """Add a question to a placement test."""
    qid = f"pq_{uuid.uuid4().hex[:12]}"
    with tx_func() as con:
        con.execute(
            "INSERT INTO placement_questions (id, test_id, question, choices_json, "
            "correct_answer, difficulty, order_index) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (qid, test_id, question, json.dumps(choices), correct_answer, difficulty, order_index),
        )
    return qid


def record_answer(test_id: str, question_id: str, answer: str,
                  correct: bool, time_taken_s: float, tx_func) -> str:
    rid = f"pr_{uuid.uuid4().hex[:12]}"
    with tx_func() as con:
        con.execute(
            "INSERT INTO placement_results (id, test_id, question_id, answer, correct, time_taken_s) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (rid, test_id, question_id, answer, 1 if correct else 0, time_taken_s),
        )
    return rid


def get_test_questions(test_id: str, tx_func) -> list[dict]:
    with tx_func() as con:
        rows = con.execute(
            "SELECT * FROM placement_questions WHERE test_id=? ORDER BY order_index",
            (test_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_test_results(test_id: str, tx_func) -> list[dict]:
    with tx_func() as con:
        rows = con.execute(
            "SELECT * FROM placement_results WHERE test_id=? ORDER BY rowid",
            (test_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def finish_test(test_id: str, tx_func) -> dict:
    """Finalize a placement test and compute recommendation."""
    results = get_test_results(test_id, tx_func)
    total = len(results)
    correct = sum(1 for r in results if r["correct"])
    score_pct = (correct / total * 100) if total > 0 else 0
    # Simple adaptive recommendation based on score
    if score_pct >= 80:
        rec_level = "advanced"
    elif score_pct >= 50:
        rec_level = "intermediate"
    else:
        rec_level = "beginner"
    result = {"total": total, "correct": correct, "score_pct": round(score_pct, 1),
              "recommended_level": rec_level}
    with tx_func() as con:
        con.execute(
            "UPDATE placement_tests SET finished_at=?, status='completed', result_json=? WHERE id=?",
            (time.time(), json.dumps(result), test_id),
        )
    return result


def get_adaptive_difficulty(test_id: str, tx_func) -> int:
    """Return next question difficulty based on recent answers (1-10 scale)."""
    results = get_test_results(test_id, tx_func)
    if not results:
        return 5
    recent = results[-3:]  # last 3 answers
    correct_streak = sum(1 for r in recent if r["correct"])
    current = 5
    if len(results) > 0:
        # Get current difficulty from last question
        with tx_func() as con:
            row = con.execute(
                "SELECT difficulty FROM placement_questions WHERE test_id=? ORDER BY order_index DESC LIMIT 1",
                (test_id,),
            ).fetchone()
        if row:
            current = row["difficulty"]
    if correct_streak >= 3:
        return min(current + 2, 10)
    elif correct_streak >= 2:
        return min(current + 1, 10)
    elif correct_streak == 0:
        return max(current - 2, 1)
    return current


def get_all_tests(tx_func) -> list[dict]:
    with tx_func() as con:
        rows = con.execute(
            "SELECT * FROM placement_tests ORDER BY started_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]
