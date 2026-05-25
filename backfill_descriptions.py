from graph_utils import enrich_graph_descriptions, load_graph, save_graph
from config import GRAPH_PATH, SNAPSHOT_PATH


def backfill(path):
    graph = load_graph(path)
    enrich_graph_descriptions(graph)
    save_graph(graph, path)


if __name__ == "__main__":
    backfill(GRAPH_PATH)
    try:
        backfill(SNAPSHOT_PATH)
    except FileNotFoundError:
        pass
    print("Backfilled descriptions in graph JSON files.")
