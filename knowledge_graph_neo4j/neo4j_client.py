import os
from neo4j import GraphDatabase

def get_driver(uri=None, user=None, password=None):
    uri = uri or os.getenv("NEO4J_URI", "neo4j://localhost:7687")
    user = user or os.getenv("NEO4J_USER", "neo4j")
    password = password or os.getenv("NEO4J_PASSWORD", "test")
    return GraphDatabase.driver(uri, auth=(user, password))
