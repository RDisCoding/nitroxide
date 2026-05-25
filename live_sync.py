import os
import time

from config import GRAPH_PATH, SQLITE_PATH
from graph_to_sql import sync_to_sql
from sql_to_graph import push_to_graph


POLL_INTERVAL_SECONDS = 1.0


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except FileNotFoundError:
        return 0.0


def run_watch(interval_seconds=POLL_INTERVAL_SECONDS):
    print("Live sync watch started. Press Ctrl+C to stop.")
    print(f"Watching {GRAPH_PATH} and {SQLITE_PATH}")

    last_graph_mtime = _mtime(GRAPH_PATH)
    last_db_mtime = _mtime(SQLITE_PATH)

    try:
        while True:
            time.sleep(interval_seconds)
            current_graph_mtime = _mtime(GRAPH_PATH)
            current_db_mtime = _mtime(SQLITE_PATH)

            graph_changed = current_graph_mtime > last_graph_mtime
            db_changed = current_db_mtime > last_db_mtime

            if not graph_changed and not db_changed:
                continue

            if graph_changed and not db_changed:
                print("Graph changed -> syncing to SQLite")
                sync_to_sql()
            elif db_changed and not graph_changed:
                print("SQLite changed -> refreshing graph")
                push_to_graph()
            else:
                if current_graph_mtime >= current_db_mtime:
                    print("Both changed -> syncing graph to SQLite")
                    sync_to_sql()
                else:
                    print("Both changed -> refreshing graph from SQLite")
                    push_to_graph()

            last_graph_mtime = _mtime(GRAPH_PATH)
            last_db_mtime = _mtime(SQLITE_PATH)
    except KeyboardInterrupt:
        print("\nLive sync watch stopped.")
