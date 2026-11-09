"""Fill an empty database with demo data.

Usage:  python seed.py            (from the project folder; recreates the DB)

Stock is kept consistent: inventory.quantity is the number of copies currently
ON THE SHELF, so every active (unreturned) loan has already been subtracted.
"""
import random
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from . import seed_data as D

LOAN_DAYS = 14


def _phone(rng):
    return "+7 7%02d %03d %02d %02d" % (rng.choice([0, 1, 2, 5, 7, 8]), rng.randint(100, 999),
                                         rng.randint(10, 99), rng.randint(10, 99))


def populate(conn, today=None, seed=2026):
    rng = random.Random(seed)
    today = today or date.today()
    iso = lambda d: d.isoformat()

    conn.execute("BEGIN IMMEDIATE")
    try:
        branch_ids = [conn.execute("INSERT INTO branch(name,address,phone) VALUES (?,?,?)", b).lastrowid
                      for b in D.BRANCHES]
        book_ids = [conn.execute("INSERT INTO book(title,author,genre,publish_year) VALUES (?,?,?,?)", b).lastrowid
                    for b in D.BOOKS]
        reader_phones = [_phone(rng) for _ in D.READERS]
        reader_phones[0], reader_phones[1] = "+7 701 123 45 67", "+7 702 234 56 78"  # as in the coursework
        reader_ids = [conn.execute("INSERT INTO reader(full_name,phone) VALUES (?,?)", (n, p)).lastrowid
                      for n, p in zip(D.READERS, reader_phones)]

        # --- how many copies each branch owns of each book -------------------------------
        total = {}  # (book_id, branch_id) -> copies owned
        for i, b in enumerate(book_ids):
            for j, br in enumerate(branch_ids):
                if j == 0:                                   # central library owns everything
                    total[(b, br)] = rng.randint(2, 5)
                elif rng.random() < 0.65:
                    total[(b, br)] = rng.randint(1, 4)
        rows = list(total)

        # --- loans -----------------------------------------------------------------------
        loans = []   # (reader, book, branch, loan_date, returned_on or None)
        for _ in range(120):                                 # history: all returned
            r = rng.choice(reader_ids)
            b, br = rng.choice(rows)
            ld = today - timedelta(days=rng.randint(24, 240))
            rd = ld + timedelta(days=rng.randint(3, 22))
            loans.append((r, b, br, ld, rd))

        active_count = {}
        per_reader = {}
        taken = set()

        def add_active(days_ago):
            for _ in range(50):
                r = rng.choice(reader_ids)
                b, br = rng.choice(rows)
                if per_reader.get(r, 0) >= 4 or (r, b) in taken:
                    continue
                taken.add((r, b))
                per_reader[r] = per_reader.get(r, 0) + 1
                active_count[(b, br)] = active_count.get((b, br), 0) + 1
                loans.append((r, b, br, today - timedelta(days=days_ago), None))
                return

        for _ in range(11):
            add_active(rng.randint(0, LOAN_DAYS - 1))        # on time
        for _ in range(7):
            add_active(rng.randint(LOAN_DAYS + 2, 45))        # overdue

        # a few copies out of stock after the active loans, to show "unavailable" in the UI
        for key, n in active_count.items():
            total[key] = max(total[key], n)

        for (b, br), copies in total.items():
            conn.execute("INSERT INTO inventory(book_id,branch_id,quantity) VALUES (?,?,?)",
                         (b, br, copies - active_count.get((b, br), 0)))

        for r, b, br, ld, rd in sorted(loans, key=lambda x: x[3]):
            due = ld + timedelta(days=LOAN_DAYS)
            lid = conn.execute("INSERT INTO loan(reader_id,book_id,branch_id,loan_date,due_date) VALUES (?,?,?,?,?)",
                               (r, b, br, iso(ld), iso(due))).lastrowid
            if rd:
                status = "Қайтарылды" if rd <= due else "Кешігіп қайтарылды"
                conn.execute("INSERT INTO book_return(loan_id,return_date,status) VALUES (?,?,?)",
                             (lid, iso(rd), status))

        # --- demo accounts ---------------------------------------------------------------
        for username, role, pw_key, bi, ri in D.DEMO_USERS:
            conn.execute(
                "INSERT INTO app_user(username,password_hash,role,reader_id,branch_id) VALUES (?,?,?,?,?)",
                (username, generate_password_hash(D.DEMO_PASSWORDS[pw_key]), role,
                 reader_ids[ri] if ri is not None else None,
                 branch_ids[bi] if bi is not None else None))
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
