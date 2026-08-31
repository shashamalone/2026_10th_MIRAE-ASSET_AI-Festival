# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request

EXPECTED_RELEASE = "financial-products-2026-08-24@ddb3d994a4a5115a75bed7efa9c4cd0f6655f95b0a49f3b0e3c01b2bf8301a38"


def request(
    url: str,
    path: str,
    statement: str | None = None,
    *,
    content_type: str = "text/plain; charset=utf-8",
) -> tuple[int, dict]:
    body = None if statement is None else statement.encode("utf-8")
    headers = {} if body is None else {"Content-Type": content_type}
    req = urllib.request.Request(
        url.rstrip("/") + path,
        data=body,
        headers=headers,
        method="GET" if body is None else "POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def wait_for_health(url: str, attempts: int = 30, interval_seconds: float = 2) -> dict:
    last_error = "no response"
    for attempt in range(attempts):
        try:
            status, health = request(url, "/health")
            if (
                status == 200
                and health.get("release_id") == EXPECTED_RELEASE
                and health.get("readiness") is True
            ):
                return health
            last_error = f"status={status} payload={health}"
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt + 1 < attempts:
            time.sleep(interval_seconds)
    raise SystemExit(f"HEALTH FAIL after {attempts} attempts: {last_error}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--health-only", action="store_true")
    parser.add_argument("--expected-graph-triples", type=int, default=1_628_311)
    args = parser.parse_args()
    wait_for_health(args.url)
    if args.health_only:
        print("RAW QUERY API HEALTH PASS")
        return

    version_status, version = request(args.url, "/db/version")
    stats_status, stats = request(args.url, "/db/stats")
    tables_status, tables = request(args.url, "/db/tables")
    columns_status, columns = request(
        args.url, "/db/columns?table_schema=enriched&table_name=product_master"
    )
    catalog_status, catalog = request(
        args.url, "/db/catalog?table_schema=enriched&table_name=product_master"
    )
    sql_status, sql = request(
        args.url,
        "/db/sql",
        "SELECT (SELECT count(*) FROM raw.bond_kr_master)+"
        "(SELECT count(*) FROM raw.etf_kr_master)+"
        "(SELECT count(*) FROM raw.etf_gl_master)+"
        "(SELECT count(*) FROM raw.fund_pub_master) AS official,"
        "(SELECT count(*) FROM relations.product_holding) AS holdings,"
        "(SELECT count(*) FROM relations.company_subsidiary) AS subsidiaries",
    )
    cap_status, capped = request(
        args.url,
        "/db/sql",
        "SELECT product_id FROM enriched.product_master ORDER BY product_id LIMIT 101",
    )
    sparql_status, sparql = request(
        args.url,
        "/db/sparql",
        "SELECT (COUNT(*) AS ?triples) WHERE { ?s ?p ?o }",
    )
    sql_write_status, _ = request(
        args.url, "/db/sql", "DELETE FROM enriched.product_master"
    )
    sparql_write_status, _ = request(
        args.url, "/db/sparql", "INSERT DATA { <a> <b> <c> }"
    )
    json_status, _ = request(
        args.url,
        "/db/sql",
        '{"sql":"SELECT 1"}',
        content_type="application/json",
    )
    generic_status, _ = request(args.url, "/db", "SELECT 1")
    v1_status, _ = request(args.url, "/v1/release")

    read_statuses = (
        version_status,
        stats_status,
        tables_status,
        columns_status,
        catalog_status,
        sql_status,
        cap_status,
        sparql_status,
    )
    if any(status != 200 for status in read_statuses):
        raise SystemExit(f"RAW QUERY READ FAIL: statuses={read_statuses}")
    if version["rows"][0].get("release_id") != EXPECTED_RELEASE:
        raise SystemExit(f"VERSION FAIL: {version}")
    table_names = {(row["table_schema"], row["table_name"]) for row in tables["rows"]}
    if ("enriched", "product_master") not in table_names:
        raise SystemExit(f"TABLE FAIL: {tables}")
    if not stats.get("rows") or not columns.get("rows") or not catalog.get("rows"):
        raise SystemExit("METADATA FAIL")
    counts = sql["rows"][0]
    if tuple(int(counts[key]) for key in ("official", "holdings", "subsidiaries")) != (
        53_375,
        46_951,
        8_866,
    ):
        raise SystemExit(f"RDB COUNT FAIL: {counts}")
    if capped.get("row_count") != 100 or capped.get("truncated") is not True:
        raise SystemExit(f"ROW CAP FAIL: {capped}")
    if int(sparql["rows"][0]["triples"]) != args.expected_graph_triples:
        raise SystemExit(f"UNION DEFAULT GRAPH FAIL: {sparql}")
    if sql_write_status == 200 or sparql_write_status == 200:
        raise SystemExit(
            f"WRITE GUARD FAIL: sql={sql_write_status} sparql={sparql_write_status}"
        )
    if json_status != 415 or generic_status != 404 or v1_status != 404:
        raise SystemExit(
            "ROUTE CONTRACT FAIL: "
            f"json={json_status} generic_db={generic_status} v1={v1_status}"
        )
    print(
        "RAW QUERY API PASS: text/plain SQL/SPARQL readonly; "
        "official=53375 holdings=46951 subsidiaries=8866 "
        f"graph={args.expected_graph_triples} union_default=on"
    )


if __name__ == "__main__":
    main()
