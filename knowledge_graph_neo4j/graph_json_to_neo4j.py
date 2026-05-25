"""Push an existing `graph_state.json` (NetworkX/pyvis export) into Neo4j.

Usage:
  python graph_json_to_neo4j.py --json ../knowledge graph/graph_state.json
"""
import json
import argparse
from neo4j_client import get_driver

ALLOWED_RELATIONS = {"COLLABORATES_WITH", "TEAMMATE_OF", "SHARES_SKILL", "SHARES_PROJECT", "MANAGES", "MEMBER_OF", "IN_DEPARTMENT"}


def push_json(graph_json_path, neo4j_uri=None, neo4j_user=None, neo4j_password=None):
    with open(graph_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Expecting format with 'nodes' and 'edges' arrays (pyvis-style or custom)
    nodes = data.get("nodes") or data.get("elements", {}).get("nodes") or []
    edges = data.get("edges") or data.get("elements", {}).get("edges") or []

    driver = get_driver(neo4j_uri, neo4j_user, neo4j_password)
    with driver.session() as session:
        for n in nodes:
            nid = n.get("id")
            label = n.get("type") or n.get("label") or "Node"
            props = dict(n.get("data", {})) if isinstance(n.get("data"), dict) else {k: v for k, v in n.items() if k not in ("id", "type")}
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
    p.add_argument("--neo4j-password")
    args = p.parse_args()
    push_json(args.json, args.neo4j_uri, args.neo4j_user, args.neo4j_password)
