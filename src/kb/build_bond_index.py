# -*- coding: utf-8 -*-
"""채권 스키마 TTL → pgvector 인덱스.

    python3 kb/build_bond_index.py

TTL을 일반 문서처럼 자르지 않는다. resource 1개 = vector 1개다.
각 resource에서 URI · rdfs:label · skos:altLabel · rdfs:comment 를 읽어 한 줄로 만든다.

    fp:riskGradeLevel | 위험등급 수준 | 1=최고위험 … 6=최저위험.

주석(rdfs:comment)이 없는 resource는 넣지 않는다. 이 인덱스의 목적은 "안전한" 같은 말을
fp: 용어로 번역하는 것이고, 번역 근거가 되는 게 주석이기 때문이다. 또 답변 단계
(agent/nodes.py)가 "comment 안에 적힌 문장만 근거로 삼는다"고 규정하므로, 주석 없는
용어는 검색에 걸려도 근거로 쓸 수 없고 Top-K 슬롯만 차지한다.

  ※ 주석 없는 코드리스트 개체 91건을 넣어 본 실측 결과는
     vectordb_test/3_baseline_130_v2/baseline_130_v2_report.md 에 있다.
     Top-1 -9, 근거 커버리지 100% → 68.6% 로 나빠져 현재 형태로는 넣지 않기로 했다.

저장소는 PostgreSQL + pgvector 다(FAISS 에서 이전). 벡터는 정규화하지 않고 원본을 넣는다 —
cosine 연산자(<=>)가 내부에서 처리하므로 결과가 같고, 정규화 단계가 하나 줄어든다.
"""
import json
import sys
import time
from pathlib import Path

import psycopg
from rdflib import RDFS, Graph, Namespace, URIRef

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (ARTIFACTS, BOND_DSN, BOND_TABLE, BOND_TTL_PATHS,  # noqa: E402
                    EMBED_DIM)
import clova  # noqa: E402

FP = Namespace("http://mafest.ai/product#")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")
TERMS_JSON = ARTIFACTS / "bond_terms.json"      # 측정 하네스(vectordb_test)가 읽는 교환 파일


def pick(g, s, prop, lang="ko"):
    """같은 프로퍼티에 여러 언어가 있으면 한국어 우선."""
    vals = list(g.objects(s, prop))
    if not vals:
        return ""
    ko = [str(v) for v in vals if getattr(v, "language", None) == lang]
    return (ko or [str(v) for v in vals])[0]


def collect():
    """주석 있는 fp: resource 를 URI 정렬 순서로 모은다.

    정렬은 재현성 때문이다 — rdflib 의 subjects() 순서는 비결정적이라, 정렬하지 않으면
    재빌드마다 적재 순서가 달라져 diff 가 무의미해진다. 다만 순서가 식별자는 아니다.
    pgvector 는 term_uri 가 PK 이므로 순서가 바뀌어도 검색 결과는 같다.
    """
    g = Graph()
    for p in BOND_TTL_PATHS:
        g.parse(p, format="turtle")
    subs = {s for s in g.subjects(RDFS.comment, None)
            if isinstance(s, URIRef) and str(s).startswith(str(FP))}
    terms = []
    for s in sorted(subs, key=str):
        uri = f"fp:{str(s).split('#')[-1]}"
        label = pick(g, s, RDFS.label)
        comment = pick(g, s, RDFS.comment)
        alts = sorted(str(o) for o in g.objects(s, SKOS.altLabel))
        # altLabel 을 검색 텍스트에 넣는다. 사용자는 '무등급'이라 쓰고 라벨은 'NotRated'인 경우가 있다.
        text = " | ".join(x for x in [uri, label, " / ".join(alts), comment] if x)
        terms.append({"term_uri": uri, "label": label, "comment": comment,
                      "alt_labels": alts, "text": text})
    return terms


def main():
    t0 = time.time()
    terms = collect()
    print(f"resource {len(terms)}개 수집 ({', '.join(p.name for p in BOND_TTL_PATHS)})")

    vecs = clova.embed_many([t["text"] for t in terms])
    if len(vecs) != len(terms):
        sys.exit(f"FAIL 임베딩 개수 불일치: {len(vecs)} vs {len(terms)}")
    if len(vecs[0]) != EMBED_DIM:
        sys.exit(f"FAIL 차원 불일치: {len(vecs[0])} (기대 {EMBED_DIM})")

    with psycopg.connect(BOND_DSN, autocommit=True) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute(f"DROP TABLE IF EXISTS {BOND_TABLE}")
        conn.execute(f"""
            CREATE TABLE {BOND_TABLE} (
                term_uri   text PRIMARY KEY,
                label      text NOT NULL,
                comment    text NOT NULL,
                alt_labels text[] NOT NULL DEFAULT '{{}}',
                content    text NOT NULL,
                embedding  vector({EMBED_DIM}) NOT NULL
            )""")
        with conn.cursor() as cur:
            cur.executemany(
                f"INSERT INTO {BOND_TABLE}"
                " (term_uri,label,comment,alt_labels,content,embedding)"
                " VALUES (%s,%s,%s,%s,%s,%s::vector)",
                [(t["term_uri"], t["label"], t["comment"], t["alt_labels"], t["text"],
                  str(list(map(float, v)))) for t, v in zip(terms, vecs)])

        n, dim, nulls = conn.execute(
            f"SELECT count(*), max(vector_dims(embedding)), count(*) FILTER"
            f" (WHERE embedding IS NULL) FROM {BOND_TABLE}").fetchone()

    if n != len(terms) or dim != EMBED_DIM or nulls:
        sys.exit(f"FAIL 적재 검증: {n}행 / {dim}차원 / NULL {nulls}")

    ARTIFACTS.mkdir(exist_ok=True)
    TERMS_JSON.write_text(json.dumps(terms, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"  {BOND_TABLE:20s} {n}행 × {dim}차원  (NULL {nulls})")
    print(f"  {TERMS_JSON.name:20s} {TERMS_JSON.stat().st_size/1024:.0f}KB")
    print(f"소요 {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
