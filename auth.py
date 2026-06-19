"""
auth.py
Session-based authentication helpers for the Carbon Footprint Platform.
"""

import sqlite3
import re
from functools import wraps

from flask import session, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash


# ── Validation helpers ───────────────────────────────────────────────────────
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,30}$")
_EMAIL_RE    = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_username(username: str) -> str | None:
    """Return an error message, or None if the username is valid."""
    if not username or not username.strip():
        return "Username is required."
    if not _USERNAME_RE.match(username.strip()):
        return "Username must be 3-30 characters: letters, digits, underscores."
    return None


def validate_password(password: str) -> str | None:
    """Return an error message, or None if the password is valid."""
    if not password:
        return "Password is required."
    if len(password) < 6:
        return "Password must be at least 6 characters."
    return None


def validate_email(email: str) -> str | None:
    """Return an error message, or None if the email is valid."""
    if not email or not email.strip():
        return "Email is required."
    if not _EMAIL_RE.match(email.strip()):
        return "Enter a valid email address."
    return None


# ── DB operations ────────────────────────────────────────────────────────────
def register_user(username: str, email: str, password: str,
                  db_path: str = "carbon.db") -> tuple[bool, str]:
    """Create a new user.

    Returns:
        (True, "") on success.
        (False, error_message) on failure.
    """
    err = validate_username(username) or validate_email(email) or validate_password(password)
    if err:
        return False, err

    username = username.strip()
    email    = email.strip().lower()
    pw_hash  = generate_password_hash(password)

    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                (username, email, pw_hash),
            )
        return True, ""
    except sqlite3.IntegrityError:
        return False, "Username or email already registered."


def authenticate_user(username: str, password: str,
                      db_path: str = "carbon.db") -> tuple[bool, str, dict]:
    """Verify credentials.

    Returns:
        (True,  "",    user_dict) on success.
        (False, error, {})       on failure.
    """
    if not username or not password:
        return False, "Username and password are required.", {}

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT id, username, email, password_hash FROM users WHERE username = ?",
            (username.strip(),),
        )
        row = cur.fetchone()

    if row is None or not check_password_hash(row["password_hash"], password):
        return False, "Invalid username or password.", {}

    return True, "", dict(row)


# ── Decorator ────────────────────────────────────────────────────────────────
def login_required(f):
    """Redirect to /login if the user is not authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access that page.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated
