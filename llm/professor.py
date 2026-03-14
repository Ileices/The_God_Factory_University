"""
Professor AI agent: curriculum generation, Socratic dialogue, grading,
content expansion, study guides, quiz generation, and research deep-dives.
The professor operates on a LLMConfig from llm/providers.py.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from llm.providers import LLMConfig, chat, simple_complete, cfg_from_settings, estimate_tokens, PROVIDER_CAPABILITIES
from core.database import (
    append_chat, get_chat, save_llm_generated, unlock_achievement, add_xp,
    get_setting, get_course, get_modules, get_lectures, get_course_depth,
    upsert_course, upsert_module, upsert_lecture,
)
from core.course_tree import (
    PACING_TEMPLATES, build_decomposition_prompt, build_jargon_prompt,
    build_verification_prompt, register_sub_courses, get_pacing_for_course,
)


@dataclass
class ProfessorResponse:
    """Structured wrapper for all Professor method outputs."""
    raw_text: str
    parsed_json: dict | list | None = None
    warnings: list[str] = field(default_factory=list)
    provider_used: str = ""

    def __str__(self) -> str:
        return self.raw_text

ROOT = Path(__file__).resolve().parent.parent

PROFESSOR_SYSTEM = """You are Ileices, the Professor of The God Factory University.
IMPORTANT: The university is called "The God Factory University" — NEVER call it "Arcane University" or any other name.

CRITICAL RULES — READ AND OBEY:
- You are a REAL academic professor. You teach REAL subjects: computer science, math, physics, biology, history, philosophy, etc.
- NEVER use fantasy, magic, wizard, spell, potion, sorcery, arcane, enchantment, mystical, or any similar language.
- NEVER reference Hogwarts, dungeons, wizards, mages, sorcerers, potions, spell-casting, or any fictional/fantasy concepts.
- Do NOT theme your answers around magic or fantasy. You are a serious academic institution.
- If the student asks about algorithms, explain algorithms. If they ask about physics, explain physics. Stay grounded in reality.
- "The God Factory" means students become extraordinary through REAL knowledge — not through magic or fantasy.

The God Factory is an institution where students become godlike by expanding their knowledge across all disciplines.

NOTE: The God Factory is NOT religious and NOT magical. The name reflects the belief that through deep study and mastery of real-world subjects — computer science, mathematics, physics, biology, history, philosophy, and more — students transcend ordinary understanding and become extraordinary thinkers.

Your role encompasses ALL dimensions of academic excellence:
- Teach concepts clearly, building intuition before formalism
- Ask Socratic questions that drive discovery
- Generate well-structured curriculum JSON exactly matching the schema when asked
- Write voiceover narration scripts for lecture videos
- Provide detailed feedback on student work
- Suggest research directions and deeper topics
- Create practice problems with worked solutions
- Assess student understanding through dialogue
- Explain your reasoning fully and transparently

Personality: blunt, direct, and intellectually rigorous. You are honored to teach at The God Factory.
You respect the student's time — no fluff, no pleasantries beyond necessity.
You use precise academic vocabulary but always ensure clarity. You challenge the student to think harder.

When generating JSON curriculum, always output ONLY valid JSON that matches this schema:
{
  "course_id": "string",
  "title": "string",
  "description": "string",
  "credits": integer,
  "modules": [
    {
      "module_id": "string",
      "title": "string",
      "lectures": [
        {
          "lecture_id": "string",
          "title": "string",
          "duration_min": integer,
          "learning_objectives": ["string"],
          "core_terms": ["string"],
          "math_focus": ["string"],
          "coding_lab": {"language": "string", "task": "string", "deliverable": "string"},
          "video_recipe": {
            "narrative_arc": ["hook","concept","demo","practice","recap"],
            "scene_blocks": [
              {
                "block_id": "A",
                "duration_s": 90,
                "narration_prompt": "string",
                "visual_prompt": "string",
                "ambiance": {"music": "string", "sfx": "string", "color_palette": "string"}
              }
            ]
          }
        }
      ]
    }
  ]
}
"""


class Professor:
    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self._query_count = 0

    def _cfg(self) -> LLMConfig:
        cfg = cfg_from_settings()
        cfg.system_prompt = PROFESSOR_SYSTEM
        cfg.temperature = 0.72
        cfg.max_tokens = 4096
        return cfg

    def _history(self) -> list[dict]:
        rows = get_chat(self.session_id, limit=20)
        return [{"role": r["role"], "content": r["content"]} for r in rows]

    def _record_and_call(self, user_msg: str, stream: bool = False):
        append_chat(self.session_id, "user", user_msg)
        self._query_count += 1
        if self._query_count >= 10:
            unlock_achievement("professor_query")
        messages = self._truncate_history()
        cfg = self._cfg()
        result = chat(cfg, messages, stream=stream)
        return result, cfg.provider

    def _truncate_history(self) -> list[dict]:
        """Return chat history truncated to fit the provider's context window."""
        messages = self._history()
        cfg = self._cfg()
        caps = PROVIDER_CAPABILITIES.get(cfg.provider, {})
        ctx_window = caps.get("context_window", 4096)
        budget = int(ctx_window * 0.75)  # leave room for response
        # Always keep the system message (injected by chat()), so budget is for history
        total = 0
        kept: list[dict] = []
        for msg in reversed(messages):
            tokens = estimate_tokens(msg["content"])
            if total + tokens > budget:
                break
            kept.append(msg)
            total += tokens
        kept.reverse()
        return kept

    def _safe_parse_json(self, raw: str) -> tuple[dict | list | None, list[str]]:
        """Parse JSON from LLM output with repair attempts; return (parsed, warnings)."""
        warnings: list[str] = []
        repaired = self.repair_json(raw)
        if repaired is None:
            warnings.append("LLM returned invalid JSON that could not be repaired")
            return None, warnings
        try:
            parsed = json.loads(repaired)
        except (json.JSONDecodeError, ValueError):
            warnings.append("JSON repair produced unparseable output")
            return None, warnings
        if repaired != raw.strip():
            warnings.append("JSON was auto-repaired from malformed LLM output")
        return parsed, warnings

    def _wrap(self, raw: str, provider: str = "", expect_json: bool = False) -> ProfessorResponse:
        """Build a ProfessorResponse, optionally parsing JSON."""
        parsed = None
        warnings: list[str] = []
        if expect_json:
            parsed, warnings = self._safe_parse_json(raw)
            if parsed and isinstance(parsed, dict):
                # Field validation: warn on suspiciously empty required fields
                for key in ("title", "course_id"):
                    if key in parsed and not parsed[key]:
                        warnings.append(f"Required field '{key}' is empty")
        return ProfessorResponse(
            raw_text=raw, parsed_json=parsed, warnings=warnings, provider_used=provider
        )

    # ─── JSON helpers ────────────────────────────────────────────────────────

    @staticmethod
    def repair_json(raw: str) -> str | None:
        """Attempt to recover valid JSON from malformed LLM output.

        Tries, in order:
          1. Direct parse
          2. Extract from markdown code fences
          3. Strip trailing commas before } or ]
          4. Balance unclosed brackets/braces
        Returns the repaired JSON string, or None if unrecoverable.
        """

        def _try_parse(text: str):
            try:
                json.loads(text)
                return text
            except (json.JSONDecodeError, ValueError):
                return None

        raw = raw.strip()

        # 1. Direct parse
        result = _try_parse(raw)
        if result:
            return result

        # 2. Extract from markdown code fences
        fence = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
        if fence:
            result = _try_parse(fence.group(1).strip())
            if result:
                return result

        # 3. Strip trailing commas (,} or ,])
        cleaned = re.sub(r",\s*([}\]])", r"\1", raw)
        result = _try_parse(cleaned)
        if result:
            return result

        # Also try on fenced content
        if fence:
            cleaned = re.sub(r",\s*([}\]])", r"\1", fence.group(1).strip())
            result = _try_parse(cleaned)
            if result:
                return result

        # 4. Balance unclosed brackets/braces
        opens = {"[": "]", "{": "}"}
        stack = []
        for ch in cleaned:
            if ch in opens:
                stack.append(opens[ch])
            elif ch in ("]", "}"):
                if stack and stack[-1] == ch:
                    stack.pop()
        if stack:
            balanced = cleaned + "".join(reversed(stack))
            result = _try_parse(balanced)
            if result:
                return result

        return None

    # ─── Public methods ──────────────────────────────────────────────────────

    def ask(self, question: str, stream: bool = False):
        """General Socratic dialogue."""
        result, provider = self._record_and_call(question, stream=stream)
        if not stream:
            append_chat(self.session_id, "assistant", str(result))
            return self._wrap(str(result), provider)
        return result

    def stream(self, user_input: str):
        """Yield assistant response chunks for streaming display."""
        gen, _provider = self._record_and_call(user_input, stream=True)
        full = ""
        try:
            for chunk in gen:
                full += chunk
                yield chunk
        except TypeError:
            # Fell back to non-streaming string
            full = str(gen)
            yield full
        append_chat(self.session_id, "assistant", full)

    def generate_curriculum(self, topics: str, level: str = "undergraduate", lectures_per_module: int = 3) -> str:
        prompt = f"""Generate a complete course curriculum JSON for:
Topics: {topics}
Level: {level}
Lectures per module: {lectures_per_module}

Output ONLY a valid JSON object matching the schema. No markdown, no explanation before or after. Just the JSON."""
        cfg = self._cfg()
        result = simple_complete(cfg, prompt)
        save_llm_generated(result, "curriculum")
        add_xp(100, "Generated curriculum", "llm_generate")
        return self._wrap(result, cfg.provider, expect_json=True)

    def generate_quiz(self, lecture_data: dict, num_questions: int = 5) -> str:
        title = lecture_data.get("title", "Lecture")
        terms = lecture_data.get("core_terms", [])
        prompt = f"""Create a {num_questions}-question quiz for the lecture: "{title}"
Core terms: {', '.join(terms)}
Output as JSON: {{"title": "...", "questions": [{{"question": "What is...?", "choices": ["A) ...","B) ...","C) ...","D) ..."], "answer": "A", "explanation": "..."}}]}}
IMPORTANT: Each question object MUST have a "question" key with the full question text.
Output ONLY valid JSON."""
        cfg = self._cfg()
        result = simple_complete(cfg, prompt)
        save_llm_generated(result, "quiz")
        return self._wrap(result, cfg.provider, expect_json=True)

    def generate_homework(self, lecture_data: dict) -> str:
        title = lecture_data.get("title", "Lecture")
        objectives = lecture_data.get("learning_objectives", [])
        lab = lecture_data.get("coding_lab", {})
        prompt = f"""Design a homework assignment for: "{title}"
Objectives: {', '.join(objectives)}
Coding lab context: {lab.get('task', 'N/A')}
Include: written questions, a coding problem, and a reflection prompt.
Output as JSON: {{"title": "...", "type": "homework", "max_score": 100, "parts": [{{"part": "...", "instructions": "...", "points": 0}}]}}"""
        cfg = self._cfg()
        result = simple_complete(cfg, prompt)
        save_llm_generated(result, "homework")
        return self._wrap(result, cfg.provider, expect_json=True)

    def study_guide(self, lecture_data: dict) -> str:
        prompt = f"""Create a concise study guide for: "{lecture_data.get('title', 'Lecture')}"
Core terms: {', '.join(lecture_data.get('core_terms', []))}
Math focus: {', '.join(lecture_data.get('math_focus', []))}
Format as JSON: {{"title": "...", "key_concepts": [...], "formulas": [...], "practice_problems": [...], "further_reading": [...]}}"""
        cfg = self._cfg()
        result = simple_complete(cfg, prompt)
        save_llm_generated(result, "study_guide")
        return self._wrap(result, cfg.provider, expect_json=True)

    def grade_essay(self, essay_text: str, rubric: str = "") -> str:
        prompt = f"""Grade this student essay and provide structured feedback.
Rubric: {rubric or 'Standard academic rubric: clarity, accuracy, depth, examples, conclusion.'}
Essay:
---
{essay_text}
---
Output JSON: {{"score": 85, "max_score": 100, "grade": "B", "strengths": [...], "improvements": [...], "feedback": "..."}}"""
        cfg = self._cfg()
        result = simple_complete(cfg, prompt)
        return self._wrap(result, cfg.provider, expect_json=True)

    def grade_code(self, code_text: str, task_description: str = "") -> str:
        prompt = f"""Review this student code submission.
Task: {task_description or 'General coding task'}
Code:
```
{code_text}
```
Output JSON: {{"score": 80, "max_score": 100, "grade": "B", "correctness": "...", "style": "...", "improvements": [...], "feedback": "..."}}"""
        cfg = self._cfg()
        result = simple_complete(cfg, prompt)
        return self._wrap(result, cfg.provider, expect_json=True)

    def expand_narration(self, scene: dict, lecture: dict) -> str:
        prompt = f"""Write a full, high-quality 60-second voiceover narration script for:
Lecture: {lecture.get('title', '')}
Scene: {scene.get('block_id', 'A')} - {scene.get('visual_prompt', '')}
Narration hint: {scene.get('narration_prompt', '')}
Key terms: {', '.join(lecture.get('core_terms', [])[:6])}
Write in a clear, engaging professor voice. No stage directions, just the spoken text."""
        cfg = self._cfg()
        return self._wrap(simple_complete(cfg, prompt), cfg.provider)

    def suggest_next_topics(self, completed_titles: list[str]) -> str:
        prompt = f"""A student has completed these lectures: {', '.join(completed_titles[-10:])}.
Suggest 5 next topics they should study, explain why each is the logical next step.
Output JSON: {{"suggestions": [{{"topic": "...", "rationale": "...", "difficulty": "...", "estimated_hours": 0}}]}}"""
        cfg = self._cfg()
        return self._wrap(simple_complete(cfg, prompt), cfg.provider, expect_json=True)

    def research_rabbit_hole(self, term: str) -> str:
        prompt = f"""The student wants to go deep on: "{term}".
Provide an exciting research rabbit hole - cutting-edge papers, historical context, 
open problems, surprising connections to other fields, and hands-on experiments.
Output JSON: {{"term": "{term}", "overview": "...", "history": "...", "open_problems": [...], 
"surprising_connections": [...], "hands_on": [...], "papers": [...]}}"""
        cfg = self._cfg()
        result = simple_complete(cfg, prompt)
        save_llm_generated(result, "rabbit_hole")
        return self._wrap(result, cfg.provider, expect_json=True)

    def enhance_video_prompts(self, lecture_data: dict) -> str:
        title = lecture_data.get("title", "")
        scenes = lecture_data.get("video_recipe", {}).get("scene_blocks", [])
        prompt = f"""Enhance these video generation prompts for: "{title}"
Current scenes: {json.dumps(scenes, indent=2)}
Output enhanced JSON replacing 'visual_prompt' and 'ambiance' in each scene with richer, 
more cinematic and educational descriptions. Preserve all other fields.
Output ONLY valid JSON array of scene_blocks."""
        cfg = self._cfg()
        result = simple_complete(cfg, prompt)
        save_llm_generated(result, "enhanced_prompts")
        return self._wrap(result, cfg.provider, expect_json=True)

    def concept_map(self, lecture_data: dict) -> str:
        prompt = f"""Create a concept map for: "{lecture_data.get('title', '')}"
Terms: {', '.join(lecture_data.get('core_terms', []))}
Output JSON: {{"nodes": [{{"id": "...", "label": "...", "type": "concept|term|principle"}}], 
"edges": [{{"from": "...", "to": "...", "label": "...", "type": "is_a|part_of|leads_to|requires"}}]}}"""
        cfg = self._cfg()
        return self._wrap(simple_complete(cfg, prompt), cfg.provider, expect_json=True)

    def oral_exam(self, lecture_data: dict, student_answer: str, question: str) -> str:
        prompt = f"""Conduct an oral examination.
Lecture: "{lecture_data.get('title', '')}"
Question asked: {question}
Student's answer: {student_answer}
As a professor, respond with follow-up questions, corrections if needed, and encouragement.
Be Socratic - guide them to deeper understanding."""
        result, provider = self._record_and_call(
            f"[ORAL EXAM] Q: {question} | Student: {student_answer}"
        )
        append_chat(self.session_id, "assistant", str(result))
        return self._wrap(str(result), provider)

    def explain_app(self, question: str) -> str:
        """Explain how the app works using internal documentation — no code secrets exposed."""
        from core.app_docs import explain_for_professor
        docs_context = explain_for_professor(question)
        prompt = (
            f"{docs_context}\n\n"
            f"Student asks: {question}\n\n"
            "Explain clearly how this feature works, step by step. "
            "Be helpful and thorough. Do NOT reveal source code, file paths, "
            "SQL queries, or internal implementation details."
        )
        cfg = self._cfg()
        cfg.system_prompt = (
            PROFESSOR_SYSTEM + "\n\n"
            "You are now in APP GUIDE mode. Answer questions about how to use "
            "the The God Factory University application. Use the provided documentation "
            "to give accurate, helpful answers. NEVER output source code, "
            "database queries, file system paths, or internal variable names."
        )
        result = simple_complete(cfg, prompt)
        append_chat(self.session_id, "user", f"[APP GUIDE] {question}")
        append_chat(self.session_id, "assistant", str(result))
        return self._wrap(result, cfg.provider)

    # ─── Chunked generation (small-model-friendly) ───────────────────────────

    def _is_small_context(self) -> bool:
        """Check if current provider has a small context window (≤8K)."""
        cfg = self._cfg()
        caps = PROVIDER_CAPABILITIES.get(cfg.provider, {})
        return caps.get("context_window", 4096) <= 8192

    def chunked_curriculum(self, topics: str, level: str = "undergraduate",
                           lectures_per_module: int = 3,
                           progress_callback=None) -> ProfessorResponse:
        """Generate curriculum in chunks: outline → modules → lectures.

        For small models, each step fits in ~2K tokens.
        For large models, tries single-shot first, falls back to chunked.
        """
        cfg = self._cfg()
        small = self._is_small_context()

        # Step 1: Generate course outline (title, description, module titles)
        if progress_callback:
            progress_callback("Generating course outline...")
        outline_prompt = f"""Create a course outline for: {topics}
Level: {level}
Output JSON: {{"course_id": "PREFIX-101", "title": "...", "description": "...", "credits": 3, "module_titles": ["Module 1 title", "Module 2 title", ...]}}
Generate {max(2, lectures_per_module)} to 8 module titles. Output ONLY valid JSON."""
        outline_raw = simple_complete(cfg, outline_prompt)
        outline_resp = self._wrap(outline_raw, cfg.provider, expect_json=True)
        if not outline_resp.parsed_json:
            return outline_resp  # Failed at outline stage

        outline = outline_resp.parsed_json
        course_id = outline.get("course_id", "COURSE-101")
        modules = []

        # Step 2: Generate each module's lectures
        module_titles = outline.get("module_titles", outline.get("modules", []))
        if isinstance(module_titles, list) and module_titles:
            if isinstance(module_titles[0], dict):
                module_titles = [m.get("title", f"Module {i+1}") for i, m in enumerate(module_titles)]

        for i, mt in enumerate(module_titles):
            if progress_callback:
                progress_callback(f"Generating module {i+1}/{len(module_titles)}: {mt}")
            mid = f"{course_id}-M{i+1}"
            mod_prompt = f"""Generate {lectures_per_module} lectures for module "{mt}" in course "{outline.get('title','')}".
Module ID: {mid}
Output JSON: {{"module_id": "{mid}", "title": "{mt}", "lectures": [
  {{"lecture_id": "{mid}-L1", "title": "...", "duration_min": 60, "learning_objectives": ["..."], "core_terms": ["..."],
    "video_recipe": {{"scene_blocks": [{{"block_id": "A", "duration_s": 90, "narration_prompt": "...", "visual_prompt": "..."}}]}}
  }}
]}}
Output ONLY valid JSON."""
            mod_raw = simple_complete(cfg, mod_prompt)
            mod_resp = self._wrap(mod_raw, cfg.provider, expect_json=True)
            if mod_resp.parsed_json:
                modules.append(mod_resp.parsed_json)
            else:
                modules.append({"module_id": mid, "title": mt, "lectures": []})

            if small:
                time.sleep(0.5)  # Rate limit for local models

        # Step 3: Assemble final course JSON
        full_course = {
            "course_id": course_id,
            "title": outline.get("title", topics[:60]),
            "description": outline.get("description", ""),
            "credits": outline.get("credits", 3),
            "modules": modules,
        }
        raw_json = json.dumps(full_course, indent=2)
        save_llm_generated(raw_json, "curriculum")
        add_xp(100, "Generated curriculum (chunked)", "llm_generate")

        if progress_callback:
            progress_callback("Course generation complete!")

        return ProfessorResponse(
            raw_text=raw_json,
            parsed_json=full_course,
            warnings=outline_resp.warnings,
            provider_used=cfg.provider,
        )

    # ─── Course Decomposition ────────────────────────────────────────────────

    def decompose_course(self, course_id: str, depth: int | None = None,
                         pacing: str | None = None,
                         progress_callback=None) -> ProfessorResponse:
        """Decompose a course into sub-courses based on its modules.

        Each module in the parent becomes a full sub-course.
        """
        from core.database import tx
        course = get_course(course_id)
        if not course:
            return ProfessorResponse(
                raw_text="", warnings=["Course not found: " + course_id])

        modules = get_modules(course_id)
        if not modules:
            return ProfessorResponse(
                raw_text="", warnings=["Course has no modules to decompose"])

        current_depth = get_course_depth(course_id)
        target_depth = depth if depth is not None else current_depth + 1
        effective_pacing = pacing or get_pacing_for_course(course_id, tx)

        # Check depth target limit
        depth_target = course.get("depth_target") or 0
        if depth_target and target_depth > depth_target:
            return ProfessorResponse(
                raw_text="",
                warnings=[f"Depth target ({depth_target}) reached. "
                          f"Requested depth {target_depth} exceeds limit."])

        if progress_callback:
            progress_callback(f"Decomposing {course['title']} to depth {target_depth}...")

        prompt = build_decomposition_prompt(
            course, modules, target_depth, effective_pacing)

        cfg = self._cfg()
        cfg.max_tokens = 8192
        raw = simple_complete(cfg, prompt)
        resp = self._wrap(raw, cfg.provider, expect_json=True)

        if not resp.parsed_json:
            return resp

        parsed = resp.parsed_json
        sub_courses = parsed if isinstance(parsed, list) else [parsed]

        if progress_callback:
            progress_callback(f"Registering {len(sub_courses)} sub-courses...")

        created_ids = register_sub_courses(
            parent_id=course_id,
            sub_courses=sub_courses,
            depth=target_depth,
            pacing=effective_pacing,
            tx_func=tx,
            upsert_course_func=upsert_course,
            upsert_module_func=upsert_module,
            upsert_lecture_func=upsert_lecture,
        )

        save_llm_generated(raw, "decomposition")
        add_xp(150, f"Decomposed {course['title']}", "decompose")

        result = {
            "parent_course_id": course_id,
            "depth": target_depth,
            "pacing": effective_pacing,
            "sub_courses_created": len(created_ids),
            "sub_course_ids": created_ids,
        }

        if progress_callback:
            progress_callback(f"Created {len(created_ids)} sub-courses!")

        return ProfessorResponse(
            raw_text=json.dumps(result, indent=2),
            parsed_json=result,
            warnings=resp.warnings,
            provider_used=cfg.provider,
        )

    def generate_jargon_course(self, course_id: str,
                               progress_callback=None) -> ProfessorResponse:
        """Generate a jargon/terminology sub-course for a parent course."""
        from core.database import tx
        course = get_course(course_id)
        if not course:
            return ProfessorResponse(
                raw_text="", warnings=["Course not found: " + course_id])

        modules = get_modules(course_id)
        if not modules:
            return ProfessorResponse(
                raw_text="", warnings=["Course has no modules for jargon extraction"])

        if progress_callback:
            progress_callback(f"Extracting terminology from {course['title']}...")

        prompt = build_jargon_prompt(course, modules)
        cfg = self._cfg()
        raw = simple_complete(cfg, prompt)
        resp = self._wrap(raw, cfg.provider, expect_json=True)

        if not resp.parsed_json:
            return resp

        jargon_course = resp.parsed_json
        jargon_course["is_jargon_course"] = True
        jargon_course["credits"] = 1  # Extra credit: 0.5-1 credit

        created_ids = register_sub_courses(
            parent_id=course_id,
            sub_courses=[jargon_course],
            depth=(course.get("depth_level") or 0) + 1,
            pacing=get_pacing_for_course(course_id, tx),
            tx_func=tx,
            upsert_course_func=upsert_course,
            upsert_module_func=upsert_module,
            upsert_lecture_func=upsert_lecture,
        )

        save_llm_generated(raw, "jargon_course")
        add_xp(75, f"Generated jargon course for {course['title']}", "jargon_gen")

        if progress_callback:
            progress_callback("Jargon course created!")

        result = {
            "parent_course_id": course_id,
            "jargon_course_id": created_ids[0] if created_ids else None,
            "terms_count": len(
                (jargon_course.get("jargon") or {}).get("terms", [])),
        }

        return ProfessorResponse(
            raw_text=json.dumps(result, indent=2),
            parsed_json=result,
            warnings=resp.warnings,
            provider_used=cfg.provider,
        )

    def generate_verification(self, assignment_id: str) -> ProfessorResponse:
        """Generate a prove-it verification assignment for AI-assisted work."""
        from core.database import tx
        with tx() as con:
            row = con.execute(
                "SELECT * FROM assignments WHERE id = ?", (assignment_id,)
            ).fetchone()
        if not row:
            return ProfessorResponse(
                raw_text="", warnings=["Assignment not found: " + assignment_id])

        assignment = dict(row)
        lecture_title = ""
        if assignment.get("lecture_id"):
            from core.database import get_lecture
            lec = get_lecture(assignment["lecture_id"])
            if lec:
                lecture_title = lec.get("title", "")

        prompt = build_verification_prompt(assignment, lecture_title)
        cfg = self._cfg()
        raw = simple_complete(cfg, prompt)
        resp = self._wrap(raw, cfg.provider, expect_json=True)

        if resp.parsed_json:
            save_llm_generated(raw, "verification_assignment")

        return resp

    def chunked_quiz(self, lecture_data: dict, num_questions: int = 5,
                     progress_callback=None) -> ProfessorResponse:
        """Generate quiz one question at a time for small models."""
        cfg = self._cfg()
        title = lecture_data.get("title", "Lecture")
        terms = lecture_data.get("core_terms", [])

        if not self._is_small_context():
            return self.generate_quiz(lecture_data, num_questions)

        questions = []
        for i in range(num_questions):
            if progress_callback:
                progress_callback(f"Generating question {i+1}/{num_questions}")
            exclude = json.dumps([q.get("question", "") for q in questions]) if questions else "[]"
            q_prompt = f"""Write 1 quiz question for "{title}" (terms: {', '.join(terms[:5])}).
Do NOT repeat these questions: {exclude}
Output JSON: {{"question": "What is...?", "choices": ["A) ...", "B) ...", "C) ...", "D) ..."], "answer": "A", "explanation": "..."}}
IMPORTANT: Include the "question" key with the full question text.
Output ONLY valid JSON."""
            raw = simple_complete(cfg, q_prompt)
            resp = self._wrap(raw, cfg.provider, expect_json=True)
            if resp.parsed_json and isinstance(resp.parsed_json, dict):
                questions.append(resp.parsed_json)
            time.sleep(0.3)

        quiz = {"title": f"Quiz: {title}", "questions": questions}
        save_llm_generated(json.dumps(quiz), "quiz")
        return ProfessorResponse(
            raw_text=json.dumps(quiz, indent=2),
            parsed_json=quiz,
            provider_used=cfg.provider,
        )

    def chunked_rabbit_hole(self, term: str, progress_callback=None) -> ProfessorResponse:
        """Research rabbit hole in sections for small models."""
        cfg = self._cfg()

        if not self._is_small_context():
            return self.research_rabbit_hole(term)

        sections = {}
        prompts = [
            ("overview", f'Write a 2-paragraph overview of "{term}". Output ONLY the text.'),
            ("history", f'Write the historical context of "{term}" in 2-3 paragraphs. Output ONLY the text.'),
            ("open_problems", f'List 3 open problems related to "{term}". Output JSON: ["problem 1", "problem 2", "problem 3"]'),
            ("connections", f'List 3 surprising connections between "{term}" and other fields. Output JSON: ["connection 1", "connection 2", "connection 3"]'),
            ("hands_on", f'Suggest 2 hands-on experiments for "{term}". Output JSON: ["experiment 1", "experiment 2"]'),
        ]
        for i, (key, prompt) in enumerate(prompts):
            if progress_callback:
                progress_callback(f"Researching {key} ({i+1}/{len(prompts)})")
            raw = simple_complete(cfg, prompt)
            if key in ("open_problems", "connections", "hands_on"):
                resp = self._wrap(raw, cfg.provider, expect_json=True)
                sections[key] = resp.parsed_json if resp.parsed_json else [raw[:200]]
            else:
                sections[key] = raw
            time.sleep(0.3)

        result = {"term": term, **sections}
        save_llm_generated(json.dumps(result), "rabbit_hole")
        return ProfessorResponse(
            raw_text=json.dumps(result, indent=2),
            parsed_json=result,
            provider_used=cfg.provider,
        )
