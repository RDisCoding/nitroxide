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

## Command reference

Use this section as the quick reference for what each command does and when to use it.

### Core database and graph workflow

- `python main.py setup`: create and seed the SQLite database from scratch. Use this when you want a clean reset.
- `python main.py push`: rebuild `graph_state.json` and `graph_snapshot.json` from SQLite. Use this after direct SQL edits or when you want the graph to match the database.
- `python main.py sync`: push graph edits back into SQLite. Use this after editing node properties or edges in the JSON graph.
- `python main.py init`: run `setup` and `push` in one step. Use this for a first-time setup or when you want to reset everything and repopulate the graph.
- `python main.py watch`: keep SQLite and the graph in sync live. Use this when you are actively editing both sides.
- `python main.py status`: print the current database state plus inferred relations. Use this when you want a quick sanity check.
- `python main.py viz`: generate `graph_visualization.html`. Use this when you want to inspect the graph visually.

### Manual graph edits

- `python main.py set <entity> <sql_id> <field> <value>`: update a single node attribute in the graph. Use this for quick metadata edits like `role`, `name`, or `description`.
- `python main.py link <source_entity> <source_id> <target_entity> <target_id> <relation>`: add a graph edge. Use this when you want to connect two nodes directly.
- `python main.py unlink <source_entity> <source_id> <target_entity> <target_id> [relation]`: remove a graph edge. Use this when a relation is wrong or no longer valid.

### Relation extraction

- `python main.py extract`: run the default spaCy-based relation extraction. Use this when you want the model to read node descriptions.
- `python main.py extract --mode llm`: run Groq LLM extraction. Use this when you want the LLM to infer relations from node data.
- `python main.py extract --mode llm --node-only`: run Groq using only node metadata. Use this when you do not want to provide any extra text corpus.
- `python main.py extract --mode llm --text-dir relation_texts`: run Groq and also include extra `.txt`, `.md`, or `.rst` files from a folder. Use this when you have supporting notes outside the graph.
- `python backfill_descriptions.py`: regenerate node descriptions inside `graph_state.json` and `graph_snapshot.json`. Use this after changing graph structure or description logic.

### Direct SQL edits

- `python sql_change.py --sql "UPDATE ..."`: apply one or more SQL statements directly to SQLite. Use this when the database is the source of truth for a change.
- `python sql_change.py --file changes.sql`: apply SQL from a file. Use this when you have a prepared SQL script.
- `python sql_change.py --sql "UPDATE ..." --sync-graph`: apply SQL and immediately refresh the graph from SQLite. Use this when you want both sides updated without a second command.

### Typical choices

- If you edited SQL directly, run `python main.py push`.
- If you edited the graph JSON directly, run `python main.py sync`.
- If you want to infer relations from the node descriptions only, run `python main.py extract --mode llm --node-only`.
- If you want to infer relations from descriptions plus extra notes, run `python main.py extract --mode llm --text-dir relation_texts`.
- If you just want the simplest setup, run `python main.py init`.

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

## Groq LLM relation extraction

If you want to infer relations with an LLM instead of spaCy, put your API key in `.env`:

```bash
GROQ_API_KEY=your_key_here
GROQ_MODEL=llama-3.1-8b-instant
```

Then run:

```bash
python main.py extract --mode llm
```

If you want the LLM to use only raw node metadata and no descriptions or extra text sources, run:

```bash
python main.py extract --mode llm --node-only
```

You can also point it at extra text sources:

```bash
python main.py extract --mode llm --text-dir relation_texts
```

This mode reads the node descriptions and text sources, asks Groq to return JSON relations, and writes the inferred edges back into the graph.
The `--node-only` flag switches it to raw node metadata only. Use this when you do not want to maintain descriptions and only have the node fields themselves plus optional relation text files.

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
