# SQL <-> Knowledge Graph Sync — Local MVP

This project now runs a richer local knowledge graph on top of SQLite and a JSON-backed NetworkX graph. Changes on either side can be reflected to the other side, and a live watcher keeps them in sync in real time.

## What is in the graph

The graph now includes:

- Departments with sub-department hierarchy
- Teams linked to departments
- Employees linked to teams and managers
- Projects owned by teams and linked by dependencies
- Skills with prerequisite relationships
- Employee-to-skill and employee-to-project links
- A `description` field on every node, generated from the node's metadata and local graph context

That gives you multiple parent-child branches and many-to-many relationships instead of a flat employee/project sample.

## Install

```bash
pip install -r requirements.txt
```

## First run

```bash
python main.py init
```

This creates and seeds the SQLite database, exports the graph to `graph_state.json`, and writes a baseline snapshot to `graph_snapshot.json`.

## Live sync

Run the watcher in one terminal:

```bash
python main.py watch
```

Then edit either side:

- Change `graph_state.json` directly, or use `python main.py set ...`, `link`, and `unlink`
- Update the SQLite database from another tool or script

The watcher will push graph changes into SQLite and refresh the graph when SQLite changes.

## spaCy relation extraction

Run the extractor to infer extra relations from the current graph:

```bash
python main.py extract
```

This uses spaCy to read node descriptions and infer relations from the text in those descriptions.

The extractor prefers the installed `en_core_web_sm` model and falls back to a blank spaCy pipeline only if that model is unavailable.

If you change the graph structure and want the descriptions refreshed, run:

```bash
python backfill_descriptions.py
```

## SQL change script

If you want to update SQLite directly from the terminal, run `sql_change.py` from the project folder:

```bash
python sql_change.py --sql "UPDATE employees SET role = 'Principal Engineer' WHERE id = 3"
```

Add `--sync-graph` if you want the graph files refreshed immediately after the SQL change:

```bash
python sql_change.py --sql "UPDATE employees SET role = 'Principal Engineer' WHERE id = 3" --sync-graph
```

To check SQL -> graph parity, run:

```bash
python main.py push
```

That command rebuilds `graph_state.json` from the current SQLite database.

## Useful commands

```bash
python main.py status
python main.py viz
python main.py set employee 3 role Staff Engineer
python main.py link employee 3 skill 4 HAS_SKILL
python main.py unlink employee 3 skill 4 HAS_SKILL
python main.py extract
python main.py sync
python main.py push
python sql_change.py --sql "UPDATE employees SET role = 'Principal Engineer' WHERE id = 3" --sync-graph
```

## Visualize the graph

Run:

```bash
python main.py viz
```

This generates `graph_visualization.html`, an interactive local view you can open in a browser.

Hovering over a node shows the node metadata plus the metadata of the nodes it connects to and receives connections from.

## Testing the loop

1. Run `python main.py init`
2. Start `python main.py watch`
3. Edit a graph node or edge
4. Check `python main.py status`
5. Change a table in SQLite from a script or editor
6. Wait for the watcher to refresh the graph

When you change a node or an edge, the console now logs the node fields that changed and the connected nodes that are affected.

## Files

- `setup_db.py` creates and seeds the richer SQLite schema
- `sql_to_graph.py` exports the database into the graph
- `graph_to_sql.py` applies the graph state back to SQLite
- `live_sync.py` runs the real-time bidirectional watcher
- `graph_utils.py` stores, loads, edits, and visualizes the graph
- `main.py` provides the CLI entry point
