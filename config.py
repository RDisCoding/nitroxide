from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
SQLITE_PATH = str(BASE_DIR / "employees.db")
GRAPH_PATH = str(BASE_DIR / "graph_state.json")
SNAPSHOT_PATH = str(BASE_DIR / "graph_snapshot.json")
VISUALIZATION_PATH = str(BASE_DIR / "graph_visualization.html")
