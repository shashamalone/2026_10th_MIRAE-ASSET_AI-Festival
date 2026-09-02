"""
Graph URI와 사용자 표기를 분리하는 exact-first entity resolver.

팀원의 gragh-test 노트북 `tools/graph_entity.py`(셀 35)를 이식했다. 로직은
그대로이고, import 경로만 우리 평면 구조로 바꿨다(`kb.ids` -> `graph_ids`,
`tools.graph` -> `graph_engine`, `tools.graph_schema` -> `graph_schema`).

[안전 계약] 이 resolver는 편집거리·임베딩 유사도를 쓰지 않는다. 후보가 2개
이상이면 ``ambiguous``로 멈추고 호출자에게 넘긴다. 호출자가 사용자 확인 없이
실행해도 되는 상태는 ``status == "resolved"`` 뿐이다.

[알려진 제약] 2단계(법인격 정규화, `_company_master`)는 `data/enriched/
company_master.csv`가 이 워크스페이스에 없어 동작하지 않는다 - CSV가 없으면
`_company_master`가 빈 dict를 돌려주고 그 다음 단계(3단계, 정규형/세그먼트
완전일치)로 조용히 넘어간다. 1·3단계가 대부분의 표기 흔들림을 이미 커버한다.
"""
from __future__ import annotations

import csv
import json
from functools import lru_cache

from agent.graph_logic import graph_engine
from kb.config import ROOT
from agent.graph_logic.graph_ids import normalize_organization_name, normalize_text
from tools.graph_schema import FP


# ── partial(부분일치) 전용 질의 템플릿 ────────────────────────────────────────
# resolve_entity(allow_partial=True) 에서만 쓴다. %(...)s 자리는 _class_spec 이
# 돌려주는 속성명과 LIMIT 으로 채운다. 완전일치 경로는 이 템플릿을 쓰지 않고
# _exact_candidates 가 UNION 으로 직접 만든다(인덱스 조회가 되도록).
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

# ABox 인스턴스 네임스페이스. TBox 의 fp:(product#) 와 다르다.
FPI = "http://mafest.ai/instance/"

# 정규형(공백·구분자 제거) 비교 경로를 태울 클래스.
# Company 계열은 여기 넣지 않는다 — 법인격 정규화(_company_master)라는
# 더 강한 전용 경로가 이미 있고, 두 경로가 겹치면 판정 근거가 흐려진다.
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
    """company_master 캐시 비우기. 데이터 재빌드 후나 테스트에서 호출한다."""
    _company_master.cache_clear()


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


def _normalized_literal_candidates(text: str, class_name: str) -> list[dict]:
    """공백·구분자를 지운 정규형의 세그먼트 완전일치 후보를 찾는다."""
    name_property, code_property = _class_spec(class_name)
    literal = json.dumps(_normalized_key(text), ensure_ascii=False)
    filters = " || ".join(_segment_match(v, literal)
                          for v in ("name", "label", "alt", "code"))
    query = f"""
PREFIX fp: <http://mafest.ai/product#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT DISTINCT ?entity ?name ?label ?alt ?code WHERE {{
  ?entity rdf:type ?actual_class .
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
    "issuer": ("Issuer", "Company", "Organization", "ETF", "ETN", "Product"),
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
