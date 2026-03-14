"""
Programs & curriculum engine for The God Factory University.
Degree programs, requirements, enrollment, and progress tracking.
"""
from __future__ import annotations

import json
import time
import uuid


_DEFAULT_PROGRAMS: list[tuple[str, str, str, str, str, int]] = [
    # (id, name, level, school, description, total_credits)
    ("cert_cs", "Certificate in Computer Science", "Certificate", "School of Computer Science", "Foundational CS skills.", 15),
    ("cert_math", "Certificate in Mathematics", "Certificate", "School of Numerical Sorcery", "Core math fundamentals.", 15),
    ("assoc_gen", "Associate of General Studies", "Associate", "College of Liberal Arts", "Broad liberal arts foundation.", 60),
    ("bach_cs", "Bachelor of Computer Science", "Bachelor", "School of Computer Science", "Complete CS curriculum.", 120),
    ("bach_eng", "Bachelor of English", "Bachelor", "School of Ancient Tongues", "Literature and composition.", 120),
    ("mast_cs", "Master of Computer Science", "Master", "School of Computer Science", "Advanced CS research.", 150),
    ("doct_cs", "Doctorate in Computer Science", "Doctorate", "School of Computer Science", "Original research contribution.", 180),
]


def create_tables(tx_func) -> None:
    with tx_func() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS programs (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                level       TEXT NOT NULL,
                school      TEXT,
                description TEXT,
                total_credits INTEGER DEFAULT 120
            );

            CREATE TABLE IF NOT EXISTS program_requirements (
                id          TEXT PRIMARY KEY,
                program_id  TEXT NOT NULL,
                course_id   TEXT,
                category    TEXT DEFAULT 'core',
                required    INTEGER DEFAULT 1,
                FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS enrollments (
                id          TEXT PRIMARY KEY,
                program_id  TEXT NOT NULL,
                enrolled_at REAL DEFAULT (unixepoch()),
                status      TEXT DEFAULT 'active',
                completed_at REAL,
                FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE CASCADE
            );
        """)


def seed_programs(tx_func) -> None:
    with tx_func() as con:
        for pid, name, level, school, desc, credits in _DEFAULT_PROGRAMS:
            con.execute(
                "INSERT OR IGNORE INTO programs (id, name, level, school, description, total_credits) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (pid, name, level, school, desc, credits),
            )


def get_all_programs(tx_func) -> list[dict]:
    with tx_func() as con:
        rows = con.execute("SELECT * FROM programs ORDER BY total_credits, name").fetchall()
    return [dict(r) for r in rows]


def get_program(program_id: str, tx_func) -> dict | None:
    with tx_func() as con:
        row = con.execute("SELECT * FROM programs WHERE id=?", (program_id,)).fetchone()
    return dict(row) if row else None


def enroll(program_id: str, tx_func) -> str:
    eid = f"enr_{uuid.uuid4().hex[:12]}"
    with tx_func() as con:
        con.execute(
            "INSERT INTO enrollments (id, program_id) VALUES (?, ?)",
            (eid, program_id),
        )
    return eid


def get_enrollments(tx_func) -> list[dict]:
    with tx_func() as con:
        rows = con.execute(
            "SELECT e.*, p.name AS program_name, p.level AS program_level, p.total_credits "
            "FROM enrollments e JOIN programs p ON e.program_id = p.id "
            "ORDER BY e.enrolled_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_program_requirements(program_id: str, tx_func) -> list[dict]:
    with tx_func() as con:
        rows = con.execute(
            "SELECT * FROM program_requirements WHERE program_id=? ORDER BY category, course_id",
            (program_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def add_requirement(program_id: str, course_id: str, category: str, required: bool, tx_func) -> str:
    rid = f"req_{uuid.uuid4().hex[:12]}"
    with tx_func() as con:
        con.execute(
            "INSERT INTO program_requirements (id, program_id, course_id, category, required) "
            "VALUES (?, ?, ?, ?, ?)",
            (rid, program_id, course_id, category, 1 if required else 0),
        )
    return rid


def complete_enrollment(enrollment_id: str, tx_func) -> None:
    with tx_func() as con:
        con.execute(
            "UPDATE enrollments SET status='completed', completed_at=? WHERE id=?",
            (time.time(), enrollment_id),
        )
