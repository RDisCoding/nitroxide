# ─────────────────────────────────────────────
#  sql_to_graph.py  —  SQL → local NetworkX graph  (one-way push)
#
#  Reads every row from SQLite, creates a richer
#  hierarchy graph with parent-child and many-to-many
#  links, then saves the graph and a snapshot baseline.
# ─────────────────────────────────────────────

import sqlite3

from config import GRAPH_PATH, SQLITE_PATH, SNAPSHOT_PATH
from graph_utils import add_edge, log_graph_delta, load_graph, node_id, save_graph
from networkx import DiGraph


def _read_table(cur, query):
    return [dict(row) for row in cur.execute(query).fetchall()]


def _read_sqlite():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    departments = _read_table(cur, "SELECT * FROM departments ORDER BY id")
    teams = _read_table(cur, "SELECT * FROM teams ORDER BY id")
    employees = _read_table(cur, "SELECT * FROM employees ORDER BY id")
    projects = _read_table(cur, "SELECT * FROM projects ORDER BY id")
    skills = _read_table(cur, "SELECT * FROM skills ORDER BY id")
    employee_projects = _read_table(cur, "SELECT * FROM employee_projects ORDER BY emp_id, project_id")
    employee_skills = _read_table(cur, "SELECT * FROM employee_skills ORDER BY emp_id, skill_id")
    project_dependencies = _read_table(cur, "SELECT * FROM project_dependencies ORDER BY project_id, prerequisite_project_id")
    skill_prerequisites = _read_table(cur, "SELECT * FROM skill_prerequisites ORDER BY skill_id, prerequisite_skill_id")

    conn.close()
    return {
        "departments": departments,
        "teams": teams,
        "employees": employees,
        "projects": projects,
        "skills": skills,
        "employee_projects": employee_projects,
        "employee_skills": employee_skills,
        "project_dependencies": project_dependencies,
        "skill_prerequisites": skill_prerequisites,
    }


def _build_graph(data):
    graph = DiGraph()

    for row in data["departments"]:
        graph.add_node(
            node_id("department", row["id"]),
            entity="department",
            label="Department",
            sql_id=row["id"],
            name=row["name"],
        )

    for row in data["teams"]:
        graph.add_node(
            node_id("team", row["id"]),
            entity="team",
            label="Team",
            sql_id=row["id"],
            name=row["name"],
        )

    for row in data["employees"]:
        graph.add_node(
            node_id("employee", row["id"]),
            entity="employee",
            label="Employee",
            sql_id=row["id"],
            name=row["name"],
            role=row["role"],
        )

    for row in data["projects"]:
        graph.add_node(
            node_id("project", row["id"]),
            entity="project",
            label="Project",
            sql_id=row["id"],
            project_name=row["project_name"],
        )

    for row in data["skills"]:
        graph.add_node(
            node_id("skill", row["id"]),
            entity="skill",
            label="Skill",
            sql_id=row["id"],
            skill_name=row["skill_name"],
        )

    for row in data["departments"]:
        if row["parent_department_id"] is not None:
            add_edge(
                graph,
                node_id("department", row["parent_department_id"]),
                node_id("department", row["id"]),
                "SUBDEPARTMENT_OF",
            )

    for row in data["teams"]:
        add_edge(
            graph,
            node_id("team", row["id"]),
            node_id("department", row["department_id"]),
            "LOCATED_IN",
        )

    for row in data["employees"]:
        add_edge(
            graph,
            node_id("employee", row["id"]),
            node_id("team", row["team_id"]),
            "MEMBER_OF",
        )
        if row["manager_id"] is not None:
            add_edge(
                graph,
                node_id("employee", row["manager_id"]),
                node_id("employee", row["id"]),
                "MANAGES",
            )

    for row in data["projects"]:
        add_edge(
            graph,
            node_id("team", row["owner_team_id"]),
            node_id("project", row["id"]),
            "OWNS_PROJECT",
        )

    for row in data["project_dependencies"]:
        add_edge(
            graph,
            node_id("project", row["project_id"]),
            node_id("project", row["prerequisite_project_id"]),
            "DEPENDS_ON",
        )

    for row in data["skill_prerequisites"]:
        add_edge(
            graph,
            node_id("skill", row["skill_id"]),
            node_id("skill", row["prerequisite_skill_id"]),
            "PREREQUISITE_OF",
        )

    for row in data["employee_skills"]:
        add_edge(
            graph,
            node_id("employee", row["emp_id"]),
            node_id("skill", row["skill_id"]),
            "HAS_SKILL",
        )

    for row in data["employee_projects"]:
        add_edge(
            graph,
            node_id("employee", row["emp_id"]),
            node_id("project", row["project_id"]),
            "WORKS_ON",
        )

    return graph


def push_to_graph():
    print("\nReading SQLite...")
    data = _read_sqlite()

    print(
        "   "
        f"{len(data['departments'])} departments | "
        f"{len(data['teams'])} teams | "
        f"{len(data['employees'])} employees | "
        f"{len(data['projects'])} projects | "
        f"{len(data['skills'])} skills"
    )

    graph = _build_graph(data)
    try:
        previous_graph = load_graph(SNAPSHOT_PATH)
    except FileNotFoundError:
        previous_graph = None

    if previous_graph is not None:
        log_graph_delta(previous_graph, graph, "SQL -> graph sync")

    save_graph(graph, GRAPH_PATH)
    save_graph(graph, SNAPSHOT_PATH)
    print(f"Graph saved -> {GRAPH_PATH}")
    print(f"Snapshot saved -> {SNAPSHOT_PATH}")
    print("Local knowledge graph populated from SQL.\n")
    print("   Edit graph_state.json to change node properties or links.")
    print("   For quick edits use: python main.py set ...")
    print("   For relationships use: python main.py link ... / unlink ...")
    print("   Then run: python main.py sync\n")


if __name__ == "__main__":
    push_to_graph()
