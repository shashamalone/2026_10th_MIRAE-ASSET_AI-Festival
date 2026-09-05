"""Collect a dated Korean ETF holdings snapshot from four publishers.

The script is intentionally artifact-only: it refuses to write under shared
``data/`` trees.  Every raw response is accompanied by a sidecar containing
the requested/validated date and a SHA-256 digest, and the final relation is
derived only from those validated responses.

Example::

    py -3.13 script/refresh_etf_holdings.py \
      --master C:/.../PREF01N001_etf_kr_master_20260824.csv \
      --output-dir artifacts/runs/20260906T000000Z/codex-t146-holdings-0906 \
      --as-of 2026-08-21
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd
import requests


USER_AGENT = {
    "User-Agent": "Mozilla/5.0 (MiraeAsset-AI-Festival; dated research snapshot)",
    "Accept": "*/*",
    "Accept-Language": "ko-KR,ko;q=0.9",
}
BRAND_NAMES = ("KODEX", "TIGER", "RISE", "ACE")
RELATION_COLUMNS = (
    "pd_itm_no",
    "holding_code_raw",
    "holding_code_type",
    "holding_name",
    "weight",
    "source",
    "as_of",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(value)
    os.replace(temporary, path)


def atomic_json(path: Path, value: object) -> None:
    atomic_write(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )


def normalize_date(value: object) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) != 8:
        return ""
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}"


def cells(fragment: str) -> list[str]:
    return [
        re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", item))).strip()
        for item in re.findall(r"<td[^>]*>(.*?)</td>", fragment, re.S | re.I)
    ]


def code_type(value: object) -> str:
    code = str(value).strip()
    if re.fullmatch(r"\d{6}", code):
        return "ticker6"
    if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{10}", code):
        return "isin"
    if " " in code and code.replace(" ", "").isalnum() and code.isascii():
        return "bloomberg"
    return "other"


def parse_kodex(body: bytes, requested_as_of: str) -> tuple[list[tuple[str, str, object]], dict]:
    payload = json.loads(body)
    pdf = payload.get("pdf") or {}
    returned_as_of = normalize_date(pdf.get("gijunYMD"))
    if returned_as_of != requested_as_of:
        raise ValueError(f"KODEX response date {returned_as_of!r} != {requested_as_of}")
    rows = [
        (str(item.get("itmNo") or "").strip(), str(item.get("secNm") or "").strip(), item.get("ratio"))
        for item in (pdf.get("list") or [])
        if str(item.get("itmNo") or "").strip()
    ]
    return rows, {"kind": "response_field", "field": "pdf.gijunYMD", "value": returned_as_of}


def parse_tiger(body: bytes, requested_as_of: str) -> tuple[list[tuple[str, str, object]], dict]:
    text = body.decode("utf-8", "replace")
    rows: list[tuple[str, str, object]] = []
    for fragment in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S | re.I):
        row = cells(fragment)
        if len(row) >= 5 and row[0]:
            rows.append((row[0], row[1], row[4]))
    return rows, {
        "kind": "publisher_dated_endpoint",
        "parameter": "fixDate",
        "value": requested_as_of,
        "response_row_count": len(rows),
    }


def parse_rise(body: bytes, requested_as_of: str) -> tuple[list[tuple[str, str, object]], dict]:
    text = body.decode("utf-8", "replace")
    rows: list[tuple[str, str, object]] = []
    for fragment in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S | re.I):
        row = cells(fragment)
        index = next((i for i, value in enumerate(row) if re.fullmatch(r"[A-Z0-9]{12}", value)), None)
        if index is None or index + 3 >= len(row) or row[index].startswith("CASH"):
            continue
        rows.append((row[index], row[index + 1], row[index + 3]))
    return rows, {
        "kind": "publisher_dated_endpoint",
        "parameter": "searchDate",
        "value": requested_as_of,
        "response_row_count": len(rows),
    }


def parse_ace(body: bytes, requested_as_of: str) -> tuple[list[tuple[str, str, object]], dict]:
    payload = json.loads(body)
    source_rows = payload.get("pdfList") or []
    returned_dates = sorted({normalize_date(item.get("std_DT")) for item in source_rows})
    returned_dates = [value for value in returned_dates if value]
    if returned_dates != [requested_as_of]:
        raise ValueError(f"ACE response dates {returned_dates!r} != {[requested_as_of]!r}")
    rows = [
        (
            str(item.get("jm_KSC_CD") or "").strip(),
            str(item.get("sec_NM") or "").strip(),
            item.get("wg"),
        )
        for item in source_rows
        if str(item.get("jm_KSC_CD") or "").strip()
    ]
    return rows, {"kind": "response_field", "field": "pdfList[].std_DT", "value": requested_as_of}


PARSERS: dict[str, Callable[[bytes, str], tuple[list[tuple[str, str, object]], dict]]] = {
    "KODEX": parse_kodex,
    "TIGER": parse_tiger,
    "RISE": parse_rise,
    "ACE": parse_ace,
}


@dataclass(frozen=True)
class Target:
    brand: str
    isin: str
    ticker: str
    name: str
    last_trading_date: str = ""


@dataclass(frozen=True)
class Adapter:
    extension: str
    source: str
    key: str


ADAPTERS = {
    "KODEX": Adapter("json", "삼성자산운용 KODEX (samsungfund.com)", "ticker"),
    "TIGER": Adapter("html", "Mirae Asset TIGER ETF (investments.miraeasset.com/tigeretf)", "isin"),
    "RISE": Adapter("xls", "KB Asset Management RISE ETF (riseetf.co.kr)", "ticker"),
    "ACE": Adapter("json", "한국투자신탁운용 ACE ETF (papi.aceetf.co.kr)", "isin"),
}


class Collector:
    def __init__(self, timeout: float, retries: int, backoff: float, pause: float):
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.pause = pause
        self.session = requests.Session()
        self.session.headers.update(USER_AGENT)

    def get(self, url: str) -> requests.Response:
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                last = exc
                status = getattr(getattr(exc, "response", None), "status_code", None)
                retryable = status in {403, 429, 500, 502, 503, 504} or status is None
                if attempt >= self.retries or not retryable:
                    raise
                if status in {403, 429}:
                    print(
                        f"publisher HTTP {status}; retry {attempt + 1}/{self.retries} "
                        f"after {self.backoff * (2**attempt):.1f}s",
                        flush=True,
                    )
                time.sleep(self.backoff * (2**attempt))
        assert last is not None
        raise last

    def kodex_map(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        seen: set[tuple[str, ...]] = set()
        page = 1
        while page <= 100:
            url = (
                "https://www.samsungfund.com/api/v1/kodex/product.do"
                f"?ordrColm=LIST_D&ordrSort=DESC&pageNo={page}&srchTerm=w&pageRows=100"
            )
            items = self.get(url).json()
            if not isinstance(items, list) or not items:
                break
            signature = tuple(str(item.get("fId") or "") for item in items)
            if signature in seen:
                break
            seen.add(signature)
            for item in items:
                if item.get("stkTicker") and item.get("fId"):
                    mapping[str(item["stkTicker"])] = str(item["fId"])
            total = max((int(item.get("totalCnt") or 0) for item in items), default=0)
            # The publisher currently caps the response at 20 even when
            # pageRows=100, so only totalCnt (not the returned page length)
            # is a reliable completion signal.
            if len(mapping) >= total:
                break
            page += 1
            time.sleep(self.pause)
        return mapping

    def rise_map(self, as_of: str) -> dict[str, str]:
        mapping: dict[str, str] = {}
        page = 1
        while page <= 60:
            url = f"https://www.riseetf.co.kr/prod/document/pdf?searchDate={as_of}&page={page}"
            text = self.get(url).text
            cards = text.split('class="card_type07"')[1:]
            if not cards:
                break
            before = len(mapping)
            for card in cards:
                title = re.search(r'<p class="title">(.*?)</p>', card, re.S | re.I)
                internal = re.search(r"searchTargetId=([0-9A-Za-z]+)", card)
                codes = (
                    re.findall(r"\(([0-9A-Z]{6})\)", re.sub(r"<[^>]+>", "", title.group(1)))
                    if title
                    else []
                )
                if codes and internal:
                    mapping[codes[-1]] = internal.group(1)
            if len(mapping) == before:
                break
            page += 1
            time.sleep(self.pause)
        return mapping

    def ace_map(self) -> dict[str, str]:
        payload = self.get("https://papi.aceetf.co.kr/api/funds?page=1&size=1000").json()
        return {
            str(item["stockCd"]): str(item["fundCd"])
            for item in (payload.get("data") or [])
            if item.get("stockCd") and item.get("fundCd")
        }


def load_targets(master: Path, brands: Iterable[str]) -> list[Target]:
    table = pd.read_csv(master, dtype=str, keep_default_na=False)
    required = {"pd_grp_no", "pd_abrv_nm", "pd_itm_no", "pd_itm_no_ma"}
    missing = sorted(required - set(table.columns))
    if missing:
        raise ValueError(f"master missing columns: {missing}")
    brand_set = set(brands)
    table = table.loc[table["pd_grp_no"].eq("ETF")].copy()
    table["brand"] = table["pd_abrv_nm"].str.split().str[0].str.upper()
    table = table.loc[table["brand"].isin(brand_set)]
    targets = [
        Target(
            row.brand,
            row.pd_itm_no,
            row.pd_itm_no_ma[1:],
            row.pd_abrv_nm,
            getattr(row, "pd_lste_dt", ""),
        )
        for row in table.sort_values(["brand", "pd_itm_no"], kind="stable").itertuples(index=False)
    ]
    if not targets:
        raise ValueError("master produced no collection targets")
    return targets


def source_url(brand: str, internal: str, as_of: str) -> str:
    dotted = as_of.replace("-", ".")
    compact = as_of.replace("-", "")
    if brand == "KODEX":
        return f"https://www.samsungfund.com/api/v1/kodex/product-pdf/{internal}.do?gijunYMD={dotted}"
    if brand == "TIGER":
        return (
            "https://investments.miraeasset.com/tigeretf/ko/product/search/detail/pdfListAjax.ajax"
            f"?ksdFund={internal}&fixDate={dotted}&pageIndex=1&firstIndex=0&listCnt=1000"
        )
    if brand == "RISE":
        return (
            "https://www.riseetf.co.kr/prod/document/pdf/listExcel"
            f"?searchTargetId={internal}&searchDate={as_of}"
        )
    if brand == "ACE":
        return f"https://papi.aceetf.co.kr/api/funds/{internal}/pdf?page=1&size=1000&std_dt={compact}"
    raise KeyError(brand)


def split_active_targets(targets: list[Target], as_of: str) -> tuple[list[Target], list[Target]]:
    compact_as_of = as_of.replace("-", "")
    inactive = [
        target
        for target in targets
        if re.fullmatch(r"\d{8}", target.last_trading_date or "")
        and target.last_trading_date <= compact_as_of
    ]
    inactive_set = set(inactive)
    return [target for target in targets if target not in inactive_set], inactive


def safe_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.resolve()
    lowered = tuple(part.lower() for part in resolved.parts)
    for suffix in (("data", "data"), ("data", "snapshots"), ("data", "archive")):
        if any(lowered[index : index + 2] == suffix for index in range(len(lowered) - 1)):
            raise ValueError(f"refusing to write into shared/immutable data tree: {resolved}")
    return resolved


def raw_path(output_dir: Path, target: Target, as_of: str) -> Path:
    return output_dir / "raw" / f"{target.brand.lower()}_{target.ticker}_{as_of.replace('-', '')}.{ADAPTERS[target.brand].extension}"


def load_resume(path: Path, target: Target, as_of: str) -> tuple[list[tuple[str, str, object]], dict] | None:
    sidecar = path.with_name(path.name + ".meta.json")
    if not path.is_file() or not sidecar.is_file():
        return None
    try:
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        body = path.read_bytes()
        if meta.get("as_of") != as_of or meta.get("isin") != target.isin:
            return None
        if meta.get("sha256") != sha256_bytes(body):
            return None
        rows, evidence = PARSERS[target.brand](body, as_of)
        if not rows or meta.get("holdings_count") != len(rows):
            return None
        meta["date_evidence"] = evidence
        return rows, meta
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def build_relation(records: list[tuple[Target, list[tuple[str, str, object]], dict]], as_of: str) -> pd.DataFrame:
    values: list[tuple[object, ...]] = []
    for target, rows, _meta in records:
        for code, name, weight in rows:
            values.append(
                (target.isin, code, code_type(code), name, weight, target.brand, as_of)
            )
    frame = pd.DataFrame(values, columns=RELATION_COLUMNS)
    if frame.empty:
        raise ValueError("validated responses produced zero holdings")
    frame["weight"] = pd.to_numeric(frame["weight"], errors="coerce")
    frame = frame.sort_values(
        ["pd_itm_no", "holding_code_raw", "holding_name", "weight"],
        kind="stable",
        na_position="last",
    ).reset_index(drop=True)
    if not frame["pd_itm_no"].str.startswith("KR").all() or not frame["as_of"].eq(as_of).all():
        raise ValueError("relation invariant failed")
    return frame


def collect(args: argparse.Namespace) -> int:
    output_dir = safe_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    brands = tuple(args.brand or BRAND_NAMES)
    all_targets = load_targets(args.master.resolve(), brands)
    targets, inactive_targets = split_active_targets(all_targets, args.as_of)
    if args.limit is not None:
        targets = [target for brand in brands for target in [x for x in targets if x.brand == brand][: args.limit]]

    client = Collector(args.timeout, args.retries, args.backoff, args.pause)
    maps: dict[str, dict[str, str] | None] = {}
    list_failures: dict[str, str] = {}
    for brand in brands:
        try:
            maps[brand] = {
                "KODEX": client.kodex_map,
                "RISE": lambda: client.rise_map(args.as_of),
                "ACE": client.ace_map,
            }.get(brand, lambda: None)()
        except Exception as exc:  # keep other publishers collectible
            maps[brand] = {}
            list_failures[brand] = f"{type(exc).__name__}: {exc}"

    started_at = utc_now()
    records: list[tuple[Target, list[tuple[str, str, object]], dict]] = []
    failures: list[dict[str, str]] = []
    anomalies: list[dict[str, object]] = []
    skipped = 0

    for position, target in enumerate(targets, 1):
        adapter = ADAPTERS[target.brand]
        path = raw_path(output_dir, target, args.as_of)
        resumed = load_resume(path, target, args.as_of) if args.resume else None
        if resumed is not None:
            rows, meta = resumed
            records.append((target, rows, meta))
            skipped += 1
            continue

        key = target.isin if adapter.key == "isin" else target.ticker
        id_map = maps[target.brand]
        internal = key if id_map is None else id_map.get(key)
        if not internal:
            failures.append(
                {"brand": target.brand, "ticker": target.ticker, "isin": target.isin, "name": target.name, "reason": "publisher mapping missing"}
            )
            continue
        url = source_url(target.brand, internal, args.as_of)
        try:
            response = client.get(url)
            body = response.content
            rows, evidence = PARSERS[target.brand](body, args.as_of)
            if not rows:
                raise ValueError("publisher returned zero holdings")
            meta = {
                "schema_version": 2,
                "source": adapter.source,
                "as_of": args.as_of,
                "retrieved_at": utc_now(),
                "url": url,
                "final_url": response.url,
                "http_status": response.status_code,
                "date_evidence": evidence,
                "isin": target.isin,
                "ticker": target.ticker,
                "name": target.name,
                "internal_id": internal,
                "holdings_count": len(rows),
                "sha256": sha256_bytes(body),
            }
            atomic_write(path, body)
            atomic_json(path.with_name(path.name + ".meta.json"), meta)
            records.append((target, rows, meta))
            weights = pd.to_numeric(pd.Series([row[2] for row in rows]), errors="coerce").sum()
            if weights < 95 or weights > 105:
                anomalies.append(
                    {"brand": target.brand, "ticker": target.ticker, "isin": target.isin, "weight_sum": round(float(weights), 6)}
                )
        except Exception as exc:
            failures.append(
                {"brand": target.brand, "ticker": target.ticker, "isin": target.isin, "name": target.name, "reason": f"{type(exc).__name__}: {exc}"}
            )
            print(
                f"FAIL {target.brand} {target.ticker}: {type(exc).__name__}: {exc}",
                flush=True,
            )
        if position % 25 == 0 or position == len(targets):
            print(f"[{position}/{len(targets)}] validated={len(records)} failures={len(failures)} resumed={skipped}", flush=True)
        time.sleep(args.pause)

    relation = build_relation(records, args.as_of)
    relation_path = output_dir / "etf_holding.csv"
    relation_bytes = relation.to_csv(index=False, encoding="utf-8", lineterminator="\n").encode("utf-8-sig")
    atomic_write(relation_path, relation_bytes)

    by_brand: dict[str, dict[str, int]] = {}
    for brand in brands:
        brand_targets = [target for target in targets if target.brand == brand]
        brand_records = [record for record in records if record[0].brand == brand]
        by_brand[brand] = {
            "target_products": len(brand_targets),
            "validated_products": len(brand_records),
            "failed_products": sum(item["brand"] == brand for item in failures),
            "holding_rows": int((relation["source"] == brand).sum()),
        }
    entries = {
        target.ticker: {
            "ticker": target.ticker,
            "isin": target.isin,
            "name": target.name,
            "source": meta["source"],
            "url": meta["url"],
            "as_of": meta["as_of"],
            "retrieved_at": meta["retrieved_at"],
            "date_evidence": meta["date_evidence"],
            "holdings_count": meta["holdings_count"],
            "raw_path": str(raw_path(output_dir, target, args.as_of).relative_to(output_dir)).replace("\\", "/"),
            "raw_sha256": meta["sha256"],
        }
        for target, _rows, meta in sorted(records, key=lambda item: item[0].ticker)
    }
    master_info = {
        "path": str(args.master.resolve()),
        "sha256": sha256_file(args.master.resolve()),
        "rows": int(len(pd.read_csv(args.master.resolve(), dtype=str, keep_default_na=False))),
    }
    manifest = {
        "schema_version": 2,
        "snapshot_as_of": args.as_of,
        "cutoff": "2026-08-24",
        "started_at": started_at,
        "completed_at": utc_now(),
        "master": master_info,
        "requested_brands": list(brands),
        "target_products": len(targets),
        "excluded_inactive_products": len(inactive_targets),
        "inactive_products": [
            {
                "brand": target.brand,
                "ticker": target.ticker,
                "isin": target.isin,
                "name": target.name,
                "last_trading_date": normalize_date(target.last_trading_date),
                "reason": "last trading date is on or before holdings snapshot date",
            }
            for target in inactive_targets
        ],
        "validated_products": len(records),
        "failed_products": len(failures),
        "resumed_products": skipped,
        "holding_rows": len(relation),
        "relation_path": relation_path.name,
        "relation_sha256": sha256_bytes(relation_bytes),
        "by_brand": by_brand,
        "publisher_list_failures": list_failures,
        "failures": failures,
        "weight_sum_anomalies": anomalies,
        "entries": entries,
    }
    atomic_json(output_dir / "etf_holdings_provenance.json", manifest)
    summary = {key: value for key, value in manifest.items() if key not in {"entries", "failures", "weight_sum_anomalies"}}
    summary["failure_count"] = len(failures)
    summary["weight_sum_anomaly_count"] = len(anomalies)
    atomic_json(output_dir / "collection_manifest.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.require_complete and failures:
        return 2
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--as-of", default="2026-08-21")
    parser.add_argument("--brand", action="append", choices=BRAND_NAMES)
    parser.add_argument("--limit", type=int, help="per-brand target limit for smoke tests")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--backoff", type=float, default=2.0)
    parser.add_argument("--pause", type=float, default=0.15)
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--require-complete", action=argparse.BooleanOptionalAction, default=False)
    args = parser.parse_args(argv)
    if normalize_date(args.as_of) != args.as_of:
        parser.error("--as-of must be YYYY-MM-DD")
    if args.as_of > "2026-08-24":
        parser.error("--as-of exceeds organizer cutoff 2026-08-24")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    return args


def main(argv: list[str] | None = None) -> int:
    return collect(parse_args(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    raise SystemExit(main())
