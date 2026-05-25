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
    2.  python main.py watch         # keep graph and SQL in sync live
    3.  Edit graph_state.json        # change nodes or relationships
    4.  python main.py status        # verify SQL updated
    5.  python main.py viz           # generate graph_visualization.html

Extra commands
    python main.py set employee 1 department Research
    python main.py link employee 3 project 2 WORKS_ON
    python main.py unlink employee 3 project 2 WORKS_ON
    python main.py extract
    python main.py viz
    python main.py sync
    python main.py push
"""


# ── status printer ────────────────────────────────────────────────────────────

def show_status():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    cur  = conn.cursor()

    def print_rows(title, query, formatter):
        print(f"\n{title}")
        rows = cur.execute(query).fetchall()
        if not rows:
            print("  (empty)")
            return
        for row in rows:
            print(formatter(row))

    print_rows(
        "Departments",
        "SELECT d.id, d.name, p.name AS parent_name FROM departments d LEFT JOIN departments p ON d.parent_department_id = p.id ORDER BY d.id",
        lambda r: f"  {r['id']:<4} {r['name']:<20} parent={r['parent_name'] or '-'}",
    )
    print_rows(
        "Teams",
        "SELECT t.id, t.name, d.name AS department_name FROM teams t JOIN departments d ON t.department_id = d.id ORDER BY t.id",
        lambda r: f"  {r['id']:<4} {r['name']:<20} department={r['department_name']}",
    )
    print_rows(
        "Employees",
        "SELECT e.id, e.name, e.role, t.name AS team_name, m.name AS manager_name FROM employees e JOIN teams t ON e.team_id = t.id LEFT JOIN employees m ON e.manager_id = m.id ORDER BY e.id",
        lambda r: f"  {r['id']:<4} {r['name']:<20} {r['role']:<22} team={r['team_name']:<16} manager={r['manager_name'] or '-'}",
    )
    print_rows(
        "Projects",
        "SELECT p.id, p.project_name, t.name AS owner_team FROM projects p JOIN teams t ON p.owner_team_id = t.id ORDER BY p.id",
        lambda r: f"  {r['id']:<4} {r['project_name']:<28} owner={r['owner_team']}",
    )
    print_rows(
        "Skills",
        "SELECT id, skill_name FROM skills ORDER BY id",
        lambda r: f"  {r['id']:<4} {r['skill_name']}",
    )
    print_rows(
        "Employee -> Skill links",
        "SELECT e.name AS employee, s.skill_name AS skill FROM employee_skills es JOIN employees e ON es.emp_id = e.id JOIN skills s ON es.skill_id = s.id ORDER BY e.name, s.skill_name",
        lambda r: f"  {r['employee']:<20} -> {r['skill']}",
    )
    print_rows(
        "Employee -> Project links",
        "SELECT e.name AS employee, p.project_name AS project FROM employee_projects ep JOIN employees e ON ep.emp_id = e.id JOIN projects p ON ep.project_id = p.id ORDER BY e.name, p.project_name",
        lambda r: f"  {r['employee']:<20} -> {r['project']}",
    )
    print_rows(
        "Inferred relations",
        "SELECT source_node, target_node, relation, evidence FROM inferred_relations ORDER BY relation, source_node, target_node",
        lambda r: f"  {r['relation']:<18} {r['source_node']:<20} -> {r['target_node']:<20} | {r['evidence']}",
    )

    print()
    conn.close()


def set_graph_node_value(entity, sql_id, field, value):
    from graph_utils import update_node_property

    updated_node = update_node_property(GRAPH_PATH, entity, sql_id, field, value)
    print(f"Updated {updated_node}: {field}={value}")


def link_graph_nodes(source_entity, source_id, target_entity, target_id, relation):
    from graph_utils import add_edge, load_graph, save_graph, node_id

    graph = load_graph(GRAPH_PATH)
    add_edge(graph, node_id(source_entity, source_id), node_id(target_entity, target_id), relation)
    save_graph(graph, GRAPH_PATH)
    print(f"Linked {source_entity}:{source_id} -> {target_entity}:{target_id} [{relation}]")


def _get_cli_flag(flag_name, default=None):
    if flag_name not in sys.argv:
        return default
    index = sys.argv.index(flag_name)
    if index + 1 >= len(sys.argv):
        return default
    value = sys.argv[index + 1]
    if value.startswith("--"):
        return default
    return value


def unlink_graph_nodes(source_entity, source_id, target_entity, target_id, relation=None):
    from graph_utils import load_graph, node_id, remove_edge, save_graph

    graph = load_graph(GRAPH_PATH)
    removed = remove_edge(graph, node_id(source_entity, source_id), node_id(target_entity, target_id), relation)
    if removed:
        save_graph(graph, GRAPH_PATH)
        print(f"Unlinked {source_entity}:{source_id} -> {target_entity}:{target_id}{f' [{relation}]' if relation else ''}")
    else:
        print("No matching edge found to remove.")


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

    elif cmd == "link":
        if len(sys.argv) < 7:
            print("Usage: python main.py link <source_entity> <source_id> <target_entity> <target_id> <relation>")
            return
        link_graph_nodes(sys.argv[2].lower(), int(sys.argv[3]), sys.argv[4].lower(), int(sys.argv[5]), sys.argv[6])

    elif cmd == "unlink":
        if len(sys.argv) < 6:
            print("Usage: python main.py unlink <source_entity> <source_id> <target_entity> <target_id> [relation]")
            return
        relation = sys.argv[6] if len(sys.argv) > 6 else None
        unlink_graph_nodes(sys.argv[2].lower(), int(sys.argv[3]), sys.argv[4].lower(), int(sys.argv[5]), relation)

    elif cmd in ("viz", "visualize", "graph"):
        visualize_graph()

    elif cmd == "watch":
        from live_sync import run_watch

        run_watch()

    elif cmd in ("extract", "extract-relations", "enrich"):
        from relation_extractor import enrich_relations

        text_dir = _get_cli_flag("--text-dir")
        bootstrap = "--bootstrap" in sys.argv
        enrich_relations(text_dir=text_dir, bootstrap=bootstrap)

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