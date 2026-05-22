# ─────────────────────────────────────────────
#  setup_db.py  —  creates & seeds SQLite DB
# ─────────────────────────────────────────────

import sqlite3
from config import SQLITE_PATH


def setup():
    conn = sqlite3.connect(SQLITE_PATH)
    cur  = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS employees (
            id         INTEGER PRIMARY KEY,
            name       TEXT    NOT NULL,
            department TEXT    NOT NULL,
            role       TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS projects (
            id           INTEGER PRIMARY KEY,
            project_name TEXT    NOT NULL
        );

        -- junction table  (many-to-many)
        CREATE TABLE IF NOT EXISTS employee_projects (
            emp_id     INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            PRIMARY KEY (emp_id, project_id),
            FOREIGN KEY (emp_id)     REFERENCES employees(id),
            FOREIGN KEY (project_id) REFERENCES projects(id)
        );
    """)

    # ── seed employees ──────────────────────────────────────────────────────
    cur.executemany(
        "INSERT OR IGNORE INTO employees VALUES (?,?,?,?)",
        [
            (1, "Rahul",   "AI",       "Engineer"),
            (2, "Ananya",  "Backend",  "Engineer"),
            (3, "Priya",   "AI",       "Manager"),
            (4, "Vikram",  "DevOps",   "Engineer"),
        ],
    )

    # ── seed projects ───────────────────────────────────────────────────────
    cur.executemany(
        "INSERT OR IGNORE INTO projects VALUES (?,?)",
        [
            (1, "Fraud Detection"),
            (2, "Recommendation Engine"),
        ],
    )

    # ── seed assignments ────────────────────────────────────────────────────
    cur.executemany(
        "INSERT OR IGNORE INTO employee_projects VALUES (?,?)",
        [
            (1, 1),   # Rahul   → Fraud Detection
            (1, 2),   # Rahul   → Recommendation Engine
            (2, 2),   # Ananya  → Recommendation Engine
            (3, 1),   # Priya   → Fraud Detection
        ],
    )

    conn.commit()
    conn.close()
    print("SQLite database created and seeded ->", SQLITE_PATH)


if __name__ == "__main__":
    setup()