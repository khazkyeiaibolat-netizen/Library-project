"""Recreate the database and fill it with demo data:  python seed.py"""
import os
import sys

from library import create_app
from library.db import connect, init_db
from library.seed import populate


def main():
    app = create_app()
    path = app.config["DATABASE"]
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(path + suffix):
            os.remove(path + suffix)
    init_db(path)
    conn = connect(path)
    populate(conn)
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("branch", "book", "reader", "inventory", "loan", "book_return", "app_user")}
    conn.close()
    print("Database created:", path)
    for t, n in counts.items():
        print(f"  {t:12} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
