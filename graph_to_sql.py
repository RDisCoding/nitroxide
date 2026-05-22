# ─────────────────────────────────────────────
#  graph_to_sql.py  —  local NetworkX graph → SQL  (sync back)
#
#  1. Loads the JSON snapshot saved by sql_to_graph.py
#  2. Reads the CURRENT state of the local graph file
#  3. Diffs old vs new
#  4. Generates & executes SQL UPDATE / INSERT / DELETE
# ─────────────────────────────────────────────

import sqlite3

from config import GRAPH_PATH, SQLITE_PATH, SNAPSHOT_PATH
from graph_utils import graph_to_state, load_graph


# ── editable fields per entity ───────────────────────────────────────────────
EMPLOYEE_FIELDS = ["name", "department", "role"]
PROJECT_FIELDS  = ["project_name"]


# ── load snapshot ────────────────────────────────────────────────────────────

def _load_graph(path):
    try:
        return load_graph(path)
    except FileNotFoundError:
        raise SystemExit(
            f"❌  Graph file not found. Run  python main.py push  first to create {path}."
        )


# ── read current graph state ────────────────────────────────────────────────

def _read_graph(path):
    graph = _load_graph(path)
    return graph_to_state(graph)


# ── diff helpers ──────────────────────────────────────────────────────────────

def _diff_employees(old_map, new_map):
    updates  = []   # (sql_id, {field: new_value})
    inserts  = []   # new employees added in graph
    deletes  = []   # employees removed from graph

    for sql_id, new_node in new_map.items():
        if sql_id not in old_map:
            inserts.append(new_node)
        else:
            old_node = old_map[sql_id]
            changes  = {f: new_node[f] for f in EMPLOYEE_FIELDS if new_node.get(f) != old_node.get(f)}
            if changes:
                updates.append((sql_id, changes))

    for sql_id in old_map:
        if sql_id not in new_map:
            deletes.append(sql_id)

    return updates, inserts, deletes


def _diff_projects(old_map, new_map):
    updates = []
    inserts = []
    deletes = []

    for sql_id, new_node in new_map.items():
        if sql_id not in old_map:
            inserts.append(new_node)
        else:
            old_node = old_map[sql_id]
            changes  = {f: new_node[f] for f in PROJECT_FIELDS if new_node.get(f) != old_node.get(f)}
            if changes:
                updates.append((sql_id, changes))

    for sql_id in old_map:
        if sql_id not in new_map:
            deletes.append(sql_id)

    return updates, inserts, deletes


def _diff_links(old_set, new_set):
    added   = new_set - old_set
    removed = old_set - new_set
    return added, removed


# ── apply SQL changes ─────────────────────────────────────────────────────────

def _apply_sql(emp_updates, emp_inserts, emp_deletes,
               proj_updates, proj_inserts, proj_deletes,
               link_added, link_removed):

    conn = sqlite3.connect(SQLITE_PATH)
    cur  = conn.cursor()
    total = 0

    # ── employees ────────────────────────────────────────────────────────────
    for sql_id, changes in emp_updates:
        set_clause = ", ".join(f"{k} = ?" for k in changes)
        values     = list(changes.values()) + [sql_id]
        query      = f"UPDATE employees SET {set_clause} WHERE id = ?"
        print(f"   UPDATE employees  id={sql_id} -> {changes}")
        cur.execute(query, values)
        total += 1

    for node in emp_inserts:
        print(f"   INSERT employee  {node}")
        cur.execute(
            "INSERT OR IGNORE INTO employees (id, name, department, role) VALUES (?,?,?,?)",
            (node["sql_id"], node["name"], node["department"], node["role"]),
        )
        total += 1

    for sql_id in emp_deletes:
        print(f"   DELETE employee  id={sql_id}")
        cur.execute("DELETE FROM employees WHERE id = ?", (sql_id,))
        cur.execute("DELETE FROM employee_projects WHERE emp_id = ?", (sql_id,))
        total += 1

    # ── projects ─────────────────────────────────────────────────────────────
    for sql_id, changes in proj_updates:
        set_clause = ", ".join(f"{k} = ?" for k in changes)
        values     = list(changes.values()) + [sql_id]
        query      = f"UPDATE projects SET {set_clause} WHERE id = ?"
        print(f"   UPDATE projects  id={sql_id} -> {changes}")
        cur.execute(query, values)
        total += 1

    for node in proj_inserts:
        print(f"   INSERT project  {node}")
        cur.execute(
            "INSERT OR IGNORE INTO projects (id, project_name) VALUES (?,?)",
            (node["sql_id"], node["project_name"]),
        )
        total += 1

    for sql_id in proj_deletes:
        print(f"   DELETE project  id={sql_id}")
        cur.execute("DELETE FROM projects WHERE id = ?", (sql_id,))
        cur.execute("DELETE FROM employee_projects WHERE project_id = ?", (sql_id,))
        total += 1

    # ── relationships ─────────────────────────────────────────────────────────
    for (emp_id, proj_id) in link_added:
        print(f"   INSERT employee_projects  emp={emp_id} -> proj={proj_id}")
        cur.execute(
            "INSERT OR IGNORE INTO employee_projects VALUES (?,?)",
            (emp_id, proj_id),
        )
        total += 1

    for (emp_id, proj_id) in link_removed:
        print(f"   DELETE employee_projects  emp={emp_id} -> proj={proj_id}")
        cur.execute(
            "DELETE FROM employee_projects WHERE emp_id=? AND project_id=?",
            (emp_id, proj_id),
        )
        total += 1

    conn.commit()
    conn.close()
    return total


# ── main ─────────────────────────────────────────────────────────────────────

def sync_to_sql():
    print("\nLoading snapshot (baseline)...")
    old_employees, old_projects, old_links = _read_graph(SNAPSHOT_PATH)

    print("Reading current local graph state...")
    new_employees, new_projects, new_links = _read_graph(GRAPH_PATH)

    print("\nDiffing old vs new...")

    emp_updates,  emp_inserts,  emp_deletes  = _diff_employees(old_employees, new_employees)
    proj_updates, proj_inserts, proj_deletes = _diff_projects(old_projects,   new_projects)
    link_added,   link_removed               = _diff_links(old_links, new_links)

    total_changes = (
        len(emp_updates)  + len(emp_inserts)  + len(emp_deletes)  +
        len(proj_updates) + len(proj_inserts) + len(proj_deletes) +
        len(link_added)   + len(link_removed)
    )

    if total_changes == 0:
        print("No changes detected. SQL is already in sync with the graph.\n")
        return

    print(f"\nApplying {total_changes} change(s) to SQLite...\n")
    applied = _apply_sql(
        emp_updates,  emp_inserts,  emp_deletes,
        proj_updates, proj_inserts, proj_deletes,
        link_added,   link_removed,
    )

    print(f"\n{applied} SQL operation(s) committed to {SQLITE_PATH}\n")
    print("   Run 'python main.py push' again to refresh the graph snapshot.\n")


if __name__ == "__main__":
    sync_to_sql()
