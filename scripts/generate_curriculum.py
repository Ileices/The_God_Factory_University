"""
Curriculum generator for The God Factory University (God Factory).

Generates structured course JSON for all grade levels and subjects,
ready for bulk import via core.database.bulk_import_json().

Usage:
    python scripts/generate_curriculum.py                 # generate all
    python scripts/generate_curriculum.py --level K       # one grade level
    python scripts/generate_curriculum.py --domain math   # one domain
    python scripts/generate_curriculum.py --import        # generate + import into DB
    python scripts/generate_curriculum.py --dry-run       # validate only, no DB write

Output: data/curriculum/<level>/<subject>.json files
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUTPUT_DIR = ROOT / "data" / "curriculum"

# ─── Curriculum Templates ──────────────────────────────────────────────────────

# Grade-level bands → subjects taught at that level
_CURRICULUM: dict[str, dict] = {
    # Elementary K-5
    "K": {
        "name": "Kindergarten",
        "subjects": {
            "reading": ("Reading Readiness", ["Letter Recognition", "Phonics Basics", "Sight Words", "Story Time"]),
            "math": ("Math Foundations", ["Counting to 20", "Shapes & Patterns", "Comparing Sizes", "Simple Addition"]),
            "science": ("Science Exploration", ["Five Senses", "Weather & Seasons", "Plants & Animals", "Earth & Sky"]),
            "social_studies": ("My World", ["Family & Community", "Rules & Safety", "Maps & Places", "Holidays & Traditions"]),
            "arts": ("Creative Arts", ["Drawing & Coloring", "Music & Rhythm", "Movement & Dance"]),
        },
    },
    "1": {
        "name": "1st Grade",
        "subjects": {
            "reading": ("Reading & Writing I", ["Phonics Mastery", "Sentence Building", "Reading Fluency", "Story Comprehension"]),
            "math": ("Math I", ["Addition & Subtraction to 20", "Place Value", "Measurement Basics", "Intro to Fractions"]),
            "science": ("Science I", ["Animal Habitats", "Matter States", "Push & Pull Forces", "Day & Night Cycle"]),
            "social_studies": ("Communities", ["Neighborhoods", "Community Helpers", "United States Basics", "Citizenship"]),
        },
    },
    "2": {
        "name": "2nd Grade",
        "subjects": {
            "reading": ("Reading & Writing II", ["Chapter Books", "Nonfiction Reading", "Writing Paragraphs", "Poetry Intro"]),
            "math": ("Math II", ["Addition & Subtraction to 100", "Skip Counting", "Telling Time", "Money Basics"]),
            "science": ("Science II", ["Life Cycles", "Ecosystems Intro", "Simple Machines", "Water Cycle"]),
        },
    },
    "3": {
        "name": "3rd Grade",
        "subjects": {
            "reading": ("Language Arts III", ["Reading Comprehension", "Writing Essays", "Grammar Rules", "Vocabulary Building"]),
            "math": ("Math III", ["Multiplication & Division", "Fractions Intro", "Geometry Basics", "Data & Graphs"]),
            "science": ("Science III", ["Earth Science", "Human Body Systems", "Energy & Light", "Scientific Method"]),
            "social_studies": ("History & Geography", ["US Regions", "World Cultures", "Map Skills Advanced", "Government Basics"]),
        },
    },
    "4": {
        "name": "4th Grade",
        "subjects": {
            "reading": ("Language Arts IV", ["Research Writing", "Literary Analysis", "Persuasive Writing", "Advanced Grammar"]),
            "math": ("Math IV", ["Long Division", "Fraction Operations", "Decimals", "Area & Perimeter"]),
            "science": ("Science IV", ["Electricity & Magnetism", "Rocks & Minerals", "Food Chains", "Weather Systems"]),
        },
    },
    "5": {
        "name": "5th Grade",
        "subjects": {
            "reading": ("Language Arts V", ["Novel Studies", "Creative Writing", "Public Speaking", "Media Literacy"]),
            "math": ("Math V", ["Decimal Operations", "Volume & Geometry", "Coordinate Planes", "Order of Operations"]),
            "science": ("Science V", ["Solar System", "Chemistry Basics", "Genetics Intro", "Engineering Design"]),
            "social_studies": ("US History", ["Colonial America", "American Revolution", "Westward Expansion", "Civil War"]),
        },
    },
    # Middle School 6-8
    "6": {
        "name": "6th Grade",
        "subjects": {
            "ela": ("English Language Arts 6", ["Narrative Writing", "Informational Text", "Grammar & Mechanics", "Vocabulary"]),
            "math": ("Math 6", ["Ratios & Proportions", "Integers", "Expressions & Equations", "Statistics"]),
            "science": ("Earth Science", ["Plate Tectonics", "Weather & Climate", "Oceanography", "Space Science"]),
            "social_studies": ("Ancient Civilizations", ["Mesopotamia & Egypt", "Greece & Rome", "China & India", "Medieval World"]),
            "spanish": ("Spanish I", ["Greetings & Basics", "Family & Home", "School & Daily Life", "Food & Culture"]),
        },
    },
    "7": {
        "name": "7th Grade",
        "subjects": {
            "ela": ("English Language Arts 7", ["Argumentative Writing", "Poetry Analysis", "Research Skills", "Rhetoric"]),
            "math": ("Pre-Algebra", ["Proportional Relationships", "Rational Numbers", "Linear Equations", "Probability"]),
            "science": ("Life Science", ["Cell Biology", "Genetics & Heredity", "Evolution", "Human Body Systems"]),
            "social_studies": ("World Geography", ["Physical Geography", "Cultural Geography", "Economic Geography", "Political Geography"]),
        },
    },
    "8": {
        "name": "8th Grade",
        "subjects": {
            "ela": ("English Language Arts 8", ["Argumentative Essays", "Shakespeare Intro", "Memoir Writing", "Critical Thinking"]),
            "math": ("Algebra I", ["Linear Functions", "Systems of Equations", "Polynomials", "Quadratic Equations"]),
            "science": ("Physical Science", ["Forces & Motion", "Energy Transformations", "Waves & Sound", "Chemical Reactions"]),
            "social_studies": ("US History to 1900", ["Constitution", "Civil War & Reconstruction", "Industrialization", "Immigration"]),
        },
    },
    # High School 9-12
    "9": {
        "name": "9th Grade",
        "subjects": {
            "english": ("English I / World Literature", ["The Odyssey", "World Mythology", "Essay Writing", "Rhetoric & Persuasion"]),
            "math": ("Geometry", ["Foundations of Geometry", "Triangles & Congruence", "Similarity & Trigonometry", "Circles & Area"]),
            "science": ("Biology", ["Cell Structure & Function", "DNA & Genetics", "Evolution & Ecology", "Human Biology"]),
            "social_studies": ("World History", ["Renaissance & Reformation", "Age of Exploration", "Revolutions", "Modern Era"]),
            "cs": ("Intro to Computer Science", ["Computational Thinking", "Python Basics", "Data & Algorithms", "Web Fundamentals"]),
        },
    },
    "10": {
        "name": "10th Grade",
        "subjects": {
            "english": ("English II / American Literature", ["Colonial & Revolutionary Lit", "Romanticism & Transcendentalism", "Realism & Naturalism", "Modern American Lit"]),
            "math": ("Algebra II", ["Complex Numbers", "Polynomial Functions", "Exponential & Logarithmic Functions", "Sequences & Series"]),
            "science": ("Chemistry", ["Atomic Structure", "Chemical Bonding", "Stoichiometry", "Thermodynamics"]),
            "social_studies": ("US Government & Economics", ["Constitution & Bill of Rights", "Branches of Government", "Microeconomics", "Macroeconomics"]),
        },
    },
    "11": {
        "name": "11th Grade",
        "subjects": {
            "english": ("English III / British Literature", ["Beowulf & Medieval Lit", "Shakespeare", "Romantic Period", "Victorian & Modern"]),
            "math": ("Pre-Calculus", ["Trigonometric Functions", "Analytic Geometry", "Limits & Continuity", "Intro to Derivatives"]),
            "science": ("Physics", ["Kinematics", "Forces & Newton's Laws", "Energy & Momentum", "Waves & Optics"]),
            "social_studies": ("US History Modern", ["World War I & II", "Cold War", "Civil Rights Movement", "Contemporary America"]),
            "ap_cs": ("AP Computer Science A", ["Java Fundamentals", "Object-Oriented Design", "Data Structures", "Algorithms & Complexity"]),
        },
    },
    "12": {
        "name": "12th Grade",
        "subjects": {
            "english": ("English IV / World Literature & Composition", ["Existentialism & Absurdism", "Postcolonial Literature", "Research Paper", "Senior Thesis"]),
            "math": ("AP Calculus AB", ["Limits & Derivatives", "Applications of Derivatives", "Integrals", "Differential Equations Intro"]),
            "science": ("AP Biology / Environmental Science", ["Molecular Biology", "Ecology", "Environmental Systems", "Sustainability"]),
            "capstone": ("Senior Capstone Project", ["Project Proposal", "Research & Development", "Implementation", "Presentation & Defense"]),
        },
    },
    # Undergraduate
    "freshman": {
        "name": "College Freshman",
        "subjects": {
            "comp": ("English Composition I & II", ["Academic Writing", "Research Methods", "Citation & Sources", "Argumentative Essays"]),
            "math": ("College Algebra / Precalculus", ["Functions & Graphs", "Polynomial & Rational Functions", "Exponential & Log Functions", "Trigonometry Review"]),
            "science": ("General Biology / Chemistry", ["Intro Biology", "Intro Chemistry", "Lab Methods", "Scientific Writing"]),
            "humanities": ("Intro to Humanities", ["Philosophy", "Art History", "World Religions", "Ethics"]),
            "cs101": ("CS 101: Intro to Programming", ["Variables & Types", "Control Flow", "Functions & Modules", "Data Structures Intro"]),
            "psych101": ("Psychology 101", ["Foundations of Psychology", "Biological Bases", "Learning & Memory", "Social Psychology"]),
        },
    },
    "sophomore": {
        "name": "College Sophomore",
        "subjects": {
            "lit": ("World Literature", ["Classical Literature", "Renaissance Literature", "Modern World Lit", "Contemporary Global Fiction"]),
            "calc": ("Calculus I & II", ["Differential Calculus", "Integral Calculus", "Applications", "Series & Sequences"]),
            "stats": ("Statistics", ["Descriptive Statistics", "Probability", "Inferential Statistics", "Regression Analysis"]),
            "cs201": ("CS 201: Data Structures", ["Arrays & Linked Lists", "Trees & Graphs", "Hash Tables", "Algorithm Analysis"]),
            "econ": ("Economics", ["Microeconomics", "Macroeconomics", "International Trade", "Public Policy"]),
        },
    },
    "junior": {
        "name": "College Junior",
        "subjects": {
            "cs301": ("CS 301: Algorithms", ["Sorting & Searching", "Graph Algorithms", "Dynamic Programming", "NP-Completeness"]),
            "cs350": ("CS 350: Operating Systems", ["Processes & Threads", "Memory Management", "File Systems", "Concurrency"]),
            "math301": ("Linear Algebra", ["Vector Spaces", "Linear Transformations", "Eigenvalues", "Applications"]),
            "research": ("Research Methods", ["Literature Review", "Experimental Design", "Data Collection", "Statistical Analysis"]),
        },
    },
    "senior": {
        "name": "College Senior",
        "subjects": {
            "cs401": ("CS 401: Software Engineering", ["Requirements & Design", "Agile Methods", "Testing & QA", "Project Management"]),
            "cs450": ("CS 450: Machine Learning", ["Supervised Learning", "Unsupervised Learning", "Neural Networks", "Deep Learning Intro"]),
            "capstone": ("Senior Thesis / Capstone", ["Proposal & Literature Review", "Methodology", "Implementation & Results", "Defense & Publication"]),
            "ethics": ("Professional Ethics", ["Tech Ethics", "Privacy & Security", "AI Ethics", "Professional Responsibility"]),
        },
    },
    # Graduate
    "masters": {
        "name": "Master's Level",
        "subjects": {
            "cs500": ("CS 500: Advanced Algorithms", ["Randomized Algorithms", "Approximation Algorithms", "Online Algorithms", "Computational Geometry"]),
            "cs510": ("CS 510: Distributed Systems", ["Consensus Protocols", "Replication & Consistency", "Fault Tolerance", "Cloud Architecture"]),
            "cs520": ("CS 520: Advanced AI", ["Search & Planning", "Probabilistic Reasoning", "Reinforcement Learning", "Natural Language Processing"]),
            "research": ("Graduate Research Seminar", ["Research Methodology", "Paper Writing", "Peer Review", "Grant Proposals"]),
            "thesis": ("Thesis Preparation", ["Topic Selection", "Literature Survey", "Methodology Chapter", "Results & Discussion"]),
        },
    },
    "doctoral": {
        "name": "Doctoral Level",
        "subjects": {
            "cs600": ("CS 600: Theory of Computation", ["Automata Theory", "Complexity Theory", "Cryptography Basics", "Quantum Computing Intro"]),
            "cs610": ("CS 610: Advanced Machine Learning", ["Generative Models", "Meta-Learning", "Continual Learning", "Interpretable AI"]),
            "quals": ("Comprehensive Exam Prep", ["Breadth Exam Review", "Depth Exam Review", "Oral Exam Preparation", "Written Exam Strategies"]),
            "dissertation": ("Dissertation", ["Proposal Defense", "Research Execution", "Writing Chapters", "Final Defense"]),
        },
    },
}


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _generate_course_json(level_id: str, subject_key: str, title: str,
                          modules: list[str], level_name: str) -> dict:
    """Generate a valid course JSON dict for one course."""
    course_id = f"{level_id}_{subject_key}"
    credit_map = {
        "K": 1, "1": 1, "2": 1, "3": 2, "4": 2, "5": 2,
        "6": 2, "7": 2, "8": 2, "9": 3, "10": 3, "11": 3, "12": 3,
        "freshman": 3, "sophomore": 3, "junior": 3, "senior": 3,
        "masters": 3, "doctoral": 3, "postdoc": 3,
    }
    credits = credit_map.get(level_id, 3)

    course = {
        "course_id": course_id,
        "title": f"{title} ({level_name})",
        "description": f"{title} for {level_name} students.",
        "credits": credits,
        "subject_id": subject_key,
        "modules": [],
    }

    for i, mod_title in enumerate(modules):
        mod_id = f"{course_id}_m{i+1}"
        mod = {
            "module_id": mod_id,
            "title": mod_title,
            "lectures": [],
        }
        # Generate 3 lectures per module
        for j in range(3):
            lec_id = f"{mod_id}_l{j+1}"
            subtopics = [
                f"Introduction to {mod_title}",
                f"Core Concepts of {mod_title}",
                f"Applications of {mod_title}",
            ]
            lec = {
                "lecture_id": lec_id,
                "title": f"{mod_title} — Part {j+1}",
                "duration_min": 15 + (j * 5),
                "learning_objectives": [f"Understand {subtopics[j].lower()}"],
                "core_terms": [mod_title.split()[0], subject_key],
                "video_recipe": {
                    "narrative_arc": ["hook", "exposition", "summary"],
                    "scene_blocks": [
                        {
                            "block_id": f"{lec_id}_s1",
                            "duration_s": 60,
                            "narration_prompt": f"Welcome to {subtopics[j]}. In this lesson, we explore the key ideas.",
                            "visual_prompt": f"Title card: {subtopics[j]}",
                        },
                        {
                            "block_id": f"{lec_id}_s2",
                            "duration_s": 120,
                            "narration_prompt": f"Let's dive deeper into {mod_title}. This is essential for mastering {title}.",
                            "visual_prompt": f"Animated diagram illustrating {mod_title} concepts",
                        },
                        {
                            "block_id": f"{lec_id}_s3",
                            "duration_s": 60,
                            "narration_prompt": f"To summarize what we've learned about {mod_title}: the key takeaway is understanding the fundamentals.",
                            "visual_prompt": "Summary slide with key terms",
                        },
                    ],
                },
            }
            mod["lectures"].append(lec)
        course["modules"].append(mod)

    return course


def generate_level(level_id: str) -> list[dict]:
    """Generate all courses for a single grade level."""
    level_data = _CURRICULUM.get(level_id)
    if not level_data:
        return []
    courses = []
    for subj_key, (title, modules) in level_data["subjects"].items():
        course = _generate_course_json(level_id, subj_key, title, modules, level_data["name"])
        courses.append(course)
    return courses


def generate_all() -> dict[str, list[dict]]:
    """Generate courses for all levels. Returns {level_id: [course_dicts]}."""
    result = {}
    for level_id in _CURRICULUM:
        result[level_id] = generate_level(level_id)
    return result


def save_to_files(all_courses: dict[str, list[dict]]) -> list[Path]:
    """Save generated courses as JSON files under data/curriculum/."""
    paths = []
    for level_id, courses in all_courses.items():
        level_dir = OUTPUT_DIR / level_id
        level_dir.mkdir(parents=True, exist_ok=True)
        for course in courses:
            subj = course["course_id"].replace(f"{level_id}_", "")
            out_path = level_dir / f"{subj}.json"
            out_path.write_text(json.dumps(course, indent=2), encoding="utf-8")
            paths.append(out_path)
    return paths


def import_to_db(all_courses: dict[str, list[dict]], dry_run: bool = False) -> tuple[int, int, list[str]]:
    """Import all generated courses into the database."""
    import core.database as db
    total_imported = 0
    total_courses = 0
    all_warnings: list[str] = []
    for level_id, courses in all_courses.items():
        for course in courses:
            total_courses += 1
            count, warnings = db.bulk_import_json(json.dumps(course), validate_only=dry_run)
            total_imported += count
            all_warnings.extend(warnings)
    return total_courses, total_imported, all_warnings


def main():
    parser = argparse.ArgumentParser(description="Generate The God Factory University curriculum")
    parser.add_argument("--level", help="Generate for specific grade level (e.g. K, 9, freshman)")
    parser.add_argument("--domain", help="Generate for specific subject domain")
    parser.add_argument("--import-db", action="store_true", help="Import generated courses into database")
    parser.add_argument("--dry-run", action="store_true", help="Validate only, no DB write")
    parser.add_argument("--list-levels", action="store_true", help="List available levels")
    args = parser.parse_args()

    if args.list_levels:
        for lid, data in _CURRICULUM.items():
            n = len(data["subjects"])
            print(f"  {lid:12s}  {data['name']:30s}  {n} courses")
        return

    # Generate
    if args.level:
        if args.level not in _CURRICULUM:
            print(f"Error: Unknown level '{args.level}'. Use --list-levels to see options.")
            sys.exit(1)
        all_courses = {args.level: generate_level(args.level)}
    else:
        all_courses = generate_all()

    # Filter by domain if specified
    if args.domain:
        for level_id in all_courses:
            all_courses[level_id] = [
                c for c in all_courses[level_id]
                if args.domain in c["course_id"]
            ]

    # Count
    total = sum(len(v) for v in all_courses.values())
    lectures = sum(
        len(lec)
        for courses in all_courses.values()
        for c in courses
        for m in c["modules"]
        for lec in [m["lectures"]]
    )
    print(f"Generated {total} courses with {lectures} lectures across {len(all_courses)} levels")

    # Save files
    paths = save_to_files(all_courses)
    print(f"Saved {len(paths)} JSON files to {OUTPUT_DIR}/")

    # Import if requested
    if args.import_db or args.dry_run:
        mode = "Dry run" if args.dry_run else "Importing"
        print(f"{mode}...")
        n_courses, n_imported, warnings = import_to_db(all_courses, dry_run=args.dry_run)
        print(f"  Courses: {n_courses}")
        print(f"  Imported items: {n_imported}")
        if warnings:
            print(f"  Warnings: {len(warnings)}")
            for w in warnings[:5]:
                print(f"    - {w}")


if __name__ == "__main__":
    main()
