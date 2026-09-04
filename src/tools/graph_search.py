"""Agent-facing GraphDB query tool."""
from infrastructure.graph_db.client import OxigraphClient


def sparql(query: str):
    return OxigraphClient().query(query)

