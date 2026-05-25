import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import networkx as nx


ENTITY_COLORS = {
    "department": "#60a5fa",
    "team": "#34d399",
    "employee": "#f59e0b",
    "project": "#c084fc",
    "skill": "#fb7185",
}

ENTITY_SIZES = {
    "department": 34,
    "team": 30,
    "employee": 28,
    "project": 30,
    "skill": 26,
}


def node_id(entity, sql_id):
    return f"{entity}:{sql_id}"


def edge_key(source, target, relation):
    return f"{source}->{target}:{relation}"


def _node_label(data):
    return data.get("name") or data.get("project_name") or data.get("skill_name") or data.get("label") or data.get("entity") or "node"


def _unique_text(values):
    seen = []
    for value in values:
        if not value:
            continue
        if value not in seen:
            seen.append(value)
    return seen


def build_node_description(graph, node):
    data = graph.nodes[node]
    entity = data.get("entity") or str(node).split(":", 1)[0]
    label = _node_label(data)

    if label == "node" and isinstance(node, str):
        label = node

    if entity == "department":
        teams = [
            _node_label(graph.nodes[target])
            for source, target, edge_data in graph.in_edges(node, data=True)
            if edge_data.get("relation") == "LOCATED_IN" and graph.nodes[source].get("entity") == "team"
        ]
        teams = _unique_text(teams)
        if teams:
            return f"{label} is a department that contains the teams {', '.join(teams[:4])}."
        return f"{label} is a department."

    if entity == "team":
        departments = [
            _node_label(graph.nodes[target])
            for source, target, edge_data in graph.out_edges(node, data=True)
            if edge_data.get("relation") == "LOCATED_IN" and graph.nodes[target].get("entity") == "department"
        ]
        projects = [
            _node_label(graph.nodes[target])
            for source, target, edge_data in graph.out_edges(node, data=True)
            if edge_data.get("relation") == "OWNS_PROJECT" and graph.nodes[target].get("entity") == "project"
        ]
        parts = [f"{label} is a team."]
        if departments:
            parts.append(f"It is located in the {departments[0]} department.")
        if projects:
            parts.append(f"It owns the projects {', '.join(_unique_text(projects)[:4])}.")
        return " ".join(parts)

    if entity == "employee":
        team_names = [
            _node_label(graph.nodes[target])
            for source, target, edge_data in graph.out_edges(node, data=True)
            if edge_data.get("relation") == "MEMBER_OF" and graph.nodes[target].get("entity") == "team"
        ]
        project_names = [
            _node_label(graph.nodes[target])
            for source, target, edge_data in graph.out_edges(node, data=True)
            if edge_data.get("relation") == "WORKS_ON" and graph.nodes[target].get("entity") == "project"
        ]
        skill_names = [
            _node_label(graph.nodes[target])
            for source, target, edge_data in graph.out_edges(node, data=True)
            if edge_data.get("relation") == "HAS_SKILL" and graph.nodes[target].get("entity") == "skill"
        ]
        manager_names = [
            _node_label(graph.nodes[source])
            for source, target, edge_data in graph.in_edges(node, data=True)
            if edge_data.get("relation") == "MANAGES" and graph.nodes[source].get("entity") == "employee"
        ]
        parts = []
        if data.get("role"):
            parts.append(f"{label} is a {data['role']}.")
        else:
            parts.append(f"{label} is an employee.")
        if team_names:
            parts.append(f"They are on the {team_names[0]} team.")
        if project_names:
            parts.append(f"They work on {', '.join(_unique_text(project_names)[:4])}.")
        if skill_names:
            parts.append(f"They have skills in {', '.join(_unique_text(skill_names)[:5])}.")
        if manager_names:
            parts.append(f"They report to {manager_names[0]}.")
        return " ".join(parts)

    if entity == "project":
        owner_teams = [
            _node_label(graph.nodes[source])
            for source, target, edge_data in graph.in_edges(node, data=True)
            if edge_data.get("relation") == "OWNS_PROJECT" and graph.nodes[source].get("entity") == "team"
        ]
        dependencies = [
            _node_label(graph.nodes[target])
            for source, target, edge_data in graph.out_edges(node, data=True)
            if edge_data.get("relation") == "DEPENDS_ON" and graph.nodes[target].get("entity") == "project"
        ]
        parts = [f"{label} is a project."]
        if owner_teams:
            parts.append(f"It is owned by the {owner_teams[0]} team.")
        if dependencies:
            parts.append(f"It depends on {', '.join(_unique_text(dependencies)[:4])}.")
        return " ".join(parts)

    if entity == "skill":
        prereqs = [
            _node_label(graph.nodes[target])
            for source, target, edge_data in graph.out_edges(node, data=True)
            if edge_data.get("relation") == "PREREQUISITE_OF" and graph.nodes[target].get("entity") == "skill"
        ]
        parts = [f"{label} is a skill."]
        if prereqs:
            parts.append(f"It is a prerequisite for {', '.join(_unique_text(prereqs)[:4])}.")
        return " ".join(parts)

    return f"{label} is a {entity or 'node'}."


def enrich_graph_descriptions(graph):
    for node, data in graph.nodes(data=True):
        data["description"] = build_node_description(graph, node)
    return graph


def _format_attr_lines(data, ignore_keys=None):
    ignore = set(ignore_keys or ())
    lines = []
    for key in sorted(data):
        if key in ignore:
            continue
        lines.append(f"{key}: {data[key]}")
    return lines


def _format_node_summary(graph, node, max_neighbors=8):
    data = graph.nodes[node]
    lines = [
        _node_label(data),
        "Metadata:",
    ]

    for line in _format_attr_lines(data, ignore_keys={"entity", "label"}):
        lines.append(f"  {line}")

    outgoing = list(graph.out_edges(node, data=True))
    incoming = list(graph.in_edges(node, data=True))

    if outgoing:
        lines.append("Connected nodes:")
        for source, target, edge_data in outgoing[:max_neighbors]:
            target_data = graph.nodes[target]
            relation = edge_data.get("relation", "")
            target_attrs = ", ".join(_format_attr_lines(target_data, ignore_keys={"entity", "label"})[:4])
            lines.append(f"  -> {relation} -> {_node_label(target_data)} | {target_attrs}")

    if incoming:
        lines.append("Incoming from:")
        for source, target, edge_data in incoming[:max_neighbors]:
            source_data = graph.nodes[source]
            relation = edge_data.get("relation", "")
            source_attrs = ", ".join(_format_attr_lines(source_data, ignore_keys={"entity", "label"})[:4])
            lines.append(f"  <- {relation} <- {_node_label(source_data)} | {source_attrs}")

    return "\n".join(lines)


def node_hover_title(graph, node, max_neighbors=8):
    return _format_node_summary(graph, node, max_neighbors=max_neighbors)


def node_attribute_delta(old_data, new_data):
    keys = set(old_data) | set(new_data)
    delta = {}
    for key in sorted(keys):
        old_value = old_data.get(key)
        new_value = new_data.get(key)
        if old_value != new_value:
            delta[key] = (old_value, new_value)
    return delta


def graph_delta(old_graph, new_graph):
    node_changes = []
    edge_additions = []
    edge_removals = []

    old_nodes = set(old_graph.nodes)
    new_nodes = set(new_graph.nodes)

    for node in sorted(old_nodes & new_nodes):
        delta = node_attribute_delta(old_graph.nodes[node], new_graph.nodes[node])
        if delta:
            node_changes.append((node, delta))

    for node in sorted(new_nodes - old_nodes):
        node_changes.append((node, {"__status__": (None, "added")}))

    for node in sorted(old_nodes - new_nodes):
        node_changes.append((node, {"__status__": ("removed", None)}))

    old_edges = {(source, target, data.get("relation", "")) for source, target, data in old_graph.edges(data=True)}
    new_edges = {(source, target, data.get("relation", "")) for source, target, data in new_graph.edges(data=True)}

    for edge in sorted(new_edges - old_edges):
        edge_additions.append(edge)

    for edge in sorted(old_edges - new_edges):
        edge_removals.append(edge)

    return node_changes, edge_additions, edge_removals


def log_graph_delta(old_graph, new_graph, heading):
    node_changes, edge_additions, edge_removals = graph_delta(old_graph, new_graph)

    if not node_changes and not edge_additions and not edge_removals:
        print(f"{heading}: no graph changes detected.")
        return

    print(f"{heading}: graph changes detected")

    for node, delta in node_changes:
        print(f"  Node {node}")
        if "__status__" in delta:
            before, after = delta["__status__"]
            if after == "added":
                print("    status: added")
            elif before == "removed":
                print("    status: removed")
            continue
        for key, (before, after) in delta.items():
            print(f"    {key}: {before} -> {after}")
        graph = new_graph if node in new_graph else old_graph
        if node in graph:
            neighbors = set(graph.successors(node)) | set(graph.predecessors(node))
            if neighbors:
                print("    affected connected nodes:")
                for neighbor in sorted(neighbors)[:8]:
                    neighbor_data = graph.nodes[neighbor]
                    print(f"      - {neighbor}: {_node_label(neighbor_data)}")

    for source, target, relation in edge_additions:
        print(f"  Edge added: {source} -> {target} [{relation}]")
        for endpoint in (source, target):
            if endpoint in new_graph:
                print(f"    endpoint: {endpoint} | {_node_label(new_graph.nodes[endpoint])}")

    for source, target, relation in edge_removals:
        print(f"  Edge removed: {source} -> {target} [{relation}]")
        for endpoint in (source, target):
            if endpoint in old_graph:
                print(f"    endpoint: {endpoint} | {_node_label(old_graph.nodes[endpoint])}")


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

    enrich_graph_descriptions(graph)
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


def add_edge(graph, source, target, relation):
    graph.add_edge(source, target, relation=relation)


def remove_edge(graph, source, target, relation=None):
    if not graph.has_edge(source, target):
        return False

    if relation is None:
        graph.remove_edge(source, target)
        return True

    data = graph.get_edge_data(source, target, default={})
    if data.get("relation") == relation:
        graph.remove_edge(source, target)
        return True

    return False


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

    network = Network(height="800px", width="100%", directed=True, bgcolor="#0b1020", font_color="#e2e8f0")
    network.barnes_hut(gravity=-22000, central_gravity=0.2, spring_length=170, spring_strength=0.02, damping=0.09)

    for node, data in graph.nodes(data=True):
        entity = data.get("entity", "node")
        label = data.get("name") or data.get("project_name") or data.get("skill_name") or node
        title = node_hover_title(graph, node)
        color = ENTITY_COLORS.get(entity, "#94a3b8")
        shape = "dot"
        size = ENTITY_SIZES.get(entity, 24)
        network.add_node(node, label=label, title=title, color=color, shape=shape, size=size)

    for source, target, data in graph.edges(data=True):
        relation = data.get("relation", "")
        edge_color = "#94a3b8"
        if relation in ("MANAGES", "MEMBER_OF", "SUBDEPARTMENT_OF"):
            edge_color = "#22c55e"
        elif relation in ("DEPENDS_ON", "PREREQUISITE_OF"):
            edge_color = "#f97316"
        elif relation in ("WORKS_ON", "HAS_SKILL", "LOCATED_IN", "OWNS_PROJECT"):
            edge_color = "#60a5fa"
        network.add_edge(source, target, label=relation, color=edge_color, arrows="to")

    html_path = Path(html_path)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    network.write_html(str(html_path), open_browser=False)
    return str(html_path)