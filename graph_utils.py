import json
from pathlib import Path

import networkx as nx


def node_id(entity, sql_id):
    return f"{entity}:{sql_id}"


def build_graph(employees, projects, links):
    graph = nx.DiGraph()

    for employee in employees:
        graph.add_node(
            node_id("employee", employee["id"]),
            entity="employee",
            label="Employee",
            sql_id=employee["id"],
            name=employee["name"],
            department=employee["department"],
            role=employee["role"],
        )

    for project in projects:
        graph.add_node(
            node_id("project", project["id"]),
            entity="project",
            label="Project",
            sql_id=project["id"],
            project_name=project["project_name"],
        )

    for link in links:
        graph.add_edge(
            node_id("employee", link["emp_id"]),
            node_id("project", link["project_id"]),
            relation="WORKS_ON",
        )

    return graph


def save_graph(graph, path):
    payload = {
        "nodes": [
            {"node_id": node, **data}
            for node, data in graph.nodes(data=True)
        ],
        "edges": [
            {"source": source, "target": target, **data}
            for source, target, data in graph.edges(data=True)
        ],
    }

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def load_graph(path):
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)

    graph = nx.DiGraph()

    for node in payload.get("nodes", []):
        node_data = dict(node)
        node_key = node_data.pop("node_id")
        graph.add_node(node_key, **node_data)

    for edge in payload.get("edges", []):
        edge_data = dict(edge)
        source = edge_data.pop("source")
        target = edge_data.pop("target")
        graph.add_edge(source, target, **edge_data)

    return graph


def graph_to_state(graph):
    employees = {}
    projects = {}
    links = set()

    for _, data in graph.nodes(data=True):
        entity = data.get("entity")
        sql_id = data.get("sql_id")
        if entity == "employee":
            employees[sql_id] = dict(data)
        elif entity == "project":
            projects[sql_id] = dict(data)

    for source, target, data in graph.edges(data=True):
        if data.get("relation") != "WORKS_ON":
            continue

        source_data = graph.nodes[source]
        target_data = graph.nodes[target]
        if source_data.get("entity") == "employee" and target_data.get("entity") == "project":
            links.add((source_data["sql_id"], target_data["sql_id"]))

    return employees, projects, links


def update_node_property(graph_path, entity, sql_id, field, value):
    graph = load_graph(graph_path)
    target_node = node_id(entity, sql_id)

    if target_node not in graph:
        raise KeyError(f"Node not found: {target_node}")

    graph.nodes[target_node][field] = value
    save_graph(graph, graph_path)
    return target_node


def render_graph_html(graph_path, html_path):
    graph = load_graph(graph_path)

    try:
        from pyvis.network import Network
    except ImportError as exc:
        raise SystemExit(
            "pyvis is required for visualization. Install it with: pip install -r requirements.txt"
        ) from exc

    network = Network(height="800px", width="100%", directed=True, bgcolor="#0f172a", font_color="#e2e8f0")
    network.barnes_hut(gravity=-18000, central_gravity=0.25, spring_length=180, spring_strength=0.02, damping=0.09)

    for node, data in graph.nodes(data=True):
        entity = data.get("entity", "node")
        label = data.get("name") or data.get("project_name") or node
        title = json.dumps(data, indent=2)
        color = "#38bdf8" if entity == "employee" else "#f59e0b"
        shape = "dot"
        size = 28 if entity == "employee" else 32
        network.add_node(node, label=label, title=title, color=color, shape=shape, size=size)

    for source, target, data in graph.edges(data=True):
        network.add_edge(source, target, label=data.get("relation", ""), color="#94a3b8")

    html_path = Path(html_path)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    network.write_html(str(html_path), open_browser=False)
    return str(html_path)