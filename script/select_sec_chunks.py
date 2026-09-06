"""
SEC 청크에서 실제로 적재할 것만 골라낸다.

[왜 전량이 아닌가]
2026q2 한 분기만으로 청크가 39,755개 나오는데, 로컬 CPU bge-m3 처리량이 약
1.1 chunks/s 라 전량 임베딩에 10시간이 걸린다. 그리고 팀의 근거문서 계획서가
이미 같은 결론을 내려 뒀다 - "AUM 상위 N 전략은 실패한다. 질의 지향 + 얇은 광역의
2층으로 가라". 커버리지 비율은 목표가 아니고, **평가 문항이 물을 상품**이 목표다.

[선별 기준]
1층(깊이) - 골드셋이 이름을 직접 부른 티커. 없으면 그 문항은 확정 실패다.
2층(넓이) - AUM 상위 N. 비공개 평가문항 대비.
그리고 상품당 청크 수를 캡한다. 위험 공시는 운용사별 정형 문구가 많아
같은 상품에서 수십 개를 넣어도 검색 품질이 비례해 오르지 않는다.

`objective_strategy` 를 `risk` 보다 우선 채운다. 전략·목적 서술이 상품마다
고유해서 검색 변별력이 높고, 골드셋 7·28·29 번이 요구하는 "전략 원문"에 직접
대응하기 때문이다.

실행:
    python script/select_sec_chunks.py --in artifacts/sec_etf --out artifacts/sec_etf_selected \\
        --tickers-file aum_top.txt --must-have VOO,IVV,BND,QQQ --per-product 12
"""
from __future__ import annotations

import argparse
import io
import json
from collections import Counter, defaultdict
from pathlib import Path

# 같은 상품 안에서 이 순서로 채운다. 전략·목적이 위험 공시보다 변별력이 높다.
SECTION_PRIORITY = {"objective_strategy": 0, "risk": 1}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in io.open(path, encoding="utf-8") if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SEC 청크 선별")
    parser.add_argument("--in", dest="src", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--tickers-file", type=Path,
                        help="줄바꿈 구분 티커 목록(AUM 상위 등). 없으면 전체 대상")
    parser.add_argument("--must-have", default="",
                        help="쉼표 구분. 골드셋이 직접 지목한 티커 - 상한과 무관하게 반드시 포함")
    parser.add_argument("--top", type=int, default=200, help="tickers-file 에서 상위 몇 개까지")
    parser.add_argument("--per-product", type=int, default=12, help="상품당 최대 청크")
    args = parser.parse_args(argv)

    chunks = read_jsonl(args.src / "document_chunks.jsonl")
    documents = {d["document_id"]: d for d in read_jsonl(args.src / "source_documents.jsonl")}
    links = read_jsonl(args.src / "product_documents.jsonl")

    doc_to_products = defaultdict(list)
    for link in links:
        doc_to_products[link["document_id"]].append(link["product_id"])

    must = {t.strip().upper() for t in args.must_have.split(",") if t.strip()}
    wanted: set[str] | None = None
    if args.tickers_file and args.tickers_file.exists():
        listed = [t.strip().upper() for t in args.tickers_file.read_text(encoding="utf-8").split("\n") if t.strip()]
        wanted = set(listed[: args.top]) | must

    def ticker_of(product_id: str) -> str:
        # product_id 는 etf_gl:VOO 또는 etf_gl:AAAA.K 형태다. RIC 접미사를 떼어낸다.
        tail = product_id.split(":", 1)[-1]
        return tail.split(".")[0].upper()

    # 청크를 상품에 붙인다. 한 문서가 여러 상품(클래스)에 걸리면 각각에 센다.
    per_product: dict[str, list[dict]] = defaultdict(list)
    for chunk in chunks:
        for product_id in doc_to_products.get(chunk["document_id"], []):
            if wanted is not None and ticker_of(product_id) not in wanted:
                continue
            per_product[product_id].append(chunk)

    selected: dict[str, dict] = {}
    kept_links: set[tuple[str, str]] = set()
    stats = Counter()
    for product_id, rows in per_product.items():
        cap = args.per_product
        if ticker_of(product_id) in must:
            cap = max(cap, args.per_product * 2)  # 지목 문항은 근거를 넉넉히
            stats["must_have_product"] += 1

        # 섹션을 번갈아 채운다. 우선순위대로만 뽑으면 objective_strategy 가
        # 상한을 다 먹어 risk 가 거의 안 남는데, 골드셋 28·29 번이 위험 비교를
        # 요구하므로 두 섹션이 모두 있어야 한다.
        by_section: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            by_section[row["section_type"]].append(row)
        for bucket in by_section.values():
            bucket.sort(key=lambda r: r["chunk_ordinal"])
        order = sorted(by_section, key=lambda s: SECTION_PRIORITY.get(s, 9))
        interleaved: list[dict] = []
        index = 0
        while len(interleaved) < cap and any(index < len(by_section[s]) for s in order):
            for section in order:
                if index < len(by_section[section]) and len(interleaved) < cap:
                    interleaved.append(by_section[section][index])
            index += 1
        rows = interleaved

        for row in rows[:cap]:
            selected[row["chunk_id"]] = row
            kept_links.add((row["document_id"], product_id))
        stats["product"] += 1
        stats["dropped_chunks"] += max(0, len(rows) - cap)

    kept_chunks = list(selected.values())
    kept_docs = [documents[d] for d, _ in sorted(kept_links) if d in documents]
    seen: set[str] = set()
    kept_docs = [d for d in kept_docs if not (d["document_id"] in seen or seen.add(d["document_id"]))]

    write_jsonl(args.out / "document_chunks.jsonl", kept_chunks)
    write_jsonl(args.out / "source_documents.jsonl", kept_docs)
    write_jsonl(args.out / "product_documents.jsonl",
                [{"document_id": d, "product_id": p, "relation_type": "prospectus"}
                 for d, p in sorted(kept_links)])

    summary = {
        "source_chunks": len(chunks),
        "selected_chunks": len(kept_chunks),
        "products": stats["product"],
        "must_have_products": stats["must_have_product"],
        "documents": len(kept_docs),
        "per_product_cap": args.per_product,
        "sections": dict(Counter(c["section_type"] for c in kept_chunks)),
    }
    (args.out / "select_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"원본 {len(chunks):,} -> 선별 {len(kept_chunks):,} 청크")
    print(f"상품 {stats['product']:,} (지목 {stats['must_have_product']}) / 문서 {len(kept_docs):,}")
    print("섹션:", summary["sections"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
