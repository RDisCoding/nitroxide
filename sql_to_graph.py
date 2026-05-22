# ─────────────────────────────────────────────
#  sql_to_graph.py  —  SQL → local NetworkX graph  (one-way push)
#
#  Reads every row from SQLite, creates matching
#  nodes + relationships in a local JSON graph file,
#  then saves a snapshot so the diff engine has a baseline.
# ─────────────────────────────────────────────

import sqlite3

from config import GRAPH_PATH, SQLITE_PATH, SNAPSHOT_PATH
from graph_utils import build_graph, save_graph


# ── helpers ─────────────────────────────────────────────────────────────────

def _read_sqlite():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    cur  = conn.cursor()

    employees = [dict(r) for r in cur.execute("SELECT * FROM employees").fetchall()]
    projects  = [dict(r) for r in cur.execute("SELECT * FROM projects").fetchall()]
    links     = [dict(r) for r in cur.execute("SELECT * FROM employee_projects").fetchall()]

    conn.close()
    return employees, projects, links


def push_to_graph():
    print("\nReading SQLite...")
    employees, projects, links = _read_sqlite()

    print(f"   {len(employees)} employees | {len(projects)} projects | {len(links)} assignments")

    graph = build_graph(employees, projects, links)
    save_graph(graph, GRAPH_PATH)
    save_graph(graph, SNAPSHOT_PATH)
    print(f"Graph saved -> {GRAPH_PATH}")
    print(f"Snapshot saved -> {SNAPSHOT_PATH}")
    print("Local knowledge graph populated from SQL.\n")
    print("   Edit graph_state.json to change node properties or links.")
    print("   Then run: python main.py sync\n")


if __name__ == "__main__":
    push_to_graph()
