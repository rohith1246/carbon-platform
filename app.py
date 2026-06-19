"""
app.py
Carbon Footprint Awareness Platform – Flask application entry point.
"""

import os
import sqlite3
import logging


from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify,
)
from werkzeug.exceptions import BadRequest

from auth import (
    register_user, authenticate_user, login_required,
    validate_username, validate_password, validate_email,
)
from carbon_engine import (
    calculate_co2, get_daily_total, get_weekly_total,
    get_category_breakdown, get_daily_trend, VALID_ACTIVITY_TYPES,
)
from ai_engine import get_ai_insights

# ── Bootstrap ────────────────────────────────────────────────────────────────
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

# Security configurations for session cookies
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
)

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "font-src 'self' https://fonts.gstatic.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "script-src 'self' 'unsafe-inline';"
    )
    return response

DB_PATH = os.environ.get("DB_PATH", "carbon.db")


# ── Database setup ───────────────────────────────────────────────────────────
def init_db() -> None:
    """Create tables if they do not exist."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(
            """
            PRAGMA journal_mode = WAL;

            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    NOT NULL UNIQUE,
                email         TEXT    NOT NULL UNIQUE,
                password_hash TEXT    NOT NULL,
                created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS activities (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                activity_type TEXT    NOT NULL,
                quantity      REAL    NOT NULL,
                co2_kg        REAL    NOT NULL,
                timestamp     TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_activities_user_ts
                ON activities(user_id, timestamp);

            CREATE INDEX IF NOT EXISTS idx_activities_covering
                ON activities(user_id, timestamp, activity_type, co2_kg);
            """
        )
    logger.info("Database initialised at %s", DB_PATH)


init_db()


# ── Helper ───────────────────────────────────────────────────────────────────
def _get_recent_activities(user_id: int, limit: int = 50) -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT id, activity_type, quantity, co2_kg, timestamp
            FROM   activities
            WHERE  user_id = ?
            ORDER  BY timestamp DESC
            LIMIT  ?
            """,
            (user_id, limit),
        )
        return [dict(row) for row in cur.fetchall()]


def _get_all_activities_7days(user_id: int) -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT activity_type, quantity, co2_kg, timestamp
            FROM   activities
            WHERE  user_id   = ?
              AND  timestamp >= DATE('now', '-6 days')
            ORDER  BY timestamp DESC
            """,
            (user_id,),
        )
        return [dict(row) for row in cur.fetchall()]


# ── Auth routes ──────────────────────────────────────────────────────────────
@app.route("/favicon.ico")
def favicon():
    return "", 204

@app.route("/")
def index():
    """Render the landing page, or redirect to dashboard if already authenticated."""
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Handle new user registration with validation checks."""
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        ok, err = register_user(username, email, password, DB_PATH)
        if ok:
            flash("Account created! Please log in.", "success")
            return redirect(url_for("login"))
        flash(err, "error")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Verify credentials and initiate session-based authentication."""
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        ok, err, user = authenticate_user(username, password, DB_PATH)
        if ok:
            session.permanent = True
            session["user_id"]  = user["id"]
            session["username"] = user["username"]
            flash(f"Welcome back, {user['username']}!", "success")
            return redirect(url_for("dashboard"))
        flash(err, "error")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    """Clear session data and log out the user."""
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


# ── Dashboard ────────────────────────────────────────────────────────────────
@app.route("/dashboard")
@login_required
def dashboard():
    """Render the user dashboard with carbon score, breakdown, and AI insights."""
    user_id  = session["user_id"]
    username = session["username"]

    activities       = _get_recent_activities(user_id, limit=20)
    daily_total      = get_daily_total(user_id, DB_PATH)
    weekly_total     = get_weekly_total(user_id, DB_PATH)
    category_breakdown = get_category_breakdown(user_id, DB_PATH)

    # AI insights - session caching to optimize performance and prevent API call overhead
    insights = session.get("ai_insights")
    if not insights:
        all_acts = _get_all_activities_7days(user_id)
        insights = get_ai_insights(all_acts, daily_total, category_breakdown)
        session["ai_insights"] = insights

    # Eco-score band
    score = insights.get("eco_score", 50)
    if score >= 70:
        score_band = "good"
    elif score >= 40:
        score_band = "average"
    else:
        score_band = "poor"

    return render_template(
        "dashboard.html",
        username=username,
        activities=activities,
        daily_total=daily_total,
        weekly_total=weekly_total,
        category_breakdown=category_breakdown,
        insights=insights,
        score_band=score_band,
        valid_types=sorted(VALID_ACTIVITY_TYPES),
    )


# ── Log activity ─────────────────────────────────────────────────────────────
@app.route("/log", methods=["POST"])
@login_required
def log_activity():
    """Log a new activity, save it to the SQLite database, and invalidate the AI cache."""
    user_id       = session["user_id"]
    activity_type = request.form.get("activity_type", "").strip().lower()
    raw_qty       = request.form.get("quantity", "").strip()

    # Validate type
    if activity_type not in VALID_ACTIVITY_TYPES:
        flash(f"Invalid activity type: '{activity_type}'.", "error")
        return redirect(url_for("dashboard"))

    # Validate quantity
    try:
        quantity = float(raw_qty)
        if quantity <= 0:
            raise ValueError
    except (ValueError, TypeError):
        flash("Quantity must be a positive number.", "error")
        return redirect(url_for("dashboard"))

    co2 = calculate_co2(activity_type, quantity)

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO activities (user_id, activity_type, quantity, co2_kg, timestamp)
            VALUES (?, ?, ?, ?, datetime('now'))
            """,
            (user_id, activity_type, quantity, co2),
        )

    # Invalidate AI insights cache since new activity alters the footprint profile
    session.pop("ai_insights", None)

    flash(
        f"Logged {quantity} unit(s) of '{activity_type}' → {co2:.2f} kg CO₂.",
        "success",
    )
    return redirect(url_for("dashboard"))


# ── Analytics ────────────────────────────────────────────────────────────────
@app.route("/analytics")
@login_required
def analytics():
    """Render the carbon analytics page showing weekly metrics and daily trends."""
    user_id  = session["user_id"]
    username = session["username"]

    weekly_total       = get_weekly_total(user_id, DB_PATH)
    category_breakdown = get_category_breakdown(user_id, DB_PATH)
    daily_trend        = get_daily_trend(user_id, DB_PATH)

    # Category percentages
    total_breakdown = sum(category_breakdown.values()) or 1
    category_pct = {
        cat: round(val / total_breakdown * 100, 1)
        for cat, val in category_breakdown.items()
    }

    return render_template(
        "analytics.html",
        username=username,
        weekly_total=weekly_total,
        category_breakdown=category_breakdown,
        category_pct=category_pct,
        daily_trend=daily_trend,
    )


# ── API endpoints (used for JSON responses / testing) ────────────────────────
@app.route("/api/status")
def api_status():
    """Health-check endpoint."""
    return jsonify({"status": "ok", "service": "carbon-platform"})


@app.route("/api/co2", methods=["POST"])
@login_required
def api_calculate():
    """Calculate CO₂ without persisting – useful for frontend previews."""
    data          = request.get_json(force=True, silent=True) or {}
    activity_type = str(data.get("activity_type", "")).strip().lower()
    raw_qty       = data.get("quantity")

    if activity_type not in VALID_ACTIVITY_TYPES:
        return jsonify({"error": f"Unknown activity type '{activity_type}'."}), 400

    try:
        quantity = float(raw_qty)
        if quantity <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "Quantity must be a positive number."}), 400

    co2 = calculate_co2(activity_type, quantity)
    return jsonify({"activity_type": activity_type, "quantity": quantity, "co2_kg": co2})


# ── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
