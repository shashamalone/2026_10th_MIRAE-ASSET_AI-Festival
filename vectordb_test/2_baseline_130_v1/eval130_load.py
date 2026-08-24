# -*- coding: utf-8 -*-
"""온톨로지 용어를 pgvector 테이블에 적재한다 (2차 테스트용).

    python3 eval130_load.py [table]      # 기본 terms130

1차 테스트(test_*.py)는 10건짜리 합성 코퍼스였다. 거기엔 서로 경쟁하는 용어가
없어서 "7/7 정답"이 나왔다. 실제 130건에는 레이블이 완전히 같은 쌍이 16쌍,
'등급'이 들어간 용어가 14개 있다. 그 환경에서 다시 재는 것이 이 파일의 목적이다.

임베딩은 저장소 artifacts/embed_cache.json 에서 읽는다 — API 호출 0건.
캐시 키는 clova.embed_many() 와 동일하게 sha1(f"{model}\x00{text}") 이다.
"""
import hashlib
import json
import sys

import psycopg

# config.py 는 형제 폴더에 있다(폴더 재편). 저장소 루트보다 먼저 넣어야
# 루트 config.py 가 아니라 이 테스트용 config.py 가 잡힌다.
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent
                       / "1_pgvector_test"))
from config import DSN, EMBED_DIM, EMBEDDING_MODEL, ROOT

TERMS = ROOT / "artifacts" / "bond_terms.json"
CACHE = ROOT / "artifacts" / "embed_cache.json"
# 인자로 테이블명을 받는다. 기본 terms130 — 기존 테이블은 지우지 않는다.
TABLE = sys.argv[1] if len(sys.argv) > 1 else "terms130"


def cache_key(text: str) -> str:
    return hashlib.sha1(f"{EMBEDDING_MODEL}\x00{text}".encode()).hexdigest()


def main():
    terms = json.loads(TERMS.read_text(encoding="utf-8"))
    cache = json.loads(CACHE.read_text(encoding="utf-8"))
    print(f"용어 {len(terms)}건 / 캐시 {len(cache)}건")

    rows, missing = [], []
    for t in terms:
        v = cache.get(cache_key(t["text"]))
        if v is None:
            missing.append(t["term_uri"])
            continue
        if len(v) != EMBED_DIM:
            sys.exit(f"FAIL  차원 불일치: {t['term_uri']} dim={len(v)}")
        rows.append((t["term_uri"], t["label"], t["comment"],
                     t.get("alt_labels") or [], t["text"], str(list(map(float, v)))))

    if missing:
        # 캐시에 없으면 조용히 빠뜨리지 않는다. 빠진 채로 재면 정확도가 부풀려진다.
        sys.exit(f"FAIL  캐시 미적중 {len(missing)}건 — {missing[:5]} … "
                 f"kb/build_bond_index.py 를 먼저 실행해 캐시를 채워라")

    with psycopg.connect(DSN, autocommit=True) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute(f"DROP TABLE IF EXISTS {TABLE}")
        conn.execute(f"""
            CREATE TABLE {TABLE} (
                term_uri   text PRIMARY KEY,
                label      text NOT NULL,
                comment    text NOT NULL,
                alt_labels text[] NOT NULL DEFAULT '{{}}',
                content    text NOT NULL,
                embedding  vector({EMBED_DIM}) NOT NULL
            )""")
        with conn.cursor() as cur:
            cur.executemany(
                f"INSERT INTO {TABLE} (term_uri,label,comment,alt_labels,content,embedding)"
                " VALUES (%s,%s,%s,%s,%s,%s::vector)", rows)
        # 1차 결론(§8.3-2)대로 simple 만 만든다. english 는 한국어에 이득이 0이었다.
        conn.execute(f"CREATE INDEX ON {TABLE} USING gin (to_tsvector('simple', content))")

        n = conn.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
        uniq = conn.execute(f"SELECT count(DISTINCT term_uri) FROM {TABLE}").fetchone()[0]
        nulls = conn.execute(
            f"SELECT count(*) FROM {TABLE} WHERE embedding IS NULL").fetchone()[0]
        dim = conn.execute(
            f"SELECT vector_dims(embedding) FROM {TABLE} LIMIT 1").fetchone()[0]
        dup = conn.execute(
            f"SELECT count(*) FROM (SELECT label FROM {TABLE}"
            " GROUP BY label HAVING count(*)>1) s").fetchone()[0]

    print(f"{TABLE}: 적재 {n}건 / DISTINCT uri {uniq} / embedding NULL {nulls} / "
          f"차원 {dim} / 레이블 중복 {dup}그룹")
    assert n == uniq == len(terms), f"적재 누락/중복: n={n} uniq={uniq} terms={len(terms)}"
    assert nulls == 0 and dim == EMBED_DIM
    print("load: PASS  (API 호출 0건)")


if __name__ == "__main__":
    main()
