# ─────────────────────────────────────────────
#  main.py  —  CLI runner for the local sync system
#
#  Usage:
#    python main.py setup    — create & seed SQLite
#    python main.py push     — SQL → local graph  (+ snapshot)
#    python main.py sync     — local graph → SQL  (diff & apply)
#    python main.py status   — print current SQL state
#    python main.py init     — setup + push  (first-time)
# ─────────────────────────────────────────────

import sys
import sqlite3
from config import GRAPH_PATH, SQLITE_PATH, VISUALIZATION_PATH


HELP = """
SQL <-> Knowledge Graph Sync System (Local MVP)

Typical workflow
    1.  python main.py init          # creates DB + pushes to local graph
    2.  Edit graph_state.json        # change nodes or relationships
        3.  python main.py sync          # reflects changes back to SQL
        4.  python main.py status        # verify SQL updated
    5.  python main.py push          # refresh graph from SQL

Extra commands
    python main.py set employee 1 department Research
    python main.py viz
"""


# ── status printer ────────────────────────────────────────────────────────────

def show_status():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    cur  = conn.cursor()

    print("\nEmployees")
    rows = cur.execute("SELECT * FROM employees ORDER BY id").fetchall()
    if rows:
        header = f"  {'id':<4} {'name':<12} {'department':<14} {'role'}"
        print(header)
        print("  " + "-" * (len(header) - 2))
        for r in rows:
            print(f"  {r['id']:<4} {r['name']:<12} {r['department']:<14} {r['role']}")
    else:
        print("  (empty)")

    print("\nProjects")
    rows = cur.execute("SELECT * FROM projects ORDER BY id").fetchall()
    for r in rows:
        print(f"  {r['id']:<4} {r['project_name']}")

    print("\nEmployee to project assignments")
    rows = cur.execute("""
        SELECT e.name AS employee, p.project_name AS project
        FROM   employee_projects ep
        JOIN   employees e ON ep.emp_id     = e.id
        JOIN   projects  p ON ep.project_id = p.id
        ORDER  BY e.name, p.project_name
    """).fetchall()
    for r in rows:
        print(f"  {r['employee']:<12}  ->  {r['project']}")

    print()
    conn.close()


def set_graph_node_value(entity, sql_id, field, value):
    from graph_utils import update_node_property

    updated_node = update_node_property(GRAPH_PATH, entity, sql_id, field, value)
    print(f"Updated {updated_node}: {field}={value}")


def visualize_graph():
    from graph_utils import render_graph_html

    output_path = render_graph_html(GRAPH_PATH, VISUALIZATION_PATH)
    print(f"Graph visualization written to {output_path}")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(HELP)
        return

    cmd = sys.argv[1].lower()

    if cmd == "setup":
        from setup_db import setup
        setup()

    elif cmd == "push":
        from sql_to_graph import push_to_graph
        push_to_graph()

    elif cmd == "sync":
        from graph_to_sql import sync_to_sql
        sync_to_sql()

    elif cmd == "status":
        show_status()

    elif cmd == "set":
        if len(sys.argv) < 6:
            print("Usage: python main.py set <entity> <sql_id> <field> <value>")
            return
        entity = sys.argv[2].lower()
        sql_id = int(sys.argv[3])
        field = sys.argv[4]
        value = " ".join(sys.argv[5:])
        set_graph_node_value(entity, sql_id, field, value)

    elif cmd in ("viz", "visualize", "graph"):
        visualize_graph()

    elif cmd == "init":
        from setup_db    import setup
        from sql_to_graph import push_to_graph
        setup()
        push_to_graph()
        print("System initialised. Edit graph_state.json to explore the graph.")

    else:
        print(f"Unknown command: '{cmd}'")
        print(HELP)


if __name__ == "__main__":
    main()