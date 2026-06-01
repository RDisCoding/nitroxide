import os
import sys
from pathlib import Path
import networkx as nx

# Add parent dir to sys.path to import config and graph_utils
current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent
sys.path.append(str(parent_dir))

from config import GRAPH_PATH
from graph_utils import enrich_graph_descriptions, log_graph_delta, load_graph, save_graph
from neo4j_client import get_driver_with_fallback, get_default_database

SNAPSHOT_NEO4J_PATH = str(current_dir / "snapshot_neo4j.json")


def _read_neo4j():
    driver = get_driver_with_fallback()
    database = get_default_database()
    nodes = []
    edges = []
    
    with driver.session(database=database) as session:
        res = session.run("MATCH (n) RETURN labels(n) as labels, properties(n) as props")
        for r in res:
            nodes.append({"labels": r["labels"], "props": r["props"]})
            
        res = session.run("MATCH (a)-[r]->(b) RETURN properties(a) as a_props, properties(b) as b_props, type(r) as type, properties(r) as props")
        for r in res:
            edges.append({
                "source_id": r["a_props"].get("id"),
                "target_id": r["b_props"].get("id"),
                "relation": r["type"],
                "props": r["props"]
            })
            
    driver.close()
    return nodes, edges


def _build_graph(nodes, edges):
    graph = nx.DiGraph()

    for node in nodes:
        props = node["props"]
        labels = node["labels"]
        node_id_val = props.get("id")
        if not node_id_val:
            continue
            
        # Create node data dict with entity
        node_data = {"sql_id": props.get("sql_id") or node_id_val.split(":")[-1] if ":" in node_id_val else node_id_val}
        node_data.update(props)
        
        # We need an entity type. Typically label is capitalized, entity is lowercase
        if labels:
            node_data["entity"] = labels[0].lower()
            node_data["label"] = labels[0]
            
        graph.add_node(node_id_val, **node_data)

    for edge in edges:
        source_id = edge["source_id"]
        target_id = edge["target_id"]
        if not source_id or not target_id:
            continue
            
        edge_data = {"relation": edge["relation"]}
        edge_data.update(edge["props"])
        graph.add_edge(source_id, target_id, **edge_data)

    enrich_graph_descriptions(graph)
    return graph


def pull_from_neo4j():
    print("\nReading Neo4j...")
    nodes, edges = _read_neo4j()

    print(f"   {len(nodes)} nodes | {len(edges)} edges")

    graph = _build_graph(nodes, edges)
    try:
        previous_graph = load_graph(SNAPSHOT_NEO4J_PATH)
    except FileNotFoundError:
        previous_graph = None

    if previous_graph is not None:
        log_graph_delta(previous_graph, graph, "Neo4j -> Graph sync")

    save_graph(graph, GRAPH_PATH)
    save_graph(graph, SNAPSHOT_NEO4J_PATH)
    print(f"Graph saved -> {GRAPH_PATH}")
    print(f"Snapshot saved -> {SNAPSHOT_NEO4J_PATH}")
    print("Local knowledge graph populated from Neo4j.\n")


if __name__ == "__main__":
    pull_from_neo4j()
