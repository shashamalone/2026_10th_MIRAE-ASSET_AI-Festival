#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Graph-only 파이프라인 통합 회귀 — 삭제된 test_route_guard/test_text2sparql 대체.

기본 실행은 전부 결정적(HCX 무호출·PostgreSQL 무접속)이다. oxigraph store 와
frames 캐시(test/vectordb_test)만 있으면 돈다.

  1. 라우팅 게이트   RDB 14문항 불변 + graph_only 개방(q022) + lookup 폴백 6케이스
  2. 엔티티 해소     src/tools/graph_entity.py 자체점검 (13케이스)
  3. plan sanitizer  src/agent/text2sparql.py 자체점검 (URI id·한글 alias 복구)
  4. plan 계약       edges=[] 속성조회 / rdfs:label output / 도메인 위반 거부
  5. evidence 계약   resolve_evidence 4분기 (row / 누락 / tbox / 무근거 ABSTAIN)

--e2e 를 주면 X1(에코프로 자회사, HCX plan 생성 포함)을 끝까지 실행한다.

알려진 한계(회귀 대상 아님): B2(신용등급 2홉)·E2(역방향 3홉)는 HCX 교정
3회 예산의 경계 케이스로, 실패 시에도 구체적 ABSTAIN 으로 안전하게 끝난다.
근거: test/agent_test/Gragh-test/battery_results.json (13문항 매트릭스).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tools.route import GRAPH_TASKS, MAX_PLAN_STEPS, select_route  # noqa: E402
from tools.schema_context import ground  # noqa: E402
from tools.graph_entity import resolve_entity  # noqa: E402
from tools.graph_schema import catalog  # noqa: E402
from tools.graph_plan import compile_graph_plan, validate_graph_plan  # noqa: E402
from tools import graph  # noqa: E402
from agent.text2sparql import _sanitize_plan, resolve_evidence  # noqa: E402
from tools.graph_plan import CompiledGraphQuery  # noqa: E402

FRAMES = ROOT / "test/vectordb_test/4_query_frame_v1/results/frames_HCX-007_audit.jsonl"
QUESTIONS = ROOT / "test/vectordb_test/5_semantic_schema_nl2sql/gold/expected_queries_35.json"
RDB_IDS = {"q001", "q002", "q003", "q005", "q006", "q007", "q008", "q009",
           "q010", "q011", "q012", "q013", "q017", "q018"}
UNSUPPORTED_IDS = {"q020", "q029"}
GRAPH_IDS = {"q022"}  # 자회사 문자열 게이트 제거 후 graph_only 로 열린 관계 질의

PASSED = 0


def ok(label: str, cond: bool, detail: str = "") -> None:
    global PASSED
    if not cond:
        sys.exit(f"FAIL  {label}  {detail}")
    PASSED += 1
    print(f"PASS  {label}")


def test_routing() -> None:
    frames = {x["question_id"]: x for x in
              map(json.loads, FRAMES.read_text(encoding="utf-8").splitlines())}
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    qmap = {f"q{int(x['id']):03d}": x["question"] for x in questions}
    for qid in sorted(RDB_IDS):
        plan = ground(qmap[qid], frames[qid])
        route = select_route(frames[qid], plan)
        assert route["query_type"] == "rdb_only", (qid, route)
        assert len(route["execution_plan"]) <= MAX_PLAN_STEPS
    ok("라우팅: RDB 14문항 rdb_only 불변", True)
    for qid in sorted(UNSUPPORTED_IDS):
        route = select_route(frames[qid], ground(qmap[qid], frames[qid]))
        assert route["query_type"] == "unsupported", (qid, route)
    ok("라우팅: q020/q029 unsupported 유지", True)
    for qid in sorted(GRAPH_IDS):
        route = select_route(frames[qid], ground(qmap[qid], frames[qid]))
        assert route["query_type"] == "graph_only", (qid, route)
    ok("라우팅: q022 relation graph_only 개방", True)

    # 합성 케이스 — lookup 폴백 경계
    entity = [{"text": "KODEX 200", "role": "product"}]
    cases = [
        ({"task": "relation", "entities": entity, "relations": [{"raw": "편입"}]},
         {}, "graph_only", "relation 일반 관계"),
        ({"task": "lookup", "entities": entity, "domain_candidates": ["etf_kr"],
          "computation": []},
         {"domain": None, "unresolved": ["보유 종목"]}, "graph_only",
         "lookup RDB 미해소 → graph 폴백"),
        ({"task": "lookup", "entities": [], "domain_candidates": [],
          "computation": []},
         {"domain": None, "unresolved": ["x"]}, "unsupported", "lookup seed 없음"),
    ]
    for frame, plan, want, label in cases:
        got = select_route({"constraints": [], "ordering": [], "relations": [],
                            "computation": [], "domain_candidates": [], **frame}, plan)
        assert got["query_type"] == want, (label, got)
    ok("라우팅: 합성 3케이스 (relation 개방·lookup 폴백·seed 부재)", True)
    assert "lookup" in GRAPH_TASKS and "relation" in GRAPH_TASKS
    ok("라우팅: GRAPH_TASKS 상수 계약", True)


def test_self_checks() -> None:
    for rel, label in (("src/tools/graph_entity.py", "엔티티 해소 자체점검 13케이스"),
                       ("src/agent/text2sparql.py", "plan sanitizer 자체점검")):
        proc = subprocess.run([sys.executable, str(ROOT / rel)],
                              env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"},
                              capture_output=True, text=True, timeout=300)
        ok(label, proc.returncode == 0, proc.stdout[-400:] + proc.stderr[-400:])


def _etf_seed_and_fragment():
    entity = resolve_entity("KODEX 200", "ETF")
    assert entity["status"] == "resolved", entity["status"]
    cat = catalog()
    fragment = cat.select_fragment("KODEX 200의 투자지역을 알려줘",
                                   seed_classes=["fp:ETF"])
    return entity, fragment, cat


def test_plan_contract() -> None:
    entity, fragment, cat = _etf_seed_and_fragment()
    fp = "http://mafest.ai/product#"

    # 1) edges=[] 속성 조회 (seed 하나 + outputs)
    plan = {"nodes": [{"id": "seed", "class_uri": "fp:ETF"}], "edges": [],
            "outputs": [{"node": "seed", "property": "fp:productShortName",
                         "alias": "short_name", "optional": False}], "limit": 5}
    compiled = compile_graph_plan(plan, entity, fragment, cat)
    rows = graph.sparql(compiled.sparql)
    ok("plan: edges=[] 속성 조회 rows>0", len(rows) >= 1, compiled.sparql[:200])

    # 2) rdfs:label output 으로 분류 개체 이름 획득
    plan2 = {"nodes": [{"id": "seed", "class_uri": "fp:ETF"},
                       {"id": "region", "class_uri": "fp:InvestmentRegion"}],
             "edges": [{"subject": "seed", "predicate": "fp:hasInvestmentRegion",
                        "object": "region"}],
             "outputs": [{"node": "region", "property": "rdfs:label",
                          "alias": "region_label", "optional": False}], "limit": 5}
    compiled2 = compile_graph_plan(plan2, entity, fragment, cat)
    rows2 = graph.sparql(compiled2.sparql)
    ok("plan: rdfs:label output (투자지역 라벨)",
       len(rows2) >= 1 and any(r.get("region_label") for r in rows2), str(rows2[:2]))
    ok("plan: 분류형 tbox_provenance 채워짐", len(compiled2.tbox_provenance) >= 1,
       str(compiled2.tbox_provenance))

    # 3) 도메인 위반 거부 — ETF 가 issuedBy(domain=Bond) 의 주어가 될 수 없다
    bad = {"nodes": [{"id": "seed", "class_uri": "fp:ETF"},
                     {"id": "issuer", "class_uri": "fp:Issuer"}],
           "edges": [{"subject": "seed", "predicate": "fp:issuedBy",
                      "object": "issuer"}],
           "outputs": [{"node": "seed", "property": "fp:productShortName",
                        "alias": "n", "optional": False}], "limit": 5}
    bond_fragment = cat.select_fragment("VOO가 발행한 회사채", seed_classes=["fp:ETF", "fp:Bond"])
    verdict = validate_graph_plan(bad, entity, bond_fragment, cat)
    ok("plan: issuedBy 도메인 위반 거부", not verdict.ok
       and any("domain" in e for e in verdict.errors), str(verdict.errors))

    # 4) sanitizer — URI node id·한글 alias 를 결정적으로 복구
    dirty = {"nodes": [{"id": f"<{entity['uri']}>", "class_uri": "fp:ETF"}],
             "edges": [],
             "outputs": [{"node": f"<{entity['uri']}>", "property": "fp:productShortName",
                          "alias": "약칭", "optional": False}], "limit": 5}
    trace: list[str] = []
    fixed = _sanitize_plan(dirty, entity, trace)
    verdict2 = validate_graph_plan(fixed, entity, fragment, cat)
    ok("plan: sanitizer 가 URI id → seed 복구·validate 통과", verdict2.ok,
       str(verdict2.errors) + str(trace))


def test_evidence_contract() -> None:
    row_cq = CompiledGraphQuery(sparql="", columns=("a", "h_as_of"),
                                evidence_columns=("h_as_of",))
    ev, err = resolve_evidence([{"a": 1, "h_as_of": "2026-08-21"}], row_cq)
    ok("evidence: row-level 정상", not err and len(ev) == 1, err)
    ev, err = resolve_evidence([{"a": 1, "h_as_of": None}], row_cq)
    ok("evidence: row-level 누락 → ABSTAIN", bool(err) and not ev, err)
    tbox_cq = CompiledGraphQuery(sparql="", columns=("a",), evidence_columns=(),
                                 tbox_provenance=(("fp:hasRiskGrade", "T", "C"),))
    ev, err = resolve_evidence([{"a": 1}], tbox_cq)
    ok("evidence: tbox_source 폴백", not err and ev[0]["kind"] == "tbox_source", err)
    naked = CompiledGraphQuery(sparql="", columns=("a",), evidence_columns=())
    ev, err = resolve_evidence([{"a": 1}], naked)
    ok("evidence: 무근거 → ABSTAIN (사각지대 봉쇄)", bool(err) and not ev, err)


def test_e2e() -> None:
    from agent.text2sparql import run
    result = run("에코프로와 연결된 자회사 관계를 알려줘. 관계 기준일과 출처도 함께 보여줘",
                 execute_rdb=False)
    rows = result.get("rows") or []
    ok("E2E X1: 자회사 관계 rows>0", result.get("status") == "ok" and rows, result.get("status"))
    ok("E2E X1: evidence == rows", len(result.get("evidence") or []) == len(rows),
       f"evidence={len(result.get('evidence') or [])} rows={len(rows)}")


def main() -> None:
    test_routing()
    test_self_checks()
    test_plan_contract()
    test_evidence_contract()
    if "--e2e" in sys.argv:
        test_e2e()
    print(f"\nPASS graph pipeline 회귀 — {PASSED}건 전부 통과"
          + (" (E2E 포함)" if "--e2e" in sys.argv else " (결정적 검사만, --e2e 로 HCX 포함)"))


if __name__ == "__main__":
    main()
