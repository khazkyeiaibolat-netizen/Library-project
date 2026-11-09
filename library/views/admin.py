"""Administrator area: analytics, accounts, branches, SQL reports, backup, CSV export."""
import csv
import io
import os
import re
import sqlite3
import tempfile
from datetime import date

from flask import (Blueprint, Response, abort, current_app, flash, g, redirect, render_template,
                   request, url_for)

from .. import auth, services
from ..db import execute, get_db, query
from ..i18n import t
from ..services import LOAN_SELECT, today_iso
from ..util import clean, to_int

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.before_request
def _admin_only():
    if g.user is None:
        return redirect(url_for("auth.login", next=request.path))
    if g.user["role"] != "admin":
        abort(403)


# ---------------------------------------------------------------------------------------------
# Analytics dashboard
# ---------------------------------------------------------------------------------------------

def _last_months(n=6):
    today = date.today()
    y, m = today.year, today.month
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


@bp.route("/")
def dashboard():
    stats = query(
        """SELECT (SELECT COUNT(*) FROM book) AS books, (SELECT COUNT(*) FROM reader) AS readers,
                  (SELECT COUNT(*) FROM branch) AS branches, (SELECT COUNT(*) FROM app_user) AS users,
                  (SELECT COUNT(*) FROM loan) AS loans,
                  (SELECT COUNT(*) FROM loan l LEFT JOIN book_return r ON r.loan_id = l.loan_id
                    WHERE r.return_id IS NULL) AS active,
                  (SELECT COUNT(*) FROM loan l LEFT JOIN book_return r ON r.loan_id = l.loan_id
                    WHERE r.return_id IS NULL AND l.due_date < :today) AS overdue,
                  (SELECT COALESCE(SUM(quantity), 0) FROM inventory) AS copies""",
        {"today": today_iso()}, one=True)
    # coursework query 10: books per branch
    per_branch = query(
        """SELECT br.name AS branch_name, COALESCE(SUM(i.quantity), 0) AS total_books
           FROM branch br LEFT JOIN inventory i ON br.branch_id = i.branch_id
           GROUP BY br.branch_id, br.name ORDER BY total_books DESC""")
    months = _last_months(6)
    counts = {r["ym"]: r["n"] for r in query(
        "SELECT substr(loan_date, 1, 7) AS ym, COUNT(*) AS n FROM loan WHERE loan_date >= ? GROUP BY ym",
        (months[0] + "-01",))}
    per_month = [(m, counts.get(m, 0)) for m in months]
    genres = query(
        """SELECT COALESCE(b.genre, '—') AS genre, COUNT(*) AS n FROM loan l
           JOIN book b ON b.book_id = l.book_id GROUP BY b.genre ORDER BY n DESC LIMIT 6""")
    top_books = query(
        """SELECT b.book_id, b.title, b.author, COUNT(*) AS n FROM loan l JOIN book b ON b.book_id = l.book_id
           GROUP BY b.book_id ORDER BY n DESC, b.title LIMIT 5""")
    roles = query("SELECT role, COUNT(*) AS n FROM app_user GROUP BY role")
    return render_template("admin/dashboard.html", stats=stats, per_branch=per_branch, per_month=per_month,
                           genres=genres, top_books=top_books, roles=roles)


# ---------------------------------------------------------------------------------------------
# User accounts
# ---------------------------------------------------------------------------------------------

USERNAME_RE = re.compile(r"^[a-z0-9_.]{3,30}$")


@bp.route("/users")
def users():
    rows = query(
        """SELECT u.user_id, u.username, u.role, u.is_active, u.created_at, u.last_login,
                  r.full_name, b.name AS branch_name
           FROM app_user u LEFT JOIN reader r ON r.reader_id = u.reader_id
           LEFT JOIN branch b ON b.branch_id = u.branch_id
           ORDER BY CASE u.role WHEN 'admin' THEN 0 WHEN 'librarian' THEN 1 WHEN 'branch_staff' THEN 2 ELSE 3 END,
                    u.username""")
    return render_template("admin/users.html", users=rows)


@bp.route("/users/new", methods=["GET", "POST"])
def user_new():
    form = {"username": "", "role": "branch_staff", "branch_id": None, "reader_id": None}
    if request.method == "POST":
        form = {"username": clean(request.form.get("username"), 30).lower(),
                "role": request.form.get("role", ""),
                "branch_id": to_int(request.form.get("branch_id"), None, 1),
                "reader_id": to_int(request.form.get("reader_id"), None, 1)}
        password = request.form.get("password", "")
        error = None
        if not USERNAME_RE.match(form["username"]):
            error = "err.username_format"
        elif form["role"] not in auth.ROLES:
            error = "err.role_invalid"
        elif form["role"] == "branch_staff" and not form["branch_id"]:
            error = "err.branch_required"
        elif form["role"] == "reader" and not form["reader_id"]:
            error = "err.reader_required"
        elif auth.password_problem(password):
            error = auth.password_problem(password)
        elif query("SELECT 1 FROM app_user WHERE username = ?", (form["username"],), one=True):
            error = "err.username_taken"
        elif form["role"] == "reader" and query("SELECT 1 FROM app_user WHERE reader_id = ?",
                                                (form["reader_id"],), one=True):
            error = "err.reader_has_account"
        if error is None:
            try:
                execute(
                    "INSERT INTO app_user(username, password_hash, role, reader_id, branch_id) VALUES (?,?,?,?,?)",
                    (form["username"], auth.hash_password(password), form["role"],
                     form["reader_id"] if form["role"] == "reader" else None,
                     form["branch_id"] if form["role"] == "branch_staff" else None))
            except sqlite3.IntegrityError:
                error = "err.invalid_reference"
            else:
                flash(t("msg.user_created"), "success")
                return redirect(url_for("admin.users"))
        flash(t(error), "error")
    branches = query("SELECT branch_id, name FROM branch ORDER BY name COLLATE KK")
    free_readers = query(
        """SELECT reader_id, full_name FROM reader
           WHERE reader_id NOT IN (SELECT reader_id FROM app_user WHERE reader_id IS NOT NULL)
           ORDER BY full_name COLLATE KK""")
    return render_template("admin/user_form.html", form=form, branches=branches, readers=free_readers,
                           roles=auth.ROLES)


@bp.route("/users/<int:user_id>/toggle", methods=["POST"])
def user_toggle(user_id):
    if user_id == g.user["user_id"]:
        flash(t("err.cannot_disable_self"), "error")
    else:
        execute("UPDATE app_user SET is_active = 1 - is_active WHERE user_id = ?", (user_id,))
        flash(t("msg.saved"), "success")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/password", methods=["POST"])
def user_password(user_id):
    password = request.form.get("password", "")
    if not query("SELECT 1 FROM app_user WHERE user_id = ?", (user_id,), one=True):
        abort(404)
    problem = auth.password_problem(password)
    if problem:
        flash(t(problem), "error")
    else:
        execute("UPDATE app_user SET password_hash = ? WHERE user_id = ?", (auth.hash_password(password), user_id))
        flash(t("msg.password_changed"), "success")
    return redirect(url_for("admin.users"))


# ---------------------------------------------------------------------------------------------
# Branches
# ---------------------------------------------------------------------------------------------

@bp.route("/branches")
def branches():
    rows = query(
        """SELECT br.branch_id, br.name, br.address, br.phone,
                  (SELECT COALESCE(SUM(quantity), 0) FROM inventory i WHERE i.branch_id = br.branch_id) AS copies,
                  (SELECT COUNT(*) FROM app_user u WHERE u.branch_id = br.branch_id) AS staff
           FROM branch br ORDER BY br.branch_id""")
    return render_template("admin/branches.html", branches=rows)


def _branch_form():
    return {"name": clean(request.form.get("name"), 100), "address": clean(request.form.get("address"), 255),
            "phone": clean(request.form.get("phone"), 20)}


def _branch_error(f):
    if not f["name"] or not f["address"]:
        return "err.name_address_required"
    if f["phone"] and not re.match(r"^\+?[0-9 ()\-]{7,20}$", f["phone"]):
        return "err.phone_format"
    return None


@bp.route("/branches/new", methods=["GET", "POST"])
def branch_new():
    form = {"name": "", "address": "", "phone": ""}
    if request.method == "POST":
        form = _branch_form()
        error = _branch_error(form)
        if error:
            flash(t(error), "error")
        else:
            execute("INSERT INTO branch(name, address, phone) VALUES (?,?,?)",
                    (form["name"], form["address"], form["phone"] or None))
            flash(t("msg.branch_added"), "success")
            return redirect(url_for("admin.branches"))
    return render_template("admin/branch_form.html", form=form, branch=None)


@bp.route("/branches/<int:branch_id>/edit", methods=["GET", "POST"])
def branch_edit(branch_id):
    branch = query("SELECT * FROM branch WHERE branch_id = ?", (branch_id,), one=True)
    if branch is None:
        abort(404)
    form = {"name": branch["name"], "address": branch["address"], "phone": branch["phone"] or ""}
    if request.method == "POST":
        form = _branch_form()
        error = _branch_error(form)
        if error:
            flash(t(error), "error")
        else:
            execute("UPDATE branch SET name = ?, address = ?, phone = ? WHERE branch_id = ?",
                    (form["name"], form["address"], form["phone"] or None, branch_id))
            flash(t("msg.saved"), "success")
            return redirect(url_for("admin.branches"))
    return render_template("admin/branch_form.html", form=form, branch=branch)


@bp.route("/branches/<int:branch_id>/delete", methods=["POST"])
def branch_delete(branch_id):
    in_use = (query("SELECT 1 FROM loan WHERE branch_id = ? LIMIT 1", (branch_id,), one=True)
              or query("SELECT 1 FROM inventory WHERE branch_id = ? LIMIT 1", (branch_id,), one=True)
              or query("SELECT 1 FROM app_user WHERE branch_id = ? LIMIT 1", (branch_id,), one=True))
    if in_use:
        flash(t("err.branch_in_use"), "error")   # ON DELETE RESTRICT in the schema would refuse it too
    else:
        execute("DELETE FROM branch WHERE branch_id = ?", (branch_id,))
        flash(t("msg.deleted"), "success")
    return redirect(url_for("admin.branches"))


# ---------------------------------------------------------------------------------------------
# SQL reports: the coursework queries running on live data
# ---------------------------------------------------------------------------------------------

REPORTS = [
    ("q5", "report.q5", "report.q5_desc",
     """SELECT b.title, b.author, br.name AS branch_name, br.address, i.quantity
FROM inventory AS i
JOIN book AS b ON i.book_id = b.book_id
JOIN branch AS br ON i.branch_id = br.branch_id
WHERE i.quantity > 0
ORDER BY b.title, br.name;"""),
    ("q7", "report.q7", "report.q7_desc",
     """SELECT l.loan_id, r.full_name, b.title, br.name AS branch_name, l.loan_date, l.due_date
FROM loan AS l
JOIN reader AS r ON l.reader_id = r.reader_id
JOIN book AS b ON l.book_id = b.book_id
JOIN branch AS br ON l.branch_id = br.branch_id
LEFT JOIN book_return AS ret ON l.loan_id = ret.loan_id
WHERE ret.return_id IS NULL
ORDER BY l.loan_date;"""),
    ("q10", "report.q10", "report.q10_desc",
     """SELECT br.name AS branch_name, SUM(i.quantity) AS total_books
FROM branch AS br
LEFT JOIN inventory AS i ON br.branch_id = i.branch_id
GROUP BY br.branch_id, br.name
ORDER BY br.name;"""),
    ("x1", "report.x1", "report.x1_desc",
     """SELECT r.full_name, COUNT(*) AS loans, SUM(ret.return_id IS NULL) AS not_returned
FROM loan AS l
JOIN reader AS r ON r.reader_id = l.reader_id
LEFT JOIN book_return AS ret ON ret.loan_id = l.loan_id
GROUP BY r.reader_id, r.full_name
ORDER BY loans DESC, r.full_name
LIMIT 10;"""),
    ("x2", "report.x2", "report.x2_desc",
     """SELECT br.name AS branch_name,
       COUNT(*) AS loans,
       SUM(ret.status = 'Кешігіп қайтарылды') AS returned_late
FROM loan AS l
JOIN branch AS br ON br.branch_id = l.branch_id
LEFT JOIN book_return AS ret ON ret.loan_id = l.loan_id
GROUP BY br.branch_id, br.name
ORDER BY loans DESC;"""),
]


@bp.route("/reports")
def reports():
    results = []
    for key, title, desc, sql in REPORTS:
        cur = get_db().execute(sql)           # fixed, trusted SQL text - no user input involved
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        results.append({"key": key, "title": title, "desc": desc, "sql": sql, "cols": cols,
                        "rows": rows[:25], "total": len(rows)})
    return render_template("admin/reports.html", results=results)


@bp.route("/export/loans.csv")
def export_loans():
    rows = query(LOAN_SELECT + " ORDER BY l.loan_id", {"today": today_iso()})
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["loan_id", "reader", "book", "branch", "loan_date", "due_date", "return_date", "status"])

    def safe(v):                         # stop spreadsheet formula injection (=, +, -, @)
        v = "" if v is None else str(v)
        return "'" + v if v[:1] in ("=", "+", "-", "@") else v

    for r in rows:
        w.writerow([r["loan_id"], safe(r["reader_name"]), safe(r["title"]), safe(r["branch_name"]),
                    r["loan_date"], r["due_date"], r["return_date"] or "",
                    r["return_status"] or ("overdue" if r["is_overdue"] else "active")])
    return Response("﻿" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=loans-{today_iso()}.csv"})


@bp.route("/backup", methods=["POST"])
def backup():
    """Consistent copy of the whole database (requirement 14 of the coursework: backups)."""
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        dst = sqlite3.connect(tmp)
        get_db().backup(dst)
        dst.close()
        with open(tmp, "rb") as fh:
            data = fh.read()
    finally:
        os.unlink(tmp)
    return Response(data, mimetype="application/x-sqlite3",
                    headers={"Content-Disposition": f"attachment; filename=library-backup-{today_iso()}.db"})
