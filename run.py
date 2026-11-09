"""Start the website:  python run.py   ->  http://127.0.0.1:5000

On the very first start the database is created and filled with demo data.
"""
import os

from library import create_app
from library.db import connect, init_db
from library.seed import populate

app = create_app()

if not os.path.exists(app.config["DATABASE"]):
    init_db(app.config["DATABASE"])
    conn = connect(app.config["DATABASE"])
    populate(conn)
    conn.close()
    print("Created a new demo database.")

if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 5000)),
            debug=os.environ.get("FLASK_DEBUG") == "1")
