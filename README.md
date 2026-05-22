# SQL ↔ Knowledge Graph Sync — Local MVP

Tests the core concept: **can graph node edits reflect back into a SQL database?**

```
SQLite  ──push──▶  Local NetworkX Graph JSON
        ◀──sync──
```

---

## 1. Prerequisites

### Python packages
```bash
pip install -r requirements.txt
```

No external graph database is required. The graph is stored locally in JSON files.
The visualization command generates a local HTML file with an interactive graph.

---

## 2. Config  (`config.py`)

```python
SQLITE_PATH    = "employees.db"
GRAPH_PATH     = "graph_state.json"
SNAPSHOT_PATH  = "graph_snapshot.json"
```

---

## 3. First-Time Setup

```bash
python main.py init
```

This:
- Creates `employees.db` with 4 employees, 2 projects, 4 assignments
- Pushes everything to `graph_state.json` as nodes + relationships
- Saves `graph_snapshot.json` as a baseline

---

## 4. Explore the Graph

Open `graph_state.json` in VS Code.

The graph is just JSON, for example:

```json
{
  "nodes": [
    {
      "node_id": "employee:1",
      "entity": "employee",
      "sql_id": 1,
      "name": "Rahul",
      "department": "AI",
      "role": "Engineer"
    }
  ],
  "edges": [
    {
      "source": "employee:1",
      "target": "project:1",
      "relation": "WORKS_ON"
    }
  ]
}
```

---

## 5. Edit a Node in the Graph

Change node properties directly in `graph_state.json`, or use the CLI:

```bash
python main.py set employee 1 department Research
```

If you prefer manual editing, the JSON shape still looks like this:

```json
{
  "node_id": "employee:1",
  "entity": "employee",
  "sql_id": 1,
  "name": "Rahul",
  "department": "Research",
  "role": "Engineer"
}
```

You can also add or remove entries in `edges` to change relationships.

To visualize the graph network locally, run:

```bash
python main.py viz
```

This writes `graph_visualization.html`, which you can open in a browser.

---

## 6. Sync Changes Back to SQL

```bash
python main.py sync
```

Output:
```
📡  Reading current local graph state …
⚖️   Diffing old vs new …
🛠️   Applying 1 change(s) to SQLite …

   📝  UPDATE employees  id=1  →  {'department': 'Research'}

✅  1 SQL operation(s) committed to employees.db
```

---

## 7. Verify SQL Updated

```bash
python main.py status
```

```
┌─ employees ────────────────────────────────────────
  id   name         department     role
  ──────────────────────────────────────────
  1    Rahul        Research       Engineer   ← changed!
  2    Ananya       Backend        Engineer
  3    Priya        AI             Manager
  4    Vikram       DevOps         Engineer
```

---

## 8. Refresh Snapshot

After syncing, update the baseline so the next diff is accurate:

```bash
python main.py push
```

---

## Full Workflow (repeat)

```
edit graph_state.json  →  python main.py sync  →  python main.py status  →  python main.py push
```

Or, for a quick node tweak:

```
python main.py set employee 1 department Research
python main.py sync
```

---

## What the Diff Engine Catches

| Graph Change                        | SQL Operation                        |
|-------------------------------------|--------------------------------------|
| Edit node property (e.g. department)| `UPDATE employees SET …`             |
| Delete a node                       | `DELETE FROM employees …`            |
| Add a new node                      | `INSERT INTO employees …`            |
| Remove a WORKS_ON relationship      | `DELETE FROM employee_projects …`    |
| Add a WORKS_ON relationship         | `INSERT INTO employee_projects …`    |

---

## Files

```
config.py         — local file paths
setup_db.py       — creates & seeds SQLite
graph_utils.py    — NetworkX helpers for local graph storage
sql_to_graph.py   — SQL → NetworkX push + snapshot
graph_to_sql.py   — graph diff → SQL sync
main.py           — CLI entry point
```
