"""
SEC 번들에 `product_coverage` 대장을 만들어 붙인다.

[왜 필요한가]
`vec.product_coverage` 는 상품마다 "문서를 확보했는가, 못 했다면 왜"를 기록하는
대장이고, `tools/vector_search.get_coverage()` 가 이걸 읽어 에이전트가
"이 상품은 문서가 없다"를 판단한다. 문서·청크만 넣고 대장을 갱신하지 않으면
**문서는 들어갔는데 에이전트가 있는 줄 모르는** 상태가 된다.

[status 값]
기존 CHECK 에는 SEC 출처에 해당하는 값이 없다. matched_manager 는 "운용사 공시와
일치", matched_dart 는 "DART 일치"라 둘 다 사실과 다르다. 대장은 출처를 정확히
남기는 자리이므로 `matched_sec` 을 새로 쓴다.
**적용 전에 deploy/vector_sec 의 status CHECK 확장 마이그레이션이 선행되어야 한다.**

[한 상품에 문서가 여러 개일 때]
`product_coverage` 의 PK 는 product_id 라 상품당 한 행이다. 가장 최근 발행
문서를 대표로 건다 - 서술형 근거는 최신본이 현재 상태를 반영하기 때문이다.

실행:
    python script/build_sec_coverage.py --bundle artifacts/sec_etf_selected
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from collections import defaultdict
from pathlib import Path

CUTOFF = "2026-08-24"
STATUS = "matched_sec"
SOURCE_ROUTE = "SEC"
REASON = "SEC EDGAR DERA 투자설명서 서술 확보 (RiskTextBlock/StrategyNarrative)"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in io.open(path, encoding="utf-8") if line.strip()]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with io.open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SEC 번들 커버리지 대장 생성")
    parser.add_argument("--bundle", required=True, type=Path)
    # source_run_id 는 NOT NULL 이다. 기존 값이 'dart-prospectus-20260901' 같은
    # 슬러그라 같은 관례를 따른다.
    parser.add_argument("--run-id", default="sec-edgar-dera-20260906")
    args = parser.parse_args(argv)

    docs = {d["document_id"]: d for d in read_jsonl(args.bundle / "source_documents.jsonl")}
    links = read_jsonl(args.bundle / "product_documents.jsonl")

    by_product: dict[str, list[str]] = defaultdict(list)
    for link in links:
        by_product[link["product_id"]].append(link["document_id"])

    rows = []
    for product_id, doc_ids in sorted(by_product.items()):
        # 가장 최근 발행 문서를 대표로 건다.
        best = max(doc_ids, key=lambda d: docs.get(d, {}).get("published_at", ""))
        as_of = docs.get(best, {}).get("published_at", "")
        if not as_of or as_of > CUTOFF:
            # CHECK(as_of <= cutoff) 를 DB 가 거부하기 전에 우리가 먼저 거른다.
            continue
        rows.append({
            "product_id": product_id,
            "status": STATUS,
            "reason": REASON,
            "as_of": as_of,
            "source_run_id": args.run_id,
            "document_id": best,
            "source_route": SOURCE_ROUTE,
        })

    out_path = args.bundle / "product_coverage.jsonl"
    with io.open(out_path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"product_coverage.jsonl: {len(rows):,}행  (status={STATUS}, route={SOURCE_ROUTE})")

    # manifest 를 갱신해 새 파일도 counts/bytes/sha256 에 포함시킨다.
    manifest_path = args.bundle / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        name = out_path.name
        manifest.setdefault("counts", {})[name] = len(rows)
        manifest.setdefault("bytes", {})[name] = out_path.stat().st_size
        manifest.setdefault("sha256", {})[name] = file_sha256(out_path)
        manifest["requires_migration"] = "deploy/vector_sec/001_add_matched_sec_status.sql"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
            encoding="utf-8")
        print(f"manifest 갱신: {name} 등록 + requires_migration 표기")
    else:
        print("manifest.json 없음 - 갱신 생략")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
