"""
SEC DERA 데이터셋에서 해외ETF 서술형 근거 청크를 만든다.

[왜]
해외ETF 5,972종은 문서 축이 0이다. DART 는 국내 공시라 구조적으로 커버가 안 되고,
RDB 에는 티커·총보수·AUM·기초지수'명' 같은 숫자와 코드만 있어 "이 ETF 는 어떤 전략으로
운용되고 무슨 위험이 있는가"에 답할 수 없다. 골드셋 7·28·29 번이 명시적으로
"전략 원문"과 "위험 설명의 문서 근거"를 요구한다.

[소스]
SEC DERA "Mutual Fund Prospectus Risk/Return Summary Data Sets".
분기별 ZIP 안의 `txt.tsv` 가 투자설명서의 서술 블록을 **XBRL 태깅된 평문**으로 담고 있다
(`value` 는 이미 텍스트 추출본이라 HTML 파싱이 필요 없다). 무인증이고
`/Archives/edgar/data` 는 robots.txt 가 명시적으로 Allow 한다.

[결합]
`txt.tsv` 의 `series` -> SEC `company_tickers_mf.json` 의 seriesId -> 티커 ->
`enriched.product_master.short_name` -> `product_id`(예: etf_gl:VOO.K).
실측 결합률: 우리 티커 6,031 중 SEC 매핑 4,695(77.8%), 2026q2 한 분기에서 1,096 series.

[cutoff]
`vec.source_document` / `vec.document_chunk` 는 `published_at <= 2026-08-24` 를 CHECK 로
강제한다. 여기서도 같은 기준으로 거른다 - DB 가 거부하기 전에 우리가 먼저 안 넣는다.

출력은 배포 번들과 같은 형식(mirae-vector-bundle-v1)의 JSONL 3종이다. 임베딩은
별도 단계(build_sec_etf_embeddings.py)에서 로컬 bge-m3 로 붙인다.

실행:
    python script/build_sec_etf_chunks.py --zip 2026q2_rr1.zip --out artifacts/sec_etf
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path

CUTOFF = date(2026, 8, 24)
REPO_ROOT = Path(__file__).resolve().parents[1]

# XBRL 태그 -> 우리 section_type. 기존 DART 청크가 쓰는 3종에 맞춘다.
TAG_SECTION = {
    "RiskTextBlock": "risk",
    "PrincipalRiskTextBlock": "risk",
    "StrategyNarrativeTextBlock": "objective_strategy",
    "ObjectivePrimaryTextBlock": "objective_strategy",
}

# 변액연금(N-4/N-6) 계약 서술이 같은 데이터셋에 섞여 있다. series 결합으로 대부분
# 걸러지지만, 명백한 계약 문구는 한 번 더 막는다.
CONTRACT_NOISE = re.compile(r"\b(the Contract|annuity contract|surrender charge)\b", re.I)

MIN_CHARS = 120
TARGET_CHARS = 1200
MAX_CHARS = 1800


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def clean(text: str) -> str:
    text = text.replace(" ", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\s*\n\s*", "\n", text).strip()


def split_chunks(text: str) -> list[str]:
    """문장 경계에서 자른다. 서술 블록은 중앙값 507자, 90%가 1,745자라
    대부분은 한 덩어리로 남고 긴 것만 쪼개진다."""
    text = clean(text)
    if len(text) <= MAX_CHARS:
        return [text] if len(text) >= MIN_CHARS else []

    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    buf = ""
    for sentence in sentences:
        if buf and len(buf) + len(sentence) + 1 > TARGET_CHARS:
            chunks.append(buf.strip())
            buf = sentence
        else:
            buf = f"{buf} {sentence}".strip()
    if buf.strip():
        chunks.append(buf.strip())
    return [c for c in chunks if len(c) >= MIN_CHARS]


def load_series_to_tickers(mf_path: Path) -> dict[str, list[str]]:
    """seriesId -> 그 series 에 속한 모든 티커.

    한 series 에 여러 share class 가 달린다. 예컨대 Vanguard 500 Index Fund
    (S000002839)에는 VFIAX(Admiral), VFINX(Investor), **VOO**(ETF)가 함께 있다.
    먼저 만난 것 하나만 잡으면 뮤추얼펀드 클래스가 ETF 티커를 가려 버려서
    VOO·BND·VTI 같은 대형 ETF 가 통째로 누락된다(실측으로 확인). 그래서 전부
    모아 두고, 매칭 시점에 **우리 상품 목록에 있는 티커**를 고른다.
    """
    payload = json.loads(mf_path.read_text(encoding="utf-8"))
    mapping: dict[str, list[str]] = {}
    for row in payload.get("data", []):
        if len(row) > 3 and row[1] and row[3]:
            mapping.setdefault(str(row[1]).strip(), []).append(str(row[3]).strip().upper())
    return mapping


def read_submissions(zf: zipfile.ZipFile) -> dict[str, dict]:
    with zf.open("sub.tsv") as handle:
        reader = csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8", errors="replace"), delimiter="\t")
        return {row["adsh"]: row for row in reader if row.get("adsh")}


def archive_url(cik: str, adsh: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh.replace('-', '')}/{adsh}-index.htm"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SEC DERA -> 해외ETF 서술 청크")
    parser.add_argument("--zip", dest="zips", action="append", required=True, type=Path,
                        help="DERA 분기 ZIP (여러 번 지정 가능)")
    parser.add_argument("--mf-map", type=Path, required=True, help="company_tickers_mf.json")
    parser.add_argument("--product-map", type=Path, required=True, help="{티커: product_id} JSON")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    csv.field_size_limit(10 ** 9)

    series_to_tickers = load_series_to_tickers(args.mf_map)
    ticker_to_pid = {k.upper(): v for k, v in json.loads(args.product_map.read_text(encoding="utf-8")).items()}
    print(f"series->tickers {len(series_to_tickers):,} / ticker->product_id {len(ticker_to_pid):,}")

    def resolve(series_id: str) -> tuple[str, str] | None:
        """series 의 여러 클래스 중 우리 해외ETF 목록에 있는 티커를 고른다."""
        for candidate in series_to_tickers.get(series_id, ()):
            product_id = ticker_to_pid.get(candidate)
            if product_id:
                return candidate, product_id
        return None

    documents: dict[str, dict] = {}
    doc_products: set[tuple[str, str]] = set()
    chunks: list[dict] = []
    seen_hashes: set[str] = set()
    stats = Counter()

    for zip_path in args.zips:
        if not zip_path.exists():
            print(f"건너뜀(없음): {zip_path}", file=sys.stderr)
            continue
        zf = zipfile.ZipFile(zip_path)
        subs = read_submissions(zf)
        print(f"{zip_path.name}: 제출 {len(subs):,}건")

        ordinal_by_doc: Counter = Counter()
        with zf.open("txt.tsv") as handle:
            reader = csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8", errors="replace"), delimiter="\t")
            for row in reader:
                section = TAG_SECTION.get(row.get("tag", ""))
                if not section:
                    continue
                stats["tag_match"] += 1

                series_id = (row.get("series") or "").strip()
                if series_id not in series_to_tickers:
                    stats["no_series_match"] += 1
                    continue
                resolved = resolve(series_id)
                if not resolved:
                    stats["not_our_product"] += 1
                    continue
                ticker, product_id = resolved

                sub = subs.get(row.get("adsh", ""))
                if not sub:
                    stats["no_submission"] += 1
                    continue

                filed = (sub.get("filed") or "").strip()
                if len(filed) != 8 or not filed.isdigit():
                    stats["bad_filed"] += 1
                    continue
                published = date(int(filed[:4]), int(filed[4:6]), int(filed[6:]))
                if published > CUTOFF:
                    stats["after_cutoff"] += 1
                    continue

                value = row.get("value") or ""
                if CONTRACT_NOISE.search(value[:400]):
                    stats["contract_noise"] += 1
                    continue

                adsh = sub["adsh"]
                document_id = f"prospectus:sec:{adsh}"
                url = archive_url(sub["cik"], adsh)
                if document_id not in documents:
                    documents[document_id] = {
                        "document_id": document_id,
                        "title": f"{sub.get('name', '')} {sub.get('form', '')} ({adsh})".strip(),
                        "publisher": sub.get("name", ""),
                        "published_at": published.isoformat(),
                        "source_url": url,
                        "source_hash": sha256(f"{adsh}|{sub.get('cik')}|{filed}"),
                        "source_type": "sec_edgar_dera_rr",
                        "as_of": published.isoformat(),
                    }
                doc_products.add((document_id, product_id))

                for piece in split_chunks(value):
                    embedding_text = f"[{section}] {ticker}\n{piece}"
                    content_hash = sha256(embedding_text)
                    if content_hash in seen_hashes:
                        stats["duplicate_chunk"] += 1
                        continue
                    seen_hashes.add(content_hash)
                    ordinal_by_doc[document_id] += 1
                    chunks.append({
                        "chunk_id": f"chunk:{content_hash[:32]}",
                        "document_id": document_id,
                        "section_type": section,
                        "chunk_ordinal": ordinal_by_doc[document_id],
                        "heading_path": [row.get("tag", "")],
                        "page_number": None,
                        "citation_text": f"{sub.get('name','')} {sub.get('form','')} ({ticker}) > {row.get('tag','')}",
                        "chunk_text": piece,
                        "embedding_text": embedding_text,
                        "published_at": published.isoformat(),
                        "effective_as_of": published.isoformat(),
                        "source_url": url,
                        "content_hash": content_hash,
                    })
                    stats["chunk"] += 1

    args.out.mkdir(parents=True, exist_ok=True)

    def dump(name: str, rows) -> None:
        path = args.out / name
        with io.open(path, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"  {name}: {len(rows):,}행")

    dump("source_documents.jsonl", list(documents.values()))
    dump("product_documents.jsonl",
         [{"document_id": d, "product_id": p, "relation_type": "prospectus"} for d, p in sorted(doc_products)])
    dump("document_chunks.jsonl", chunks)

    products = {p for _, p in doc_products}
    summary = {
        "cutoff": CUTOFF.isoformat(),
        "sources": [z.name for z in args.zips],
        "documents": len(documents),
        "products_covered": len(products),
        "chunks": len(chunks),
        "sections": dict(Counter(c["section_type"] for c in chunks)),
        "filtered": dict(stats),
    }
    (args.out / "build_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"\n문서 {len(documents):,} / 상품 {len(products):,} / 청크 {len(chunks):,}")
    print("섹션:", summary["sections"])
    print("필터:", dict(stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
