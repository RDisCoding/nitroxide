import os
import sys
import time
from pathlib import Path

# Add parent dir to sys.path to import config
current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent
sys.path.append(str(parent_dir))

from config import GRAPH_PATH, SQLITE_PATH
from neo4j_client import get_driver_with_fallback, get_default_database
from graph_to_neo4j import sync_to_neo4j
from neo4j_to_graph import pull_from_neo4j

# Import SQLite sync functions
from graph_to_sql import sync_to_sql
from sql_to_graph import push_to_graph

POLL_INTERVAL_SECONDS = 1.5


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except FileNotFoundError:
        return 0.0


def _get_neo4j_state_hash(driver):
    database = get_default_database()
    try:
        with driver.session(database=database) as session:
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


def run_unified_watch(interval=POLL_INTERVAL_SECONDS):
    print("Unified Live Sync started. Press Ctrl+C to stop.")
    print(f"Watching SQLite ({SQLITE_PATH}), Graph JSON ({GRAPH_PATH}), and Neo4j Database")

    driver = get_driver_with_fallback()
    
    last_db_mtime = _mtime(SQLITE_PATH)
    last_graph_mtime = _mtime(GRAPH_PATH)
    last_neo4j_hash = _get_neo4j_state_hash(driver)

    try:
        while True:
            time.sleep(interval)
            current_db_mtime = _mtime(SQLITE_PATH)
            current_graph_mtime = _mtime(GRAPH_PATH)
            current_neo4j_hash = _get_neo4j_state_hash(driver)

            sqlite_changed = current_db_mtime > last_db_mtime
            graph_changed = current_graph_mtime > last_graph_mtime
            neo4j_changed = current_neo4j_hash is not None and current_neo4j_hash != last_neo4j_hash

            if not (sqlite_changed or graph_changed or neo4j_changed):
                continue

            if sqlite_changed and not (graph_changed or neo4j_changed):
                print("\nSQLite changed -> Pushing to Graph and Neo4j")
                push_to_graph()
                sync_to_neo4j()
            elif neo4j_changed and not (sqlite_changed or graph_changed):
                print("\nNeo4j changed -> Pulling to Graph and SQLite")
                pull_from_neo4j()
                sync_to_sql()
            elif graph_changed and not (sqlite_changed or neo4j_changed):
                print("\nGraph JSON changed -> Syncing to SQLite and Neo4j")
                sync_to_sql()
                sync_to_neo4j()
            else:
                # If multiple sources changed at the exact same time, we resolve conflicts
                # by treating the local JSON as the source of truth, since it acts as the bridge.
                print("\nMultiple sources changed -> Syncing Graph JSON to SQLite and Neo4j")
                sync_to_sql()
                sync_to_neo4j()

            # Refresh trackers after sync operations
            last_db_mtime = _mtime(SQLITE_PATH)
            last_graph_mtime = _mtime(GRAPH_PATH)
            last_neo4j_hash = _get_neo4j_state_hash(driver)
            
    except KeyboardInterrupt:
        print("\nUnified Live Sync stopped.")
    finally:
        driver.close()


if __name__ == "__main__":
    run_unified_watch()
