#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TBox 5개 TTL → 평가 전용 pgvector 인덱스 (schema_terms_all).

    python3 build_tbox_index.py

운영 인덱스(bond_schema_terms, 채권+common 130건)는 건드리지 않는다. 별도 테이블을
쓰는 이유는 둘이다.

  1. 운영 인덱스는 gold concept 을 전량 커버하는 문항이 12/35 뿐이라 A/B 가 무의미하다.
     5개 TTL 을 다 넣으면 188건이 되고 커버리지가 33/35 로 오른다(나머지 2건은 gold 오타였다).
  2. 인덱스 구성을 바꾸면 검색 품질이 통째로 흔들린다. 주석 없는 코드리스트 91건을
     넣었다가 근거 커버리지가 100% → 68.6% 로 무너진 전례가 있다
     (vectordb_test/3_baseline_130_v2/baseline_130_v2_report.md).
     평가 때문에 운영 경로를 흔들지 않는다.

수집 규칙은 src/kb/build_bond_index.py 와 같다 — resource 1개 = vector 1개,
rdfs:comment 가 없는 resource 는 넣지 않는다.
"""
import sys
import time
from pathlib import Path

import psycopg
from rdflib import RDFS, Graph, Namespace, URIRef

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
from config import BOND_DSN, EMBED_DIM  # noqa: E402
import clova  # noqa: E402

FP = Namespace("http://mafest.ai/product#")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")
TTLS = [ROOT / "ontology" / f for f in
        ("common.ttl", "bond_kr.ttl", "etf_kr.ttl", "etf_gl.ttl", "fund_pub.ttl")]
TABLE = "schema_terms_all"


def pick(g, s, prop, lang="ko"):
    vals = list(g.objects(s, prop))
    if not vals:
        return ""
    ko = [str(v) for v in vals if getattr(v, "language", None) == lang]
    return (ko or [str(v) for v in vals])[0]


def collect():
    g = Graph()
    for p in TTLS:
        g.parse(p, format="turtle")
    subs = {s for s in g.subjects(RDFS.comment, None)
            if isinstance(s, URIRef) and str(s).startswith(str(FP))}
    terms = []
    for s in sorted(subs, key=str):      # 정렬은 재빌드 간 diff 를 의미 있게 만들기 위해서다
        uri = f"fp:{str(s).split('#')[-1]}"
        label, comment = pick(g, s, RDFS.label), pick(g, s, RDFS.comment)
        alts = sorted(str(o) for o in g.objects(s, SKOS.altLabel))
        text = " | ".join(x for x in [uri, label, " / ".join(alts), comment] if x)
        terms.append({"term_uri": uri, "label": label, "comment": comment,
                      "alt_labels": alts, "text": text})
    return terms


def main():
    t0 = time.time()
    terms = collect()
    print(f"resource {len(terms)}개 수집 ({', '.join(p.name for p in TTLS)})")
    vecs = clova.embed_many([t["text"] for t in terms])
    if len(vecs) != len(terms) or len(vecs[0]) != EMBED_DIM:
        sys.exit(f"FAIL 임베딩 {len(vecs)}건 / {len(vecs[0]) if vecs else 0}차원")

    with psycopg.connect(BOND_DSN, autocommit=True) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute(f"DROP TABLE IF EXISTS {TABLE}")
        conn.execute(f"""CREATE TABLE {TABLE} (
                term_uri text PRIMARY KEY, label text NOT NULL, comment text NOT NULL,
                alt_labels text[] NOT NULL DEFAULT '{{}}', content text NOT NULL,
                embedding vector({EMBED_DIM}) NOT NULL)""")
        with conn.cursor() as cur:
            cur.executemany(
                f"INSERT INTO {TABLE} (term_uri,label,comment,alt_labels,content,embedding)"
                " VALUES (%s,%s,%s,%s,%s,%s::vector)",
                [(t["term_uri"], t["label"], t["comment"], t["alt_labels"], t["text"],
                  str(list(map(float, v)))) for t, v in zip(terms, vecs)])
        n, dim = conn.execute(
            f"SELECT count(*), max(vector_dims(embedding)) FROM {TABLE}").fetchone()
    if n != len(terms) or dim != EMBED_DIM:
        sys.exit(f"FAIL 적재 검증: {n}행 / {dim}차원")
    print(f"  {TABLE} {n}행 × {dim}차원   소요 {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
