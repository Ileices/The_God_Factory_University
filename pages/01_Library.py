"""
Library page — browse courses, import new ones, manage curriculum.
"""

import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.database import (
    bulk_import_json, get_all_courses, get_modules, get_lectures,
    delete_course, get_progress, add_xp, get_child_courses, get_course,
    course_completion_pct, course_credit_hours, get_pacing_for_course,
    upsert_course, get_competency_profile, BLOOMS_LEVELS, hours_to_credits,
    get_study_hours, get_assessment_hours,
)
from ui.theme import inject_theme, gf_header, section_divider, progress_badge, play_sfx, help_button

inject_theme()
gf_header("Library", "Your collection of courses and knowledge.")
help_button("browsing-courses")

# ─── Bulk Import ─────────────────────────────────────────────────────────────
with st.expander("[ BULK IMPORT ] -- Paste JSON from LLM or file", expanded=False):
    help_button("importing-courses")
    st.markdown(
        "Paste any of: a single course object, a JSON array, "
        "or multiple newline-separated JSON objects. "
        "See `schemas/SCHEMA_GUIDE.md` for the prompt to give an LLM."
    )
    raw = st.text_area("JSON Input", height=200, placeholder='{"course_id": "...", "title": "...", "modules": [...]}')
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        import_clicked = st.button("Import", use_container_width=True)
    with btn_col2:
        validate_clicked = st.button("Validate Only (Dry Run)", use_container_width=True)
    if import_clicked or validate_clicked:
        if raw.strip():
            dry = validate_clicked
            with st.spinner("Validating..." if dry else "Importing..."):
                count, errors = bulk_import_json(raw.strip(), validate_only=dry)
            # Build structured import report
            report = {
                "mode": "dry_run" if dry else "import",
                "objects_processed": count,
                "errors": len(errors),
                "error_details": errors,
            }
            if count:
                if dry:
                    st.success(f"Validation passed for {count} object(s). Ready to import.")
                else:
                    play_sfx("success")
                    st.success(f"Imported {count} objects successfully.")
                    add_xp(count * 10, "Library import", "import")
            for e in errors:
                st.error(e)
            if errors or count:
                with st.expander("Import Report", expanded=bool(errors)):
                    st.json(report)
                    st.download_button(
                        "Download Report JSON",
                        json.dumps(report, indent=2),
                        file_name="import_report.json",
                        mime="application/json",
                    )
        else:
            st.warning("Paste some JSON first.")

section_divider("Courses")

courses = get_all_courses()
if not courses:
    st.info("No courses yet. Import one above, or open Professor AI to generate one.")
    st.stop()

# Separate root courses (no parent) from sub-courses
root_courses = [c for c in courses if not c.get("parent_course_id")]
sub_course_map: dict[str, list[dict]] = {}
for c in courses:
    pid = c.get("parent_course_id")
    if pid:
        sub_course_map.setdefault(pid, []).append(c)


def _render_course(course: dict, indent: int = 0) -> None:
    """Render a course and its sub-courses recursively."""
    modules = get_modules(course["id"])
    total_lectures = sum(len(get_lectures(m["id"])) for m in modules)
    children = sub_course_map.get(course["id"], [])
    depth = course.get("depth_level") or 0
    pacing = course.get("pacing") or "standard"
    is_jargon = course.get("is_jargon_course")
    prefix = "  " * indent
    jargon_tag = " [Terminology]" if is_jargon else ""

    label = f"{prefix}{course['id']}  {course['title']}{jargon_tag}  ({total_lectures} lec, {course['credits']} cr)"
    if children:
        label += f"  [{len(children)} sub-courses]"

    with st.expander(label, expanded=False):
        col_a, col_b, col_c = st.columns([3, 1, 1])
        with col_a:
            st.caption(course.get("description") or "No description.")
            st.caption(f"Source: {course.get('source', 'imported')} | Pacing: {pacing} | Depth: {depth}")
            cr_hours = course_credit_hours(course["id"])
            comp_pct = course_completion_pct(course["id"])
            if cr_hours > 0 or comp_pct > 0:
                st.caption(f"Hours logged: {cr_hours:.1f} | Completion: {comp_pct:.0f}%")
        with col_b:
            st.metric("Credits", course["credits"])
        with col_c:
            if st.button("Delete", key=f"del_{course['id']}"):
                delete_course(course["id"])
                play_sfx("error")
                st.rerun()

        # Pacing selector and decompose button
        pace_col, decomp_col = st.columns(2)
        with pace_col:
            new_pacing = st.selectbox(
                "Pacing", ["fast", "standard", "slow"],
                index=["fast", "standard", "slow"].index(pacing),
                key=f"pace_{course['id']}",
            )
            if new_pacing != pacing:
                upsert_course(
                    course["id"], course["title"],
                    course.get("description", ""), course["credits"],
                    {}, course.get("source", "imported"),
                    parent_course_id=course.get("parent_course_id"),
                    depth_level=depth,
                    depth_target=course.get("depth_target") or 0,
                    pacing=new_pacing,
                    is_jargon_course=course.get("is_jargon_course") or 0,
                    jargon=course.get("jargon"),
                )
                st.rerun()
        with decomp_col:
            if st.button("Decompose", key=f"decompose_{course['id']}"):
                from llm.professor import Professor
                prof = Professor(session_id="library_decompose")
                with st.spinner("Generating sub-courses..."):
                    resp = prof.decompose_course(course["id"])
                if resp.parsed_json and resp.parsed_json.get("sub_courses_created"):
                    st.success(f"Created {resp.parsed_json['sub_courses_created']} sub-courses!")
                    st.rerun()
                else:
                    for w in resp.warnings:
                        st.warning(w)
            if st.button("Generate Jargon Course", key=f"jargon_{course['id']}"):
                from llm.professor import Professor
                prof = Professor(session_id="library_jargon")
                with st.spinner("Extracting terminology..."):
                    resp = prof.generate_jargon_course(course["id"])
                if resp.parsed_json and resp.parsed_json.get("jargon_course_id"):
                    st.success("Jargon course created!")
                    st.rerun()
                else:
                    for w in resp.warnings:
                        st.warning(w)

        for module in modules:
            st.markdown(
                f"<div style='color:#ffd700;font-family:monospace;margin-top:10px;'>"
                f"  Module {module['order_index']+1}: {module['title']}</div>",
                unsafe_allow_html=True,
            )
            for lec in get_lectures(module["id"]):
                prog = get_progress(lec["id"])
                badge = progress_badge(prog.get("status", "not_started"))
                st.markdown(
                    f"<div style='font-family:monospace;padding:2px 20px;color:#b8b8d0;'>"
                    f"  ├ {lec['title']} &nbsp; {badge}</div>",
                    unsafe_allow_html=True,
                )

        # Hours dashboard
        cr_hours = course_credit_hours(course["id"])
        assess_hrs = get_assessment_hours(course["id"])
        if cr_hours > 0 or assess_hrs > 0:
            st.markdown("---")
            hr1, hr2, hr3 = st.columns(3)
            with hr1:
                st.markdown(f"<span style='font-family:monospace;color:#00d4ff;'>Study: {cr_hours:.1f}h</span>",
                            unsafe_allow_html=True)
            with hr2:
                st.markdown(f"<span style='font-family:monospace;color:#e04040;'>Assess: {assess_hrs:.1f}h</span>",
                            unsafe_allow_html=True)
            with hr3:
                fc = hours_to_credits(cr_hours + assess_hrs)
                st.markdown(f"<span style='font-family:monospace;color:#ffd700;'>Credits: {fc:.2f}</span>",
                            unsafe_allow_html=True)

        # Competency radar chart (Bloom's taxonomy)
        profile = get_competency_profile(course["id"])
        has_data = any(profile[lv]["assessments"] > 0 for lv in BLOOMS_LEVELS)
        if has_data:
            st.markdown("---")
            st.markdown("**Competency Profile (Bloom's Taxonomy)**")
            for lv in BLOOMS_LEVELS:
                d = profile[lv]
                pct = d["pct"]
                bar_len = 20
                filled = int(pct / 100 * bar_len)
                bar = "\u2588" * filled + "\u2591" * (bar_len - filled)
                colour = "#40dc80" if pct >= 70 else "#ffd700" if pct >= 40 else "#e04040"
                st.markdown(
                    f"<div style='font-family:monospace;font-size:0.85rem;'>"
                    f"<span style='color:#a0a0c0;'>{lv:<14}</span>  "
                    f"<span style='color:{colour};'>[{bar}]</span>  "
                    f"<span style='color:#b8b8d0;'>{pct:.0f}% ({d['assessments']} assess)</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        # Render sub-courses inline
        if children:
            st.markdown("---")
            st.markdown(f"**Sub-courses ({len(children)})**")
            for child in children:
                _render_course(child, indent + 1)


for course in root_courses:
    _render_course(course)
