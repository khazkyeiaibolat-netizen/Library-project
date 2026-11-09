"""Authentication, role checks, CSRF protection and login throttling."""
import hmac
import secrets
import time
from functools import wraps
from urllib.parse import urlparse

from flask import abort, current_app, g, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .db import execute, query

ROLES = ("reader", "branch_staff", "librarian", "admin")
STAFF_ROLES = ("branch_staff", "librarian", "admin")

# ----- password helpers ---------------------------------------------------------------------

MIN_PASSWORD = 8


def hash_password(password):
    return generate_password_hash(password)       # salted scrypt/pbkdf2 - never store plain text


def password_problem(password):
    """Return an i18n key describing why a password is too weak, or None."""
    if len(password) < MIN_PASSWORD:
        return "err.password_short"
    if password.isdigit() or password.isalpha():
        return "err.password_weak"
    return None


# ----- current user ---------------------------------------------------------------------------

def load_user():
    g.user = None
    uid = session.get("user_id")
    if uid is None or request.endpoint == "static":
        return
    row = query(
        """SELECT u.user_id, u.username, u.role, u.reader_id, u.branch_id, u.is_active,
                  r.full_name, r.phone, b.name AS branch_name
           FROM app_user u
           LEFT JOIN reader r ON r.reader_id = u.reader_id
           LEFT JOIN branch b ON b.branch_id = u.branch_id
           WHERE u.user_id = ?""", (uid,), one=True)
    if row is None or not row["is_active"]:
        session.clear()
        return
    g.user = row


def login_user(user_row):
    lang = session.get("lang")
    session.clear()                               # new session id on login (prevents fixation)
    session["user_id"] = user_row["user_id"]
    session.permanent = True
    if lang:
        session["lang"] = lang
    execute("UPDATE app_user SET last_login = CURRENT_TIMESTAMP WHERE user_id = ?", (user_row["user_id"],))


def logout_user():
    lang = session.get("lang")
    session.clear()
    if lang:
        session["lang"] = lang


def authenticate(username, password):
    """Return the user row if the credentials are right, else None."""
    row = query("SELECT * FROM app_user WHERE username = ?", (username.strip().lower(),), one=True)
    # Always run a hash check so the response time does not reveal whether the user exists.
    stored = row["password_hash"] if row else _DUMMY_HASH
    ok = check_password_hash(stored, password)
    if row and ok and row["is_active"]:
        return row
    return None


_DUMMY_HASH = generate_password_hash("not-a-real-password")


# ----- decorators -----------------------------------------------------------------------------

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if g.user["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


staff_required = roles_required(*STAFF_ROLES)
admin_required = roles_required("admin")
catalog_manager_required = roles_required("librarian", "admin")


def staff_branch():
    """Branch id a branch-staff user is limited to (None = all branches)."""
    if g.user and g.user["role"] == "branch_staff":
        return g.user["branch_id"]
    return None


def enforce_branch(branch_id):
    own = staff_branch()
    if own is not None and int(branch_id) != own:
        abort(403)


def safe_next(target):
    """Only allow redirects to paths on this site (blocks open-redirect attacks)."""
    if not target:
        return None
    parts = urlparse(target)
    if parts.scheme or parts.netloc or not target.startswith("/") or target.startswith("//"):
        return None
    return target


# ----- CSRF -----------------------------------------------------------------------------------

def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def _check_csrf():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
        expected = session.get("_csrf", "")
        if not expected or not hmac.compare_digest(sent, expected):
            abort(403)


# ----- login throttling (in memory; fine for a single-process demo server) --------------------

_FAILS = {}
MAX_FAILS, LOCK_SECONDS = 5, 300


def _key(username):
    return (request.remote_addr, username.strip().lower())


def is_locked(username):
    entry = _FAILS.get(_key(username))
    if not entry:
        return False
    count, first = entry
    if time.time() - first > LOCK_SECONDS:
        _FAILS.pop(_key(username), None)
        return False
    return count >= MAX_FAILS


def record_failure(username):
    count, first = _FAILS.get(_key(username), (0, time.time()))
    _FAILS[_key(username)] = (count + 1, first)


def clear_failures(username):
    _FAILS.pop(_key(username), None)


def reset_throttle():
    _FAILS.clear()


def init_app(app):
    app.before_request(load_user)
    app.before_request(_check_csrf)
    app.jinja_env.globals["csrf_token"] = csrf_token
