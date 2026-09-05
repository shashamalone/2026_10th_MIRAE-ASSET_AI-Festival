"""Turn saved traces into a question/answer/process review, without model calls."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    run = args.run.resolve()
    if (ROOT / "artifacts/runs").resolve() not in run.parents or "codex-t139-sql-0905" not in run.parts:
        parser.error("agent-scoped run path required")
    cases = {c["id"]: c for c in json.loads(args.audit.read_text(encoding="utf-8"))["cases"]}
    review_file = run / "review-decisions.json"
    reviews = json.loads(review_file.read_text(encoding="utf-8")) if review_file.exists() else {}
    ids = ["Q5"] + [f"Q{i}" for i in range(7, 36)]
    lines = ["# Q5·Q7–Q35 수정 및 문항별 검토", "",
             "실제 질문·이전 답변·단회 답변·조회 과정과 남은 제약을 함께 기록합니다. "
             "파이프라인 정상 종료는 정답 판정이 아닙니다. NULL을 명시적으로 확인 불가로 답한 것은 정상 처리입니다.", "",
             "같은 문항의 유료 실행은 1회입니다. 이후 수정은 저장 기록 재생과 오프라인 회귀로 검증하며 "
             "실제 단회 답변을 수정된 답변으로 덮어쓰지 않습니다. 서버 배포·DB 변경은 하지 않았습니다.", "",
             "## 검토 상태", "", "| 문항 | 단회 실행 | 검토 판정 |", "| --- | --- | --- |"]
    traces = {}
    for qid in ids:
        path = run / "live" / qid / "traces.jsonl"
        if path.exists():
            raw = [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s.strip()]
            if len(raw) != 1:
                raise ValueError(f"{qid}: expected exactly one trace, got {len(raw)}")
            traces[qid] = raw[0]
        status = traces.get(qid, {}).get("status", "미실행")
        lines.append(f"| {qid} | {status} | {reviews.get(qid, {}).get('status', '검토 대기')} |")
    lines += ["", "점수 주의: 미실행/예외 문항을 성공으로 분모에서 제외하지 않습니다. "
              "이번 단회 진단을 과거 3회 전부 통과 점수나 주최측 공식 채점 점수와 직접 비교하지 않습니다."]
    for qid in ids:
        old = cases.get(qid, {})
        trace = traces.get(qid)
        review = reviews.get(qid, {})
        lines += ["", f"## {qid}", "", "### 실제 질문", "", old.get("question", "질문 미확보"),
                  "", "### 원인과 수정", "", review.get("change", "수정·검증 내용을 검토 중입니다."),
                  "", "### 남은 사항", "", review.get("remaining", "문항별 검토 대기"),
                  "", "### 이전 실행 답변", "", str(old.get("answer") or "(빈 답변)"),
                  "", "### 이번 실제 단회 답변", ""]
        if not trace:
            lines.append("아직 실제 실행하지 않았습니다. 이전 답변이나 오프라인 재생을 새 실행으로 표시하지 않습니다.")
            continue
        answer = trace.get("answer") or {}
        lines.append(answer.get("answer") or "(최종 answer 없음)")
        manifest = json.loads((run / "live" / qid / "manifest.json").read_text(encoding="utf-8"))
        lines += ["", "### 실행 및 조회 과정", "",
                  f"- 코드: `{manifest['commit']}`; dirty={manifest['dirty']} (파일별 SHA256은 manifest 참조)",
                  f"- 정상 종료 상태: {trace.get('status')}; 질의 처리: {trace.get('e2e_ms', 0) / 1000:.3f}초",
                  f"- LLM 호출/오류/429: {trace.get('rate_limit', {}).get('llm_calls', 0)} / "
                  f"{trace.get('rate_limit', {}).get('llm_errors', 0)} / {trace.get('rate_limit', {}).get('status_429_count', 0)}",
                  "", "검수된 의도 분석:", "", "```json",
                  json.dumps(trace.get("verified_intent") or trace.get("intent"), ensure_ascii=False, indent=2), "```"]
        for sid, result in (trace.get("step_results") or {}).items():
            lines += ["", f"#### {sid} ({result.get('engine')})", "",
                      f"상태={result.get('status', 'error' if result.get('error') else 'blocked' if result.get('skipped_reason') else 'ok')}; "
                      f"반환={result.get('rows_total', result.get('count', 0))}; "
                      f"사유={result.get('error') or result.get('skipped_reason') or result.get('note') or '없음'}"]
            for field, language in (("sql", "sql"), ("sparql", "sparql")):
                if result.get(field):
                    lines += ["", "```" + language, result[field], "```"]
            for hydration in result.get("hydration_queries") or []:
                lines += ["", f"상세 조회 ({hydration['domain']}):", "", "```sql", str(hydration.get("sql")), "```"]
            if result.get("chunks"):
                sources = [{k: c.get(k) for k in ("chunk_id", "document_id", "document_title", "citation_text", "source_url", "published_at", "effective_as_of", "page_number")}
                           for c in result["chunks"]]
                lines += ["", "확보된 문서 출처:", "", "```json", json.dumps(sources, ensure_ascii=False, indent=2), "```"]
        lines += ["", "실제 실행 로그:", "", "```text", "\n".join(trace.get("trace_messages") or []), "```"]
        if trace.get("exception"):
            lines += ["", "예외:", "", "```text", str(trace["exception"]), "```"]
    path = run / "문항별_수정검토_Q5_Q7-Q35.md"
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(json.dumps({"report": str(path), "executed": len(traces), "requested": len(ids),
                      "blank_answers": [q for q, t in traces.items() if not (t.get("answer") or {}).get("answer")]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
