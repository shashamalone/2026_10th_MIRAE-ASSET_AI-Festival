# -*- coding: utf-8 -*-
"""Graph URI와 사용자 표기를 분리하는 exact-first entity resolver.

이 파일은 ``src/tools/graph_entity.py`` 로 그대로 옮길 수 있는 드롭인 버전이다.
2026-08-30 노트북 검증에서 드러난 4개 원인을 모두 반영했다. 근거는 전부
로컬 oxigraph store(cutoff 2026-08-24) 실측이다.

  원인 1  상품의 사용자 표기는 fp:productShortName 에 있는데 fp:productName
          (정식명)만 조회했다 → "KODEX200" 이 not_found.
  원인 2  seed 클래스 순서를 질문 본문 단어로 편향시켰다 → "KODEX200과 연결된
          공모펀드"에서 seed KODEX200 을 PublicFund 로 해소했다.
  원인 3  fp:Theme 의 rdfs:label 은 "우주항공/방산"@ko 로 언어태그가 붙어
          plain literal 완전일치가 성립하지 않는다.
  원인 4  실제 테마명이 "우주항공/방산" 이라 "우주항공" 과 완전일치가 아니다.

[안전 계약] 이 resolver 는 편집거리·임베딩 유사도를 쓰지 않는다. 후보가 2개
이상이면 ``ambiguous`` 로 멈추고 호출자에게 넘긴다. 상품명 유사명 대체는
AGENTS.md 절대규칙 위반이다("KODEX 200" 부분일치 14건, "KODEX AI로봇" 18건).
호출자가 사용자 확인 없이 실행해도 되는 상태는 ``status == "resolved"`` 뿐이다.
"""
from __future__ import annotations

import csv
import json
from functools import lru_cache

from kb.ids import normalize_organization_name, normalize_text
from tools import graph
from tools.graph_schema import FP
from config import ROOT


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
# 예) fpi:corp-00536541, fpi:etfkr-KR7069500007, fpi:fund-KR5114601001
FPI = "http://mafest.ai/instance/"

# 정규형(공백·구분자 제거) 비교 경로를 태울 클래스.
# Company 계열은 여기 넣지 않는다 — 법인격 정규화(_company_master)라는
# 더 강한 전용 경로가 이미 있고, 두 경로가 겹치면 판정 근거가 흐려진다.
NORMALIZED_CLASSES = {
    "ETF", "ETN", "Product", "Bond", "PublicFund", "ShareClass",
    "Security", "Theme", "Industry", "Document",
}


def _class_spec(class_name: str) -> tuple[str, str]:
    """클래스 → (이름 속성, 코드 속성). 값은 SPARQL 술어 문자열이다.

    ``|`` 는 SPARQL 1.1 property path 의 대안(alternative)이다. 한 자리에 두
    술어를 넣으면 UNION 분기·변수·FILTER 절을 늘리지 않고도 두 속성을 함께
    검사할 수 있다. 이 함수 한 곳만 고치면 완전일치·정규형·부분일치 세 경로에
    모두 반영되는 이유가 이것이다.
    """
    # 기업 계열 — organizationName 이 정식 법인명, corpCode 는 DART 8자리.
    if class_name in {"Company", "Organization", "Issuer", "AssetManager"}:
        return "fp:organizationName", "fp:corpCode"

    # 상품 계열 — 사용자가 부르는 이름은 productShortName 이다.
    #   실측: fpi:etfkr-KR7069500007
    #     productShortName = "KODEX 200"
    #     productName      = "삼성 KODEX200 증권상장지수투자신탁[주식]"
    #   productName 만 보면 "KODEX200" 도 "KODEX 200" 도 못 찾는다(원인 1).
    #   store 내 productShortName 보유: PublicFund 14,716 / Product 8,960 /
    #   ETF 7,207 / ETN 65. Bond·ShareClass 는 없지만 넣어도 손해가 없다.
    if class_name in {"ETF", "ETN", "Product", "Bond", "PublicFund", "ShareClass"}:
        return "fp:productName|fp:productShortName", "fp:productCode"

    # 증권 — 종목명이 rdfs:label 에 plain literal 로 들어 있다.
    if class_name == "Security":
        return "rdfs:label", "fp:securityCode"

    # 테마 — rdfs:label 은 "우주항공/방산"@ko 처럼 언어태그가 붙어 있다(원인 3).
    #   SPARQL 에서 "우주항공/방산"@ko != "우주항공/방산" 이라 plain literal 로는
    #   완전일치가 성립하지 않는다. fp:themeName 은 언어태그 없는 plain 이라
    #   이쪽을 앞에 두어 exact 경로를 살린다. 코드 속성은 테마에 없으므로
    #   themeName 을 재사용한다(중복 OPTIONAL 은 결과에 영향이 없다).
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
    """정규형 비교 키. SPARQL 쪽 REPLACE(LCASE(...), "[\\s_-]+", "") 와 짝이다.

    NFKC 정규화 + casefold 는 kb.ids.normalize_text 의 단일 구현을 쓴다
    (AGENTS.md: 식별자 정규화는 src/kb/ids.py 하나만 사용).
    """
    return normalize_text(text).replace(" ", "").replace("-", "").replace("_", "")


@lru_cache(maxsize=1)
def _company_master() -> dict[str, tuple[dict, ...]]:
    """정규형 → DART code 후보. 전체 Graph scan 대신 빌드 원천의 식별키를 쓴다.

    "에스케이하이닉스(주)" 처럼 법인격·한글 약칭이 섞인 표기를 흡수하기 위한
    기업 전용 경로다. corp_name_norm 컬럼이 있으면 그대로 믿고, 없을 때만
    normalize_organization_name 으로 만든다.
    """
    path = ROOT / "data" / "enriched" / "company_master.csv"
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
    """CSV 후보 중 Graph 에 실제로 적재된 것만 남긴다.

    company_master.csv 에는 있으나 온톨로지 인스턴스로 올라오지 않은 기업이
    있다. 그대로 반환하면 존재하지 않는 URI 를 seed 로 넘겨 뒤에서 빈 결과가
    나오고, 원인이 '관계 없음' 인지 '엔티티 부재' 인지 구분되지 않는다.
    """
    candidates = []
    for item in _company_master().get(normalized, ()):
        exists = graph.sparql(f"""
PREFIX fp: <http://mafest.ai/product#>
ASK {{ <{item['uri']}> a fp:Company . }}
""")
        if exists:
            candidates.append(item)
    return candidates


def _exact_candidates(text: str, class_name: str) -> list[dict]:
    """입력 문자열 그대로의 완전일치. 정규화도 부분일치도 하지 않는다.

    UNION 4분기(이름·label·altLabel·코드)는 각각 술어+객체가 상수라 store
    인덱스를 그대로 탄다. FILTER 로 바꾸면 클래스 전체 스캔이 되므로 유지한다.
    rdf:type 은 subClassOf* 로 올려 하위 클래스(예: fp:CorporateBond ⊂ fp:Bond)도
    같은 질의로 잡는다.
    """
    name_property, code_property = _class_spec(class_name)
    # json.dumps 는 따옴표·역슬래시를 SPARQL 문자열 리터럴과 같은 규칙으로
    # 이스케이프한다. 사용자 입력이 질의 구조를 깨지 못하게 하는 지점이다.
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
    return _rows_to_candidates(graph.sparql(query), class_name)


def _rows_to_candidates(rows: list[dict], class_name: str) -> list[dict]:
    """행 단위 SPARQL 결과를 entity URI 단위 후보로 접는다.

    property path 대안(productName|productShortName)과 OPTIONAL 조합 때문에 한
    entity 가 여러 행으로 나온다. 여기서 URI 로 병합하므로 **모호성 판정은
    행 수가 아니라 고유 entity 수로 이뤄진다** — 이 구분이 깨지면 멀쩡한
    단일 상품이 ambiguous 로 잘못 막힌다.
    """
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

    status 는 resolved / ambiguous / partial_candidates / not_found 넷이다.
    resolved 일 때만 후보 0번을 최상위로 펼쳐(uri·canonical_name 등) 호출자가
    바로 쓸 수 있게 하고, match_mode 로 어떤 규칙에 걸렸는지 남긴다.
    match_mode 는 답변 evidence 에 인용되므로 경로별로 다른 값을 써야 한다.
    """
    out = {"status": status, "text": text, "expected_class": FP + class_name,
           "candidates": candidates}
    if status == "resolved":
        out.update(candidates[0])
        out["match_mode"] = match_mode
    return out


def _segment_match(var: str, literal: str) -> str:
    """구분자('/') 경계 완전일치를 검사하는 SPARQL 식을 만든다.

    양쪽을 "/" 로 감싼 뒤 포함 여부를 본다. 정규식을 쓰지 않으므로 사용자
    입력의 특수문자가 패턴으로 해석될 여지가 없다.

        "/우주항공/방산/"  CONTAINS "/우주항공/"  → true   (세그먼트 일치)
        "/조선/해운/"      CONTAINS "/해운/"      → true
        "/코스피200/"      CONTAINS "/코스피/"    → false  (부분일치는 안 됨)

    구분자가 없는 이름에서는 "/이름/" 대 "/입력/" 비교라 평범한 완전일치와
    똑같이 동작한다. 즉 이 규칙은 완전일치를 **확장**할 뿐 느슨하게 만들지
    않는다. REPLACE 안의 "[\\\\s_-]+" 는 SPARQL 리터럴로 들어가 최종 정규식
    [\\s_-]+ 가 되며, 공백·하이픈·언더스코어를 지운다.
    """
    return (f'(BOUND(?{var}) && CONTAINS('
            f'CONCAT("/", REPLACE(LCASE(STR(?{var})), "[\\\\s_-]+", ""), "/"), '
            f'CONCAT("/", LCASE({literal}), "/")))')


def _normalized_literal_candidates(text: str, class_name: str) -> list[dict]:
    """공백·구분자를 지운 정규형의 세그먼트 완전일치 후보를 찾는다.

    편집거리도 임베딩 유사도도 아니다. 따라서 유사 상품 대체에 쓰이지 않는다.
    STR(?x) 로 감싸므로 언어태그("...@ko")가 붙은 리터럴도 여기서는 비교된다.

    비용 주의: FILTER 방식이라 해당 클래스 전체를 훑는다. 완전일치
    (_exact_candidates)가 실패했을 때만 호출하는 2차 경로로 유지한다.
    """
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
    return _rows_to_candidates(graph.sparql(query), class_name)


# 말미에 붙는 일반 상품군 토큰. 이름의 일부가 아니라 **화자가 덧붙인 종류 설명**이다.
#   실측: HCX frame 이 "LVDS ETF가 보유한 종목" 에서 엔티티 텍스트를 "LVDS" 가 아니라
#   "LVDS ETF" 로 뽑는다. store 의 productShortName 은 "LVDS" 라 완전일치 0건 →
#   ambiguous(2종) 여야 할 질의가 not_found 로 끝났다.
# 이름 자체가 이 토큰으로 끝나는 상품은 1단계 완전일치가 먼저 잡으므로 손실이 없다.
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

    어느 단계든 후보가 2개 이상이면 즉시 ambiguous 로 멈춘다. 다음 단계로
    내려가 더 느슨한 규칙으로 하나를 고르는 일은 하지 않는다.

    ``_strip_type_suffix`` 는 5단계 재시도의 재귀 1회 제한용 내부 인자다.
    """
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
    # "(주) 에코프로" → "에코프로". company_master 의 검증된 정규형만 쓰고
    # 편집거리는 쓰지 않는다.
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
            # 어떤 규칙에 걸렸는지 구분해 근거에 남긴다. 이름 전체가 정규형까지
            # 같으면 literal, "우주항공"→"우주항공/방산" 처럼 세그먼트로만
            # 일치하면 segment 다. 후자는 사람이 검토할 여지가 더 크다.
            key = _normalized_key(raw)
            exact_form = any(_normalized_key(n) == key for n in normalized[0]["names"])
            mode = "normalized_literal_exact" if exact_form else "normalized_segment_exact"
            return _result("resolved", raw, class_name, normalized, mode)
        if len(normalized) > 1:
            # 예: "원유" → fp:Theme_원유 와 fp:Theme_원유/가스기업 둘 다 걸린다.
            return _result("ambiguous", raw, class_name, normalized)

    # ── 4단계: 부분일치(후보 제시 전용) ─────────────────────────────────────
    # 단일 후보여도 resolved 로 승격하지 않는다. 호출자가 사용자에게 확인해야
    # 한다. "KODEX" 로 14건이 걸리는 상황을 자동 확정하면 오답이 된다.
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
        partial = _rows_to_candidates(graph.sparql(query), class_name)
        if partial:
            return _result("partial_candidates", raw, class_name, partial[:20])

    # ── 5단계: 말미 상품군 토큰 제거 후 재시도 ───────────────────────────────
    # "LVDS ETF" → "LVDS". 자르는 것은 **공백으로 분리된 마지막 토큰 하나뿐**이고
    # 그 토큰이 _TYPE_SUFFIX_TOKENS 에 정확히 있을 때만이다. 편집거리·부분일치가
    # 아니므로 유사 상품 대체로 번지지 않는다. ambiguous 는 그대로 올려 보내
    # 임의 확정하지 않는다. 재귀는 _strip_type_suffix=False 로 1회로 막는다.
    parts = raw.split()
    if _strip_type_suffix and len(parts) > 1 and parts[-1].upper() in _TYPE_SUFFIX_KEYS:
        retry = resolve_entity(" ".join(parts[:-1]), class_name,
                               allow_partial=allow_partial, _strip_type_suffix=False)
        if retry["status"] != "not_found":
            if retry["status"] == "resolved":
                # 어떤 규칙에 걸렸는지 근거에 남긴다. 예: exact_type_stripped
                retry["match_mode"] = f"{retry.get('match_mode')}_type_stripped"
            return retry

    return _result("not_found", raw, class_name, [])


# ── 범용 seed resolver ──────────────────────────────────────────────────────
# role → 시도할 클래스 순서. 완전일치 기반이라 순서는 대개 성능에만 영향을
# 주지만, **같은 표기가 여러 클래스에 실재할 때는 결과를 바꾼다**.
#   실측: "KODEX200" 은 fpi:etfkr-KR7069500007(ETF) 와
#         fpi:fund-KR5114601001(PublicFund) 양쪽에 있다.
#   상장 통칭으로 부르는 표기이므로 product role 에서는 ETF 를 앞에 둔다.
_ROLE_CLASS_ORDER = {
    "company": ("Company", "Security", "Organization"),
    # ETF·ETN·Product 는 발행 주체 클래스가 아닌 **후순위**다. "VOO가 발행한 회사채"
    # 처럼 상품이 issuer 로 태깅됐을 때 상품으로 해소해야, plan 의 fp:issuedBy
    # (domain=Bond 단독)가 validator 의 domain 위반으로 걸려 의도된 ABSTAIN 이 된다.
    # 여기서 not_found 로 조기 종료하면 '도메인 위반' 판정 경로 자체를 못 탄다.
    "issuer": ("Issuer", "Company", "Organization", "ETF", "ETN", "Product"),
    "manager": ("AssetManager", "Organization"),
    "product": ("ETF", "PublicFund", "Bond", "ETN", "Product"),
    "share_class": ("ShareClass", "PublicFund"),
    "ticker": ("ETF", "ETN", "Security", "Product"),
    "theme": ("Theme",),
    "index": ("Security",),
}


def _ordered_classes(role: str) -> tuple[str, ...]:
    """seed 로 시도할 클래스 순서. **entity 의 role 로만** 정한다.

    질문 본문의 상품군 단어를 여기 섞지 않는다. "공모펀드"·"ETF" 같은 말은
    찾으려는 **대상(target)** 이지 seed 엔티티의 클래스가 아니기 때문이다.
    질문 텍스트로 순서를 편향시키면 이렇게 어긋난다(원인 2, 실측):

        "KODEX200과 연결된 공모펀드를 찾아줘"
          → 질문에 "공모펀드" 가 있다는 이유로 PublicFund 를 먼저 시도
          → seed KODEX200 이 fund-KR5114601001 로 해소됨 (ETF 여야 한다)

        "우주항공 테마와 연결된 ETF를 찾아줘"
          → role 이 theme 인데 질문에 "ETF" 가 있어 ETF 부터 조회
          → 테마명이 어느 ETF 약칭과 겹치면 seed 자체가 뒤바뀐다
    """
    return _ROLE_CLASS_ORDER.get(role, ("Product", "Company"))


def resolve_frame_seed(question: str, frame: dict) -> dict:
    """Query Frame 의 복수 entity/class 후보에서 실행 가능한 seed 를 확정한다.

    ``question`` 은 호출부 호환과 로깅을 위해 남겨 둔 인자다. 클래스 순서
    결정에는 쓰지 않는다(_ordered_classes 주석 참고).

    반환의 ``attempts`` 에는 시도한 (text, role, class, status) 를 전부 남긴다.
    실패했을 때 '엔티티가 없다' 인지 '클래스를 잘못 골랐다' 인지 구분하려면
    이 기록이 필요하다.
    """
    attempts: list[dict] = []
    entities = [e for e in frame.get("entities") or [] if e.get("text")]

    for entity in entities:
        text = str(entity["text"]).strip()
        role = entity.get("role") or "product"

        for class_name in _ordered_classes(role):
            try:
                resolved = resolve_entity(text, class_name)
            except ValueError:
                # 지원하지 않는 클래스는 건너뛴다(_class_spec 이 던진다).
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
                # 상위 클래스로 넓혀 임의로 하나를 고르지 않는다. 모호성은
                # 그대로 호출자에게 올려 사용자 확인을 받게 한다.
                return {"status": "ambiguous", "entity": resolved,
                        "source_entity": entity, "attempts": attempts}

    return {"status": "not_found", "entity": None,
            "source_entity": None, "attempts": attempts}


if __name__ == "__main__":
    # 자체 점검. 실행: PYTHONPATH=src python3 src/tools/graph_entity.py
    # (노트북용 동일 사본: test/agent_test/Gragh-test/graph_entity.py)
    # 로컬 oxigraph store(artifacts/oxigraph)와 company_master.csv 가 필요하다.
    def frame(text: str, role: str) -> dict:
        return {"entities": [{"text": text, "role": role}]}

    CASES = [
        # (입력, 클래스, 기대 status, 기대 match_mode)
        ("에코프로", "Company", "resolved", "exact"),
        ("(주) 에코프로", "Company", "resolved", "normalized_exact"),
        ("KODEX200", "ETF", "resolved", "normalized_literal_exact"),
        ("KODEX 200", "ETF", "resolved", "exact"),
        ("우주항공", "Theme", "resolved", "normalized_segment_exact"),
        ("우주항공/방산", "Theme", "resolved", "exact"),
        # "원유" 는 fp:Theme_원유 와 fp:Theme_원유/가스기업 양쪽의 세그먼트에
        # 걸리지만, 1단계 exact(themeName "원유")가 먼저 확정한다.
        # 완전일치가 세그먼트 일치를 이기는 것이 의도된 순서다.
        ("원유", "Theme", "resolved", "exact"),
        ("코스피", "Theme", "not_found", None),         # 코스피200 에 부분일치 금지
        ("LVDS", "ETF", "ambiguous", None),            # 같은 약칭 ETF 2종 — 1단계에서 중단
        ("교보증권 (CP)", "Security", "ambiguous", None),  # 정규형 단계에서 34종 중단
        ("존재하지않는상품XYZ", "ETF", "not_found", None),
    ]
    failures = []
    for text, cls, want_status, want_mode in CASES:
        got = resolve_entity(text, cls)
        ok = got["status"] == want_status and (
            want_mode is None or got.get("match_mode") == want_mode)
        print(f"{'PASS' if ok else 'FAIL'}  {text:16} {cls:11} "
              f"{got['status']:18} {got.get('match_mode') or '-'}")
        if not ok:
            failures.append((text, cls, want_status, want_mode, got["status"],
                             got.get("match_mode")))

    # seed 확정 — 질문 본문 단어가 클래스 선택을 흔들지 않는지 확인한다.
    SEEDS = [
        ("KODEX200과 연결된 공모펀드를 찾아줘", frame("KODEX200", "product"), "ETF"),
        ("우주항공 테마와 연결된 ETF를 찾아줘", frame("우주항공", "theme"), "Theme"),
    ]
    for question, fr, want_class in SEEDS:
        seed = resolve_frame_seed(question, fr)
        cls = (seed["entity"] or {}).get("class_uri", "")
        ok = seed["status"] == "resolved" and cls.endswith("#" + want_class)
        print(f"{'PASS' if ok else 'FAIL'}  seed  {question[:28]:30} "
              f"{seed['status']:12} {cls.split('#')[-1] or '-'} "
              f"{(seed['entity'] or {}).get('match_mode') or '-'}")
        if not ok:
            failures.append((question, want_class, "resolved", None,
                             seed["status"], cls))

    print(f"\n{len(CASES) + len(SEEDS) - len(failures)}/"
          f"{len(CASES) + len(SEEDS)} PASS")
    for f in failures:
        print("  FAIL", f)
    raise SystemExit(1 if failures else 0)
