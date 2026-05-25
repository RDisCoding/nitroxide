# knowledge_graph_neo4j

This folder contains utilities to sync the project's knowledge graph data with a Neo4j database.

Prerequisites
- Python 3.10+ (3.11 recommended)
- Docker (recommended for running Neo4j locally) or a running Neo4j instance

Install Python deps

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Start Neo4j with Docker (quickest)

```powershell
docker run --name neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/test -d neo4j:5.12
```

Environment variables
- `NEO4J_URI` (default: `neo4j://localhost:7687`)
- `NEO4J_USER` (default: `neo4j`)
- `NEO4J_PASSWORD` (default: `test`)

Examples

1) Push SQLite `employees.db` into Neo4j

```powershell
python sql_to_neo4j.py --sqlite "../knowledge graph/employees.db"
```

2) Push an existing JSON graph export into Neo4j

```powershell
python graph_json_to_neo4j.py --json "../knowledge graph/graph_state.json"
```

3) Pull full Neo4j export to JSON

```powershell
python pull_from_neo4j.py --out graph_state_neo4j.json
```

Notes and safety
- Relationship types in the code are validated against a small allow-list in the scripts. If you add new relation types, update `ALLOWED_RELATIONS` in the scripts.
- The scripts use `MERGE` to avoid duplicate nodes when re-running.

Common debug steps
- Confirm Neo4j is reachable: `curl http://localhost:7474` or open http://localhost:7474 in a browser (HTTP UI) and http://localhost:7474/browser/
- If authentication fails, override env vars or pass `--neo4j-*` args.

Recommended workflow
1. Run `python sql_to_neo4j.py --sqlite "../knowledge graph/employees.db"` to create nodes/relations from the canonical SQL DB.
2. Optionally pull the DB: `python pull_from_neo4j.py --out neo4j_export.json` to inspect what was created.
3. If you edit the graph JSON and want to reflect changes: `python graph_json_to_neo4j.py --json "../knowledge graph/graph_state.json"`.

If you want, I can add a small CLI wrapper to automate common operations (push, pull, diff).