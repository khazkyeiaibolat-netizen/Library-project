"""Staff area: circulation (issue / return), readers, books, stock.

branch_staff accounts are limited to their own branch; librarian and admin see all branches.
"""
import re
import sqlite3
from datetime import date

from flask import (Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template,
                   request, url_for)

from .. import auth, services
from ..db import execute, query
from ..i18n import t
from ..services import LOAN_SELECT, ServiceError, today_iso
from ..util import Page, clean, to_int

bp = Blueprint("staff", __name__, url_prefix="/staff")


@bp.before_request
def _staff_only():
    if g.user is None:
        return redirect(url_for("auth.login", next=request.path))
    if g.user["role"] not in auth.STAFF_ROLES:
        abort(403)


def _branches():
    """Branches this user may work with."""
    scope = auth.staff_branch()
    if scope:
        return query("SELECT branch_id, name FROM branch WHERE branch_id = ?", (scope,))
    return query("SELECT branch_id, name FROM branch ORDER BY name COLLATE KK")


def _back(default_endpoint, **kw):
    return redirect(auth.safe_next(request.form.get("next")) or url_for(default_endpoint, **kw))


# ---------------------------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------------------------

@bp.route("/")
def dashboard():
    scope = auth.staff_branch()
    p = {"scope": scope, "today": today_iso()}
    stats = query(
        """SELECT
             (SELECT COUNT(*) FROM loan l LEFT JOIN book_return r ON r.loan_id = l.loan_id
               WHERE r.return_id IS NULL AND (:scope IS NULL OR l.branch_id = :scope)) AS active,
             (SELECT COUNT(*) FROM loan l LEFT JOIN book_return r ON r.loan_id = l.loan_id
               WHERE r.return_id IS NULL AND l.due_date < :today
                 AND (:scope IS NULL OR l.branch_id = :scope)) AS overdue,
             (SELECT COUNT(*) FROM loan l WHERE l.loan_date = :today
                 AND (:scope IS NULL OR l.branch_id = :scope)) AS issued_today,
             (SELECT COUNT(*) FROM book_return r JOIN loan l ON l.loan_id = r.loan_id
               WHERE r.return_date = :today AND (:scope IS NULL OR l.branch_id = :scope)) AS returned_today,
             (SELECT COALESCE(SUM(quantity), 0) FROM inventory
               WHERE (:scope IS NULL OR branch_id = :scope)) AS copies,
             (SELECT COUNT(*) FROM inventory
               WHERE quantity = 0 AND (:scope IS NULL OR branch_id = :scope)) AS out_of_stock""", p, one=True)
    overdue = query(
        LOAN_SELECT + """ WHERE ret.return_id IS NULL AND l.due_date < :today
                           AND (:scope IS NULL OR l.branch_id = :scope)
                         ORDER BY l.due_date LIMIT 8""", p)
    recent = query(
        LOAN_SELECT + """ WHERE (:scope IS NULL OR l.branch_id = :scope)
                          ORDER BY l.loan_date DESC, l.loan_id DESC LIMIT 8""", p)
    return render_template("staff/dashboard.html", stats=stats, overdue=overdue, recent=recent)


# ---------------------------------------------------------------------------------------------
# Loans
# ---------------------------------------------------------------------------------------------

STATUS_SQL = {
    "active": "ret.return_id IS NULL",
    "overdue": "ret.return_id IS NULL AND l.due_date < :today",
    "returned": "ret.return_id IS NOT NULL",
    "all": "1 = 1",
}


@bp.route("/loans")
def loans():
    status = request.args.get("status") if request.args.get("status") in STATUS_SQL else "active"
    q = clean(request.args.get("q"), 100)
    scope = auth.staff_branch()
    branch = scope or to_int(request.args.get("branch"), None, 1)
    sql = (LOAN_SELECT + f""" WHERE {STATUS_SQL[status]}
              AND (:branch IS NULL OR l.branch_id = :branch)
              AND (:q = '' OR instr(FOLD(r.full_name), :q) > 0 OR instr(FOLD(b.title), :q) > 0)""")
    p = {"today": today_iso(), "branch": branch, "q": q.casefold()}
    total = query(f"SELECT COUNT(*) AS n FROM ({sql})", p, one=True)["n"]
    page = Page(total, 15)
    order = "l.due_date, l.loan_id" if status in ("active", "overdue") else "l.loan_date DESC, l.loan_id DESC"
    rows = query(f"{sql} ORDER BY {order} LIMIT :limit OFFSET :offset",
                 {**p, "limit": page.per_page, "offset": page.offset})
    return render_template("staff/loans.html", loans=rows, page=page, status=status, q=q,
                           branch=branch, branches=_branches(), total=total)


@bp.route("/loans/new", methods=["GET", "POST"])
def loan_new():
    branches = _branches()
    sel = {"reader": to_int(request.values.get("reader"), None, 1),
           "book": to_int(request.values.get("book"), None, 1),
           "branch": to_int(request.values.get("branch"), None, 1)}
    if request.method == "POST":
        try:
            if None in sel.values():
                raise ServiceError("err.choose_all")
            auth.enforce_branch(sel["branch"])
            services.issue_loan(sel["reader"], sel["book"], sel["branch"])
        except ServiceError as e:
            flash(t(e.key, **e.params), "error")
        else:
            reader = query("SELECT full_name FROM reader WHERE reader_id = ?", (sel["reader"],), one=True)
            flash(t("msg.loan_issued", name=reader["full_name"]), "success")
            return redirect(url_for("staff.loans"))
    if sel["branch"] is None or sel["branch"] not in [b["branch_id"] for b in branches]:
        sel["branch"] = branches[0]["branch_id"] if branches else None
    readers = query("SELECT reader_id, full_name, phone FROM reader ORDER BY full_name COLLATE KK")
    books = _available_books(sel["branch"])
    return render_template("staff/loan_new.html", readers=readers, books=books, branches=branches, sel=sel)


def _available_books(branch_id):
    return query(
        """SELECT b.book_id, b.title, b.author, i.quantity FROM inventory i
           JOIN book b ON b.book_id = i.book_id
           WHERE i.branch_id = ? AND i.quantity > 0 ORDER BY b.title COLLATE KK""", (branch_id,))


@bp.route("/api/branch/<int:branch_id>/available")
def api_available(branch_id):
    auth.enforce_branch(branch_id)
    return jsonify([{"book_id": b["book_id"], "title": b["title"], "author": b["author"],
                     "quantity": b["quantity"]} for b in _available_books(branch_id)])


@bp.route("/loans/<int:loan_id>/return", methods=["POST"])
def loan_return(loan_id):
    try:
        late = services.return_loan(loan_id, only_branch=auth.staff_branch())
    except ServiceError as e:
        flash(t(e.key, **e.params), "error")
    else:
        flash(t("msg.returned_late" if late else "msg.returned"), "success")
    return _back("staff.loans")


# ---------------------------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------------------------

PHONE_RE = re.compile(r"^\+?[0-9 ()\-]{7,20}$")


@bp.route("/readers")
def readers():
    q = clean(request.args.get("q"), 100)
    p = {"q": q.casefold()}
    where = "WHERE instr(FOLD(r.full_name), :q) > 0 OR instr(COALESCE(r.phone, ''), :q) > 0"
    total = query(f"SELECT COUNT(*) AS n FROM reader r {where if q else ''}", p, one=True)["n"]
    page = Page(total, 15)
    rows = query(
        f"""SELECT r.reader_id, r.full_name, r.phone,
                   (SELECT COUNT(*) FROM loan l LEFT JOIN book_return x ON x.loan_id = l.loan_id
                     WHERE l.reader_id = r.reader_id AND x.return_id IS NULL) AS active,
                   (SELECT COUNT(*) FROM loan l WHERE l.reader_id = r.reader_id) AS total_loans,
                   (SELECT username FROM app_user u WHERE u.reader_id = r.reader_id) AS username
            FROM reader r {where if q else ''}
            ORDER BY r.full_name COLLATE KK LIMIT :limit OFFSET :offset""",
        {**p, "limit": page.per_page, "offset": page.offset})
    return render_template("staff/readers.html", readers=rows, page=page, q=q, total=total)


def _reader_form():
    return clean(request.form.get("full_name"), 150), clean(request.form.get("phone"), 20)


@bp.route("/readers/new", methods=["GET", "POST"])
def reader_new():
    form = {"full_name": "", "phone": ""}
    if request.method == "POST":
        name, phone = _reader_form()
        form = {"full_name": name, "phone": phone}
        if len(name) < 3:
            flash(t("err.name_required"), "error")
        elif phone and not PHONE_RE.match(phone):
            flash(t("err.phone_format"), "error")
        else:
            rid = execute("INSERT INTO reader(full_name, phone) VALUES (?,?)", (name, phone or None)).lastrowid
            flash(t("msg.reader_added"), "success")
            return redirect(url_for("staff.reader_detail", reader_id=rid))
    return render_template("staff/reader_form.html", form=form, reader=None)


@bp.route("/readers/<int:reader_id>", methods=["GET", "POST"])
def reader_detail(reader_id):
    reader = query("SELECT * FROM reader WHERE reader_id = ?", (reader_id,), one=True)
    if reader is None:
        abort(404)
    if request.method == "POST":
        name, phone = _reader_form()
        if len(name) < 3:
            flash(t("err.name_required"), "error")
        elif phone and not PHONE_RE.match(phone):
            flash(t("err.phone_format"), "error")
        else:
            execute("UPDATE reader SET full_name = ?, phone = ? WHERE reader_id = ?",
                    (name, phone or None, reader_id))
            flash(t("msg.saved"), "success")
            return redirect(url_for("staff.reader_detail", reader_id=reader_id))
        reader = {"reader_id": reader_id, "full_name": name, "phone": phone}
    loans = query(LOAN_SELECT + " WHERE l.reader_id = :rid ORDER BY (ret.return_id IS NOT NULL), l.loan_date DESC",
                  {"rid": reader_id, "today": today_iso()})
    account = query("SELECT username, is_active FROM app_user WHERE reader_id = ?", (reader_id,), one=True)
    return render_template("staff/reader_detail.html", reader=reader, loans=loans, account=account)


@bp.route("/readers/<int:reader_id>/delete", methods=["POST"])
@auth.catalog_manager_required
def reader_delete(reader_id):
    if query("SELECT 1 FROM loan WHERE reader_id = ? LIMIT 1", (reader_id,), one=True):
        flash(t("err.reader_has_loans"), "error")
    elif query("SELECT 1 FROM app_user WHERE reader_id = ?", (reader_id,), one=True):
        flash(t("err.reader_has_account"), "error")
    else:
        execute("DELETE FROM reader WHERE reader_id = ?", (reader_id,))
        flash(t("msg.deleted"), "success")
        return redirect(url_for("staff.readers"))
    return redirect(url_for("staff.reader_detail", reader_id=reader_id))


# ---------------------------------------------------------------------------------------------
# Books (catalogue records; librarian / admin only for changes)
# ---------------------------------------------------------------------------------------------

@bp.route("/books")
def books():
    q = clean(request.args.get("q"), 100)
    genre = clean(request.args.get("genre"), 50)
    p = {"q": q.casefold(), "genre": genre}
    where = """WHERE (:q = '' OR instr(FOLD(b.title), :q) > 0 OR instr(FOLD(b.author), :q) > 0)
                 AND (:genre = '' OR b.genre = :genre)"""
    total = query(f"SELECT COUNT(*) AS n FROM book b {where}", p, one=True)["n"]
    page = Page(total, 15)
    rows = query(
        f"""SELECT b.book_id, b.title, b.author, b.genre, b.publish_year,
                   COALESCE((SELECT SUM(quantity) FROM inventory i WHERE i.book_id = b.book_id), 0) AS copies
            FROM book b {where} ORDER BY b.title COLLATE KK LIMIT :limit OFFSET :offset""",
        {**p, "limit": page.per_page, "offset": page.offset})
    genres = query("SELECT DISTINCT genre FROM book WHERE genre IS NOT NULL ORDER BY genre COLLATE KK")
    return render_template("staff/books.html", books=rows, page=page, q=q, genre=genre,
                           genres=genres, total=total)


def _book_form():
    year_raw = clean(request.form.get("publish_year"), 6)
    return {"title": clean(request.form.get("title"), 200),
            "author": clean(request.form.get("author"), 150),
            "genre": clean(request.form.get("genre"), 50),
            "publish_year": year_raw}


def _validate_book(f):
    if not f["title"] or not f["author"]:
        return "err.title_author_required"
    if f["publish_year"]:
        y = to_int(f["publish_year"])
        if y is None or not (1000 <= y <= date.today().year + 1):
            return "err.year_invalid"
    return None


@bp.route("/books/new", methods=["GET", "POST"])
@auth.catalog_manager_required
def book_new():
    form = {"title": "", "author": "", "genre": "", "publish_year": ""}
    stock = {"branch": None, "quantity": ""}
    if request.method == "POST":
        form = _book_form()
        stock = {"branch": to_int(request.form.get("branch"), None, 1),
                 "quantity": clean(request.form.get("quantity"), 4)}
        error = _validate_book(form)
        qty = to_int(stock["quantity"], 0, 0, 1000) if stock["quantity"] else 0
        if error is None and stock["quantity"] and qty is None:
            error = "err.quantity_negative"
        if error:
            flash(t(error), "error")
        else:
            bid = execute("INSERT INTO book(title, author, genre, publish_year) VALUES (?,?,?,?)",
                          (form["title"], form["author"], form["genre"] or None,
                           to_int(form["publish_year"]))).lastrowid
            if stock["branch"] and qty:
                services.add_stock(bid, stock["branch"], qty)
            flash(t("msg.book_added"), "success")
            return redirect(url_for("public.book_detail", book_id=bid))
    return render_template("staff/book_form.html", form=form, book=None, stock=stock,
                           genres=_genres(), branches=query("SELECT branch_id, name FROM branch ORDER BY name COLLATE KK"))


def _genres():
    return query("SELECT DISTINCT genre FROM book WHERE genre IS NOT NULL ORDER BY genre COLLATE KK")


@bp.route("/books/<int:book_id>/edit", methods=["GET", "POST"])
@auth.catalog_manager_required
def book_edit(book_id):
    book = query("SELECT * FROM book WHERE book_id = ?", (book_id,), one=True)
    if book is None:
        abort(404)
    form = {"title": book["title"], "author": book["author"], "genre": book["genre"] or "",
            "publish_year": book["publish_year"] or ""}
    if request.method == "POST":
        form = _book_form()
        error = _validate_book(form)
        if error:
            flash(t(error), "error")
        else:
            execute("UPDATE book SET title = ?, author = ?, genre = ?, publish_year = ? WHERE book_id = ?",
                    (form["title"], form["author"], form["genre"] or None, to_int(form["publish_year"]), book_id))
            flash(t("msg.saved"), "success")
            return redirect(url_for("public.book_detail", book_id=book_id))
    return render_template("staff/book_form.html", form=form, book=book, stock=None, genres=_genres(), branches=[])


@bp.route("/books/<int:book_id>/delete", methods=["POST"])
@auth.catalog_manager_required
def book_delete(book_id):
    try:
        # inventory rows of the book are removed first; loans keep the book (ON DELETE RESTRICT)
        if query("SELECT 1 FROM loan WHERE book_id = ? LIMIT 1", (book_id,), one=True):
            raise sqlite3.IntegrityError
        if query("SELECT 1 FROM inventory WHERE book_id = ? AND quantity > 0 LIMIT 1", (book_id,), one=True):
            flash(t("err.book_has_stock"), "error")
            return redirect(url_for("public.book_detail", book_id=book_id))
        execute("DELETE FROM inventory WHERE book_id = ?", (book_id,))
        execute("DELETE FROM book WHERE book_id = ?", (book_id,))
    except sqlite3.IntegrityError:
        flash(t("err.book_in_use"), "error")
        return redirect(url_for("public.book_detail", book_id=book_id))
    flash(t("msg.deleted"), "success")
    return redirect(url_for("staff.books"))


# ---------------------------------------------------------------------------------------------
# Stock
# ---------------------------------------------------------------------------------------------

@bp.route("/inventory")
def inventory():
    scope = auth.staff_branch()
    branch = scope or to_int(request.args.get("branch"), None, 1)
    q = clean(request.args.get("q"), 100)
    only_zero = request.args.get("empty") == "1"
    sql = """FROM inventory i JOIN book b ON b.book_id = i.book_id JOIN branch br ON br.branch_id = i.branch_id
             WHERE (:branch IS NULL OR i.branch_id = :branch)
               AND (:q = '' OR instr(FOLD(b.title), :q) > 0 OR instr(FOLD(b.author), :q) > 0)
               AND (:zero = 0 OR i.quantity = 0)"""
    p = {"branch": branch, "q": q.casefold(), "zero": 1 if only_zero else 0}
    total = query(f"SELECT COUNT(*) AS n {sql}", p, one=True)["n"]
    page = Page(total, 15)
    rows = query(
        f"""SELECT i.inventory_id, i.book_id, i.branch_id, i.quantity, b.title, b.author, br.name AS branch_name,
                   (SELECT COUNT(*) FROM loan l LEFT JOIN book_return r ON r.loan_id = l.loan_id
                     WHERE l.book_id = i.book_id AND l.branch_id = i.branch_id AND r.return_id IS NULL) AS on_loan
            {sql} ORDER BY b.title COLLATE KK, br.name LIMIT :limit OFFSET :offset""",
        {**p, "limit": page.per_page, "offset": page.offset})
    all_books = query("SELECT book_id, title FROM book ORDER BY title COLLATE KK")
    all_branches = query("SELECT branch_id, name FROM branch ORDER BY name COLLATE KK")
    return render_template("staff/inventory.html", rows=rows, page=page, q=q, branch=branch,
                           only_zero=only_zero, branches=_branches(), all_branches=all_branches,
                           all_books=all_books, total=total)


def _stock_args():
    return (to_int(request.form.get("book_id"), None, 1), to_int(request.form.get("branch_id"), None, 1),
            to_int(request.form.get("quantity"), None, 0, 100000))


@bp.route("/inventory/set", methods=["POST"])
def inventory_set():
    book_id, branch_id, qty = _stock_args()
    try:
        if None in (book_id, branch_id, qty):
            raise ServiceError("err.choose_all")
        auth.enforce_branch(branch_id)
        if not query("SELECT 1 FROM book WHERE book_id = ?", (book_id,), one=True):
            raise ServiceError("err.book_not_found")
        services.set_stock(book_id, branch_id, qty)
    except ServiceError as e:
        flash(t(e.key, **e.params), "error")
    else:
        flash(t("msg.stock_updated"), "success")
    return _back("staff.inventory")


@bp.route("/inventory/add", methods=["POST"])
def inventory_add():
    book_id, branch_id, qty = _stock_args()
    try:
        if None in (book_id, branch_id, qty):
            raise ServiceError("err.choose_all")
        auth.enforce_branch(branch_id)
        if not query("SELECT 1 FROM book WHERE book_id = ?", (book_id,), one=True):
            raise ServiceError("err.book_not_found")
        services.add_stock(book_id, branch_id, qty)
    except ServiceError as e:
        flash(t(e.key, **e.params), "error")
    else:
        flash(t("msg.stock_updated"), "success")
    return _back("staff.inventory")


@bp.route("/inventory/transfer", methods=["POST"])
def inventory_transfer():
    book_id = to_int(request.form.get("book_id"), None, 1)
    src = to_int(request.form.get("branch_id"), None, 1)
    dst = to_int(request.form.get("to_branch"), None, 1)
    qty = to_int(request.form.get("quantity"), None, 1, 100000)
    try:
        if None in (book_id, src, dst, qty):
            raise ServiceError("err.choose_all")
        auth.enforce_branch(src)
        services.transfer_stock(book_id, src, dst, qty)
    except ServiceError as e:
        flash(t(e.key, **e.params), "error")
    else:
        flash(t("msg.transferred"), "success")
    return _back("staff.inventory")
