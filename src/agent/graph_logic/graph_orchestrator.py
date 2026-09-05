"""
질문(+frame) -> schema-grounded GraphLogicalPlan -> SPARQL 실행.

팀원의 gragh-test 노트북 `agent/text2sparql.py`(셀 39)를 이식했다. 원본과
다른 점 두 가지:

1. `frame = frame or query_frame.extract(...)` 폴백을 없앴다. 팀원의 자체
   Query Frame 추출기(`agent/query_frame.py`)는 이식 대상이 아니다 - 우리는
   이미 §2에서 병합한 우리 자신의 intent 스키마(`schemas.py`)를 쓰고, Graph
   엔진이 필요로 하는 최소 모양({"entities":[{"text","role"}]})만 `nodes.py`의
   `graph_search_node`가 relation에서 직접 만들어 넘긴다. 그래서 `frame`은
   이제 선택이 아니라 필수 인자다.
2. 말미의 RDB handoff 블록(`build_etf_rdb_handoff`/`execute_etf_rdb_handoff`
   호출)을 제거했다. 우리 프로젝트의 Graph->RDB 핸드오프는 기존 RDB
   파이프라인(카탈로그 매칭 -> 자연어 초안 -> SQL 생성)에 조건 하나를 얹는
   방식을 쓴다(`nodes.py`의 `rdb_search_node`). 대신 결과 rows에서 상품/증권
   식별 코드로 보이는 컬럼(`*_code`류 alias)을 모아 `entity_codes`로
   반환값에 추가했다 - 이게 그 핸드오프의 입력이 된다.

LLM 호출도 팀원의 자체 `clova.chat(...)` 대신 우리 프로젝트가 이미 쓰는
`get_clova._llm_plan.with_structured_output(...)`으로 바꿨다(나머지 파일과
같은 LLM 클라이언트를 공유하기 위해서다) - 그 외 plan 생성·검증·재시도
로직 자체는 그대로다.
"""
from __future__ import annotations

import json
from collections.abc import Callable

from agent.graph_logic import graph_engine
from agent.get_clova import _llm_plan
from agent.graph_logic.graph_entity import resolve_entity, resolve_frame_seed
from agent.graph_logic.graph_plan import (
    _ID,
    company_holding_etf_plan,
    compile_graph_plan,
    subsidiary_holding_etf_plan,
    subsidiary_relation_plan,
    theme_membership_plan,
    validate_graph_plan,
)
from tools.graph_schema import FP, SchemaFragment, catalog, compact_uri, expand_uri
from agent.prompts import GRAPH_PLAN_SYSTEM


MAX_CORRECTIONS = 3
SNAPSHOT_AS_OF_RULE = "snapshot@2026-08-24"


def _plan_json_schema(fragment: SchemaFragment) -> dict:
    """GraphLogicalPlan 구조화 출력 스키마. fragment가 허용하는 class/property
    만 enum으로 좁혀서, LLM이 schema fragment 밖의 값을 지어내지 못하게 한다.

    node id에 정규식(`_ID.pattern`)을 "pattern" 키워드로 강제하지 않고
    description 문구로만 안내한다 - 일부 구조화 출력 API가 pattern 키워드
    자체를 거부하는 사례가 팀원 쪽에서 실측됐다(HTTP 400). id 계약은
    GRAPH_PLAN_SYSTEM 규칙 7과 `_sanitize_plan`(아래) 두 곳에서 강제한다."""
    classes = [compact_uri(x) for x in fragment.classes]
    object_properties = [compact_uri(x.uri) for x in fragment.properties if x.kind == "object"]
    # rdfs:label 은 TBox datatype property 가 아니지만 분류 개체(fp:InvestmentRegion
    # 등)의 이름을 얻는 유일한 경로다. graph_plan 이 catalog 검사를 면제한다.
    datatype_properties = [compact_uri(x.uri) for x in fragment.properties
                           if x.kind == "datatype"] + ["rdfs:label"]
    node_id = {"type": "string", "description": _ID.pattern}
    return {
        "title": "graph_logical_plan",
        "type": "object",
        "properties": {
            "nodes": {"type": "array", "maxItems": 9, "items": {
                "type": "object",
                "properties": {
                    "id": dict(node_id),
                    "class_uri": {"type": "string", "enum": classes},
                },
                "required": ["id", "class_uri"],
            }},
            "edges": {"type": "array", "maxItems": 8, "items": {
                "type": "object",
                "properties": {
                    "subject": dict(node_id),
                    "predicate": {"type": "string", "enum": object_properties},
                    "object": dict(node_id),
                },
                "required": ["subject", "predicate", "object"],
            }},
            "outputs": {"type": "array", "maxItems": 12, "items": {
                "type": "object",
                "properties": {
                    "node": dict(node_id),
                    "property": {"type": "string", "enum": datatype_properties},
                    "alias": {"type": "string"},
                    "optional": {"type": "boolean"},
                },
                "required": ["node", "property", "alias", "optional"],
            }},
            "limit": {"type": "integer"},
        },
        "required": ["nodes", "edges", "outputs", "limit"],
    }


def _schema_search_text(question: str, frame: dict) -> str:
    parts = [question]
    parts.extend(x.get("text", "") for x in frame.get("requested_fields") or [])
    parts.extend(x.get("field_text", "") for x in frame.get("constraints") or [])
    parts.extend(x.get("raw", "") for x in frame.get("relations") or [])
    return "\n".join(x for x in parts if x)


def _fast_plan(question: str, frame: dict, seed_class: str = "Company") -> tuple[dict | None, list[str]]:
    """"자회사"/"편입" 류 관계는 결정적 plan으로 바로 처리한다(LLM 생성/
    재시도 없이). 원본 질문 텍스트 자체에 이미 "자회사"/"편입" 같은
    한국어 표현이 그대로 들어 있으므로, frame.relations가 비어 있어도
    (우리 어댑터는 이 필드를 채우지 않는다) question 텍스트만으로 정확히
    판정된다.

    [2026-09-02 추가: company_holding_etf_plan 분기] "자회사" 체인 없이
    "<회사>를 편입/보유한 ETF"만 묻는 질문(예: "SK하이닉스를 편입한 ETF")은
    LLM이 GraphLogicalPlan을 직접 생성해야 했는데, 증권->발행기업 역방향
    edge를 자주 틀려 3회 교정 안에 abstain하는 사례가 실측됐다 - 실제로는
    이 관계가 이미 그래프에 있었다(직접 확인, ETF 10건 이상). 자회사류와
    똑같이 결정적 plan으로 처리해서 이 실패를 없앤다."""
    relations = frame.get("relations") or []
    if frame.get("relation_scope"):
        # A question may contain several independent relations. Only this
        # step's dependency chain may decide its path; other clauses are not
        # permission to add a subsidiary or holding edge.
        predicates = {str(r.get("relation", "")).casefold() for r in relations}
        has_subsidiary = bool(predicates & {"subsidiary_of", "has_subsidiary", "자회사"})
        has_holding = bool(predicates & {"holds", "holding", "held_by", "편입", "보유"})
        target = str((relations[-1] if relations else {}).get("subject_domain", "")).casefold()
        etf_target = "etf" in target or (has_holding and not target)
        relation_text = ""
    else:
        relation_text = " ".join([question] + [x.get("raw", "") for x in relations]).casefold()
        has_subsidiary = "자회사" in relation_text or "출자" in relation_text
        has_holding = "편입" in relation_text or "보유" in relation_text or "포함" in relation_text
        etf_target = "etf" in relation_text or "상장지수" in relation_text
    limit = frame.get("limit") or 100
    if not has_subsidiary and not has_holding:
        return None, []
    if has_subsidiary:
        if etf_target and has_holding:
            return subsidiary_holding_etf_plan(limit=max(limit, 100)), [
                "fp:Company", "fp:SubsidiaryRelation", "fp:Security", "fp:Holding",
                "fp:ETF", "fp:Document",
            ]
        return subsidiary_relation_plan(limit=limit), [
            "fp:Company", "fp:SubsidiaryRelation", "fp:Document",
        ]
    if etf_target:
        plan = company_holding_etf_plan(limit=max(limit, 100))
        if seed_class == "Security":
            plan["nodes"] = [{**n, "id": "seed"} if n["id"] == "security" else n
                             for n in plan["nodes"] if n["id"] != "seed"]
            plan["edges"] = [{**e, "object": "seed"} if e["object"] == "security" else e
                             for e in plan["edges"] if e["predicate"] != "fp:issuedByCompany"]
        elif seed_class != "Company":
            return None, []
        return plan, [
            "fp:Company", "fp:Security", "fp:Holding", "fp:ETF", "fp:Document",
        ]
    return None, []


def _sanitize_alias(plan: dict, trace: list[str] | None = None) -> dict:
    """output alias 계약(`_ID`)만 결정적으로 복구한다.

    alias는 SELECT 변수명일 뿐 plan 안 어디서도 참조되지 않으므로 개명이
    안전하다. 한글·빈 문자열 alias 때문에 correction 예산이 통째로 날아가는
    사례가 팀원 쪽에서 반복됐다."""
    outputs = [x for x in plan.get("outputs") or [] if isinstance(x, dict)]
    if all(_ID.fullmatch(str(x.get("alias", ""))) for x in outputs):
        return plan
    taken = {str(x.get("alias", "")) for x in outputs if _ID.fullmatch(str(x.get("alias", "")))}
    taken |= {str(n.get("id", "")) for n in plan.get("nodes") or [] if isinstance(n, dict)}
    fixed, counter = [], 0
    for output in outputs:
        alias = str(output.get("alias", ""))
        if _ID.fullmatch(alias):
            fixed.append(output)
            continue
        counter += 1
        while f"out{counter}" in taken:
            counter += 1
        taken.add(f"out{counter}")
        if trace is not None:
            trace.append(f"plan sanitize alias: {alias!r} -> out{counter}")
        fixed.append({**output, "alias": f"out{counter}"})
    return {**plan, "outputs": fixed}


def _sanitize_plan(plan: dict, entity: dict, trace: list[str] | None = None) -> dict:
    """node id 계약(`_ID` + seed 1개)만 결정적으로 복구한다.

    HCX가 node id에 해소된 URI(`<http://mafest.ai/instance/...>`)를 그대로
    넣어 self-correction 예산이 전부 "허용하지 않는 node id"·"seed node 없음"
    으로 끝나는 사례가 팀원 쪽에서 반복됐다. 여기서 고치는 것은 id
    표기뿐이며 class·predicate·방향은 건드리지 않는다. seed를 유일하게
    특정하지 못하면 개명하지 않고 validator 오류를 그대로 내보낸다."""
    if not isinstance(plan, dict):
        return plan
    plan = _sanitize_alias(plan, trace)
    nodes = [node for node in plan.get("nodes") or [] if isinstance(node, dict)]
    if not nodes:
        return plan

    rename: dict[str, str] = {}
    used = {str(node.get("id", "")) for node in nodes
            if _ID.fullmatch(str(node.get("id", "")))}

    if "seed" not in used:
        # ① 원래 id 문자열이 해소된 URI/정식명을 품고 있으면 그 node가 seed다.
        marks = [str(entity.get(key) or "") for key in ("uri", "canonical_name")]
        hits = [str(node.get("id", "")) for node in nodes
                if any(mark and mark in str(node.get("id", "")) for mark in marks)]
        if len(hits) != 1:
            # ② class가 해소된 엔티티와 호환되는 node가 유일할 때만 seed로 본다.
            entity_class = entity.get("class_uri") or ""
            hits = [str(node.get("id", "")) for node in nodes
                    if entity_class and catalog().compatible(
                        entity_class, {str(expand_uri(str(node.get("class_uri", ""))))})]
        if len(hits) == 1:
            rename[hits[0]] = "seed"
            used.add("seed")

    counter = 0
    for node in nodes:
        old = str(node.get("id", ""))
        if old in rename or _ID.fullmatch(old):
            continue
        counter += 1
        while f"n{counter}" in used:
            counter += 1
        rename[old] = f"n{counter}"
        used.add(f"n{counter}")

    if not rename:
        return plan

    def sub(value: object) -> str:
        return rename.get(str(value), str(value))

    out = dict(plan)
    out["nodes"] = [{**node, "id": sub(node.get("id"))} for node in nodes]
    out["edges"] = [{**edge, "subject": sub(edge.get("subject")), "object": sub(edge.get("object"))}
                    for edge in plan.get("edges") or [] if isinstance(edge, dict)]
    out["outputs"] = [{**output, "node": sub(output.get("node"))}
                      for output in plan.get("outputs") or [] if isinstance(output, dict)]
    if trace is not None:
        trace.extend(f"plan sanitize: {old} -> {new}" for old, new in rename.items())
    return out


def _generate(question: str, entity: dict, fragment: SchemaFragment,
              previous_plan: dict | None, errors: list[str]) -> dict:
    feedback = ""
    if previous_plan is not None:
        feedback = ("\n[직전 plan]\n" + json.dumps(previous_plan, ensure_ascii=False) +
                    "\n[검사기 오류]\n- " + "\n- ".join(errors) +
                    "\nnode id 규칙: 해소된 엔티티 node는 seed, 나머지는 n1·bond 같은 짧은 영문 id.\n"
                    "참조 규칙: edges·outputs가 쓰는 id는 nodes에 먼저 선언한다. "
                    "output alias는 ^[A-Za-z][A-Za-z0-9_]{0,39}$ 영문 식별자다(한글 금지).\n"
                    "seed 속성만 묻는 질문이면 edges=[]로 두고, 분류 개체의 이름은 "
                    "output property rdfs:label로 얻는다.\n"
                    "오류를 모두 고친 새 plan을 출력하라. 술어를 지어내지 마라.\n")
    user = (
        f"[질문]\n{question}\n\n"
        f"[해소된 seed]\nURI=<{entity['uri']}> class={compact_uri(entity['class_uri'])}\n\n"
        f"{fragment.to_prompt()}\n"
        "[plan 모양 확인] 질문의 답이 분류 체계 값(투자지역·자산유형·위험등급·펀드유형·\n"
        "테마)이거나 seed와 연결된 다른 개체이면 edges로 그 개체 node를 잡고, 분류 개체의\n"
        "이름은 rdfs:label로 얻는다. 이름이 비슷한 datatype property로 대체하지 마라.\n"
        f"{feedback}"
    )
    structured_llm = _llm_plan.with_structured_output(_plan_json_schema(fragment), method="json_schema")
    return structured_llm.invoke([("system", GRAPH_PLAN_SYSTEM), ("human", user)])


def _evidence(rows: list[dict], evidence_columns: tuple[str, ...]) -> list[dict]:
    out = []
    for row_no, row in enumerate(rows):
        item = {key: row.get(key) for key in evidence_columns if row.get(key) is not None}
        if item:
            out.append({"row": row_no, **item})
    return out


def resolve_evidence(rows: list[dict], compiled) -> tuple[list[dict], str]:
    """(evidence, abstain_reason).

    row-level evidence가 있으면 그대로 돌려준다. 분류형 조회처럼 evidence
    클래스가 없는 plan은 TBox의 sourceTable/sourceColumn을 근거로 쓰고,
    그것마저 없으면 무근거이므로 ABSTAIN한다."""
    if compiled.evidence_columns:
        core = [column for column in compiled.evidence_columns if column.endswith(("_as_of", "_source"))]
        if not core:
            return [], "관계의 기준일·원천 식별자 계약이 없습니다"
        missing = [index for index, row in enumerate(rows)
                   if any(row.get(column) is None or str(row.get(column)).strip() == "" for column in core)]
        if missing:
            return [], f"기준일·원천 식별자 evidence 누락 행: {missing[:10]}"
        evidence = _evidence(rows, compiled.evidence_columns)
        for item in evidence:
            absent = [c for c in compiled.evidence_columns if c not in core and not rows[item["row"]].get(c)]
            item.update(kind="source_record", document_status="metadata_missing" if absent else "metadata_present",
                        missing_document_fields=absent)
        return evidence, ""
    if not compiled.tbox_provenance:
        return [], "evidence 부재: plan에 근거 클래스도 TBox provenance(sourceTable/sourceColumn)도 없다"
    return [{"kind": "tbox_source", "property": curie, "source_table": table,
             "source_column": column, "as_of_rule": SNAPSHOT_AS_OF_RULE}
            for curie, table, column in compiled.tbox_provenance], ""


def _extract_entity_codes(plan: dict, rows: list[dict]) -> list[str]:
    """rows에서 상품/증권 식별 코드로 보이는 컬럼 값을 모은다.

    §8(Graph->RDB 핸드오프)의 입력이 되는 값이다 - output의 property가
    *Code로 끝나거나(fp:productCode, fp:securityCode 등) alias 자체에
    "code"가 들어 있으면 그 컬럼을 식별 코드 컬럼으로 본다."""
    code_aliases = [
        str(o.get("alias"))
        for o in (plan.get("outputs") or [])
        if isinstance(o, dict) and str(expand_uri(str(o.get("property", "")))) == FP + "productCode"
    ]
    codes: list[str] = []
    for row in rows:
        for alias in code_aliases:
            value = row.get(alias)
            if value and str(value) not in codes:
                codes.append(str(value))
    return codes


def run(question: str, frame: dict, *,
        generator: Callable[[str, dict, SchemaFragment, dict | None, list[str]], dict] | None = None,
        max_corrections: int = MAX_CORRECTIONS) -> dict:
    """안전한 Text2SPARQL vertical slice.

    ``frame``은 호출부(nodes.py의 graph_search_node 어댑터)가 relation에서
    직접 만들어 넘긴다({"entities":[{"text","role"}], ...}) - 필수 인자다.
    ``generator``는 단위 테스트에서만 주입한다. 운영 기본값은 HyperCLOVA X다.
    검증 실패 plan은 실행하지 않고 오류를 되돌려 최대 max_corrections회 다시
    생성한다."""
    trace = []
    seed = resolve_frame_seed(question, frame)
    if seed["status"] == "not_found" and frame.get("relation_scope"):
        root = (frame.get("relations") or [{}])[0]
        if root.get("relation") in {"holds", "holding", "held_by", "subsidiary_of", "has_subsidiary"}:
            entities = frame.get("entities") or []
            if entities and entities[0].get("role") not in {"company", "issuer"}:
                alternate = {**frame, "entities": [{**entities[0], "role": "company"}]}
                alternate_seed = resolve_frame_seed(question, alternate)
                alternate_seed["attempts"] = seed["attempts"] + alternate_seed["attempts"]
                seed = alternate_seed
                trace.append("관계 주체가 상품으로 해소되지 않아 동일 표기를 회사/증권 식별자로 대조했습니다.")
    attempts_summary = ", ".join(
        f"{a['text']}/{a['role']}/{a['class_name']}={a['status']}" for a in seed["attempts"])
    if seed["status"] == "ambiguous":
        trace.append(f"entity: ambiguous ({attempts_summary})")
        candidates = [{"uri": c.get("uri"), "canonical_name": c.get("canonical_name")}
                      for c in seed["entity"]["candidates"]]
        return {"status": "abstain_entity_ambiguous", "rows": [], "entity": seed["entity"],
                "candidates": candidates, "evidence": [], "entity_codes": [], "trace": trace}
    if seed["status"] == "not_found":
        trace.append(f"entity: not_found ({attempts_summary})")
        return {"status": "abstain_entity_not_found", "rows": [], "evidence": [],
                "entity_codes": [], "trace": trace}
    resolved = seed["entity"]
    class_local = resolved["class_uri"].rsplit("#", 1)[-1]
    trace.append(f"entity: {resolved['text']} -> resolved ({class_local})")
    trace.append(f"entity attempts: {attempts_summary}")

    scoped_question = question
    if frame.get("relation_scope"):
        scoped_question = json.dumps({"entities": frame.get("entities"), "relations": frame.get("relations"),
                                      "requested_fields": frame.get("requested_fields"), "constraints": frame.get("constraints")}, ensure_ascii=False)
    plan, seeds = _fast_plan(scoped_question, frame, class_local)
    schema_text = _schema_search_text(scoped_question, frame)
    try:
        fragment = catalog().select_fragment(schema_text, seed_classes=seeds or [resolved["class_uri"]],
                                             hops=2, max_classes=18, max_properties=60)
    except Exception as exc:
        return {"status": "abstain_schema_unresolved", "rows": [], "entity": resolved,
                "evidence": [], "entity_codes": [], "trace": trace + [f"schema: {type(exc).__name__}: {exc}"]}
    trace.append(f"schema: mode={fragment.selection_mode} classes={len(fragment.classes)} "
                 f"properties={len(fragment.properties)}")

    generate = generator or _generate
    attempts, errors, previous = [], [], None
    if plan is not None:
        validation = validate_graph_plan(plan, resolved, fragment, catalog())
        attempts.append({"attempt": 0, "mode": "verified_fast_path", **validation.as_dict()})
        if not validation.ok:
            return {"status": "abstain_invalid_graph_plan", "rows": [], "entity": resolved,
                    "schema_fragment": fragment.as_dict(), "attempts": attempts,
                    "evidence": [], "entity_codes": [], "trace": trace}
    else:
        for attempt in range(1, max(1, min(max_corrections, MAX_CORRECTIONS)) + 1):
            try:
                candidate = _sanitize_plan(
                    generate(scoped_question, resolved, fragment, previous, errors), resolved, trace)
                validation = validate_graph_plan(candidate, resolved, fragment, catalog())
                errors = list(validation.errors)
            except Exception as exc:
                candidate = previous or {}
                errors = [f"생성/파싱 실패: {type(exc).__name__}: {exc}"]
                validation = None
            attempts.append({"attempt": attempt, "mode": "hcx_graph_plan",
                             "status": "PASS" if validation and validation.ok else "REJECT",
                             "errors": errors})
            previous = candidate
            if validation and validation.ok:
                plan = candidate
                break
        if plan is None:
            return {"status": "abstain_invalid_graph_plan", "rows": [], "entity": resolved,
                    "schema_fragment": fragment.as_dict(), "attempts": attempts,
                    "evidence": [], "entity_codes": [], "trace": trace}

    try:
        compiled = compile_graph_plan(plan, resolved, fragment, catalog())
        rows = graph_engine.sparql(compiled.sparql)
    except Exception as exc:
        return {"status": "abstain_graph_execution_failed", "rows": [], "entity": resolved,
                "schema_fragment": fragment.as_dict(), "graph_plan": plan,
                "attempts": attempts, "evidence": [], "entity_codes": [],
                "trace": trace + [f"graph 실행 실패: {type(exc).__name__}: {exc}"]}
    trace.append(f"graph: rows={len(rows)}")
    evidence, abstain_reason = resolve_evidence(rows, compiled)
    if abstain_reason:
        return {"status": "abstain_evidence_missing", "rows": [], "entity": resolved,
                "schema_fragment": fragment.as_dict(), "graph_plan": plan,
                "sparql": compiled.sparql, "attempts": attempts, "evidence": [],
                "entity_codes": [], "trace": trace + [abstain_reason]}
    entity_codes = _extract_entity_codes(plan, rows)
    document_missing = any(e.get("document_status") == "metadata_missing" for e in evidence)
    note = ("관계 원천 식별자와 기준일은 확인했지만 연결된 문서 메타데이터·본문은 미확보입니다. "
            "데이터셋에 기록된 관계만 제시하며 공식 문서 인용·위험 주장 또는 현재 편입 확인으로 간주하지 않습니다." if document_missing else "")
    return {
        "status": "ok" if rows else "empty",
        "rows": rows,
        "entity": resolved,
        "schema_fragment": fragment.as_dict(),
        "graph_plan": plan,
        "sparql": compiled.sparql,
        "attempts": attempts,
        "evidence": evidence,
        "evidence_level": "source_record" if document_missing else "document_metadata_or_tbox",
        "note": note,
        "coverage_truncated": len(rows) >= int(plan.get("limit") or 100),
        "entity_codes": entity_codes,
        "tbox_provenance": [list(x) for x in compiled.tbox_provenance],
        "trace": trace,
    }


def run_theme_membership(question: str, theme_keyword: str, *, limit: int = 100) -> dict:
    """"<키워드> 테마 ETF" 전용 결정적 경로.

    run()의 seed 해소(resolve_frame_seed)는 "이름 하나 -> URI 하나"인
    단일 seed 모델이라 후보가 2개 이상이면 곧장 ambiguous로 멈춘다. 이건
    회사/상품명에는 맞는 안전 계약이지만(편집거리로 "비슷한 걸 짐작"하면
    안 되는 이유가 분명하다), 테마는 성격이 다르다 - 사용자가 실제로
    쓰는 "반도체" 같은 키워드는 LSEG 176테마 taxonomy에서 애초에 여러
    하위 테마("K-반도체", "글로벌반도체" 등)에 걸쳐 있는 게 정상이고,
    "이 키워드를 포함하는 테마 전부"가 곧 사용자의 원래 의도다(2026-09-02
    실측: resolve_entity("반도체","Theme")는 not_found, allow_partial=True로
    돌리면 정확히 이 두 후보가 나온다). 그래서 여기서는 resolve_entity
    (allow_partial=True)로 후보 테마를 전부 찾아 후보마다
    theme_membership_plan을 반복 실행해 합친다 - 테마 후보는 이미 그래프에
    실재하는 확정된 분류값이라, 회사명처럼 "존재하지 않는 걸 지어내는"
    위험 없이(최악의 경우도 "관련성이 옅은 테마까지 포함" 정도) 여러 개를
    합쳐도 안전하다.

    ontology/common.ttl의 fp:relatedToTheme 주석대로 이 관계의 유일한
    원천은 국내ETF 1,099종(LSEG)뿐이다 - 해외ETF/펀드/채권 테마 질문은
    이 경로를 타도 매번 0건일 수 있다(데이터 범위 제약, 버그 아님)."""
    trace: list[str] = []
    keyword = (theme_keyword or "").strip()
    if not keyword:
        return {"status": "abstain_no_seed_text", "rows": [], "evidence": [],
                "entity_codes": [], "trace": ["테마 키워드가 비어 있음"]}

    resolved = resolve_entity(keyword, "Theme", allow_partial=True)
    if resolved["status"] == "not_found":
        trace.append(f"theme: not_found ({keyword!r})")
        return {"status": "abstain_entity_not_found", "rows": [], "evidence": [],
                "entity_codes": [], "trace": trace}

    candidates = [resolved] if resolved["status"] == "resolved" else list(resolved["candidates"])
    trace.append(f"theme candidates: {[c.get('canonical_name') for c in candidates]}")

    try:
        fragment = catalog().select_fragment(
            question, seed_classes=["fp:Theme", "fp:ETF"], hops=2,
            max_classes=18, max_properties=60,
        )
    except Exception as exc:
        return {"status": "abstain_schema_unresolved", "rows": [], "evidence": [],
                "entity_codes": [], "trace": trace + [f"schema: {type(exc).__name__}: {exc}"]}
    trace.append(f"schema: mode={fragment.selection_mode} classes={len(fragment.classes)} "
                 f"properties={len(fragment.properties)}")

    plan = theme_membership_plan(limit=limit)
    validation = validate_graph_plan(plan, candidates[0], fragment, catalog())
    if not validation.ok:
        return {"status": "abstain_invalid_graph_plan", "rows": [], "entity": candidates[0],
                "schema_fragment": fragment.as_dict(), "graph_plan": plan,
                "evidence": [], "entity_codes": [],
                "trace": trace + [f"plan 검증 실패: {validation.errors}"]}

    all_rows: list[dict] = []
    sparqls: list[str] = []
    compiled = None
    for candidate in candidates:
        try:
            compiled = compile_graph_plan(plan, candidate, fragment, catalog())
            rows = graph_engine.sparql(compiled.sparql)
        except Exception as exc:
            trace.append(f"theme={candidate.get('canonical_name')}: 실행 실패 - "
                         f"{type(exc).__name__}: {exc}")
            continue
        sparqls.append(compiled.sparql)
        for row in rows:
            tagged = dict(row)
            tagged["_matched_theme"] = candidate.get("canonical_name")
            all_rows.append(tagged)
        trace.append(f"theme={candidate.get('canonical_name')}: {len(rows)}건")

    if not sparqls:
        return {"status": "abstain_graph_execution_failed", "rows": [], "entity": candidates[0],
                "schema_fragment": fragment.as_dict(), "graph_plan": plan,
                "evidence": [], "entity_codes": [], "trace": trace}

    evidence, abstain_reason = resolve_evidence(all_rows, compiled)
    if abstain_reason:
        return {"status": "abstain_evidence_missing", "rows": [], "entity": candidates[0],
                "schema_fragment": fragment.as_dict(), "graph_plan": plan,
                "sparql": "\n\n".join(sparqls), "evidence": [], "entity_codes": [],
                "trace": trace + [abstain_reason]}

    entity_codes = _extract_entity_codes(plan, all_rows)
    return {
        "status": "ok" if all_rows else "empty",
        "rows": all_rows,
        "entity": {"canonical_name": keyword,
                   "candidates": [c.get("canonical_name") for c in candidates]},
        "schema_fragment": fragment.as_dict(),
        "graph_plan": plan,
        "sparql": "\n\n".join(sparqls),
        "evidence": evidence,
        "coverage_truncated": len(all_rows) >= limit,
        "entity_codes": entity_codes,
        "tbox_provenance": [list(x) for x in compiled.tbox_provenance] if compiled else [],
        "trace": trace,
    }
