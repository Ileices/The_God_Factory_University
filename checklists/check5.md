# THE GOD FACTORY UNIVERSITY: RECURSIVE COURSE SYSTEM & ACADEMIC RIGOR CHECKLIST

> **Created**: 2026-03-14
> **Purpose**: Implement recursive course decomposition, jargon sub-courses, pacing system,
>   real-world benchmark tracking, academic integrity, and realistic credit-hour requirements.
> **Scope**: Brings the university from toy-scale (45 hrs = doctorate) to real-scale
>   (8,100+ verified hours = doctorate) rivaling MIT/Harvard rigor.

---

## Phase 1: Schema & Database Foundation

### 1.1 Course Tree Structure
- [x] Add `parent_course_id TEXT` column to courses table (self-referential FK, NULL = root course)
- [x] Add `depth_level INTEGER DEFAULT 0` to courses (0 = root, 1+ = sub-course depth)
- [x] Add `depth_target INTEGER DEFAULT 0` to courses (expected decomposition depth for full credit)
- [x] Add `pacing TEXT DEFAULT 'standard'` to courses (enum: 'fast', 'standard', 'slow')
- [x] Add `credit_hours REAL DEFAULT 0` to courses (actual instructional + study hours logged)
- [x] Add `is_jargon_course INTEGER DEFAULT 0` to courses (boolean flag)
- [x] Add `jargon TEXT` to courses (JSON: key terms, definitions, etymology, usage examples)
- [x] Add `ai_policy TEXT` to assignments (JSON: allowed_uses, prohibited_uses, verification_required)
- [x] Schema migration #2 for all new columns (ALTER TABLE with safe error handling)
- [x] Update `upsert_course()` to accept and persist new fields
- [x] Update `get_all_courses()` / `get_course()` to return new fields

### 1.2 Course Tree Queries
- [x] `get_child_courses(parent_id)` — direct children of a course
- [x] `get_course_tree(root_id)` — full recursive tree (CTE query)
- [x] `get_course_depth(course_id)` — current max depth of a course's tree
- [x] `get_root_course(course_id)` — walk up to find the root parent
- [x] `course_completion_pct(course_id)` — % of sub-tree lectures completed
- [x] `course_credit_hours_logged(course_id)` — sum of actual hours in sub-tree

### 1.3 Credit-Hour System
- [x] Define `CREDIT_HOUR_RATIO = 45` — 1 credit = 45 total hours (Carnegie standard)
- [x] `compute_credit_hours(course_id)` — instruction_time + study_time + assessment_time
- [x] `earned_credit_hours()` — total verified hours across all completed sub-trees
- [x] Update `credits_earned()` to use credit-hour calculation (hours / 45 = credits)
- [x] Update DEGREE_TRACKS to reflect real requirements:
  - Certificate: 15 credits (675 hours)
  - Associate: 60 credits (2,700 hours)
  - Bachelor: 120 credits (5,400 hours)
  - Master: 150 credits (6,750 hours)
  - Doctorate: 180 credits (8,100 hours + qualifying exams + dissertation)
- [x] Fractional credit display in UI (e.g., "0.33 of 3.0 credits earned")

### 1.4 Schema Validation Updates
- [x] Add `parent_course_id` to course_validation_schema.json
- [x] Add `depth_target` to schema
- [x] Add `pacing` enum to schema
- [x] Add `jargon` object definition to schema
- [x] Add `ai_policy` to assignment definition in schema
- [x] Update `difficulty_level` enum (keep existing values)

---

## Phase 2: Course Decomposition Engine

### 2.1 Recursive Decomposition (core/course_tree.py — NEW FILE)
- [x] `decompose_course(course_id, depth=1)` — Professor AI generates sub-courses from topic blocks
- [x] Each topic block in parent → becomes its own full sub-course with modules/lectures
- [x] At depth ≥ 2: include implementation courses (build/code the concept)
- [x] At depth ≥ 3: include real-world application courses (industry use cases)
- [x] Link parent ↔ child via `parent_course_id`
- [x] Auto-generate jargon sub-course for each decomposed course
- [x] Respect `depth_target` — warn when target depth reached

### 2.2 Pacing Integration
- [x] Fast pace: 2-3 concepts per lecture, rapid progression, minimal repetition
- [x] Standard pace: 1 concept per lecture, balanced theory + practice
- [x] Slow pace: 1 concept across 2-4 lectures (intro → detail → edge cases → assessment)
- [x] Pacing stored per course, inheritable from parent if not set
- [x] Professor AI prompt templates for each pacing level
- [x] Pacing affects lecture count and duration in generated sub-courses

### 2.3 Jargon Course Generation
- [x] `generate_jargon_course(course_id)` — extract key terms from parent course
- [x] Jargon course structure: term → definition → etymology → context → quiz
- [x] Mark as `is_jargon_course=1`, linked via `parent_course_id`
- [x] Extra credit: jargon courses worth 0.5 credits each
- [x] Professor AI prompt for jargon extraction and course building

### 2.4 Curriculum Generator Update
- [x] Update `generate_curriculum.py` to support `parent_course_id` field
- [x] Add `--decompose` flag to recursively generate sub-courses
- [x] Add `--depth N` flag to control decomposition depth
- [x] Add `--pacing fast|standard|slow` flag
- [x] Update credit calculation in generator (credit_map uses hours-based system)

---

## Phase 3: Assessment & Academic Integrity

### 3.1 AI Policy Framework
- [x] Define AI policy levels per assignment type:
  - `unrestricted` — AI use allowed freely (research, brainstorming)
  - `assisted` — AI allowed for specific tasks (charts, grammar) but not core work
  - `supervised` — AI used under constraints, must produce verification artifact
  - `prohibited` — no AI assistance allowed (exams, qualifying tests)
- [x] `ai_policy` JSON structure: `{level, allowed_uses[], prohibited_uses[], verification_type}`
- [x] Verification types: `none`, `original_example`, `oral_explanation`, `peer_review`
- [x] Default policies per course type:
  - English/Writing: `assisted` (AI for charts/research, not essays)
  - Programming: `supervised` (AI debug OK if student reproduces independently)
  - Math/Science: `assisted` (computation tools OK, proofs must be original)
  - Exams: `prohibited`

### 3.2 Verification Assignments
- [x] "Prove-it" assignment type: auto-generated after AI-assisted work
- [x] Student must produce original work demonstrating same concept without AI
- [x] Grade comparison: if prove-it score << original score → flag for review
- [x] Professor AI method: `generate_verification(assignment_id)` — create prove-it variant

### 3.3 Competency Assessment
- [x] Competency levels: `recall`, `understanding`, `application`, `analysis`, `synthesis`, `evaluation` (Bloom's Taxonomy)
- [x] Each course tracks mastery across Bloom's levels via assignments
- [x] Course completion requires minimum scores at each applicable Bloom's level
- [x] `get_competency_profile(course_id)` — returns scores per Bloom's level
- [x] `check_mastery(course_id)` — verifies all required competency levels met

---

## Phase 4: Tracking & Benchmarks

### 4.1 Qualification Tracking (core/qualifications.py — NEW FILE)
- [x] New table: `competency_benchmarks` (benchmark_id, name, description, required_courses JSON, min_gpa, min_hours)
- [x] New table: `qualification_progress` (student qualification tracking, auto-updated)
- [x] Seed benchmarks for industry-standard qualifications:
  - "Equivalent to MIT 6.006 (Intro to Algorithms)" — requires CS 301 + sub-courses, GPA ≥ 3.0
  - "Equivalent to Stanford CS229 (Machine Learning)" — requires CS 450 + CS 610, GPA ≥ 3.0
  - "CompTIA A+ Equivalent" — requires specific IT coursework bundle
  - "AWS Cloud Practitioner Equivalent" — requires cloud computing coursework
- [x] `check_qualifications()` — scan all benchmarks, update progress
- [x] `get_qualifications()` — return list with earned/in-progress/locked status
- [x] `get_qualification_roadmap(benchmark_id)` — remaining courses needed

### 4.2 Credit-Hour Logging
- [x] Track instruction time: lecture watch time (from progress.watch_time_s)
- [x] Track study time: study_sessions.duration_min
- [x] Track assessment time: assignment attempt duration
- [x] `log_study_hours(course_id, hours, activity_type)` — manual time logging
- [x] Aggregate across course tree for parent course credit calculation
- [x] Dashboard: hours logged vs. hours required per course

### 4.3 Real-World Benchmark Comparison
- [x] Benchmark data structure: {school, course_name, credit_hours, topics_covered, assessment_types}
- [x] Comparison display: "Your CS 301 covers X of Y topics from MIT 6.006"
- [x] Gap analysis: "To match MIT 6.006, you still need: [topic list]"
- [x] Rigor rating: percentage of target benchmark covered

---

## Phase 5: UI Integration

### 5.1 Course Tree UI (pages/01_Library.py updates)
- [x] Nested expandable tree view for courses with sub-courses
- [x] Depth indicator (visual indentation + level badge)
- [x] "Decompose" button on each course → triggers sub-course generation
- [x] Pacing selector dropdown per course
- [x] Jargon course indicator and quick-access link
- [x] Progress bar that reflects sub-tree completion (not just direct lectures)

### 5.2 Grades & Credits UI (pages/06_Grades.py updates)
- [x] Credit-hours display alongside credit count
- [x] Fractional credits earned per course (based on sub-tree completion %)
- [x] Updated degree progress using credit-hour calculation
- [x] Time-to-degree estimate based on current study rate

### 5.3 Qualifications Dashboard (pages/18_Qualifications.py — NEW PAGE)
- [x] List all tracked qualifications with earned/in-progress/locked status
- [x] Progress bars per qualification
- [x] Roadmap view: remaining courses per qualification
- [x] Benchmark comparison cards (vs MIT, Stanford, etc.)

### 5.4 Academic Integrity UI
- [x] AI policy badge on each assignment (🟢 unrestricted / 🟡 assisted / 🟠 supervised / 🔴 prohibited)
- [x] "Prove-it" challenge prompt after AI-assisted submissions
- [x] Competency radar chart per course (Bloom's taxonomy levels)

---

## Cross-References to Existing Checklists

> These items from check1-4 are directly addressed or enhanced by this plan:

### From check1.md
- [x] §7 Gamification: 10 levels (enhanced with credit-hour tracking)
- [ ] §3 Curriculum: K-doctorate progression (enhanced with recursive decomposition)
- [ ] §5 AI Professor: curriculum generation (enhanced with decompose_course)

### From check3.md
- [ ] Phase 0.5: Academic calendar & terms (needed for credit-hour tracking)
- [ ] Phase 3: Full Curriculum K-Doctorate (enhanced with sub-courses)
- [ ] Phase 5: Student Profile & Statistics (enhanced with qualification tracking)
- [ ] Phase 6: Behavioral Assessment (partially covered by competency tracking)

### From check4.md
- [ ] §D.1: Academic Infrastructure Gaps (course tree fills the biggest gap)
- [ ] §D.4: Prerequisite enforcement (tree structure creates natural prerequisites)
- [ ] §D.5: Credit-hour system (fully implemented here)

---

## Implementation Notes

**File Size Discipline**: All new files ≤ 1000 LOC. Split if approaching limit.
**Migration Safety**: All ALTER TABLE in try/except for idempotency.
**Backward Compatibility**: Existing courses continue to work (parent_course_id=NULL, depth=0).
**Test Coverage**: New tests for tree queries, credit calculation, decomposition.
