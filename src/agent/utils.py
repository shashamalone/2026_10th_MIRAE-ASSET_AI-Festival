"""
노드 안에서 필요한 로직에 사용되는 함수들 정리.

지금은 RDB 검색 노드(rdb_search_node)가 쓰는 함수들만 있다. "개념명을
실제 컬럼으로 바꾸고, 값이 유효한지 확인하고, SQL을 만들어서 실행한다"
까지의 전체 파이프라인을 여기 모아뒀다. GraphDB/VectorDB는 아직 세부
로직이 없어서(라우팅 구조만 존재) 이 파일에는 RDB 관련 함수만 있다.
나중에 그쪽 로직이 생기면 graph_utils.py, vector_utils.py처럼 따로
나누는 편이 이 파일이 계속 RDB 전용으로 읽히게 하는 데 낫다.

추상적인 개념 분해(Intent) -> 도메인에 맞는 테이블 찾기 -> 미리 정의된 카탈로그(ATTRIBUTE_CATALOG)로 개념을 컬럼에 확정 매핑 
-> 모르는 것만 LLM에게 실제 컬럼 목록을 주고 선택하게 하기

[전체 흐름 요약]
plan_query_db.py가 만든 RDB 단계 하나(step)를 받아서:
  1. collect_needed_concepts(step) - 이 단계가 컬럼으로 해석해야 하는
     개념명 목록을 모은다(conditions의 attribute, subtype, sort의
     attribute, fields, 상품명).
  2. resolve_concepts_for_domain(...) - rdb_schema.ATTRIBUTE_CATALOG로
     먼저 결정론적으로 찾고, 없는 것만 LLM 폴백(컬럼명을 지어내지
     못하도록 실제 컬럼 목록을 보여주고 그 안에서만 고르게 함).
  3. build_resolved_schema(...) - 컬럼 매핑 + 값 검증(ordinal 타입이면
     value_order 안에 있는지, 값이 아예 비어 있지 않은지)까지 끝난
     조건/정렬/필드 구조를 만든다. ordinal 조건은 여기서
     resolve_ordinal_matched_values로 "이상/이하가 정확히 어떤 값들을
     가리키는지"까지 미리 계산해 둔다(LLM이 CASE WHEN 방향을 스스로
     판단하다가 틀리는 것을 막기 위해서다).
  4. format_resolved_schema(...) - 이걸 SQL 생성 LLM에 보여줄 텍스트로
     정리한다.
  5. get_pg_connection() / run_sql(...) - 로컬 Postgres에 실제로 붙어서
     SQL을 실행하고 행을 가져온다.
"""
from __future__ import annotations

import os
import re
from typing import Any

from agent.graph_logic import graph_ids
from tools import rdb_schema
from tools import catalog_sql
from agent.prompts import COLUMN_RESOLUTION_SYSTEM_PROMPT
from tools.rdb_schema import AttributeSpec
from tools.schemas import COLUMN_RESOLUTION_JSON_SCHEMA


# ---------------------------------------------------------------------------
# 0) 판매가능여부 조건 사전 처리 (rdb_schema.DOMAIN_SALE_POLICY 적용)
# ---------------------------------------------------------------------------
SALE_AVAILABILITY_CONCEPT = "판매가능여부"
# A provenance request is a set of source-date columns, not one guessed column.
PROVENANCE_CONCEPTS = {"기준일", "각수치의기준일", "데이터갱신일", "데이터업데이트일"}


def apply_sale_policy(step: dict) -> tuple[dict, list[str]]:
    """conditions 중 '판매가능여부' 조건을 rdb_schema.DOMAIN_SALE_POLICY에
    따라 미리 처리한다. (수정된 step, 정책 적용 로그) 튜플을 돌려준다.

    반드시 collect_needed_concepts보다 먼저 호출해야 한다. 그러지 않으면
    다음 사고가 난다: 국공채/해외ETF처럼 이 개념을 ATTRIBUTE_CATALOG에
    의도적으로 넣지 않은 도메인(mode="no_filter")에서는 '판매가능여부'가
    needed_concepts에 들어가고, 카탈로그에도 없고 LLM 폴백도 실제로는
    무효라고 공지된 컬럼(buyable_quantity 등)을 억지로 붙잡거나 실패해서
    unresolved_concepts에 남는다. build_resolved_schema는 unresolved_concepts가
    하나라도 있으면 그 RDB 단계 전체를 "미해결 개념"으로 건너뛰므로, 조건
    하나 때문에 질문 전체가 답변불가 처리되는 사고로 이어진다.

    mode="column_filter"인 도메인(국내ETF, 펀드)은 여기서 손대지 않는다.
    이미 ATTRIBUTE_CATALOG에 대응 컬럼(pd_sale_yn, sale_yn)이 있어서 기존
    개념->컬럼 해석 경로가 그대로 정확하게 처리하기 때문이다. 이 함수는
    카탈로그에 일부러 넣지 않은 도메인만 상대한다."""
    domain = step.get("domain", "")
    policy = rdb_schema.get_sale_policy(domain)
    if policy.get("mode") != "no_filter":
        return step, []

    conditions = step.get("conditions") or []
    kept = [c for c in conditions if c.get("attribute", "").replace(" ", "") != SALE_AVAILABILITY_CONCEPT]
    if len(kept) == len(conditions):
        return step, []

    new_step = dict(step)
    new_step["conditions"] = kept
    note = f"'판매가능여부' 조건은 적용하지 않았습니다({policy.get('reason', '')})"
    return new_step, [note]


# ---------------------------------------------------------------------------
# 1) 개념 수집
# ---------------------------------------------------------------------------
def collect_needed_concepts(step: dict) -> list[str]:
    """RDB 단계 하나에서 컬럼으로 해석해야 하는 개념명 전부를 모은다.
    순서를 유지한 채 중복은 제거한다.

    subtype(회사채, 레버리지 등)은 여기서 다루지 않는다. 예전에는
    "상품유형" 개념 이름 하나로 뭉뚱그려 이 목록에 넣었지만, ETF/펀드는
    subtype 값마다 실제로 가리키는 컬럼이 달라서(레버리지는 배수 컬럼,
    공모/사모는 다른 컬럼) 개념 이름 하나로 표현이 안 된다. 지금은
    resolve_subtype_conditions가 rdb_schema.resolve_subtype_condition으로
    값 단위로 직접 컬럼을 찾는다(build_resolved_schema에서 호출)."""
    concepts: list[str] = [c["attribute"] for c in build_condition_list(step)]

    sort = step.get("sort") or {}
    if sort.get("attribute"):
        concepts.append(sort["attribute"])

    concepts.extend(f for f in step.get("fields", []) if catalog_sql.normalize(f) not in PROVENANCE_CONCEPTS)

    # "상품명"은 항상 필요하다(role="target" 조회에 한해). 조건에
    # 쓰였든(product_name_entities) 아니든, 결과 행이 순자산 숫자나
    # 신용등급 값만 달랑 있으면 "어느 상품인지" 알 수 없어서 답으로
    # 쓸모가 없다. "순자산이 가장 큰 상품"처럼 fields에 상품명 자체를
    # 명시적으로 요청하지 않는 질문이 대부분이라, fields만 믿으면 항상
    # 빠진다. 그래서 role이 target이면 조건 없이 넣는다.
    if step.get("role", "target") == "target":
        concepts.append("상품명")

    seen: set[str] = set()
    deduped: list[str] = []
    for c in concepts:
        if c not in seen:
            seen.add(c)
            deduped.append(c)
    return deduped


def build_condition_list(step: dict) -> list[dict]:
    """step의 conditions에 product_name_entities를 조건 형태로 흡수해서
    하나의 리스트로 합친다. 이후 코드는 이 리스트 하나만 다루면 된다.

    subtype은 여기서 다루지 않는다(resolve_subtype_conditions가 별도로
    처리해서 build_resolved_schema가 직접 합친다)."""
    # Internal OR/identity markers can only be produced below, not by model
    # output that happens to contain additional JSON properties.
    conditions: list[dict] = [{key: c[key] for key in ("attribute", "operator", "value", "value_2") if key in c}
                             for c in step.get("conditions", [])]

    for e in step.get("product_name_entities") or []:
        # 정확한 표기가 DB와 다를 수 있어(공백, 접미사 등) eq가 아니라
        # contains로 매칭한다.
        conditions.append({"attribute": "상품명", "operator": "contains", "value": e["surface_form"], "value_2": "", "any_group": "product_names", "entity_identity": True})
        if step.get("domain") == "해외ETF" and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.^-]{0,19}", e["surface_form"]):
            # Tickers and RICs are identifiers, not substrings of a fund's full
            # legal name. Resolve both via reviewed catalogue concepts.
            for attribute in ("티커", "상품코드"):
                conditions.append({"attribute": attribute, "operator": "eq", "value": e["surface_form"],
                                   "value_2": "", "any_group": "product_names"})

    return conditions


def resolve_subtype_conditions(domain: str, subtype: list[str]) -> tuple[list[dict], list[str]]:
    """product_domain의 subtype 값들을 rdb_schema.resolve_subtype_condition으로
    직접 실제 컬럼 조건으로 바꾼다. (이미 컬럼까지 정해진 조건 레코드 목록,
    적용 로그) 튜플을 돌려준다.

    해석하지 못한 subtype도 필터다. 로그만 남기고 버리면 제한 없는
    전체 상품 조회를 해당 유형의 결과로 오인하므로 invalid로 보존한다."""
    records: list[dict] = []
    notes: list[str] = []
    for value in subtype or []:
        mapped = rdb_schema.resolve_subtype_condition(domain, value)
        if domain in {"국내ETF", "해외ETF"} and value.upper() in {"ETF", "ETN"}:
            mapped = {"column": "pd_grp_no", "operator": "eq", "value": value.upper()}
        if mapped is None:
            records.append({"attribute": "상품유형", "value": value, "value_2": "", "operator": "eq",
                            "column": None, "spec": None, "valid": False,
                            "invalid_reason": f"하위유형 '{value}'에 대응하는 검증된 필터가 없습니다."})
            continue
        records.append(
            {
                "attribute": f"상품유형({value})",
                "operator": mapped["operator"],
                "value": mapped["value"],
                "value_2": "",
                "column": mapped["column"],
                "spec": None,
                "valid": True,
                "invalid_reason": None,
                "matched_values": None,
            }
        )
    return records, notes


# ---------------------------------------------------------------------------
# 2) 개념 -> 컬럼 해석 (카탈로그 우선, LLM 폴백)
# ---------------------------------------------------------------------------
def resolve_concepts_for_domain(
    domain: str, needed_concepts: list[str], question: str, llm: Any
) -> tuple[dict[str, AttributeSpec], list[str]]:
    """개념명 목록을 rdb_schema.ATTRIBUTE_CATALOG로 먼저 결정론적으로
    해석하고, 카탈로그에 없는 것만 LLM 폴백으로 넘긴다. LLM 호출이
    실패해도(타임아웃, 인증 오류 등) 예외를 던지지 않고 해당 개념들을
    그냥 미해결로 남긴다 - 호출부가 "미해결 개념이 있으면 SQL 생성을
    건너뛴다"로 안전하게 처리하기 때문이다."""
    attribute_map = rdb_schema.get_attribute_catalog(domain)
    concept_to_spec: dict[str, AttributeSpec] = {}
    unresolved: list[str] = []

    # [보편적 방어 로직 1] 카탈로그 키들의 공백을 모두 제거하고 소문자로 만든 매핑을 미리 준비합니다.
    # 예: "1년 수익률" -> "1년수익률", "ESG 채권" -> "esg채권"
    normalized_attr_map = {
        k.replace(" ", "").lower(): v for k, v in attribute_map.items()
    }

    for concept in needed_concepts:
        # [보편적 방어 로직 2] LLM이 뽑아낸 개념명도 공백을 제거하고 소문자로 만듭니다.
        normalized_concept = concept.replace(" ", "").lower()
        
        # 원본 이름으로 먼저 찾아보고, 없으면 정규화된(공백 제거된) 이름으로 찾습니다.
        spec = attribute_map.get(concept) or normalized_attr_map.get(normalized_concept)
        
        if spec is not None:
            # 딕셔너리에 저장할 때는 LLM이 만든 '원본 concept 이름'을 그대로 유지해야
            # 뒤에 이어지는 조건 조립(build_resolved_schema) 단계에서 키가 엇갈리지 않습니다.
            concept_to_spec[concept] = spec
        else:
            unresolved.append(concept)

    metadata: dict = {}
    if unresolved:
        try:
            metadata = catalog_sql.domain_metadata(domain)
            aliases = catalog_sql.description_aliases(domain, metadata)
            for concept in unresolved:
                spec = aliases.get(catalog_sql.normalize(concept))
                if spec is not None:
                    concept_to_spec[concept] = spec
            unresolved = [c for c in unresolved if c not in concept_to_spec]
        except Exception as exc:
            print(f"[카탈로그 의미 메타 사용 불가] {domain}: {exc}")

    if unresolved:
        try:
            fallback = _resolve_unknown_concepts_via_llm(domain, unresolved, question, llm)
        except Exception:
            fallback = {}
        for concept, column in fallback.items():
            concept_to_spec[concept] = catalog_sql.spec_for_column(domain, column, metadata)
        unresolved = [c for c in unresolved if c not in fallback]

    return concept_to_spec, unresolved


def _resolve_unknown_concepts_via_llm(domain: str, concepts: list[str], question: str, llm: Any) -> dict[str, str]:
    """카탈로그에 없는 개념들을 이 도메인의 실제 컬럼 목록과 대조해서
    매칭한다. LLM이 column을 빈 문자열로 준 concept은 결과에서 제외된다
    (= 여전히 미해결로 남는다). 컬럼명을 지어내지 못하도록 실제 컬럼
    목록 전체(rdb_schema.get_full_column_list)를 프롬프트에 보여준다."""
    if not concepts:
        return {}
    structured_llm = llm.with_structured_output(COLUMN_RESOLUTION_JSON_SCHEMA, method="json_schema")
    # Live existence, unlike descriptions, is not optional in the LLM fallback.
    from tools import schema_snapshot
    snapshot = schema_snapshot.get_snapshot()
    table = rdb_schema.get_domain_entry(domain)["table"]
    allowed = set(schema_snapshot.get_columns(table, snapshot))
    try:
        metadata = catalog_sql.domain_metadata(domain, snapshot)
    except Exception:
        metadata = {}
    import json
    real_columns = [json.dumps({"column": col,
                    "reviewed": rdb_schema.RDB_SCHEMA[domain]["properties"].get(col, {}),
                    "metadata": {k: metadata.get(col, {}).get(k) for k in
                                 ("description", "unit", "zero_null_rule", "as_of_column")}},
                    ensure_ascii=False) for col in sorted(allowed)]
    result = structured_llm.invoke(
        [
            ("system", COLUMN_RESOLUTION_SYSTEM_PROMPT),
            (
                "human",
                f"[테이블]\n{domain}\n\n"
                f"[테이블의 실제 컬럼 목록]\n{', '.join(real_columns)}\n\n"
                f"[원본 질문]\n{question}\n\n"
                f"[매칭할 개념 목록]\n{', '.join(concepts)}",
            ),
        ]
    )
    # 구조화 출력도 신뢰 경계 밖이다. 요청하지 않은 개념, SQL 표현식,
    # 다른 테이블의 컬럼 및 지어낸 식별자는 절대 카탈로그로 승격하지 않는다.
    accepted: dict[str, str] = {}
    conflicts: set[str] = set()
    for row in result.get("resolutions", []):
        concept, column = row.get("concept"), row.get("column")
        if concept not in concepts or column not in allowed:
            continue
        if concept in accepted and accepted[concept] != column:
            conflicts.add(concept)
        accepted[concept] = column
    return {c: col for c, col in accepted.items() if c not in conflicts}


def validate_ordinal_value(spec: AttributeSpec, value: str) -> tuple[bool, str | None, str]:
    """ordinal 타입(신용등급 등)은 값의 전체 도메인이 정해진 표준
    척도이므로, 조건에 쓰인 값이 그 척도 안에 있는지 검증한다. "신용등급
    AAAA"처럼 개념은 맞는데 값이 도메인 밖인 경우를 여기서 잡는다.

    완전 일치가 안 되면 부분 일치(예: "2" 또는 "2등급"이 "높은위험(2등급)"
    안에 포함되는지)도 확인해서, 맞으면 그 정식 표기(matched_value)로
    바꿔 돌려준다. 이 정식 표기가 이후 resolve_ordinal_matched_values의
    입력이 된다."""
    matched_value = value
    if spec.value_type == "ordinal" and spec.value_order:
        if value in spec.value_order:
            return True, None, matched_value
        candidates = [v for v in spec.value_order if value and value in v]
        if len(candidates) == 1:
            return True, None, candidates[0]
        return False, f"'{value}'는 {spec.column}의 유효 값 범위에 없습니다 (유효 값: {spec.value_order})", matched_value
    return True, None, matched_value


def resolve_ordinal_matched_values(spec: AttributeSpec, operator: str, value: str, value_2: str = "") -> list[str] | None:
    """ordinal 타입 조건(신용등급, 위험등급 등)이 실제로 어떤 원시 문자열
    값들과 일치하는지 미리 계산한다.

    [왜 필요한가] SQL 생성을 LLM에게 통째로 맡기면 "AA- 이상"을 CASE
    WHEN 없이 crd_grd > 'AA-' 같은 문자열 비교로 써버리는 경우가 있다.
    알파벳 순서는 신용등급 순서와 다르기 때문에(예: 'BB+'가 알파벳상
    'AA-'보다 크다고 잘못 포함됨) 이건 틀린 SQL이다. value_order가 이미
    정확한 순위를 담고 있으므로, "AA- 이상"이 정확히 어떤 문자열들을
    가리키는지 여기서 파이썬으로 결정론적으로 계산해서 명시적인 값
    목록(IN 리스트)으로 넘긴다. LLM은 이 목록을 그대로 옮겨 쓰기만
    하면 되므로 순서를 잘못 해석할 여지가 없다.

    [value_order 방향 규약] rdb_schema.AttributeSpec.value_order는 항상
    오름차순(자연어의 "더 크다/좋다/높다"의 반대쪽이 index 0)으로
    정의되어 있다고 가정한다. 그래서 gte(이상)는 value_order[idx:](이
    값과 같거나 더 큰 쪽 전부), lte(이하)는 value_order[:idx+1](이 값과
    같거나 더 작은 쪽 전부)로 고정해서 계산한다. 카탈로그 쪽에서 이
    방향을 지키지 않으면(내림차순으로 넣으면) 결과가 뒤집힌다 -
    rdb_schema.py의 AttributeSpec.value_order 필드 주석 참고.

    value가 value_order 안에 없으면(검증되지 않은 값) None을 돌려준다.
    호출부가 이미 validate_ordinal_value로 검증을 마친 값만 넘기는
    것을 전제로 한다."""
    order = spec.value_order
    if not order or value not in order:
        return None
    idx = order.index(value)
    if operator == "eq":
        return [value]
    if operator == "gte":
        return order[idx:]
    if operator == "gt":
        return order[idx + 1:]
    if operator == "lte":
        return order[: idx + 1]
    if operator == "lt":
        return order[:idx]
    if operator in {"ne", "neq"}:
        return [item for item in order if item != value]
    if operator == "between":
        if value_2 not in order:
            return None
        idx2 = order.index(value_2)
        lo, hi = sorted([idx, idx2])
        return order[lo : hi + 1]
    return None


# ---------------------------------------------------------------------------
# 3) 해석된 스키마 조립
# ---------------------------------------------------------------------------
def build_resolved_schema(step: dict, concept_to_spec: dict[str, AttributeSpec], unresolved: list[str]) -> dict:
    """컬럼 매핑 + 값 검증까지 끝난 조건/정렬/필드 구조를 만든다.
    unresolved_concepts나 invalid_conditions가 비어 있지 않으면
    SQL을 생성하면 안 된다는 신호다(호출부가 판단)."""
    domain = step["domain"]
    entry = rdb_schema.get_domain_entry(domain)
    table = entry["table"]

    resolved_conditions = []
    invalid_conditions = []
    notes: list[str] = []

    # subtype은 개념명 경유가 아니라 값 단위로 직접 컬럼을 찾는다(위
    # resolve_subtype_conditions 참고). 이미 컬럼까지 정해진 채로 오므로
    # 아래 일반 조건 루프(카탈로그/LLM 폴백 대상)와 섞이지 않게 먼저
    # resolved_conditions에 바로 얹는다.
    subtype_records, subtype_notes = resolve_subtype_conditions(domain, step.get("subtype") or [])
    unverified_subtypes = []
    identity_lookup = bool(step.get("product_name_entities")) and not step.get("conditions") and not step.get("sort")
    if identity_lookup:
        # The planner sometimes invents a classification of a named product.
        # We can still return identity-matched source rows, but cannot claim that
        # an unsupported classification/filter has been verified.
        unverified_subtypes = [r["value"] for r in subtype_records if not r["valid"]]
        subtype_records = [r for r in subtype_records if r["valid"]]
        if unverified_subtypes:
            notes.append(f"상품식별에 의한 참고 조회입니다. 하위유형 {unverified_subtypes}은 검증되지 않았으며 해당 분류 조건을 충족한다고 판단하면 안 됩니다.")
    resolved_conditions.extend(subtype_records)
    invalid_conditions.extend(record for record in subtype_records if not record["valid"])
    notes.extend(subtype_notes)

    for c in build_condition_list(step):
        # 방어적 검증: value가 비어 있으면 절대 SQL까지 내려가면 안 된다.
        # 가장 흔한 원인은 질문 분석 단계가 "가장 큰/최고/최소" 같은
        # 최상급 표현을 conditions로 잘못 분류한 경우다(정상적으로는
        # sort로 가야 한다). 여기서 걸러서 명확한 이유를 남기지 않으면,
        # 이 조건이 그대로 SQL 생성 LLM에 "attribute eq ''" 형태로
        # 넘어가고, 숫자 컬럼에 빈 문자열을 비교하는 SQL이 만들어져
        # Postgres 실행 단계에서야 알아보기 힘든 타입 오류로 터진다.
        if c.get("value") is None or not str(c.get("value", "")).strip():
            record = {**c, "column": None, "spec": None, "valid": False,
                      "invalid_reason": "조건 값이 비어 있어 필터를 확정할 수 없습니다."}
            invalid_conditions.append(record)
            resolved_conditions.append(record)
            continue

        spec = concept_to_spec.get(c["attribute"])
        record = {
            "attribute": c["attribute"],
            "operator": c["operator"],
            "value": c["value"],
            "value_2": c.get("value_2", ""),
            "column": spec.column if spec else None,
            "spec": spec,
            "valid": True,
            "invalid_reason": None,
            "matched_values": None,
            "org_name_variants": None,
            "any_group": c.get("any_group"),
            "entity_identity": c.get("entity_identity", False),
        }
        if spec is not None:
            valid, reason, matched_val = validate_ordinal_value(spec, c["value"])
            record["value"] = matched_val
            record["valid"] = valid
            record["invalid_reason"] = reason
            if not valid:
                invalid_conditions.append(record)
            elif spec.value_type == "ordinal":
                # value_2도(between일 때) 같은 방식으로 정식 표기로 맞춘다.
                value_2_raw = c.get("value_2", "")
                matched_value_2 = ""
                if c["operator"] == "between":
                    v2_valid, reason, matched_value_2 = validate_ordinal_value(spec, value_2_raw)
                    if not v2_valid:
                        record["valid"] = False
                        record["invalid_reason"] = reason
                        invalid_conditions.append(record)
                    else:
                        record["value_2"] = matched_value_2
                # "AA- 이상"이 실제로 어떤 문자열 전부를 가리키는지 여기서
                # 미리 계산해서 못박는다. SQL 생성 LLM은 이 목록을 그대로
                # IN(...)에 옮기기만 하면 되고, 순서/방향을 직접 판단할
                # 필요가 없다.
                record["matched_values"] = resolve_ordinal_matched_values(
                    spec, c["operator"], matched_val, matched_value_2
                )
            elif spec.is_organization_name:
                # "SK하이닉스"(질문에서 흔한 통칭) vs "에스케이하이닉스(주)"
                # (RDB 원본 표기) 같은 표기 차이로 exact match가 0건 되는
                # 사고를 막는다(실측, 2026-09-02). 검증된 약칭표 안의
                # 치환만 쓰므로 편집거리/유사도 대체가 아니다.
                variants = graph_ids.expand_organization_aliases(matched_val)
                if len(variants) > 1:
                    record["org_name_variants"] = variants
        resolved_conditions.append(record)

    sort_in = step.get("sort") or {}
    resolved_sort = None
    if sort_in.get("attribute"):
        spec = concept_to_spec.get(sort_in["attribute"])
        resolved_sort = {
            "attribute": sort_in["attribute"],
            "column": spec.column if spec else None,
            "order": sort_in.get("order") or "asc",
            "limit": sort_in.get("limit", ""),
            "spec": spec,
        }

    resolved_fields = []
    # "상품명"을 fields 목록 맨 앞에 항상 포함한다(role=target일 때).
    # 질문이 fields에 명시적으로 상품명을 요청하지 않아도(대부분 안 한다
    # - "순자산이 가장 큰 상품"이라고 하지 "상품명과 순자산을"이라고
    # 묻지 않는다), 결과 행을 식별할 방법이 없으면 답으로 쓸 수 없다.
    field_names = list(step.get("fields", []))
    if step.get("role", "target") == "target" and "상품명" not in field_names:
        field_names = ["상품명"] + field_names

    # conditions/sort에 실제로 쓰이는 개념이 미해결이면 그 단계 전체를
    # 막아야 한다(필터링 자체가 깨지므로). 반면 output_requirements.fields는
    # "결과에 곁들여 보여주면 좋은 값" 수준이라, 그중 하나를 컬럼에
    # 대응시키지 못했다고 질문 전체를 답변불가로 만들면 안 된다 - 실측
    # (2026-09-02, "SK하이닉스가 발행한 채권과 SK하이닉스를 편입한 ETF"
    # 질문)으로 확인됐다: LLM이 fields에 "ETF 상세 정보"처럼 실제로
    # 대응하는 컬럼이 없는 문구를 넣는 사례가 있었는데, 조건(발행사=
    # SK하이닉스)까지 멀쩡한 단계가 그 필드 하나 때문에 통째로 스킵됐다.
    # 그래서 fields에서만 쓰이는(조건·정렬에는 안 쓰이는) 미해결 개념은
    # SELECT에서 조용히 빼고, "이 단계를 막을지" 판단은 blocking_concepts
    # (조건·정렬·강제 상품명)에 실제로 걸린 미해결 개념만으로 한다.
    blocking_concepts = {c["attribute"] for c in build_condition_list(step)}
    if sort_in.get("attribute"):
        blocking_concepts.add(sort_in["attribute"])
    if step.get("role", "target") == "target":
        blocking_concepts.add("상품명")

    for f in field_names:
        if catalog_sql.normalize(f) in PROVENANCE_CONCEPTS:
            notes.append(f"'{f}'는 단일 컬럼으로 추측하지 않고 DB 메타의 원본 기준일 컬럼들을 함께 조회합니다.")
            continue
        spec = concept_to_spec.get(f)
        if spec is None and f in unresolved and f not in blocking_concepts:
            notes.append(f"요청된 필드 '{f}'는 대응하는 컬럼을 찾지 못해 결과에서 제외했습니다.")
            continue
        resolved_fields.append({"attribute": f, "column": spec.column if spec else None, "spec": spec})

    blocking_unresolved = [c for c in unresolved if c in blocking_concepts]

    # 이 단계가 실제로 쓰는 AttributeSpec 중 join_table이 채워진 것들을
    # 전부 모아 JOIN 절을 조립한다. 같은 보강 테이블을 여러 조건/필드가
    # 같이 쓰면(예: 총보수율 조건 + 총보수율 정렬) 중복 JOIN을 만들지
    # 않도록 join_table 기준으로 한 번만 등록한다.
    joins: list[str] = []
    seen_join_tables: set[str] = set()

    def _register_join(spec: AttributeSpec | None) -> None:
        if spec and spec.join_table and spec.join_table not in seen_join_tables:
            seen_join_tables.add(spec.join_table)
            joins.append(f"LEFT JOIN {spec.join_table} AS {spec.join_alias} ON {spec.join_on}")

    for c in resolved_conditions:
        _register_join(c.get("spec"))
    if resolved_sort:
        _register_join(resolved_sort.get("spec"))
    for f in resolved_fields:
        _register_join(f.get("spec"))

    return {
        "domain": domain,
        "table": table,
        "subtype": list(step.get("subtype") or []),
        "unverified_subtypes": unverified_subtypes,
        "conditions": resolved_conditions,
        "sort": resolved_sort,
        "fields": resolved_fields,
        "unresolved_concepts": blocking_unresolved,
        "invalid_conditions": invalid_conditions,
        "notes": notes,
        "joins": joins,
    }


def format_resolved_schema(resolved_schema: dict, apply_limit: bool = True, union_mode: bool = False) -> str:
    """resolved_schema를 SQL 생성 LLM에 보여줄 한국어 텍스트로 정리한다.

    apply_limit=False면 "이 결과는 나중에 다른 도메인과 합쳐져서 다시
    정렬되니 LIMIT을 넣지 말라"는 문구를 덧붙인다. 여러 product_domain을
    한 번에 조회하는 교차질의(route.needs_merge_rank=True)에서, 도메인
    하나의 SQL에 LIMIT을 걸어버리면 합친 뒤의 진짜 TOP N에 들어갈 행이
    미리 잘려나갈 수 있기 때문이다.

    union_mode=True면(§9, route.merge_group_step_ids에 속한 단계) "완결된
    SELECT문"이 아니라 nodes.py의 _execute_merged_target_group이 Python
    에서 UNION ALL로 이어붙일 서브쿼리 하나를 만들라는 지시로 바뀐다 -
    SELECT 목록을 상품코드/상품명/도메인(리터럴)/정렬값 4개 별칭으로
    고정하고(도메인마다 컬럼 구성이 달라도 UNION은 컬럼 수·순서가
    같아야 한다), ORDER BY/LIMIT은 절대 넣지 말라고 명시한다(바깥쪽
    UNION 전체 쿼리가 정렬·절단을 전담한다). apply_limit은 union_mode일
    때 항상 False와 같은 효과이므로 별도로 확인하지 않는다."""
    joins = resolved_schema.get("joins") or []
    has_joins = bool(joins)

    def _qualify(column: str | None) -> str | None:
        """JOIN이 하나라도 있는 쿼리에서, 별칭이 아직 안 붙은(기본 테이블)
        컬럼에 "base." 접두어를 붙인다. 보강 테이블 컬럼(예: ee.charge_rt_final)은
        AttributeSpec.column에 이미 별칭이 박혀 있으므로("." 포함) 손대지
        않는다. JOIN이 없는 쿼리(절대다수)는 이 함수가 아무것도 안 바꾸고
        예전과 완전히 같은 텍스트를 만든다."""
        if not has_joins or not column or "." in column:
            return column
        return f"base.{column}"

    if has_joins:
        lines = [f"테이블: {resolved_schema['table']} AS base"]
        for j in joins:
            lines.append(f"  {j}")
    else:
        lines = [f"테이블: {resolved_schema['table']}"]
    lines.append("조건:")

    for c in resolved_schema["conditions"]:
        spec: AttributeSpec | None = c["spec"]
        column = _qualify(c["column"])
        line = f"  - {c['attribute']} {c['operator']} {c['value']!r} -> 컬럼 {column}"
        if spec:
            line += f" (value_type={spec.value_type})"
            if c.get("matched_values") is not None:
                # ordinal 조건은 "이상/이하가 정확히 어떤 값들을 가리키는지"를
                # 이미 파이썬이 계산해 뒀다. SQL 작성 LLM은 이 목록을 그대로
                # IN(...)에 옮기기만 하면 된다 - CASE WHEN으로 순위를 직접
                # 만들거나 문자열을 그대로 부등호 비교하면 안 된다(알파벳
                # 순서가 실제 등급 순서와 다르다).
                values_repr = ", ".join(repr(v) for v in c["matched_values"])
                line += (
                    f"\n    이 조건이 실제로 가리키는 값은 이미 계산되어 있다. "
                    f"SQL에서 반드시 이렇게 쓴다: {column} IN ({values_repr})"
                    f"\n    (직접 부등호로 비교하거나 CASE WHEN을 새로 만들지 말 것 - "
                    f"문자열 알파벳 순서는 실제 등급 순서와 다르다.)"
                )
            elif c.get("org_name_variants"):
                # 회사/기관명은 "SK하이닉스"(질문 통칭)와 "에스케이하이닉스(주)"
                # (원본 표기)처럼 검증된 약칭표 기준으로 다르게 적혀 있을 수
                # 있다. 이미 계산해 둔 변형 후보 중 하나라도 부분일치하면
                # 매치되게 한다 - 정확히 일치(=)시키면 법인격 접미사·표기
                # 차이 때문에 0건이 나올 수 있다(실측 확인).
                variants_repr = ", ".join(repr(v) for v in c["org_name_variants"])
                line += (
                    f"\n    이 조직명은 표기가 다를 수 있다(검증된 약칭표 기준 변형 후보: "
                    f"{variants_repr}). 정확히 일치(=)시키지 말고, 이 변형 후보 각각에 대해 "
                    f"TRIM({column}) LIKE '%변형%' 조건을 OR로 묶어서 하나라도 포함되면 "
                    f"매치되게 하라(편집거리로 새 이름을 지어내지 말고 반드시 위 변형 후보만 쓸 것)."
                )
            elif spec.value_order:
                line += f", 값 순서(낮은 값부터): {spec.value_order}"
            if spec.true_condition:
                line += f", 참 조건: {column} {spec.true_condition}"
            if spec.note:
                line += f"\n    참고: {spec.note}"
        lines.append(line)

    if resolved_schema["sort"] and not union_mode:
        s = resolved_schema["sort"]
        sort_column = _qualify(s["column"])
        lines.append(f"정렬: {s['attribute']} -> 컬럼 {sort_column}, {s['order']}")
        # PostgreSQL은 DESC 정렬에서 NULL을 "가장 큰 값"으로 취급해 맨
        # 앞으로 보낸다(ASC는 반대로 맨 뒤). 정렬 기준 컬럼에 NULL이
        # 조금이라도 있으면, LIMIT과 결합했을 때 최댓값/최솟값 대신 NULL
        # 행이 뽑히는 사고가 난다. note에 결측 언급이 있을 때만이 아니라
        # sort가 있으면 항상, 조건 없이 이 지시를 내린다 - "최댓값을
        # 찾으려면 NULL도 봐야 한다"처럼 LLM이 그럴듯하지만 틀리게
        # 추론하는 경우가 실제로 있었다.
        lines.append(
            f"  주의: PostgreSQL은 DESC 정렬에서 NULL을 가장 큰 값으로 취급해 맨 앞에 "
            f"둔다(ASC는 맨 뒤). {sort_column}에 NULL이 하나라도 있으면 최댓값/최솟값 대신 "
            f"NULL 행이 뽑힐 수 있으므로, WHERE 절에 반드시 {sort_column} IS NOT NULL을 "
            f"추가한 뒤 정렬하세요. \"NULL도 포함해서 최댓값을 찾는다\"는 식으로 판단하지 "
            f"마세요 - NULL은 비교 대상 값이 아니라 결측입니다."
        )
        if s["spec"] and s["spec"].value_type == "ordinal" and s["spec"].value_order:
            lines.append(
                f"  이 컬럼은 ordinal이라 알파벳/문자열 순서로 정렬하면 안 된다. "
                f"CASE WHEN으로 아래 목록의 순서대로 0부터 순번을 매긴 뒤 그 순번으로 정렬한다"
                f"(목록의 앞쪽일수록 작은 순번): {s['spec'].value_order}"
            )
        if s.get("limit") and apply_limit:
            lines.append(f"  결과 개수 제한: 상위 {s['limit']}개 (SQL에 LIMIT {s['limit']} 포함)")
        elif s.get("limit") and not apply_limit:
            lines.append(
                f"  주의: 원래 상위 {s['limit']}개 제한이 있지만, 이 결과는 다른 도메인 결과와 "
                f"합쳐진 뒤 다시 정렬되므로 이 SQL에는 LIMIT을 넣지 않는다."
            )
        if s["spec"] and s["spec"].note:
            lines.append(f"  참고: {s['spec'].note}")

    if resolved_schema["fields"] and not union_mode:
        fields_desc = ", ".join(f"{f['attribute']}->{_qualify(f['column'])}" for f in resolved_schema["fields"])
        lines.append(
            f"SELECT에 반드시 포함할 필드(전부, 빠짐없이): {fields_desc}\n"
            f"  이 중 상품명은 질문에 명시적으로 요청되지 않았어도 항상 포함된다 - "
            f"결과 행이 어느 상품인지 식별할 수 없으면 답으로 쓸 수 없기 때문이다. "
            f"WHERE나 ORDER BY에만 쓰고 SELECT에서 빠뜨리면 안 된다."
        )

    if union_mode:
        # §9: 여러 도메인의 서브쿼리를 UNION ALL로 합칠 것이므로, 이
        # 서브쿼리 하나만 보고는 알 수 없는 별칭 계약을 명시적으로
        # 강제한다. 도메인마다 실제 컬럼 구성이 다르므로(예: 국내ETF
        # pd_itm_no vs 펀드 itm_no) SELECT 목록을 4개 고정 별칭으로
        # 맞추지 않으면 UNION 자체가 "각 SELECT의 열 개수가 달라야
        # 합니다" 에러로 깨진다.
        code_field = next((f for f in resolved_schema["fields"] if f["attribute"] == "상품코드"), None)
        name_field = next((f for f in resolved_schema["fields"] if f["attribute"] == "상품명"), None)
        sort_column = _qualify(resolved_schema["sort"]["column"]) if resolved_schema["sort"] else None
        domain_literal = resolved_schema["domain"].replace("'", "''")
        lines.append(
            "[UNION ALL 서브쿼리 모드] 이 SELECT는 최종 결과가 아니라, 다른 도메인의 "
            "SELECT문들과 UNION ALL로 합쳐질 조각 하나입니다. SELECT 목록에 반드시 "
            "아래 4개만, 이 순서 그대로, 정확히 이 별칭으로 쓰세요(그 외 필드는 넣지 마세요):\n"
            f"  {_qualify(code_field['column']) if code_field else '(상품코드 컬럼 없음)'} AS code,\n"
            f"  {_qualify(name_field['column']) if name_field else '(상품명 컬럼 없음)'} AS name,\n"
            f"  '{domain_literal}' AS domain,\n"
            f"  {sort_column if sort_column else '(정렬 컬럼 없음)'} AS sort_value\n"
            "이 서브쿼리에는 ORDER BY와 LIMIT을 절대 쓰지 마세요 - 정렬과 개수 제한(TOP N)은 "
            "이 서브쿼리들을 UNION ALL로 합친 바깥쪽 쿼리가 전담합니다. WHERE 절의 조건들은 "
            "평소와 똑같이 그대로 적용하세요."
        )

    caveats = rdb_schema.get_sql_caveats(resolved_schema["domain"])
    if caveats:
        lines.append("이 도메인에서 SQL을 쓸 때 반드시 지켜야 할 주의사항:")
        for c in caveats:
            lines.append(f"  - {c}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 4) Postgres 연결/실행
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

RDB_API_BASE_URL = os.environ.get("RDB_API_BASE_URL", "http://40.82.145.44:8000")
RDB_API_TIMEOUT = float(os.environ.get("RDB_API_TIMEOUT", "30"))
 
 
def get_pg_connection():
    """이름은 호출부 호환을 위해 그대로 뒀다. 실제로는 psycopg2 커넥션이
    아니라 재사용 가능한 requests.Session이다. .close()는 requests.Session에도
    있는 메서드라 호출부의 conn.close() 코드도 그대로 동작한다."""
    import requests
 
    session = requests.Session()
    api_key = os.environ.get("RDB_API_KEY")
    if api_key:
        session.headers["Authorization"] = f"Bearer {api_key}"
    return session

def run_sql(conn, sql: str) -> list[dict]:
    """conn(=requests.Session)으로 POST /db/sql을 호출해 SQL을 실행하고
    행을 dict 목록으로 돌려준다. INSERT/UPDATE 없이 SELECT만 실행한다고
    가정한다.

    [2026-09-02 API 계약 변경 — 담당 팀원 확인] 예전엔 JSON 봉투
    ({"query":..., "sql":..., "params":{}}, Content-Type: application/json)
    를 보냈지만, 서버가 이제 Content-Type: text/plain; charset=utf-8로
    SQL 원문 문자열 그 자체를 요청 바디에 담아 보내야 받는다. 직접 재현해
    확인했다: json=으로 보내면(Content-Type: application/json) HTTP 415로
    즉시 거부되고, Content-Type만 text/plain으로 바꾸고 바디를 JSON 봉투로
    유지해도 서버가 바디를 SQL 원문으로 그대로 읽어버려서 "SELECT/WITH/
    EXPLAIN만 허용합니다"로 거부한다(봉투의 여는 중괄호 `{`가 SELECT로
    시작하지 않는다고 판단됨) - 반드시 봉투 없이 SQL 문자열 자체만 보내야
    한다. 응답 형식은 안 바뀌었다(`rows` 키에 행 목록) - _extract_rows는
    그대로 쓴다."""
    safe_sql = sql.replace('%', '%%')

    print(f"\n[DEBUG] 서버로 전송하는 SQL:\n{sql}\n")

    resp = conn.post(
        f"{RDB_API_BASE_URL}/db/sql",
        data=safe_sql.encode("utf-8"),
        headers={"Content-Type": "text/plain; charset=utf-8"},
        timeout=RDB_API_TIMEOUT,
    )
    if not resp.ok:
        raise RuntimeError(describe_api_error(resp))
    return _extract_rows(resp.json())

def _extract_rows(payload: Any) -> list[dict]:
    """성공 응답 바디에서 행 목록을 뽑는다. 정확한 키 이름이 문서에
    없어서 흔한 형태를 순서대로 시도한다. 실제 응답을 한 번 받아 보면
    이 함수를 확인된 형태 하나로 단순화해야 한다."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("rows", "result", "results", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    raise ValueError(
        f"/db/sql 응답에서 행 목록을 찾지 못했습니다. 실제 응답 형태를 확인하고 "
        f"_extract_rows를 그 형태에 맞게 고치세요. 받은 응답: {payload!r}"
    ) 
 
def describe_api_error(resp) -> str:
    """API 에러 응답을 사람이 읽을 수 있는 설명으로 만든다.

    지금까지 실측으로 확인된 형식이 세 가지라 전부 처리한다
    (2026-08-30 확인):
      1. {"code", "message", "release_id", "details": {"errors": [...]}}
         - 요청 본문 자체가 pydantic 검증에 실패했을 때(예: 필드 길이
           부족). errors 안의 개별 항목은 loc/msg/type/input을 갖는다.
      2. {"detail": "<문자열 하나>"}
         - 라우트 자체의 비즈니스 규칙 위반(예: sparql 필드를 채워
           보냈을 때의 "다른 query 종류" 거부). Swagger 문서의 예시와
           다르게 detail이 배열이 아니라 문자열 하나다.
      3. {"detail": [...]}
         - Swagger 문서에 나온 표준 FastAPI 형식. 실제로 관측되지는
           않았지만 혹시 몰라 남겨 둔다.
    SQL 실행 자체가 틀렸을 때(문법 오류, 존재하지 않는 컬럼)도 이 중
    하나를 쓰는지는 아직 확인되지 않았다."""
    parts = [f"HTTP {resp.status_code}"]
    try:
        body = resp.json()
    except ValueError:
        parts.append(resp.text[:2000])
        return "\n".join(parts)

    if isinstance(body, dict) and "code" in body:
        parts.append(f"{body.get('code')}: {body.get('message')}")
        errors = (body.get("details") or {}).get("errors")
        if isinstance(errors, list):
            for item in errors:
                loc = " -> ".join(str(p) for p in item.get("loc", []))
                parts.append(f"  {loc}: {item.get('msg')} (입력값: {item.get('input')!r})")
    elif isinstance(body, dict) and "detail" in body:
        detail = body["detail"]
        if isinstance(detail, list):
            for item in detail:
                loc = " -> ".join(str(p) for p in item.get("loc", []))
                parts.append(f"  {loc}: {item.get('msg')}")
        else:
            parts.append(str(detail))
    else:
        parts.append(repr(body))
    return "\n".join(parts)

def describe_pg_error(exc: Exception) -> str:
    """이전 psycopg2 버전과의 호환용 별칭. run_sql이 던지는 RuntimeError는
    이미 describe_api_error로 정리된 메시지를 담고 있으므로 str(exc)만
    돌려주면 된다. 호출부에서 describe_pg_error(exc)를 그대로 쓰고 있다면
    수정하지 않아도 되게 하려고 이름을 남겨 뒀다."""
    return str(exc)
