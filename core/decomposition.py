"""
Course decomposition prompts and sub-course registration for The God Factory University.
Extracted from course_tree.py to respect the 1000 LOC limit (DEVELOPMENT.md Rule 1).
"""
from __future__ import annotations

import json


# ─── Pacing Templates ─────────────────────────────────────────────────────────

PACING_TEMPLATES: dict[str, dict] = {
    "fast": {
        "concepts_per_lecture": 3,
        "lectures_per_module": 2,
        "instruction": (
            "Present 2-3 concepts per lecture. Move quickly. "
            "Assume prerequisite knowledge. Minimal repetition. "
            "Focus on core principles and skip introductory material."
        ),
    },
    "standard": {
        "concepts_per_lecture": 1,
        "lectures_per_module": 3,
        "instruction": (
            "Present 1 concept per lecture. Balanced mix of theory and practice. "
            "Include examples, brief review, and a practice problem."
        ),
    },
    "slow": {
        "concepts_per_lecture": 1,
        "lectures_per_module": 4,
        "instruction": (
            "Spread 1 concept across multiple lectures: introduction, "
            "detailed walkthrough, edge cases and common mistakes, "
            "then guided practice. Repeat key ideas. Build confidence."
        ),
    },
}


def get_pacing_for_course(course_id: str, tx_func) -> str:
    """Get effective pacing for a course, inheriting from parent if unset."""
    with tx_func() as con:
        row = con.execute(
            "SELECT pacing, parent_course_id FROM courses WHERE id = ?",
            (course_id,),
        ).fetchone()
    if not row:
        return "standard"
    pacing = row["pacing"]
    if pacing and pacing != "standard":
        return pacing
    if row["parent_course_id"]:
        return get_pacing_for_course(row["parent_course_id"], tx_func)
    return pacing or "standard"


# ─── Course Decomposition ─────────────────────────────────────────────────────

def build_decomposition_prompt(course: dict, modules: list[dict],
                               depth: int, pacing: str) -> str:
    """Build the LLM prompt for decomposing a course into sub-courses."""
    pacing_cfg = PACING_TEMPLATES.get(pacing, PACING_TEMPLATES["standard"])
    lpm = pacing_cfg["lectures_per_module"]

    lines = [
        f"Decompose the course \"{course['title']}\" into sub-courses.",
        f"The parent course has {len(modules)} modules:",
    ]
    for m in modules:
        lines.append(f"  - {m['title']}")

    lines.append(f"\nCurrent depth: {depth}. Generate one sub-course per module above.")
    lines.append(f"Pacing: {pacing}. {pacing_cfg['instruction']}")
    lines.append(f"Lectures per module: {lpm}")

    if depth >= 2:
        lines.append(
            "At this depth, include implementation-focused content. "
            "Add hands-on labs, coding exercises, or build projects."
        )
    if depth >= 3:
        lines.append(
            "At this depth, include real-world application content. "
            "Add industry case studies, professional workflows, "
            "and practical problem-solving scenarios."
        )

    lines.append(
        "\nFor EACH module, output a sub-course JSON object. "
        "Return a JSON array of sub-course objects:\n"
        '[\n  {\n    "course_id": "PARENT_m1_d{depth}",\n'
        '    "title": "...",\n    "description": "...",\n'
        '    "credits": 3,\n'
        '    "modules": [\n      {\n'
        '        "module_id": "...",\n        "title": "...",\n'
        '        "lectures": [\n          {\n'
        '            "lecture_id": "...",\n'
        '            "title": "...",\n'
        '            "duration_min": 20,\n'
        '            "learning_objectives": ["..."],\n'
        '            "core_terms": ["..."],\n'
        '            "video_recipe": {\n'
        '                "scene_blocks": [{\n'
        '                    "block_id": "A",\n'
        '                    "duration_s": 90,\n'
        '                    "narration_prompt": "...",\n'
        '                    "visual_prompt": "..."\n'
        '                }]\n'
        '            }\n'
        '          }\n        ]\n      }\n    ]\n  }\n]\n'
        "Output ONLY valid JSON. No markdown fences, no explanation."
    )
    return "\n".join(lines)


def build_jargon_prompt(course: dict, modules: list[dict]) -> str:
    """Build the LLM prompt for generating a jargon sub-course."""
    mod_titles = [m["title"] for m in modules]
    return (
        f"Extract the key technical terms from the course \"{course['title']}\" "
        f"which covers these modules: {', '.join(mod_titles)}.\n\n"
        "Create a jargon-focused sub-course with ONE module containing lectures "
        "that teach the terminology. Each lecture covers 3-5 related terms.\n\n"
        "For each term, provide: definition, etymology (word origin), "
        "a usage example in context, and 1-2 related terms.\n\n"
        "Output a single JSON object:\n"
        '{\n  "course_id": "PARENT_jargon",\n'
        '  "title": "Terminology: COURSE_TITLE",\n'
        '  "description": "Key terms and vocabulary for ...",\n'
        '  "credits": 1,\n'
        '  "jargon": {\n'
        '    "terms": [\n'
        '      {\n'
        '        "term": "...",\n'
        '        "definition": "...",\n'
        '        "etymology": "...",\n'
        '        "usage_example": "...",\n'
        '        "related_terms": ["..."]\n'
        '      }\n'
        '    ]\n'
        '  },\n'
        '  "modules": [\n'
        '    {\n'
        '      "module_id": "...",\n'
        '      "title": "Core Terminology",\n'
        '      "lectures": [\n'
        '        {\n'
        '          "lecture_id": "...",\n'
        '          "title": "...",\n'
        '          "duration_min": 15,\n'
        '          "learning_objectives": ["Define and use: term1, term2, term3"],\n'
        '          "core_terms": ["term1", "term2", "term3"],\n'
        '          "video_recipe": {\n'
        '              "scene_blocks": [{"block_id": "A", "duration_s": 60, '
        '"narration_prompt": "...", "visual_prompt": "..."}]\n'
        '          }\n'
        '        }\n'
        '      ]\n'
        '    }\n'
        '  ]\n'
        '}\n'
        "Output ONLY valid JSON."
    )


def build_verification_prompt(assignment: dict, lecture_title: str) -> str:
    """Build prompt for generating a prove-it verification assignment."""
    return (
        f"The student completed an AI-assisted assignment: \"{assignment.get('title', '')}\"\n"
        f"For lecture: \"{lecture_title}\"\n"
        f"Original type: {assignment.get('type', 'homework')}\n"
        f"Original score: {assignment.get('score', 'N/A')}\n\n"
        "Create a VERIFICATION (prove-it) assignment that tests the same concepts "
        "but requires the student to demonstrate understanding WITHOUT AI assistance.\n\n"
        "The verification should:\n"
        "- Test the same core concepts as the original\n"
        "- Require original thinking (not recitation)\n"
        "- Be completable in 15-30 minutes\n"
        "- Include clear rubric criteria\n\n"
        "Output JSON:\n"
        '{\n'
        '  "title": "Prove-It: ...",\n'
        '  "type": "verification",\n'
        '  "description": "...",\n'
        '  "max_score": 100,\n'
        '  "ai_policy": {"level": "prohibited", "verification_type": "original_example"},\n'
        '  "parts": [\n'
        '    {"part": "...", "instructions": "...", "points": 0}\n'
        '  ]\n'
        '}\n'
        "Output ONLY valid JSON."
    )


def register_sub_courses(parent_id: str, sub_courses: list[dict],
                         depth: int, pacing: str, tx_func,
                         upsert_course_func, upsert_module_func,
                         upsert_lecture_func) -> list[str]:
    """Register parsed sub-course JSONs into the database. Returns list of new course IDs."""
    created_ids = []
    for sc in sub_courses:
        cid = sc.get("course_id", f"{parent_id}_sub_{len(created_ids)}")
        jargon_data = sc.get("jargon")
        jargon_str = json.dumps(jargon_data) if jargon_data else None
        is_jargon = 1 if sc.get("is_jargon_course") else 0

        upsert_course_func(
            course_id=cid,
            title=sc.get("title", "Sub-course"),
            description=sc.get("description", ""),
            credits=sc.get("credits", 3),
            data=sc.get("data", {}),
            source="decomposed",
            parent_course_id=parent_id,
            depth_level=depth,
            depth_target=sc.get("depth_target", 0),
            pacing=pacing,
            is_jargon_course=is_jargon,
            jargon=jargon_str,
        )

        for mi, mod in enumerate(sc.get("modules", [])):
            mid = mod.get("module_id", f"{cid}_m{mi + 1}")
            upsert_module_func(mid, cid, mod.get("title", f"Module {mi + 1}"), mi, {})
            for li, lec in enumerate(mod.get("lectures", [])):
                lid = lec.get("lecture_id", f"{mid}_l{li + 1}")
                upsert_lecture_func(
                    lid, mid, cid,
                    lec.get("title", f"Lecture {li + 1}"),
                    lec.get("duration_min", 20),
                    li,
                    {k: v for k, v in lec.items()
                     if k not in ("lecture_id", "title", "duration_min")},
                )

        created_ids.append(cid)
    return created_ids
