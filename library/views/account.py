"""Pages for the signed-in user: own loans, profile, password."""
import re

from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from werkzeug.security import check_password_hash

from .. import auth
from ..db import execute, query
from ..i18n import t
from ..services import LOAN_SELECT, today_iso
from ..util import clean

bp = Blueprint("account", __name__, url_prefix="/account")


@bp.route("/")
@auth.login_required
def home():
    if g.user["role"] in auth.STAFF_ROLES:
        return redirect(url_for("staff.dashboard"))
    return redirect(url_for("account.my_loans"))


@bp.route("/loans")
@auth.roles_required("reader")
def my_loans():
    rows = query(LOAN_SELECT + " WHERE l.reader_id = :rid ORDER BY (ret.return_id IS NOT NULL), l.due_date, l.loan_id DESC",
                 {"rid": g.user["reader_id"], "today": today_iso()})
    active = [r for r in rows if r["return_id"] is None]
    history = [r for r in rows if r["return_id"] is not None]
    history.sort(key=lambda r: r["return_date"], reverse=True)
    return render_template("account/loans.html", active=active, history=history,
                           overdue=sum(r["is_overdue"] for r in active))


@bp.route("/profile", methods=["GET", "POST"])
@auth.login_required
def profile():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "details" and g.user["reader_id"]:
            name, phone = clean(request.form.get("full_name"), 150), clean(request.form.get("phone"), 20)
            if len(name) < 3:
                flash(t("err.name_required"), "error")
            elif phone and not re.match(r"^\+?[0-9 ()\-]{7,20}$", phone):
                flash(t("err.phone_format"), "error")
            else:
                execute("UPDATE reader SET full_name = ?, phone = ? WHERE reader_id = ?",
                        (name, phone or None, g.user["reader_id"]))
                flash(t("msg.saved"), "success")
                return redirect(url_for("account.profile"))
        elif action == "password":
            current = request.form.get("current_password", "")
            new, confirm = request.form.get("new_password", ""), request.form.get("new_password2", "")
            row = query("SELECT password_hash FROM app_user WHERE user_id = ?", (g.user["user_id"],), one=True)
            if not check_password_hash(row["password_hash"], current):
                flash(t("err.current_password"), "error")
            elif auth.password_problem(new):
                flash(t(auth.password_problem(new)), "error")
            elif new != confirm:
                flash(t("err.password_mismatch"), "error")
            else:
                execute("UPDATE app_user SET password_hash = ? WHERE user_id = ?",
                        (auth.hash_password(new), g.user["user_id"]))
                flash(t("msg.password_changed"), "success")
                return redirect(url_for("account.profile"))
    return render_template("account/profile.html")
