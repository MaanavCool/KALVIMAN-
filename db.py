# db.py
# ════════════════════════════════════════════════════════════════
# Tiny SQLite storage layer. No server, no password — the database
# is a single file (gcare_data.db) created automatically on first run.
#
# Every student row also stores the ML result, so the Excel export
# and the report page never have to re-run the model.
# ════════════════════════════════════════════════════════════════

import sqlite3
import json
from datetime import datetime
from config import SQLITE_PATH as DB_PATH

# All answer columns coming from the form (order = INSERT order)
STUDENT_COLS = [
    "name", "age", "gender", "email", "phone", "city", "state", "country",
    "stream", "school_college", "current_degree", "institution_name",
    "academic_percent", "board", "has_backlogs", "parent_occupation", "family_income",
    "rate_problem_solving", "rate_creating", "rate_helping_people",
    "rate_selling", "rate_data", "rate_leading", "rate_building", "rate_teaching",
    "rate_research", "rate_opportunity",
    "interest_areas", "activity_flow", "help_asked", "proud_achievement",
    "problem_solving_style", "learning_style", "work_style", "decision_style",
    "stress_style", "work_pace", "easy_subjects", "hard_subjects", "project_approach",
    "dream_careers", "career_reason", "career_influence", "work_preference",
    "career_scale", "desired_impact", "experience", "entrepreneurial",
    "income_priority", "work_environment", "work_life_balance", "work_timing",
    "preferred_country", "success_at_30",
    "education_budget", "funding_comfort", "willing_to_relocate", "target_degree",
    "language_comfort", "competitive_exams", "exam_scores",
    "abroad_interest", "target_countries", "abroad_reason", "abroad_concern",
    "english_score", "abroad_progress",
    "college_priority", "institution_type", "campus_size", "accreditation_importance",
    "shortlisted_colleges", "target_exams", "industry_connect",
    "study_field", "emerging_fields", "dual_degree_interest", "post_ug_plan",
    "target_course", "course_confusion",
    "rate_finishes_tasks", "rate_works_pressure", "rate_asks_help",
    "rate_recovers_setbacks", "rate_time_management", "rate_initiative",
    "rate_focus", "rate_criticism", "rate_adaptability",
    "challenge_overcome", "tough_decision",
    "guidance_priority", "clarity_needed", "biggest_worry", "decision_maker",
    "decision_timeline", "prior_counselling", "referral_source", "additional_info",
]

# ML result columns saved alongside each student
ML_COLS = [
    "ml_best_fit", "ml_match_percent", "ml_top3",
    "ml_resilience", "ml_report",
]

INT_COLS = {
    "age", "rate_problem_solving", "rate_creating", "rate_helping_people",
    "rate_selling", "rate_data", "rate_leading", "rate_building", "rate_teaching",
    "rate_finishes_tasks", "rate_works_pressure", "rate_asks_help",
    "rate_recovers_setbacks", "rate_time_management", "ml_match_percent",
}


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the students table if it doesn't exist."""
    col_defs = ["id INTEGER PRIMARY KEY AUTOINCREMENT",
                "submitted_at TEXT"]
    for c in STUDENT_COLS + ML_COLS:
        if c == "ml_resilience":
            col_defs.append(f"{c} REAL")
        elif c in INT_COLS:
            col_defs.append(f"{c} INTEGER")
        else:
            col_defs.append(f"{c} TEXT")
    ddl = "CREATE TABLE IF NOT EXISTS students (\n  " + ",\n  ".join(col_defs) + "\n)"
    conn = _connect()
    conn.execute(ddl)
    conn.commit()
    conn.close()


def email_exists(email: str) -> bool:
    conn = _connect()
    row = conn.execute("SELECT 1 FROM students WHERE lower(email)=?",
                       (email.strip().lower(),)).fetchone()
    conn.close()
    return row is not None


def insert_student(answers: dict, ml: dict) -> int:
    """Insert one student + ML result. Returns the new id."""
    cols = ["submitted_at"] + STUDENT_COLS + ML_COLS
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    values = [now]
    for c in STUDENT_COLS:
        v = answers.get(c)
        if c in INT_COLS and v not in (None, ""):
            try: v = int(v)
            except (TypeError, ValueError): v = None
        values.append(v)

    values += [
        ml.get("best_fit"),
        ml.get("match_percent"),
        json.dumps(ml.get("top_three", [])),
        ml.get("resilience_score"),
        ml.get("summary_text"),
    ]

    placeholders = ", ".join(["?"] * len(cols))
    conn = _connect()
    cur = conn.execute(
        f"INSERT INTO students ({', '.join(cols)}) VALUES ({placeholders})", values)
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def _row_to_dict(row):
    d = dict(row)
    if d.get("ml_top3"):
        try: d["ml_top3_parsed"] = json.loads(d["ml_top3"])
        except (ValueError, TypeError): d["ml_top3_parsed"] = []
    return d


def fetch_all(filters: dict | None = None):
    sql = "SELECT * FROM students WHERE 1=1"
    params = []
    filters = filters or {}
    if filters.get("q"):
        sql += " AND (name LIKE ? OR email LIKE ? OR city LIKE ? OR dream_careers LIKE ?)"
        like = f"%{filters['q']}%"; params += [like, like, like, like]
    if filters.get("degree"):
        sql += " AND current_degree = ?";    params.append(filters["degree"])
    if filters.get("work_pref"):
        sql += " AND work_preference = ?";   params.append(filters["work_pref"])
    if filters.get("country"):
        sql += " AND preferred_country = ?"; params.append(filters["country"])
    if filters.get("budget"):
        sql += " AND education_budget = ?";  params.append(filters["budget"])
    sql += " ORDER BY id DESC"
    conn = _connect()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def fetch_one(student_id: int):
    conn = _connect()
    row = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def get_stats():
    conn = _connect()
    def group(col):
        rows = conn.execute(
            f"SELECT {col} AS k, COUNT(*) AS c FROM students GROUP BY {col}").fetchall()
        return {(r["k"] or "—"): r["c"] for r in rows}
    total = conn.execute("SELECT COUNT(*) AS t FROM students").fetchone()["t"]
    stats = {
        "total": total,
        "by_degree":  group("current_degree"),
        "by_work":    group("work_preference"),
        "by_country": group("preferred_country"),
        "by_cluster": group("ml_best_fit"),
    }
    conn.close()
    return stats


# ── FEEDBACK SYSTEM (for AI learning & model improvement) ──────────
def init_feedback_table():
    conn = _connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS report_feedback (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id  INTEGER,
            accuracy    INTEGER,
            usefulness  INTEGER,
            best_fit_correct TEXT,
            actual_choice    TEXT,
            comments    TEXT,
            created_at  TEXT,
            FOREIGN KEY (student_id) REFERENCES students(id)
        )
    """)
    conn.commit()
    conn.close()


def save_feedback(student_id, accuracy, usefulness, best_fit_correct, actual_choice, comments):
    from datetime import datetime
    conn = _connect()
    conn.execute(
        "INSERT INTO report_feedback (student_id, accuracy, usefulness, best_fit_correct, "
        "actual_choice, comments, created_at) VALUES (?,?,?,?,?,?,?)",
        (student_id, accuracy, usefulness, best_fit_correct, actual_choice, comments,
         datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()


def get_feedback_stats():
    conn = _connect()
    rows = conn.execute("SELECT * FROM report_feedback").fetchall()
    conn.close()
    if not rows:
        return {"total": 0, "avg_accuracy": 0, "avg_usefulness": 0, "correct_pct": 0}
    total = len(rows)
    avg_acc = sum(r["accuracy"] or 3 for r in rows) / total
    avg_use = sum(r["usefulness"] or 3 for r in rows) / total
    correct = sum(1 for r in rows if r["best_fit_correct"] == "Yes") / total * 100
    return {"total": total, "avg_accuracy": round(avg_acc, 1),
            "avg_usefulness": round(avg_use, 1), "correct_pct": round(correct)}


def get_training_feedback():
    """Get feedback data that can be used to retrain the model.
    Returns list of dicts with student answers + whether the prediction was correct."""
    conn = _connect()
    rows = conn.execute("""
        SELECT s.*, f.best_fit_correct, f.actual_choice
        FROM report_feedback f
        JOIN students s ON s.id = f.student_id
        WHERE f.best_fit_correct IS NOT NULL
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Employer & Jobs ───────────────────────────────────────────────
def _init_employer_tables():
    conn = _connect(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS employers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name TEXT, contact_person TEXT, email TEXT, phone TEXT,
        industry TEXT, website TEXT, city TEXT, description TEXT,
        created_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employer_id INTEGER, title TEXT, description TEXT, location TEXT,
        salary_range TEXT, skills_required TEXT, degree_required TEXT,
        job_type TEXT, created_at TEXT,
        FOREIGN KEY (employer_id) REFERENCES employers(id))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS visitor_count (
        id INTEGER PRIMARY KEY, total INTEGER DEFAULT 0)""")
    cur.execute("INSERT OR IGNORE INTO visitor_count (id, total) VALUES (1, 0)")
    conn.commit(); cur.close(); conn.close()

def insert_employer(data):
    from datetime import datetime
    p = '?'
    cols = ["company_name","contact_person","email","phone","industry","website","city","description","created_at"]
    vals = [data.get(c,"") for c in cols[:-1]] + [datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
    conn = _connect(); cur = conn.cursor()
    cur.execute(f"INSERT INTO employers ({','.join(cols)}) VALUES ({','.join([p]*len(cols))})", vals)
    eid = cur.lastrowid; conn.commit(); cur.close(); conn.close()
    return eid

def insert_job(data):
    from datetime import datetime
    p = '?'
    cols = ["employer_id","title","description","location","salary_range","skills_required","degree_required","job_type","created_at"]
    vals = [data.get(c,"") for c in cols[:-1]] + [datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
    conn = _connect(); cur = conn.cursor()
    cur.execute(f"INSERT INTO jobs ({','.join(cols)}) VALUES ({','.join([p]*len(cols))})", vals)
    jid = cur.lastrowid; conn.commit(); cur.close(); conn.close()
    return jid

def get_jobs():
    conn = _connect(); cur = conn.cursor()
    cur.execute("SELECT j.*, e.company_name FROM jobs j LEFT JOIN employers e ON j.employer_id=e.id ORDER BY j.id DESC")
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return rows

def search_candidates(skills=None, degree=""):
    p = '?'
    sql = "SELECT id, name, email, city, current_degree, interest_areas, ml_best_fit, ml_match_percent FROM students WHERE 1=1"
    params = []
    if degree:
        sql += f" AND current_degree={p}"; params.append(degree)
    if skills:
        for s in skills[:5]:
            sql += f" AND (interest_areas LIKE {p} OR ml_best_fit LIKE {p})"
            params += [f"%{s}%", f"%{s}%"]
    sql += " ORDER BY ml_match_percent DESC LIMIT 50"
    conn = _connect(); cur = conn.cursor()
    cur.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return rows

def increment_visitor():
    conn = _connect(); cur = conn.cursor()
    cur.execute("UPDATE visitor_count SET total = total + 1 WHERE id = 1")
    conn.commit(); cur.close(); conn.close()

def get_visitor_count():
    conn = _connect(); cur = conn.cursor()
    cur.execute("SELECT total FROM visitor_count WHERE id=1")
    r = cur.fetchone()
    cur.close(); conn.close()
    return {"visitors": (dict(r) if r else {}).get("total", 0)}

# Auto-init employer tables
try:
    _init_employer_tables()
except:
    pass
