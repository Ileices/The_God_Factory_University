"""
Batch Render — queue and render all lectures with progress bar.
Filter/sort by course, difficulty, date. Visual effects applied automatically.
"""

import json
import sys
import threading
import time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.database import get_all_courses, get_modules, get_lectures, get_setting, save_setting
from ui.theme import inject_theme, gf_header, section_divider, play_sfx, help_button

inject_theme()
gf_header("Batch Render", "Queue lectures for rendering with visual effects applied automatically.")
help_button("batch-render")

EXPORT_DIR = ROOT / "exports"

# ─── Collect all lectures ─────────────────────────────────────────────────────
courses = get_all_courses()
if not courses:
    st.warning("No courses loaded.")
    st.stop()

all_lectures = []
course_map: dict[str, str] = {}  # course_id -> title
for course in courses:
    course_map[str(course["id"])] = course["title"]
    for module in get_modules(course["id"]):
        for lec in get_lectures(module["id"]):
            lec_data = json.loads(lec.get("data") or "{}")
            all_lectures.append({
                "course_id": str(course["id"]),
                "course_title": course["title"],
                "module_title": module["title"],
                "difficulty": lec_data.get("difficulty_level", ""),
                "created_at": lec.get("created_at", ""),
                "lecture": lec,
            })

if not all_lectures:
    st.info("No lectures found.")
    st.stop()

# ─── Filter & Sort Controls ──────────────────────────────────────────────────
section_divider("Filter & Sort")
f1, f2, f3 = st.columns(3)
with f1:
    course_options = ["All Courses"] + sorted(set(course_map.values()))
    filter_course = st.selectbox("Course", course_options)
with f2:
    diff_options = ["All Levels", "K-5", "6-8", "9-12", "Freshman", "Sophomore",
                    "Junior", "Senior", "Masters", "Doctoral"]
    filter_diff = st.selectbox("Difficulty", diff_options)
with f3:
    sort_by = st.selectbox("Sort by", ["Course → Module → Lecture", "Newest First", "Oldest First"])

# Apply filters
filtered = all_lectures[:]
if filter_course != "All Courses":
    filtered = [l for l in filtered if l["course_title"] == filter_course]
if filter_diff != "All Levels":
    filtered = [l for l in filtered if l["difficulty"] == filter_diff]

# Apply sort
if sort_by == "Newest First":
    filtered.sort(key=lambda x: x.get("created_at", ""), reverse=True)
elif sort_by == "Oldest First":
    filtered.sort(key=lambda x: x.get("created_at", ""))

section_divider("Select Lectures to Render")
st.markdown(
    f"<span style='color:#a0a0c0;font-family:monospace;font-size:0.82rem;'>"
    f"{len(filtered)} lectures match filters ({len(all_lectures)} total). "
    f"Select those to render, then start the queue.</span>",
    unsafe_allow_html=True,
)

select_all = st.checkbox("Select all lectures", value=True)
selected_ids = set()
for item in filtered:
    lec = item["lecture"]
    label = f"{item['course_title']} / {item['module_title']} / {lec['title']}"
    checked = st.checkbox(label, value=select_all, key=f"sel_{lec['id']}")
    if checked:
        selected_ids.add(lec["id"])

section_divider("Render Queue")
help_button("batch-render")
render_provider = get_setting("render_provider", "local")
st.markdown(f"<span style='font-family:monospace;color:#606080;font-size:0.8rem;'>Render backend: {render_provider}</span>", unsafe_allow_html=True)

queue = [item for item in filtered if item["lecture"]["id"] in selected_ids]

col_a, col_b = st.columns(2)
with col_a:
    fps = st.select_slider("Output FPS", options=[10, 15, 24], value=15)
with col_b:
    resolution = st.selectbox("Resolution", ["960x540", "1280x720", "1920x1080"], index=0)
res_w, res_h = map(int, resolution.split("x"))

if "render_state" not in st.session_state:
    st.session_state["render_state"] = "idle"
    st.session_state["render_log"] = []
    st.session_state["render_progress"] = 0

START_KEY = "batch_start"

def do_batch_render(queue_snapshot, fps, res_w, res_h):
    from media.video_engine import render_lecture
    log = []
    total = len(queue_snapshot)
    for idx, item in enumerate(queue_snapshot):
        lec_row = item["lecture"]
        lec_data = json.loads(lec_row["data"] or "{}")
        lec_data.setdefault("lecture_id", lec_row["id"])
        lec_data.setdefault("title", lec_row["title"])
        try:
            render_lecture(lec_data, EXPORT_DIR, fps=fps, width=res_w, height=res_h)
            log.append(f"[OK]  {lec_row['title']}")
        except Exception as e:
            log.append(f"[ERR] {lec_row['title']}: {e}")
        st.session_state["render_progress"] = (idx + 1) / total
        st.session_state["render_log"] = log[:]
    st.session_state["render_state"] = "done"
    st.session_state["render_log"] = log

if st.session_state["render_state"] == "idle":
    if st.button(f"Start Batch Render ({len(queue)} lectures)", use_container_width=True, type="primary"):
        if not queue:
            st.warning("Select at least one lecture.")
        else:
            st.session_state["render_state"] = "running"
            st.session_state["render_log"] = []
            st.session_state["render_progress"] = 0
            t = threading.Thread(target=do_batch_render, args=(queue, fps, res_w, res_h), daemon=True)
            t.start()
            play_sfx("collect")
            st.rerun()

if st.session_state["render_state"] == "running":
    prog = st.session_state["render_progress"]
    st.progress(prog, text=f"Rendering... {int(prog*100)}%")
    log_text = "\n".join(st.session_state["render_log"][-20:])
    if log_text:
        st.code(log_text, language="bash")
    if st.button("Abort", type="secondary"):
        st.session_state["render_state"] = "idle"
        st.rerun()
    time.sleep(1)
    st.rerun()

if st.session_state["render_state"] == "done":
    play_sfx("level_up")
    st.success("Batch render complete.")
    log_text = "\n".join(st.session_state["render_log"])
    st.code(log_text, language="bash")
    if st.button("Reset", use_container_width=True):
        st.session_state["render_state"] = "idle"
        st.session_state["render_log"] = []
        st.session_state["render_progress"] = 0
        st.rerun()

# ─── Visual Effects (applied automatically) ──────────────────────────────────
section_divider("Visual Effects (Auto-Applied)")
st.markdown(
    "<span style='color:#a0a0c0;font-family:monospace;font-size:0.82rem;'>"
    "These effects are applied automatically during rendering. No extra export step needed.</span>",
    unsafe_allow_html=True,
)

ve1, ve2 = st.columns(2)
with ve1:
    apply_transitions = st.toggle("Scene transitions (crossfade)", value=True)
    apply_ken_burns = st.toggle("Ken Burns pan/zoom on stills", value=True)
    apply_color_grade = st.toggle("Cinematic color grading", value=True)
with ve2:
    apply_text_overlay = st.toggle("Title/term text overlays", value=True)
    apply_ambient = st.toggle("Ambient particle effects", value=False)
    apply_watermark = st.toggle("Watermark / branding", value=False)

# Store visual effects as render settings
vfx_config = {
    "transitions": apply_transitions,
    "ken_burns": apply_ken_burns,
    "color_grade": apply_color_grade,
    "text_overlay": apply_text_overlay,
    "ambient_particles": apply_ambient,
    "watermark": apply_watermark,
}
save_setting("vfx_config", json.dumps(vfx_config))

# ─── Already rendered files ───────────────────────────────────────────────────
section_divider("Rendered Files")
video_files = sorted(EXPORT_DIR.glob("*.mp4"))
if video_files:
    for vf in video_files[-30:]:
        size_mb = vf.stat().st_size / (1024 * 1024)
        st.markdown(
            f"<span style='font-family:monospace;color:#606080;font-size:0.82rem;'>"
            f"  {vf.name}  —  {size_mb:.1f} MB</span>",
            unsafe_allow_html=True,
        )
else:
    st.info("No videos rendered yet.")
