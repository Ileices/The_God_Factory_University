"""
Standardized test prep engine for Arcane University.
Manages GED / SAT / ACT / GRE practice sessions with timed mode and scoring.
"""
from __future__ import annotations

import json
import time
import uuid

# Simplified percentile lookup tables (score -> approx percentile)
_PERCENTILE_TABLES: dict[str, list[tuple[int, int]]] = {
    "SAT": [(400, 1), (800, 10), (1000, 35), (1100, 50), (1200, 67), (1300, 82), (1400, 93), (1500, 98), (1600, 99)],
    "ACT": [(1, 1), (12, 10), (18, 35), (21, 50), (25, 70), (28, 85), (32, 95), (36, 99)],
    "GRE": [(130, 1), (145, 15), (150, 35), (155, 60), (160, 80), (165, 93), (170, 98)],
    "GED": [(100, 1), (130, 10), (145, 35), (155, 50), (165, 70), (175, 90), (200, 99)],
}

_TEST_SECTIONS: dict[str, list[str]] = {
    "SAT": ["Reading", "Writing & Language", "Math (No Calc)", "Math (Calculator)"],
    "ACT": ["English", "Math", "Reading", "Science"],
    "GRE": ["Verbal Reasoning", "Quantitative Reasoning", "Analytical Writing"],
    "GED": ["Reasoning Through Language Arts", "Mathematical Reasoning", "Science", "Social Studies"],
}


def create_tables(tx_func) -> None:
    with tx_func() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS test_prep_sessions (
                id          TEXT PRIMARY KEY,
                test_name   TEXT NOT NULL,
                section     TEXT,
                score       REAL,
                max_score   REAL,
                time_taken_s REAL DEFAULT 0,
                taken_at    REAL DEFAULT (unixepoch()),
                result_json TEXT
            );

            CREATE TABLE IF NOT EXISTS test_prep_questions (
                id          TEXT PRIMARY KEY,
                session_id  TEXT NOT NULL,
                test_name   TEXT NOT NULL,
                section     TEXT,
                question    TEXT NOT NULL,
                choices_json TEXT,
                correct_answer TEXT,
                difficulty  INTEGER DEFAULT 5,
                order_index INTEGER DEFAULT 0,
                FOREIGN KEY (session_id) REFERENCES test_prep_sessions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS test_prep_answers (
                id          TEXT PRIMARY KEY,
                session_id  TEXT NOT NULL,
                question_id TEXT NOT NULL,
                answer      TEXT,
                correct     INTEGER DEFAULT 0,
                time_taken_s REAL DEFAULT 0,
                FOREIGN KEY (session_id) REFERENCES test_prep_sessions(id) ON DELETE CASCADE
            );
        """)


def get_test_names() -> list[str]:
    return list(_TEST_SECTIONS.keys())


def get_sections(test_name: str) -> list[str]:
    return _TEST_SECTIONS.get(test_name, [])


def start_session(test_name: str, section: str, tx_func) -> str:
    sid = f"tp_{uuid.uuid4().hex[:12]}"
    with tx_func() as con:
        con.execute(
            "INSERT INTO test_prep_sessions (id, test_name, section) VALUES (?, ?, ?)",
            (sid, test_name, section),
        )
    return sid


def add_question(session_id: str, test_name: str, section: str, question: str,
                 choices: list[str], correct_answer: str, difficulty: int,
                 order_index: int, tx_func) -> str:
    qid = f"tq_{uuid.uuid4().hex[:12]}"
    with tx_func() as con:
        con.execute(
            "INSERT INTO test_prep_questions (id, session_id, test_name, section, question, "
            "choices_json, correct_answer, difficulty, order_index) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (qid, session_id, test_name, section, question,
             json.dumps(choices), correct_answer, difficulty, order_index),
        )
    return qid


def record_answer(session_id: str, question_id: str, answer: str,
                  correct: bool, time_taken_s: float, tx_func) -> str:
    aid = f"ta_{uuid.uuid4().hex[:12]}"
    with tx_func() as con:
        con.execute(
            "INSERT INTO test_prep_answers (id, session_id, question_id, answer, correct, time_taken_s) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (aid, session_id, question_id, answer, 1 if correct else 0, time_taken_s),
        )
    return aid


def finish_session(session_id: str, tx_func) -> dict:
    with tx_func() as con:
        answers = con.execute(
            "SELECT * FROM test_prep_answers WHERE session_id=? ORDER BY rowid",
            (session_id,),
        ).fetchall()
        sess = con.execute(
            "SELECT * FROM test_prep_sessions WHERE id=?", (session_id,)
        ).fetchone()
    total = len(answers)
    correct = sum(1 for a in answers if a["correct"])
    score_pct = (correct / total * 100) if total > 0 else 0
    time_taken = sum(a["time_taken_s"] for a in answers)
    result = {
        "total": total, "correct": correct, "score_pct": round(score_pct, 1),
        "time_taken_s": round(time_taken, 1),
        "percentile": estimate_percentile(sess["test_name"], score_pct) if sess else 0,
    }
    with tx_func() as con:
        con.execute(
            "UPDATE test_prep_sessions SET score=?, time_taken_s=?, result_json=? WHERE id=?",
            (score_pct, time_taken, json.dumps(result), session_id),
        )
    return result


def estimate_percentile(test_name: str, score_pct: float) -> int:
    table = _PERCENTILE_TABLES.get(test_name)
    if not table:
        return 50
    # Map percentage to approximate raw score range then interpolate
    # Simplified: treat score_pct directly as a lookup key
    if score_pct >= 95:
        return 99
    elif score_pct >= 85:
        return 90
    elif score_pct >= 70:
        return 70
    elif score_pct >= 50:
        return 50
    elif score_pct >= 30:
        return 25
    return 10


def get_session_history(test_name: str | None, tx_func) -> list[dict]:
    with tx_func() as con:
        if test_name:
            rows = con.execute(
                "SELECT * FROM test_prep_sessions WHERE test_name=? ORDER BY taken_at DESC",
                (test_name,),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM test_prep_sessions ORDER BY taken_at DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def get_session_questions(session_id: str, tx_func) -> list[dict]:
    with tx_func() as con:
        rows = con.execute(
            "SELECT * FROM test_prep_questions WHERE session_id=? ORDER BY order_index",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]
