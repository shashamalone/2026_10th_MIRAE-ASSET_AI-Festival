# -*- coding: utf-8 -*-
"""Audit the selective T107 + T108 API composition without importing the app."""
from __future__ import annotations

import argparse
import ast
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXPECTED_ROUTES = {
    ("GET", "/health"),
    ("POST", "/db/sql"),
    ("POST", "/db/sparql"),
    ("GET", "/db/stats"),
    ("GET", "/db/tables"),
    ("GET", "/db/columns"),
    ("GET", "/db/catalog"),
    ("GET", "/db/version"),
    ("GET", "/answer"),
}
VECTOR_TABLES = {
    "bond_schema_terms",
    "schema_terms_all",
    "source_document",
    "document_product",
    "product_coverage",
    "chunk_embedding",
    "document_chunk",
}


def _assignment(tree: ast.AST, name: str) -> ast.AST | None:
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return node.value
    return None


def _literal_assignment(tree: ast.AST, name: str) -> Any:
    value = _assignment(tree, name)
    if value is None:
        return None
    try:
        return ast.literal_eval(value)
    except (ValueError, TypeError):
        return None


def _function(tree: ast.AST, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _routes(tree: ast.AST) -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not decorator.args:
                continue
            target = decorator.func
            path = decorator.args[0]
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "app"
                and target.attr in {"get", "post"}
                and isinstance(path, ast.Constant)
                and isinstance(path.value, str)
            ):
                routes.add((target.attr.upper(), path.value))
    return routes


def _has_actual_nul_guard(tree: ast.AST) -> bool:
    read_raw_query = _function(tree, "read_raw_query")
    if read_raw_query is None:
        return False
    return any(
        isinstance(node, ast.Compare)
        and any(isinstance(operator, ast.In) for operator in node.ops)
        and any(
            isinstance(comparator, ast.Name) and comparator.id == "statement"
            for comparator in node.comparators
        )
        and isinstance(node.left, ast.Constant)
        and node.left.value == "\x00"
        for node in ast.walk(read_raw_query)
    )


def _called_names(node: ast.AST | None) -> set[str]:
    if node is None:
        return set()
    return {
        call.func.id
        for call in ast.walk(node)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    }


def audit_source(source: str, source_path: str = "src/api.py") -> dict[str, Any]:
    tree = ast.parse(source, filename=source_path)
    routes = _routes(tree)
    app_version = _literal_assignment(tree, "APP_VERSION")
    version_tuple: tuple[int, ...] = ()
    if isinstance(app_version, str) and re.fullmatch(r"\d+\.\d+\.\d+", app_version):
        version_tuple = tuple(int(part) for part in app_version.split("."))

    graph_assignment = _assignment(tree, "EXPECTED_GRAPH_TRIPLES")
    graph_source = ast.get_source_segment(source, graph_assignment) if graph_assignment else ""
    vector_health = _function(tree, "vector_health")
    vector_source = ast.get_source_segment(source, vector_health) if vector_health else ""
    health = _function(tree, "health")
    health_source = ast.get_source_segment(source, health) if health else ""
    db_stats = _function(tree, "db_stats")
    stats_source = ast.get_source_segment(source, db_stats) if db_stats else ""
    calls = _called_names(tree)

    vector_count_keys = _literal_assignment(tree, "VECTOR_COUNT_KEYS")
    checks = {
        "api_version_advanced": version_tuple > (4, 1, 0),
        "canonical_graph_default": bool(
            graph_source
            and 'os.environ.get("EXPECTED_GRAPH_TRIPLES", "1226698")' in graph_source
            and "1169374" not in graph_source
        ),
        "actual_nul_guard": _has_actual_nul_guard(tree),
        "read_only_guards_called": {
            "ensure_read_only_sql",
            "ensure_read_only_sparql",
        }.issubset(calls),
        "exact_route_surface": routes == EXPECTED_ROUTES,
        "vector_constants_exact": (
            _literal_assignment(tree, "VECTOR_MODEL_ID") == "BAAI/bge-m3"
            and _literal_assignment(tree, "VECTOR_DIMENSION") == 1024
            and _literal_assignment(tree, "VECTOR_HNSW_INDEXES") == 3
            and _literal_assignment(tree, "VECTOR_SEARCH_FUNCTIONS") == 2
            and isinstance(vector_count_keys, dict)
            and set(vector_count_keys) == VECTOR_TABLES
        ),
        "active_vector_release_queried": bool(
            vector_source
            and "FROM vec.vector_deploy_run" in vector_source
            and "ORDER BY cutover_at DESC NULLS LAST,updated_at DESC" in vector_source
        ),
        "all_vector_tables_live_counted": bool(
            vector_source
            and all(f"FROM vec.{table}" in vector_source for table in VECTOR_TABLES)
        ),
        "vector_runtime_objects_checked": bool(
            vector_source
            and "a.amname='hnsw'" in vector_source
            and "search_schema_terms" in vector_source
            and "search_document_chunks" in vector_source
            and "has_function_privilege" in vector_source
        ),
        "vector_metadata_fail_closed": bool(
            vector_source
            and 'vector.get("status") == "active"' in vector_source
            and 'vector.get("release_id") == RELEASE_ID' in vector_source
            and 'vector.get("model_id") == VECTOR_MODEL_ID' in vector_source
            and "_same_int" in vector_source
        ),
        "health_requires_strict_vector_ready": bool(
            health_source
            and 'vector.get("ready") is True' in health_source
            and "validation_result->>'vector_status'" not in health_source
            and 'vector_status in {"pending", "ready"}' not in health_source
        ),
        "stats_exposes_seven_vector_tables": bool(
            stats_source
            and all(f"vec.{table}" in stats_source for table in VECTOR_TABLES)
        ),
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source_path,
        "overall_pass": all(checks.values()),
        "checks": checks,
        "observed": {
            "app_version": app_version,
            "routes": [f"{method} {path}" for method, path in sorted(routes)],
            "vector_tables": sorted(vector_count_keys) if isinstance(vector_count_keys, dict) else [],
        },
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# API vector-health composition audit",
        "",
        f"- Overall: **{'PASS' if result['overall_pass'] else 'FAIL'}**",
        f"- Source: `{result['source']}`",
        f"- API version: `{result['observed']['app_version']}`",
        f"- Route count: `{len(result['observed']['routes'])}`",
        f"- Vector table count: `{len(result['observed']['vector_tables'])}`",
        "",
        "## Contract checks",
        "",
    ]
    lines.extend(
        f"- {'PASS' if passed else 'FAIL'} `{name}`"
        for name, passed in result["checks"].items()
    )
    lines.extend(["", "## Routes", ""])
    lines.extend(f"- `{route}`" for route in result["observed"]["routes"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    api_path = args.repo_root.resolve() / "src" / "api.py"
    result = audit_source(api_path.read_text(encoding="utf-8"), "src/api.py")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "api_vector_health_composition.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "api_vector_health_composition.md").write_text(
        render_markdown(result),
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
