"""Pages anyone can open: home, catalog, book details, branches, about."""
from flask import Blueprint, abort, redirect, render_template, request, session, url_for

from ..auth import safe_next
from ..db import query
from ..i18n import LANGS
from ..util import Page, clean, to_int

bp = Blueprint("public", __name__)

SORTS = {
    "title": "b.title COLLATE KK",
    "author": "b.author COLLATE KK, b.title",
    "year_new": "b.publish_year DESC, b.title",
    "year_old": "b.publish_year ASC, b.title",
    "popular": "borrowed DESC, b.title",
}


@bp.route("/")
def index():
    stats = query(
        """SELECT (SELECT COUNT(*) FROM book)    AS books,
                  (SELECT COUNT(*) FROM branch)  AS branches,
                  (SELECT COUNT(*) FROM reader)  AS readers,
                  (SELECT COALESCE(SUM(quantity), 0) FROM inventory) AS copies,
                  (SELECT COUNT(*) FROM loan l LEFT JOIN book_return r ON r.loan_id = l.loan_id
                    WHERE r.return_id IS NULL) AS active_loans""", one=True)
    popular = query(
        """SELECT b.book_id, b.title, b.author, b.genre, COUNT(l.loan_id) AS borrowed,
                  COALESCE((SELECT SUM(quantity) FROM inventory i WHERE i.book_id = b.book_id), 0) AS available
           FROM book b JOIN loan l ON l.book_id = b.book_id
           GROUP BY b.book_id ORDER BY borrowed DESC, b.title LIMIT 6""")
    newest = query(
        """SELECT b.book_id, b.title, b.author, b.genre, b.publish_year,
                  COALESCE((SELECT SUM(quantity) FROM inventory i WHERE i.book_id = b.book_id), 0) AS available
           FROM book b ORDER BY b.book_id DESC LIMIT 6""")
    branches = query(
        """SELECT br.branch_id, br.name, br.address, COALESCE(SUM(i.quantity), 0) AS copies,
                  COUNT(i.inventory_id) AS titles
           FROM branch br LEFT JOIN inventory i ON i.branch_id = br.branch_id
           GROUP BY br.branch_id ORDER BY br.branch_id""")
    return render_template("index.html", stats=stats, popular=popular, newest=newest, branches=branches)


@bp.route("/catalog")
def catalog():
    q = clean(request.args.get("q"), 100)
    genre = clean(request.args.get("genre"), 50)
    branch = to_int(request.args.get("branch"), None, 1)
    only_available = request.args.get("available") == "1"
    sort = request.args.get("sort") if request.args.get("sort") in SORTS else "title"

    # The fragments below are fixed strings; every user value is passed as a bound parameter.
    join_branch = "AND i.branch_id = :branch" if branch else ""
    where = ["(:q = '' OR instr(FOLD(b.title), :q) > 0 OR instr(FOLD(b.author), :q) > 0)",
             "(:genre = '' OR b.genre = :genre)"]
    having = []
    if branch:
        having.append("COUNT(i.inventory_id) > 0")
    if only_available:
        having.append("available > 0")
    base = f"""
        SELECT b.book_id, b.title, b.author, b.genre, b.publish_year,
               COALESCE(SUM(i.quantity), 0) AS available,
               COALESCE(SUM(CASE WHEN i.quantity > 0 THEN 1 ELSE 0 END), 0) AS branches_with,
               (SELECT COUNT(*) FROM loan l WHERE l.book_id = b.book_id) AS borrowed
        FROM book b LEFT JOIN inventory i ON i.book_id = b.book_id {join_branch}
        WHERE {' AND '.join(where)}
        GROUP BY b.book_id
        {('HAVING ' + ' AND '.join(having)) if having else ''}"""
    params = {"q": q.casefold(), "genre": genre, "branch": branch}

    total = query(f"SELECT COUNT(*) AS n FROM ({base})", params, one=True)["n"]
    page = Page(total, 12)
    books = query(f"{base} ORDER BY {SORTS[sort]} LIMIT :limit OFFSET :offset",
                  {**params, "limit": page.per_page, "offset": page.offset})
    genres = query("SELECT genre, COUNT(*) AS n FROM book WHERE genre IS NOT NULL GROUP BY genre ORDER BY genre")
    branches = query("SELECT branch_id, name FROM branch ORDER BY name")
    return render_template("catalog.html", books=books, page=page, total=total, q=q, genre=genre,
                           branch=branch, only_available=only_available, sort=sort,
                           genres=genres, branches=branches, sorts=list(SORTS))


@bp.route("/book/<int:book_id>")
def book_detail(book_id):
    book = query("SELECT * FROM book WHERE book_id = ?", (book_id,), one=True)
    if book is None:
        abort(404)
    # coursework query 5: where is the book available?
    stock = query(
        """SELECT br.branch_id, br.name, br.address, br.phone, COALESCE(i.quantity, 0) AS quantity,
                  (SELECT COUNT(*) FROM loan l LEFT JOIN book_return r ON r.loan_id = l.loan_id
                    WHERE l.book_id = :b AND l.branch_id = br.branch_id AND r.return_id IS NULL) AS on_loan
           FROM branch br LEFT JOIN inventory i ON i.branch_id = br.branch_id AND i.book_id = :b
           ORDER BY (COALESCE(i.quantity, 0) > 0) DESC, br.name""", {"b": book_id})
    times_borrowed = query("SELECT COUNT(*) AS n FROM loan WHERE book_id = ?", (book_id,), one=True)["n"]
    related = query(
        """SELECT book_id, title, author, genre FROM book
           WHERE book_id != ? AND (author = ? OR genre = ?)
           ORDER BY (author = ?) DESC, title LIMIT 4""",
        (book_id, book["author"], book["genre"], book["author"]))
    return render_template("book_detail.html", book=book, stock=stock, times_borrowed=times_borrowed,
                           related=related, total_available=sum(s["quantity"] for s in stock))


@bp.route("/branches")
def branches():
    rows = query(
        """SELECT br.branch_id, br.name, br.address, br.phone,
                  COALESCE(SUM(i.quantity), 0) AS copies, COUNT(i.inventory_id) AS titles,
                  (SELECT COUNT(*) FROM loan l LEFT JOIN book_return r ON r.loan_id = l.loan_id
                    WHERE l.branch_id = br.branch_id AND r.return_id IS NULL) AS on_loan
           FROM branch br LEFT JOIN inventory i ON i.branch_id = br.branch_id
           GROUP BY br.branch_id ORDER BY br.branch_id""")
    return render_template("branches.html", branches=rows)


@bp.route("/branch/<int:branch_id>")
def branch_detail(branch_id):
    branch = query("SELECT * FROM branch WHERE branch_id = ?", (branch_id,), one=True)
    if branch is None:
        abort(404)
    q = clean(request.args.get("q"), 100)
    where = "AND (instr(FOLD(b.title), :q) > 0 OR instr(FOLD(b.author), :q) > 0)" if q else ""
    total = query(f"SELECT COUNT(*) AS n FROM inventory i JOIN book b ON b.book_id = i.book_id "
                  f"WHERE i.branch_id = :br {where}", {"br": branch_id, "q": q.casefold()}, one=True)["n"]
    page = Page(total, 15)
    books = query(
        f"""SELECT b.book_id, b.title, b.author, b.genre, i.quantity
            FROM inventory i JOIN book b ON b.book_id = i.book_id
            WHERE i.branch_id = :br {where}
            ORDER BY b.title COLLATE KK LIMIT :limit OFFSET :offset""",
        {"br": branch_id, "q": q.casefold(), "limit": page.per_page, "offset": page.offset})
    stats = query(
        """SELECT COALESCE(SUM(quantity), 0) AS copies, COUNT(*) AS titles FROM inventory WHERE branch_id = ?""",
        (branch_id,), one=True)
    return render_template("branch_detail.html", branch=branch, books=books, page=page, q=q, stats=stats)


@bp.route("/about")
def about():
    tables = {}
    for name in ("branch", "book", "inventory", "reader", "loan", "book_return", "app_user"):
        cols = query(f"PRAGMA table_info({name})")           # name comes from the fixed list above
        fks = {r["from"]: f'{r["table"]}.{r["to"]}' for r in query(f"PRAGMA foreign_key_list({name})")}
        count = query(f"SELECT COUNT(*) AS n FROM {name}", one=True)["n"]
        tables[name] = {"columns": cols, "fks": fks, "rows": count}
    return render_template("about.html", tables=tables)


@bp.route("/lang/<code>")
def set_language(code):
    if code in LANGS:
        session["lang"] = code
    target = safe_next(request.args.get("next")) or url_for("public.index")
    return redirect(target)
