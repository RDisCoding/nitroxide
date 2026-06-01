import os
import sys
import time
from pathlib import Path

# Add parent dir to sys.path to import config
current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent
sys.path.append(str(parent_dir))

from config import GRAPH_PATH
from neo4j_client import get_driver_with_fallback, get_default_database
from graph_to_neo4j import sync_to_neo4j
from neo4j_to_graph import pull_from_neo4j

POLL_INTERVAL_SECONDS = 2.0


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except FileNotFoundError:
        return 0.0


def _get_neo4j_state_hash(driver):
    """
    Computes a lightweight hash/count of the Neo4j database to detect external changes.
    Since Neo4j doesn't provide a single 'last updated' timestamp by default,
    we count nodes, edges, and sum internal IDs as a proxy for state changes.
    """
    database = get_default_database()
    try:
        with driver.session(database=database) as session:
            # Query sums the internal element IDs and counts to create a signature
            res = session.run("""
                OPTIONAL MATCH (n)
                WITH count(n) as node_count
                OPTIONAL MATCH ()-[r]->()
                RETURN node_count, count(r) as edge_count
            """)
            record = res.single()
            if not record:
                return "empty"
            return f"{record['node_count']}_{record['edge_count']}"
    except Exception as e:
        print(f"Error checking Neo4j state: {e}")
        return None


def run_watch(interval_seconds=POLL_INTERVAL_SECONDS):
    print("Live sync watch for Neo4j started. Press Ctrl+C to stop.")
    print(f"Watching {GRAPH_PATH} and Neo4j Database")

    driver = get_driver_with_fallback()
    
    last_graph_mtime = _mtime(GRAPH_PATH)
    last_db_hash = _get_neo4j_state_hash(driver)
    
    print(f"Initial DB hash: {last_db_hash}")

    try:
        while True:
            time.sleep(interval_seconds)
            current_graph_mtime = _mtime(GRAPH_PATH)
            current_db_hash = _get_neo4j_state_hash(driver)

            graph_changed = current_graph_mtime > last_graph_mtime
            db_changed = current_db_hash is not None and current_db_hash != last_db_hash

            if not graph_changed and not db_changed:
                continue

            if graph_changed and not db_changed:
                print("\nGraph changed -> syncing to Neo4j")
                sync_to_neo4j()
            elif db_changed and not graph_changed:
                print("\nNeo4j DB changed -> refreshing graph")
                pull_from_neo4j()
            else:
                # Both changed: since db_hash doesn't give us a timestamp, 
                # we'll prioritize pulling from Neo4j in a collision, or 
                # we can push to Neo4j. Let's push to Neo4j as graph_state might be newer.
                print("\nBoth changed -> syncing graph to Neo4j (resolving conflict)")
                sync_to_neo4j()

            # Update tracking variables
            last_graph_mtime = _mtime(GRAPH_PATH)
            last_db_hash = _get_neo4j_state_hash(driver)
            
    except KeyboardInterrupt:
        print("\nLive sync watch stopped.")
    finally:
        driver.close()


if __name__ == "__main__":
    run_watch()
