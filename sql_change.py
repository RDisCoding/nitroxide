#!/usr/bin/env python
"""Execute SQL changes against the local SQLite database.

Examples:
  python sql_change.py --sql "UPDATE employees SET role = 'Principal Engineer' WHERE id = 3"
  python sql_change.py --file changes.sql
  python sql_change.py --sql "UPDATE employees SET role = 'Principal Engineer' WHERE id = 3" --sync-graph
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from config import SQLITE_PATH


def _read_sql_input(args: argparse.Namespace) -> str:
    if args.file is not None:
        return Path(args.file).read_text(encoding="utf-8")
    return args.sql


def _execute_sql(sql_text: str) -> None:
    statements = [statement.strip() for statement in sql_text.split(";") if statement.strip()]
    if not statements:
        raise SystemExit("No SQL statements were provided.")

    conn = sqlite3.connect(SQLITE_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        cur = conn.cursor()
        for statement in statements:
            cur.execute(statement)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute SQL changes against the local SQLite database.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--sql", help="Inline SQL to execute.")
    source.add_argument("--file", help="Path to a .sql file to execute.")
    parser.add_argument(
        "--sync-graph",
        action="store_true",
        help="Refresh graph_state.json after the SQL change is applied.",
    )
    args = parser.parse_args()

    sql_text = _read_sql_input(args)
    _execute_sql(sql_text)
    print(f"SQL change applied to {SQLITE_PATH}")

    if args.sync_graph:
        from sql_to_graph import push_to_graph

        push_to_graph()


if __name__ == "__main__":
    main()
