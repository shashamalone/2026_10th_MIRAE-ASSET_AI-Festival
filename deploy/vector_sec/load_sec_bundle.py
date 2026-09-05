"""
SEC 해외ETF 번들을 vec 스키마에 **증분** 적재한다.

[기존 배포 경로와 다른 점]
`deploy/vector_v1/vector_ops.py` 는 번들 7종을 전량 재적재하는 풀 배포기다. 여기서는
기존 9,055 청크를 건드리지 않고 SEC 분량만 추가한다. 그래서 `bond_schema_terms` /
`schema_terms_all`(TBox) 은 요구하지 않는다.

[적재 순서 — FK 의존]
    source_document          (독립)
    chunk_embedding          (독립)
      -> document_chunk      (document_id FK, (content_hash,model,revision) FK)
    document_product         (document_id FK)
    product_coverage         (document_id FK)

[멱등]
전부 ON CONFLICT DO NOTHING 이다. 같은 번들을 두 번 넣어도 행이 늘지 않는다.
중간에 끊겨도 다시 돌리면 된다.

[product_coverage]
`status='matched_sec'` 은 기존 CHECK 에 없다. 마이그레이션이 선행되지 않았으면
이 단계만 건너뛰고 나머지는 정상 적재한 뒤, 무엇이 남았는지 보고한다.
(문서·청크는 들어가고 대장만 비는 상태가 된다 - 검색은 되지만 커버리지 감사는
SEC 분량을 모른다.)

환경변수:
    ADMIN_DATABASE_URL   쓰기 권한 DSN. 없으면 DATABASE_URL.
                         예: postgresql://agent_admin:PW@127.0.0.1:5432/financial_agent

실행:
    python load_sec_bundle.py --bundle ./bundle --dry-run
    python load_sec_bundle.py --bundle ./bundle
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import sys
from datetime import date
from pathlib import Path

CUTOFF = date(2026, 8, 24)
MODEL_LABEL = "bge-m3"
MODEL_REVISION = "b28ce2a6fcc9c75ef1c0619575d0ec19af760082"
DIMENSION = 1024
LOCK_KEY = 1_082_026_083_2  # vector_ops.py 의 키와 겹치지 않게 끝자리만 다르게
NORM_MIN, NORM_MAX = 0.999, 1.001

REQUIRED = ("source_documents.jsonl", "chunk_embeddings.jsonl",
            "document_chunks.jsonl", "product_documents.jsonl")
OPTIONAL = ("product_coverage.jsonl",)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in io.open(path, encoding="utf-8") if line.strip()]


def die(message: str) -> None:
    print(f"[중단] {message}", file=sys.stderr)
    raise SystemExit(1)


def validate(bundle: Path) -> dict[str, list[dict]]:
    data: dict[str, list[dict]] = {}
    for name in REQUIRED:
        path = bundle / name
        if not path.exists():
            die(f"필수 파일 없음: {name}")
        data[name] = read_jsonl(path)
    for name in OPTIONAL:
        path = bundle / name
        data[name] = read_jsonl(path) if path.exists() else []

    # 기준일: DB CHECK 가 거부하기 전에 우리가 먼저 잡는다.
    for name in ("source_documents.jsonl", "document_chunks.jsonl"):
        bad = [r for r in data[name]
               if date.fromisoformat(r["published_at"]) > CUTOFF]
        if bad:
            die(f"{name}: 기준일 {CUTOFF} 초과 {len(bad)}건")

    # DB 가 NOT NULL 로 막는 컬럼은 여기서 먼저 잡는다. 적재 도중 터지면
    # 트랜잭션이 통째로 롤백되어 어디까지 갔는지 파악이 어렵다.
    for row in data["chunk_embeddings.jsonl"]:
        if not row.get("embedding_text"):
            die(f"embedding_text 비어 있음 ({row.get('content_hash','?')[:12]})")
    for row in data["product_coverage.jsonl"]:
        if not row.get("source_run_id"):
            die(f"source_run_id 비어 있음 ({row.get('product_id','?')}) - NOT NULL 컬럼이다")

    # 임베딩: 차원·정규화·리비전. 여기가 어긋나면 검색이 조용히 망가진다.
    for row in data["chunk_embeddings.jsonl"]:
        vector = row["embedding"]
        if len(vector) != DIMENSION:
            die(f"차원 불일치 {len(vector)} != {DIMENSION} ({row['content_hash'][:12]})")
        norm = math.sqrt(sum(v * v for v in vector))
        if not NORM_MIN <= norm <= NORM_MAX:
            die(f"정규화 위반 norm={norm:.6f} ({row['content_hash'][:12]})")
        if row.get("model_revision") != MODEL_REVISION:
            die(f"리비전 불일치 {row.get('model_revision')} != {MODEL_REVISION}")
        if row.get("embedding_model") != MODEL_LABEL:
            die(f"모델명 불일치 {row.get('embedding_model')}")

    # 청크가 참조하는 임베딩과 문서가 번들 안에 다 있는지.
    hashes = {r["content_hash"] for r in data["chunk_embeddings.jsonl"]}
    docs = {r["document_id"] for r in data["source_documents.jsonl"]}
    missing_h = {c["content_hash"] for c in data["document_chunks.jsonl"]} - hashes
    missing_d = {c["document_id"] for c in data["document_chunks.jsonl"]} - docs
    if missing_h:
        die(f"임베딩 누락 {len(missing_h)}건")
    if missing_d:
        die(f"문서 누락 {len(missing_d)}건")

    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SEC 번들 증분 적재")
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true", help="검증만 하고 쓰지 않는다")
    args = parser.parse_args(argv)

    data = validate(args.bundle)
    print("검증 통과")
    for name in REQUIRED + OPTIONAL:
        print(f"  {name}: {len(data[name]):,}행")

    if args.dry_run:
        print("\n--dry-run: DB 에 쓰지 않고 종료")
        return 0

    import psycopg  # noqa: PLC0415
    from psycopg.rows import dict_row  # noqa: PLC0415

    conninfo = os.environ.get("ADMIN_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not conninfo:
        die("ADMIN_DATABASE_URL 또는 DATABASE_URL 이 필요하다")

    with psycopg.connect(conninfo, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
            cur.execute("SELECT current_user AS u")
            print(f"\n접속 계정: {cur.fetchone()['u']}")

            cur.execute("SELECT count(*) AS n FROM vec.document_chunk")
            before_chunks = cur.fetchone()["n"]
            cur.execute("SELECT count(*) AS n FROM vec.product_coverage")
            before_cov = cur.fetchone()["n"]
            print(f"적재 전: document_chunk {before_chunks:,} / product_coverage {before_cov:,}")

            cur.executemany(
                """INSERT INTO vec.source_document
                   (document_id,title,publisher,published_at,source_url,source_hash,source_type,as_of)
                   VALUES (%(document_id)s,%(title)s,%(publisher)s,%(published_at)s,
                           %(source_url)s,%(source_hash)s,%(source_type)s,%(as_of)s)
                   ON CONFLICT (document_id) DO NOTHING""",
                data["source_documents.jsonl"])
            print(f"  source_document      +{cur.rowcount if cur.rowcount and cur.rowcount>0 else 0}")

            # embedding_text 는 NOT NULL 이다. 번들에는 있는데 초기 구현이
            # INSERT 컬럼 목록에서 빠뜨려 NotNullViolation 이 났다(실측).
            cur.executemany(
                """INSERT INTO vec.chunk_embedding
                   (content_hash,embedding_text,embedding_model,model_revision,
                    embedding_dim,embedding)
                   VALUES (%(content_hash)s,%(embedding_text)s,%(embedding_model)s,
                           %(model_revision)s,%(embedding_dim)s,%(embedding)s)
                   ON CONFLICT (content_hash,embedding_model,model_revision) DO NOTHING""",
                [{**r, "embedding": str(r["embedding"])} for r in data["chunk_embeddings.jsonl"]])

            cur.executemany(
                """INSERT INTO vec.document_chunk
                   (chunk_id,document_id,section_type,chunk_ordinal,heading_path,page_number,
                    citation_text,chunk_text,published_at,effective_as_of,source_url,
                    content_hash,embedding_model,model_revision)
                   VALUES (%(chunk_id)s,%(document_id)s,%(section_type)s,%(chunk_ordinal)s,
                           %(heading_path)s,%(page_number)s,%(citation_text)s,%(chunk_text)s,
                           %(published_at)s,%(effective_as_of)s,%(source_url)s,
                           %(content_hash)s,%(embedding_model)s,%(model_revision)s)
                   ON CONFLICT (chunk_id) DO NOTHING""",
                [{**c,
                  "heading_path": " > ".join(c.get("heading_path") or []),
                  "embedding_model": MODEL_LABEL,
                  "model_revision": MODEL_REVISION}
                 for c in data["document_chunks.jsonl"]])

            cur.executemany(
                """INSERT INTO vec.document_product (document_id,product_id,relation_type)
                   VALUES (%(document_id)s,%(product_id)s,%(relation_type)s)
                   ON CONFLICT (document_id,product_id,relation_type) DO NOTHING""",
                data["product_documents.jsonl"])

            coverage_done = False
            if data["product_coverage.jsonl"]:
                cur.execute("""SELECT pg_get_constraintdef(oid) AS d FROM pg_constraint
                               WHERE conname = 'product_coverage_status_check'""")
                row = cur.fetchone()
                if row and "matched_sec" in row["d"]:
                    cur.executemany(
                        """INSERT INTO vec.product_coverage
                           (product_id,status,reason,as_of,source_run_id,document_id,source_route)
                           VALUES (%(product_id)s,%(status)s,%(reason)s,%(as_of)s,
                                   %(source_run_id)s,%(document_id)s,%(source_route)s)
                           ON CONFLICT (product_id) DO UPDATE SET
                             status=EXCLUDED.status, reason=EXCLUDED.reason,
                             as_of=EXCLUDED.as_of, document_id=EXCLUDED.document_id,
                             source_route=EXCLUDED.source_route""",
                        data["product_coverage.jsonl"])
                    coverage_done = True
                else:
                    print("\n  [건너뜀] product_coverage — status CHECK 에 matched_sec 이 없다.")
                    print("           마이그레이션 적용 후 이 스크립트를 다시 돌리면 대장만 채워진다.")

            cur.execute("SELECT count(*) AS n FROM vec.document_chunk")
            after_chunks = cur.fetchone()["n"]
            cur.execute("SELECT count(*) AS n FROM vec.product_coverage")
            after_cov = cur.fetchone()["n"]
            cur.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
        conn.commit()

    print(f"\n적재 후: document_chunk {after_chunks:,} (+{after_chunks-before_chunks:,})")
    print(f"         product_coverage {after_cov:,} (+{after_cov-before_cov:,})"
          f"{'' if coverage_done else '  ← 대장 미적재'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
