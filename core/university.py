"""
University infrastructure: prerequisites, course lifecycle, spaced repetition,
flashcards, syllabus, study timer, certificates, and other educational features.

This module adds the "university plumbing" that a real educational platform needs:
  - Prerequisites enforcement
  - Course lifecycle (draft/published/archived)
  - Spaced repetition scheduling (SM-2 algorithm)
  - Flashcard system
  - Syllabus generator
  - Study timer with Pomodoro support
  - Certificate generation
  - Academic calendar
  - Backup/restore
"""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _db():
    """Lazy import to avoid circular dependency with core.database."""
    import core.database as db
    return db


# ─── DB tables ────────────────────────────────────────────────────────────────

def create_tables(tx_fn) -> None:
    """Create university infrastructure tables."""
    with tx_fn() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS prerequisites (
            course_id      TEXT NOT NULL,
            prereq_id      TEXT NOT NULL,
            required       INTEGER DEFAULT 1,
            PRIMARY KEY (course_id, prereq_id)
        );

        CREATE TABLE IF NOT EXISTS course_lifecycle (
            course_id      TEXT PRIMARY KEY,
            status         TEXT DEFAULT 'draft',
            published_at   REAL,
            archived_at    REAL
        );

        CREATE TABLE IF NOT EXISTS flashcards (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            lecture_id     TEXT,
            course_id      TEXT,
            front          TEXT NOT NULL,
            back           TEXT NOT NULL,
            ease_factor    REAL DEFAULT 2.5,
            interval_days  REAL DEFAULT 1.0,
            repetitions    INTEGER DEFAULT 0,
            next_review    REAL,
            created_at     REAL DEFAULT (unixepoch())
        );

        CREATE TABLE IF NOT EXISTS study_sessions (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            session_type   TEXT DEFAULT 'pomodoro',
            started_at     REAL DEFAULT (unixepoch()),
            ended_at       REAL,
            duration_min   REAL DEFAULT 0,
            lecture_id     TEXT,
            notes          TEXT
        );

        CREATE TABLE IF NOT EXISTS certificates (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id      TEXT NOT NULL,
            student_name   TEXT,
            issued_at      REAL DEFAULT (unixepoch()),
            grade          TEXT,
            gpa            REAL,
            data           TEXT
        );

        CREATE TABLE IF NOT EXISTS notes (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            lecture_id     TEXT,
            course_id      TEXT,
            content        TEXT NOT NULL,
            created_at     REAL DEFAULT (unixepoch()),
            updated_at     REAL
        );

        CREATE TABLE IF NOT EXISTS academic_calendar (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type     TEXT NOT NULL,
            title          TEXT NOT NULL,
            start_date     TEXT NOT NULL,
            end_date       TEXT,
            course_id      TEXT,
            data           TEXT
        );
        """)


# ─── Prerequisites ────────────────────────────────────────────────────────────

def add_prerequisite(course_id: str, prereq_id: str, required: bool = True) -> None:
    """Add a prerequisite relationship."""
    with _db().tx() as con:
        con.execute(
            "INSERT OR REPLACE INTO prerequisites (course_id, prereq_id, required) VALUES (?,?,?)",
            (course_id, prereq_id, 1 if required else 0),
        )


def remove_prerequisite(course_id: str, prereq_id: str) -> None:
    with _db().tx() as con:
        con.execute(
            "DELETE FROM prerequisites WHERE course_id=? AND prereq_id=?",
            (course_id, prereq_id),
        )


def get_prerequisites(course_id: str) -> list[dict]:
    """Get all prerequisites for a course."""
    with _db().tx() as con:
        rows = con.execute(
            """SELECT p.prereq_id, p.required, c.title
               FROM prerequisites p
               LEFT JOIN courses c ON c.id = p.prereq_id
               WHERE p.course_id=?""",
            (course_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def check_prerequisites_met(course_id: str) -> tuple[bool, list[str]]:
    """Check if all required prerequisites are completed.
    Returns (all_met, list_of_unmet_prereq_ids).
    """
    prereqs = get_prerequisites(course_id)
    unmet = []
    for p in prereqs:
        if not p["required"]:
            continue
        pid = p["prereq_id"]
        # Check if all lectures in the prereq course are completed
        db = _db()
        modules = db.get_modules(pid)
        all_done = True
        for m in modules:
            lectures = db.get_lectures(m["id"])
            for lec in lectures:
                prog = db.get_progress(lec["id"])
                if prog.get("status") != "completed":
                    all_done = False
                    break
            if not all_done:
                break
        if not all_done:
            unmet.append(pid)
    return len(unmet) == 0, unmet


def get_prerequisite_graph() -> dict:
    """Get the full prerequisite graph for visualization."""
    with _db().tx() as con:
        rows = con.execute(
            "SELECT course_id, prereq_id, required FROM prerequisites"
        ).fetchall()
    nodes = set()
    edges = []
    for r in rows:
        nodes.add(r["course_id"])
        nodes.add(r["prereq_id"])
        edges.append({
            "from": r["prereq_id"],
            "to": r["course_id"],
            "required": bool(r["required"]),
        })
    return {"nodes": list(nodes), "edges": edges}


# ─── Course lifecycle ──────────────────────────────────────────────────────────

def set_course_status(course_id: str, status: str) -> None:
    """Set course lifecycle status: draft, published, archived."""
    now = time.time()
    with _db().tx() as con:
        con.execute(
            "INSERT OR REPLACE INTO course_lifecycle (course_id, status, published_at, archived_at) "
            "VALUES (?, ?, ?, ?)",
            (
                course_id, status,
                now if status == "published" else None,
                now if status == "archived" else None,
            ),
        )


def get_course_status(course_id: str) -> str:
    """Get the lifecycle status of a course."""
    with _db().tx() as con:
        row = con.execute(
            "SELECT status FROM course_lifecycle WHERE course_id=?", (course_id,)
        ).fetchone()
    return row["status"] if row else "draft"


def get_courses_by_status(status: str) -> list[dict]:
    """Get all courses with a given lifecycle status."""
    with _db().tx() as con:
        rows = con.execute(
            """SELECT c.*, cl.status as lifecycle_status
               FROM courses c
               LEFT JOIN course_lifecycle cl ON c.id = cl.course_id
               WHERE COALESCE(cl.status, 'draft') = ?""",
            (status,),
        ).fetchall()
    return [dict(r) for r in rows]


# ─── Spaced Repetition (SM-2 Algorithm) ──────────────────────────────────────

def create_flashcard(front: str, back: str, lecture_id: str = "",
                     course_id: str = "") -> int:
    """Create a new flashcard. Returns the card ID."""
    now = time.time()
    with _db().tx() as con:
        cur = con.execute(
            "INSERT INTO flashcards (lecture_id, course_id, front, back, next_review) "
            "VALUES (?,?,?,?,?)",
            (lecture_id, course_id, front, back, now),
        )
        return cur.lastrowid


def review_flashcard(card_id: int, quality: int) -> dict:
    """Review a flashcard using SM-2 algorithm.

    quality: 0-5 (0=complete blank, 5=perfect recall)
    Returns updated card state.
    """
    with _db().tx() as con:
        row = con.execute("SELECT * FROM flashcards WHERE id=?", (card_id,)).fetchone()
    if not row:
        return {"error": "Card not found"}

    ef = row["ease_factor"]
    interval = row["interval_days"]
    reps = row["repetitions"]

    # SM-2 algorithm
    if quality < 3:
        reps = 0
        interval = 1.0
    else:
        if reps == 0:
            interval = 1.0
        elif reps == 1:
            interval = 6.0
        else:
            interval = interval * ef
        reps += 1

    ef = max(1.3, ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))
    next_review = time.time() + interval * 86400

    with _db().tx() as con:
        con.execute(
            "UPDATE flashcards SET ease_factor=?, interval_days=?, repetitions=?, next_review=? WHERE id=?",
            (ef, interval, reps, next_review, card_id),
        )
    return {
        "card_id": card_id,
        "ease_factor": round(ef, 2),
        "interval_days": round(interval, 1),
        "repetitions": reps,
        "next_review_hours": round((next_review - time.time()) / 3600, 1),
    }


def get_due_flashcards(limit: int = 20, course_id: str = "") -> list[dict]:
    """Get flashcards that are due for review."""
    now = time.time()
    with _db().tx() as con:
        if course_id:
            rows = con.execute(
                "SELECT * FROM flashcards WHERE next_review <= ? AND course_id=? ORDER BY next_review LIMIT ?",
                (now, course_id, limit),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM flashcards WHERE next_review <= ? ORDER BY next_review LIMIT ?",
                (now, limit),
            ).fetchall()
    return [dict(r) for r in rows]


def get_all_flashcards(course_id: str = "") -> list[dict]:
    """Get all flashcards, optionally filtered by course."""
    with _db().tx() as con:
        if course_id:
            rows = con.execute(
                "SELECT * FROM flashcards WHERE course_id=? ORDER BY created_at", (course_id,)
            ).fetchall()
        else:
            rows = con.execute("SELECT * FROM flashcards ORDER BY created_at").fetchall()
    return [dict(r) for r in rows]


def delete_flashcard(card_id: int) -> None:
    with _db().tx() as con:
        con.execute("DELETE FROM flashcards WHERE id=?", (card_id,))


def generate_flashcards_from_lecture(lecture_id: str) -> list[int]:
    """Auto-generate flashcards from a lecture's core terms."""
    lec = _db().get_lecture(lecture_id)
    if not lec:
        return []
    data = json.loads(lec.get("data") or "{}")
    terms = data.get("core_terms", [])
    objectives = data.get("learning_objectives", [])
    course_id = lec.get("course_id", "")
    card_ids = []

    for term in terms:
        cid = create_flashcard(
            front=f"Define: {term}",
            back=f"A key concept from '{lec['title']}'. Review your lecture notes for the full definition.",
            lecture_id=lecture_id,
            course_id=course_id,
        )
        card_ids.append(cid)

    for obj in objectives[:5]:
        cid = create_flashcard(
            front=f"Explain: {obj}",
            back=f"Learning objective from '{lec['title']}'.",
            lecture_id=lecture_id,
            course_id=course_id,
        )
        card_ids.append(cid)

    return card_ids


# ─── Study Timer ──────────────────────────────────────────────────────────────

def start_study_session(session_type: str = "pomodoro", lecture_id: str = "") -> int:
    """Start a new study session. Returns session ID."""
    with _db().tx() as con:
        cur = con.execute(
            "INSERT INTO study_sessions (session_type, lecture_id) VALUES (?,?)",
            (session_type, lecture_id),
        )
        return cur.lastrowid


def end_study_session(session_id: int, notes: str = "") -> dict:
    """End a study session and calculate duration."""
    now = time.time()
    with _db().tx() as con:
        row = con.execute("SELECT * FROM study_sessions WHERE id=?", (session_id,)).fetchone()
        if not row:
            return {"error": "Session not found"}
        duration = (now - row["started_at"]) / 60.0
        con.execute(
            "UPDATE study_sessions SET ended_at=?, duration_min=?, notes=? WHERE id=?",
            (now, duration, notes, session_id),
        )
    if duration >= 25:
        _db().add_xp(15, "Study session completed", "study")
    return {"session_id": session_id, "duration_min": round(duration, 1)}


def get_study_stats() -> dict:
    """Get study statistics."""
    with _db().tx() as con:
        total = con.execute("SELECT SUM(duration_min) as total FROM study_sessions WHERE ended_at IS NOT NULL").fetchone()
        count = con.execute("SELECT COUNT(*) as n FROM study_sessions WHERE ended_at IS NOT NULL").fetchone()
        today = datetime.now().strftime("%Y-%m-%d")
        today_total = con.execute(
            "SELECT SUM(duration_min) as total FROM study_sessions WHERE ended_at IS NOT NULL AND date(started_at, 'unixepoch') = ?",
            (today,)
        ).fetchone()
    return {
        "total_hours": round((total["total"] or 0) / 60, 1),
        "total_sessions": count["n"],
        "today_minutes": round(today_total["total"] or 0, 1),
    }


# ─── Notes ────────────────────────────────────────────────────────────────────

def save_note(content: str, lecture_id: str = "", course_id: str = "") -> int:
    """Save a study note. Returns note ID."""
    now = time.time()
    with _db().tx() as con:
        cur = con.execute(
            "INSERT INTO notes (lecture_id, course_id, content, updated_at) VALUES (?,?,?,?)",
            (lecture_id, course_id, content, now),
        )
        return cur.lastrowid


def update_note(note_id: int, content: str) -> None:
    with _db().tx() as con:
        con.execute(
            "UPDATE notes SET content=?, updated_at=? WHERE id=?",
            (content, time.time(), note_id),
        )


def get_notes(lecture_id: str = "", course_id: str = "") -> list[dict]:
    """Get notes, optionally filtered by lecture or course."""
    with _db().tx() as con:
        if lecture_id:
            rows = con.execute("SELECT * FROM notes WHERE lecture_id=? ORDER BY created_at DESC", (lecture_id,)).fetchall()
        elif course_id:
            rows = con.execute("SELECT * FROM notes WHERE course_id=? ORDER BY created_at DESC", (course_id,)).fetchall()
        else:
            rows = con.execute("SELECT * FROM notes ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def delete_note(note_id: int) -> None:
    with _db().tx() as con:
        con.execute("DELETE FROM notes WHERE id=?", (note_id,))


# ─── Certificates ──────────────────────────────────────────────────────────────

def generate_certificate(course_id: str, grade: str = "",
                         gpa: float = 0.0) -> dict:
    """Generate a completion certificate for a course."""
    db = _db()
    student_name = db.get_setting("student_name", "Scholar")
    courses = db.get_all_courses()
    course = next((c for c in courses if c["id"] == course_id), None)
    if not course:
        return {"error": "Course not found"}

    cert_data = {
        "course_title": course["title"],
        "student_name": student_name,
        "date": datetime.now().strftime("%B %d, %Y"),
        "grade": grade,
        "gpa": gpa,
        "institution": "The God Factory University",
    }
    with _db().tx() as con:
        cur = con.execute(
            "INSERT INTO certificates (course_id, student_name, grade, gpa, data) VALUES (?,?,?,?,?)",
            (course_id, student_name, grade, gpa, json.dumps(cert_data)),
        )
    db.add_xp(200, f"Certificate earned: {course['title']}", "certificate")
    db.unlock_achievement("first_certificate")
    return {"certificate_id": cur.lastrowid, **cert_data}


def get_certificates() -> list[dict]:
    with _db().tx() as con:
        rows = con.execute("SELECT * FROM certificates ORDER BY issued_at DESC").fetchall()
    return [dict(r) for r in rows]


# ─── Syllabus Generator ──────────────────────────────────────────────────────

def generate_syllabus(course_id: str) -> dict:
    """Generate a structured syllabus for a course."""
    db = _db()
    courses = db.get_all_courses()
    course = next((c for c in courses if c["id"] == course_id), None)
    if not course:
        return {"error": "Course not found"}

    data = json.loads(course.get("data") or "{}")
    modules = db.get_modules(course_id)
    prereqs = get_prerequisites(course_id)

    syllabus = {
        "institution": "The God Factory University",
        "course_id": course_id,
        "title": course["title"],
        "description": course.get("description", ""),
        "credits": course.get("credits", 3),
        "prerequisites": [p["prereq_id"] for p in prereqs],
        "difficulty_level": data.get("difficulty_level", "Undergraduate"),
        "schedule": [],
    }

    week = 1
    for m in modules:
        lectures = db.get_lectures(m["id"])
        syllabus["schedule"].append({
            "week": week,
            "module": m["title"],
            "lectures": [l["title"] for l in lectures],
            "objectives": [],
        })
        # Extract objectives from lecture data
        for lec in lectures:
            lec_data = json.loads(lec.get("data") or "{}")
            syllabus["schedule"][-1]["objectives"].extend(
                lec_data.get("learning_objectives", [])
            )
        week += 1

    return syllabus


# ─── Academic Calendar ────────────────────────────────────────────────────────

def add_calendar_event(event_type: str, title: str, start_date: str,
                       end_date: str = "", course_id: str = "", data: dict = None) -> int:
    with _db().tx() as con:
        cur = con.execute(
            "INSERT INTO academic_calendar (event_type, title, start_date, end_date, course_id, data) VALUES (?,?,?,?,?,?)",
            (event_type, title, start_date, end_date, course_id, json.dumps(data or {})),
        )
        return cur.lastrowid


def get_calendar_events(course_id: str = "") -> list[dict]:
    with _db().tx() as con:
        if course_id:
            rows = con.execute(
                "SELECT * FROM academic_calendar WHERE course_id=? ORDER BY start_date", (course_id,)
            ).fetchall()
        else:
            rows = con.execute("SELECT * FROM academic_calendar ORDER BY start_date").fetchall()
    return [dict(r) for r in rows]


# ─── Backup & Restore ─────────────────────────────────────────────────────────

def backup_database(output_path: Path | None = None) -> Path:
    """Create a backup of the entire database."""
    import shutil
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = ROOT / "data" / "backups" / f"university_{ts}.db"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(_db().DB_PATH), str(output_path))
    return output_path


def restore_database(backup_path: Path) -> bool:
    """Restore database from a backup file."""
    import shutil
    if not backup_path.exists():
        return False
    # Create safety backup first
    safety = ROOT / "data" / "backups" / f"pre_restore_{int(time.time())}.db"
    safety.parent.mkdir(parents=True, exist_ok=True)
    db_path = _db().DB_PATH
    shutil.copy2(str(db_path), str(safety))
    shutil.copy2(str(backup_path), str(db_path))
    return True


def list_backups() -> list[dict]:
    """List available database backups."""
    backup_dir = ROOT / "data" / "backups"
    if not backup_dir.exists():
        return []
    return [
        {
            "path": str(f),
            "name": f.name,
            "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
            "created": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        }
        for f in sorted(backup_dir.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    ]


# ─── Course Analytics ──────────────────────────────────────────────────────────

def get_course_analytics(course_id: str) -> dict:
    """Get analytics for a specific course."""
    db = _db()
    modules = db.get_modules(course_id)
    total_lectures = 0
    completed_lectures = 0
    total_watch_time = 0.0

    for m in modules:
        lectures = db.get_lectures(m["id"])
        for lec in lectures:
            total_lectures += 1
            prog = db.get_progress(lec["id"])
            if prog.get("status") == "completed":
                completed_lectures += 1
            total_watch_time += prog.get("watch_time_s", 0)

    return {
        "course_id": course_id,
        "total_lectures": total_lectures,
        "completed_lectures": completed_lectures,
        "completion_pct": round(completed_lectures / max(total_lectures, 1) * 100, 1),
        "total_watch_hours": round(total_watch_time / 3600, 1),
    }


def get_overall_analytics() -> dict:
    """Get overall university analytics."""
    db = _db()
    courses = db.get_all_courses()
    total_courses = len(courses)
    total_modules = 0
    total_lectures = 0

    for c in courses:
        mods = db.get_modules(c["id"])
        total_modules += len(mods)
        for m in mods:
            total_lectures += len(db.get_lectures(m["id"]))

    study = get_study_stats()
    flashcards = get_all_flashcards()
    due = get_due_flashcards()

    return {
        "total_courses": total_courses,
        "total_modules": total_modules,
        "total_lectures": total_lectures,
        "total_flashcards": len(flashcards),
        "flashcards_due": len(due),
        "study_hours": study["total_hours"],
        "study_sessions": study["total_sessions"],
    }
