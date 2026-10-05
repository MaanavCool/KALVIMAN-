import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Database
SQLITE_PATH = os.path.join(BASE_DIR, "kalviman_data.db")
USE_POSTGRES = os.environ.get("USE_POSTGRES", "false").lower() == "true"
DB_HOST     = os.environ.get("DB_HOST", "localhost")
DB_PORT     = int(os.environ.get("DB_PORT", 5432))
DB_NAME     = os.environ.get("DB_NAME", "kalviman")
DB_USER     = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "postgres")

# Flask
FLASK_HOST  = "0.0.0.0"
FLASK_PORT  = int(os.environ.get("PORT", 5000))
FLASK_DEBUG = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
SECRET_KEY  = os.environ.get("SECRET_KEY", "kalviman-dev-key-change-in-production")

# ML & Excel
MODEL_PATH  = os.path.join(BASE_DIR, "ml", "career_model.joblib")
EXCEL_PATH  = os.path.join(BASE_DIR, "Kalviman_Students_Live.xlsx")

# Email OTP
OTP_MODE        = "email"
OTP_TTL_MIN     = 10
OTP_LENGTH      = 6
EMAIL_ADDRESS      = ""
EMAIL_APP_PASSWORD = ""
EMAIL_FROM_NAME    = "Kalviman"
SMTP_HOST          = "smtp.gmail.com"
SMTP_PORT          = 587

# AI (Google Gemini — FREE)
AI_MODE    = os.environ.get("AI_MODE", "rules")
AI_API_KEY = os.environ.get("AI_API_KEY", "")
