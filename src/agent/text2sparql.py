# -*- coding: utf-8 -*-
"""질문 → schema-grounded GraphLogicalPlan → SPARQL → 선택적 RDB 후처리."""
from __future__ import annotations

import json
from collections.abc import Callable

import clova
from agent import query_frame
from config import FRAME_MODEL
from tools import graph
from tools.graph_entity import resolve_frame_seed
from tools.graph_plan import (_ID, build_etf_rdb_handoff, compile_graph_plan,
                              execute_etf_rdb_handoff, subsidiary_holding_etf_plan,
                              subsidiary_relation_plan, validate_graph_plan)
from tools.graph_schema import FP, SchemaFragment, catalog, compact_uri, expand_uri


GRAPH_MODEL = FRAME_MODEL  # 절대 규칙: HyperCLOVA X만 사용한다.
MAX_CORRECTIONS = 3

GRAPH_PLAN_SYSTEM = """너는 금융상품 지식그래프용 GraphLogicalPlan만 생성한다.
지정된 JSON object 하나만 출력하고 설명·SPARQL·코드펜스를 출력하지 마라.

규칙:
1. class_uri와 predicate/property는 제공된 schema fragment의 값만 복사한다.
   단 output property `rdfs:label`은 fragment 목록과 무관하게 항상 쓸 수 있다.
2. seed는 이미 URI로 해소된 엔티티다. labels 문자열 FILTER를 만들지 않는다.
3. edge의 subject/object 방향은 domain → range 방향과 정확히 같아야 한다.
4. 역방향 탐색도 edge 방향을 뒤집지 않는다. 예: 증권→발행기업 속성은
   탐색이 기업에서 증권으로 진행돼도 subject=증권, object=기업으로 적는다.
5. 출처·기준일·근거문서는 코드가 자동 부착한다. 이를 임의로 만들지 않는다.
6. 질문에 없는 관계를 추가하지 않는다. 모호하면 빈 plan으로 추측하지 말고 최소 경로만 낸다.
7. 해소된 엔티티를 나타내는 node의 id는 반드시 소문자 seed 하나다. 다른 node id는
   n1, bond 처럼 ^[A-Za-z][A-Za-z0-9_]{0,39}$ 를 만족하는 짧은 영문 식별자만 허용한다.
   URI·꺾쇠괄호·한글을 id로 쓰지 마라. edge의 subject/object와 output의 node도
   이 id를 그대로 참조한다.
8. edges·outputs가 참조하는 모든 id는 nodes에 먼저 선언한다. 선언하지 않은 id를
   참조하면 plan 전체가 기각된다.
9. output의 alias도 ^[A-Za-z][A-Za-z0-9_]{0,39}$ 를 만족하는 짧은 영문 식별자다.
   한글·빈 문자열·공백을 alias로 쓰지 마라. 예: region_label, risk_grade.
10. plan 모양은 아래 순서로 결정한다.
   (a) 질문이 seed와 **연결된 다른 개체**(상품·기업·종목·보유·관계)를 요구하면 그
       개체 node를 선언하고 edges로 잇는다. 예: "…와 연결된 ETF", "…가 발행한 채권",
       "…가 보유한 종목". 이때 edges를 비우면 오답이다.
   (b) 답이 **분류 체계 값**(투자지역·자산유형·위험등급·펀드유형·테마)이면 이것도
       (a)다. fp:has*·fp:relatedTo* ObjectProperty로 분류 개체 node를 잡고, 그 node의
       output property `rdfs:label`로 이름을 얻는다. 이름이 비슷한 datatype
       property(fp:riskGradeLabel·fp:baseMarket 등)로 대신하지 마라 — 원천 결측이
       많아 조용히 0행이 된다.
   (c) 답이 seed 자신의 수치·코드·문자열 속성뿐일 때만 edges를 빈 배열 []로 둔다.
11. output property는 반드시 그 node의 class가 domain인 것만 쓴다. 다른 class의
   속성을 붙이면 domain 위반으로 기각된다.
12. outputs는 절대 비워두지 않는다. 질문이 요구하는 값을 최소 1개 이상 넣는다.
   목록을 묻는 질문이면 limit을 20 이상으로 둔다.
"""


def _response_format(fragment: SchemaFragment) -> dict:
    classes = [compact_uri(x) for x in fragment.classes]
    object_properties = [compact_uri(x.uri) for x in fragment.properties if x.kind == "object"]
    # rdfs:label 은 TBox datatype property 가 아니지만 분류 개체(fp:InvestmentRegion
    # 등)의 이름을 얻는 유일한 경로다. graph_plan 이 catalog 검사를 면제한다.
    datatype_properties = [compact_uri(x.uri) for x in fragment.properties
                           if x.kind == "datatype"] + ["rdfs:label"]
    # id 계약(graph_plan._ID)은 여기 pattern 으로 적을 수 없다 — HCX response_format
    # 은 pattern 을 거부한다(HTTP 400 code 40055 "'pattern' is not supported").
    # 계약은 GRAPH_PLAN_SYSTEM 규칙 7과 _sanitize_plan 두 곳에서 강제한다.
    node_id = {"type": "string", "description": _ID.pattern}
    schema = {
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
    return {"type": "json", "schema": schema}


def _schema_search_text(question: str, frame: dict) -> str:
    parts = [question]
    parts.extend(x.get("text", "") for x in frame.get("requested_fields") or [])
    parts.extend(x.get("field_text", "") for x in frame.get("constraints") or [])
    parts.extend(x.get("raw", "") for x in frame.get("relations") or [])
    return "\n".join(x for x in parts if x)


def _fast_plan(question: str, frame: dict) -> tuple[dict | None, list[str]]:
    relation_text = " ".join(
        [question] + [x.get("raw", "") for x in frame.get("relations") or []]
    ).casefold()
    limit = frame.get("limit") or 100
    if "자회사" not in relation_text and "출자" not in relation_text:
        return None, []
    if "etf" in relation_text or "편입" in relation_text or "상장지수" in relation_text:
        return subsidiary_holding_etf_plan(limit=max(limit, 100)), [
            "fp:Company", "fp:SubsidiaryRelation", "fp:Security", "fp:Holding",
            "fp:ETF", "fp:Document",
        ]
    return subsidiary_relation_plan(limit=limit), [
        "fp:Company", "fp:SubsidiaryRelation", "fp:Document",
    ]


def _sanitize_alias(plan: dict, trace: list[str] | None = None) -> dict:
    """output alias 계약(`_ID`)만 결정적으로 복구한다.

    alias는 SELECT 변수명일 뿐 plan 안 어디서도 참조되지 않으므로 개명이 안전하다.
    한글·빈 문자열 alias 때문에 correction 예산이 통째로 날아가는 사례가 반복됐다.
    """
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

    HCX가 node id에 해소된 URI(`<http://mafest.ai/instance/...>`)를 그대로 넣어
    self-correction 3회가 전부 "허용하지 않는 node id"·"seed node 없음"으로 끝나는
    사례가 반복됐다. 여기서 고치는 것은 **id 표기뿐**이며 class·predicate·방향은
    건드리지 않는다. seed를 유일하게 특정하지 못하면 개명하지 않고 validator 오류를
    그대로 내보낸다(추측 금지 — AGENTS.md 절대규칙 4).
    """
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
            # ② class가 해소된 엔티티와 호환되는 node가 **유일**할 때만 seed로 본다.
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
    text = clova.chat(GRAPH_MODEL, GRAPH_PLAN_SYSTEM, user, max_tokens=2048,
                      response_format=_response_format(fragment), temperature=0.0)
    return clova.parse_json_loose(text)


def _evidence(rows: list[dict], evidence_columns: tuple[str, ...]) -> list[dict]:
    out = []
    for row_no, row in enumerate(rows):
        item = {key: row.get(key) for key in evidence_columns if row.get(key) is not None}
        if item:
            out.append({"row": row_no, **item})
    return out


SNAPSHOT_AS_OF_RULE = "snapshot@2026-08-24"


def resolve_evidence(rows: list[dict], compiled) -> tuple[list[dict], str]:
    """(evidence, abstain_reason).

    row-level evidence가 있으면 기존 형태·개수 그대로 돌려준다. 분류형 조회처럼
    evidence 클래스가 없는 plan은 TBox의 sourceTable/sourceColumn을 근거로 쓰고,
    그것마저 없으면 무근거이므로 ABSTAIN한다.
    """
    if compiled.evidence_columns:
        missing = [index for index, row in enumerate(rows)
                   if any(row.get(column) is None for column in compiled.evidence_columns)]
        if missing:
            return [], f"evidence 누락 행: {missing[:10]}"
        return _evidence(rows, compiled.evidence_columns), ""
    if not compiled.tbox_provenance:
        return [], "evidence 부재: plan에 근거 클래스도 TBox provenance(sourceTable/sourceColumn)도 없다"
    return [{"kind": "tbox_source", "property": curie, "source_table": table,
             "source_column": column, "as_of_rule": SNAPSHOT_AS_OF_RULE}
            for curie, table, column in compiled.tbox_provenance], ""


def _ordering(frame: dict) -> tuple[str, str] | None:
    items = frame.get("ordering") or []
    if not items:
        return None
    return items[0].get("field_text", ""), items[0].get("direction", "desc")


def run(question: str, *, frame: dict | None = None,
        generator: Callable[[str, dict, SchemaFragment, dict | None, list[str]], dict] | None = None,
        execute_rdb: bool = True, rdb_conn=None,
        max_corrections: int = MAX_CORRECTIONS) -> dict:
    """안전한 Text2SPARQL vertical slice.

    ``generator``는 단위 테스트에서만 주입한다. 운영 기본값은 HyperCLOVA X다.
    검증 실패 plan은 실행하지 않고 오류를 되돌려 최대 3회 다시 생성한다.
    """
    trace = []
    try:
        frame = frame or query_frame.extract(question, use_audit=False)
    except Exception as exc:
        return {"status": "abstain_intent_failed", "rows": [], "evidence": [],
                "trace": [f"intent 실패: {type(exc).__name__}: {exc}"]}
    seed = resolve_frame_seed(question, frame)
    attempts_summary = ", ".join(
        f"{a['text']}/{a['role']}/{a['class_name']}={a['status']}" for a in seed["attempts"])
    if seed["status"] == "ambiguous":
        trace.append(f"entity: ambiguous ({attempts_summary})")
        candidates = [{"uri": c.get("uri"), "canonical_name": c.get("canonical_name")}
                      for c in seed["entity"]["candidates"]]
        return {"status": "abstain_entity_ambiguous", "rows": [], "entity": seed["entity"],
                "candidates": candidates, "evidence": [], "trace": trace}
    if seed["status"] == "not_found":
        trace.append(f"entity: not_found ({attempts_summary})")
        return {"status": "abstain_entity_not_found", "rows": [], "evidence": [],
                "trace": trace}
    resolved = seed["entity"]
    class_local = resolved["class_uri"].rsplit("#", 1)[-1]
    trace.append(f"entity: {resolved['text']} -> resolved ({class_local})")
    trace.append(f"entity attempts: {attempts_summary}")

    plan, seeds = _fast_plan(question, frame)
    schema_text = _schema_search_text(question, frame)
    try:
        fragment = catalog().select_fragment(schema_text, seed_classes=seeds or [resolved["class_uri"]],
                                             hops=2, max_classes=18, max_properties=60)
    except Exception as exc:
        return {"status": "abstain_schema_unresolved", "rows": [], "entity": resolved,
                "evidence": [], "trace": trace + [f"schema: {type(exc).__name__}: {exc}"]}
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
                    "evidence": [], "trace": trace}
    else:
        for attempt in range(1, max(1, min(max_corrections, MAX_CORRECTIONS)) + 1):
            try:
                candidate = _sanitize_plan(
                    generate(question, resolved, fragment, previous, errors), resolved, trace)
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
                    "evidence": [], "trace": trace}

    try:
        compiled = compile_graph_plan(plan, resolved, fragment, catalog())
        rows = graph.sparql(compiled.sparql)
    except Exception as exc:
        return {"status": "abstain_graph_execution_failed", "rows": [], "entity": resolved,
                "schema_fragment": fragment.as_dict(), "graph_plan": plan,
                "attempts": attempts, "evidence": [],
                "trace": trace + [f"graph 실행 실패: {type(exc).__name__}: {exc}"]}
    trace.append(f"graph: rows={len(rows)}")
    evidence, abstain_reason = resolve_evidence(rows, compiled)
    if abstain_reason:
        return {"status": "abstain_evidence_missing", "rows": [], "entity": resolved,
                "schema_fragment": fragment.as_dict(), "graph_plan": plan,
                "sparql": compiled.sparql, "attempts": attempts, "evidence": [],
                "trace": trace + [abstain_reason]}
    result = {
        "status": "ok" if rows else "empty",
        "rows": rows,
        "entity": resolved,
        "schema_fragment": fragment.as_dict(),
        "graph_plan": plan,
        "sparql": compiled.sparql,
        "attempts": attempts,
        "evidence": evidence,
        "tbox_provenance": [list(x) for x in compiled.tbox_provenance],
        "trace": trace,
        "rdb_handoff": None,
        "rdb_result": None,
    }
    ordering = _ordering(frame)
    if rows and ordering and any(row.get("etf_code") for row in rows):
        field, direction = ordering
        try:
            handoff = build_etf_rdb_handoff(rows, field, direction=direction,
                                            limit=frame.get("limit"))
            result["rdb_handoff"] = handoff
            if execute_rdb:
                result["rdb_result"] = execute_etf_rdb_handoff(
                    rows, field, direction=direction, limit=frame.get("limit"), conn=rdb_conn)
            result["trace"].append(
                f"rdb handoff: ids={handoff['handoff']['entity_count']} order={field} {direction}")
        except Exception as exc:
            result["status"] = "abstain_rdb_handoff_failed"
            result["trace"].append(f"rdb handoff 실패: {type(exc).__name__}: {exc}")
    return result


if __name__ == "__main__":
    # _sanitize_plan 자체 점검(HCX·store 불필요). 실행: PYTHONPATH=src python3 src/agent/text2sparql.py
    entity = {"uri": "http://mafest.ai/instance/etfkr-KR7069500007", "class_uri": FP + "ETF"}
    dirty = {
        "nodes": [{"id": "<http://mafest.ai/instance/etfkr-KR7069500007>", "class_uri": "fp:ETF"},
                  {"id": "보유", "class_uri": "fp:Holding"}],
        "edges": [{"subject": "<http://mafest.ai/instance/etfkr-KR7069500007>",
                   "predicate": "fp:hasHolding", "object": "보유"}],
        "outputs": [{"node": "보유", "property": "fp:weight", "alias": "weight", "optional": True}],
        "limit": 50,
    }
    notes: list[str] = []
    fixed = _sanitize_plan(dirty, entity, notes)
    assert [n["id"] for n in fixed["nodes"]] == ["seed", "n1"], fixed
    assert fixed["edges"][0]["subject"] == "seed" and fixed["edges"][0]["object"] == "n1", fixed
    assert fixed["outputs"][0]["node"] == "n1", fixed
    assert len(notes) == 2, notes
    # seed를 유일하게 특정하지 못하면 손대지 않는다(추측 금지).
    ambiguous = {"nodes": [{"id": "a", "class_uri": "fp:ETF"}, {"id": "b", "class_uri": "fp:ETF"}],
                 "edges": [], "outputs": [], "limit": 10}
    assert _sanitize_plan(ambiguous, entity) is ambiguous
    # 한글·빈 alias는 out1, out2로 치환한다(alias는 어디서도 참조되지 않는다).
    alias_notes: list[str] = []
    aliased = _sanitize_plan({
        "nodes": [{"id": "seed", "class_uri": "fp:ETF"}],
        "edges": [],
        "outputs": [{"node": "seed", "property": "fp:baseMarket", "alias": "투자지역"},
                    {"node": "seed", "property": "rdfs:label", "alias": ""},
                    {"node": "seed", "property": "fp:productShortName", "alias": "name"}],
        "limit": 10}, entity, alias_notes)
    assert [x["alias"] for x in aliased["outputs"]] == ["out1", "out2", "name"], aliased
    assert len(alias_notes) == 2, alias_notes
    # 미등록 id는 class를 추측해 만들지 않는다 — validator 오류로 내보낸다.
    dangling = {"nodes": [{"id": "seed", "class_uri": "fp:ETF"}],
                "edges": [{"subject": "seed", "predicate": "fp:hasHolding", "object": "h1"}],
                "outputs": [{"node": "h1", "property": "fp:weight", "alias": "w"}], "limit": 10}
    kept = _sanitize_plan(dangling, entity)
    assert [n["id"] for n in kept["nodes"]] == ["seed"], kept
    assert kept["edges"][0]["object"] == "h1" and kept["outputs"][0]["node"] == "h1", kept
    print("PASS _sanitize_plan", notes, alias_notes)
