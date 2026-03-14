"""
Course tree operations for The God Factory University.

Manages recursive course decomposition, sub-course relationships,
credit-hour tracking, pacing, jargon courses, and qualification benchmarks.

Tables created here:
  - competency_benchmarks  — real-world qualification mappings
  - qualification_progress — student progress toward qualifications
  - study_hours_log        — manual/auto time tracking per course

Queries:
  - get_child_courses()       — direct children of a course
  - get_course_tree()         — recursive CTE walk
  - get_root_course()         — walk up to root parent
  - course_completion_pct()   — sub-tree lecture completion %
  - course_credit_hours()     — sum hours in sub-tree
  - check_qualifications()    — evaluate all benchmarks
"""
from __future__ import annotations

import json
import time

# Carnegie Unit: 1 credit = 15 contact hours + 30 study hours = 45 total hours
CREDIT_HOUR_RATIO = 45

# AI policy levels for assignments
AI_POLICY_LEVELS = ("unrestricted", "assisted", "supervised", "prohibited")

# Bloom's taxonomy competency levels
BLOOMS_LEVELS = ("recall", "understanding", "application", "analysis", "synthesis", "evaluation")

# Pacing options
PACING_OPTIONS = ("fast", "standard", "slow")


# ─── Table Creation ────────────────────────────────────────────────────────────

def create_tables(tx_func) -> None:
    with tx_func() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS competency_benchmarks (
                id              TEXT PRIMARY KEY,
                name            TEXT NOT NULL,
                description     TEXT,
                school_ref      TEXT,
                required_courses TEXT,
                min_gpa         REAL DEFAULT 3.0,
                min_hours       REAL DEFAULT 0,
                category        TEXT DEFAULT 'academic',
                created_at      REAL DEFAULT (unixepoch())
            );

            CREATE TABLE IF NOT EXISTS qualification_progress (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                benchmark_id    TEXT NOT NULL,
                status          TEXT DEFAULT 'locked',
                progress_pct    REAL DEFAULT 0,
                earned_at       REAL,
                updated_at      REAL DEFAULT (unixepoch()),
                FOREIGN KEY (benchmark_id) REFERENCES competency_benchmarks(id) ON DELETE CASCADE,
                UNIQUE(benchmark_id)
            );

            CREATE TABLE IF NOT EXISTS study_hours_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id       TEXT NOT NULL,
                hours           REAL NOT NULL,
                activity_type   TEXT DEFAULT 'study',
                notes           TEXT,
                logged_at       REAL DEFAULT (unixepoch())
            );

            CREATE TABLE IF NOT EXISTS competency_scores (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id       TEXT NOT NULL,
                blooms_level    TEXT NOT NULL,
                score           REAL DEFAULT 0,
                max_score       REAL DEFAULT 100,
                assessment_id   TEXT,
                updated_at      REAL DEFAULT (unixepoch()),
                UNIQUE(course_id, blooms_level, assessment_id)
            );
        """)


# ─── Benchmark Seeding ─────────────────────────────────────────────────────────

_DEFAULT_BENCHMARKS: list[tuple[str, str, str, str, str, float, float, str]] = [
    # (id, name, description, school_ref, required_courses_json, min_gpa, min_hours, category)
    ("mit_6006", "Equivalent to MIT 6.006 (Intro to Algorithms)",
     "Covers sorting, searching, graph algorithms, dynamic programming, and complexity analysis.",
     "MIT", '["junior_cs301"]', 3.0, 135, "computer_science"),
    ("mit_6045", "Equivalent to MIT 6.045 (Automata & Complexity)",
     "Covers automata theory, computability, complexity classes, and cryptographic foundations.",
     "MIT", '["doctoral_cs600"]', 3.0, 135, "computer_science"),
    ("stanford_cs229", "Equivalent to Stanford CS229 (Machine Learning)",
     "Covers supervised/unsupervised learning, neural networks, and deep learning.",
     "Stanford", '["senior_cs450", "doctoral_cs610"]', 3.0, 270, "computer_science"),
    ("stanford_cs161", "Equivalent to Stanford CS161 (Algorithms)",
     "Covers algorithm design, analysis, sorting, graph algorithms, and NP-completeness.",
     "Stanford", '["junior_cs301"]', 3.0, 135, "computer_science"),
    ("comptia_aplus", "CompTIA A+ Equivalent",
     "Hardware, software, networking, and troubleshooting fundamentals.",
     "CompTIA", '["freshman_cs101"]', 2.5, 90, "certification"),
    ("harvard_cs50", "Equivalent to Harvard CS50 (Intro to CS)",
     "Covers abstraction, algorithms, data structures, web development, and software engineering.",
     "Harvard", '["freshman_cs101", "sophomore_cs201"]', 3.0, 200, "computer_science"),
]


def seed_benchmarks(tx_func) -> None:
    with tx_func() as con:
        for bid, name, desc, school, req, gpa, hrs, cat in _DEFAULT_BENCHMARKS:
            con.execute(
                "INSERT OR IGNORE INTO competency_benchmarks "
                "(id, name, description, school_ref, required_courses, min_gpa, min_hours, category) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (bid, name, desc, school, req, gpa, hrs, cat),
            )


# ─── Course Tree Queries ──────────────────────────────────────────────────────

def get_child_courses(parent_id: str, tx_func) -> list[dict]:
    """Direct children of a course."""
    with tx_func() as con:
        rows = con.execute(
            "SELECT * FROM courses WHERE parent_course_id = ? ORDER BY created_at",
            (parent_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_course_tree(root_id: str, tx_func) -> list[dict]:
    """Full recursive tree using CTE. Returns flat list with depth_level ordering."""
    with tx_func() as con:
        rows = con.execute("""
            WITH RECURSIVE tree AS (
                SELECT id, title, parent_course_id, depth_level, credits, pacing,
                       is_jargon_course, credit_hours, depth_target
                FROM courses WHERE id = ?
                UNION ALL
                SELECT c.id, c.title, c.parent_course_id, c.depth_level, c.credits,
                       c.pacing, c.is_jargon_course, c.credit_hours, c.depth_target
                FROM courses c
                JOIN tree t ON c.parent_course_id = t.id
            )
            SELECT * FROM tree ORDER BY depth_level, title
        """, (root_id,)).fetchall()
    return [dict(r) for r in rows]


def get_course_depth(course_id: str, tx_func) -> int:
    """Maximum depth of a course's sub-tree."""
    with tx_func() as con:
        row = con.execute("""
            WITH RECURSIVE tree AS (
                SELECT id, 0 AS depth FROM courses WHERE id = ?
                UNION ALL
                SELECT c.id, t.depth + 1
                FROM courses c JOIN tree t ON c.parent_course_id = t.id
            )
            SELECT MAX(depth) AS max_depth FROM tree
        """, (course_id,)).fetchone()
    return row["max_depth"] or 0 if row else 0


def get_root_course(course_id: str, tx_func) -> str:
    """Walk up parent chain to find root course ID."""
    with tx_func() as con:
        current = course_id
        for _ in range(50):  # safety limit
            row = con.execute(
                "SELECT parent_course_id FROM courses WHERE id = ?", (current,)
            ).fetchone()
            if not row or not row["parent_course_id"]:
                return current
            current = row["parent_course_id"]
    return current


def course_completion_pct(course_id: str, tx_func) -> float:
    """Percentage of lectures completed across the entire sub-tree."""
    with tx_func() as con:
        row = con.execute("""
            WITH RECURSIVE tree AS (
                SELECT id FROM courses WHERE id = ?
                UNION ALL
                SELECT c.id FROM courses c JOIN tree t ON c.parent_course_id = t.id
            )
            SELECT
                COUNT(l.id) AS total_lectures,
                SUM(CASE WHEN p.status = 'completed' THEN 1 ELSE 0 END) AS completed
            FROM lectures l
            JOIN tree ON l.course_id = tree.id
            LEFT JOIN progress p ON p.lecture_id = l.id
        """, (course_id,)).fetchone()
    if not row or not row["total_lectures"]:
        return 0.0
    return round((row["completed"] or 0) / row["total_lectures"] * 100, 1)


def course_credit_hours(course_id: str, tx_func) -> float:
    """Sum of logged study hours across entire sub-tree."""
    with tx_func() as con:
        # Instruction time from lecture watch_time
        row1 = con.execute("""
            WITH RECURSIVE tree AS (
                SELECT id FROM courses WHERE id = ?
                UNION ALL
                SELECT c.id FROM courses c JOIN tree t ON c.parent_course_id = t.id
            )
            SELECT COALESCE(SUM(p.watch_time_s), 0) / 3600.0 AS watch_hours
            FROM lectures l
            JOIN tree ON l.course_id = tree.id
            LEFT JOIN progress p ON p.lecture_id = l.id
        """, (course_id,)).fetchone()
        watch_hours = row1["watch_hours"] if row1 else 0.0

        # Manual study hours
        row2 = con.execute("""
            WITH RECURSIVE tree AS (
                SELECT id FROM courses WHERE id = ?
                UNION ALL
                SELECT c.id FROM courses c JOIN tree t ON c.parent_course_id = t.id
            )
            SELECT COALESCE(SUM(h.hours), 0) AS study_hours
            FROM study_hours_log h
            JOIN tree ON h.course_id = tree.id
        """, (course_id,)).fetchone()
        study_hours = row2["study_hours"] if row2 else 0.0

    return round(watch_hours + study_hours, 2)


def hours_to_credits(hours: float) -> float:
    """Convert total hours to credits using Carnegie Unit standard."""
    return round(hours / CREDIT_HOUR_RATIO, 2)


# ─── Study Hours Logging ──────────────────────────────────────────────────────

def log_study_hours(course_id: str, hours: float, activity_type: str = "study",
                    notes: str = "", tx_func=None) -> None:
    if tx_func is None:
        return
    with tx_func() as con:
        con.execute(
            "INSERT INTO study_hours_log (course_id, hours, activity_type, notes) VALUES (?, ?, ?, ?)",
            (course_id, hours, activity_type, notes),
        )


def get_study_hours(course_id: str, tx_func) -> list[dict]:
    """Get study hour log entries for a course."""
    with tx_func() as con:
        rows = con.execute(
            "SELECT * FROM study_hours_log WHERE course_id = ? ORDER BY logged_at DESC",
            (course_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ─── Qualifications ───────────────────────────────────────────────────────────

def get_all_benchmarks(tx_func) -> list[dict]:
    with tx_func() as con:
        rows = con.execute("SELECT * FROM competency_benchmarks ORDER BY category, name").fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["required_courses"] = json.loads(d.get("required_courses") or "[]")
        result.append(d)
    return result


def check_qualifications(tx_func, compute_gpa_func, credits_func) -> list[dict]:
    """Evaluate all benchmarks against current student progress. Returns updated list."""
    benchmarks = get_all_benchmarks(tx_func)
    gpa, _ = compute_gpa_func()
    results = []

    for bm in benchmarks:
        required = bm["required_courses"]
        total_required = len(required) if required else 1
        completed_count = 0

        with tx_func() as con:
            for cid in required:
                row = con.execute("""
                    SELECT COUNT(*) AS n FROM lectures l
                    JOIN progress p ON p.lecture_id = l.id
                    WHERE l.course_id = ? AND p.status = 'completed'
                """, (cid,)).fetchone()
                if row and row["n"] > 0:
                    completed_count += 1

        # Check hours
        total_hours = 0.0
        for cid in required:
            total_hours += course_credit_hours(cid, tx_func)

        course_pct = (completed_count / total_required * 100) if total_required else 0
        hours_pct = (total_hours / bm["min_hours"] * 100) if bm["min_hours"] else 100
        gpa_met = gpa >= bm["min_gpa"]

        # Overall progress: weighted average
        progress = min(course_pct * 0.5 + hours_pct * 0.3 + (100 if gpa_met else 0) * 0.2, 100)

        status = "locked"
        earned_at = None
        if progress >= 100 and gpa_met:
            status = "earned"
            earned_at = time.time()
        elif progress > 0:
            status = "in_progress"

        # Upsert progress
        with tx_func() as con:
            con.execute("""
                INSERT INTO qualification_progress (benchmark_id, status, progress_pct, earned_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(benchmark_id) DO UPDATE SET
                    status = excluded.status,
                    progress_pct = excluded.progress_pct,
                    earned_at = COALESCE(qualification_progress.earned_at, excluded.earned_at),
                    updated_at = excluded.updated_at
            """, (bm["id"], status, round(progress, 1), earned_at, time.time()))

        results.append({
            **bm,
            "status": status,
            "progress_pct": round(progress, 1),
            "earned_at": earned_at,
            "course_progress": f"{completed_count}/{total_required}",
            "hours_logged": round(total_hours, 1),
            "gpa_met": gpa_met,
        })

    return results


def get_qualifications(tx_func) -> list[dict]:
    """Get current qualification progress without recomputing."""
    with tx_func() as con:
        rows = con.execute("""
            SELECT b.*, q.status AS q_status, q.progress_pct, q.earned_at AS q_earned_at
            FROM competency_benchmarks b
            LEFT JOIN qualification_progress q ON q.benchmark_id = b.id
            ORDER BY b.category, b.name
        """).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["required_courses"] = json.loads(d.get("required_courses") or "[]")
        d["status"] = d.pop("q_status", None) or "locked"
        d["earned_at"] = d.pop("q_earned_at", None)
        result.append(d)
    return result


def get_qualification_roadmap(benchmark_id: str, tx_func) -> dict:
    """Get remaining courses needed for a specific qualification."""
    with tx_func() as con:
        row = con.execute(
            "SELECT * FROM competency_benchmarks WHERE id = ?", (benchmark_id,)
        ).fetchone()
    if not row:
        return {"error": "Benchmark not found"}

    bm = dict(row)
    required = json.loads(bm.get("required_courses") or "[]")
    completed = []
    remaining = []

    for cid in required:
        with tx_func() as con:
            r = con.execute("""
                SELECT COUNT(*) AS n FROM lectures l
                JOIN progress p ON p.lecture_id = l.id
                WHERE l.course_id = ? AND p.status = 'completed'
            """, (cid,)).fetchone()
        if r and r["n"] > 0:
            completed.append(cid)
        else:
            remaining.append(cid)

    return {
        "benchmark": bm["name"],
        "total_required": len(required),
        "completed": completed,
        "remaining": remaining,
        "hours_needed": bm.get("min_hours", 0),
        "hours_logged": sum(course_credit_hours(cid, tx_func) for cid in required),
        "min_gpa": bm.get("min_gpa", 0),
    }


# ─── Pacing Templates ─────────────────────────────────────────────────────────

from core.decomposition import (
    PACING_TEMPLATES,
    get_pacing_for_course,
    build_decomposition_prompt,
    build_jargon_prompt,
    build_verification_prompt,
    register_sub_courses,
)


# ─── AI Policy Defaults ───────────────────────────────────────────────────────

# Default AI policies per assignment type / subject
AI_POLICY_DEFAULTS: dict[str, dict] = {
    "exam": {
        "level": "prohibited",
        "allowed_uses": [],
        "prohibited_uses": ["all"],
        "verification_type": "none",
    },
    "quiz": {
        "level": "prohibited",
        "allowed_uses": [],
        "prohibited_uses": ["all"],
        "verification_type": "none",
    },
    "homework": {
        "level": "assisted",
        "allowed_uses": ["research", "grammar_check", "code_debugging"],
        "prohibited_uses": ["direct_answers", "essay_generation"],
        "verification_type": "original_example",
    },
    "project": {
        "level": "supervised",
        "allowed_uses": ["research", "scaffolding", "debugging"],
        "prohibited_uses": ["complete_solutions"],
        "verification_type": "oral_explanation",
    },
    "lab": {
        "level": "supervised",
        "allowed_uses": ["debugging", "documentation_lookup"],
        "prohibited_uses": ["complete_implementations"],
        "verification_type": "original_example",
    },
    "verification": {
        "level": "prohibited",
        "allowed_uses": [],
        "prohibited_uses": ["all"],
        "verification_type": "original_example",
    },
}


def get_default_ai_policy(assignment_type: str) -> dict:
    """Get the default AI policy for a given assignment type."""
    return AI_POLICY_DEFAULTS.get(
        assignment_type, AI_POLICY_DEFAULTS["homework"])


def get_assignment_ai_policy(assignment: dict) -> dict:
    """Get AI policy for an assignment — stored policy or default."""
    stored = assignment.get("ai_policy")
    if stored:
        if isinstance(stored, str):
            try:
                return json.loads(stored)
            except (json.JSONDecodeError, ValueError):
                pass
        elif isinstance(stored, dict):
            return stored
    return get_default_ai_policy(assignment.get("type", "homework"))


# ─── Competency Tracking (Bloom's Taxonomy) ────────────────────────────────────

def record_competency_score(course_id: str, blooms_level: str, score: float,
                            max_score: float = 100, assessment_id: str = "",
                            tx_func=None) -> None:
    """Record a competency score at a Bloom's taxonomy level for a course."""
    if blooms_level not in BLOOMS_LEVELS:
        return
    if tx_func is None:
        return
    with tx_func() as con:
        con.execute("""
            INSERT INTO competency_scores (course_id, blooms_level, score, max_score, assessment_id, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(course_id, blooms_level, assessment_id) DO UPDATE SET
                score = excluded.score,
                max_score = excluded.max_score,
                updated_at = excluded.updated_at
        """, (course_id, blooms_level, score, max_score, assessment_id, time.time()))


def get_competency_profile(course_id: str, tx_func) -> dict:
    """Get average competency scores per Bloom's level for a course."""
    with tx_func() as con:
        rows = con.execute("""
            SELECT blooms_level,
                   AVG(score) AS avg_score,
                   AVG(max_score) AS avg_max,
                   COUNT(*) AS assessments
            FROM competency_scores
            WHERE course_id = ?
            GROUP BY blooms_level
        """, (course_id,)).fetchall()
    profile = {}
    for level in BLOOMS_LEVELS:
        profile[level] = {"avg_score": 0, "avg_max": 100, "assessments": 0, "pct": 0}
    for r in rows:
        d = dict(r)
        level = d["blooms_level"]
        pct = round((d["avg_score"] / d["avg_max"] * 100) if d["avg_max"] else 0, 1)
        profile[level] = {
            "avg_score": round(d["avg_score"], 1),
            "avg_max": round(d["avg_max"], 1),
            "assessments": d["assessments"],
            "pct": pct,
        }
    return profile


def check_mastery(course_id: str, tx_func,
                  min_pct: float = 70.0) -> dict:
    """Check if student has met minimum competency at all applicable Bloom's levels."""
    profile = get_competency_profile(course_id, tx_func)
    mastered_levels = []
    failed_levels = []
    untested_levels = []
    for level in BLOOMS_LEVELS:
        data = profile[level]
        if data["assessments"] == 0:
            untested_levels.append(level)
        elif data["pct"] >= min_pct:
            mastered_levels.append(level)
        else:
            failed_levels.append(level)
    return {
        "course_id": course_id,
        "mastered": mastered_levels,
        "failed": failed_levels,
        "untested": untested_levels,
        "is_complete": len(failed_levels) == 0 and len(untested_levels) == 0,
        "profile": profile,
    }


# ─── Benchmark Comparison & Gap Analysis ───────────────────────────────────────

def get_benchmark_comparison(benchmark_id: str, tx_func) -> dict:
    """Compare student's coursework against a real-world benchmark.

    Returns topic coverage, hours comparison, gap analysis, and rigor rating.
    """
    with tx_func() as con:
        row = con.execute(
            "SELECT * FROM competency_benchmarks WHERE id = ?", (benchmark_id,)
        ).fetchone()
    if not row:
        return {"error": "Benchmark not found"}

    bm = dict(row)
    required = json.loads(bm.get("required_courses") or "[]")

    # Gather topics from each course's modules
    covered_topics = []
    total_topics = 0
    total_hours = 0.0
    for cid in required:
        with tx_func() as con:
            modules = con.execute(
                "SELECT title FROM modules WHERE course_id = ? ORDER BY order_index",
                (cid,),
            ).fetchall()
        topics_for_course = [m["title"] for m in modules]
        total_topics += len(topics_for_course)

        # Check which topics have at least one completed lecture
        for mod_row in modules:
            with tx_func() as con:
                completed = con.execute("""
                    SELECT COUNT(*) AS n FROM lectures l
                    JOIN modules m ON l.module_id = m.id
                    JOIN progress p ON p.lecture_id = l.id
                    WHERE m.title = ? AND m.course_id = ? AND p.status = 'completed'
                """, (mod_row["title"], cid)).fetchone()
            if completed and completed["n"] > 0:
                covered_topics.append(mod_row["title"])

        total_hours += course_credit_hours(cid, tx_func)

    covered_count = len(covered_topics)
    coverage_pct = round(covered_count / total_topics * 100, 1) if total_topics else 0
    hours_pct = round(total_hours / bm["min_hours"] * 100, 1) if bm["min_hours"] else 100
    rigor_pct = round((coverage_pct * 0.6 + hours_pct * 0.4), 1)

    # Gap: topics not yet covered
    all_topics = []
    for cid in required:
        with tx_func() as con:
            modules = con.execute(
                "SELECT title FROM modules WHERE course_id = ? ORDER BY order_index",
                (cid,),
            ).fetchall()
        all_topics.extend(m["title"] for m in modules)
    gap_topics = [t for t in all_topics if t not in covered_topics]

    return {
        "benchmark": bm["name"],
        "school": bm.get("school_ref", ""),
        "total_topics": total_topics,
        "covered_topics": covered_count,
        "coverage_pct": coverage_pct,
        "hours_logged": round(total_hours, 1),
        "hours_required": bm["min_hours"],
        "hours_pct": hours_pct,
        "rigor_pct": rigor_pct,
        "gap_topics": gap_topics,
    }
