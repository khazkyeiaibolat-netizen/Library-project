"""Business rules of the library. Views call these functions; they never edit stock directly.

Stock model (same as the coursework): inventory.quantity = copies currently on the shelf
of a branch. Issuing a book takes one copy off the shelf, returning it puts one back.
"""
from datetime import date, timedelta

from flask import current_app

from .db import execute, query, transaction


class ServiceError(Exception):
    """A business-rule violation. `key` is an i18n key shown to the user."""

    def __init__(self, key, **params):
        super().__init__(key)
        self.key = key
        self.params = params


def today_iso():
    return date.today().isoformat()


# ---------------------------------------------------------------------------------------------
# Loans
# ---------------------------------------------------------------------------------------------

def active_loans_of(reader_id):
    return query(
        """SELECT COUNT(*) AS n FROM loan l
           LEFT JOIN book_return r ON r.loan_id = l.loan_id
           WHERE l.reader_id = ? AND r.return_id IS NULL""", (reader_id,), one=True)["n"]


def issue_loan(reader_id, book_id, branch_id):
    """Lend one copy. Stock and the loan record change in ONE transaction (coursework query 11)."""
    with transaction() as db:
        if not query("SELECT 1 FROM reader WHERE reader_id = ?", (reader_id,), one=True):
            raise ServiceError("err.reader_not_found")
        if not query("SELECT 1 FROM book WHERE book_id = ?", (book_id,), one=True):
            raise ServiceError("err.book_not_found")
        if not query("SELECT 1 FROM branch WHERE branch_id = ?", (branch_id,), one=True):
            raise ServiceError("err.branch_not_found")

        stock = query("SELECT quantity FROM inventory WHERE book_id = ? AND branch_id = ?",
                      (book_id, branch_id), one=True)
        if stock is None or stock["quantity"] < 1:
            raise ServiceError("err.out_of_stock")

        if active_loans_of(reader_id) >= current_app.config["MAX_ACTIVE_LOANS"]:
            raise ServiceError("err.loan_limit", n=current_app.config["MAX_ACTIVE_LOANS"])

        duplicate = query(
            """SELECT 1 FROM loan l LEFT JOIN book_return r ON r.loan_id = l.loan_id
               WHERE l.reader_id = ? AND l.book_id = ? AND r.return_id IS NULL""",
            (reader_id, book_id), one=True)
        if duplicate:
            raise ServiceError("err.already_has_book")

        db.execute("UPDATE inventory SET quantity = quantity - 1 WHERE book_id = ? AND branch_id = ?",
                   (book_id, branch_id))
        due = date.today() + timedelta(days=current_app.config["LOAN_DAYS"])
        cur = db.execute(
            "INSERT INTO loan(reader_id, book_id, branch_id, loan_date, due_date) VALUES (?,?,?,?,?)",
            (reader_id, book_id, branch_id, today_iso(), due.isoformat()))
        return cur.lastrowid


def return_loan(loan_id, only_branch=None):
    """Register a return and put the copy back on the shelf (one transaction)."""
    with transaction() as db:
        loan = query("SELECT * FROM loan WHERE loan_id = ?", (loan_id,), one=True)
        if loan is None:
            raise ServiceError("err.loan_not_found")
        if only_branch is not None and loan["branch_id"] != only_branch:
            raise ServiceError("err.other_branch")
        if query("SELECT 1 FROM book_return WHERE loan_id = ?", (loan_id,), one=True):
            raise ServiceError("err.already_returned")

        late = today_iso() > loan["due_date"]
        db.execute("INSERT INTO book_return(loan_id, return_date, status) VALUES (?,?,?)",
                   (loan_id, today_iso(), "Кешігіп қайтарылды" if late else "Қайтарылды"))
        db.execute(
            """INSERT INTO inventory(book_id, branch_id, quantity) VALUES (?,?,1)
               ON CONFLICT(book_id, branch_id) DO UPDATE SET quantity = quantity + 1""",
            (loan["book_id"], loan["branch_id"]))
        return late


# ---------------------------------------------------------------------------------------------
# Stock
# ---------------------------------------------------------------------------------------------

def set_stock(book_id, branch_id, quantity):
    if quantity < 0:
        raise ServiceError("err.quantity_negative")
    with transaction() as db:
        db.execute(
            """INSERT INTO inventory(book_id, branch_id, quantity) VALUES (?,?,?)
               ON CONFLICT(book_id, branch_id) DO UPDATE SET quantity = excluded.quantity""",
            (book_id, branch_id, quantity))


def add_stock(book_id, branch_id, amount):
    if amount < 1:
        raise ServiceError("err.quantity_positive")
    with transaction() as db:
        db.execute(
            """INSERT INTO inventory(book_id, branch_id, quantity) VALUES (?,?,?)
               ON CONFLICT(book_id, branch_id) DO UPDATE SET quantity = quantity + excluded.quantity""",
            (book_id, branch_id, amount))


def transfer_stock(book_id, from_branch, to_branch, amount):
    """Move copies between two branches - both updates happen together or not at all."""
    if from_branch == to_branch:
        raise ServiceError("err.same_branch")
    if amount < 1:
        raise ServiceError("err.quantity_positive")
    with transaction() as db:
        src = query("SELECT quantity FROM inventory WHERE book_id = ? AND branch_id = ?",
                    (book_id, from_branch), one=True)
        if src is None or src["quantity"] < amount:
            raise ServiceError("err.not_enough_stock")
        if not query("SELECT 1 FROM branch WHERE branch_id = ?", (to_branch,), one=True):
            raise ServiceError("err.branch_not_found")
        db.execute("UPDATE inventory SET quantity = quantity - ? WHERE book_id = ? AND branch_id = ?",
                   (amount, book_id, from_branch))
        db.execute(
            """INSERT INTO inventory(book_id, branch_id, quantity) VALUES (?,?,?)
               ON CONFLICT(book_id, branch_id) DO UPDATE SET quantity = quantity + excluded.quantity""",
            (book_id, to_branch, amount))


# ---------------------------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------------------------

def register_reader_account(username, password_hash, full_name, phone):
    """Create the reader record and its login together."""
    with transaction() as db:
        if query("SELECT 1 FROM app_user WHERE username = ?", (username,), one=True):
            raise ServiceError("err.username_taken")
        reader_id = db.execute("INSERT INTO reader(full_name, phone) VALUES (?,?)",
                               (full_name, phone or None)).lastrowid
        db.execute(
            "INSERT INTO app_user(username, password_hash, role, reader_id) VALUES (?,?,?,?)",
            (username, password_hash, "reader", reader_id))
        return reader_id


# ---------------------------------------------------------------------------------------------
# Shared queries
# ---------------------------------------------------------------------------------------------

LOAN_SELECT = """
    SELECT l.loan_id, l.loan_date, l.due_date, l.reader_id, l.book_id, l.branch_id,
           r.full_name AS reader_name, b.title, b.author, br.name AS branch_name,
           ret.return_id, ret.return_date, ret.status AS return_status,
           CASE WHEN ret.return_id IS NULL AND l.due_date < :today THEN 1 ELSE 0 END AS is_overdue
    FROM loan l
    JOIN reader r  ON r.reader_id  = l.reader_id
    JOIN book b    ON b.book_id    = l.book_id
    JOIN branch br ON br.branch_id = l.branch_id
    LEFT JOIN book_return ret ON ret.loan_id = l.loan_id
"""
