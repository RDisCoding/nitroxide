import os
import time
from pathlib import Path

from neo4j import GraphDatabase

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None


if load_dotenv is not None:
    current_dir = Path(__file__).resolve().parent
    load_dotenv(current_dir / ".env")
    load_dotenv(current_dir.parent / ".env")
    for path in current_dir.glob("Neo4j-*-Created-*.txt"):
        load_dotenv(path)

def get_driver(uri=None, user=None, password=None):
    uri = uri or os.getenv("NEO4J_URI")
    user = user or os.getenv("NEO4J_USER") or os.getenv("NEO4J_USERNAME") or "neo4j"
    password = password or os.getenv("NEO4J_PASSWORD", "test")
    if not uri:
        raise RuntimeError(
            "Missing NEO4J_URI. Set it in knowledge_graph_neo4j/.env or pass --neo4j-uri "
            "(for Aura use neo4j+s://<host>:7687)."
        )
    return GraphDatabase.driver(uri, auth=(user, password))


def build_fallback_uri(uri):
    if not uri:
        return None
    if uri.startswith("neo4j+s://"):
        return "bolt+s://" + uri[len("neo4j+s://"):]
    if uri.startswith("neo4j://"):
        return "bolt://" + uri[len("neo4j://"):]
    return None


def get_default_database():
    return os.getenv("NEO4J_DATABASE") or "neo4j"


def verify_connectivity(driver, attempts=5, base_delay=2):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            driver.verify_connectivity()
            return
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(base_delay * attempt)
    raise RuntimeError(
        "Unable to connect to Aura after retries. The instance may still be provisioning, "
        "the password may be wrong, or the Aura host may be unavailable."
    ) from last_error


def get_driver_with_fallback(uri=None, user=None, password=None):
    primary_uri = uri or os.getenv("NEO4J_URI")
    user = user or os.getenv("NEO4J_USER") or os.getenv("NEO4J_USERNAME") or "neo4j"
    password = password or os.getenv("NEO4J_PASSWORD", "test")

    candidates = [primary_uri]
    fallback_uri = build_fallback_uri(primary_uri)
    if fallback_uri and fallback_uri not in candidates:
        candidates.append(fallback_uri)

    last_error = None
    for candidate in candidates:
        if not candidate:
            continue
        driver = GraphDatabase.driver(candidate, auth=(user, password))
        try:
            verify_connectivity(driver)
            return driver
        except Exception as exc:
            last_error = exc
            driver.close()

    raise RuntimeError(
        "Unable to connect to Neo4j using either the Aura routed URI or the direct Bolt fallback. "
        "Check that the instance is running, the password is correct, and the database name is neo4j."
    ) from last_error
