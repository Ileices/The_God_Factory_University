"""
Professor AI — LLM-powered academic advisor, tutor, and curriculum generator.
"""

import json
import sys
import time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.database import (
    get_setting, save_chat_history, get_chat_history, bulk_import_json,
    save_llm_generated, add_xp, unlock_achievement,
)
from ui.theme import inject_theme, gf_header, section_divider, play_sfx, stat_card, help_button, sanitize_llm_output

inject_theme()
gf_header("Professor AI", "Ileices — your blunt, brilliant guide at The God Factory.")
help_button("professor-chat")

# ─── Provider status bar ──────────────────────────────────────────────────────
provider = get_setting("llm_provider", "ollama")
model = get_setting("llm_model", "llama3")

status_icon = {
    "ollama": "[LOCAL]",
    "lm_studio": "[LOCAL]",
    "openai": "[API]",
    "github": "[API]",
    "anthropic": "[API]",
    "groq": "[FREE]",
    "mistral": "[API]",
    "together": "[API]",
    "huggingface": "[FREE]",
}.get(provider, "[?]")

st.markdown(
    f"<div style='font-family:monospace;color:#606080;font-size:0.8rem;margin-bottom:8px;'>"
    f"PROFESSOR  {status_icon}  {provider.upper()}  /  {model}  "
    f"— configure in Settings</div>",
    unsafe_allow_html=True,
)

def get_professor():
    from llm.professor import Professor
    return Professor(session_id="main")

# ─── Action tabs ─────────────────────────────────────────────────────────────
tab_chat, tab_gen, tab_grade, tab_quiz, tab_rabbit, tab_history, tab_guide = st.tabs([
    "Chat",
    "Generate Curriculum",
    "Grade Work",
    "Create Quiz",
    "Research Rabbit Hole",
    "Chat History",
    "App Guide",
])

# ── Tab 1: Chat ───────────────────────────────────────────────────────────────
with tab_chat:
    section_divider("Conversation")
    help_button("professor-chat")

    # Session selector
    if "chat_session_id" not in st.session_state:
        st.session_state["chat_session_id"] = "main"

    s1, s2 = st.columns([3, 1])
    with s1:
        session_id = st.text_input("Session", value=st.session_state["chat_session_id"],
                                   key="session_input", label_visibility="collapsed",
                                   placeholder="Session name (e.g. 'main', 'calculus-help')")
        if session_id != st.session_state["chat_session_id"]:
            st.session_state["chat_session_id"] = session_id
            st.rerun()
    with s2:
        new_name = f"chat-{int(time.time())}"
        if st.button("New Chat", use_container_width=True):
            st.session_state["chat_session_id"] = new_name
            st.rerun()

    session_id = st.session_state["chat_session_id"]
    history = get_chat_history(session_id)

    chat_box = st.container()
    with chat_box:
        for msg in history[-40:]:
            with st.chat_message(msg["role"]):
                st.markdown(sanitize_llm_output(msg["content"]))

    user_input = st.chat_input("Ask the Professor anything...")
    if user_input:
        save_chat_history(session_id, "user", user_input)
        with chat_box:
            with st.chat_message("user"):
                st.markdown(user_input)

        with chat_box:
            with st.chat_message("assistant"):
                placeholder = st.empty()
                full_response = ""
                try:
                    prof = get_professor()
                    for chunk in prof.stream(user_input):
                        full_response += chunk
                        placeholder.markdown(sanitize_llm_output(full_response) + " \u25cc")
                    placeholder.markdown(sanitize_llm_output(full_response))
                    save_chat_history(session_id, "assistant", full_response)
                    add_xp(5, "Consulted the Professor", "professor_chat")
                except Exception as e:
                    full_response = f"(Professor offline: {e})"
                    placeholder.error(full_response)
        st.rerun()

# ── Tab 2: Generate Curriculum ────────────────────────────────────────────────
with tab_gen:
    section_divider("Curriculum Generator")
    help_button("generate-curriculum")
    st.markdown(
        "<span style='color:#a0a0c0;font-family:monospace;font-size:0.85rem;'>"
        "Describe a topic or paste your own notes. The Professor will generate a complete "
        "course JSON that you can import into the Library.</span>",
        unsafe_allow_html=True,
    )

    # Bulk course info for LLM context
    from core.database import get_all_courses, get_modules
    with st.expander("Existing Courses (copy for LLM context)"):
        _all_courses = get_all_courses()
        if _all_courses:
            _lines = []
            for c in _all_courses:
                cid = c.get("course_id", c.get("id", ""))
                title = c.get("title", "")
                data = json.loads(c.get("data") or "{}")
                prereqs = data.get("recommended_prerequisites", data.get("prerequisites", []))
                diff = data.get("difficulty_level", "")
                credits = c.get("credits", data.get("credits", ""))
                mods = get_modules(c["id"])
                mod_names = [m["title"] for m in mods]
                line = f"{cid} | {title}"
                if diff:
                    line += f" | {diff}"
                if credits:
                    line += f" | {credits}cr"
                if prereqs:
                    line += f" | prereqs: {', '.join(prereqs)}"
                if mod_names:
                    line += f" | modules: {', '.join(mod_names[:5])}"
                    if len(mod_names) > 5:
                        line += f"... (+{len(mod_names)-5})"
                _lines.append(line)
            bulk_text = "\n".join(_lines)
            st.code(bulk_text, language="text")
            st.download_button(
                "Download Course List",
                bulk_text,
                file_name="course_catalog.txt",
                mime="text/plain",
                use_container_width=True,
            )
        else:
            st.info("No courses yet. Generate or import one first.")

    topic = st.text_area(
        "Topics / subject matter",
        height=120,
        placeholder="Example: Introduction to Quantum Computing — qubits, gates, entanglement, algorithms",
    )
    n_modules = st.slider("Number of modules", 1, 12, 4)
    n_lec_per = st.slider("Lectures per module", 1, 8, 3)

    if st.button("Generate Course JSON", use_container_width=True):
        if not topic.strip():
            st.warning("Enter a topic description first.")
        else:
            with st.spinner("Professor is designing the curriculum..."):
                try:
                    prof = get_professor()
                    result = prof.generate_curriculum(topic, lectures_per_module=n_lec_per)
                    pass  # professor.generate_curriculum already saves to llm_generated
                    add_xp(50, f"Generated: {topic[:40]}", "curriculum_generated")
                    unlock_achievement("first_curriculum")
                    play_sfx("unlock")
                    st.success("Curriculum generated. Export below or import directly.")
                    st.code(json.dumps(result, indent=2)[:6000] + ("..." if len(json.dumps(result)) > 6000 else ""), language="json")

                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("Import to Library", use_container_width=True):
                            n_ok, _errs = bulk_import_json(result)
                            play_sfx("success")
                            st.success(f"Imported {n_ok} objects to Library.")
                    with col2:
                        raw = json.dumps(result, indent=2)
                        st.download_button(
                            "Download JSON",
                            raw,
                            file_name="generated_course.json",
                            mime="application/json",
                            use_container_width=True,
                        )
                except Exception as e:
                    st.error(f"Generation failed: {e}")

# ── Tab 3: Grade Work ─────────────────────────────────────────────────────────
with tab_grade:
    section_divider("Grade an Essay or Code Submission")
    help_button("grade-work")
    rubric = st.text_input("Grading rubric (optional)", "Accuracy, Depth, Clarity, Examples, Originality")
    work_type = st.radio("Submission type", ["Essay", "Code"], horizontal=True)
    work_text = st.text_area("Paste submission here", height=200)
    max_pts = st.number_input("Max points", 10, 200, 100)

    if st.button("Grade with Professor", use_container_width=True):
        if not work_text.strip():
            st.warning("Paste some work to grade.")
        else:
            with st.spinner("Professor is reviewing..."):
                try:
                    prof = get_professor()
                    if work_type == "Essay":
                        result = prof.grade_essay(work_text, rubric)
                    else:
                        result = prof.grade_code(work_text, rubric)
                    add_xp(10, "Submitted work for grading", "work_graded")
                    st.json(result)
                except Exception as e:
                    st.error(f"Grading failed: {e}")

# ── Tab 4: Create Quiz ────────────────────────────────────────────────────────
with tab_quiz:
    section_divider("Quiz Generator")
    help_button("create-quiz")
    quiz_topic = st.text_input("Topic / lecture title for quiz", "")
    n_q = st.slider("Number of questions", 3, 20, 5)
    q_types = st.multiselect("Question types", ["multiple_choice", "short_answer", "true_false", "fill_blank"], default=["multiple_choice"])
    diff = st.select_slider("Difficulty", ["easy", "medium", "hard", "expert"], value="medium")

    if st.button("Generate Quiz", use_container_width=True):
        if not quiz_topic.strip():
            st.warning("Enter a topic first.")
        else:
            with st.spinner("Professor is crafting questions..."):
                try:
                    prof = get_professor()
                    import json as _json
                    resp = prof.generate_quiz({"title": quiz_topic, "core_terms": []}, n_q)
                    play_sfx("collect")
                    try:
                        raw = resp.parsed_json if hasattr(resp, 'parsed_json') and resp.parsed_json else _json.loads(str(resp))
                        quiz = raw if isinstance(raw, dict) else {"questions": []}
                    except Exception:
                        quiz = {"questions": []}
                    st.success(f"Quiz ready: {len(quiz.get('questions', []))} questions")
                    for i, q in enumerate(quiz.get("questions", []), 1):
                        q_text = q.get('question') or q.get('q', '')
                        with st.expander(f"Q{i}: {q_text[:80]}"):
                            st.markdown(f"**{q_text}**")
                            if q.get("type"):
                                st.write("**Type:**", q.get("type"))
                            if "choices" in q:
                                for c in q["choices"]:
                                    st.write(f"  - {c}")
                            st.markdown(f"**Answer:** `{q.get('answer','')}`")
                            if q.get("explanation"):
                                st.info(q["explanation"])
                except Exception as e:
                    st.error(f"Quiz generation failed: {e}")

# ── Tab 5: Research Rabbit Hole ───────────────────────────────────────────────
with tab_rabbit:
    section_divider("Research Rabbit Hole")
    help_button("research-rabbit-hole")
    st.markdown(
        "<span style='color:#a0a0c0;font-family:monospace;font-size:0.85rem;'>"
        "Enter a keyword or topic. The Professor will reveal its connections, history, "
        "controversies, open problems, and deeper rabbit holes to explore.</span>",
        unsafe_allow_html=True,
    )
    seed_term = st.text_input("Seed keyword or concept", "")
    depth = st.slider("Exploration depth", 1, 5, 2)

    if st.button("Dive In", use_container_width=True):
        if not seed_term.strip():
            st.warning("Enter a keyword to explore.")
        else:
            with st.spinner("Professor is mapping the labyrinth..."):
                try:
                    prof = get_professor()
                    import json as _json2
                    resp2 = prof.research_rabbit_hole(seed_term)
                    add_xp(20, f"Explored: {seed_term}", "rabbit_hole")
                    play_sfx("xp_gain")
                    try:
                        raw2 = resp2.parsed_json if hasattr(resp2, 'parsed_json') and resp2.parsed_json else _json2.loads(str(resp2))
                        result = raw2 if isinstance(raw2, dict) else {"term": seed_term, "overview": str(resp2)}
                    except Exception:
                        result = {"term": seed_term, "overview": str(resp2)}
                    st.markdown(f"### {result.get('term', seed_term)}")
                    st.write(result.get("overview", ""))
                    for key in ("history", "open_problems", "surprising_connections", "hands_on", "papers"):
                        items = result.get(key, [])
                        if items:
                            with st.expander(key.replace("_", " ").title()):
                                if isinstance(items, list):
                                    for item in items:
                                        st.write(f"  {item}")
                                else:
                                    st.write(items)
                except Exception as e:
                    st.error(f"Failed: {e}")

# ── Tab 6: Chat History Browser ───────────────────────────────────────────────
with tab_history:
    section_divider("Chat History")
    from core.chat_store import list_sessions, load_session, label_session, export_for_llm

    sessions = list_sessions()
    if not sessions:
        st.info("No saved chat sessions yet. Start chatting in the Chat tab.")
    else:
        st.markdown(f"**{len(sessions)} saved sessions**")

        # Session list
        for s in sessions[:30]:
            sid = s.get("session_id", "")
            label = s.get("label", sid)
            count = s.get("message_count", 0)
            with st.expander(f"{label}  ({count} messages)"):
                new_label = st.text_input("Label", value=label, key=f"lbl_{sid}")
                if new_label != label:
                    label_session(sid, new_label)

                msgs = load_session(sid)
                for msg in msgs[-30:]:
                    role = msg.get("role", "unknown")
                    icon = "user" if role == "user" else "assistant"
                    with st.chat_message(icon):
                        st.markdown(sanitize_llm_output(msg.get("content", "")[:1000]))

                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Load in Chat Tab", key=f"load_{sid}"):
                        st.session_state["chat_session_id"] = sid
                        st.rerun()
                with c2:
                    llm_text = export_for_llm(sid)
                    st.download_button(
                        "Export for LLM",
                        llm_text,
                        file_name=f"chat_{sid}.txt",
                        mime="text/plain",
                        key=f"exp_{sid}",
                    )

# ── Tab 7: App Guide ─────────────────────────────────────────────────────────
with tab_guide:
    section_divider("App Guide — Ask About Any Feature")
    st.markdown(
        "<span style='color:#a0a0c0;font-family:monospace;font-size:0.85rem;'>"
        "Ask the Professor how to use any feature of The God Factory University. "
        "The Professor reads the app documentation and explains in depth — "
        "without revealing any code secrets.</span>",
        unsafe_allow_html=True,
    )

    quick_topics = [
        "How do I import a course?",
        "How does grading work?",
        "What LLM providers are available?",
        "How do I render a lecture video?",
        "What are binaural beats?",
        "How does the degree system work?",
        "How do I set up Ollama locally?",
        "What is the XP and level system?",
    ]

    st.markdown("**Quick Questions:**")
    cols = st.columns(2)
    selected_quick = None
    for i, q in enumerate(quick_topics):
        with cols[i % 2]:
            if st.button(q, key=f"quick_{i}", use_container_width=True):
                selected_quick = q

    custom_q = st.text_input("Or ask your own question:", "")
    question = selected_quick or custom_q

    if question and (selected_quick or st.button("Ask Professor", use_container_width=True)):
        with st.spinner("Professor is consulting the archives..."):
            try:
                prof = get_professor()
                answer = prof.explain_app(question)
                st.markdown("### Answer")
                st.markdown(sanitize_llm_output(answer))
                add_xp(5, "App guide query", "help")
            except Exception as e:
                st.error(f"Failed: {e}")
