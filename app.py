"""
KALVIMAN API SERVER (Decoupled Backend)
========================================
Pure JSON API — no HTML serving.
Frontend is a separate React app deployed to S3/CloudFront.
This API deploys to EC2 behind Nginx.
"""

import os, json
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

import db
import otp
from security import apply_security_headers, sanitize_dict, rate_limit
from excel_sync import rebuild_excel
from ml.career_model import generate_report
from config import (EXCEL_PATH, MODEL_PATH, FLASK_HOST, FLASK_PORT, FLASK_DEBUG, SQLITE_PATH)

app = Flask(__name__)

# CORS — allow React frontend (S3/CloudFront) to call this API
# In production, replace '*' with your actual CloudFront domain
CORS(app, origins=["*"], supports_credentials=True)

# Security headers on every response
app.after_request(apply_security_headers)

# Init database
db.init_db()


# ════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ════════════════════════════════════════════════════════════════
@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "kalviman-api",
        "version": "1.0.0",
        "database": "sqlite",
        "timestamp": datetime.now().isoformat()
    })


# ════════════════════════════════════════════════════════════════
# AUTH — OTP
# ════════════════════════════════════════════════════════════════
@app.route("/api/send-otp", methods=["POST"])
@rate_limit(max_per_minute=5)
def send_otp_route():
    d = sanitize_dict(request.json or {})
    name = (d.get("name") or "").strip()
    phone = (d.get("phone") or "").strip()
    email = (d.get("email") or "").strip().lower()

    if not name or not email:
        return jsonify({"ok": False, "error": "Name and email are required."}), 400

    if db.email_exists(email):
        return jsonify({"ok": False, "error": "This email has already been used for an assessment."}), 409

    result = otp.request_otp(name, phone, email)
    return jsonify(result), 200 if result["ok"] else 400


@app.route("/api/verify-otp", methods=["POST"])
@rate_limit(max_per_minute=10)
def verify_otp_route():
    d = sanitize_dict(request.json or {})
    email = (d.get("email") or "").strip().lower()
    code = (d.get("code") or "").strip()

    if not email or not code:
        return jsonify({"ok": False, "error": "Email and code are required."}), 400

    result = otp.verify_otp(email, code)
    return jsonify(result), 200 if result["ok"] else 400


# ════════════════════════════════════════════════════════════════
# ASSESSMENT — SUBMIT + REPORT
# ════════════════════════════════════════════════════════════════
@app.route("/api/submit", methods=["POST"])
@rate_limit(max_per_minute=5)
def submit_student():
    data = sanitize_dict(request.json or {})
    email = (data.get("email") or "").strip().lower()

    if not email or not data.get("name"):
        return jsonify({"error": "Name and email are required."}), 400

    if not otp.is_verified(email):
        return jsonify({"error": "Email not verified. Complete OTP first."}), 403

    # Generate ML report
    from config import AI_API_KEY
    report = generate_report(MODEL_PATH, data, api_key=AI_API_KEY)

    # Store in DB
    student_id = db.insert_student(data, report)

    # Update Excel
    try:
        rebuild_excel(db.fetch_all())
    except Exception as e:
        print(f"[Excel] {e}")

    # Generate student ID
    gid = f"KALVIMAN-{str(student_id).zfill(5)}"

    return jsonify({
        "success": True,
        "id": student_id,
        "gid": gid,
        "best_fit": report.get("best_fit"),
        "match": report.get("match_percent"),
    })


@app.route("/api/report/<int:student_id>")
def get_report(student_id):
    row = db.fetch_one(student_id)
    if not row:
        return jsonify({"error": "Student not found."}), 404

    from config import AI_API_KEY
    report = generate_report(MODEL_PATH, row, api_key=AI_API_KEY)
    report["name"] = row.get("name")
    report["gcare_id"] = f"KALVIMAN-{str(student_id).zfill(5)}"
    report["student_id"] = student_id
    return jsonify(report)


# ════════════════════════════════════════════════════════════════
# ADMIN — STUDENTS
# ════════════════════════════════════════════════════════════════
@app.route("/api/students")
def list_students():
    filters = {
        "q": request.args.get("q", ""),
        "degree": request.args.get("degree", ""),
        "work_pref": request.args.get("work_pref", ""),
        "country": request.args.get("country", ""),
        "budget": request.args.get("budget", ""),
    }
    rows = db.fetch_all(filters)
    return jsonify({"total": len(rows), "students": rows})


@app.route("/api/students/<int:student_id>")
def get_student(student_id):
    row = db.fetch_one(student_id)
    if not row:
        return jsonify({"error": "Student not found."}), 404
    return jsonify(row)


@app.route("/api/stats")
def stats():
    return jsonify(db.get_stats())


# ════════════════════════════════════════════════════════════════
# AI CHATBOT — MANDY
# ════════════════════════════════════════════════════════════════
@app.route("/api/mandy", methods=["POST"])
@rate_limit(max_per_minute=15)
def mandy_chat():
    d = sanitize_dict(request.json or {})
    message = (d.get("message") or "").strip()
    history = d.get("history", [])

    if not message:
        return jsonify({"reply": "Hi! I'm MANDY, your Kalviman AI assistant. Ask me anything about courses, colleges, or studying abroad!"}), 200

    from config import AI_MODE, AI_API_KEY

    if AI_MODE == "api" and AI_API_KEY:
        reply = _mandy_api(message, history, AI_API_KEY)
    else:
        reply = _mandy_respond(message)
    return jsonify({"reply": reply})


def _mandy_api(message, history, api_key):
    """Call Google Gemini API (FREE) for intelligent responses."""
    import urllib.request
    try:
        chat_context = ""
        for h in history[-10:]:
            role = "Student" if h.get("role") == "user" else "MANDY"
            chat_context += f"{role}: {h.get('content', '')}\n"

        prompt = (
            "You are MANDY, the friendly AI assistant for Kalviman — an AI-powered career "
            "guidance platform for Indian students aged 16-25. You help with: course selection, "
            "college selection, studying abroad, entrance exams, scholarships, career paths, "
            "and salary expectations.\n\n"
            "Rules: Be warm and direct. Give specific advice. For complex questions, suggest "
            "taking the free Kalviman assessment. Keep responses 3-8 sentences.\n\n"
            f"Conversation:\n{chat_context}\nStudent: {message}\n\nRespond as MANDY:"
        )

        body = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 600}
        }).encode()

        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print(f"[MANDY API error] {e}")
        return _mandy_respond(message)


def _mandy_respond(msg):
    """Rule-based fallback — works without any API key."""
    ml = msg.lower()
    if any(w in ml for w in ["hi","hello","hey"]):
        return "Hey there! I'm MANDY, your Kalviman career assistant. Ask me about courses, colleges, studying abroad, or take our free assessment!"
    if any(w in ml for w in ["abroad","overseas","usa","uk","germany","canada","ielts"]):
        return "For studying abroad: USA needs GRE/TOEFL, UK offers 1-year masters, Canada has strong PR pathways, Germany is often tuition-free. Our assessment has a dedicated Study Abroad section that analyses your budget and goals. Take it for personalised recommendations!"
    if any(w in ml for w in ["college","iit","nit","bits","university"]):
        return "Choosing a college depends on your field, budget, and entrance exam scores. IITs/NITs are top government options (JEE), BITS has its own exam, VIT/SRM/Manipal are strong private choices. Our assessment matches your profile to specific colleges — try it!"
    if any(w in ml for w in ["course","btech","mbbs","mba","stream"]):
        return "Course selection is the biggest career decision! Match it to your strengths, not trends. Consider the career roles it leads to and your post-UG plans. Our assessment analyses all of this across 98 questions — take it for a personalised recommendation!"
    if any(w in ml for w in ["salary","job","placement","career"]):
        return "Salaries vary by field: Software ₹6-40L+, Data Science ₹8-50L+, Finance ₹6-40L+, Medicine ₹6-30L+. Our report includes salary ranges for your best-fit direction!"
    if any(w in ml for w in ["thank","bye","goodbye"]):
        return "You're welcome! Take the free Kalviman assessment whenever you're ready — 20 minutes that could change your trajectory. Good luck!"
    return "Great question! For personalised advice, take our free 20-minute assessment — it analyses 98 data points and gives you an AI-generated career report. Click 'Get Started' to begin!"


# ════════════════════════════════════════════════════════════════
# FEEDBACK & LEARNING
# ════════════════════════════════════════════════════════════════
@app.route("/api/feedback", methods=["POST"])
@rate_limit(max_per_minute=10)
def submit_feedback():
    d = sanitize_dict(request.json or {})
    sid = d.get("student_id")
    if not sid:
        return jsonify({"error": "student_id required"}), 400
    db.save_feedback(
        student_id=sid,
        accuracy=d.get("accuracy", 3),
        usefulness=d.get("usefulness", 3),
        best_fit_correct=d.get("best_fit_correct", ""),
        actual_choice=d.get("actual_choice", ""),
        comments=d.get("comments", ""),
    )
    return jsonify({"ok": True, "message": "Thank you — your feedback helps our AI improve."})


@app.route("/api/feedback-stats")
def feedback_stats():
    return jsonify(db.get_feedback_stats())


@app.route("/api/retrain", methods=["POST"])
@rate_limit(max_per_minute=1)
def retrain_model():
    try:
        from ml.career_model import train_and_save
        acc = train_and_save(MODEL_PATH, n_per_cluster=350, verbose=False)
        return jsonify({"ok": True, "accuracy": acc, "message": f"Model retrained. Accuracy: {acc:.3f}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ════════════════════════════════════════════════════════════════
# DATA EXPORT
# ════════════════════════════════════════════════════════════════
@app.route("/api/download-excel")
def download_excel():
    rebuild_excel(db.fetch_all())
    if not os.path.exists(EXCEL_PATH):
        return jsonify({"error": "Excel file not found"}), 404
    return send_file(EXCEL_PATH, as_attachment=True,
        download_name=f"Kalviman_Students_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx")


# ════════════════════════════════════════════════════════════════
# STARTUP
# ════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 55)
    print("  KALVIMAN API SERVER (Decoupled)")
    print("=" * 55)
    print(f"  API     ->  http://localhost:{FLASK_PORT}/api/health")
    print(f"  Storage ->  SQLite ({SQLITE_PATH})")
    print(f"  Model   ->  {MODEL_PATH}")
    print("=" * 55)
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)


# ════════════════════════════════════════════════════════════════
# EMPLOYER REGISTRATION & JOB POSTING
# ════════════════════════════════════════════════════════════════
@app.route("/api/employer/register", methods=["POST"])
@rate_limit(max_per_minute=5)
def employer_register():
    d = sanitize_dict(request.json or {})
    required = ["company_name", "contact_person", "email", "phone"]
    missing = [f for f in required if not (d.get(f) or "").strip()]
    if missing:
        return jsonify({"error": f"Missing: {', '.join(missing)}"}), 400
    eid = db.insert_employer(d)
    # Send welcome email
    _send_welcome_email(d.get("email"), d.get("contact_person"), "employer")
    return jsonify({"ok": True, "id": eid, "message": "Registration successful. Welcome to Kalviman!"})


@app.route("/api/employer/jobs", methods=["POST"])
@rate_limit(max_per_minute=10)
def post_job():
    d = sanitize_dict(request.json or {})
    if not d.get("title") or not d.get("employer_id"):
        return jsonify({"error": "Job title and employer_id required."}), 400
    jid = db.insert_job(d)
    return jsonify({"ok": True, "id": jid})


@app.route("/api/employer/jobs")
def list_jobs():
    return jsonify(db.get_jobs())


@app.route("/api/employer/search-candidates", methods=["POST"])
def search_candidates():
    d = request.json or {}
    skills = d.get("skills", [])
    degree = d.get("degree", "")
    results = db.search_candidates(skills=skills, degree=degree)
    return jsonify({"total": len(results), "candidates": results})


# ════════════════════════════════════════════════════════════════
# VISITOR COUNTER
# ════════════════════════════════════════════════════════════════
@app.route("/api/visitor-count", methods=["POST"])
def track_visitor():
    db.increment_visitor()
    return jsonify({"ok": True})


@app.route("/api/visitor-count")
def get_visitor_count():
    return jsonify(db.get_visitor_count())


# ════════════════════════════════════════════════════════════════
# WELCOME EMAIL
# ════════════════════════════════════════════════════════════════
def _send_welcome_email(email, name, user_type="student"):
    from config import EMAIL_ADDRESS, EMAIL_APP_PASSWORD, SMTP_HOST, SMTP_PORT
    if not EMAIL_ADDRESS or not EMAIL_APP_PASSWORD:
        print(f"[Welcome] Would send to {email} (email not configured)")
        return
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        subject = "Welcome to Kalviman!" if user_type == "student" else "Welcome to Kalviman — Employer Portal"
        html = f"""<div style="font-family:Arial,sans-serif;max-width:520px;margin:auto;padding:32px">
        <h2 style="color:#0f172a;margin-bottom:4px">Welcome to Kalviman!</h2>
        <p>Hi {name or 'there'},</p>
        <p>Thank you for registering on <strong>Kalviman</strong> — India's AI-powered career guidance platform.</p>
        {'<p>Your career assessment results are ready. Log in to view your personalised career report, recommended courses, colleges, and a 5-year roadmap built specifically for you.</p>' if user_type=='student' else '<p>You can now post job openings, search for candidates by skill, and connect with assessed students whose profiles match your requirements.</p>'}
        <p style="color:#64748b;font-size:13px;margin-top:24px">Best regards,<br><strong>Team Kalviman</strong><br>Gcare Global Campus Consultants Pvt. Ltd., Chennai</p>
        </div>"""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Kalviman <{EMAIL_ADDRESS}>"
        msg["To"] = email
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            s.starttls(); s.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
            s.sendmail(EMAIL_ADDRESS, [email], msg.as_string())
        print(f"[Welcome] Sent to {email}")
    except Exception as e:
        print(f"[Welcome] Failed: {e}")
