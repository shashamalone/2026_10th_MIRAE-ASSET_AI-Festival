"""
Graph URI와 사용자 표기를 분리하는 exact-first entity resolver.

팀원의 gragh-test 노트북 `tools/graph_entity.py`(셀 35)를 이식했다. 로직은
그대로이고, import 경로만 우리 평면 구조로 바꿨다(`kb.ids` -> `graph_ids`,
`tools.graph` -> `graph_engine`, `tools.graph_schema` -> `graph_schema`).

[안전 계약] 이 resolver는 편집거리·임베딩 유사도를 쓰지 않는다. 후보가 2개
이상이면 ``ambiguous``로 멈추고 호출자에게 넘긴다. 호출자가 사용자 확인 없이
실행해도 되는 상태는 ``status == "resolved"`` 뿐이다.

[법인명 보강] 2단계(법인격 정규화, `_company_master`)는
`data/enriched/company_master.csv`를 읽는다. 파일이 없는 배포 환경에서는
빈 dict로 폴백하고 다음 단계(정규형/세그먼트 완전일치)를 계속 수행한다.

[성능] 3단계는 첫 호출 때 한 번 만드는 프로세스 내 인덱스(`_entity_index`)로
조회한다. 원래의 클래스 전체 SPARQL 스캔은 호출당 2.6~6.1s였고(2026-09-05
실측) 인덱스 구축이 실패하면 그 경로로 폴백한다.
"""
from __future__ import annotations

import csv
import json
import logging
import pickle
import re
import time
from functools import lru_cache
from pathlib import Path

from agent.graph_logic import graph_engine
from kb.config import ROOT
from agent.graph_logic.graph_ids import normalize_organization_name, normalize_text
from tools.graph_schema import FP

logger = logging.getLogger(__name__)

_ENTITY_QUERY = """
PREFIX fp: <http://mafest.ai/product#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT DISTINCT ?entity ?name ?label ?alt ?code WHERE {
  ?entity rdf:type ?actual_class .
  ?actual_class rdfs:subClassOf* fp:%(class_name)s .
  OPTIONAL { ?entity %(name_property)s ?name }
  OPTIONAL { ?entity rdfs:label ?label }
  OPTIONAL { ?entity skos:altLabel ?alt }
  OPTIONAL { ?entity %(code_property)s ?code }
}
ORDER BY ?entity ?name ?label ?alt ?code
%(window)s
"""

FPI = "http://mafest.ai/instance/"

NORMALIZED_CLASSES = {
    "ETF", "ETN", "Product", "Bond", "PublicFund", "ShareClass",
    "Security", "Theme", "Industry", "Document",
}


def _class_spec(class_name: str) -> tuple[str, str]:
    """클래스 → (이름 속성, 코드 속성). 값은 SPARQL 술어 문자열이다."""
    # 기업 계열 — organizationName 이 정식 법인명, corpCode 는 DART 8자리.
    if class_name in {"Company", "Organization", "Issuer", "AssetManager"}:
        return "fp:organizationName", "fp:corpCode"

    # 상품 계열 — 사용자가 부르는 이름은 productShortName 이다.
    if class_name in {"ETF", "ETN", "Product", "Bond", "PublicFund", "ShareClass"}:
        return "fp:productName|fp:productShortName", "fp:productCode"

    # 증권 — 종목명이 rdfs:label 에 plain literal 로 들어 있다.
    if class_name == "Security":
        return "rdfs:label", "fp:securityCode"

    # 테마 — rdfs:label 은 "우주항공/방산"@ko 처럼 언어태그가 붙어 있다.
    if class_name == "Theme":
        return "fp:themeName|rdfs:label", "fp:themeName"

    if class_name == "Industry":
        return "rdfs:label", "rdfs:label"

    if class_name == "Document":
        return "fp:documentTitle", "fp:sourceId"

    # 지원 목록 밖은 조용히 빈 결과를 내지 않고 즉시 실패시킨다.
    # resolve_frame_seed 는 이 ValueError 를 잡아 다음 클래스로 넘어간다.
    raise ValueError(f"지원하지 않는 entity class: {class_name}")


def _normalized_key(text: object) -> str:
    """정규형 비교 키. SPARQL 쪽 REPLACE(LCASE(...), "[\\s_-]+", "") 와 짝이다."""
    return normalize_text(text).replace(" ", "").replace("-", "").replace("_", "")


@lru_cache(maxsize=1)
def _company_master() -> dict[str, tuple[dict, ...]]:
    """정규형 → DART code 후보. CSV가 없으면(이 워크스페이스의 알려진 제약)
    빈 dict를 돌려주고, resolve_entity의 2단계는 조용히 건너뛴다."""
    path = ROOT / "data" / "enriched" / "company_master.csv"
    if not path.is_file():
        return {}
    out: dict[str, list[dict]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            normalized = (row.get("corp_name_norm")
                          or normalize_organization_name(row.get("corp_name")))
            if not normalized:
                continue
            out.setdefault(normalized, []).append({
                "uri": FPI + "corp-" + row["corp_code"].zfill(8),
                "class_uri": FP + "Company",
                "canonical_name": row.get("corp_name", ""),
                "names": (row.get("corp_name", ""),),
                "codes": (row["corp_code"].zfill(8),),
            })
    return {key: tuple(value) for key, value in out.items()}


def _existing_company_candidates(normalized: str) -> list[dict]:
    """CSV 후보 중 Graph 에 실제로 적재된 것만 남긴다."""
    candidates = []
    for item in _company_master().get(normalized, ()):
        exists = graph_engine.sparql(f"""
PREFIX fp: <http://mafest.ai/product#>
ASK {{ <{item['uri']}> a fp:Company . }}
""")
        if exists:
            candidates.append(item)
    return candidates


def _exact_candidates(text: str, class_name: str) -> list[dict]:
    """입력 문자열 그대로의 완전일치. 정규화도 부분일치도 하지 않는다."""
    name_property, code_property = _class_spec(class_name)
    literal = json.dumps(text, ensure_ascii=False)
    query = f"""
PREFIX fp: <http://mafest.ai/product#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT DISTINCT ?entity ?name ?label ?alt ?code WHERE {{
  {{ ?entity {name_property} {literal} }}
  UNION {{ ?entity rdfs:label {literal} }}
  UNION {{ ?entity skos:altLabel {literal} }}
  UNION {{ ?entity {code_property} {literal} }}
  ?entity rdf:type ?actual_class .
  ?actual_class rdfs:subClassOf* fp:{class_name} .
  OPTIONAL {{ ?entity {name_property} ?name }}
  OPTIONAL {{ ?entity rdfs:label ?label }}
  OPTIONAL {{ ?entity skos:altLabel ?alt }}
  OPTIONAL {{ ?entity {code_property} ?code }}
}}
ORDER BY ?entity ?name ?label ?alt ?code
LIMIT 100
"""
    return _rows_to_candidates(graph_engine.sparql(query), class_name)


def _rows_to_candidates(rows: list[dict], class_name: str) -> list[dict]:
    """행 단위 SPARQL 결과를 entity URI 단위 후보로 접는다.

    **모호성 판정은 행 수가 아니라 고유 entity 수로 이뤄진다** - 이 구분이
    깨지면 멀쩡한 단일 상품이 ambiguous 로 잘못 막힌다."""
    entities: dict[str, dict] = {}
    for row in rows:
        item = entities.setdefault(row["entity"], {
            "uri": row["entity"],
            "class_uri": FP + class_name,
            "canonical_name": row.get("name") or row.get("label") or "",
            "names": set(),
            "codes": set(),
        })
        if row.get("name"):
            item["canonical_name"] = row["name"]
        for key in ("name", "label", "alt"):
            if row.get(key):
                item["names"].add(row[key])
        if row.get("code"):
            item["codes"].add(row["code"])
    return [{**x, "names": tuple(sorted(x["names"])), "codes": tuple(sorted(x["codes"]))}
            for x in entities.values()]


def clear_entity_cache() -> None:
    """company_master 캐시와 3단계 엔티티 인덱스 비우기. 데이터 재빌드 후나
    테스트에서 호출한다."""
    global _INDEX_FAILURE
    _company_master.cache_clear()
    _entity_index.cache_clear()
    _INDEX_FAILURE = None


def _result(status: str, text: str, class_name: str, candidates: list[dict],
            match_mode: str | None = None) -> dict:
    """resolver 반환 규격을 한 곳에서 만든다.

    status 는 resolved / ambiguous / partial_candidates / not_found 넷이다."""
    out = {"status": status, "text": text, "expected_class": FP + class_name,
           "candidates": candidates}
    if status == "resolved":
        out.update(candidates[0])
        out["match_mode"] = match_mode
    return out


def _segment_match(var: str, literal: str) -> str:
    """구분자('/') 경계 완전일치를 검사하는 SPARQL 식을 만든다."""
    return (f'(BOUND(?{var}) && CONTAINS('
            f'CONCAT("/", REPLACE(LCASE(STR(?{var})), "[\\\\s_-]+", ""), "/"), '
            f'CONCAT("/", LCASE({literal}), "/")))')

_PREFIX_IRI = {
    "fp": FP,
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
}
_INDEX_FAILURE: str | None = None  # 구축 실패 사유. 있으면 SPARQL 경로로 폴백한다.


def _iris(term: str) -> tuple[str, ...]:
    """'fp:productName|fp:productShortName' 같은 술어 표기 → IRI 목록."""
    out = []
    for part in term.split("|"):
        prefix, local = part.split(":", 1)
        out.append(_PREFIX_IRI[prefix] + local)
    return tuple(out)


def _sparql_norm(value: object) -> str:
    """_segment_match 의 REPLACE(LCASE(STR(?v)), "[\\s_-]+", "") 와 같은 정규형."""
    return re.sub(r"[\s_\-]+", "", str(value).lower())


def _segment_keys(norm: str) -> set[str]:
    """CONTAINS("/"+norm+"/", "/"+lit+"/") 를 참으로 만드는 lit 전체 집합.
    "/" 세그먼트의 모든 연속 구간이며 전체 문자열도 포함한다."""
    segs = norm.split("/")
    keys: set[str] = set()
    for i in range(len(segs)):
        for j in range(i, len(segs)):
            key = "/".join(segs[i:j + 1])
            if key:
                keys.add(key)
    return keys


def _class_closure(class_name: str) -> set[str]:
    rows = graph_engine.sparql(f"""
PREFIX fp: <http://mafest.ai/product#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?c WHERE {{ ?c rdfs:subClassOf* fp:{class_name} }}
""")
    return {r["c"] for r in rows}


def _values_by_entity(iri: str) -> dict[str, list[str]]:
    rows = graph_engine.sparql(f"SELECT ?entity ?v WHERE {{ ?entity <{iri}> ?v }}", max_rows=None)
    out: dict[str, list[str]] = {}
    for r in rows:
        if r.get("v") is not None:
            out.setdefault(r["entity"], []).append(r["v"])
    return out


_INDEX_CACHE_VERSION = 1
_INDEX_CACHE_PATH = ROOT / "artifacts" / "graph_entity_index.pkl"


def _store_signature() -> dict | None:
    """캐시 유효성 키: 실제로 열린 스토어 경로와 그 안 파일들의 최신 mtime.
    스토어를 다시 빌드하면 mtime 이 바뀌어 캐시가 자동으로 무효화된다."""
    client = getattr(graph_engine, "_CLIENT", None)
    path = getattr(client, "remote_store_path", None) or getattr(client, "local_store_path", None)
    if not path or not Path(path).is_dir():
        return None
    mtime = max((p.stat().st_mtime for p in Path(path).rglob("*") if p.is_file()), default=0.0)
    return {"version": _INDEX_CACHE_VERSION, "store": str(path), "mtime": mtime,
            "classes": sorted(NORMALIZED_CLASSES)}


def _load_index_cache(signature: dict | None):
    if signature is None or not _INDEX_CACHE_PATH.is_file():
        return None
    try:
        with _INDEX_CACHE_PATH.open("rb") as handle:
            payload = pickle.load(handle)
        if payload.get("signature") == signature:
            return payload["index"]
    except Exception as exc:  # noqa: BLE001 - 캐시는 최적화일 뿐, 깨지면 다시 만든다
        logger.warning("entity index cache unreadable, rebuilding: %s", exc)
    return None


def _save_index_cache(signature: dict | None, index: dict) -> None:
    if signature is None:
        return
    try:
        _INDEX_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _INDEX_CACHE_PATH.with_suffix(".pkl.tmp")
        with tmp.open("wb") as handle:
            pickle.dump({"signature": signature, "index": index}, handle, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(_INDEX_CACHE_PATH)
    except Exception as exc:  # noqa: BLE001
        logger.warning("entity index cache not saved: %s", exc)


@lru_cache(maxsize=1)
def _entity_index() -> dict[str, dict[str, frozenset[str]]]:
    """class_name → 세그먼트 키 → 그 키가 name/label/alt/code 어느 하나에 있는 entity URI.

    FILTER 의 OR 조건과 같은 범위라 원래 질의가 돌려줄 entity 의 상위집합이다.
    구축에 약 15s(1.17M 트리플, 2026-09-05 실측)가 걸려 artifacts/ 에 pickle 로
    남기고, 스토어 경로·mtime 이 같으면 다음 프로세스는 그것을 읽는다."""
    signature = _store_signature()
    cached = _load_index_cache(signature)
    if cached is not None:
        logger.info("graph entity index loaded from cache: %s", _INDEX_CACHE_PATH)
        return cached
    t0 = time.perf_counter()
    types = graph_engine.sparql(
        "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n"
        "SELECT ?entity ?type WHERE { ?entity rdf:type ?type }",
        max_rows=None,
    )
    entities_by_type: dict[str, set[str]] = {}
    for r in types:
        entities_by_type.setdefault(r["type"], set()).add(r["entity"])

    label_iri = _PREFIX_IRI["rdfs"] + "label"
    alt_iri = _PREFIX_IRI["skos"] + "altLabel"
    spec: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {}
    needed = {label_iri, alt_iri}
    for cls in NORMALIZED_CLASSES:
        name_p, code_p = _class_spec(cls)
        spec[cls] = (_iris(name_p), _iris(code_p))
        needed.update(spec[cls][0])
        needed.update(spec[cls][1])
    values = {iri: _values_by_entity(iri) for iri in needed}

    index: dict[str, dict[str, frozenset[str]]] = {}
    for cls, (name_iris, code_iris) in spec.items():
        members: set[str] = set()
        for c in _class_closure(cls):
            members |= entities_by_type.get(c, set())
        bucket: dict[str, set[str]] = {}
        for ent in members:
            keys: set[str] = set()
            for iri in (*name_iris, label_iri, alt_iri, *code_iris):
                for v in values[iri].get(ent, ()):
                    keys |= _segment_keys(_sparql_norm(v))
            for key in keys:
                bucket.setdefault(key, set()).add(ent)
        index[cls] = {key: frozenset(ents) for key, ents in bucket.items()}
    logger.info("graph entity index built: %d classes, %.1fs", len(index), time.perf_counter() - t0)
    _save_index_cache(signature, index)
    return index


def _normalized_literal_candidates(text: str, class_name: str) -> list[dict]:
    """공백·구분자를 지운 정규형의 세그먼트 완전일치 후보를 찾는다.

    인덱스로 걸릴 수 있는 entity 를 고른 뒤, 그 entity 로 제한한 원래 SPARQL 을
    실행한다. 후보·행 순서·LIMIT 100 이 스캔 판과 같다. 인덱스를 못 만들면
    스캔 판으로 폴백한다 - 빈 인덱스로 not_found 를 내는 것은 조용한 오답이라
    허용하지 않는다."""
    global _INDEX_FAILURE
    index = None
    if _INDEX_FAILURE is None:
        try:
            index = _entity_index()
        except Exception as exc:  # noqa: BLE001 - 어떤 실패든 폴백해야 한다
            _INDEX_FAILURE = f"{type(exc).__name__}: {exc}"
            logger.warning("entity index unavailable, falling back to SPARQL scan: %s", _INDEX_FAILURE)
    if index is None:
        return _normalized_literal_candidates_sparql(text, class_name)
    hits = index.get(class_name, {}).get(_normalized_key(text).lower())
    if not hits:
        return []
    return _normalized_literal_candidates_sparql(text, class_name, entities=sorted(hits))


def _normalized_literal_candidates_sparql(text: str, class_name: str, *,
                                          entities: list[str] | None = None) -> list[dict]:
    """3단계의 원래 SPARQL. ``entities`` 가 없으면 클래스 전체 스캔(인덱스 폴백·
    회귀 테스트 기준값)이고, 있으면 VALUES 로 그 entity 만 본다."""
    name_property, code_property = _class_spec(class_name)
    literal = json.dumps(_normalized_key(text), ensure_ascii=False)
    filters = " || ".join(_segment_match(v, literal)
                          for v in ("name", "label", "alt", "code"))
    values_clause = ""
    if entities:
        values_clause = "  VALUES ?entity { " + " ".join(f"<{uri}>" for uri in entities) + " }\n"
    query = f"""
PREFIX fp: <http://mafest.ai/product#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT DISTINCT ?entity ?name ?label ?alt ?code WHERE {{
{values_clause}  ?entity rdf:type ?actual_class .
  ?actual_class rdfs:subClassOf* fp:{class_name} .
  OPTIONAL {{ ?entity {name_property} ?name }}
  OPTIONAL {{ ?entity rdfs:label ?label }}
  OPTIONAL {{ ?entity skos:altLabel ?alt }}
  OPTIONAL {{ ?entity {code_property} ?code }}
  FILTER( {filters} )
}}
ORDER BY ?entity
LIMIT 100
"""
    return _rows_to_candidates(graph_engine.sparql(query), class_name)


# 말미에 붙는 일반 상품군 토큰. 이름의 일부가 아니라 화자가 덧붙인 종류 설명이다.
_TYPE_SUFFIX_TOKENS = {"ETF", "ETN", "펀드", "공모펀드", "채권", "회사채", "주식", "테마", "지수"}
_TYPE_SUFFIX_KEYS = {x.upper() for x in _TYPE_SUFFIX_TOKENS}


def resolve_entity(text: str, class_name: str = "Company", *,
                   allow_partial: bool = False,
                   _strip_type_suffix: bool = True) -> dict:
    """표기 문자열 → Graph URI. 좁은 규칙부터 순서대로 시도한다.

    1) exact                    입력 그대로 완전일치
    2) normalized_exact         (기업 전용) 법인격·약칭 제거 후 완전일치
    3) normalized_literal_exact 공백·구분자 제거 후 완전일치
       normalized_segment_exact 위와 같되 "/" 세그먼트로 일치
                                (프로세스 내 인덱스 조회, 실패 시 SPARQL 스캔)
    4) partial_candidates       allow_partial 일 때만, 후보 제시 전용
    5) *_type_stripped          말미 상품군 토큰을 뗀 문자열로 1~4 를 한 번 더

    어느 단계든 후보가 2개 이상이면 즉시 ambiguous 로 멈춘다."""
    raw = str(text or "").strip()
    if not raw:
        return _result("not_found", raw, class_name, [])

    # ── 1단계: 입력 그대로 완전일치 ─────────────────────────────────────────
    exact = _exact_candidates(raw, class_name)
    if len(exact) == 1:
        return _result("resolved", raw, class_name, exact, "exact")
    if len(exact) > 1:
        return _result("ambiguous", raw, class_name, exact)

    # ── 2단계: 기업 전용 법인격 정규화 ──────────────────────────────────────
    if class_name in {"Company", "Organization", "Issuer", "AssetManager"}:
        normalized_name = normalize_organization_name(raw)
        matched = _existing_company_candidates(normalized_name) if normalized_name else []
        if len(matched) == 1:
            return _result("resolved", raw, class_name, matched, "normalized_exact")
        if len(matched) > 1:
            return _result("ambiguous", raw, class_name, matched)

    # ── 3단계: 정규형 + 구분자 세그먼트 완전일치 ────────────────────────────
    if class_name in NORMALIZED_CLASSES:
        normalized = _normalized_literal_candidates(raw, class_name)
        if len(normalized) == 1:
            key = _normalized_key(raw)
            exact_form = any(_normalized_key(n) == key for n in normalized[0]["names"])
            mode = "normalized_literal_exact" if exact_form else "normalized_segment_exact"
            return _result("resolved", raw, class_name, normalized, mode)
        if len(normalized) > 1:
            return _result("ambiguous", raw, class_name, normalized)

    # ── 4단계: 부분일치(후보 제시 전용) ─────────────────────────────────────
    if allow_partial:
        name_property, code_property = _class_spec(class_name)
        literal = json.dumps(raw, ensure_ascii=False)
        query = _ENTITY_QUERY.replace("}\nORDER BY", f"""
  FILTER(
    (BOUND(?name) && CONTAINS(LCASE(STR(?name)), LCASE({literal}))) ||
    (BOUND(?label) && CONTAINS(LCASE(STR(?label)), LCASE({literal}))) ||
    (BOUND(?alt) && CONTAINS(LCASE(STR(?alt)), LCASE({literal}))) ||
    (BOUND(?code) && CONTAINS(LCASE(STR(?code)), LCASE({literal})))
  )
}}
ORDER BY""") % {
            "class_name": class_name,
            "name_property": name_property,
            "code_property": code_property,
            "window": "LIMIT 20",
        }
        partial = _rows_to_candidates(graph_engine.sparql(query), class_name)
        if partial:
            return _result("partial_candidates", raw, class_name, partial[:20])

    # ── 5단계: 말미 상품군 토큰 제거 후 재시도 ───────────────────────────────
    parts = raw.split()
    if _strip_type_suffix and len(parts) > 1 and parts[-1].upper() in _TYPE_SUFFIX_KEYS:
        retry = resolve_entity(" ".join(parts[:-1]), class_name,
                               allow_partial=allow_partial, _strip_type_suffix=False)
        if retry["status"] != "not_found":
            if retry["status"] == "resolved":
                retry["match_mode"] = f"{retry.get('match_mode')}_type_stripped"
            return retry

    return _result("not_found", raw, class_name, [])


# ── 범용 seed resolver ──────────────────────────────────────────────────────
# role → 시도할 클래스 순서. 완전일치 기반이라 순서는 대개 성능에만 영향을
# 주지만, 같은 표기가 여러 클래스에 실재할 때는 결과를 바꾼다.
_ROLE_CLASS_ORDER = {
    "company": ("Company", "Security", "Organization"),
    "issuer": ("Issuer", "Company", "Organization"),
    "manager": ("AssetManager", "Organization"),
    "product": ("ETF", "PublicFund", "Bond", "ETN", "Product"),
    "share_class": ("ShareClass", "PublicFund"),
    "ticker": ("ETF", "ETN", "Security", "Product"),
    "theme": ("Theme",),
    "index": ("Security",),
}


def _ordered_classes(role: str) -> tuple[str, ...]:
    """seed 로 시도할 클래스 순서. entity 의 role 로만 정한다(질문 본문의
    상품군 단어를 섞지 않는다 - 섞으면 seed 자체가 뒤바뀌는 사례가 실측됐다)."""
    return _ROLE_CLASS_ORDER.get(role, ("Product", "Company"))


def resolve_frame_seed(question: str, frame: dict) -> dict:
    """Query Frame 의 복수 entity/class 후보에서 실행 가능한 seed 를 확정한다.

    ``question`` 은 호출부 호환과 로깅을 위해 남겨 둔 인자다. 클래스 순서
    결정에는 쓰지 않는다(_ordered_classes 주석 참고)."""
    attempts: list[dict] = []
    entities = [e for e in frame.get("entities") or [] if e.get("text")]

    for entity in entities:
        text = str(entity["text"]).strip()
        role = entity.get("role") or "product"

        for class_name in _ordered_classes(role):
            try:
                resolved = resolve_entity(text, class_name)
            except ValueError:
                continue

            attempts.append({
                "text": text,
                "role": role,
                "class_name": class_name,
                "status": resolved["status"],
                "candidate_count": len(resolved.get("candidates") or []),
            })

            if resolved["status"] == "resolved":
                return {"status": "resolved", "entity": resolved,
                        "source_entity": entity, "attempts": attempts}

            if resolved["status"] == "ambiguous":
                return {"status": "ambiguous", "entity": resolved,
                        "source_entity": entity, "attempts": attempts}

    return {"status": "not_found", "entity": None,
            "source_entity": None, "attempts": attempts}
