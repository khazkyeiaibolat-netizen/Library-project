"""SQLite connection helpers.

All SQL in the project uses parameter placeholders (?) - never string
formatting - so user input cannot change the meaning of a query (SQL injection).
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from flask import current_app, g

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "database" / "schema.sql"


def _fold(value):
    """Case-insensitive text for searching. SQLite's own LOWER()/LIKE only
    understand ASCII, so Kazakh/Cyrillic search needs this Python helper."""
    return value.casefold() if isinstance(value, str) else value


KK_ALPHABET = "аәбвгғдеёжзийкқлмнңоөпрстуұүфхһцчшщъыіьэюя"


def _kk_key(text):
    """Sort key that follows the Kazakh alphabet (Ә after А, Қ after К, ...)."""
    key = []
    for ch in (text or "").casefold():
        i = KK_ALPHABET.find(ch)
        if i >= 0:
            key.append((1, i))
        elif ch.isalpha():
            key.append((2, ord(ch)))          # Latin etc. after Cyrillic
        else:
            key.append((0, ord(ch)))          # digits and punctuation first
    return key


def _kk_collation(a, b):
    ka, kb = _kk_key(a), _kk_key(b)
    return (ka > kb) - (ka < kb)


def connect(path):
    conn = sqlite3.connect(path, isolation_level=None)  # we manage transactions
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.create_function("FOLD", 1, _fold, deterministic=True)
    conn.create_collation("KK", _kk_collation)
    return conn


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@contextmanager
def transaction(db=None):
    """BEGIN IMMEDIATE ... COMMIT, or ROLLBACK if anything raises.

    This mirrors the START TRANSACTION / COMMIT blocks of query 11 in the
    coursework: stock and loan records either change together or not at all.
    """
    db = db or get_db()
    db.execute("BEGIN IMMEDIATE")
    try:
        yield db
    except BaseException:
        db.execute("ROLLBACK")
        raise
    else:
        db.execute("COMMIT")


def init_db(path):
    conn = connect(path)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.close()


def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=()):
    return get_db().execute(sql, args)
