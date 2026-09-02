# -*- coding: utf-8 -*-
"""벡터 / 키워드(FTS) / 트라이그램 / 하이브리드(RRF) 검색.

reranker 는 만들지 않는다. 하이브리드는 두 랭킹을 RRF 로 합치는 것뿐이다.
"""
import psycopg
from pgvector.psycopg import register_vector

from config import DSN, RRF_K, TOP_K


def connect():
    """config.DSN 으로 접속. TCP 강제."""
    conn = psycopg.connect(DSN, autocommit=True)
    register_vector(conn)
    return conn


def vector_search(conn, qvec, k=TOP_K):
    """cosine 거리(<=>) 오름차순. score = 1 - distance = cosine 유사도.

    ::vector 캐스팅이 필요한 이유: register_vector 는 numpy 배열만 vector 로 보낸다.
    clova.embed_many() 는 순수 파이썬 list 를 주므로 float8[] 로 나가 연산자를 못 찾는다.
    모든 벡터 질의가 이 함수를 지나가므로 여기서 한 번만 캐스팅한다.
    """
    rows = conn.execute(
        """
        SELECT doc_key, content, (embedding <=> %(v)s::vector) AS dist
          FROM documents
         ORDER BY embedding <=> %(v)s::vector
         LIMIT %(k)s
        """,
        {"v": str(list(map(float, qvec))), "k": k},
    ).fetchall()
    return [{"doc_key": d, "content": c, "score": round(1.0 - dist, 6),
             "distance": round(dist, 6)} for d, c, dist in rows]


def keyword_search(conn, query, k=TOP_K, cfg="simple"):
    """PostgreSQL FTS. cfg 는 'simple' 또는 'english'.

    plainto_tsquery 는 입력을 같은 설정으로 토큰화해 AND 로 묶는다.
    한국어에는 형태소 분석기가 없어 어절(공백 단위)이 곧 토큰이 된다.
    """
    rows = conn.execute(
        """
        SELECT doc_key, content,
               ts_rank(to_tsvector(%(cfg)s, content), plainto_tsquery(%(cfg)s, %(q)s)) AS rank
          FROM documents
         WHERE to_tsvector(%(cfg)s, content) @@ plainto_tsquery(%(cfg)s, %(q)s)
         ORDER BY rank DESC
         LIMIT %(k)s
        """,
        {"cfg": cfg, "q": query, "k": k},
    ).fetchall()
    return [{"doc_key": d, "content": c, "score": round(r, 6)} for d, c, r in rows]


def trigram_search(conn, query, k=TOP_K, threshold=0.0):
    """pg_trgm 폴백. word_similarity 는 질의가 문서의 '일부'와 얼마나 겹치는지를 본다.

    부분어(예: '등급' -> '위험등급')와 조사 결합을 FTS 대신 잡아내는지 확인용.
    """
    rows = conn.execute(
        """
        SELECT doc_key, content, word_similarity(%(q)s, content) AS sim
          FROM documents
         WHERE content ILIKE '%%' || %(q)s || '%%'
            OR word_similarity(%(q)s, content) > %(t)s
         ORDER BY sim DESC
         LIMIT %(k)s
        """,
        {"q": query, "k": k, "t": threshold},
    ).fetchall()
    return [{"doc_key": d, "content": c, "score": round(s, 6)} for d, c, s in rows]


def rrf(rankings, k=RRF_K):
    """Reciprocal Rank Fusion. score(d) = sum over lists of 1/(k + rank(d)), rank 는 1부터."""
    fused = {}
    for lst in rankings:
        for rank, item in enumerate(lst, start=1):
            e = fused.setdefault(item["doc_key"],
                                 {"doc_key": item["doc_key"], "content": item["content"],
                                  "score": 0.0, "ranks": {}})
            e["score"] += 1.0 / (k + rank)
    for lst, name in zip(rankings, ("vector", "keyword")):
        for rank, item in enumerate(lst, start=1):
            fused[item["doc_key"]]["ranks"][name] = rank
    out = sorted(fused.values(), key=lambda e: -e["score"])[:TOP_K]
    for e in out:
        e["score"] = round(e["score"], 6)
    return out


def hybrid_search(conn, query, qvec, k=TOP_K, cfg="simple"):
    """벡터 랭킹 + FTS 랭킹을 RRF 로 결합. 후보를 넓게 뽑고 합친 뒤 자른다."""
    v = vector_search(conn, qvec, k=k * 2)
    kw = keyword_search(conn, query, k=k * 2, cfg=cfg)
    return rrf([v, kw])
