"""Login, registration (readers only) and logout."""
import re

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for

from .. import auth, services
from ..i18n import t
from ..util import clean

bp = Blueprint("auth", __name__)

USERNAME_RE = re.compile(r"^[a-z0-9_.]{3,30}$")


def _home_for(user):
    return url_for("staff.dashboard") if user["role"] in auth.STAFF_ROLES else url_for("account.my_loans")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(_home_for(g.user))
    next_url = auth.safe_next(request.values.get("next"))
    if request.method == "POST":
        username = clean(request.form.get("username"), 60)
        password = request.form.get("password", "")
        if auth.is_locked(username):
            flash(t("err.too_many_attempts"), "error")
        else:
            user = auth.authenticate(username, password)
            if user is None:
                auth.record_failure(username)
                flash(t("err.bad_login"), "error")
            else:
                auth.clear_failures(username)
                auth.login_user(user)
                flash(t("msg.welcome", name=user["username"]), "success")
                return redirect(next_url or _home_for(user))
    return render_template("login.html", next_url=next_url or "", demo=current_app.config["DEMO_MODE"])


@bp.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(_home_for(g.user))
    form = {"full_name": "", "phone": "", "username": ""}
    if request.method == "POST":
        form = {"full_name": clean(request.form.get("full_name"), 150),
                "phone": clean(request.form.get("phone"), 20),
                "username": clean(request.form.get("username"), 30).lower()}
        password = request.form.get("password", "")
        confirm = request.form.get("password2", "")
        error = None
        if len(form["full_name"]) < 3:
            error = "err.name_required"
        elif not USERNAME_RE.match(form["username"]):
            error = "err.username_format"
        elif form["phone"] and not re.match(r"^\+?[0-9 ()\-]{7,20}$", form["phone"]):
            error = "err.phone_format"
        elif auth.password_problem(password):
            error = auth.password_problem(password)
        elif password != confirm:
            error = "err.password_mismatch"
        if error is None:
            try:
                services.register_reader_account(form["username"], auth.hash_password(password),
                                                 form["full_name"], form["phone"])
            except services.ServiceError as e:
                error = e.key
            else:
                flash(t("msg.registered"), "success")
                return redirect(url_for("auth.login"))
        flash(t(error), "error")
    return render_template("register.html", form=form)


@bp.route("/logout", methods=["POST"])
def logout():
    auth.logout_user()
    flash(t("msg.logged_out"), "success")
    return redirect(url_for("public.index"))
