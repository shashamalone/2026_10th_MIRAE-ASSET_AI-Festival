# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request

EXPECTED_RELEASE = "financial-products-2026-08-24@ddb3d994a4a5115a75bed7efa9c4cd0f6655f95b0a49f3b0e3c01b2bf8301a38"


def request(url: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url.rstrip("/") + path,
        data=body,
        headers={"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
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
    parser.add_argument("--team-db-public", action="store_true")
    args = parser.parse_args()
    wait_for_health(args.url)
    if args.health_only:
        print("V2 HEALTH PASS")
        return
    checks = [
        request(args.url, "/v1/release"),
        request(args.url, "/v1/capabilities"),
        request(args.url, "/v1/products/search", {"name": "KODEX 200", "match": "exact", "limit": 5}),
        request(args.url, "/v1/ontology/validate", {"validation_type": "credit_rating", "value": "AAAA"}),
    ]
    if any(code != 200 for code, _payload in checks):
        raise SystemExit(f"CURATED API FAIL: {checks}")
    if checks[0][1].get("release_id") != EXPECTED_RELEASE:
        raise SystemExit("RELEASE FAIL")
    if (checks[1][1].get("coverage") or {}).get("question_count") != 35:
        raise SystemExit("CAPABILITY FAIL")
    if (checks[3][1].get("data") or {}).get("code") != "ABSTAIN_INVALID_TAXONOMY":
        raise SystemExit("ONTOLOGY FAIL")
    if not args.team_db_public:
        raw_status, raw_payload = request(args.url, "/db/sql", {"sql": "SELECT 1"})
        if raw_status != 404 or raw_payload.get("code") != "ROUTE_NOT_PUBLIC":
            raise SystemExit(f"PUBLIC RAW ROUTE FAIL: status={raw_status} payload={raw_payload}")
        print("DATA API V1 PASS: release/capabilities/search/ontology curated; raw query not public")
        return

    version_status, version = request(args.url, "/db/version")
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
        {
            "sql": (
                "SELECT (SELECT count(*) FROM raw.bond_kr_master)+"
                "(SELECT count(*) FROM raw.etf_kr_master)+"
                "(SELECT count(*) FROM raw.etf_gl_master)+"
                "(SELECT count(*) FROM raw.fund_pub_master) AS official,"
                "(SELECT count(*) FROM relations.product_holding) AS holdings,"
                "(SELECT count(*) FROM relations.company_subsidiary) AS subsidiaries"
            )
        },
    )
    cap_status, capped = request(
        args.url,
        "/db/sql",
        {"sql": "SELECT product_id FROM enriched.product_master ORDER BY product_id LIMIT 101"},
    )
    sparql_status, sparql = request(
        args.url,
        "/db/sparql",
        {
            "sparql": (
                "SELECT (COUNT(*) AS ?triples) WHERE { "
                "{ ?s ?p ?o } UNION { GRAPH ?g { ?s ?p ?o } } }"
            )
        },
    )
    sql_write_status, _ = request(
        args.url, "/db/sql", {"sql": "DELETE FROM enriched.product_master"}
    )
    sparql_write_status, _ = request(
        args.url, "/db/sparql", {"sparql": "INSERT DATA { <a> <b> <c> }"}
    )
    if any(status != 200 for status in (
        version_status,
        tables_status,
        columns_status,
        catalog_status,
        sql_status,
        cap_status,
        sparql_status,
    )):
        raise SystemExit("TEAM DB READ FAIL")
    if version["rows"][0].get("release_id") != EXPECTED_RELEASE:
        raise SystemExit(f"TEAM DB VERSION FAIL: {version}")
    table_names = {(row["table_schema"], row["table_name"]) for row in tables["rows"]}
    if ("enriched", "product_master") not in table_names or ("relations", "product_holding") not in table_names:
        raise SystemExit(f"TEAM DB TABLE FAIL: {tables}")
    if not columns.get("rows") or not catalog.get("rows"):
        raise SystemExit("TEAM DB CATALOG FAIL")
    counts = sql["rows"][0]
    if tuple(int(counts[key]) for key in ("official", "holdings", "subsidiaries")) != (53375, 46951, 8866):
        raise SystemExit(f"TEAM DB COUNT FAIL: {counts}")
    if capped.get("row_count") != 100 or capped.get("truncated") is not True:
        raise SystemExit(f"TEAM DB CAP FAIL: {capped}")
    if int(sparql["rows"][0]["triples"]) != 655388:
        raise SystemExit(f"TEAM DB GRAPH FAIL: {sparql}")
    if sql_write_status == 200 or sparql_write_status == 200:
        raise SystemExit(
            f"TEAM DB WRITE GUARD FAIL: sql={sql_write_status} sparql={sparql_write_status}"
        )
    print(
        "TEAM DB API PASS: release/catalog/sql/sparql readonly; "
        "official=53375 holdings=46951 subsidiaries=8866 graph=655388"
    )


if __name__ == "__main__":
    main()
