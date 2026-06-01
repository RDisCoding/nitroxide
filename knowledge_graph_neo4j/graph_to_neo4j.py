import os
import sys
from pathlib import Path
import json

# Add parent dir to sys.path to import config and graph_utils
current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent
sys.path.append(str(parent_dir))

from config import GRAPH_PATH, SNAPSHOT_PATH
from graph_utils import load_graph, log_graph_delta, save_graph, graph_delta
from neo4j_client import get_driver_with_fallback, get_default_database

SNAPSHOT_NEO4J_PATH = str(current_dir / "snapshot_neo4j.json")


def _apply_delta(driver, old_graph, new_graph):
    node_changes, edge_additions, edge_removals = graph_delta(old_graph, new_graph)
    database = get_default_database()
    
    with driver.session(database=database) as session:
        # Handle Node Removals
        for node_id, delta in node_changes:
            if "__status__" in delta and delta["__status__"][0] == "removed":
                session.run("MATCH (n {id: $id}) DETACH DELETE n", id=node_id)
        
        # Handle Edge Removals
        for source, target, relation in edge_removals:
            if not relation:
                relation = "RELATED_TO"
            cypher = f"MATCH (a {{id: $source}})-[r:{relation}]->(b {{id: $target}}) DELETE r"
            session.run(cypher, source=source, target=target)
            
        # Handle Node Additions & Modifications
        for node_id, delta in node_changes:
            if "__status__" in delta and delta["__status__"][0] == "removed":
                continue
            
            data = new_graph.nodes[node_id]
            label = data.get("type") or data.get("label") or (data.get("entity") or "Node")
            props = {k: v for k, v in data.items() if k not in ("id", "node_id", "nodeId", "type", "label") and v is not None}
            cypher = f"MERGE (n:{label} {{id: $id}}) SET n += $props"
            session.run(cypher, id=node_id, props=props)
            
        # Handle Edge Additions
        for source, target, relation in edge_additions:
            if not relation:
                relation = "RELATED_TO"
            cypher = f"MATCH (a {{id: $source}}), (b {{id: $target}}) MERGE (a)-[r:{relation}]->(b)"
            session.run(cypher, source=source, target=target)


def sync_to_neo4j():
    print("\nLoading graph snapshot baseline for Neo4j...")
    
    try:
        current_graph = load_graph(GRAPH_PATH)
    except FileNotFoundError:
        print(f"Graph file not found: {GRAPH_PATH}. Run python main.py push first.")
        return
        
    try:
        snapshot_graph = load_graph(SNAPSHOT_NEO4J_PATH)
    except FileNotFoundError:
        import networkx as nx
        snapshot_graph = nx.DiGraph()

    log_graph_delta(snapshot_graph, current_graph, "Graph -> Neo4j sync")

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
            print("No graph changes detected. Neo4j is already in sync.\n")
            return

    print("Applying current graph state to Neo4j...")
    try:
        driver = get_driver_with_fallback()
        _apply_delta(driver, snapshot_graph, current_graph)
        driver.close()
    except Exception as e:
        print(f"Failed to sync to Neo4j: {e}")
        return

    save_graph(current_graph, SNAPSHOT_NEO4J_PATH)
    print(f"Graph state applied to Neo4j")
    print(f"Snapshot refreshed -> {SNAPSHOT_NEO4J_PATH}\n")


if __name__ == "__main__":
    sync_to_neo4j()
