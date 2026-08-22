# -*- coding: utf-8 -*-
"""채권 스키마 TTL → FAISS 인덱스.

    python3 kb/build_bond_index.py

TTL을 일반 문서처럼 자르지 않는다. resource 1개 = vector 1개다.
각 resource에서 URI · rdfs:label · rdfs:comment 를 읽어 한 줄로 만든다.

    fp:riskGradeLevel | 위험등급 수준 | 1=최고위험 … 6=최저위험.

주석(rdfs:comment)이 없는 resource는 넣지 않는다. 이 인덱스의 목적은
"안전한" 같은 말을 fp: 용어로 번역하는 것이고, 번역 근거가 되는 게 주석이기 때문이다.
"""
import json
import sys
import time
from pathlib import Path

import faiss
import numpy as np
from rdflib import RDFS, Graph, Namespace, URIRef

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (ARTIFACTS, BOND_INDEX_PATH, BOND_TERMS_PATH,  # noqa: E402
                    BOND_TTL_PATHS)
import clova  # noqa: E402

FP = Namespace("http://mafest.ai/product#")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")


def pick(g, s, prop, lang="ko"):
    """같은 프로퍼티에 여러 언어가 있으면 한국어 우선."""
    vals = list(g.objects(s, prop))
    if not vals:
        return ""
    ko = [str(v) for v in vals if getattr(v, "language", None) == lang]
    return (ko or [str(v) for v in vals])[0]


def collect():
    """주석 있는 fp: resource를 정렬된 순서로 모은다. 순서가 곧 vector_id다."""
    g = Graph()
    for p in BOND_TTL_PATHS:
        g.parse(p, format="turtle")
    subs = {s for s in g.subjects(RDFS.comment, None)
            if isinstance(s, URIRef) and str(s).startswith(str(FP))}
    terms = []
    for s in sorted(subs, key=str):          # 정렬 — 재빌드해도 vector_id가 안 흔들린다
        uri = f"fp:{str(s).split('#')[-1]}"
        label = pick(g, s, RDFS.label)
        comment = pick(g, s, RDFS.comment)
        alts = sorted(str(o) for o in g.objects(s, SKOS.altLabel))
        # altLabel을 검색 텍스트에 넣는다. 사용자는 '무등급'이라 쓰고 라벨은 'NotRated'인 경우가 있다.
        text = " | ".join(x for x in [uri, label, comment, " / ".join(alts)] if x)
        terms.append({"vector_id": len(terms), "term_uri": uri, "label": label,
                      "comment": comment, "alt_labels": alts, "text": text})
    return terms


def main():
    t0 = time.time()
    terms = collect()
    print(f"resource {len(terms)}개 수집 ({', '.join(p.name for p in BOND_TTL_PATHS)})")

    vecs = clova.embed_many([t["text"] for t in terms])
    v = np.asarray(vecs, dtype=np.float32)
    if v.shape[0] != len(terms):
        sys.exit(f"FAIL 임베딩 개수 불일치: {v.shape[0]} vs {len(terms)}")
    faiss.normalize_L2(v)                    # cosine을 내적으로 계산하기 위한 정규화
    index = faiss.IndexFlatIP(v.shape[1])
    index.add(v)

    ARTIFACTS.mkdir(exist_ok=True)
    faiss.write_index(index, str(BOND_INDEX_PATH))
    BOND_TERMS_PATH.write_text(json.dumps(terms, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"  {BOND_INDEX_PATH.name:20s} {index.ntotal}벡터 × {v.shape[1]}차원  "
          f"{BOND_INDEX_PATH.stat().st_size/1024:.0f}KB")
    print(f"  {BOND_TERMS_PATH.name:20s} {BOND_TERMS_PATH.stat().st_size/1024:.0f}KB")
    print(f"소요 {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
