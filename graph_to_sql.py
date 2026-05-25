# ─────────────────────────────────────────────
#  graph_to_sql.py  —  local NetworkX graph → SQL
#
#  Applies the current graph state to SQLite so the
#  database mirrors the knowledge graph in real time.
# ─────────────────────────────────────────────

import sqlite3

from config import GRAPH_PATH, SNAPSHOT_PATH, SQLITE_PATH
from graph_utils import load_graph, log_graph_delta, save_graph

INFERRED_RELATIONS = {"COLLABORATES_WITH", "TEAMMATE_OF", "SHARES_SKILL", "SHARES_PROJECT"}


def _load_graph(path):
    try:
        return load_graph(path)
    except FileNotFoundError:
        raise SystemExit(
            f"Graph file not found. Run python main.py push first to create {path}."
        )


def _node_maps(graph):
    nodes = {
        "department": {},
        "team": {},
        "employee": {},
        "project": {},
        "skill": {},
    }
    for node_id, data in graph.nodes(data=True):
        entity = data.get("entity")
        sql_id = data.get("sql_id")
        if entity in nodes:
            nodes[entity][sql_id] = dict(data)
    return nodes


def _relation_pairs(graph, relation, source_entity, target_entity):
    pairs = set()
    for source, target, data in graph.edges(data=True):
        if data.get("relation") != relation:
            continue
        source_data = graph.nodes[source]
        target_data = graph.nodes[target]
        if source_data.get("entity") != source_entity or target_data.get("entity") != target_entity:
            continue
        pairs.add((source_data["sql_id"], target_data["sql_id"]))
    return pairs


def _single_parent_map(graph, relation, parent_entity, child_entity):
    mapping = {}
    for source, target, data in graph.edges(data=True):
        if data.get("relation") != relation:
            continue
        source_data = graph.nodes[source]
        target_data = graph.nodes[target]
        if source_data.get("entity") != parent_entity or target_data.get("entity") != child_entity:
            continue
        mapping[target_data["sql_id"]] = source_data["sql_id"]
    return mapping


def _direct_map(graph, relation, source_entity, target_entity):
    mapping = {}
    for source, target, data in graph.edges(data=True):
        if data.get("relation") != relation:
            continue
        source_data = graph.nodes[source]
        target_data = graph.nodes[target]
        if source_data.get("entity") != source_entity or target_data.get("entity") != target_entity:
            continue
        mapping[source_data["sql_id"]] = target_data["sql_id"]
    return mapping


def _reset_tables(cur):
    cur.executescript(
        """
        DELETE FROM employee_projects;
        DELETE FROM employee_skills;
        DELETE FROM project_dependencies;
        DELETE FROM skill_prerequisites;
        DELETE FROM employees;
        DELETE FROM projects;
        DELETE FROM teams;
        DELETE FROM departments;
        DELETE FROM skills;
        """
    )


def _apply_nodes(cur, nodes, department_parent, team_department, employee_team, employee_manager, project_owner):
    for department in nodes["department"].values():
        cur.execute(
            "INSERT INTO departments (id, name, parent_department_id) VALUES (?,?,?)",
            (department["sql_id"], department["name"], department_parent.get(department["sql_id"])),
        )

    for team in nodes["team"].values():
        cur.execute(
            "INSERT INTO teams (id, name, department_id) VALUES (?,?,?)",
            (team["sql_id"], team["name"], team_department.get(team["sql_id"])),
        )

    for employee in nodes["employee"].values():
        cur.execute(
            "INSERT INTO employees (id, name, role, team_id, manager_id) VALUES (?,?,?,?,?)",
            (
                employee["sql_id"],
                employee["name"],
                employee["role"],
                employee_team.get(employee["sql_id"]),
                employee_manager.get(employee["sql_id"]),
            ),
        )

    for project in nodes["project"].values():
        cur.execute(
            "INSERT INTO projects (id, project_name, owner_team_id) VALUES (?,?,?)",
            (project["sql_id"], project["project_name"], project_owner.get(project["sql_id"])),
        )

    for skill in nodes["skill"].values():
        cur.execute(
            "INSERT INTO skills (id, skill_name) VALUES (?,?)",
            (skill["sql_id"], skill["skill_name"]),
        )


def _apply_relation_columns(cur, graph):
    department_parent = _single_parent_map(graph, "SUBDEPARTMENT_OF", "department", "department")
    team_department = _single_parent_map(graph, "LOCATED_IN", "team", "department")
    employee_team = _single_parent_map(graph, "MEMBER_OF", "employee", "team")
    employee_manager = _single_parent_map(graph, "MANAGES", "employee", "employee")
    project_owner = _single_parent_map(graph, "OWNS_PROJECT", "team", "project")

    for department_id, parent_id in department_parent.items():
        cur.execute(
            "UPDATE departments SET parent_department_id = ? WHERE id = ?",
            (parent_id, department_id),
        )

    for team_id, department_id in team_department.items():
        cur.execute(
            "UPDATE teams SET department_id = ? WHERE id = ?",
            (department_id, team_id),
        )

    for employee_id, team_id in employee_team.items():
        cur.execute(
            "UPDATE employees SET team_id = ? WHERE id = ?",
            (team_id, employee_id),
        )

    for employee_id, manager_id in employee_manager.items():
        cur.execute(
            "UPDATE employees SET manager_id = ? WHERE id = ?",
            (manager_id, employee_id),
        )

    for project_id, team_id in project_owner.items():
        cur.execute(
            "UPDATE projects SET owner_team_id = ? WHERE id = ?",
            (team_id, project_id),
        )


def _replace_relation_table(cur, table, rows, query):
    cur.execute(f"DELETE FROM {table}")
    cur.executemany(query, rows)


def _apply_inferred_relations(cur, graph):
    inferred_rows = []
    for source, target, data in graph.edges(data=True):
        relation = data.get("relation")
        if relation not in INFERRED_RELATIONS:
            continue
        evidence = data.get("evidence", "spaCy-inferred relation")
        inferred_rows.append((source, target, relation, evidence))

    _replace_relation_table(
        cur,
        "inferred_relations",
        inferred_rows,
        "INSERT INTO inferred_relations (source_node, target_node, relation, evidence) VALUES (?,?,?,?)",
    )


def _apply_relation_tables(cur, graph):
    project_dependencies = _relation_pairs(graph, "DEPENDS_ON", "project", "project")
    skill_prerequisites = _relation_pairs(graph, "PREREQUISITE_OF", "skill", "skill")
    employee_skills = _relation_pairs(graph, "HAS_SKILL", "employee", "skill")
    employee_projects = _relation_pairs(graph, "WORKS_ON", "employee", "project")

    _replace_relation_table(
        cur,
        "project_dependencies",
        sorted(project_dependencies),
        "INSERT INTO project_dependencies (project_id, prerequisite_project_id) VALUES (?,?)",
    )
    _replace_relation_table(
        cur,
        "skill_prerequisites",
        sorted(skill_prerequisites),
        "INSERT INTO skill_prerequisites (skill_id, prerequisite_skill_id) VALUES (?,?)",
    )
    _replace_relation_table(
        cur,
        "employee_skills",
        sorted(employee_skills),
        "INSERT INTO employee_skills (emp_id, skill_id) VALUES (?,?)",
    )
    _replace_relation_table(
        cur,
        "employee_projects",
        sorted(employee_projects),
        "INSERT INTO employee_projects (emp_id, project_id) VALUES (?,?)",
    )


def _write_sql_from_graph(graph):
    conn = sqlite3.connect(SQLITE_PATH)
    conn.execute("PRAGMA foreign_keys = OFF")
    cur = conn.cursor()

    _reset_tables(cur)
    nodes = _node_maps(graph)
    department_parent = _single_parent_map(graph, "SUBDEPARTMENT_OF", "department", "department")
    team_department = _direct_map(graph, "LOCATED_IN", "team", "department")
    employee_team = _direct_map(graph, "MEMBER_OF", "employee", "team")
    employee_manager = _single_parent_map(graph, "MANAGES", "employee", "employee")
    project_owner = _single_parent_map(graph, "OWNS_PROJECT", "team", "project")

    _apply_nodes(
        cur,
        nodes,
        department_parent,
        team_department,
        employee_team,
        employee_manager,
        project_owner,
    )
    _apply_relation_tables(cur, graph)
    _apply_inferred_relations(cur, graph)

    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")
    conn.close()


def sync_to_sql():
    print("\nLoading graph snapshot baseline...")
    snapshot_graph = _load_graph(SNAPSHOT_PATH)
    current_graph = _load_graph(GRAPH_PATH)

    log_graph_delta(snapshot_graph, current_graph, "Graph -> SQL sync")

    if snapshot_graph.number_of_nodes() == current_graph.number_of_nodes() and snapshot_graph.number_of_edges() == current_graph.number_of_edges():
        same_snapshot = True
        for node, data in snapshot_graph.nodes(data=True):
            if node not in current_graph.nodes or current_graph.nodes[node] != data:
                same_snapshot = False
                break
        if same_snapshot:
            for source, target, data in snapshot_graph.edges(data=True):
                if not current_graph.has_edge(source, target) or current_graph.get_edge_data(source, target) != data:
                    same_snapshot = False
                    break
        if same_snapshot:
            print("No graph changes detected. SQL is already in sync.\n")
            return

    print("Applying current graph state to SQLite...")
    _write_sql_from_graph(current_graph)
    save_graph(current_graph, SNAPSHOT_PATH)
    print(f"Graph state applied to {SQLITE_PATH}")
    print(f"Snapshot refreshed -> {SNAPSHOT_PATH}\n")


if __name__ == "__main__":
    sync_to_sql()
