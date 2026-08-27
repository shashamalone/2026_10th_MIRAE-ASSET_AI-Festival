# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
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
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--health-only", action="store_true")
    args = parser.parse_args()
    status, health = request(args.url, "/health")
    if status != 200 or health.get("release_id") != EXPECTED_RELEASE or not health.get("readiness"):
        raise SystemExit(f"HEALTH FAIL: status={status} payload={health}")
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
    raw_status, raw_payload = request(
        args.url,
        "/db/sql",
        {"sql": "SELECT 1"},
    )
    if raw_status != 404 or raw_payload.get("code") != "ROUTE_NOT_PUBLIC":
        raise SystemExit(f"PUBLIC RAW ROUTE FAIL: status={raw_status} payload={raw_payload}")
    print("DATA API V1 PASS: release/capabilities/search/ontology curated; raw query not public")


if __name__ == "__main__":
    main()
