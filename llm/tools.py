"""
Tool registry for The God Factory University agent system.

Each tool is a callable with a JSON-schema description.
Tools are registered via decorator and can be looked up by name.
Dual prompt format: full JSON-schema for large models, compressed for 3B.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

# ─── Tool definition ─────────────────────────────────────────────────────────

@dataclass
class Tool:
    """A callable tool the agent can invoke."""
    name: str
    description: str
    parameters: dict  # JSON Schema for parameters
    handler: Callable[..., Any]
    category: str = "general"
    requires_review: bool = False  # If True, result goes to draft queue

    def to_schema(self) -> dict:
        """Return the tool as a JSON-schema dict for LLM consumption."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


# ─── Registry ────────────────────────────────────────────────────────────────

_TOOLS: dict[str, Tool] = {}


def register(name: str, description: str, parameters: dict,
             category: str = "general", requires_review: bool = False):
    """Decorator to register a function as an agent tool."""
    def decorator(fn: Callable) -> Callable:
        _TOOLS[name] = Tool(
            name=name,
            description=description,
            parameters=parameters,
            handler=fn,
            category=category,
            requires_review=requires_review,
        )
        return fn
    return decorator


def get_tool(name: str) -> Tool | None:
    return _TOOLS.get(name)


def list_tools(category: str | None = None) -> list[Tool]:
    tools = list(_TOOLS.values())
    if category:
        tools = [t for t in tools if t.category == category]
    return tools


def get_schemas(category: str | None = None) -> list[dict]:
    """Return JSON schemas for all tools (or a category)."""
    return [t.to_schema() for t in list_tools(category)]


def call_tool(name: str, args: dict) -> dict:
    """Execute a tool by name. Returns {"ok": bool, "result": ...}."""
    tool = get_tool(name)
    if not tool:
        return {"ok": False, "error": f"Unknown tool: {name}"}
    try:
        result = tool.handler(**args)
        return {"ok": True, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─── Course building tools ───────────────────────────────────────────────────

@register(
    name="create_course_outline",
    description="Create a new course with title, description, and module skeleton. Returns course_id.",
    parameters={
        "type": "object",
        "properties": {
            "course_id": {"type": "string", "description": "Unique course ID (e.g. CS101)"},
            "title": {"type": "string", "description": "Course title"},
            "description": {"type": "string", "description": "Course description"},
            "credits": {"type": "integer", "description": "Credit hours (default 3)"},
            "module_titles": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of module titles for the course",
            },
        },
        "required": ["course_id", "title", "description", "module_titles"],
    },
    category="course",
)
def create_course_outline(course_id: str, title: str, description: str,
                          module_titles: list[str], credits: int = 3) -> dict:
    from core.database import upsert_course, upsert_module
    data = {
        "course_id": course_id,
        "title": title,
        "description": description,
        "credits": credits,
        "difficulty_level": "Undergraduate",
        "modules": [],
    }
    upsert_course(course_id, title, description, credits, data)
    modules = []
    for i, mt in enumerate(module_titles):
        mid = f"{course_id}-M{i+1}"
        upsert_module(mid, course_id, mt, i, {"module_id": mid, "title": mt})
        modules.append({"module_id": mid, "title": mt})
    data["modules"] = modules
    upsert_course(course_id, title, description, credits, data)
    return {"course_id": course_id, "modules_created": len(modules)}


@register(
    name="add_module",
    description="Add a new module to an existing course.",
    parameters={
        "type": "object",
        "properties": {
            "course_id": {"type": "string"},
            "module_id": {"type": "string"},
            "title": {"type": "string"},
            "order_index": {"type": "integer"},
        },
        "required": ["course_id", "module_id", "title"],
    },
    category="course",
)
def add_module(course_id: str, module_id: str, title: str, order_index: int = 0) -> dict:
    from core.database import upsert_module
    upsert_module(module_id, course_id, title, order_index, {"module_id": module_id, "title": title})
    return {"module_id": module_id, "status": "created"}


@register(
    name="add_lecture",
    description="Add a lecture with full video recipe to a module.",
    parameters={
        "type": "object",
        "properties": {
            "module_id": {"type": "string"},
            "course_id": {"type": "string"},
            "lecture_id": {"type": "string"},
            "title": {"type": "string"},
            "duration_min": {"type": "integer"},
            "learning_objectives": {"type": "array", "items": {"type": "string"}},
            "core_terms": {"type": "array", "items": {"type": "string"}},
            "scene_blocks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "block_id": {"type": "string"},
                        "duration_s": {"type": "integer"},
                        "narration_prompt": {"type": "string"},
                        "visual_prompt": {"type": "string"},
                    },
                },
            },
        },
        "required": ["module_id", "course_id", "lecture_id", "title"],
    },
    category="course",
)
def add_lecture(module_id: str, course_id: str, lecture_id: str, title: str,
                duration_min: int = 60, learning_objectives: list[str] | None = None,
                core_terms: list[str] | None = None,
                scene_blocks: list[dict] | None = None, order_index: int = 0) -> dict:
    from core.database import upsert_lecture
    data = {
        "lecture_id": lecture_id,
        "title": title,
        "duration_min": duration_min,
        "learning_objectives": learning_objectives or [],
        "core_terms": core_terms or [],
        "video_recipe": {
            "narrative_arc": ["hook", "concept", "demo", "practice", "recap"],
            "scene_blocks": scene_blocks or [],
        },
    }
    upsert_lecture(lecture_id, module_id, course_id, title, duration_min, order_index, data)
    return {"lecture_id": lecture_id, "status": "created"}


@register(
    name="add_assignment",
    description="Add a quiz or homework assignment to a lecture or course.",
    parameters={
        "type": "object",
        "properties": {
            "assignment_id": {"type": "string"},
            "title": {"type": "string"},
            "lecture_id": {"type": "string"},
            "course_id": {"type": "string"},
            "type": {"type": "string", "enum": ["quiz", "homework", "essay", "code"]},
            "questions": {"type": "array", "items": {"type": "object"}},
            "max_score": {"type": "number"},
        },
        "required": ["assignment_id", "title", "type"],
    },
    category="course",
)
def add_assignment(assignment_id: str, title: str, type: str = "quiz",
                   lecture_id: str = "", course_id: str = "",
                   questions: list[dict] | None = None,
                   max_score: float = 100) -> dict:
    from core.database import save_assignment
    save_assignment({
        "id": assignment_id,
        "title": title,
        "type": type,
        "lecture_id": lecture_id,
        "course_id": course_id,
        "max_score": max_score,
        "data": {"questions": questions or []},
    })
    return {"assignment_id": assignment_id, "status": "created"}


@register(
    name="get_course_manifest",
    description="Get a compact manifest of a course (modules and lectures).",
    parameters={
        "type": "object",
        "properties": {
            "course_id": {"type": "string", "description": "The course ID to look up"},
        },
        "required": ["course_id"],
    },
    category="course",
)
def get_course_manifest(course_id: str) -> dict:
    from core.database import get_all_courses, get_modules, get_lectures
    courses = get_all_courses()
    course = next((c for c in courses if c.get("id") == course_id), None)
    if not course:
        return {"error": f"Course {course_id} not found"}
    modules = get_modules(course_id)
    result = {
        "course_id": course_id,
        "title": course.get("title", ""),
        "credits": course.get("credits", 3),
        "modules": [],
    }
    for m in modules:
        lectures = get_lectures(m["id"])
        result["modules"].append({
            "module_id": m["id"],
            "title": m["title"],
            "lectures": [{"lecture_id": l["id"], "title": l["title"]} for l in lectures],
        })
    return result


@register(
    name="get_all_courses_summary",
    description="Get a summary list of all courses in the university.",
    parameters={"type": "object", "properties": {}},
    category="course",
)
def get_all_courses_summary() -> dict:
    from core.database import get_all_courses, get_modules
    courses = get_all_courses()
    result = []
    for c in courses:
        mods = get_modules(c["id"])
        result.append({
            "course_id": c["id"],
            "title": c.get("title", ""),
            "credits": c.get("credits", 3),
            "module_count": len(mods),
        })
    return {"courses": result, "total": len(result)}


@register(
    name="validate_and_import",
    description="Validate a course JSON object against the schema and import it to the database.",
    parameters={
        "type": "object",
        "properties": {
            "course_json": {"type": "object", "description": "Full course JSON to validate and import"},
        },
        "required": ["course_json"],
    },
    category="course",
    requires_review=True,
)
def validate_and_import(course_json: dict) -> dict:
    from core.database import bulk_import_json
    raw = json.dumps(course_json)
    imported, errors = bulk_import_json(raw)
    return {"imported": imported, "errors": errors}


@register(
    name="search_courses",
    description="Search courses by keyword in title or description.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search keyword"},
        },
        "required": ["query"],
    },
    category="course",
)
def search_courses(query: str) -> dict:
    from core.database import get_all_courses
    q = query.lower()
    courses = get_all_courses()
    matches = [
        {"course_id": c["id"], "title": c.get("title", "")}
        for c in courses
        if q in c.get("title", "").lower() or q in (c.get("description") or "").lower()
    ]
    return {"matches": matches, "count": len(matches)}


# ─── Video editing tools ─────────────────────────────────────────────────────

@register(
    name="list_scenes",
    description="List all scenes for a lecture.",
    parameters={
        "type": "object",
        "properties": {
            "lecture_id": {"type": "string"},
        },
        "required": ["lecture_id"],
    },
    category="video",
)
def list_scenes(lecture_id: str) -> dict:
    from core.database import get_lecture
    lec = get_lecture(lecture_id)
    if not lec:
        return {"error": f"Lecture {lecture_id} not found"}
    data = json.loads(lec.get("data") or "{}")
    scenes = data.get("video_recipe", {}).get("scene_blocks", [])
    return {
        "lecture_id": lecture_id,
        "scenes": [
            {"block_id": s.get("block_id"), "duration_s": s.get("duration_s"),
             "narration_prompt": s.get("narration_prompt", "")[:100],
             "visual_prompt": s.get("visual_prompt", "")[:100]}
            for s in scenes
        ],
    }


@register(
    name="edit_scene",
    description="Edit a scene's narration, visual prompt, or duration.",
    parameters={
        "type": "object",
        "properties": {
            "lecture_id": {"type": "string"},
            "block_id": {"type": "string"},
            "narration_prompt": {"type": "string"},
            "visual_prompt": {"type": "string"},
            "duration_s": {"type": "integer"},
        },
        "required": ["lecture_id", "block_id"],
    },
    category="video",
)
def edit_scene(lecture_id: str, block_id: str, narration_prompt: str | None = None,
               visual_prompt: str | None = None, duration_s: int | None = None) -> dict:
    from core.database import get_lecture
    lec = get_lecture(lecture_id)
    if not lec:
        return {"error": f"Lecture {lecture_id} not found"}
    data = json.loads(lec.get("data") or "{}")
    scenes = data.get("video_recipe", {}).get("scene_blocks", [])
    found = False
    for s in scenes:
        if s.get("block_id") == block_id:
            if narration_prompt is not None:
                s["narration_prompt"] = narration_prompt
            if visual_prompt is not None:
                s["visual_prompt"] = visual_prompt
            if duration_s is not None:
                s["duration_s"] = duration_s
            found = True
            break
    if not found:
        return {"error": f"Scene {block_id} not found"}
    _update_lecture_data(lecture_id, data)
    return {"status": "updated", "block_id": block_id}


@register(
    name="add_scene",
    description="Add a new scene to a lecture's video recipe.",
    parameters={
        "type": "object",
        "properties": {
            "lecture_id": {"type": "string"},
            "block_id": {"type": "string"},
            "narration_prompt": {"type": "string"},
            "visual_prompt": {"type": "string"},
            "duration_s": {"type": "integer"},
            "insert_after": {"type": "string", "description": "block_id to insert after (omit for end)"},
        },
        "required": ["lecture_id", "block_id", "narration_prompt", "visual_prompt", "duration_s"],
    },
    category="video",
)
def add_scene(lecture_id: str, block_id: str, narration_prompt: str,
              visual_prompt: str, duration_s: int, insert_after: str = "") -> dict:
    from core.database import get_lecture
    lec = get_lecture(lecture_id)
    if not lec:
        return {"error": f"Lecture {lecture_id} not found"}
    data = json.loads(lec.get("data") or "{}")
    recipe = data.setdefault("video_recipe", {})
    scenes = recipe.setdefault("scene_blocks", [])
    new_scene = {
        "block_id": block_id,
        "duration_s": duration_s,
        "narration_prompt": narration_prompt,
        "visual_prompt": visual_prompt,
        "ambiance": {"music": "ambient", "sfx": "gentle", "color_palette": "cyan and dark"},
    }
    if insert_after:
        idx = next((i for i, s in enumerate(scenes) if s.get("block_id") == insert_after), -1)
        if idx >= 0:
            scenes.insert(idx + 1, new_scene)
        else:
            scenes.append(new_scene)
    else:
        scenes.append(new_scene)
    _update_lecture_data(lecture_id, data)
    return {"status": "added", "block_id": block_id, "total_scenes": len(scenes)}


@register(
    name="remove_scene",
    description="Remove a scene from a lecture.",
    parameters={
        "type": "object",
        "properties": {
            "lecture_id": {"type": "string"},
            "block_id": {"type": "string"},
        },
        "required": ["lecture_id", "block_id"],
    },
    category="video",
)
def remove_scene(lecture_id: str, block_id: str) -> dict:
    from core.database import get_lecture
    lec = get_lecture(lecture_id)
    if not lec:
        return {"error": f"Lecture {lecture_id} not found"}
    data = json.loads(lec.get("data") or "{}")
    scenes = data.get("video_recipe", {}).get("scene_blocks", [])
    original_len = len(scenes)
    scenes = [s for s in scenes if s.get("block_id") != block_id]
    if len(scenes) == original_len:
        return {"error": f"Scene {block_id} not found"}
    data["video_recipe"]["scene_blocks"] = scenes
    _update_lecture_data(lecture_id, data)
    return {"status": "removed", "remaining_scenes": len(scenes)}


@register(
    name="reorder_scenes",
    description="Reorder scenes in a lecture by providing the block_ids in desired order.",
    parameters={
        "type": "object",
        "properties": {
            "lecture_id": {"type": "string"},
            "scene_order": {"type": "array", "items": {"type": "string"}, "description": "block_ids in desired order"},
        },
        "required": ["lecture_id", "scene_order"],
    },
    category="video",
)
def reorder_scenes(lecture_id: str, scene_order: list[str]) -> dict:
    from core.database import get_lecture
    lec = get_lecture(lecture_id)
    if not lec:
        return {"error": f"Lecture {lecture_id} not found"}
    data = json.loads(lec.get("data") or "{}")
    scenes_by_id = {s["block_id"]: s for s in data.get("video_recipe", {}).get("scene_blocks", [])}
    reordered = [scenes_by_id[bid] for bid in scene_order if bid in scenes_by_id]
    data.setdefault("video_recipe", {})["scene_blocks"] = reordered
    _update_lecture_data(lecture_id, data)
    return {"status": "reordered", "order": scene_order}


@register(
    name="enhance_narration",
    description="Use LLM to rewrite/improve a scene's narration script.",
    parameters={
        "type": "object",
        "properties": {
            "lecture_id": {"type": "string"},
            "block_id": {"type": "string"},
            "style": {"type": "string", "description": "Style hint, e.g. 'more engaging', 'simpler'"},
        },
        "required": ["lecture_id", "block_id"],
    },
    category="video",
)
def enhance_narration(lecture_id: str, block_id: str, style: str = "clear and engaging") -> dict:
    from core.database import get_lecture
    from llm.providers import simple_complete, cfg_from_settings
    lec = get_lecture(lecture_id)
    if not lec:
        return {"error": f"Lecture {lecture_id} not found"}
    data = json.loads(lec.get("data") or "{}")
    scenes = data.get("video_recipe", {}).get("scene_blocks", [])
    scene = next((s for s in scenes if s.get("block_id") == block_id), None)
    if not scene:
        return {"error": f"Scene {block_id} not found"}
    cfg = cfg_from_settings()
    prompt = (
        f"Rewrite this narration script to be {style}.\n"
        f"Original: {scene.get('narration_prompt', '')}\n"
        f"Lecture context: {data.get('title', '')}\n"
        "Output only the rewritten narration text, nothing else."
    )
    result = simple_complete(cfg, prompt)
    if not result.startswith("[LLM ERROR]"):
        scene["narration_prompt"] = result
        _update_lecture_data(lecture_id, data)
        return {"status": "enhanced", "block_id": block_id, "new_narration": result[:200]}
    return {"error": result}


@register(
    name="render_lecture",
    description="Render a lecture to MP4 video.",
    parameters={
        "type": "object",
        "properties": {
            "lecture_id": {"type": "string"},
        },
        "required": ["lecture_id"],
    },
    category="video",
)
def render_lecture_tool(lecture_id: str) -> dict:
    from core.database import get_lecture
    from media.video_engine import render_lecture as _render
    from pathlib import Path
    lec = get_lecture(lecture_id)
    if not lec:
        return {"error": f"Lecture {lecture_id} not found"}
    data = json.loads(lec.get("data") or "{}")
    data.setdefault("lecture_id", lecture_id)
    data.setdefault("title", lec.get("title", "Lecture"))
    output_dir = Path("exports") / "renders"
    try:
        paths = _render(data, output_dir)
        return {"status": "rendered", "files": [str(p) for p in paths]}
    except Exception as e:
        return {"error": str(e)}


# ─── Utility tools ────────────────────────────────────────────────────────────

@register(
    name="get_lecture_data",
    description="Get full lecture data including scenes, objectives, and terms.",
    parameters={
        "type": "object",
        "properties": {
            "lecture_id": {"type": "string"},
        },
        "required": ["lecture_id"],
    },
    category="utility",
)
def get_lecture_data(lecture_id: str) -> dict:
    from core.database import get_lecture
    lec = get_lecture(lecture_id)
    if not lec:
        return {"error": f"Lecture {lecture_id} not found"}
    data = json.loads(lec.get("data") or "{}")
    data["title"] = lec.get("title", data.get("title", ""))
    return data


@register(
    name="generate_quiz_for_lecture",
    description="Generate a quiz for a specific lecture using the LLM.",
    parameters={
        "type": "object",
        "properties": {
            "lecture_id": {"type": "string"},
            "num_questions": {"type": "integer", "description": "Number of quiz questions (default 5)"},
        },
        "required": ["lecture_id"],
    },
    category="course",
)
def generate_quiz_for_lecture(lecture_id: str, num_questions: int = 5) -> dict:
    from core.database import get_lecture
    from llm.professor import Professor
    lec = get_lecture(lecture_id)
    if not lec:
        return {"error": f"Lecture {lecture_id} not found"}
    data = json.loads(lec.get("data") or "{}")
    data["title"] = lec.get("title", data.get("title", ""))
    prof = Professor()
    resp = prof.generate_quiz(data, num_questions)
    if resp.parsed_json:
        return {"status": "generated", "quiz": resp.parsed_json}
    return {"status": "generated", "raw": resp.raw_text[:500]}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _update_lecture_data(lecture_id: str, data: dict) -> None:
    """Update the data JSON blob for a lecture in the DB."""
    from core.database import tx
    import json as _json
    with tx() as con:
        con.execute(
            "UPDATE lectures SET data=? WHERE id=?",
            (_json.dumps(data), lecture_id),
        )
