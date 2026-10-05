# otp.py — Email OTP (uses db.py for storage)
import random, string, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import db
from config import (OTP_MODE, OTP_TTL_MIN, OTP_LENGTH,
    EMAIL_ADDRESS, EMAIL_APP_PASSWORD, EMAIL_FROM_NAME, SMTP_HOST, SMTP_PORT)

def _code(): return "".join(random.choices(string.digits, k=OTP_LENGTH))
def _norm(e): return (e or "").strip().lower()

def request_otp(name, phone, email):
    email_n = _norm(email)
    if not email_n or "@" not in email_n:
        return {"ok": False, "error": "Valid email required."}
    ph = "".join(c for c in (phone or "") if c.isdigit())
    code = _code()
    exp = (datetime.now() + timedelta(minutes=OTP_TTL_MIN)).strftime("%Y-%m-%d %H:%M:%S")
    db.save_otp(name, ph[-10:] if len(ph) >= 10 else ph, email_n, code, exp)
    result = _deliver(name, email_n, code)
    return {"ok": result["sent"], "mode": OTP_MODE, "note": result["note"],
            "demo_code": result.get("demo_code"), "error": None if result["sent"] else result["note"]}

def verify_otp(email, code):
    row = db.get_otp(_norm(email))
    if not row: return {"ok": False, "error": "No code found. Request a new one."}
    if datetime.now() > datetime.strptime(row["expires_at"], "%Y-%m-%d %H:%M:%S"):
        return {"ok": False, "error": "Code expired. Request a new one."}
    if (code or "").strip() != row["code"]:
        return {"ok": False, "error": "Incorrect code."}
    db.mark_otp_verified(row["id"])
    return {"ok": True, "name": row["name"], "phone": row["phone"], "email": _norm(email)}

def is_verified(email): return db.is_verified(email)

def _deliver(name, email, code):
    if OTP_MODE == "email" and EMAIL_ADDRESS and EMAIL_APP_PASSWORD:
        try:
            _send_email(name, email, code)
            return {"sent": True, "note": f"Code sent to {email}."}
        except Exception as e:
            print(f"[OTP] Email failed: {e}")
    print(f"\n{'='*46}\n  OTP: {code} for {name} <{email}> (valid {OTP_TTL_MIN}min)\n{'='*46}\n")
    return {"sent": True, "demo_code": code, "note": "Demo mode."}

def _send_email(name, to, code):
    html = f'<div style="font-family:Arial;max-width:480px;margin:auto;padding:24px"><h2>Kalviman</h2><p>Hi {name},</p><p>Your code:</p><div style="font-size:34px;letter-spacing:8px;font-weight:700;background:#f1f5f9;border-radius:12px;padding:16px;text-align:center">{code}</div><p style="color:#64748b;font-size:13px">Valid for {OTP_TTL_MIN} minutes.</p></div>'
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Your Kalviman verification code"
    msg["From"] = f"{EMAIL_FROM_NAME} <{EMAIL_ADDRESS}>"
    msg["To"] = to
    msg.attach(MIMEText(f"Your Kalviman code: {code}", "plain"))
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
        s.starttls(); s.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
        s.sendmail(EMAIL_ADDRESS, [to], msg.as_string())
