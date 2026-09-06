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
from datetime import datetime
from decimal import Decimal
from typing import Any

from agent.graph_logic import graph_ids
from agent.evidence_contract import (
    GRAPH_FIELD_CONCEPTS,
    is_document_evidence_field,
    is_identity_field,
)
from tools import rdb_schema
from tools import catalog_sql
from agent.prompts import COLUMN_RESOLUTION_SYSTEM_PROMPT
from tools.rdb_schema import AttributeSpec
from tools.schemas import COLUMN_RESOLUTION_JSON_SCHEMA


# ---------------------------------------------------------------------------
# 0) 판매가능여부 조건 사전 처리 (rdb_schema.DOMAIN_SALE_POLICY 적용)
# ---------------------------------------------------------------------------
SALE_AVAILABILITY_CONCEPT = "판매가능여부"
PROVENANCE_CONCEPTS = {"기준일", "각수치의기준일", "데이터갱신일", "데이터업데이트일", "수치갱신일",
                       "수치기준일", "지표기준일", "수익률기준일", "데이터기준일", "수치의갱신일", "aum기준일"}


def is_source_column_request(label: str) -> bool:
    name = catalog_sql.normalize(label)
    return (any(s in name for s in ("컬럼", "필드")) and any(s in name for s in ("근거", "출처"))) or name in {"전략원문의출처", "전략원문출처"}


def preserve_explicit_investment_region(intent: dict, question: str) -> tuple[dict, list[str]]:
    """A region directly modifying an asset is exposure, not listing venue.

    Accept only catalogue regions and explicit asset grammar, not product names
    or the broad phrase '미국 ETF' whose venue/exposure is ambiguous.
    """
    text = question
    for entity in intent.get("target_entities") or []:
        if entity.get("entity_type") == "product_name" and entity.get("surface_form"):
            text = text.replace(entity["surface_form"], " ")
    regions = set()
    for entry in _ontology_labels("InvestmentRegion"):
        if entry["label"] in {"해외", "국내외", "글로벌"}:
            continue
        for alias in entry["aliases"]:
            if re.search(r"(?<![가-힣A-Za-z])" + re.escape(alias) + r"\s+(?:주식|채권)(?:형|에\s*투자|\s*투자)?", text):
                regions.add(entry["label"])
    if len(regions) != 1:
        return intent, []
    region = next(iter(regions))
    conditions = list(intent.get("conditions") or [])
    added = []
    for domain in intent.get("product_domain") or []:
        name = domain.get("domain")
        if name not in rdb_schema.ETF_CLASSIFICATION_AXES:
            continue
        relevant = [c for c in conditions if c.get("domain") in {None, "", name} and
                    catalog_sql.normalize(c.get("attribute", "")) == "투자지역"]
        if not relevant:
            conditions.append({"domain": name, "attribute": "투자지역", "operator": "eq", "value": region, "value_2": ""})
            added.append(f"'{region} 주식/채권'의 명시적 투자지역 조건 보존: {name}. 상장시장과 구분합니다.")
    return ({**intent, "conditions": conditions}, added) if added else (intent, [])


def preserve_overseas_exposure_scope(intent: dict, question: str) -> tuple[dict, list[str]]:
    text = re.sub(r"\s+", "", question)
    match = re.search(r"해외(주식|채권)에투자", text)
    if not match or re.search(r"해외ETF|해외상장|외국상장|미국상장", text):
        return intent, []
    domains = intent.get("product_domain") or []
    if len(domains) != 1 or domains[0].get("domain") != "해외ETF":
        return intent, []
    conditions = list(intent.get("conditions") or [])
    domestic = [{**c, "domain": "국내ETF"} for c in conditions if c.get("domain") == "해외ETF"]
    domestic.extend([{"domain": "국내ETF", "attribute": "투자자산유형", "operator": "eq", "value": match[1], "value_2": ""},
                     {"domain": "국내ETF", "attribute": "투자지역", "operator": "ne", "value": "국내", "value_2": ""}])
    sort = dict(intent.get("sort") or {})
    if sort.get("domains"):
        sort["domains"] = list(dict.fromkeys([*sort["domains"], "국내ETF"]))
    fixed = {**intent, "conditions": conditions + domestic, "sort": sort,
             "product_domain": [*domains, {"domain": "국내ETF", "subtype": list(domains[0].get("subtype") or [])}]}
    return fixed, ["'해외 자산에 투자'는 해외 상장과 다르므로 국내 상장 ETF 후보도 조회합니다. 해외 상장 범위는 유지하며 통화·수익률 미지원 조건을 숨기지 않습니다."]


def restore_shared_theme_scope(intent: dict, question: str) -> tuple[dict, list[str]]:
    if intent.get("relations"):
        return intent, []
    domains = intent.get("product_domain") or []
    normalized_question = catalog_sql.normalize(question)
    theme_labels = {catalog_sql.normalize(a) for entry in _ontology_labels("Theme") for a in entry["aliases"]}
    topics = []
    for domain in domains:
        for subtype in domain.get("subtype") or []:
            key = catalog_sql.normalize(subtype)
            if (len(key) >= 2 and any(key in label for label in theme_labels)
                    and key + "에투자" in normalized_question
                    and rdb_schema.resolve_subtype_condition(domain["domain"], subtype) is None):
                topics.append(subtype)
    topics = list(dict.fromkeys(topics))
    if not topics:
        return intent, []
    shared = "통합" in question or bool(re.search(r"ETF(?:와|·|및)(?:공모)?펀드", normalized_question, re.IGNORECASE))
    relations, conditions, fixed_domains = [], list(intent.get("conditions") or []), []
    for domain in domains:
        relevant = topics if shared else [s for s in topics if s in domain.get("subtype", [])]
        fixed_domains.append({**domain, "subtype": [s for s in domain.get("subtype") or [] if s not in relevant]})
        for topic in relevant:
            relations.append({"id": f"theme{len(relations)+1}", "relation": "has_theme", "subject_domain": domain["domain"],
                              "object_entity": topic, "object_ref": "", "entity_role": "theme"})
            for region in _ontology_labels("InvestmentRegion"):
                label = region["label"]
                if catalog_sql.normalize(label + topic + "에투자") in normalized_question:
                    conditions.append({"domain": domain["domain"], "attribute": "투자지역", "operator": "eq", "value": label, "value_2": ""})
    return {**intent, "product_domain": fixed_domains, "conditions": conditions, "relations": relations}, [
        "원문 투자 주제와 TBox 테마 명칭을 대조하여 각 상품군에 분류 연결 조건을 적용합니다. 분류는 실제 편입을 대신하지 않습니다. 해당 상품군의 연결이 없으면 전체 상품 조회로 확대하지 않습니다."]


def lookup_product_identities(names: list[str]) -> list[dict]:
    from tools import schema_snapshot
    snap = schema_snapshot.get_snapshot()
    queries = []
    for name in list(dict.fromkeys(names))[:8]:
        for domain, columns in rdb_schema.PRODUCT_IDENTITY_COLUMNS.items():
            table = rdb_schema.get_domain_entry(domain)["table"]
            catalog = rdb_schema.get_attribute_catalog(domain)
            code, product_name = catalog["상품코드"].column, catalog["상품명"].column
            schema_snapshot.assert_contract(column_refs=[(table, c) for c in (*columns, code, product_name)], snapshot=snap)
            value = catalog_sql.literal(catalog_sql.normalize(name))
            terms = [f"LOWER(REPLACE({c}::text, ' ', '')) = {value}" for c in columns]
            queries.append(f"(SELECT {catalog_sql.literal(name)} AS query_name, {catalog_sql.literal(domain)} AS domain, "
                           f"{code} AS code, {product_name} AS name FROM {table} WHERE "
                           + " OR ".join(terms) + " LIMIT 2)")
    if not queries:
        return []
    conn = get_pg_connection()
    try:
        return run_sql(conn, "SELECT * FROM (" + " UNION ALL ".join(queries) + ") AS identities")
    finally:
        conn.close()


def resolve_named_product_domains(intent: dict) -> tuple[dict, list[str]]:
    names = [e.get("surface_form", "") for e in intent.get("target_entities") or []
             if e.get("entity_type") == "product_name" and e.get("surface_form")]
    if not names or len(names) > 8 or intent.get("relations"):
        return intent, []
    try:
        evidence = lookup_product_identities(names)
    except Exception as exc:
        return intent, [f"상품 도메인 원천 대조 미실행: {type(exc).__name__}; 기존 분석 유지"]
    domains = []
    for name in names:
        matched = {r["domain"] for r in evidence if r.get("query_name") == name}
        if len(matched) != 1:
            return intent, [f"상품 '{name}'의 도메인을 유일하게 확인하지 못했습니다(정확 일치 {len(matched)}개 도메인)."]
        if next(iter(matched)) not in domains:
            domains.append(next(iter(matched)))
    previous = [d["domain"] for d in intent.get("product_domain") or []]
    if set(previous) == set(domains):
        return intent, []
    if len(previous) > 1:
        return intent, [f"상품 식별 도메인 {domains}; 명시된 복수 도메인 {previous} 비교는 유지합니다."]
    fixed = {**intent, "product_domain": [{"domain": d, "subtype": []} for d in domains]}
    fixed["conditions"] = [{**c, "domain": domains[0]} if len(domains) == 1 and c.get("domain") in previous else dict(c)
                           for c in intent.get("conditions") or []]
    sort = dict(intent.get("sort") or {})
    if sort.get("domains") and set(sort["domains"]) <= set(previous):
        sort["domains"] = domains
    fixed["sort"] = sort
    fixed["identity_evidence"] = evidence
    return fixed, [f"실제 상품 식별 컬럼의 정확 일치로 도메인 보정: {previous} → {domains}; 임의 하위유형 추론 제거"]


def prune_inferred_named_subtypes(intent: dict, question: str) -> tuple[dict, list[str]]:
    entities = [e.get("surface_form", "") for e in intent.get("target_entities") or [] if e.get("entity_type") == "product_name"]
    if not entities or intent.get("relations") or intent.get("conditions") or (intent.get("sort") or {}).get("attribute"):
        return intent, []
    text = catalog_sql.normalize(question)
    for name in entities:
        text = text.replace(catalog_sql.normalize(name), "")
    domains, removed = [], []
    for d in intent.get("product_domain") or []:
        keep = [s for s in d.get("subtype") or [] if catalog_sql.normalize(s) in text]
        removed.extend(s for s in d.get("subtype") or [] if s not in keep)
        domains.append({**d, "subtype": keep})
    return ({**intent, "product_domain": domains}, [f"명명 상품의 원문에 없는 추정 하위유형 제거: {removed}"]) if removed else (intent, [])


def validate_issuer_subjects(intent: dict, question: str) -> tuple[dict, list[str]]:
    if "발행" not in question or not any(d.get("domain") == "채권" for d in intent.get("product_domain") or []):
        return intent, []
    names = [e.get("surface_form") for e in intent.get("target_entities") or []
             if e.get("entity_type") in {"company", "issuer"} and e.get("surface_form")]
    names += [r.get("object_entity") for r in intent.get("relations") or []
              if r.get("relation") in {"issued_by", "issues", "발행"} and r.get("object_entity")]
    names = list(dict.fromkeys(names))[:8]
    if not names:
        return intent, []
    try:
        matches = lookup_product_identities(names)
        for name in names:
            products = [r for r in matches if r.get("query_name") == name]
            if not products:
                continue
            terms = ["LOWER(REPLACE(pd_pbcm,' ',''))=" + catalog_sql.literal(catalog_sql.normalize(v))
                     for v in graph_ids.expand_organization_aliases(name)]
            conn = get_pg_connection()
            try:
                issuers = run_sql(conn, "SELECT DISTINCT pd_pbcm FROM raw.prbd01n001 WHERE " + " OR ".join(terms) + " LIMIT 5")
            finally:
                conn.close()
            if not issuers:
                reason = (f"'{name}'은 원천 상품목록에서 {products[0]['domain']} 상품 "
                          f"{products[0]['name']}({products[0]['code']})으로 확인됐지만 채권 발행사로는 확인되지 않았습니다. "
                          "상품과 발행기관을 동일시할 수 없습니다. 실제 발행사 이름 또는 보유 채권을 묻는 것인지 확인해 주세요.")
                return {**intent, "issuer_type_conflict": reason}, [reason]
    except Exception as exc:
        return intent, [f"발행 주체와 상품 식별자 대조 미완료: {type(exc).__name__}"]
    return intent, []


def preserve_explicit_output_requests(intent: dict, question: str) -> tuple[dict, list[str]]:
    text = catalog_sql.normalize(question.replace("\n", ";"))
    for entity in intent.get("target_entities") or []:
        name = catalog_sql.normalize(entity.get("surface_form") or "")
        if name:
            text = re.sub(re.escape(name), " ", text, flags=re.IGNORECASE)
    names = set(PROVENANCE_CONCEPTS) | GRAPH_FIELD_CONCEPTS
    for domain in intent.get("product_domain") or []:
        name = domain.get("domain", "")
        if name not in rdb_schema.RDB_SCHEMA:
            continue
        names.update(rdb_schema.get_attribute_catalog(name))
        for key, view in rdb_schema.get_output_views(name).items():
            names.update((key, *view["aliases"]))
    normalized_names = {catalog_sql.normalize(name) for name in names}
    recovered = []
    for clause in re.split(r"[.!?;\n]", text):
        normalized = catalog_sql.normalize(clause)
        if re.search(r"(?:제외|빼고|빼줘|생략|말고|말아|필요없)", normalized):
            continue
        request = re.search(r"(?:알려|보여|제시|표시|출력|포함|붙여)", normalized)
        if not request:
            continue
        body = normalized[:request.start()]
        body = re.sub(r"(?:함께|같이|모두|전부|각각)+$", "", body)
        for name in sorted(normalized_names, key=lambda n: (-len(n), n)):
            pattern = re.escape(name) + r"(?=,|，|·|/|과|와|및|을|를|도|$)"
            if re.search(pattern, body):
                recovered.append(name)
                body = re.sub(pattern, " ", body)
    output = dict(intent.get("output_requirements") or {})
    fields = []
    for field in output.get("fields") or []:
        stripped = re.sub(r"^(?:국내ETF|해외ETF|ETF|채권|펀드)\s+", "", field)
        parts = [part.strip() for part in re.split(r"[·/]", stripped)]
        if parts and all(catalog_sql.normalize(part) in normalized_names for part in parts):
            fields.extend(parts)
        else:
            fields.append(field)
    known = {catalog_sql.normalize(f) for f in fields}
    added = []
    for name in recovered:
        if name not in known:
            fields.append(name)
            added.append(name)
            known.add(name)
    if not added and fields == list(output.get("fields") or []):
        return intent, []
    output["fields"] = fields
    return {**intent, "output_requirements": output}, [f"원문 요청 항목 복구: {', '.join(added)}"]


def _ontology_labels(class_name: str):
    from rdflib import RDF, RDFS, SKOS, URIRef
    from tools.graph_schema import FP, catalog
    graph = catalog().graph
    for node in graph.subjects(RDF.type, URIRef(FP + class_name)):
        labels = list(graph.objects(node, RDFS.label))
        preferred = next((str(v) for v in labels if v.language == "ko"), str(node))
        aliases = {str(v) for v in labels + list(graph.objects(node, SKOS.altLabel))}
        yield {"uri": str(node), "label": preferred, "aliases": aliases}


def _ontology_match(class_name: str, value: str) -> dict:
    matches = [entry for entry in _ontology_labels(class_name)
               if value.strip().casefold() in {a.strip().casefold() for a in entry["aliases"]}]
    if len(matches) != 1:
        raise ValueError("온톨로지 분류값이 없거나 여러 개여서 유일하게 확정할 수 없습니다")
    return matches[0]


def categorical_source_values(domain: str, column: str, value: str) -> list[str]:
    axis = rdb_schema.ETF_CLASSIFICATION_AXES.get(domain, {}).get(column)
    if column in {"curr_cd", "pd_curr_cd", "pd_trd_ccy"}:
        axis = "Currency"
        value = {"원화": "한국 원", "한국원화": "한국 원", "달러": "미국 달러"}.get(value, value)
    if not axis:
        return []
    try:
        entry = _ontology_match(axis, value)
    except ValueError:
        return []
    specs = [s for s in rdb_schema.get_attribute_catalog(domain).values() if s.column == column]
    known = {v for s in specs for v in s.known_values}
    aliases = entry["aliases"]
    candidates = known if known else aliases
    return sorted(v for v in candidates if v.strip().casefold() in {a.strip().casefold() for a in aliases})


def _source_date(value):
    text = str(value).strip()
    if re.fullmatch(r"\d{8}\.0+", text):
        text = text.split(".")[0]
    text = text.replace("-", "")
    if text in {"0", "99991231"}:
        raise ValueError("미상/영구채 sentinel 날짜로 잔존만기를 계산할 수 없습니다")
    if not re.fullmatch(r"\d{8}", text):
        raise ValueError("원천 날짜 형식을 확인할 수 없습니다")
    return datetime.strptime(text, "%Y%m%d").date()


def _maturity_class(days: int) -> tuple[dict, str]:
    if days < 0:
        return _ontology_match("MaturityClass", "만기경과"), "만기경과"
    matches = []
    years = Decimal(days) / Decimal(365)
    for entry in _ontology_labels("MaturityClass"):
        for alias in entry["aliases"]:
            match = re.fullmatch(r"(\d+)-(\d+)년", alias)
            less = re.fullmatch(r"(\d+)년미만", alias)
            more = re.fullmatch(r"(\d+)년이상", alias)
            accepted = (match and Decimal(match[1]) <= years < Decimal(match[2])) or (
                less and years < Decimal(less[1])) or (more and years >= Decimal(more[1]))
            if accepted:
                matches.append((entry, alias))
    if len(matches) != 1:
        raise ValueError("온톨로지 만기 구간이 없거나 중복되어 확정할 수 없습니다")
    return matches[0]


def derive_output_views(rows: list[dict], views: list[dict]) -> list[dict]:
    if not views:
        return rows
    output = []
    for source in rows:
        row, items = dict(source), {}
        for view in views:
            columns = view["inputs"]
            item = {"field": view["attribute"], "column": None, "value": None,
                    "status": "available", "source_columns": [f"{view.get('source_table', 'raw.prbd01n001')}.{c}" for c in columns]}
            if view["kind"] == "unsupported":
                item.update(status="derivation_unavailable", detail=view["reason"])
                items[catalog_sql.normalize(view["attribute"])] = item
                continue
            if view["kind"] == "rating_order":
                order = rdb_schema.get_attribute_catalog("채권")["신용등급"].value_order
                item.update(value=" < ".join(order), detail="rdb_schema 신용등급 서열(낮음→높음). AA0·A0 등의 0은 원천 중립등급 표기입니다. 신용평가 보고서 원문을 확보했다는 뜻은 아닙니다.")
                items[catalog_sql.normalize(view["attribute"])] = item
                continue
            if view["kind"] == "return_series":
                parts = []
                for column, period in zip(columns, view["periods"]):
                    value = row.get(column)
                    status = "미조회" if column not in row else "NULL·확인 불가" if value is None else str(value) + "%"
                    parts.append(f"{period}: {status} ({column})")
                item.update(value="; ".join(parts), detail="기간이 지정되지 않은 요청이므로 원천 기간별 수익률을 구분합니다. 임의로 1개월 수익률 하나로 대체하지 않습니다.")
                items[catalog_sql.normalize(view["attribute"])] = item
                continue
            if view["kind"] == "listing":
                try:
                    start, basis = _source_date(row.get("pd_lstg_dt")), _source_date(row.get("cu_upt_dt"))
                    end_raw = str(row.get("pd_lste_dt", "")).strip()
                    end = None if end_raw == "99991231" else _source_date(end_raw)
                    listed = start <= basis and (end is None or basis < end)
                    item.update(value="상장기간 내" if listed else "상장기간 밖", detail=f"상장일 {start}, 상장종료일 {end_raw}, 원천 갱신일 {basis} 대조. 99991231은 종료일 미정 코드이며 현재 매매 가능 여부를 뜻하지 않습니다.")
                except ValueError as exc:
                    item.update(status="derivation_unavailable", detail=str(exc))
                items[catalog_sql.normalize(view["attribute"])] = item
                continue
            if view["kind"] == "identity_keys":
                item.update(value="; ".join(f"{c}={row[c] if row.get(c) is not None else '값 미확보'}" for c in columns),
                            detail="식별·상장 관련 원천키입니다. 서로 다른 레코드의 동일성은 키를 교차 대조한 결과만으로 판정합니다.")
                items[catalog_sql.normalize(view["attribute"])] = item
                continue
            if view["kind"] == "classification":
                parts = []
                for column, axis in view["axes"].items():
                    raw = row.get(column)
                    if column not in row or raw is None or str(raw).strip() == "":
                        parts.append(f"{axis}: {column} 원천값 미확보(분류 확인 불가)")
                        continue
                    try:
                        match = _ontology_match(axis, str(raw))
                        parts.append(f"{column}={raw} → {match['label']} ({match['uri']})")
                    except ValueError:
                        parts.append(f"{column}={raw} → {axis}의 유일한 분류 규칙 미확보")
                item.update(value="; ".join(parts), detail="원천값과 로컬 TBox label/altLabel의 정확 일치. 원격 GraphDB 관계 조회가 아닙니다.")
                items[catalog_sql.normalize(view["attribute"])] = item
                continue
            missing = [c for c in columns if c not in row]
            nulls = [c for c in columns if c in row and row[c] is None]
            empty = [c for c in columns if c in row and isinstance(row[c], str) and not row[c].strip()]
            if missing or nulls or empty:
                item["status"] = "not_selected" if missing else "null" if nulls else "empty"
                item["detail"] = "분류 입력 미확보: " + ", ".join(missing or nulls or empty)
            else:
                try:
                    if view.get("ambiguous"):
                        raise ValueError("어떤 속성의 온톨로지 분류인지 명확하지 않아 확정할 수 없습니다")
                    if view["kind"] == "share_class":
                        match = re.search(r"(?:Class|종류)\s*([A-Za-z][A-Za-z0-9-]*)$", str(row["itm_nm"]), re.IGNORECASE)
                        if not match:
                            raise ValueError("원천 상품명에 명시된 클래스 접미사를 확인할 수 없습니다")
                        item.update(value=match[1], detail=f"원천 상품명 itm_nm={row['itm_nm']}의 명시적 Class/종류 접미사")
                    elif view["kind"] == "rating":
                        entry = _ontology_match("CreditRating", str(row["crd_grd"]))
                        item["value"] = f"{entry['label']} ({entry['uri']})"
                        item["detail"] = (f"신용등급 분류: 원본 crd_grd={row['crd_grd']}; "
                                          "ontology/common.ttl의 CreditRating label/altLabel 일치")
                    else:
                        maturity, basis = _source_date(row["mat_dt"]), _source_date(row["info_base_dt"])
                        days = (maturity - basis).days
                        entry, bucket = _maturity_class(days)
                        item["value"] = f"{entry['label']} ({bucket}; {entry['uri']})"
                        item["detail"] = (f"mat_dt={row['mat_dt']} - info_base_dt={row['info_base_dt']} = {days}일; "
                                          "1년=365일, 하한 포함·상한 미포함; ontology/bond_kr.ttl의 MaturityClass 구간. "
                                          "상환일자 기준 구분이며 콜 행사·법적 만기 조건을 별도로 확정한 것이 아닙니다.")
                    if view["kind"] != "share_class":
                        item["detail"] += " 로컬 온톨로지 규칙 적용 결과이며 원격 GraphDB 조회값이 아닙니다."
                except Exception as exc:
                    item.update(status="derivation_unavailable", detail=str(exc))
            items[catalog_sql.normalize(view["attribute"])] = item
        row["_derived_fields"] = items
        output.append(row)
    return output


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

    concepts.extend(f for f in step.get("fields", []) if catalog_sql.normalize(f) not in PROVENANCE_CONCEPTS
                    and not is_source_column_request(f)
                    and not is_identity_field(f)
                    and not is_document_evidence_field(f)
                    and catalog_sql.normalize(f) not in GRAPH_FIELD_CONCEPTS
                    and not rdb_schema.get_output_view(step.get("domain", ""), f))

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
    conditions: list[dict] = [{key: c[key] for key in ("attribute", "operator", "value", "value_2") if key in c}
                             for c in step.get("conditions", [])]

    for e in step.get("product_name_entities") or []:

        conditions.append({"attribute": "상품명", "operator": "contains", "value": e["surface_form"], "value_2": "", "any_group": "product_names", "entity_identity": True})
        if step.get("domain") == "해외ETF" and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.^-]{0,19}", e["surface_form"]):

            for attribute in ("티커", "상품코드"):
                conditions.append({"attribute": attribute, "operator": "eq", "value": e["surface_form"],
                                   "value_2": "", "any_group": "product_names"})

    for name in step.get("issuer_name_entities") or []:
        conditions.append({"attribute": "발행사", "operator": "eq", "value": name,
                           "value_2": "", "any_group": "graph_issuer_names"})

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
        if not str(value or "").strip():
            continue
        mapped = rdb_schema.resolve_subtype_condition(domain, value)
        if domain in {"국내ETF", "해외ETF"} and value.upper() not in {"ETF", "ETN"}:
            stripped = re.sub(r"\s*(?:ETF|ETN)$", "", value, flags=re.IGNORECASE).strip()
            mapped = mapped or rdb_schema.resolve_subtype_condition(domain, stripped)
            value = stripped
        if domain in {"채권", "펀드"} and value in {"원화", "원화채권", "원화표시"}:
            mapped = {"column": "curr_cd", "operator": "eq", "value": "KRW"}
        if domain in {"국내ETF", "해외ETF"} and value.upper() in {"ETF", "ETN"}:
            mapped = {"column": "pd_grp_no", "operator": "eq", "value": value.upper()}
        if mapped is None:
            candidates = [(column, categorical_source_values(domain, column, value))
                          for column in rdb_schema.ETF_CLASSIFICATION_AXES.get(domain, {})]
            candidates = [(column, values) for column, values in candidates if values]
            if len(candidates) == 1:
                column, values = candidates[0]
                for raw in values:
                    records.append({"attribute": f"상품유형({value})", "operator": "eq", "value": raw,
                                    "value_2": "", "column": column, "spec": None, "valid": True,
                                    "any_group": f"subtype:{value}:{column}", "invalid_reason": None})
                notes.append(f"하위유형 '{value}'를 로컬 온톨로지와 원천 범주로 대조: {column} IN {values}")
                continue
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

    normalized_attr_map = {
        k.replace(" ", "").lower(): v for k, v in attribute_map.items()
    }

    for concept in needed_concepts:

        normalized_concept = concept.replace(" ", "").lower()
        
        spec = attribute_map.get(concept) or normalized_attr_map.get(normalized_concept)
        
        if spec is not None:
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

    subtype_records, subtype_notes = resolve_subtype_conditions(domain, step.get("subtype") or [])
    unverified_subtypes = []
    identity_lookup = bool(step.get("product_name_entities")) and not step.get("conditions") and not step.get("sort")
    if identity_lookup:
        unverified_subtypes = [r["value"] for r in subtype_records if not r["valid"]]
        subtype_records = [r for r in subtype_records if r["valid"]]
        if unverified_subtypes:
            notes.append(f"상품식별에 의한 참고 조회입니다. 하위유형 {unverified_subtypes}은 검증되지 않았으며 해당 분류 조건을 충족한다고 판단하면 안 됩니다.")
    resolved_conditions.extend(subtype_records)
    invalid_conditions.extend(record for record in subtype_records if not record["valid"])
    notes.extend(subtype_notes)

    for c in build_condition_list(step):
        if rdb_schema.get_output_view(domain, c["attribute"]):
            record = {**c, "column": None, "spec": None, "valid": False,
                      "invalid_reason": "출력 전용 분류 항목의 필터는 지원하지 않습니다."}
            invalid_conditions.append(record)
            resolved_conditions.append(record)
            continue

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
            if c["operator"] in {"eq", "ne", "neq"}:
                source_values = categorical_source_values(domain, spec.column, str(c["value"]))
                if source_values:
                    record["category_values"] = source_values
                    notes.append(f"'{c['attribute']}'의 범주값 원천 대조: {c['value']} → {source_values}")
            valid, reason, matched_val = validate_ordinal_value(spec, c["value"])
            record["value"] = matched_val
            record["valid"] = valid
            record["invalid_reason"] = reason
            if not valid:
                invalid_conditions.append(record)
            elif spec.value_type == "ordinal":
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

                record["matched_values"] = resolve_ordinal_matched_values(
                    spec, c["operator"], matched_val, matched_value_2
                )
            elif spec.is_organization_name:

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
        if rdb_schema.get_output_view(domain, sort_in["attribute"]):
            invalid_conditions.append({"attribute": sort_in["attribute"], "value": "정렬",
                                       "invalid_reason": "출력 전용 분류 항목의 정렬은 지원하지 않습니다."})

    resolved_fields = []
    output_views = []
    field_names = list(step.get("fields", []))
    if step.get("role", "target") == "target" and "상품명" not in field_names:
        field_names = ["상품명"] + field_names

    blocking_concepts = {c["attribute"] for c in build_condition_list(step)}
    if sort_in.get("attribute"):
        blocking_concepts.add(sort_in["attribute"])
    if step.get("role", "target") == "target":
        blocking_concepts.add("상품명")

    for f in field_names:
        view = rdb_schema.get_output_view(domain, f)
        if view:
            if catalog_sql.normalize(f) == "온톨로지분류값":
                anchors = [rdb_schema.get_output_view(domain, n) for n in field_names if n != f]
                raw_rating = any(v and v["kind"] == "raw_rating" for v in anchors)
                rating = any(catalog_sql.normalize(n) == "신용등급" for n in field_names)
                maturity = any(v and v["kind"] == "maturity" for v in anchors)
                if maturity and not raw_rating and not rating:
                    view = {**view, "kind": "maturity", "inputs": ("mat_dt", "info_base_dt")}
                elif not raw_rating and (not rating or maturity):
                    view = {**view, "ambiguous": True, "inputs": ()}
            if view["kind"] != "raw_rating":
                output_views.append({"attribute": f, "source_table": table, **view})
                notes.append(f"'{f}'는 원천 입력 조회 후 명시된 출력 규칙을 적용해 산출합니다.")
            for name in view["inputs"]:
                resolved_fields.append({"attribute": f if view["kind"] == "raw_rating" else f"분류근거({name})",
                                        "column": name, "spec": catalog_sql.spec_for_column(domain, name, {})})
            continue
        if (is_identity_field(f) or is_document_evidence_field(f)
                or catalog_sql.normalize(f) in GRAPH_FIELD_CONCEPTS):
            if is_document_evidence_field(f):
                notes.append(f"'{f}'는 RDB 컬럼으로 추측하지 않고 문서 근거 계층에서 확인합니다.")
            continue
        if catalog_sql.normalize(f) in PROVENANCE_CONCEPTS or is_source_column_request(f):
            notes.append(f"'{f}'는 단일 컬럼으로 추측하지 않고 DB 메타의 원본 기준일 컬럼들을 함께 조회합니다.")
            continue
        spec = concept_to_spec.get(f)
        if spec is None and f in unresolved and f not in blocking_concepts:
            notes.append(f"요청된 필드 '{f}'는 대응하는 컬럼을 찾지 못해 결과에서 제외했습니다.")
            continue
        resolved_fields.append({"attribute": f, "column": spec.column if spec else None, "spec": spec})

    blocking_unresolved = [c for c in unresolved if c in blocking_concepts]

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
        "output_views": output_views,
        "class_suffixes": list(step.get("class_suffixes") or []),
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

                values_repr = ", ".join(repr(v) for v in c["matched_values"])
                line += (
                    f"\n    이 조건이 실제로 가리키는 값은 이미 계산되어 있다. "
                    f"SQL에서 반드시 이렇게 쓴다: {column} IN ({values_repr})"
                    f"\n    (직접 부등호로 비교하거나 CASE WHEN을 새로 만들지 말 것 - "
                    f"문자열 알파벳 순서는 실제 등급 순서와 다르다.)"
                )
            elif c.get("org_name_variants"):
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

    return str(exc)
