"""
nodes.py

LangGraph 노드 함수 모음. plan_query_db.py(DB 검색 흐름 결정)를 뺀
나머지 전부가 여기 있다: 질문 입력, 질문 분석, RDB/GraphDB/VectorDB
검색, 결과 합치기, 답변 생성.

[구현 상태]
- receive_question_node, analyze_intent_node: 완전히 동작한다.
- rdb_search_node: 완전히 동작한다. 로컬 Postgres에 실제로 연결해서
  SQL을 실행한다. 카탈로그 우선 + LLM 폴백으로 컬럼을 찾고, 값 검증을
  거치고, 자연어 초안 -> SQL 2단계로 쿼리를 생성한다(utils.py의
  헬퍼들을 그대로 쓴다).
- graph_search_node: Graph logical plan을 만들고 GraphDB adapter를 통해
  읽기 전용 SPARQL을 실행한다.
- vector_search_node: 상위 단계 결과와 intent에서 상품 스코프를 모아
  product_id로 해소하고, topic별 HyperCLOVA 임베딩으로 pgvector 청크를
  검색한다. 요청 주제(topics/fields)를 section_type 힌트로 바꿔 검색
  섹션을 제한하고, 문서 확보 여부(coverage)까지 판정해 ok/low_confidence/
  no_document/no_product_match/topic_not_covered/no_hit 상태를 남기며,
  장애는 해당 단계만 abstain한다.
- merge_results_node: RDB 결과를 모아서 하나의 리스트로 만든다.
  needs_merge_rank(여러 도메인을 합쳐서 다시 정렬해야 하는 교차질의)
  케이스의 정렬 로직은 아직 최소 구현이다 - 도메인마다 정렬 개념이
  실제로 다른 컬럼명으로 풀리기 때문에, 이 완전한 통합 정렬은 후속
  작업으로 남겨 뒀다(아래 함수 docstring에 표시).
- generate_answer_node: 완전히 동작한다. merged_rows를 LLM에 보여주고
  자연어 답변을 만든다. 요청 항목(intent.output_requirements)과 Vector
  단계의 문서 근거 상태(topic_coverage 포함)를 함께 넘겨, 요청하지 않은
  화제를 덧붙이거나 미확보 주제를 다른 섹션 청크로 대신 답하지 않게 한다.
"""
from __future__ import annotations

import json
import math
import os
import time
from decimal import Decimal, InvalidOperation
from typing import Any

from agent.get_clova import _llm_answer, _llm_plan
from agent.intent_guard import guard_intent
from agent.prompts import *
from tools.schemas import INTENT_ANALYSIS_JSON_SCHEMA, SQL_OUTPUT_JSON_SCHEMA,FINAL_ANSWER_JSON_SCHEMA
from agent.state import ready_step_ids

from agent.graph_logic import graph_orchestrator
from tools import rdb_schema
from tools import schema_snapshot
from tools import catalog_sql
from agent import utils
from agent.get_clova import embed
from tools.vector_search import get_coverage, resolve_product_ids, search_documents

PipelineState = dict[str, Any]


# ---------------------------------------------------------------------------
# 노드 1: 사용자 질문 입력
# ---------------------------------------------------------------------------
def receive_question_node(state: PipelineState) -> dict:
    question = state.get("question", "")
    return {"trace": [f"질문 수신: {question}"]}


# ---------------------------------------------------------------------------
# 노드 2: 질문 분석
# ---------------------------------------------------------------------------
def analyze_intent_node(state: PipelineState) -> dict:
    structured_llm = _llm_plan.with_structured_output(INTENT_ANALYSIS_JSON_SCHEMA, method="json_schema")
    intent = structured_llm.invoke(
        [
            ("system", INTENT_ANALYSIS_SYSTEM_PROMPT),
            ("human", f"[사용자 질의]\n{state['question']}"),
        ]
    )
    intent, guard_notes = guard_intent(intent)
    domains = [d.get("domain") for d in (intent.get("product_domain") or [])]
    trace = [f"질의 분석 완료. product_domain={domains}"]
    trace.extend(f"질의 분석 보정: {note}" for note in guard_notes)
    return {"intent": intent, "trace": trace}

def verify_intent_node(state: PipelineState) -> dict:
    """analyze_intent_node의 결과를 LLM as a Judge가 다시 한번 검토하여
    누락된 조건이나 잘못된 분류를 교정한다."""
    question = state.get("question", "")
    initial_intent = state.get("intent", {})
    
    structured_llm = _llm_plan.with_structured_output(INTENT_ANALYSIS_JSON_SCHEMA, method="json_schema")
    
    initial_intent_str = json.dumps(initial_intent, ensure_ascii=False, indent=2)
    
    corrected_intent = structured_llm.invoke(
        [
            ("system", INTENT_VERIFICATION_SYSTEM_PROMPT),
            (
                "human", 
                f"[사용자 질문]\n{question}\n\n"
                f"[1차 분석 결과]\n{initial_intent_str}\n\n"
                "위 분석 결과를 엄격하게 검토하고, 누락된 조건이 있다면 추가하고 잘못된 부분을 교정하여 "
                "반드시 기존과 동일한 JSON 구조로 다시 출력하세요."
            ),
        ]
    )
    # 수정 여부 판별 (딕셔너리의 키/값들이 완전히 동일한지 체크)
    changed = json.dumps(initial_intent, sort_keys=True) != json.dumps(corrected_intent, sort_keys=True)
    if changed:
        final_intent = corrected_intent
        trace_msg = "의도 분석 검수 완료: 수정됨 (누락된 조건 복구 또는 교정)"
    else:
        final_intent = initial_intent  # 변경점이 없다면 원본 객체를 그대로 재사용 (안전성 극대화)
        trace_msg = "의도 분석 검수 완료: 수정 사항 없음 (원본 유지)"

    final_intent, guard_notes = guard_intent(final_intent)
    trace = [trace_msg]
    trace.extend(f"의도 검수 보정: {note}" for note in guard_notes)

    return {"intent": final_intent, "trace": trace}

# ---------------------------------------------------------------------------
# 노드 4a: RDB 검색 
# ---------------------------------------------------------------------------
def _draft_query_description(question: str, schema_block: str) -> str:
    response = _llm_plan.invoke(
        [
            ("system", SQL_DRAFT_SYSTEM_PROMPT),
            ("human", f"[원본 질문]\n{question}\n\n[해석된 스키마]\n{schema_block}"),
        ]
    )
    return response.content if hasattr(response, "content") else str(response)


def _write_sql(draft_text: str, schema_block: str) -> dict:
    structured_llm = _llm_plan.with_structured_output(SQL_OUTPUT_JSON_SCHEMA, method="json_schema")
    return structured_llm.invoke(
        [
            ("system", SQL_WRITE_SYSTEM_PROMPT),
            ("human", f"[해석된 스키마]\n{schema_block}\n\n[자연어 초안]\n{draft_text}"),
        ]
    )


def _execute_target_step(step: dict, question: str, conn, apply_limit: bool, max_retries: int) -> dict:
    result = _execute_target_step_query(step, question, conn, apply_limit, max_retries)
    # Preserve requested fields even when compilation, policy or execution blocks.
    result["requested_fields"] = list(step.get("fields") or [])
    return result


def _execute_target_step_query(step: dict, question: str, conn, apply_limit: bool, max_retries: int) -> dict:
    """role="target"인 RDB 단계(최종 답의 일부가 되는 조회). intent가
    구조화한 conditions/sort/fields를 그대로 쓴다."""
    if step.get("graph_handoff_blocked"):
        return {"engine": "rdb", "role": "target", "domain": step["domain"],
                "rows": [], "count": 0, "sql": None,
                "skipped_reason": step["graph_handoff_blocked"]}
    step, policy_notes = utils.apply_sale_policy(step)
    domain = step["domain"]
    needed_concepts = utils.collect_needed_concepts(step)
    concept_to_spec, unresolved = utils.resolve_concepts_for_domain(domain, needed_concepts, question, _llm_plan)
    resolved_schema = utils.build_resolved_schema(step, concept_to_spec, unresolved)
    policy_notes = policy_notes + resolved_schema.get("notes", [])

    if resolved_schema["unresolved_concepts"]:
        return {
            "engine": "rdb", "role": "target", "domain": domain, "rows": [], "count": 0, "sql": None,
            "skipped_reason": f"미해결 개념: {resolved_schema['unresolved_concepts']}",
        }
    if resolved_schema["invalid_conditions"]:
        # invalid_reason에 이미 구체적인 원인이 담겨 있다(빈 값인지, 값이
        # 도메인 밖인지). "attribute=value"만 보여주면 원인을 알 수 없어서
        # 디버깅이 어려우므로 reason을 그대로 붙인다.
        details = "; ".join(
            f"{r['attribute']}={r['value']!r} ({r['invalid_reason']})" for r in resolved_schema["invalid_conditions"]
        )
        return {
            "engine": "rdb", "role": "target", "domain": domain, "rows": [], "count": 0, "sql": None,
            "skipped_reason": f"유효하지 않은 조건: {details}",
        }

    schema_block = utils.format_resolved_schema(resolved_schema, apply_limit=apply_limit)
    try:
        draft = "확정 카탈로그 기반 결정론적 SQL"
        sql_result = catalog_sql.compile_select(resolved_schema, apply_limit=apply_limit)
    except Exception as e:
        return {
            "engine": "rdb", "role": "target", "domain": domain, "rows": [], "count": 0, "sql": None,
            "error": f"SQL 컴파일/스키마 검증 실패: {e}",
        }

    run = _run_sql_with_retry(conn, domain, question, schema_block, sql_result, max_retries)
    result = {
        "engine": "rdb", "role": "target", "domain": domain,
        "rows": run["rows"], "count": len(run["rows"]),
        "sql": run["sql"], "sql_draft_nl": draft, "assumptions": policy_notes + run["assumptions"],
        "sql_attempts": run["attempts"], "sql_retry_log": run["attempts_log"],
        "sql_compiler": sql_result["compiler"], "column_refs": sql_result["column_refs"],
        "output_fields": sql_result["output_fields"],
        "unverified_subtypes": resolved_schema.get("unverified_subtypes", []),
    }
    if run["error"]:
        result["error"] = run["error"]
    return result


def _execute_merged_target_group(
    steps: list[dict], question: str, conn, sort: dict, sort_limit: str, max_retries: int
) -> dict[str, dict]:
    """§9: route.merge_group_step_ids에 속한 RDB target 단계들을 UNION ALL
    서브쿼리 하나로 묶어 SQL 레벨에서 정렬·절단까지 끝낸다.

    각 도메인은 _execute_target_step과 완전히 같은 개념->컬럼 해석
    파이프라인(apply_sale_policy -> collect_needed_concepts ->
    resolve_concepts_for_domain -> build_resolved_schema)을 거친다 - 이
    부분은 도메인마다 테이블/카탈로그가 다르므로 원래도 독립적이어야
    하고 고칠 이유가 없다. 다른 점은 "완결된 SELECT문"이 아니라
    format_resolved_schema(union_mode=True)가 만드는, 고정된 4개 별칭
    (code/name/domain/sort_value)만 내보내는 서브쿼리를 생성시킨다는
    것뿐이다. 도메인별 서브쿼리는 Python에서(LLM 없이) UNION ALL로
    이어붙이고, 바깥쪽에 ORDER BY .. NULLS LAST LIMIT을 씌운 완결된
    SQL 하나를 만들어 기존 _run_sql_with_retry에 그대로 실행시킨다 -
    "SQL 텍스트 + 에러 -> 고친 SQL 텍스트" 계약만 지키면 되므로 그 함수는
    UNION 여부를 신경 쓸 필요가 없어 수정하지 않았다.

    반환값은 {step_id: result} 매핑이다. 실제로 SQL을 실행하는 건 한
    번뿐이므로, 그 결과는 그룹에 기여한 도메인 중 첫 번째의 step_id
    (이미 정렬·절단이 끝난 최종 TOP N)에만 담고, 나머지 기여 도메인의
    step_id는 rows=[]와 merged_into 메모만 남긴다 - merge_results_node가
    step_results 전체를 순회해 이어붙일 때 같은 행이 중복되지 않고
    SQL이 만든 순서가 그대로 보존된다. 개념이 없거나(예: 해외ETF의
    1년수익률) 조건이 무효인 도메인은 이 그룹에서만 제외하고 사유를
    남긴다 - 질문 전체를 답변불가 처리하지 않는다."""
    sort_order = sort.get("order") or "desc"
    try:
        if sort_order not in {"asc", "desc"}:
            raise catalog_sql.CompileError("정렬 방향은 asc/desc여야 합니다")
        parsed_limit = catalog_sql.limit_value(sort_limit)
    except catalog_sql.CompileError as exc:
        return {step["step_id"]: {"engine": "rdb", "role": "target", "domain": step["domain"],
                "rows": [], "count": 0, "sql": None, "skipped_reason": str(exc)} for step in steps}

    contributing_step_ids: list[str] = []
    contributing_domains: list[str] = []
    subqueries: list[str] = []
    schema_blocks: list[str] = []
    all_notes: list[str] = []
    results: dict[str, dict] = {}
    output_fields_by_domain: dict[str, list] = {}
    requested_fields_by_domain = {s["domain"]: list(s.get("fields") or []) for s in steps}

    for step in steps:
        step_id = step["step_id"]
        domain = step["domain"]
        if step.get("graph_handoff_blocked"):
            results[step_id] = {"engine": "rdb", "role": "target", "domain": domain,
                               "rows": [], "count": 0, "sql": None,
                               "skipped_reason": step["graph_handoff_blocked"]}
            continue
        step2, policy_notes = utils.apply_sale_policy(step)
        # UNION 서브쿼리는 4개 고정 별칭(상품코드/상품명/도메인/정렬값)만
        # 내보낸다 - 도메인마다 컬럼 구성이 달라도 UNION ALL은 컬럼
        # 개수·순서가 똑같아야 하므로, 이 그룹에서는 다른 요청 필드를
        # 포기하고 "합쳐서 TOP N"에만 집중한다.
        step2 = dict(step2)
        step2["fields"] = ["상품코드"]

        needed_concepts = utils.collect_needed_concepts(step2)
        concept_to_spec, unresolved = utils.resolve_concepts_for_domain(domain, needed_concepts, question, _llm_plan)
        resolved_schema = utils.build_resolved_schema(step2, concept_to_spec, unresolved)
        policy_notes = policy_notes + resolved_schema.get("notes", [])

        skipped_reason = None
        if resolved_schema["unresolved_concepts"]:
            skipped_reason = f"미해결 개념: {resolved_schema['unresolved_concepts']}"
        elif resolved_schema["invalid_conditions"]:
            details = "; ".join(
                f"{r['attribute']}={r['value']!r} ({r['invalid_reason']})" for r in resolved_schema["invalid_conditions"]
            )
            skipped_reason = f"유효하지 않은 조건: {details}"
        elif not resolved_schema["sort"]:
            skipped_reason = "정렬 기준을 이 도메인 컬럼으로 해석하지 못해 그룹 정렬에 참여할 수 없음"

        if skipped_reason:
            results[step_id] = {
                "engine": "rdb", "role": "target", "domain": domain,
                "rows": [], "count": 0, "sql": None, "skipped_reason": skipped_reason,
            }
            continue

        schema_block = utils.format_resolved_schema(resolved_schema, apply_limit=False, union_mode=True)
        try:
            sql_result = catalog_sql.compile_select(resolved_schema, apply_limit=False, union_mode=True)
        except Exception as e:
            # 이 도메인 하나만 그룹에서 제외한다(질문 전체를 죽이지 않는다) -
            # 미해결 개념/무효 조건과 같은 skipped_reason 취급.
            results[step_id] = {
                "engine": "rdb", "role": "target", "domain": domain, "rows": [], "count": 0, "sql": None,
                "skipped_reason": f"SQL 컴파일/스키마 검증 실패로 그룹에서 제외: {e}",
            }
            continue

        contributing_step_ids.append(step_id)
        output_fields_by_domain[domain] = sql_result["output_fields"]
        contributing_domains.append(domain)
        subqueries.append(sql_result["sql"].strip().rstrip(";"))
        schema_blocks.append(f"[{domain} 서브쿼리]\n{schema_block}")
        all_notes.extend(policy_notes)
        all_notes.extend(sql_result.get("assumptions", []))

    if not subqueries:
        # 그룹 전체가 제외됐다(전부 미해결/무효/정렬 불가) - 이미 각
        # step_id에 skipped_reason이 담긴 결과가 있으므로 그대로 반환.
        return results

    order_dir = "ASC" if sort_order == "asc" else "DESC"
    limit_clause = f"\nLIMIT {parsed_limit}" if parsed_limit is not None else ""
    combined_sql = (
        "SELECT * FROM (\n" + "\n  UNION ALL\n".join(subqueries) + "\n) merged\n"
        f"ORDER BY sort_value {order_dir} NULLS LAST{limit_clause}"
    )
    combined_schema_block = "\n\n".join(schema_blocks)

    sql_result = {"sql": combined_sql, "assumptions": [], "compiled": True}
    # domain 인자는 _run_sql_with_retry가 실패 시 rdb_schema.get_full_column_list(domain)
    # 로 "실제 컬럼 전체 목록"을 만드는 데만 쓰인다. 이 쿼리는 여러 테이블에
    # 걸쳐 있어 도메인 하나로는 완전한 목록이 안 되지만, 그 함수는 §9를 위해
    # 수정하지 않기로 했으므로(계획 §9) 첫 번째 기여 도메인을 넘긴다 - 수정 힌트는
    # 주로 DB 에러의 HINT/DETAIL과 위에서 넘기는 combined_schema_block(도메인별
    # 서브쿼리 스키마 전부)에서 나온다.
    run = _run_sql_with_retry(conn, contributing_domains[0], question, combined_schema_block, sql_result, max_retries)

    primary_step_id = contributing_step_ids[0]
    results[primary_step_id] = {
        "engine": "rdb", "role": "target", "domain": "+".join(contributing_domains),
        "rows": run["rows"], "count": len(run["rows"]),
        "sql": run["sql"], "assumptions": all_notes + run["assumptions"],
        "sql_attempts": run["attempts"], "sql_retry_log": run["attempts_log"],
        "output_fields_by_domain": output_fields_by_domain,
        "requested_fields_by_domain": requested_fields_by_domain,
    }
    if run["error"]:
        results[primary_step_id]["error"] = run["error"]
    for step_id, domain in zip(contributing_step_ids[1:], contributing_domains[1:]):
        results[step_id] = {
            "engine": "rdb", "role": "target", "domain": domain,
            "rows": [], "count": 0, "sql": None, "merged_into": primary_step_id,
        }
    return results


# ---------------------------------------------------------------------------
# SQL 실행 + 실패 시 LLM as a judge 재시도 (target/entity_lookup 공유)
# ---------------------------------------------------------------------------
DEFAULT_MAX_SQL_RETRIES = 3


def _fix_sql(question: str, schema_block: str, real_columns_desc: str, wrong_sql: str, error_desc: str) -> dict:
    """실패한 SQL을 [질문 + 해석된 스키마 + 실제 컬럼 전체 목록(설명 포함)
    + 실패한 SQL + Postgres 에러(HINT 포함)]를 근거로 다시 쓰게 한다.
    실제 컬럼 전체 목록을 같이 주는 이유는, 이전 SQL이 존재하지 않는
    컬럼명을 썼을 경우 [해석된 스키마]에 나온 컬럼만으로는 "그럼 진짜
    컬럼명이 뭔지" 알 수 없기 때문이다(오탈자 교정에는 전체 목록이
    필요하다)."""
    structured_llm = _llm_plan.with_structured_output(SQL_OUTPUT_JSON_SCHEMA, method="json_schema")
    return structured_llm.invoke(
        [
            ("system", SQL_FIX_SYSTEM_PROMPT),
            (
                "human",
                f"[원본 질문]\n{question}\n\n[해석된 스키마]\n{schema_block}\n\n"
                f"[실제 컬럼 전체 목록]\n{real_columns_desc}\n\n"
                f"[실패한 SQL]\n{wrong_sql}\n\n[DB 에러]\n{error_desc}",
            ),
        ]
    )


# ---------------------------------------------------------------------------
# 재시도 루프가 쓰는 "실제 컬럼 목록"과 에러 분류 (T-116)
#
# 왜 필요한가: _fix_sql 은 실패한 SQL 을 고치라고 LLM 에게 넘기면서 "실제
# 컬럼 목록"을 근거로 준다. 그 근거가 지금까지 rdb_schema 상수에서 나왔는데,
# 그 상수가 틀려서 SQL 이 실패한 경우(2026-09-05 실측: enriched.etf_kr_enriched
# 는 배포 DB에 없다) 수리 루프는 방금 실패한 것과 같은 오답을 근거로 다시
# 쓴다. 구조적으로 수렴하지 않고 재시도 예산만 태우며, 실패 1건이 LLM 호출
# max_retries 건으로 증폭돼 서버 분당 한도(기본 60)를 밀어 올린다.
# ---------------------------------------------------------------------------

# 서버 rate limit 은 60초 슬라이딩 윈도우다(api.py PUBLIC_RATE_LIMIT_PER_MINUTE).
#
# ⚠ 알려진 한계: 이 값은 Retry-After 를 "존중"한 것이 아니라 윈도우 길이를
# 아는 상태에서의 추정이다. utils.run_sql 이 RuntimeError 로 문자열만 던져
# 헤더가 여기까지 오지 않기 때문이다. 정확히 하려면 (a) 서버가 Retry-After 를
# 주고(T-119) (b) utils.run_sql 이 그 값을 예외에 실어 줘야 한다 - (b)는
# utils.py 라서 이 task 의 write_scope 밖이다.
#
# 대기 횟수를 1회로 묶는다. 사용자 질의 경로라서 최대 체감 지연을 60초
# 안쪽으로 유지해야 하고, 윈도우가 60초이므로 그보다 짧게 기다리면 어차피
# 다시 429 가 난다.
_RATE_LIMIT_WAIT_SECONDS = float(os.environ.get("RDB_API_RATE_LIMIT_WAIT", "60"))
_MAX_RATE_LIMIT_WAITS = 1


def _live_column_list(domain: str, schema_block: str = "") -> str:
    """이 도메인이 SQL 에서 쓸 수 있는 컬럼 목록을 live 스키마 기준으로 만든다.

    컬럼의 존재 여부는 live(information_schema)가 정본이고, 각 컬럼의 설명은
    카탈로그가 정본이다. 둘을 합쳐서 주되, 카탈로그에만 있고 live 에 없는
    컬럼은 "쓰지 말 것"이라고 명시한다 - 그게 바로 수리 루프를 무한히 헛돌게
    만들던 항목이기 때문이다.

    기본 테이블 컬럼만 나열하면 조인으로 들어오는 컬럼(예: 총보수율의
    pm.expense_ratio)을 LLM 이 "없는 컬럼"으로 오해한다. 그래서 조인이
    제공하는 별칭 컬럼도 같이 알려 준다 - **단, 이번 쿼리에 그 조인이 실제로
    등록돼 있을 때만.**

    조인은 질의가 그 개념을 실제로 쓸 때만 resolved_schema 에 등록되고, 그때만
    schema_block 에 "LEFT JOIN ... AS <별칭> ON ..." 줄이 들어간다
    (utils.format_resolved_schema). 등록되지도 않은 별칭을 "그대로 쓸 수
    있다"고 알려 주면, LLM 이 그 별칭을 써서 "missing FROM-clause entry"
    라는 **새로운** 실패를 만든다 - 수리하러 온 함수가 고장을 만드는 셈이다.
    그래서 schema_block 에 실제로 등록된 별칭만 노출한다.

    **live 근거를 못 얻으면 예외를 던진다.** 예전엔 카탈로그로 조용히
    폴백했는데, 그러면 이 함수가 존재하는 이유(틀린 카탈로그로 수리하지
    않기)가 사라진다. 호출부가 이 예외를 받아 수리 자체를 포기한다.
    """
    entry = rdb_schema.DOMAIN_TABLE_INFO.get(domain)
    if not entry:
        raise schema_snapshot.SnapshotUnavailableError(
            f"도메인 {domain!r} 의 기본 테이블을 알 수 없어 live 컬럼 목록을 "
            "만들 수 없다."
        )

    # 실패는 그대로 전파한다(폴백 금지).
    snapshot = schema_snapshot.get_snapshot()
    live_columns = schema_snapshot.get_columns(entry["table"], snapshot)

    catalog_lines = rdb_schema.get_full_column_list(domain)
    # 카탈로그 줄은 "컬럼명 (설명)" 형태다. 컬럼명으로 색인한다.
    described: dict[str, str] = {}
    for line in catalog_lines:
        described[line.split(" (", 1)[0].strip()] = line

    lines = [
        f"[{entry['table']} 의 live 실제 컬럼 {len(live_columns)}개 "
        f"- 이 목록에 없는 컬럼은 DB에 존재하지 않으므로 절대 쓰지 말 것]"
    ]
    lines.extend(described.get(col, f"{col} (카탈로그에 설명 없음)") for col in live_columns)

    stale = sorted(set(described) - set(live_columns))
    if stale:
        lines.append(
            "(카탈로그에는 있으나 live 에 없는 컬럼 - 쓰면 반드시 실패한다: "
            + ", ".join(stale) + ")"
        )

    # 이번 쿼리에 등록된 조인만 노출한다. utils 는 조인을
    # "LEFT JOIN <테이블> AS <별칭> ON <조건>" 으로 렌더하므로 "AS <별칭> ON"
    # 이 schema_block 에 있는지로 판정한다.
    joined = [
        f"{spec.column} ({concept}; {spec.join_alias} 조인으로 제공)"
        for concept, spec in rdb_schema.ATTRIBUTE_CATALOG.get(domain, {}).items()
        if spec.join_table
        and "." in spec.column
        and spec.join_alias
        and f"AS {spec.join_alias} ON" in schema_block
    ]
    if joined:
        lines.append("[이번 쿼리의 JOIN 으로 제공되는 컬럼 - 그대로 쓸 수 있다]")
        lines.extend(joined)
    else:
        # 조인이 없는 쿼리에서 별칭을 쓰면 missing FROM-clause 로 실패한다.
        lines.append(
            "(이번 쿼리에는 JOIN 이 없다. base 테이블에 없는 값은 만들어 낼 수 "
            "없으므로, 별칭(ee., pm. 같은 접두어)을 새로 지어내지 말 것.)"
        )

    return "\n".join(lines)


def _is_rate_limited(error_desc: str) -> bool:
    """서버 분당 한도에 걸린 응답인지."""
    return "HTTP 429" in error_desc or "RATE_LIMITED" in error_desc


def _is_schema_contract_violation(error_desc: str) -> bool:
    """실패 원인이 '카탈로그가 없는 것을 가리켜서'인지 판별한다.

    없는 테이블/컬럼을 참조했다는 에러는 두 가지 원인이 있다.
      (1) LLM 이 없는 이름을 지어냈다  -> 고치라고 시키면 된다.
      (2) 카탈로그 자체가 틀렸다       -> 고치라고 시켜도 같은 근거를 다시
          받으므로 영원히 못 고친다.
    둘을 구분하려고, 그런 에러가 났을 때만 T-115 의 계약 검증을 한 번 돌린다.
    계약이 깨져 있으면 (2)이므로 재시도하지 않고 즉시 멈춘다.
    """
    lowered = error_desc.lower()
    undefined_object = any(
        token in lowered
        for token in ("undefinedtable", "undefinedcolumn", "does not exist", "존재하지")
    )
    if not undefined_object:
        return False
    try:
        rdb_schema.assert_schema_contract()
    except schema_snapshot.SchemaContractError:
        return True
    except Exception:
        # 계약을 확인할 수 없으면 단정하지 않는다(기존 동작 유지).
        return False
    return False


def _run_sql_with_retry(
    conn, domain: str, question: str, schema_block: str, sql_result: dict, max_retries: int
) -> dict:
    """SQL을 실행하고, 실패하면 [질문 + 스키마 + 실제 컬럼 목록 + 실패한
    SQL + Postgres 에러(HINT 포함)]를 판정 LLM(_fix_sql)에게 줘서 다시
    쓰게 한다. 최대 max_retries번 시도하고, 그래도 실패하면 마지막
    에러와 함께 포기한다.

    role="target"과 role="entity_lookup" 양쪽에서 공유한다 - SQL 실행이
    실패했을 때 재시도하는 로직 자체는 두 role이 다를 이유가 없다(둘 다
    "이 SQL을 이 커넥션에 실행한다"는 같은 문제라서). 예전에는 이 재시도
    루프가 entity_lookup 쪽에만, 그것도 target 전용 변수(draft)를 참조하는
    채로 잘못 들어가 있어서 실제로 타면 NameError가 나는 상태였다 - 이
    함수로 분리하면서 그 문제도 같이 없앴다."""
    current_sql = sql_result["sql"]
    assumptions = list(sql_result.get("assumptions", []))
    # [T-116] 근거를 카탈로그 상수가 아니라 live 스키마에서 만든다. 이 한 줄이
    # 바뀌지 않으면 T-115 의 계약 검증이 있어도 수리 루프는 여전히 틀린 근거로
    # 돈다.
    #
    # live 근거를 못 얻으면 카탈로그로 폴백하지 않는다. 폴백하면 정확히
    # 예전 동작(틀린 근거로 수리)으로 되돌아가기 때문이다. 대신 "수리 금지"
    # 상태로 진행한다 - 원래 SQL 은 그대로 한 번 실행해 본다(멀쩡할 수도
    # 있다). 실패했을 때 근거 없이 고치지 않을 뿐이다.
    attempts_log: list[str] = []

    # 예산이 없으면 아무것도 하지 않는다. live 스키마를 먼저 받아 오면
    # 쓰지도 않을 네트워크 호출(테이블 수 + 3회)을 낭비한다.
    if max_retries <= 0:
        return {
            "rows": [], "sql": current_sql, "assumptions": assumptions,
            "attempts": 0, "attempts_log": attempts_log,
            "error": f"재시도 예산이 0 이하라 SQL 을 한 번도 실행하지 않았다(max_retries={max_retries}).",
        }

    try:
        # Compiler already verified every used physical reference. Never repair
        # compiled SQL with an LLM, even if the database later rejects it.
        real_columns_desc = "" if sql_result.get("compiled") else _live_column_list(domain, schema_block)
        repair_allowed = True
        ground_truth_error = ""
    except Exception as exc:
        real_columns_desc = ""
        repair_allowed = False
        ground_truth_error = str(exc)
        attempts_log.append(f"(live 스키마 근거 확보 실패 - SQL 수리 비활성화: {exc})")
        print(
            "[⚠️ 근거 없음] live 스키마를 확인할 수 없어 SQL 자동 수리를 "
            f"비활성화합니다(원래 SQL 은 그대로 1회 실행). 원인: {exc}\n"
        )

    # rate limit 대기는 "SQL 을 고쳐 보는 시도"가 아니므로 재시도 예산을
    # 쓰지 않는다. for 문은 예산과 대기를 구분할 수 없어 while 로 바꿨다.
    attempt = 0
    rate_limit_waits = 0

    while attempt < max_retries:
        attempt += 1
        try:
            # conn.commit()을 여기서 부르지 않는다. Postgres 커넥션이 아니라
            # requests.Session이라 트랜잭션 개념 자체가 없다 - POST 요청
            #하나가 성공 응답을 받은 시점에 이미 서버 쪽에서 조회가
            # 끝난 것이고, 클라이언트가 별도로 커밋할 것이 없다.
            rows = utils.run_sql(conn, current_sql)
            if attempt > 1:
                attempts_log.append(f"시도 {attempt}: 성공")
            return {
                "rows": rows, "sql": current_sql, "assumptions": assumptions,
                "attempts": attempt, "attempts_log": attempts_log, "error": None,
            }
        except Exception as e:
            # conn.rollback()도 같은 이유로 뺐다. requests.Session에는 그런
            # 메서드가 없고(AttributeError로 실제로 확인됨), 실패한 POST
            # 요청은 애초에 서버 쪽에 아무것도 커밋되지 않았으므로 클라이언트가
            # 되돌릴 상태가 없다.
            error_desc = utils.describe_pg_error(e)
            first_line = error_desc.splitlines()[0] if error_desc else "(빈 에러 메시지)"
            attempts_log.append(f"시도 {attempt}: 실패 - {first_line}")

            # [T-116] 고쳐서 될 실패인지 먼저 가른다. 아래 두 종류는 LLM 에게
            # 넘겨도 절대 해결되지 않으므로 재시도 예산을 태우면 안 된다.

            if _is_rate_limited(error_desc):
                # SQL 이 틀린 게 아니라 서버 한도에 걸린 것이다. 여기서 _fix_sql
                # 을 부르면 멀쩡한 SQL 을 LLM 이 "고쳐서" 망가뜨리고, 그 호출이
                # 다시 한도를 밀어 올린다. 같은 SQL 로 기다렸다 다시 친다.
                if rate_limit_waits >= _MAX_RATE_LIMIT_WAITS:
                    print(f"[⏳ 한도 초과] {rate_limit_waits}회 대기 후에도 429. 중단합니다.\n")
                    return {
                        "rows": [], "sql": current_sql, "assumptions": assumptions,
                        "attempts": attempt, "attempts_log": attempts_log,
                        "error": f"서버 분당 요청 한도(429)를 {rate_limit_waits}회 "
                                 f"대기 후에도 넘지 못했다. 마지막 에러: {error_desc}",
                    }
                rate_limit_waits += 1
                attempt -= 1  # 한도 대기는 'SQL 수정 시도'가 아니므로 예산 미소비
                attempts_log.append(
                    f"  (429 - {_RATE_LIMIT_WAIT_SECONDS:.0f}초 대기 후 같은 SQL 재실행, "
                    f"{rate_limit_waits}/{_MAX_RATE_LIMIT_WAITS})"
                )
                print(f"[⏳ 429] 분당 한도. {_RATE_LIMIT_WAIT_SECONDS:.0f}초 대기 후 재시도합니다.\n")
                time.sleep(_RATE_LIMIT_WAIT_SECONDS)
                continue

            if sql_result.get("compiled"):
                attempts_log.append("  (결정론적 SQL: 컬럼/조건 보존을 위해 LLM 수리 금지)")
                return {
                    "rows": [], "sql": current_sql, "assumptions": assumptions,
                    "attempts": attempt, "attempts_log": attempts_log,
                    "error": f"컴파일된 SQL 실행 실패(임의 재작성 안 함): {error_desc}",
                }

            if _is_schema_contract_violation(error_desc):
                # 카탈로그가 없는 것을 가리키고 있다. LLM 에게 고치라고 하면
                # 같은 카탈로그를 근거로 다시 받으므로 영원히 수렴하지 않는다.
                # 여기서 멈추는 것이 재시도 증폭(=429 발생원)을 끊는 지점이다.
                attempts_log.append("  (스키마 계약 위반 - 재시도 무의미, 즉시 중단)")
                print(
                    "[🛑 스키마 계약 위반] 카탈로그가 배포 DB에 없는 테이블/컬럼을 "
                    "가리키고 있습니다. SQL 을 고쳐서 해결될 문제가 아니라 재시도를 "
                    "중단합니다. tools.schema_snapshot 으로 스냅샷을 갱신하고 "
                    "rdb_schema 카탈로그를 맞추세요.\n"
                    f"원인(DB 에러):\n{error_desc}\n"
                )
                return {
                    "rows": [], "sql": current_sql, "assumptions": assumptions,
                    "attempts": attempt, "attempts_log": attempts_log,
                    "error": "스키마 계약 위반으로 재시도 중단(카탈로그가 배포 DB와 "
                             f"어긋남). 마지막 에러: {error_desc}",
                }
            # error_desc가 여러 줄(예: describe_api_error의 검증 에러 목록)이면
            # 첫 줄만으로는 원인을 알 수 없으므로 전체 내용을 별도로 남긴다.
            # _fix_sql에는 이미 error_desc 전체가 그대로 전달되지만, 사람이
            # (노트북 출력에서) 확인할 방법이 없었던 부분을 보완한다.
            if "\n" in error_desc:
                attempts_log.append(f"  (전체 에러 상세)\n{error_desc}")
            # attempts_log는 rdb_search 노드가 전부 끝난 뒤에야 노트북에 모아서
            # 출력된다. utils.run_sql의 "[DEBUG] 서버로 전송하는 SQL" print는
            # 매 시도마다 실시간으로 찍히는데, 실패 원인은 한참 뒤 요약에서만
            # 보여서 "SQL이 왜 바뀌었는지"를 그 자리에서 알 수 없었다. 그래서
            # 같은 정보를 여기서도 바로 print한다(대체가 아니라 추가).
            print(f"\n[❌ SQL 실패] 시도 {attempt}/{max_retries}\n원인(DB 에러):\n{error_desc}\n")

            if attempt == max_retries:
                print(f"[❌ 재시도 소진] {max_retries}회 모두 실패. 마지막 에러:\n{error_desc}\n")
                return {
                    "rows": [], "sql": current_sql, "assumptions": assumptions,
                    "attempts": attempt, "attempts_log": attempts_log,
                    "error": f"{max_retries}회 재시도 후에도 실패. 마지막 에러: {error_desc}",
                }

            if not repair_allowed:
                # live 근거 없이 고치라고 하면 예전과 똑같이 틀린 근거로
                # 헛돌게 된다. 고치지 않고 정직하게 멈춘다.
                attempts_log.append("  (live 근거 없음 - 수리하지 않고 중단)")
                print(
                    "[🛑 수리 중단] live 스키마 근거가 없어 SQL 을 고치지 "
                    "않습니다. 근거 없는 수정은 예전의 무한 재시도로 되돌아갑니다.\n"
                    f"원인(DB 에러):\n{error_desc}\n"
                )
                return {
                    "rows": [], "sql": current_sql, "assumptions": assumptions,
                    "attempts": attempt, "attempts_log": attempts_log,
                    "error": "live 스키마 근거를 얻지 못해 SQL 수리를 중단했다"
                             f"(근거 실패: {ground_truth_error}). DB 에러: {error_desc}",
                }

            # _fix_sql은 Clova LLM에 네트워크 요청을 보낸다. 이 호출 자체가
            # 실패하면(타임아웃, API 오류, 구조화 출력 파싱 실패 등) 예외를
            # 여기서 잡지 않으면 이 함수 밖(rdb_search_node, LangGraph 노드,
            # 결국 app.stream() 루프)까지 그대로 전파되어 노트북에서 이후
            # 노드가 하나도 출력되지 않고 최종 답변도 나오지 않게 된다. 그래서
            # 다른 반환 경로와 같은 형태의 결과를 돌려주고 재시도를 여기서
            # 깨끗하게 중단한다.
            try:
                fix_result = _fix_sql(question, schema_block, real_columns_desc, current_sql, error_desc)
            except Exception as fix_exc:
                attempts_log.append(f"시도 {attempt}: SQL 수정 LLM 호출 실패 - {fix_exc}")
                print(f"[⚠️ SQL 수정 LLM 호출 실패] 시도 {attempt}: {fix_exc}\n재시도를 중단합니다.\n")
                return {
                    "rows": [], "sql": current_sql, "assumptions": assumptions,
                    "attempts": attempt, "attempts_log": attempts_log,
                    "error": f"SQL 수정 LLM 호출 실패로 재시도 중단 (시도 {attempt}/{max_retries}). 원인: {fix_exc}",
                }
            current_sql = fix_result["sql"]
            assumptions = fix_result.get("assumptions", assumptions)
            # SQL_FIX_SYSTEM_PROMPT가 LLM에게 "무엇을 왜 고쳤는지 assumptions에
            # 남기라"고 이미 지시하고 있으므로, LLM이 스스로 판단한 수정 이유는
            # fix_result["assumptions"]에 담겨 있다. 다음 시도 전에 이 이유와
            # 새 SQL을 함께 기록/출력한다 - 실패 원인과 짝을 이루어야 "무엇이
            # 에러나서 어떻게, 왜 고쳤는지"를 그대로 확인할 수 있다.
            fix_reason = "; ".join(fix_result.get("assumptions") or []) or "(LLM이 수정 이유를 남기지 않음)"
            attempts_log.append(f"시도 {attempt}: 수정 이유(LLM 판단) - {fix_reason}")
            attempts_log.append(f"시도 {attempt}: LLM 수정 SQL ->\n{fix_result['sql']}")
            # 이 print는 utils.run_sql이 다음 시도의 "[DEBUG] 서버로 전송하는
            # SQL"을 찍기 직전에 실행되므로, 두 DEBUG 출력 사이에 정확히
            # "왜 이렇게 고쳐졌는지"가 끼어 들어간다.
            print(
                f"[🔧 SQL 수정] 시도 {attempt} 실패 -> 시도 {attempt + 1} 재시도\n"
                f"수정 이유(LLM 판단): {fix_reason}\n"
                f"수정된 SQL:\n{fix_result['sql']}\n"
            )

    # 여기까지 오면 안 된다(max_retries<=0 은 함수 앞에서 이미 걸렀고, 루프는
    # 모든 경로에서 return 한다). 그래도 None 을 흘려보내지는 않는다 - 예전
    # for 문 버전은 이 구멍으로 None 을 내보내 호출부에서 AttributeError 로
    # 터졌다.
    return {
        "rows": [], "sql": current_sql, "assumptions": assumptions,
        "attempts": attempt, "attempts_log": attempts_log,
        "error": "재시도 루프가 결과 없이 종료됐다(도달하면 안 되는 경로).",
    }


def _execute_entity_lookup_step(step: dict, conn, max_retries: int) -> dict:
    """role="entity_lookup"인 RDB 단계(plan_query_db.py의 LLM 폴백이
    만든, 뒤 Graph 단계의 입력만 준비하는 조회). 구조화된 conditions가
    없고 purpose 자연어 문장만 있으므로, 자연어 초안 단계 없이 바로
    SQL 작성 단계로 넘긴다."""
    domain = step["domain"]
    purpose = step.get("purpose", "")
    entry = rdb_schema.get_domain_entry(domain)
    real_columns = rdb_schema.get_full_column_list(domain)
    caveats = rdb_schema.get_sql_caveats(domain)
    caveats_block = ("\n주의사항:\n" + "\n".join(f"- {c}" for c in caveats)) if caveats else ""
    schema_block = f"테이블: {entry['table']}\n실제 컬럼 목록: {', '.join(real_columns)}\n조회 목적: {purpose}{caveats_block}"

    try:
        sql_result = _write_sql(purpose, schema_block)
    except Exception as e:
        return {
            "engine": "rdb", "role": "entity_lookup", "domain": domain, "rows": [], "count": 0, "sql": None,
            "error": f"SQL 생성 LLM 호출 실패: {e}",
        }

    run = _run_sql_with_retry(conn, domain, purpose, schema_block, sql_result, max_retries)
    result = {
        "engine": "rdb", "role": "entity_lookup", "domain": domain,
        "rows": run["rows"], "count": len(run["rows"]),
        "sql": run["sql"], "assumptions": run["assumptions"],
        "sql_attempts": run["attempts"], "sql_retry_log": run["attempts_log"],
    }
    if run["error"]:
        result["error"] = run["error"]
    return result


def _apply_graph_handoff(step: dict, step_results: dict[str, Any]) -> dict:
    """Graph -> RDB 핸드오프(§8). 이 RDB 단계가 의존하는 Graph 단계
    결과(§5 웨이브 스케줄러 덕분에 이 시점엔 이미 state["step_results"]에
    들어 있다)에 entity_codes가 있으면 "상품코드 in (...)" 조건 하나를
    끼워 넣는다.

    새 컴파일러나 새 실행 경로를 만들지 않는다 - `utils.build_condition_list`가
    product_name_entities를 `{"attribute": "상품명", "operator": "contains", ...}`
    조건으로 흡수해 끼워 넣는 것과 정확히 같은 패턴이다. attribute="상품코드"는
    rdb_schema.py의 개념->컬럼 카탈로그(도메인별 pd_no/pd_itm_no/itm_no, 전부
    GraphDB의 fp:productCode와 값이 같은 ISIN/RIC임을 확인)가 이미 실제
    컬럼으로 매핑하므로, 이후는 기존 자연어 초안 -> SQL 생성 파이프라인이
    그대로 처리한다."""
    entity_codes: list[str] = []
    for dep_id in step.get("depends_on") or []:
        dep_result = step_results.get(dep_id) or {}
        if dep_result.get("engine") == "graph":
            codes = dep_result.get("entity_codes") or []
            if dep_result.get("error") or not codes:
                return {**step, "graph_handoff_blocked":
                        f"선행 Graph 단계 {dep_id}에서 관계에 맞는 상품코드를 확보하지 못해 제한 없는 RDB 조회를 중단했습니다."}
            entity_codes.extend(codes)
    if not entity_codes:
        return step
    entity_codes = list(dict.fromkeys(entity_codes))  # 중복 제거, 순서는 유지
    new_step = dict(step)
    new_step["conditions"] = list(step.get("conditions") or []) + [
        {"attribute": "상품코드", "operator": "in", "value": ", ".join(entity_codes), "value_2": ""}
    ]
    return new_step


def rdb_search_node(state: PipelineState) -> dict:
    plan = state.get("plan") or []
    route = state.get("route") or {}
    # §5 웨이브 스케줄러: graph.py의 dispatch가 "이번 웨이브에 rdb 엔진이
    # 준비됐다"고 판단해서 이 노드를 불렀더라도, plan에는 아직 depends_on이
    # 안 채워진 다른 rdb 단계가 같이 있을 수 있다(교차질의처럼 rdb 단계가
    # 여러 개인데 그중 일부만 이번 웨이브에 준비된 경우). ready_step_ids로
    # "이미 끝났거나 아직 준비 안 된" 단계를 걸러내고 이번 웨이브 몫만 처리한다.
    done = set((state.get("step_results") or {}).keys())
    ready = ready_step_ids(plan, done)
    rdb_steps = [s for s in plan if s.get("engine") == "rdb" and s["step_id"] in ready]

    if not rdb_steps:
        return {"trace": ["RDB 검색: 이번 웨이브에 실행할 RDB 단계가 없어 건너뜀"]}

    # 재시도 횟수는 사용자가 지정할 수 있다: app.invoke({"question": ...,
    # "max_sql_retries": 5})처럼 호출 시점에 state로 넘기면 그 값을 쓰고,
    # 안 주면 DEFAULT_MAX_SQL_RETRIES(3)를 쓴다.
    max_retries = state.get("max_sql_retries") or DEFAULT_MAX_SQL_RETRIES

    try:
        conn = utils.get_pg_connection()
    except Exception as e:
        step_results = {s["step_id"]: {"engine": "rdb", "rows": [], "count": 0, "error": f"DB 연결 실패: {e}"} for s in rdb_steps}
        return {"step_results": step_results, "trace": [f"RDB 검색: Postgres 연결 실패 - {e}"]}

    step_results: dict[str, Any] = {}
    trace_msgs: list[str] = []
    apply_limit = not route.get("needs_merge_rank", False)
    all_step_results = state.get("step_results") or {}

    # §9: route.merge_group_step_ids에 속한 단계들은 개별 실행이 아니라
    # UNION ALL 한 번으로 묶는다. 이번 웨이브에 그 그룹의 멤버가 전부(2개
    # 이상) 준비돼야 묶을 수 있다 - 일부만 준비됐으면(§5 웨이브 스케줄러와의
    # 알려진 제약, 계획서 §4 참고) UNION의 의미가 없으므로 그냥 개별 경로로
    # 처리한다(정렬은 못 하지만 조회 자체는 된다).
    merge_group_ids = set(route.get("merge_group_step_ids") or [])
    group_steps = [s for s in rdb_steps if s["step_id"] in merge_group_ids]
    group_steps = [_apply_graph_handoff(s, all_step_results) for s in group_steps]
    solo_steps = [s for s in rdb_steps if s["step_id"] not in merge_group_ids]

    try:
        if len(group_steps) >= 2:
            sort = group_steps[0].get("sort") or {}
            sort_limit = route.get("sort_limit", "")
            group_results = _execute_merged_target_group(
                group_steps, state.get("question", ""), conn, sort, sort_limit, max_retries
            )
            step_results.update(group_results)
            for step_id, result in group_results.items():
                if result.get("merged_into"):
                    trace_msgs.append(f"RDB 검색 [{step_id}]: UNION 그룹으로 처리됨 (결과는 {result['merged_into']}에 포함)")
                elif result.get("error"):
                    trace_msgs.append(f"RDB 검색 [{step_id}]: 오류({result.get('sql_attempts','?')}회 시도) - {result['error']}")
                elif result.get("skipped_reason"):
                    trace_msgs.append(f"RDB 검색 [{step_id}]: 건너뜀 - {result['skipped_reason']}")
                else:
                    domain_count = len(result["domain"].split("+"))
                    trace_msgs.append(
                        f"RDB 검색 [{step_id}]: UNION ALL로 {domain_count}개 도메인 합쳐 "
                        f"{result['count']}건 조회(이미 정렬·절단 완료)"
                    )
        elif group_steps:
            trace_msgs.append(
                f"RDB 검색: UNION 그룹 멤버가 이번 웨이브에 {len(group_steps)}개만 준비돼 "
                "개별 경로로 처리합니다(§5 알려진 제약)."
            )
            solo_steps = solo_steps + group_steps

        for step in solo_steps:
            step_id = step["step_id"]
            if step.get("role") == "entity_lookup":
                result = _execute_entity_lookup_step(step, conn, max_retries)
            else:
                # §8 Graph -> RDB 핸드오프: 이 단계가 의존하는 Graph 단계의
                # entity_codes를 "상품코드 in (...)" 조건으로 주입한다.
                # 대부분의 질문은 depends_on이 비어 있거나 Graph를 안
                # 기다리므로 이 함수는 아무것도 안 바꾸고 그대로 통과시킨다.
                handoff_step = _apply_graph_handoff(step, all_step_results)
                if handoff_step is not step and not handoff_step.get("graph_handoff_blocked"):
                    injected = handoff_step["conditions"][-1]
                    trace_msgs.append(
                        f"RDB 검색 [{step_id}]: Graph 핸드오프 - 상품코드 {len(injected['value'].split(', '))}개 조건 주입"
                    )
                result = _execute_target_step(handoff_step, state.get("question", ""), conn, apply_limit, max_retries)
            step_results[step_id] = result

            if result.get("error"):
                trace_msgs.append(f"RDB 검색 [{step_id}]: 오류({result.get('sql_attempts','?')}회 시도) - {result['error']}")
            elif result.get("skipped_reason"):
                trace_msgs.append(f"RDB 검색 [{step_id}]: 건너뜀 - {result['skipped_reason']}")
            elif result.get("sql_attempts", 1) > 1:
                trace_msgs.append(f"RDB 검색 [{step_id}]: {result['count']}건 조회 (재시도 {result['sql_attempts']}회만에 성공)")
            else:
                trace_msgs.append(f"RDB 검색 [{step_id}]: {result['count']}건 조회")
    finally:
        conn.close()

    return {"step_results": step_results, "trace": trace_msgs}


# ---------------------------------------------------------------------------
# 노드 4b: GraphDB 검색 (실구현 - graph_orchestrator.run())
# ---------------------------------------------------------------------------
def _chain_root_relation(relation: dict, relations_by_id: dict[str, dict]) -> dict:
    """object_ref 체인을 따라 올라가 최초로 object_entity가 채워진 relation을
    찾는다. graph_orchestrator.run()의 엔티티 해소는 "이름 하나 -> URI
    하나"를 전제하는 단일 seed 모델이라, 여러 단계로 이어진 relation
    체인이어도 실제로 이름이 주어진 가장 처음 relation까지 거슬러 올라가야
    resolve_frame_seed가 쓸 seed 문자열을 구할 수 있다."""
    current = relation
    seen: set[str] = set()
    while not current.get("object_entity") and current.get("object_ref"):
        ref = current["object_ref"]
        if ref in seen or ref not in relations_by_id:
            break
        seen.add(ref)
        current = relations_by_id[ref]
    return current


def _build_graph_frame(relation: dict, relations_by_id: dict[str, dict]) -> dict:
    """relation.object_entity/entity_role(§2에서 추가)을
    graph_entity.resolve_frame_seed가 기대하는
    {"entities":[{"text":...,"role":...}]} 모양으로 바꾸는 어댑터.
    object_ref로 이어진 체인이면 _chain_root_relation으로 최초 이름까지
    거슬러 올라간다."""
    root = _chain_root_relation(relation, relations_by_id)
    text = (root.get("object_entity") or "").strip()
    role = root.get("entity_role") or "product"
    return {
        "entities": [{"text": text, "role": role}] if text else [],
        "relations": [],
        "requested_fields": [],
        "constraints": [],
        "limit": 100,
    }


def graph_search_node(state: PipelineState) -> dict:
    """graph_orchestrator.run()으로 실제 SPARQL 조회를 수행한다.

    §5 웨이브 스케줄러: rdb_search_node와 같은 이유로 ready_step_ids로
    "이번 웨이브에 준비되고 아직 안 한" graph 단계만 골라 처리한다.

    [relation 체인의 중간 단계는 조회하지 않는다] object_ref로 다른 relation
    을 참조하는 relation(체인의 마지막이 아닌 것)은 실제 SPARQL 조회를
    하지 않고 자리만 채운다("chained" 상태) - graph_orchestrator.run()은
    seed 하나에서 전체 관계 경로를 한 SPARQL로 컴파일하는 방식이라(예:
    "에코프로의 자회사가 편입한 ETF"는 subsidiary_holding_etf_plan 하나가
    자회사->증권->보유->ETF까지 전부 처리한다), 중간 단계를 따로 조회하면
    같은 조회를 중복하거나 중간 결과(회사 목록)를 다음 단계에 넘길 방법이
    없다. 실제 조회는 체인의 마지막(terminal) 단계에서, 체인 최초의
    object_entity를 seed로 삼아 한 번에 수행된다(_build_graph_frame 참고).
    이는 팀원의 gragh-test 노트북이 애초에 "seed 하나 -> 전체 경로"로
    설계된 것과 같은 제약이다."""
    plan = state.get("plan") or []
    done = set((state.get("step_results") or {}).keys())
    ready = ready_step_ids(plan, done)
    graph_steps = [s for s in plan if s.get("engine") == "graph" and s["step_id"] in ready]

    if not graph_steps:
        return {"trace": ["GraphDB 검색: 이번 웨이브에 실행할 Graph 단계가 없어 건너뜀"]}

    question = state.get("question", "")
    all_graph_steps = [s for s in plan if s.get("engine") == "graph"]
    relations_by_id = {s["relation"]["id"]: s["relation"] for s in all_graph_steps}
    referenced_ids = {r.get("object_ref") for r in relations_by_id.values() if r.get("object_ref")}

    step_results: dict[str, Any] = {}
    trace_msgs: list[str] = []

    for step in graph_steps:
        step_id = step["step_id"]
        relation = step["relation"]
        is_terminal = relation["id"] not in referenced_ids

        # "체인 중간 단계"는 relation 자체가 object_ref를 쓰는지가 아니라
        # 다른 relation의 object_ref로 "참조되는지"(= terminal이 아닌지)로
        # 판단한다. 체인의 시작 relation(예: "에코프로의 자회사"의 R1)은
        # 자기 자신은 object_ref를 안 쓰지만(object_entity로 직접 이름을
        # 줌) 뒤의 relation(R2)에게 참조되는 non-terminal이다 - 이걸 여기서
        # 실행해버리면 terminal 단계(R2)가 나중에 또 같은 조회를 반복하거나
        # (원래 있던 버그, 2026-09-02 실측) seed를 잘못 잡는다. 체인의
        # 실제 다단계 조회는 terminal 단계 하나에서만 수행한다.
        if not is_terminal:
            step_results[step_id] = {
                "engine": "graph", "status": "chained", "rows": [],
                "entity_codes": [], "evidence": [],
                "note": "체인 중간 단계 - terminal 단계에서 함께 처리됨",
            }
            trace_msgs.append(f"GraphDB 검색 [{step_id}]: 체인 중간 단계 - terminal 단계에서 함께 처리")
            continue

        frame = _build_graph_frame(relation, relations_by_id)
        if not frame["entities"]:
            step_results[step_id] = {
                "engine": "graph", "status": "abstain_no_seed_text", "rows": [],
                "entity_codes": [], "evidence": [],
                "note": "관계 주체의 이름(object_entity)을 찾지 못해 조회를 건너뜀",
            }
            trace_msgs.append(f"GraphDB 검색 [{step_id}]: 주체 이름 없음 - 건너뜀")
            continue

        try:
            # 테마 관계는 일반 seed 해소(resolve_frame_seed, "이름 하나 ->
            # URI 하나")로 처리하지 않는다. "반도체"처럼 사용자가 쓰는
            # 키워드는 LSEG 176테마 taxonomy에서 흔히 여러 하위 테마
            # ("K-반도체","글로벌반도체" 등)에 걸쳐 있어 후보가 2개 이상이면
            # 곧장 ambiguous로 멈추는 일반 경로로는 항상 실패한다(2026-09-02
            # 실측). entity_role="theme"이면 후보 테마를 전부 찾아 합치는
            # 전용 경로(run_theme_membership)로 보낸다.
            if frame["entities"][0]["role"] == "theme":
                result = graph_orchestrator.run_theme_membership(question, frame["entities"][0]["text"])
            else:
                result = graph_orchestrator.run(question, frame=frame)
        except Exception as e:
            # 예외 문구를 note에도 남긴다 - trace만 두면 step_results 조립에서
            # 버려져 노트북에 status만 보이고 원인을 추적할 수 없었다(2026-09-03).
            result = {"status": "abstain_exception", "rows": [], "evidence": [],
                      "entity_codes": [], "trace": [f"{type(e).__name__}: {e}"],
                      "note": f"{type(e).__name__}: {e}"}

        step_results[step_id] = {
            "engine": "graph",
            "status": result.get("status"),
            "rows": result.get("rows", []),
            "entity_codes": result.get("entity_codes", []),
            "evidence": result.get("evidence", []),
            "entity": result.get("entity"),
            "sparql": result.get("sparql"),
            "note": result.get("note"),
        }
        trace_msgs.append(
            f"GraphDB 검색 [{step_id}]: status={result.get('status')}, "
            f"{len(result.get('rows', []))}건 조회, entity_codes={len(result.get('entity_codes', []))}건"
        )

    return {"step_results": step_results, "trace": trace_msgs}


# ---------------------------------------------------------------------------
# 노드 4c: VectorDB 검색
# ---------------------------------------------------------------------------
# 0828 실험 노트북에서 확인한 값들. 실제 top1 점수가 0.55~0.68 구간이라
# 0.45 아래는 "질문과 무관한 문서를 억지로 인용"하는 쪽에 가까웠다.
VECTOR_SCORE_FLOOR = 0.45
VECTOR_MAX_TOPICS = 3
VECTOR_DEFAULT_TOP_K = 5
VECTOR_SCOPE_LIMIT = 50
# RDB 결과 행에는 LLM이 고른 컬럼만 담긴다(예: pd_nm, pd_net_tamt만).
# 코드 컬럼이 아예 없는 경우가 흔해서 이름 컬럼으로도 스코프를 잡아야 한다.
VECTOR_CODE_KEYS = ("pd_itm_no", "itm_no", "pd_no", "상품코드", "product_id", "code")
VECTOR_NAME_KEYS = ("pd_nm", "itm_nm", "상품명", "name", "product_name")
# 요청 주제 ↔ vec.document_chunk.section_type 대조용 힌트. 847/974 문서가
# 표지 투자위험 요약(risk) 청크뿐이라, 섹션을 제한하지 않으면 '운용 전략'
# 질문에도 위험 청크가 floor를 넘겨 인용된다(2026-09-03 실측).
VECTOR_SECTION_HINTS = {
    "objective_strategy": ("전략", "투자목적", "투자 목적", "운용목표", "운용 목표", "운용방침", "운용 방침"),
    "risk": ("위험", "리스크"),
    "base_index": ("기초지수", "기초 지수", "비교지수", "벤치마크", "추적"),
}
VECTOR_SECTION_LABELS = {"objective_strategy": "투자목적·운용전략", "risk": "투자위험", "base_index": "기초지수"}


def _section_hints(labels: list[str]) -> dict[str, list[str]]:
    """요청 주제 라벨을 section_type별로 묶는다(매칭된 섹션만 반환).

    질문 원문은 보지 않는다 - "미래에셋에서 운용하는"처럼 상품명·운용사
    표현이 '운용'에 걸려 엉뚱한 섹션을 요청하게 되기 때문이다."""
    hints: dict[str, list[str]] = {}
    for label in labels:
        text = str(label)
        for section, keywords in VECTOR_SECTION_HINTS.items():
            if any(keyword in text for keyword in keywords):
                bucket = hints.setdefault(section, [])
                if text not in bucket:
                    bucket.append(text)
    return hints


def _vector_scope(state: PipelineState, step: dict) -> tuple[list[str], list[str]]:
    """이 Vector 단계가 근거를 찾아야 할 상품의 (코드, 이름) 후보를 모은다.
    intent/step의 product_name 엔티티와 depends_on 단계의 RDB 행·Graph
    entity_codes가 출처다. 순서를 유지한 채 중복만 제거한다."""
    codes: list[str] = []
    names: list[str] = []

    def push(bucket: list[str], value: Any) -> None:
        text = str(value).strip()
        if text and text not in bucket:
            bucket.append(text)

    entity_sources = [
        (state.get("intent") or {}).get("target_entities") or [],
        step.get("target_entities") or [],
    ]
    for entities in entity_sources:
        for entity in entities:
            if entity.get("entity_type") == "product_name":
                push(names, entity.get("surface_form") or "")

    step_results = state.get("step_results") or {}
    for dep_id in step.get("depends_on") or []:
        dep = step_results.get(dep_id) or {}
        if dep.get("engine") == "rdb":
            for row in dep.get("rows") or []:
                for key in VECTOR_CODE_KEYS:
                    if row.get(key):
                        push(codes, row[key])
                for key in VECTOR_NAME_KEYS:
                    if row.get(key):
                        push(names, row[key])
        elif dep.get("engine") == "graph":
            for code in dep.get("entity_codes") or []:
                push(codes, code)

    return codes[:VECTOR_SCOPE_LIMIT], names[:VECTOR_SCOPE_LIMIT]


def _summarize_coverage(product_ids: list[str], coverage: dict[str, dict]) -> dict[str, int]:
    """product_coverage 상태를 4분류로 센다. 테이블에 행이 아예 없는
    상품은 unknown(=문서가 없다고 단정할 수 없음)으로 둔다."""
    summary = {"matched": 0, "unavailable": 0, "download_failed": 0, "unknown": 0}
    for product_id in product_ids:
        status = (coverage.get(product_id) or {}).get("status")
        if isinstance(status, str) and status.startswith("matched"):
            summary["matched"] += 1
        elif status in summary:
            summary[status] += 1
        else:
            summary["unknown"] += 1
    return summary


def _normalize_chunk(chunk: dict) -> dict:
    """psycopg2는 date 객체를, SQL API는 문자열을 돌려준다. 답변·직렬화
    단계가 형을 신경 쓰지 않도록 여기서 한 번만 맞춘다."""
    return {
        "chunk_id": str(chunk.get("chunk_id")),
        "document_id": str(chunk.get("document_id") or ""),
        "section_type": chunk.get("section_type") or "",
        "citation_text": chunk.get("citation_text") or "",
        "chunk_text": chunk.get("chunk_text") or "",
        "score": float(chunk.get("score") or 0.0),
        "effective_as_of": str(chunk.get("effective_as_of") or ""),
        "published_at": str(chunk.get("published_at") or ""),
        "source_url": chunk.get("source_url") or "",
        "product_ids": list(chunk.get("product_ids") or []),
    }


def _run_vector_step(state: PipelineState, step: dict, question: str) -> dict:
    """Vector 단계 하나를 실행한다.

    스코프 해소 -> topics/fields를 section_type 힌트로 변환 -> 섹션 제한
    검색 -> 상태 판정 순서다. 요청 주제 섹션이 하나도 안 걸리면 결과가
    없을 때 topic_not_covered로 남기고, 걸린 결과가 있어도 미확보 주제를
    topic_coverage/note에 적는다."""
    codes, names = _vector_scope(state, step)
    product_ids = resolve_product_ids(codes, names) if (codes or names) else []
    coverage = get_coverage(product_ids) if product_ids else {}
    summary = _summarize_coverage(product_ids, coverage)

    if (codes or names) and not product_ids:
        # 상품을 지목했는데 product_master 완전일치에 실패한 경우다. 여기서
        # 전체 문서로 넓히면 다른 상품의 투자설명서를 그 상품의 근거처럼
        # 인용하게 되므로(상품명 완전일치 우선·유사명 대체 금지) 검색을
        # 생략하고 사유만 남긴다.
        return {
            "engine": "vector", "status": "no_product_match",
            "chunks": [], "count": 0, "queries": [],
            "product_scope": {"codes": codes, "names": names, "product_ids": [], "coverage": summary},
            "raw_top": [],
            "topic_coverage": {"requested": {}, "uncovered": {}},
            "note": f"상품 후보 {len(codes) + len(names)}건을 product_master에서 해소하지 못해 문서 검색 생략",
        }

    # topic마다 따로 임베딩한다. "투자 위험"과 "기초지수"는 문서 안에서
    # 서로 다른 section에 있어서 질문 하나로는 한쪽만 걸린다.
    topics = (step.get("topics") or [])[:VECTOR_MAX_TOPICS]
    labels = topics + [f for f in (step.get("fields") or []) if f not in topics]
    hints = _section_hints(labels)
    section_types = list(hints) or None
    queries = [f"{question} {topic}".strip() for topic in topics] or [question]

    merged: dict[str, dict] = {}
    for query in queries:
        for raw in search_documents(
            embed(query),
            top_k=step.get("top_k", VECTOR_DEFAULT_TOP_K),
            product_ids=product_ids or None,
            section_types=section_types,
        ):
            chunk = _normalize_chunk(raw)
            previous = merged.get(chunk["chunk_id"])
            if previous is None or chunk["score"] > previous["score"]:
                merged[chunk["chunk_id"]] = chunk

    ordered = sorted(merged.values(), key=lambda c: c["score"], reverse=True)
    raw_top = [(c["chunk_id"], round(c["score"], 3)) for c in ordered[:5]]
    chunks = [c for c in ordered if c["score"] >= VECTOR_SCORE_FLOOR]

    found = {c["section_type"] for c in chunks}
    uncovered = {sec: labs for sec, labs in hints.items() if sec not in found}

    missing = summary["unavailable"] + summary["download_failed"]
    if chunks:
        status = "ok"
    elif ordered:
        status = "low_confidence"
    elif product_ids and summary["matched"] == 0 and missing > 0:
        # 상품은 특정했는데 그 상품의 투자설명서 자체가 없는 경우다.
        # "검색 결과 없음"과 구분해야 답변이 사유를 정확히 말할 수 있다.
        status = "no_document"
    elif hints:
        # 문서는 있으나 요청 주제 섹션이 없다(예: risk 청크만 적재된 문서).
        status = "topic_not_covered"
    else:
        status = "no_hit"

    scope_note = (
        f"스코프 {len(product_ids)}상품(문서 확보 {summary['matched']}, 미확보 {missing})"
        if product_ids else "스코프 없음(전체 문서 검색)"
    )
    note = f"{scope_note}, 청크 {len(chunks)}건(≥{VECTOR_SCORE_FLOOR})"
    if uncovered:
        note += ", 요청 주제 미확보: " + "; ".join(
            f"{'/'.join(labs)}({VECTOR_SECTION_LABELS[sec]} 섹션 없음)"
            for sec, labs in uncovered.items()
        )
    return {
        "engine": "vector",
        "status": status,
        "chunks": chunks,
        "count": len(chunks),
        "queries": queries,
        "product_scope": {
            "codes": codes, "names": names,
            "product_ids": product_ids, "coverage": summary,
        },
        "raw_top": raw_top,
        "topic_coverage": {"requested": hints, "uncovered": uncovered},
        "note": note,
    }


def vector_search_node(state: PipelineState) -> dict:
    """Vector 단계별로 상품 스코프를 해소하고 pgvector 근거 청크를 검색한다.

    [흐름] ready_step_ids로 이번 웨이브 몫만 고른 뒤, 단계마다
    _vector_scope -> resolve_product_ids -> get_coverage -> section 힌트
    산출 -> topic별 embed+search_documents(섹션 제한) -> chunk_id 중복
    제거 -> SCORE_FLOOR 필터를 돈다.

    [입출력] state의 question/intent/plan/step_results를 읽고
    {step_id: {status, chunks, count, queries, product_scope, raw_top,
    topic_coverage, note}}와 trace를 반환한다. 요청 주제 섹션이 문서에
    없으면 status=topic_not_covered다.

    [실패·제약] 임베딩/DB 장애는 그 단계만 abstain_vector_unavailable로
    남기고 다른 단계는 계속 실행한다. vector 단계는 설계상 rdb/graph
    단계에 의존하므로(plan_query_db.py) 보통 마지막 웨이브에서만 준비된다.

    [구현 상태] 스코프·커버리지·검색·상태 판정까지 실동작한다."""
    plan = state.get("plan") or []
    done = set((state.get("step_results") or {}).keys())
    ready = ready_step_ids(plan, done)
    vector_steps = [s for s in plan if s.get("engine") == "vector" and s["step_id"] in ready]

    if not vector_steps:
        return {"trace": ["VectorDB 검색: 이번 웨이브에 실행할 Vector 단계가 없어 건너뜀"]}

    question = state.get("question", "")
    step_results: dict[str, Any] = {}
    trace_msgs: list[str] = []

    for step in vector_steps:
        step_id = step["step_id"]
        # 단계별로 감싼다 - 한 단계의 임베딩/DB 실패가 다른 단계까지
        # 죽이면 근거를 더 모을 수 있었던 질문도 통째로 답변불가가 된다.
        try:
            result = _run_vector_step(state, step, question)
        except Exception as exc:
            result = {
                "engine": "vector", "status": "abstain_vector_unavailable",
                "chunks": [], "count": 0,
                "error": f"{type(exc).__name__}: {exc}",
            }
            trace_msgs.append(f"VectorDB 검색 [{step_id}]: 검색 불가 - {result['error']}")
        else:
            scope = result["product_scope"]
            trace_msgs.append(
                f"VectorDB 검색 [{step_id}]: status={result['status']}, {result['count']}건 "
                f"(스코프 {len(scope['product_ids'])}상품, 문서확보 {scope['coverage']['matched']})"
                + (f", 미확보 주제 {len(result['topic_coverage']['uncovered'])}건"
                   if result["topic_coverage"]["uncovered"] else "")
            )
        step_results[step_id] = result

    return {"step_results": step_results, "trace": trace_msgs}


# ---------------------------------------------------------------------------
# 노드 5: 결과 합치기
# ---------------------------------------------------------------------------
def merge_results_node(state: PipelineState) -> dict:
    """RDB의 role="target" 결과와 Graph 결과를 하나의 행 목록으로 모은다.
    각 행에 _domain을 태그해서 어느 도메인/엔진에서 왔는지 답변 생성
    단계가 알 수 있게 한다.

    [§9 갱신] route.needs_merge_rank가 True인 교차질의는 이제
    rdb_search_node가 _execute_merged_target_group으로 도메인별 서브쿼리를
    UNION ALL + ORDER BY + LIMIT 하나로 SQL 레벨에서 이미 정렬·절단해서
    돌려준다 - 그 결과는 그룹의 대표 step_id 하나에만 담겨 있고, 나머지
    그룹 멤버의 step_id는 rows가 비어 있으므로(merged_into만 있음) 여기서
    그냥 순서대로 이어붙이기만 해도 SQL이 만든 순서가 그대로 보존된다.
    Python에서 다시 정렬할 필요가 없다(예전엔 "아직 미구현"이었던 부분).

    [Vector 갱신] vector 단계의 청크도 청크 하나당 한 행씩(_domain="vector")
    같은 목록에 넣는다. 답변 생성 LLM이 수치 행과 문서 인용을 한 자리에서
    보고, _build_answer_preview의 도메인별 예산 분배도 그대로 적용받게 하기
    위해서다. 본문은 400자로 자른다(전문은 step_results에 그대로 남는다).
    "섹션"에 VECTOR_SECTION_LABELS로 바꾼 section_type 라벨을 담아, 답변
    생성 LLM이 이 행의 섹션이 질문이 요청한 주제와 같은지 대조할 수 있게 한다.

    UNION 결과의 행에는 SELECT 목록 자체에 이미 "domain" 컬럼(리터럴
    문자열)이 들어 있다 - 한 결과 안에 여러 도메인 행이 섞여 있어서
    result.get("domain")(합성 라벨, 예: "국내ETF+해외ETF+펀드") 하나로는
    행마다 실제 출처를 구분할 수 없기 때문이다. 행 자체에 "domain"이
    있으면 그 값을 우선하고, 없으면(일반 단일 도메인 결과) 지금처럼
    result.get("domain")을 쓴다.

    Graph 단계가 §8 핸드오프의 입력으로만 쓰인 경우에도 그 결과를 빼지
    않는다 - "에코프로의 자회사가 어디인지" 자체도 근거 있는 사실이라
    최종 답변·evidence에 노출하는 편이 낫다는 판단이다."""
    step_results = state.get("step_results") or {}

    merged_rows: list[dict] = []
    for step_id, result in step_results.items():
        if result.get("engine") == "rdb" and result.get("role", "target") == "target":
            for row in result.get("rows", []):
                tagged = dict(row)
                tagged["_domain"] = row.get("domain") or result.get("domain")
                tagged["_step_id"] = step_id
                merged_rows.append(tagged)
        elif result.get("engine") == "graph":
            for row in result.get("rows", []):
                tagged = dict(row)
                tagged["_domain"] = "graph"
                tagged["_step_id"] = step_id
                merged_rows.append(tagged)
        elif result.get("engine") == "vector":
            for chunk in result.get("chunks") or []:
                merged_rows.append({
                    "출처문서": chunk.get("citation_text", ""),
                    "섹션": VECTOR_SECTION_LABELS.get(chunk.get("section_type", ""), chunk.get("section_type", "")),
                    "인용": (chunk.get("chunk_text") or "")[:400],
                    "기준일": chunk.get("effective_as_of", ""),
                    "출처URL": chunk.get("source_url", ""),
                    "상품ID": ", ".join(chunk.get("product_ids") or []),
                    "유사도": round(float(chunk.get("score") or 0.0), 3),
                    "_domain": "vector",
                    "_step_id": step_id,
                })

    return {"merged_rows": merged_rows, "trace": [f"결과 합치기: {len(merged_rows)}행"]}


# ---------------------------------------------------------------------------
# 노드 6: 답변 생성
# ---------------------------------------------------------------------------
def _describe_applied_conditions(intent: dict) -> str:
    """intent에서 이미 SQL로 적용된 조건을 사람이 읽는 한 줄 요약으로
    만든다. 답변 생성 LLM에게 "이 조건들은 이미 필터링에 반영됐다"는
    걸 구체적으로 보여줘서, 반환된 행에 그 컬럼이 안 보인다는 이유로
    "확인할 수 없다"고 잘못 판단하지 않게 하기 위한 이중 안전장치다
    (1차 방어는 ANSWER_SYSTEM_PROMPT 자체에 있다)."""
    parts = []
    for d in intent.get("product_domain") or []:
        if d.get("subtype"):
            parts.append(f"{d['domain']} 중 {', '.join(d['subtype'])}")
    for c in intent.get("conditions") or []:
        parts.append(f"{c['attribute']} {c['operator']} {c['value']}")
    sort = intent.get("sort") or {}
    if sort.get("attribute"):
        limit_desc = f", 상위 {sort['limit']}개" if sort.get("limit") else ""
        parts.append(f"{sort['attribute']} {sort['order']} 정렬{limit_desc}")
    return "; ".join(parts) if parts else "(특별한 조건 없음)"


def _describe_requested_items(intent: dict) -> str:
    """intent.output_requirements(fields/narrative_topics)를 답변 LLM에게
    "이 항목만 다루라"고 보여줄 한 줄로 요약한다. 질문이 요구하지 않은
    화제(예금자보호 등)까지 답에 섞이는 걸 막는 1차 방어다."""
    req = intent.get("output_requirements") or {}
    parts = []
    fields = req.get("fields") or []
    if fields:
        parts.append(f"구조화 값: {', '.join(fields)}")
    topics = req.get("narrative_topics") or []
    if topics:
        parts.append(f"서술 주제: {', '.join(topics)}")
    return "; ".join(parts) if parts else "(명시된 항목 없음 - 질문 원문을 따른다)"


def _describe_vector_status(step_results: dict) -> str:
    """각 Vector 단계의 status·note/error와, 요청했으나 문서에 없는 주제
    (topic_coverage.uncovered)를 답변 LLM에게 보여준다. 미확보 주제는
    행이 없어도 조용히 무시되지 않고 "확인할 수 없음" 사유로 이어져야
    하므로, 검색 결과가 비어 있는 이유를 여기서 명시적으로 전달한다."""
    lines: list[str] = []
    for step_id, result in (step_results or {}).items():
        if result.get("engine") != "vector":
            continue
        detail = result.get("note") or result.get("error") or ""
        line = f"{step_id}: status={result.get('status')}, {detail}"
        uncovered = (result.get("topic_coverage") or {}).get("uncovered") or {}
        if uncovered:
            line += ", 미확보 주제: " + ", ".join(
                f"{'/'.join(labels)}({VECTOR_SECTION_LABELS.get(sec, sec)} 섹션 없음)"
                for sec, labels in uncovered.items()
            )
        lines.append(line)
    return "\n".join(lines) if lines else "(문서 검색 단계 없음)"


def _describe_sql_assumptions(step_results: dict) -> str:
    """각 RDB 단계가 SQL을 쓰면서 실제로 적용한 규칙을 모아 답변 생성
    LLM에게 보여준다. NULL 제외, TRIM 같은 SQL 작성 LLM의 자체 보고뿐
    아니라, rdb_schema.DOMAIN_SALE_POLICY에 따라 조건을 아예 적용하지
    않은 경우(utils.apply_sale_policy가 남긴 로그)도 여기 섞여 들어온다.

    이게 필요한 이유: _describe_applied_conditions는 intent에 적힌
    조건을 그대로 요약할 뿐이라, intent가 "판매가능여부 eq true"를
    담고 있어도 실제 SQL에서는(공지에 따라) 그 조건을 빼고 실행했을 수
    있다. 이 함수가 그 실제 실행 내역을 보여줘서, 답변 LLM이 "조건에
    쓰인 컬럼이 안 보여도 이미 걸러졌다"고 과신하지 않게 정정한다."""
    notes: list[str] = []
    for result in (step_results or {}).values():
        if result.get("engine") != "rdb":
            continue
        for a in result.get("assumptions") or []:
            if a not in notes:
                notes.append(a)
    return "; ".join(notes) if notes else "(추가로 밝혀진 규칙 없음)"


def _build_retrieved_context(state: PipelineState) -> str:
    """§10: route.domains + 고정 스냅샷 날짜 대신, state["step_results"]를
    순회해 각 엔진이 실제로 무엇을 근거로 썼는지 조립한다.

    - RDB 단계: 도메인, 조회 건수, 기준일, 실행된 SQL. merged_into로
      다른 단계에 흡수됐거나(§9 UNION 그룹의 비대표 멤버) skipped/error인
      단계는 실제로 근거를 낸 게 없으므로 뺀다.
    - Graph 단계: 어떤 relation(주체 -- 관계 --> 대상)을 탐색했는지(plan에서
      가져옴), 조회 건수, evidence 요약. "chained"(체인 중간 단계, 실제
      조회는 terminal 단계에서 수행됨)는 뺀다.
    - Vector 단계: 검색 건수와 query를 근거 요약에 남긴다.
    """
    step_results = state.get("step_results") or {}
    plan_by_id = {s["step_id"]: s for s in state.get("plan") or []}
    parts: list[str] = []

    for step_id, result in step_results.items():
        engine = result.get("engine")
        if engine == "rdb":
            if result.get("merged_into") or result.get("skipped_reason") or result.get("error") or not result.get("sql"):
                continue
            parts.append(
                f"[RDB:{result.get('domain', '')}] {result.get('count', 0)}건 조회, "
                f"기준일 {rdb_schema.DATA_SNAPSHOT_DATE}, SQL: {result['sql']}"
            )
        elif engine == "graph":
            if result.get("status") == "chained":
                continue
            relation = (plan_by_id.get(step_id) or {}).get("relation") or {}
            rel_desc = (
                f"{relation.get('subject_domain') or '?'} --{relation.get('relation') or '?'}--> "
                f"{relation.get('object_entity') or relation.get('object_ref') or '?'}"
            )
            evidence = result.get("evidence") or []
            if evidence and evidence[0].get("kind") == "tbox_source":
                ev = evidence[0]
                evidence_note = f", 근거: {ev.get('source_table')}.{ev.get('source_column')}({ev.get('as_of_rule')})"
            elif evidence:
                evidence_note = f", 행 단위 근거 {len(evidence)}건 확보(출처 문서·기준일 포함)"
            else:
                evidence_note = ""
            parts.append(
                f"[Graph] {rel_desc} - status={result.get('status')}, "
                f"{len(result.get('rows') or [])}건{evidence_note}"
            )
        elif engine == "vector":
            if result.get("status") == "chained":
                continue
            # abstain/no_document이면 note 대신 error를 붙인다 - 답변 LLM이
            # "문서 미확보"를 사유로 말할 수 있어야 한다.
            detail = result.get("note") or result.get("error") or ""
            segments = [f"[Vector] status={result.get('status')}, {result.get('count', 0)}건, {detail}"]
            segments.extend(
                f"인용: {c.get('citation_text')}({c.get('effective_as_of')})"
                for c in (result.get("chunks") or [])[:2]
            )
            parts.append(", ".join(segments))

    return " | ".join(parts) if parts else "참조 없음"


def _build_answer_preview(merged_rows: list[dict], total_budget: int = 20) -> list[dict]:
    """merged_rows[:N]으로 그냥 자르면, 여러 도메인/엔진 결과가 섞였을 때
    step_results 순회 순서상 먼저 오는 도메인 하나가 예산을 전부 차지해
    나머지 도메인이 답변 생성 LLM에게 아예 안 보이는 문제가 있었다
    (2026-09-02, "SK하이닉스가 발행한 채권과 SK하이닉스를 편입한 ETF"
    질문 - graph_RG1의 100건이 step_results에서 가장 먼저 와 예산 20을
    다 채우는 바람에, 실제로 존재하는 채권 16건과 ETF RDB 100건이 통째로
    안 보여서 최종 답변에 채권 쪽이 완전히 누락됐다. RDB/Graph 양쪽 다
    정상 조회에 성공했는데도 답변만 틀린, 순수 답변 합성 단계의 버그였다).
    도메인(`_domain` 태그)별로 공평하게 나눠서 어떤 도메인도 완전히
    빠지지 않게 한다."""
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for row in merged_rows:
        key = row.get("_domain") or "기타"
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row)

    if not order:
        return []

    per_domain = max(1, total_budget // len(order))
    preview: list[dict] = []
    for key in order:
        preview.extend(groups[key][:per_domain])

    # 도메인 수가 적어서(예: 2개) per_domain 몫이 남는 도메인이 생기면,
    # 남는 예산을 순서대로 더 채운다 - 정확히 total_budget을 채우기 위함.
    remaining = total_budget - len(preview)
    if remaining > 0:
        for key in order:
            already = min(per_domain, len(groups[key]))
            extra = groups[key][already:already + remaining]
            if not extra:
                continue
            preview.extend(extra)
            remaining -= len(extra)
            if remaining <= 0:
                break

    return [{k: v for k, v in row.items() if not k.startswith("_")} for row in preview]


def _field_evidence(label: str, binding: dict | None, row: dict | None,
                    failure: str | None = None) -> dict:
    """A missing key is not SQL NULL; zero/False are values, not absence."""
    item = {"field": label, "column": (binding or {}).get("column"),
            "status": failure, "value": None}
    if failure:
        return item
    if row is None:
        item["status"] = "no_rows"
    elif binding is None:
        item["status"] = "unmapped"
    elif binding["key"] not in row:
        item["status"] = "not_selected"
    else:
        value = row[binding["key"]]
        item["value"] = value
        if value is None:
            item["status"] = "null"
        elif isinstance(value, str) and not value.strip():
            item["status"] = "empty"
        elif (isinstance(value, float) and not math.isfinite(value)) or (
                hasattr(value, "is_finite") and not value.is_finite()):
            item.update(status="invalid", value=None)
        else:
            item["status"] = "available"
        item["unit"] = binding.get("unit", "")
        item["zero_null_rule"] = binding.get("zero_null_rule", "")
        rule = item["zero_null_rule"] or ""
        if item["status"] == "available" and "사용 금지" in rule:
            item["status"] = "restricted"
        if item["status"] == "available" and not isinstance(value, bool):
            try:
                is_zero = Decimal(str(value).strip().replace(",", "")).is_zero()
            except InvalidOperation:
                is_zero = False
            if is_zero and "0" in rule and ("값 없음" in rule or "is_available=false" in rule):
                item["status"] = "zero_unavailable"
    return item


def _build_rdb_answer_contract(state: PipelineState, row_budget: int = 20) -> list[dict]:
    """Use execution-time projection bindings, never re-resolve fields with an LLM.

    No question IDs/product names are special-cased. Older/legacy SQL without
    projection metadata is reported as unverified, not guessed from similar keys.
    Each record is kept separate (including different markets of one product).
    """
    req = (state.get("intent") or {}).get("output_requirements") or {}
    plans = {p["step_id"]: p for p in state.get("plan") or []}
    targets = [(sid, r) for sid, r in (state.get("step_results") or {}).items()
               if r.get("engine") == "rdb" and r.get("role", "target") == "target"
               and not r.get("merged_into")]
    contract = []
    per_step = max(1, row_budget // max(1, len(targets)))
    for sid, result in targets:
        rows = result.get("rows") or []
        failure = "query_failed" if result.get("error") else (
            "blocked" if result.get("skipped_reason") else None)
        # Do not display stale/partial rows after a failed query as valid values.
        visible = [] if failure else rows[:per_step]
        for index, row in enumerate(visible or [None]):
            domain = (row or {}).get("domain") or result.get("domain", "")
            bindings = result.get("output_fields_by_domain", {}).get(
                domain, result.get("output_fields") or [])
            labels = result.get("requested_fields_by_domain", {}).get(domain,
                result.get("requested_fields", plans.get(sid, {}).get("fields", req.get("fields") or [])))
            labels = list(labels or [])
            if len(targets) == 1:
                # A planner omission must not silently erase an intent request.
                labels.extend(req.get("fields") or [])
            has_date_request = any(catalog_sql.normalize(f) in utils.PROVENANCE_CONCEPTS for f in labels)
            # Identification and source dates are compiler-provided provenance.
            labels.extend(b["attribute"] for b in bindings
                          if b["attribute"] in {"상품명", "상품코드"}
                          or (b["attribute"].startswith("출처기준일(") and not has_date_request))
            if not labels:
                labels = list(req.get("fields") or ["조회 결과"])
            by_label = {}
            for binding in bindings:
                by_label.setdefault(catalog_sql.normalize(binding["attribute"]), []).append(binding)
            items, seen = [], set()
            for label in labels:
                normalized = catalog_sql.normalize(label)
                if normalized in seen:
                    continue
                seen.add(normalized)
                matches = by_label.get(normalized, [])
                if normalized in utils.PROVENANCE_CONCEPTS:
                    dates = list(dict.fromkeys(c for b in bindings for c in b.get("as_of_columns", [])))
                    if dates:
                        for date_column in dates:
                            binding = next((b for b in bindings if b["key"] == date_column), None)
                            items.append(_field_evidence(f"{label}({date_column})", binding, row, failure))
                        continue
                # A request for source column names is provenance, not a DB value.
                if "컬럼" in normalized and any(word in normalized for word in ("근거", "출처")):
                    item = _field_evidence(label, None, row, failure)
                    if bindings and not failure and row is not None:
                        item.update(status="available", value="각 항목의 근거 컬럼을 함께 표시했습니다.")
                    items.append(item)
                    continue
                columns = {b["column"] for b in matches}
                binding = matches[0] if len(columns) == 1 else None
                item = _field_evidence(label, binding, row, failure)
                if binding and row is not None and not failure:
                    item["as_of"] = [_field_evidence(c, next((b for b in bindings if b["key"] == c), None), row)
                                     for c in binding.get("as_of_columns", []) if c != binding["key"]]
                items.append(item)
            contract.append({"step_id": sid, "domain": domain, "row_number": index + 1 if visible else None,
                             "retrieved_rows": len(rows), "displayed_rows": len(visible),
                             "items": items, "notes": list(result.get("assumptions") or [])})
    return contract


_FIELD_UNAVAILABLE_TEXT = {
    "null": "제공된 조회 결과의 값이 NULL이어서 확인할 수 없습니다. 0 또는 해당 사실의 부재를 뜻하지 않습니다.",
    "empty": "제공된 조회 결과가 빈 값이어서 확인할 수 없습니다.",
    "not_selected": "조회 결과에 해당 컬럼이 포함되지 않아 확인할 수 없습니다. NULL 여부도 확인되지 않았습니다.",
    "unmapped": "요청 항목과 조회 컬럼의 대응을 확정하지 못해 확인할 수 없습니다.",
    "no_rows": "조회 결과가 0건이어서 확인할 수 없습니다. 상품 자체가 존재하지 않는다는 뜻은 아닙니다.",
    "query_failed": "조회에 실패하여 확인할 수 없습니다. 값의 존재 여부는 확인되지 않았습니다.",
    "blocked": "조회가 차단되어 확인할 수 없습니다. 값의 존재 여부는 확인되지 않았습니다.",
    "invalid": "조회 값이 유효한 수치가 아니어서 확인할 수 없습니다.",
    "zero_unavailable": "유효한 측정값으로 확인할 수 없습니다. 카탈로그에서 원천 0을 결측·불가용으로 정의합니다.",
    "restricted": "카탈로그에서 판정·필터·정렬에 사용할 수 없는 값으로 정의합니다.",
}


def _display_field_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value).replace("\r", "\\r").replace("\n", "\\n")


def _render_rdb_answer_contract(contract: list[dict]) -> str:
    """Values and absence notices are rendered by code; no LLM can omit them."""
    blocks = []
    for record in contract:
        heading = f"[{record['domain']} / {record['step_id']}]"
        if record["row_number"] is not None:
            heading += (f" 조회 결과 {record['row_number']}번"
                        f" (반환 {record['retrieved_rows']}건 중 {record['displayed_rows']}건 표시)")
        lines = [heading]
        for available, title in [(True, "확인된 값"), (False, "확인 불가 항목")]:
            selected = [i for i in record["items"] if (i["status"] == "available") == available]
            if not selected:
                continue
            lines.extend(["", title])
            for item in selected:
                value = _display_field_value(item["value"]) if available else _FIELD_UNAVAILABLE_TEXT[item["status"]]
                if item["status"] in {"zero_unavailable", "restricted"}:
                    value += f" 원천값: {_display_field_value(item['value'])}; 규칙: {item['zero_null_rule']}"
                source = f" (근거 컬럼: {item['column']})" if item["column"] else ""
                unit = (f" [원천 단위: {item['unit']}]"
                        if available and item.get("unit") not in (None, "", "공식 문서 미표기") else "")
                dates = item.get("as_of") or []
                date_refs = f" [카탈로그 기준일 컬럼: {', '.join(d['field'] for d in dates)}]" if dates else ""
                lines.append(f"- {item['field']}: {value}{unit}{source}{date_refs}")
                if available and item["value"] == 0 and item.get("zero_null_rule"):
                    lines.append(f"  - 원천 값 해석 규칙: {item['zero_null_rule']}")
        # Dates already shown as requested/provenance fields need not be repeated
        # under every numeric item. Missing date bindings still get a clear reason.
        shown_columns = {i["column"] for i in record["items"] if i.get("column")}
        extra_dates = {d["field"]: d for i in record["items"] for d in i.get("as_of", [])
                       if d.get("column") not in shown_columns}
        if extra_dates:
            lines.extend(["", "추가 기준일 상태"])
            for label, date_item in extra_dates.items():
                value = (_display_field_value(date_item["value"]) if date_item["status"] == "available"
                         else _FIELD_UNAVAILABLE_TEXT[date_item["status"]])
                lines.append(f"- 기준일({label}): {value}")
        if any(i.get("unit") == "공식 문서 미표기" for i in record["items"]):
            lines.extend(["", "카탈로그에서 단위를 확인할 수 없는 값은 단위를 추정하지 않고 원문으로 표시했습니다."])
        if record["notes"]:
            lines.extend(["", "SQL 조회 단계 유의사항(최종 출력 여부와 별개)"] + [f"- {n}" for n in dict.fromkeys(record["notes"])])
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _invoke_answer_with_field_fallback(llm, messages: list, has_field_answer: bool) -> dict:
    try:
        response = llm.invoke(messages)
        return response if isinstance(response, dict) else {}
    except Exception:
        if not has_field_answer:
            raise
        # A narrative model outage must not discard already retrieved RDB facts.
        return {"answer": "추가 설명 생성에 실패했습니다. 아래는 확인된 RDB 조회 결과입니다.",
                "think_trace": "RDB 항목별 상태를 출력했으며 추가 설명 생성은 실패했습니다."}


def generate_answer_node(state: PipelineState) -> dict:
    # 1. State에서 필요한 값 추출 (question_id가 들어온다고 가정)
    question_id = state.get("question_id", "Q-UNKNOWN")
    question = state.get("question", "")
    merged_rows = state.get("merged_rows") or []
    route = state.get("route") or {}
    intent = state.get("intent") or {}
    blocking_reasons = route.get("blocking_reasons") or []

    # 2. retrieved_context (답변 근거) - state["step_results"]에서 엔진별
    # 실제 근거(SQL/건수/Graph 관계·evidence)를 조립한다(§10).
    retrieved_context = _build_retrieved_context(state)

    field_contract = _build_rdb_answer_contract(state)
    field_answer = _render_rdb_answer_contract(field_contract)
    narrative_topics = (intent.get("output_requirements") or {}).get("narrative_topics") or []
    # Only direct structured lookup bypasses synthesis. Graph/Vector evidence and
    # narrative questions still use the existing synthesis path plus the contract.
    structured_only = (bool(field_contract) and not narrative_topics
                       and intent.get("task") == "lookup"
                       and not route.get("needs_graph") and not route.get("needs_vector")
                       and not any(r.get("engine") in {"graph", "vector"}
                                   for r in (state.get("step_results") or {}).values()))
    if structured_only:
        response = {"question_id": question_id, "question": question,
                    "retrieved_context": retrieved_context,
                    "think_trace": "RDB 실행 결과와 요청 항목의 컬럼 대응을 대조하여 값과 확인 불가 사유를 구분해 표시했습니다.",
                    "answer": field_answer}
        return {"answer": json.dumps(response, ensure_ascii=False),
                "trace": ["답변 생성: 요청 항목별 결정론적 출력 (추가 LLM 호출 없음)"]}

    # 3. 예외 처리: 데이터가 없는 경우
    if not merged_rows:
        # 서술형 질문은 blocking_reasons가 비어 있어도 "문서 미확보" 때문에
        # 답을 못 하는 경우가 있다. 그 사유를 그대로 답변에 남긴다.
        reasons = list(blocking_reasons)
        for result in (state.get("step_results") or {}).values():
            if result.get("engine") == "vector" and result.get("status") not in (None, "ok"):
                detail = result.get("note") or result.get("error") or ""
                reasons.append(f"문서 근거 {result['status']}: {detail}".strip())
        reason = f" ({'; '.join(reasons)})" if reasons else ""
        answer_text = f"제공된 데이터로는 이 질문에 답변할 수 없습니다.{reason}"
        if field_answer:
            answer_text += "\n\n" + field_answer
        
        final_response = {
            "question_id": question_id,
            "question": question,
            "retrieved_context": retrieved_context,
            "think_trace": "데이터 검색 불가 및 쿼리 플랜 실패로 인한 답변 불가 처리",
            "answer": answer_text
        }
        # FastAPI 등에서 쉽게 리턴하도록 JSON string이나 dict 자체를 반환 구조에 맞춤
        return {"answer": json.dumps(final_response, ensure_ascii=False), "trace": ["답변 생성: 데이터 없음 -> 답변불가 처리"]}
 
    # 4. LLM용 데이터 준비
    preview = _build_answer_preview(merged_rows)
    rows_text = json.dumps(preview, ensure_ascii=False, default=str, indent=2)
    applied_conditions = _describe_applied_conditions(intent)
    requested_items = _describe_requested_items(intent)
    vector_status = _describe_vector_status(state.get("step_results") or {})
    sql_assumptions = _describe_sql_assumptions(state.get("step_results") or {})
    # §10: think_trace를 LLM이 매번 새로 지어내지 않고, 파이프라인이 각
    # 노드에서 실제로 쌓아 온 실행 기록(질의 분석 -> plan 수립 -> 엔진별
    # 조회 -> 결과 합치기)을 근거로 요약하게 한다.
    execution_log = "\n".join(state.get("trace") or []) or "(기록 없음)"

    # 5. 구조화된 출력(Structured Output)으로 LLM 호출
    structured_llm = _llm_answer.with_structured_output(FINAL_ANSWER_JSON_SCHEMA, method="json_schema")

    response = _invoke_answer_with_field_fallback(structured_llm,
        [
            ("system", ANSWER_SYSTEM_PROMPT),
            (
                "human",
                f"[질문]\n{question}\n\n"
                f"[질문이 요구한 항목] (answer는 이 항목만 다룬다)\n{requested_items}\n\n"
                f"[요청 항목별 RDB 상태] (값/NULL/미조회/실패를 구별한다. 아래 구조화 항목은 코드가 별도로 출력하므로 answer에는 문서·관계 설명만 작성한다.)\n"
                f"{json.dumps(field_contract, ensure_ascii=False, default=str)}\n\n"
                f"[문서 근거 상태] (미확보 주제는 '확인할 수 없음'으로 답할 것)\n{vector_status}\n\n"
                f"[계획의 조건] (실제 적용 여부는 SQL 실행 기록과 조정된 규칙을 따른다. "
                f"SELECT에 필터 컬럼이 없다는 이유만으로 실행된 필터를 무효로 판단하지 않는다.)\n"
                f"{applied_conditions}\n\n"
                f"[SQL 실행 시 실제로 적용되거나 조정된 규칙]\n{sql_assumptions}\n\n"
                f"[실제 실행 기록] (think_trace는 이 로그를 근거로 요약할 것 - 지어내지 말 것)\n{execution_log}\n\n"
                f"[검색된 데이터] (전체 {len(merged_rows)}건 중 {len(preview)}건 표시)\n{rows_text}",
            ),
        ], bool(field_answer)
    )
    
    # 6. 대회 요구사항(5개 필드)에 맞춰 최종 응답 객체 생성
    answer_text = response.get("answer") or ""
    if not isinstance(answer_text, str):
        answer_text = json.dumps(answer_text, ensure_ascii=False, default=str)
    if field_answer:
        answer_text = "\n\n".join(part for part in [answer_text.strip(), field_answer] if part)
    if not answer_text.strip():
        answer_text = "검색 결과는 있으나 최종 설명을 생성하지 못했습니다. 요청 항목의 근거를 확인해야 합니다."
    final_response = {
        "question_id": question_id,
        "question": question,
        "retrieved_context": retrieved_context,
        "think_trace": response.get("think_trace", "추론 과정 생성 누락"),
        "answer": answer_text
    }
    
    # 최종적으로 문자열로 직렬화하여 반환 (FastAPI 라우터단에서 바로 리턴 가능하도록)
    return {
        "answer": json.dumps(final_response, ensure_ascii=False), 
        "trace": [f"답변 생성 완료 ({len(merged_rows)}건 기반)"]
    }
