"""One-shot rebranding script: Arcane University -> The God Factory University."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = {".venv", "__pycache__", ".git", "node_modules", "data"}

REPLACEMENTS = [
    ("Arcane University", "The God Factory University"),
    ("ARCANE UNIVERSITY", "THE GOD FACTORY UNIVERSITY"),
    ("Arcane university", "The God Factory University"),
    ("arcane university", "The God Factory University"),
    ("arcane_university", "god_factory"),
    ("_ARCANE_TEST_DB", "_GF_TEST_DB"),
    ("Arcane cyan", "God Factory cyan"),
    ("arcane_header", "gf_header"),
    ('"Arcane"', '"Transcendent"'),
    ("Arcane Adept", "Transcendent Adept"),
    ("School of Arcane Computing", "School of Computer Science"),
    ("College of the Arcane Arts", "College of Liberal Arts"),
    ("Arcane University Course", "God Factory University Course"),
    ("dungeon-academic", "dark-academic"),
    ("dungeon academic", "dark academic"),
    ("Dungeon-academic", "Dark-academic"),
    ("dungeon hierarchy", "progression hierarchy"),
    ("dungeon ranks", "progression ranks"),
    ("dungeon milestones", "milestones"),
    ("Dungeon completion celebration", "Completion celebration"),
    ("dungeon-themed gamification", "knowledge-themed gamification"),
    ("Hello from Arcane University", "Hello from The God Factory University"),
    ("arcane apparatus", "knowledge apparatus"),
    ("arcane academy", "God Factory"),
    ("arcane.log", "god_factory.log"),
]

files_changed = 0
for path in sorted(ROOT.rglob("*")):
    if any(skip in path.parts for skip in SKIP):
        continue
    if path.suffix not in (".py", ".md", ".json", ".bat", ".sh", ".txt"):
        continue
    if path.name in ("notes.txt", "rebrand.py"):
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        continue
    original = text
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    if text != original:
        path.write_text(text, encoding="utf-8")
        files_changed += 1
        print(f"  Updated: {path.relative_to(ROOT)}")

print(f"\nDone: {files_changed} files updated")
