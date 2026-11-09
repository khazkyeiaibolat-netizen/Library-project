-- Library database (SQLite dialect)
-- The six tables below follow the coursework design 1:1 (branch, book, reader,
-- inventory, loan, book_return). `app_user` is the only addition: it stores
-- website logins and links an account to a reader and/or a branch.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS branch (
    branch_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL,
    address   TEXT NOT NULL,
    phone     TEXT
);

CREATE TABLE IF NOT EXISTS book (
    book_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    author       TEXT NOT NULL,
    genre        TEXT,
    publish_year INTEGER
);
CREATE INDEX IF NOT EXISTS idx_book_title  ON book(title);
CREATE INDEX IF NOT EXISTS idx_book_author ON book(author);

CREATE TABLE IF NOT EXISTS reader (
    reader_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    phone     TEXT
);
CREATE INDEX IF NOT EXISTS idx_reader_name ON reader(full_name);

CREATE TABLE IF NOT EXISTS inventory (
    inventory_id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id      INTEGER NOT NULL
                 REFERENCES book(book_id)     ON DELETE RESTRICT ON UPDATE CASCADE,
    branch_id    INTEGER NOT NULL
                 REFERENCES branch(branch_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    quantity     INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    CONSTRAINT uq_book_branch UNIQUE (book_id, branch_id)
);

CREATE TABLE IF NOT EXISTS loan (
    loan_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    reader_id INTEGER NOT NULL
              REFERENCES reader(reader_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    book_id   INTEGER NOT NULL
              REFERENCES book(book_id)     ON DELETE RESTRICT ON UPDATE CASCADE,
    branch_id INTEGER NOT NULL
              REFERENCES branch(branch_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    loan_date TEXT NOT NULL,   -- ISO date YYYY-MM-DD
    due_date  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_loan_reader ON loan(reader_id);
CREATE INDEX IF NOT EXISTS idx_loan_branch ON loan(branch_id);

CREATE TABLE IF NOT EXISTS book_return (
    return_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    loan_id     INTEGER NOT NULL UNIQUE
                REFERENCES loan(loan_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    return_date TEXT NOT NULL,
    status      TEXT NOT NULL
);

-- Website accounts (not part of the coursework ER diagram).
CREATE TABLE IF NOT EXISTS app_user (
    user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL
                  CHECK (role IN ('reader', 'branch_staff', 'librarian', 'admin')),
    reader_id     INTEGER UNIQUE
                  REFERENCES reader(reader_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    branch_id     INTEGER
                  REFERENCES branch(branch_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login    TEXT
);
