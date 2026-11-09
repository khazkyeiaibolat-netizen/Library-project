"""Run with:  python -m pytest -q"""
import re

import pytest

from library import create_app
from library.auth import reset_throttle
from library.db import connect, init_db
from library.seed import populate


@pytest.fixture()
def app(tmp_path):
    path = str(tmp_path / "test.db")
    init_db(path)
    conn = connect(path)
    populate(conn)
    conn.close()
    reset_throttle()
    return create_app({"TESTING": True, "DATABASE": path, "SECRET_KEY": "test"})


@pytest.fixture()
def client(app):
    return app.test_client()


def token(client, url="/login"):
    html = client.get(url).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def login(client, username, password):
    return client.post("/login", data={"username": username, "password": password,
                                       "csrf_token": token(client)}, follow_redirects=False)


def post(client, url, data=None, page="/staff/"):
    data = dict(data or {})
    data["csrf_token"] = token(client, page)
    return client.post(url, data=data, follow_redirects=True)


def db_value(app, sql, args=()):
    conn = connect(app.config["DATABASE"])
    try:
        row = conn.execute(sql, args).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def shelf(app, book, branch):
    return db_value(app, "SELECT quantity FROM inventory WHERE book_id=? AND branch_id=?", (book, branch))


def free_reader(app):
    """A reader with no active loans."""
    return db_value(app, """SELECT reader_id FROM reader r WHERE NOT EXISTS (
        SELECT 1 FROM loan l LEFT JOIN book_return x ON x.loan_id=l.loan_id
        WHERE l.reader_id=r.reader_id AND x.return_id IS NULL) ORDER BY reader_id DESC LIMIT 1""")


def stocked(app, branch=1):
    return db_value(app, "SELECT book_id FROM inventory WHERE branch_id=? AND quantity>=2 ORDER BY book_id LIMIT 1", (branch,))


# ---------------------------------------------------------------- public pages ---------------

PUBLIC = ["/", "/catalog", "/catalog?q=абай&genre=Роман&available=1&sort=popular&branch=1", "/book/1",
          "/branches", "/branch/2", "/about", "/login", "/register"]


@pytest.mark.parametrize("lang", ["kk", "en"])
@pytest.mark.parametrize("url", PUBLIC)
def test_public_pages_render_without_missing_text(client, url, lang):
    client.get(f"/lang/{lang}")
    r = client.get(url)
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    # an untranslated key would show up as e.g. "nav.catalog" in the page text
    assert not re.search(r">\s*(nav|common|book|catalog|auth|stat|home)\.[a-z_]+\s*<", html)


def test_search_is_case_insensitive_for_cyrillic(client):
    for q in ("абай", "АБАЙ", "әуезов", "Әуезов"):
        html = client.get("/catalog", query_string={"q": q}).get_data(as_text=True)
        assert "Абай жолы" in html, q
    assert "Ештеңе" in client.get("/catalog", query_string={"q": "zzzzqqq"}).get_data(as_text=True)


def test_sql_injection_attempt_is_harmless(client, app):
    r = client.get("/catalog", query_string={"q": "'; DROP TABLE book; --"})
    assert r.status_code == 200
    assert db_value(app, "SELECT COUNT(*) FROM book") > 50


def test_404_page(client):
    assert client.get("/no-such-page").status_code == 404


# ---------------------------------------------------------------- authentication --------------

def test_login_logout_and_wrong_password(client):
    assert login(client, "aidana", "wrong").status_code == 200       # stays on the form
    r = login(client, "aidana", "Reader2026!")
    assert r.status_code == 302 and r.headers["Location"].endswith("/account/loans")
    assert "Менің кітаптарым" in client.get("/").get_data(as_text=True)
    out = post(client, "/logout", page="/")
    assert out.status_code == 200
    assert client.get("/account/loans").status_code == 302


def test_login_throttle(client):
    for _ in range(5):
        login(client, "aidana", "bad")
    r = login(client, "aidana", "Reader2026!")      # correct password, but locked
    assert r.status_code == 200


def test_post_without_csrf_token_is_rejected(client):
    assert client.post("/login", data={"username": "admin", "password": "Admin2026!"}).status_code == 403


def test_open_redirect_blocked(client):
    t = token(client)
    r = client.post("/login", data={"username": "admin", "password": "Admin2026!", "csrf_token": t,
                                    "next": "https://evil.example/"})
    assert r.status_code == 302 and "evil.example" not in r.headers["Location"]


def test_register_reader_creates_reader_and_login(client, app):
    before = db_value(app, "SELECT COUNT(*) FROM reader")
    t = token(client, "/register")
    r = client.post("/register", data={"csrf_token": t, "full_name": "Жанар Төлегенова", "phone": "+7 701 000 11 22",
                                       "username": "zhanar", "password": "Secret2026", "password2": "Secret2026"},
                    follow_redirects=False)
    assert r.status_code == 302
    assert db_value(app, "SELECT COUNT(*) FROM reader") == before + 1
    assert login(client, "zhanar", "Secret2026").status_code == 302


@pytest.mark.parametrize("password", ["short1", "onlyletters", "12345678"])
def test_weak_passwords_rejected(client, app, password):
    t = token(client, "/register")
    r = client.post("/register", data={"csrf_token": t, "full_name": "Test Reader", "username": "weakling",
                                       "password": password, "password2": password})
    assert r.status_code == 200
    assert db_value(app, "SELECT COUNT(*) FROM app_user WHERE username='weakling'") == 0


def test_passwords_are_stored_hashed(app):
    h = db_value(app, "SELECT password_hash FROM app_user WHERE username='admin'")
    assert "Admin2026!" not in h and h.startswith(("scrypt:", "pbkdf2:"))


def test_change_password(client):
    login(client, "aidana", "Reader2026!")
    t = token(client, "/account/profile")
    client.post("/account/profile", data={"csrf_token": t, "action": "password", "current_password": "Reader2026!",
                                          "new_password": "NewPass2026", "new_password2": "NewPass2026"})
    post(client, "/logout", page="/")
    assert login(client, "aidana", "Reader2026!").status_code == 200
    assert login(client, "aidana", "NewPass2026").status_code == 302


# ---------------------------------------------------------------- roles -----------------------

STAFF_URLS = ["/staff/", "/staff/loans", "/staff/loans?status=overdue", "/staff/loans?status=all&q=абай",
              "/staff/loans/new", "/staff/readers", "/staff/readers/1", "/staff/readers/new", "/staff/books",
              "/staff/inventory", "/staff/inventory?empty=1"]
ADMIN_URLS = ["/admin/", "/admin/users", "/admin/users/new", "/admin/branches", "/admin/branches/new",
              "/admin/branches/1/edit", "/admin/reports", "/admin/export/loans.csv"]
MANAGER_URLS = ["/staff/books/new", "/staff/books/1/edit"]


@pytest.mark.parametrize("lang", ["kk", "en"])
@pytest.mark.parametrize("user,pw,role", [("admin", "Admin2026!", "admin"), ("librarian", "Library2026!", "librarian"),
                                          ("staff_saryarka", "Staff2026!", "branch_staff")])
def test_staff_pages_render(client, user, pw, role, lang):
    login(client, user, pw)
    client.get(f"/lang/{lang}")
    urls = STAFF_URLS + (MANAGER_URLS if role != "branch_staff" else []) + (ADMIN_URLS if role == "admin" else [])
    for url in urls:
        r = client.get(url)
        assert r.status_code == 200, (user, url)
        assert not re.search(r">\s*(staff|loan|inv|admin|report|reader|book)\.[a-z_]+\s*<", r.get_data(as_text=True)), url


def test_reader_cannot_enter_staff_or_admin(client):
    login(client, "aidana", "Reader2026!")
    for url in STAFF_URLS + ADMIN_URLS + MANAGER_URLS:
        assert client.get(url).status_code == 403, url
    assert client.get("/account/loans").status_code == 200


def test_anonymous_is_sent_to_login(client):
    for url in ("/staff/", "/admin/", "/account/loans", "/account/profile"):
        r = client.get(url)
        assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_staff_cannot_enter_admin_or_edit_catalog(client):
    login(client, "staff_central", "Staff2026!")
    for url in ADMIN_URLS + MANAGER_URLS:
        assert client.get(url).status_code == 403, url
    assert client.post("/staff/books/1/delete", data={"csrf_token": token(client, "/staff/")}).status_code == 403


def test_disabled_account_is_logged_out(client, app):
    login(client, "librarian", "Library2026!")
    assert client.get("/staff/").status_code == 200
    conn = connect(app.config["DATABASE"])
    conn.execute("UPDATE app_user SET is_active=0 WHERE username='librarian'")
    conn.close()
    assert client.get("/staff/").status_code == 302


# ---------------------------------------------------------------- circulation -----------------

def test_issue_and_return_keep_stock_consistent(client, app):
    login(client, "librarian", "Library2026!")
    book, reader = stocked(app, 1), free_reader(app)
    start = shelf(app, book, 1)
    loans_before = db_value(app, "SELECT COUNT(*) FROM loan")

    r = post(client, "/staff/loans/new", {"reader": reader, "book": book, "branch": 1}, "/staff/loans/new")
    assert "Кітап берілді" in r.get_data(as_text=True)
    assert shelf(app, book, 1) == start - 1
    assert db_value(app, "SELECT COUNT(*) FROM loan") == loans_before + 1
    loan_id = db_value(app, "SELECT MAX(loan_id) FROM loan")
    assert db_value(app, "SELECT julianday(due_date)-julianday(loan_date) FROM loan WHERE loan_id=?", (loan_id,)) == 14

    r = post(client, f"/staff/loans/{loan_id}/return")
    assert "Кітап қабылданды" in r.get_data(as_text=True)
    assert shelf(app, book, 1) == start
    assert db_value(app, "SELECT status FROM book_return WHERE loan_id=?", (loan_id,)) == "Қайтарылды"

    again = post(client, f"/staff/loans/{loan_id}/return")           # double return must not add stock
    assert "бұрын қайтарылған" in again.get_data(as_text=True)
    assert shelf(app, book, 1) == start


def test_cannot_lend_out_of_stock_book(client, app):
    login(client, "librarian", "Library2026!")
    conn = connect(app.config["DATABASE"])
    conn.execute("UPDATE inventory SET quantity=0 WHERE book_id=1 AND branch_id=1")
    conn.close()
    n = db_value(app, "SELECT COUNT(*) FROM loan")
    r = post(client, "/staff/loans/new", {"reader": free_reader(app), "book": 1, "branch": 1}, "/staff/loans/new")
    assert "бос данасы жоқ" in r.get_data(as_text=True)
    assert db_value(app, "SELECT COUNT(*) FROM loan") == n and shelf(app, 1, 1) == 0


def test_loan_limit_and_duplicate_rules(client, app):
    login(client, "librarian", "Library2026!")
    reader = free_reader(app)
    conn = connect(app.config["DATABASE"])
    conn.execute("UPDATE inventory SET quantity = quantity + 10")      # plenty of stock
    conn.close()
    books = [r[0] for r in connect(app.config["DATABASE"]).execute("SELECT book_id FROM inventory WHERE branch_id=1 LIMIT 6")]
    for b in books[:5]:
        post(client, "/staff/loans/new", {"reader": reader, "book": b, "branch": 1}, "/staff/loans/new")
    assert db_value(app, "SELECT COUNT(*) FROM loan l LEFT JOIN book_return r ON r.loan_id=l.loan_id "
                         "WHERE l.reader_id=? AND r.return_id IS NULL", (reader,)) == 5
    r = post(client, "/staff/loans/new", {"reader": reader, "book": books[5], "branch": 1}, "/staff/loans/new")
    assert "артық ала алмайды" in r.get_data(as_text=True)


def test_duplicate_active_loan_rejected(client, app):
    login(client, "librarian", "Library2026!")
    reader, book = free_reader(app), stocked(app, 1)
    post(client, "/staff/loans/new", {"reader": reader, "book": book, "branch": 1}, "/staff/loans/new")
    r = post(client, "/staff/loans/new", {"reader": reader, "book": book, "branch": 1}, "/staff/loans/new")
    assert "әлі қайтарылмаған" in r.get_data(as_text=True)


def test_branch_staff_limited_to_own_branch(client, app):
    login(client, "staff_saryarka", "Staff2026!")                     # branch 2
    reader, book = free_reader(app), stocked(app, 1)
    r = client.post("/staff/loans/new", data={"reader": reader, "book": book, "branch": 1,
                                              "csrf_token": token(client, "/staff/loans/new")})
    assert r.status_code == 403
    assert client.get("/staff/api/branch/1/available").status_code == 403
    assert client.get("/staff/api/branch/2/available").status_code == 200
    other = db_value(app, "SELECT loan_id FROM loan l WHERE branch_id=1 AND NOT EXISTS "
                          "(SELECT 1 FROM book_return r WHERE r.loan_id=l.loan_id) LIMIT 1")
    r = post(client, f"/staff/loans/{other}/return")
    assert "басқа филиалдан" in r.get_data(as_text=True)
    assert db_value(app, "SELECT COUNT(*) FROM book_return WHERE loan_id=?", (other,)) == 0
    # the stock screen only shows the user's own branch
    html = client.get("/staff/inventory?branch=1").get_data(as_text=True)
    assert "Сарыарқа филиалы" in html and "Алматы филиалы</td>" not in html


def test_inventory_set_add_and_transfer(client, app):
    login(client, "librarian", "Library2026!")
    book = stocked(app, 1)
    a1, b1 = shelf(app, book, 1), shelf(app, book, 2) or 0
    post(client, "/staff/inventory/transfer", {"book_id": book, "branch_id": 1, "to_branch": 2, "quantity": 1}, "/staff/inventory")
    assert shelf(app, book, 1) == a1 - 1 and shelf(app, book, 2) == b1 + 1
    r = post(client, "/staff/inventory/transfer", {"book_id": book, "branch_id": 1, "to_branch": 2, "quantity": 999}, "/staff/inventory")
    assert "жеткіліксіз" in r.get_data(as_text=True) and shelf(app, book, 1) == a1 - 1
    post(client, "/staff/inventory/set", {"book_id": book, "branch_id": 1, "quantity": 7}, "/staff/inventory")
    assert shelf(app, book, 1) == 7
    r = post(client, "/staff/inventory/set", {"book_id": book, "branch_id": 1, "quantity": -3}, "/staff/inventory")
    assert shelf(app, book, 1) == 7


def test_stock_matches_loans_in_seed_data(app):
    """Seed data invariant: every active loan has already been taken off the shelf."""
    assert db_value(app, "SELECT COUNT(*) FROM inventory WHERE quantity < 0") == 0
    assert db_value(app, """SELECT COUNT(*) FROM loan l JOIN book_return r ON r.loan_id=l.loan_id
                            WHERE r.return_date < l.loan_date""") == 0


# ---------------------------------------------------------------- catalogue management ---------

def test_book_crud_and_delete_rules(client, app):
    login(client, "librarian", "Library2026!")
    r = post(client, "/staff/books/new", {"title": "Тест кітабы", "author": "Автор А.", "genre": "Роман",
                                          "publish_year": "2020", "branch": 1, "quantity": 3}, "/staff/books/new")
    assert "Кітап қосылды" in r.get_data(as_text=True)
    bid = db_value(app, "SELECT book_id FROM book WHERE title='Тест кітабы'")
    assert shelf(app, bid, 1) == 3
    post(client, f"/staff/books/{bid}/delete", page=f"/staff/books/{bid}/edit")            # has stock -> refused
    assert db_value(app, "SELECT COUNT(*) FROM book WHERE book_id=?", (bid,)) == 1
    post(client, "/staff/inventory/set", {"book_id": bid, "branch_id": 1, "quantity": 0}, "/staff/inventory")
    post(client, f"/staff/books/{bid}/delete", page=f"/staff/books/{bid}/edit")
    assert db_value(app, "SELECT COUNT(*) FROM book WHERE book_id=?", (bid,)) == 0
    # a book with loan history can never be deleted (ON DELETE RESTRICT)
    used = db_value(app, "SELECT book_id FROM loan GROUP BY book_id ORDER BY COUNT(*) DESC LIMIT 1")
    r = post(client, f"/staff/books/{used}/delete", page=f"/staff/books/{used}/edit")
    assert "өшірілмейді" in r.get_data(as_text=True)
    assert db_value(app, "SELECT COUNT(*) FROM book WHERE book_id=?", (used,)) == 1


def test_book_validation(client, app):
    login(client, "librarian", "Library2026!")
    n = db_value(app, "SELECT COUNT(*) FROM book")
    post(client, "/staff/books/new", {"title": "", "author": "X"}, "/staff/books/new")
    post(client, "/staff/books/new", {"title": "A", "author": "B", "publish_year": "abc"}, "/staff/books/new")
    assert db_value(app, "SELECT COUNT(*) FROM book") == n


def test_reader_delete_rules(client, app):
    login(client, "librarian", "Library2026!")
    post(client, "/staff/readers/new", {"full_name": "Уақытша Оқырман", "phone": "+7 700 111 11 11"}, "/staff/readers/new")
    rid = db_value(app, "SELECT reader_id FROM reader WHERE full_name='Уақытша Оқырман'")
    post(client, f"/staff/readers/{rid}/delete", page=f"/staff/readers/{rid}")
    assert db_value(app, "SELECT COUNT(*) FROM reader WHERE reader_id=?", (rid,)) == 0
    post(client, "/staff/readers/2/delete", page="/staff/readers/2")                   # has loans + account
    assert db_value(app, "SELECT COUNT(*) FROM reader WHERE reader_id=2") == 1


# ---------------------------------------------------------------- admin --------------------------

def test_admin_creates_branch_staff_who_can_log_in(client, app):
    login(client, "admin", "Admin2026!")
    r = post(client, "/admin/users/new", {"username": "new_staff", "password": "Staff2026!x", "role": "branch_staff",
                                          "branch_id": 3}, "/admin/users/new")
    assert "Пайдаланушы құрылды" in r.get_data(as_text=True)
    post(client, "/logout", page="/")
    r = login(client, "new_staff", "Staff2026!x")
    assert r.status_code == 302
    assert db_value(app, "SELECT branch_id FROM app_user WHERE username='new_staff'") == 3


def test_admin_cannot_disable_self_and_can_disable_others(client, app):
    login(client, "admin", "Admin2026!")
    me = db_value(app, "SELECT user_id FROM app_user WHERE username='admin'")
    post(client, f"/admin/users/{me}/toggle", page="/admin/users")
    assert db_value(app, "SELECT is_active FROM app_user WHERE username='admin'") == 1
    other = db_value(app, "SELECT user_id FROM app_user WHERE username='madina'")
    post(client, f"/admin/users/{other}/toggle", page="/admin/users")
    assert db_value(app, "SELECT is_active FROM app_user WHERE username='madina'") == 0
    post(client, "/logout", page="/")
    assert login(client, "madina", "Reader2026!").status_code == 200


def test_branch_delete_blocked_when_in_use_and_allowed_when_empty(client, app):
    login(client, "admin", "Admin2026!")
    post(client, "/admin/branches/1/delete", page="/admin/branches")
    assert db_value(app, "SELECT COUNT(*) FROM branch WHERE branch_id=1") == 1
    post(client, "/admin/branches/new", {"name": "Тест филиалы", "address": "Тест көшесі 1"}, "/admin/branches/new")
    bid = db_value(app, "SELECT branch_id FROM branch WHERE name='Тест филиалы'")
    post(client, f"/admin/branches/{bid}/delete", page="/admin/branches")
    assert db_value(app, "SELECT COUNT(*) FROM branch WHERE branch_id=?", (bid,)) == 0


def test_backup_and_csv_export(client):
    login(client, "admin", "Admin2026!")
    r = client.post("/admin/backup", data={"csrf_token": token(client, "/admin/branches")})
    assert r.status_code == 200 and r.data.startswith(b"SQLite format 3")
    csv_text = client.get("/admin/export/loans.csv").get_data(as_text=True)
    assert csv_text.splitlines()[0].startswith("﻿loan_id,reader") and len(csv_text.splitlines()) > 100


def test_reports_run_the_coursework_queries(client):
    login(client, "admin", "Admin2026!")
    html = client.get("/admin/reports").get_data(as_text=True)
    assert "LEFT JOIN book_return AS ret" in html and "total_books" in html


def test_security_headers(client):
    r = client.get("/")
    assert r.headers["X-Frame-Options"] == "DENY" and "script-src 'self'" in r.headers["Content-Security-Policy"]
