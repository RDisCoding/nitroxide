"""Push an existing `graph_state.json` (NetworkX/pyvis export) into Neo4j.

Usage:
  python graph_json_to_neo4j.py --json ../knowledge graph/graph_state.json
"""
import os
import json
import argparse
from neo4j_client import get_default_database, get_driver_with_fallback

ALLOWED_RELATIONS = {"COLLABORATES_WITH", "TEAMMATE_OF", "SHARES_SKILL", "SHARES_PROJECT", "MANAGES", "MEMBER_OF", "IN_DEPARTMENT"}


def push_json(graph_json_path, neo4j_uri=None, neo4j_user=None, neo4j_password=None):
    with open(graph_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Expecting format with 'nodes' and 'edges' arrays (pyvis-style or custom)
    nodes = data.get("nodes") or data.get("elements", {}).get("nodes") or []
    edges = data.get("edges") or data.get("elements", {}).get("edges") or []
    database = get_default_database()

    driver = get_driver_with_fallback(neo4j_uri, neo4j_user, neo4j_password)
    with driver.session(database=database) as session:
        for n in nodes:
            # Support different node id fields produced by NetworkX/pyvis and our exports
            nid = n.get("id") or n.get("node_id") or n.get("nodeId") or n.get("sql_id")
            label = n.get("type") or n.get("label") or (n.get("entity") or "Node")
            if isinstance(n.get("data"), dict):
                props = dict(n.get("data", {}))
            else:
                # Flatten node properties while skipping id-like and label keys
                props = {k: v for k, v in n.items() if k not in ("id", "node_id", "nodeId", "type", "label")}
            # Ensure there is an id to use as a lookup key in Neo4j
            if nid is None:
                # fallback to using name or generated id
                nid = props.get("name") or props.get("project_name") or f"node_{abs(hash(json.dumps(n))) % 100000}"
                props["_generated_id"] = True
            # Create node with label
            cypher = f"MERGE (x:{label} {{id:$id}}) SET x += $props"
            session.run(cypher, id=nid, props=props)
        for e in edges:
            src = e.get("from") or e.get("source") or e.get("from_id") or e.get("fromId")
            dst = e.get("to") or e.get("target") or e.get("to_id") or e.get("toId")
            rtype = (e.get("type") or e.get("label") or "RELATED_TO").upper().replace(" ", "_")
            if rtype not in ALLOWED_RELATIONS:
                rtype = "RELATED_TO"
            cypher = f"MATCH (a {{id:$a}}), (b {{id:$b}}) MERGE (a)-[r:{rtype}]->(b)"
            session.run(cypher, a=src, b=dst)
    driver.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--json", required=True, help="Path to graph_state.json")
    p.add_argument("--neo4j-uri")
    p.add_argument("--neo4j-user")
    p.add_argument("--neo4j-username")
    p.add_argument("--neo4j-password")
    p.add_argument("--neo4j-database")
    args = p.parse_args()
    if args.neo4j_database:
        os.environ["NEO4J_DATABASE"] = args.neo4j_database
    if args.neo4j_username and not args.neo4j_user:
        args.neo4j_user = args.neo4j_username
    push_json(args.json, args.neo4j_uri, args.neo4j_user, args.neo4j_password)
