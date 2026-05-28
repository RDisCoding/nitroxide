"""Export all nodes and relationships from Neo4j to a JSON file.

Usage:
  python pull_from_neo4j.py --out graph_state_neo4j.json
"""
import argparse
import json
from neo4j_client import get_default_database, get_driver_with_fallback


def pull(out_path, neo4j_uri=None, neo4j_user=None, neo4j_password=None):
    driver = get_driver_with_fallback(neo4j_uri, neo4j_user, neo4j_password)
    nodes = []
    edges = []
    with driver.session(database=get_default_database()) as session:
        res = session.run("MATCH (n) RETURN id(n) as _nid, labels(n) as labels, properties(n) as props")
        for r in res:
            nodes.append({"id": r["_nid"], "labels": r["labels"], "props": r["props"]})
        res = session.run("MATCH (a)-[r]->(b) RETURN id(a) as a_id, id(b) as b_id, type(r) as type, properties(r) as props")
        for r in res:
            edges.append({"from": r["a_id"], "to": r["b_id"], "type": r["type"], "props": r["props"]})
    driver.close()
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"nodes": nodes, "edges": edges}, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--neo4j-uri")
    p.add_argument("--neo4j-user")
    p.add_argument("--neo4j-password")
    args = p.parse_args()
    pull(args.out, args.neo4j_uri, args.neo4j_user, args.neo4j_password)
