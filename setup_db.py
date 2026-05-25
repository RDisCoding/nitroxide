# ─────────────────────────────────────────────
#  setup_db.py  —  creates & seeds SQLite DB
# ─────────────────────────────────────────────

import sqlite3

from config import SQLITE_PATH


def _seed(cur, query, rows):
    cur.executemany(query, rows)


def setup():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    cur.executescript(
        """
        DROP TABLE IF EXISTS employee_projects;
        DROP TABLE IF EXISTS employee_skills;
        DROP TABLE IF EXISTS project_dependencies;
        DROP TABLE IF EXISTS skill_prerequisites;
        DROP TABLE IF EXISTS employees;
        DROP TABLE IF EXISTS projects;
        DROP TABLE IF EXISTS teams;
        DROP TABLE IF EXISTS departments;
        DROP TABLE IF EXISTS skills;
        """
    )

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS departments (
            id                   INTEGER PRIMARY KEY,
            name                 TEXT    NOT NULL,
            parent_department_id INTEGER,
            FOREIGN KEY (parent_department_id) REFERENCES departments(id)
        );

        CREATE TABLE IF NOT EXISTS teams (
            id            INTEGER PRIMARY KEY,
            name          TEXT    NOT NULL,
            department_id  INTEGER NOT NULL,
            FOREIGN KEY (department_id) REFERENCES departments(id)
        );

        CREATE TABLE IF NOT EXISTS employees (
            id         INTEGER PRIMARY KEY,
            name       TEXT    NOT NULL,
            role       TEXT    NOT NULL,
            team_id    INTEGER NOT NULL,
            manager_id INTEGER,
            FOREIGN KEY (team_id) REFERENCES teams(id),
            FOREIGN KEY (manager_id) REFERENCES employees(id)
        );

        CREATE TABLE IF NOT EXISTS projects (
            id              INTEGER PRIMARY KEY,
            project_name    TEXT    NOT NULL,
            owner_team_id    INTEGER NOT NULL,
            FOREIGN KEY (owner_team_id) REFERENCES teams(id)
        );

        CREATE TABLE IF NOT EXISTS project_dependencies (
            project_id             INTEGER NOT NULL,
            prerequisite_project_id INTEGER NOT NULL,
            PRIMARY KEY (project_id, prerequisite_project_id),
            FOREIGN KEY (project_id) REFERENCES projects(id),
            FOREIGN KEY (prerequisite_project_id) REFERENCES projects(id)
        );

        CREATE TABLE IF NOT EXISTS skills (
            id          INTEGER PRIMARY KEY,
            skill_name  TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS skill_prerequisites (
            skill_id              INTEGER NOT NULL,
            prerequisite_skill_id  INTEGER NOT NULL,
            PRIMARY KEY (skill_id, prerequisite_skill_id),
            FOREIGN KEY (skill_id) REFERENCES skills(id),
            FOREIGN KEY (prerequisite_skill_id) REFERENCES skills(id)
        );

        CREATE TABLE IF NOT EXISTS employee_skills (
            emp_id   INTEGER NOT NULL,
            skill_id INTEGER NOT NULL,
            PRIMARY KEY (emp_id, skill_id),
            FOREIGN KEY (emp_id) REFERENCES employees(id),
            FOREIGN KEY (skill_id) REFERENCES skills(id)
        );

        CREATE TABLE IF NOT EXISTS employee_projects (
            emp_id     INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            PRIMARY KEY (emp_id, project_id),
            FOREIGN KEY (emp_id) REFERENCES employees(id),
            FOREIGN KEY (project_id) REFERENCES projects(id)
        );

        CREATE TABLE IF NOT EXISTS inferred_relations (
            source_node TEXT    NOT NULL,
            target_node TEXT    NOT NULL,
            relation    TEXT    NOT NULL,
            evidence    TEXT    NOT NULL,
            PRIMARY KEY (source_node, target_node, relation)
        );
        """
    )

    _seed(
        cur,
        "INSERT OR IGNORE INTO departments VALUES (?,?,?)",
        [
            (1, "Engineering", None),
            (2, "Platform", 1),
            (3, "Applications", 1),
            (4, "AI Research", 1),
            (5, "Security", 1),
        ],
    )

    _seed(
        cur,
        "INSERT OR IGNORE INTO teams VALUES (?,?,?)",
        [
            (1, "Core Platform", 2),
            (2, "DevOps", 2),
            (3, "ML Research", 4),
            (4, "Product Apps", 3),
            (5, "Security Ops", 5),
        ],
    )

    _seed(
        cur,
        "INSERT OR IGNORE INTO employees VALUES (?,?,?,?,?)",
        [
            (1, "Nandita Ray", "Director", 1, None),
            (2, "Priya Menon", "Engineering Manager", 1, 1),
            (3, "Rahul Sharma", "Senior Engineer", 1, 2),
            (4, "Ananya Iyer", "Engineer", 4, 2),
            (5, "Vikram Rao", "DevOps Lead", 2, 1),
            (6, "Sara Khan", "DevOps Engineer", 2, 5),
            (7, "Meera Sen", "ML Manager", 3, 1),
            (8, "Arjun Das", "ML Engineer", 3, 7),
            (9, "Imran Ali", "Security Manager", 5, 1),
            (10, "Asha Patel", "Security Analyst", 5, 9),
        ],
    )

    _seed(
        cur,
        "INSERT OR IGNORE INTO projects VALUES (?,?,?)",
        [
            (1, "Internal Graph Platform", 1),
            (2, "Sync Engine", 1),
            (3, "Employee Portal", 4),
            (4, "Security Dashboard", 5),
            (5, "Model Ops Toolkit", 3),
            (6, "Onboarding Automation", 4),
        ],
    )

    _seed(
        cur,
        "INSERT OR IGNORE INTO project_dependencies VALUES (?,?)",
        [
            (2, 1),
            (3, 2),
            (3, 6),
            (4, 1),
            (5, 1),
            (6, 2),
            (6, 3),
        ],
    )

    _seed(
        cur,
        "INSERT OR IGNORE INTO skills VALUES (?,?)",
        [
            (1, "SQL"),
            (2, "Python"),
            (3, "SQLite"),
            (4, "NetworkX"),
            (5, "Security Analysis"),
            (6, "Project Planning"),
            (7, "Data Modeling"),
        ],
    )

    _seed(
        cur,
        "INSERT OR IGNORE INTO skill_prerequisites VALUES (?,?)",
        [
            (3, 1),
            (4, 1),
            (4, 2),
            (5, 1),
            (7, 1),
            (7, 6),
        ],
    )

    _seed(
        cur,
        "INSERT OR IGNORE INTO employee_skills VALUES (?,?)",
        [
            (1, 1), (1, 2), (1, 6),
            (2, 1), (2, 6),
            (3, 1), (3, 2), (3, 4), (3, 7),
            (4, 1), (4, 2), (4, 7),
            (5, 1), (5, 3), (5, 6),
            (6, 2), (6, 3),
            (7, 1), (7, 2), (7, 6),
            (8, 2), (8, 4),
            (9, 1), (9, 5), (9, 7),
            (10, 1), (10, 5),
        ],
    )

    _seed(
        cur,
        "INSERT OR IGNORE INTO employee_projects VALUES (?,?)",
        [
            (1, 1), (1, 2),
            (2, 1), (2, 2),
            (3, 1), (3, 2),
            (4, 3), (4, 6),
            (5, 1), (5, 2),
            (6, 2), (6, 6),
            (7, 5), (7, 6),
            (8, 5),
            (9, 4),
            (10, 4),
        ],
    )

    cur.execute("DELETE FROM inferred_relations")

    conn.commit()
    conn.close()
    print("SQLite database created and seeded ->", SQLITE_PATH)


if __name__ == "__main__":
    setup()
