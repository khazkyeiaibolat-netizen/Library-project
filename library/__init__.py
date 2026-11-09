"""Library information system - application factory."""
import os
import secrets
from datetime import timedelta
from pathlib import Path

from flask import Flask, g, render_template, request, session

from . import auth, db, i18n, util


def _secret_key(instance_path):
    """Use LIBRARY_SECRET_KEY if set, otherwise create one once and keep it in instance/."""
    env = os.environ.get("LIBRARY_SECRET_KEY")
    if env:
        return env
    key_file = Path(instance_path) / "secret.key"
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32))
    return key_file.read_text().strip()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    app.config.update(
        DATABASE=os.environ.get("LIBRARY_DB", os.path.join(app.instance_path, "library.db")),
        SECRET_KEY=_secret_key(app.instance_path),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("LIBRARY_HTTPS") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        MAX_CONTENT_LENGTH=64 * 1024,
        DEMO_MODE=os.environ.get("LIBRARY_DEMO", "1") == "1",   # shows demo logins on the login page
        LOAN_DAYS=14,
        MAX_ACTIVE_LOANS=5,
        PER_PAGE=12,
    )
    if test_config:
        app.config.update(test_config)

    app.teardown_appcontext(db.close_db)
    auth.init_app(app)
    i18n.init_app(app)
    app.jinja_env.globals["page_url"] = util.page_url

    from .views import account, admin, auth_views, public, staff
    for module in (public, auth_views, account, staff, admin):
        app.register_blueprint(module.bp)

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "script-src 'self'; frame-ancestors 'none'; form-action 'self'")
        if request.endpoint and request.endpoint != "static" and "Cache-Control" not in resp.headers:
            resp.headers["Cache-Control"] = "no-store" if session.get("user_id") else "no-cache"
        return resp

    for code in (403, 404, 405, 413):
        app.register_error_handler(code, _error_page)
    return app


def _error_page(err):
    return render_template("error.html", code=err.code), err.code
