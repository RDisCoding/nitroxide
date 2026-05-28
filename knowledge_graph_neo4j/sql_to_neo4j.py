"""Push an SQLite-based employees DB into Neo4j.

Usage examples:
  python sql_to_neo4j.py --sqlite "../knowledge graph/employees.db"
  NEO4J_URI=neo4j://localhost:7687 NEO4J_USER=neo4j NEO4J_PASSWORD=test python sql_to_neo4j.py --sqlite "../knowledge graph/employees.db"
"""
import sqlite3
import argparse
from neo4j_client import get_default_database, get_driver_with_fallback

ALLOWED_RELATIONS = {"COLLABORATES_WITH", "TEAMMATE_OF", "SHARES_SKILL", "SHARES_PROJECT", "MANAGES", "MEMBER_OF", "IN_DEPARTMENT"}


def push_sql(sqlite_path, neo4j_uri=None, neo4j_user=None, neo4j_password=None):
    conn = sqlite3.connect(sqlite_path)
    cur = conn.cursor()
    driver = get_driver_with_fallback(neo4j_uri, neo4j_user, neo4j_password)
    with driver.session(database=get_default_database()) as session:
        # Departments
        try:
            for id, name in cur.execute("SELECT id, name FROM departments"):
                session.run("MERGE (d:Department {id:$id}) SET d.name=$name", id=id, name=name)
        except Exception:
            pass
        # Teams
        try:
            for id, name, department_id in cur.execute("SELECT id, name, department_id FROM teams"):
                session.run("MERGE (t:Team {id:$id}) SET t.name=$name", id=id, name=name)
                if department_id is not None:
                    session.run(
                        "MATCH (t:Team {id:$id}), (d:Department {id:$did}) MERGE (t)-[:IN_DEPARTMENT]->(d)",
                        id=id, did=department_id,
                    )
        except Exception:
            pass
        # Employees
        try:
            for id, name, title, team_id, manager_id in cur.execute(
                "SELECT id, name, title, team_id, manager_id FROM employees"
            ):
                session.run("MERGE (e:Employee {id:$id}) SET e.name=$name, e.title=$title", id=id, name=name, title=title)
                if team_id is not None:
                    session.run(
                        "MATCH (e:Employee {id:$id}), (t:Team {id:$tid}) MERGE (e)-[:MEMBER_OF]->(t)",
                        id=id,
                        tid=team_id,
                    )
                if manager_id is not None:
                    session.run(
                        "MATCH (e:Employee {id:$id}), (m:Employee {id:$mid}) MERGE (m)-[:MANAGES]->(e)",
                        id=id,
                        mid=manager_id,
                    )
        except Exception:
            pass
        # Inferred relations table (if exists) - try multiple known schemas
        try:
            # try legacy schema (src_id, dst_id, relation_type)
            rows = list(cur.execute("SELECT src_id, dst_id, relation_type FROM inferred_relations"))
        except Exception:
            try:
                # fallback to modern schema (source_node, target_node, relation)
                rows = list(cur.execute("SELECT source_node, target_node, relation FROM inferred_relations"))
            except Exception:
                rows = []

        for row in rows:
            if len(row) >= 3:
                src, dst, rtype = row[0], row[1], row[2]
            else:
                continue
            if not isinstance(rtype, str):
                rtype = str(rtype)
            if rtype not in ALLOWED_RELATIONS:
                continue
            cypher = f"MATCH (a {{id:$a}}), (b {{id:$b}}) MERGE (a)-[r:{rtype}]->(b)"
            session.run(cypher, a=src, b=dst)
    conn.close()
    driver.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--sqlite", required=True, help="Path to employees SQLite DB")
    p.add_argument("--neo4j-uri")
    p.add_argument("--neo4j-user")
    p.add_argument("--neo4j-password")
    args = p.parse_args()
    push_sql(args.sqlite, args.neo4j_uri, args.neo4j_user, args.neo4j_password)
