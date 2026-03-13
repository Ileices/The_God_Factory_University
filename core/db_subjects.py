"""
Subject taxonomy for Arcane University.
Hierarchical subject tree: domain → field → subfield.
Extracted as sub-module per DEVELOPMENT.md Rule 5.
"""
from __future__ import annotations


# (id, parent_id, name, level)
_TAXONOMY: list[tuple[str, str | None, str, str]] = [
    # ── Domains (top level) ─────────────────────────────────────────────────
    ("math",        None,           "Mathematics",          "domain"),
    ("science",     None,           "Science",              "domain"),
    ("english",     None,           "English & Literature", "domain"),
    ("history",     None,           "History",              "domain"),
    ("cs",          None,           "Computer Science",     "domain"),
    ("arts",        None,           "Arts",                 "domain"),
    ("socsci",      None,           "Social Sciences",      "domain"),
    ("philosophy",  None,           "Philosophy",           "domain"),
    ("business",    None,           "Business",             "domain"),
    ("health",      None,           "Health Sciences",      "domain"),
    # ── Math subfields ──────────────────────────────────────────────────────
    ("math_arith",      "math",     "Arithmetic",           "field"),
    ("math_algebra",    "math",     "Algebra",              "field"),
    ("math_geometry",   "math",     "Geometry",             "field"),
    ("math_trig",       "math",     "Trigonometry",         "field"),
    ("math_calc",       "math",     "Calculus",             "field"),
    ("math_stats",      "math",     "Statistics & Probability", "field"),
    ("math_linear",     "math",     "Linear Algebra",       "field"),
    ("math_discrete",   "math",     "Discrete Mathematics", "field"),
    # ── Science subfields ───────────────────────────────────────────────────
    ("sci_physics",     "science",  "Physics",              "field"),
    ("sci_chemistry",   "science",  "Chemistry",            "field"),
    ("sci_biology",     "science",  "Biology",              "field"),
    ("sci_earth",       "science",  "Earth Science",        "field"),
    ("sci_astronomy",   "science",  "Astronomy",            "field"),
    ("sci_enviro",      "science",  "Environmental Science","field"),
    # ── English subfields ───────────────────────────────────────────────────
    ("eng_grammar",     "english",  "Grammar & Writing",    "field"),
    ("eng_literature",  "english",  "Literature",           "field"),
    ("eng_composition", "english",  "Composition",          "field"),
    ("eng_rhetoric",    "english",  "Rhetoric",             "field"),
    # ── History subfields ───────────────────────────────────────────────────
    ("hist_world",      "history",  "World History",        "field"),
    ("hist_us",         "history",  "US History",           "field"),
    ("hist_euro",       "history",  "European History",     "field"),
    ("hist_ancient",    "history",  "Ancient History",      "field"),
    # ── CS subfields ────────────────────────────────────────────────────────
    ("cs_intro",        "cs",       "Intro to Programming", "field"),
    ("cs_dsa",          "cs",       "Data Structures & Algorithms", "field"),
    ("cs_web",          "cs",       "Web Development",      "field"),
    ("cs_ml",           "cs",       "Machine Learning & AI","field"),
    ("cs_db",           "cs",       "Databases",            "field"),
    ("cs_systems",      "cs",       "Operating Systems",    "field"),
    ("cs_networks",     "cs",       "Computer Networks",    "field"),
    # ── Arts subfields ──────────────────────────────────────────────────────
    ("arts_visual",     "arts",     "Visual Arts",          "field"),
    ("arts_music",      "arts",     "Music",                "field"),
    ("arts_theater",    "arts",     "Theater & Drama",      "field"),
    ("arts_film",       "arts",     "Film Studies",         "field"),
    # ── Social Sciences subfields ───────────────────────────────────────────
    ("soc_psych",       "socsci",   "Psychology",           "field"),
    ("soc_sociology",   "socsci",   "Sociology",            "field"),
    ("soc_econ",        "socsci",   "Economics",            "field"),
    ("soc_polisci",     "socsci",   "Political Science",    "field"),
    ("soc_anthro",      "socsci",   "Anthropology",         "field"),
    # ── Philosophy subfields ────────────────────────────────────────────────
    ("phil_ethics",     "philosophy","Ethics",               "field"),
    ("phil_logic",      "philosophy","Logic",                "field"),
    ("phil_metaph",     "philosophy","Metaphysics",          "field"),
    ("phil_epist",      "philosophy","Epistemology",         "field"),
    # ── Business subfields ──────────────────────────────────────────────────
    ("biz_accounting",  "business", "Accounting",           "field"),
    ("biz_finance",     "business", "Finance",              "field"),
    ("biz_marketing",   "business", "Marketing",            "field"),
    ("biz_mgmt",        "business", "Management",           "field"),
    ("biz_entrep",      "business", "Entrepreneurship",     "field"),
    # ── Health Sciences subfields ───────────────────────────────────────────
    ("hlth_anatomy",    "health",   "Anatomy & Physiology", "field"),
    ("hlth_nursing",    "health",   "Nursing",              "field"),
    ("hlth_nutrition",  "health",   "Nutrition",            "field"),
    ("hlth_pubhealth",  "health",   "Public Health",        "field"),
]


def create_tables(tx_func) -> None:
    """Create subjects table if it doesn't exist."""
    with tx_func() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS subjects (
                id          TEXT PRIMARY KEY,
                parent_id   TEXT,
                name        TEXT NOT NULL,
                level       TEXT NOT NULL DEFAULT 'domain',
                FOREIGN KEY (parent_id) REFERENCES subjects(id)
            )
        """)


def seed_subjects(tx_func) -> None:
    """Insert taxonomy entries if they don't exist yet."""
    with tx_func() as con:
        for sid, parent, name, level in _TAXONOMY:
            con.execute(
                "INSERT OR IGNORE INTO subjects (id, parent_id, name, level) VALUES (?, ?, ?, ?)",
                (sid, parent, name, level),
            )


def get_domains(tx_func) -> list[dict]:
    """Return top-level domains."""
    with tx_func() as con:
        rows = con.execute(
            "SELECT * FROM subjects WHERE parent_id IS NULL ORDER BY name"
        ).fetchall()
    return [dict(r) for r in rows]


def get_children(parent_id: str, tx_func) -> list[dict]:
    """Return direct children of a subject."""
    with tx_func() as con:
        rows = con.execute(
            "SELECT * FROM subjects WHERE parent_id=? ORDER BY name", (parent_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_subject(subject_id: str, tx_func) -> dict | None:
    with tx_func() as con:
        row = con.execute("SELECT * FROM subjects WHERE id=?", (subject_id,)).fetchone()
    return dict(row) if row else None


def get_all_subjects(tx_func) -> list[dict]:
    """Return all subjects ordered by level then name."""
    with tx_func() as con:
        rows = con.execute("SELECT * FROM subjects ORDER BY level, name").fetchall()
    return [dict(r) for r in rows]
