"""
평가용 API 서버 — GET /answer

주최측 규격(과제설명 p11):
  GET /answer?question_id=<id>&question=<URL 인코딩된 질의>
  Content-Type: application/json; charset=utf-8
  응답 5필드 필수: question_id, question, retrieved_context, think_trace, answer
  - 확인 불가 질의도 200 OK + 동일 스키마
  - 인증 헤더·POST 바디 사용 안 함
  - 미정의 파라미터가 들어와도 500 없이 처리
  - 문항당 60초 이내 권장

[왜 stdlib 인가]
FastAPI/uvicorn 을 쓰지 않고 http.server 로 짰다. requirements.txt 는 평가
재현을 위해 고정되어 있고, 평가 기간(09.07~09.20)에 서버에서 추가 설치를
하지 않아도 되게 하려는 것이다. 의존성이 늘면 배포 시점에 실패할 여지가
생기는데, 이 엔드포인트는 2주간 무인으로 떠 있어야 한다.

[설계 원칙 — 절대 500 을 내지 않는다]
채점자가 받는 것은 항상 200 + 5필드 JSON 이다. 파이프라인이 터지든,
타임아웃이든, 파라미터가 이상하든 마찬가지다. 오류를 502/500 으로 흘리면
그 문항은 무조건 0점이지만, 스키마를 지킨 "확인할 수 없음"은 답변 불가
문항에서는 오히려 정답 처리된다(과제설명 p7).

[타임아웃]
운영측 300초 제한 전에 응답하도록 기본 290초에서 끊는다
(ANSWER_TIMEOUT_SECONDS 로 조정). 시간이 넘으면 그때까지
쌓인 trace 를 근거로 5필드를 채워 200 으로 돌려준다. 초과한 작업 스레드는
결과를 버리고 계속 두는데, 이미 응답한 요청을 되돌릴 수는 없기 때문이다.

실행:
    PYTHONPATH=src python -m serve_answer            # 0.0.0.0:8080
    PYTHONPATH=src python -m serve_answer --port 80
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

LOG = logging.getLogger("serve_answer")

DEFAULT_PORT = int(os.getenv("ANSWER_PORT", "8080"))
DEFAULT_HOST = os.getenv("ANSWER_HOST", "0.0.0.0")
TIMEOUT_SECONDS = float(os.getenv("ANSWER_TIMEOUT_SECONDS", "290"))
MAX_WORKERS = int(os.getenv("ANSWER_MAX_WORKERS", "4"))

# 파이프라인 import 는 기동 시 1회만 시도한다. 실패해도 서버는 뜬다 —
# 채점자에게 connection refused 를 주는 것보다, 스키마를 지킨 답변 불가를
# 주는 편이 낫다. 실패 사유는 기동 로그에 남고 _IMPORT_ERROR 로 보관한다.
_APP: Any = None
_IMPORT_ERROR: str | None = None


def _load_pipeline() -> None:
    global _APP, _IMPORT_ERROR
    try:
        from agent.graph import app  # noqa: PLC0415

        _APP = app
        LOG.info("파이프라인 로드 완료")
    except Exception as exc:  # noqa: BLE001 - 어떤 실패든 서버는 떠야 한다
        _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
        LOG.exception("파이프라인 로드 실패 — 답변 불가 모드로 기동한다")


def _envelope(
    question_id: str,
    question: str,
    *,
    answer: str,
    retrieved_context: str = "",
    think_trace: str = "",
) -> dict[str, str]:
    """규격 5필드를 항상 문자열로 채운다. None 이 새어 나가면 채점기가
    파싱에 실패할 수 있으므로 여기서 전부 str 로 고정한다."""
    return {
        "question_id": str(question_id or ""),
        "question": str(question or ""),
        "retrieved_context": str(retrieved_context or ""),
        "think_trace": str(think_trace or ""),
        "answer": str(answer or ""),
    }


def _parse_pipeline_answer(state: dict, question_id: str, question: str) -> dict[str, str]:
    """generate_answer_node 는 5필드 dict 를 JSON 문자열로 직렬화해
    state["answer"] 에 넣는다. 그 계약이 깨진 경우(평문 문자열 등)에도
    응답 스키마는 지켜야 하므로 감싸서 되돌린다."""
    raw = state.get("answer")

    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            parsed = None
        if isinstance(parsed, dict):
            return _envelope(
                parsed.get("question_id") or question_id,
                parsed.get("question") or question,
                answer=parsed.get("answer", ""),
                retrieved_context=parsed.get("retrieved_context", ""),
                think_trace=parsed.get("think_trace", ""),
            )
        # JSON 이 아니면 평문 답변으로 취급하고 trace 로 근거를 채운다.
        return _envelope(
            question_id,
            question,
            answer=raw,
            think_trace="\n".join(state.get("trace") or []),
        )

    return _envelope(
        question_id,
        question,
        answer="제공된 데이터로는 이 질문에 답변할 수 없습니다.",
        think_trace="\n".join(state.get("trace") or []),
    )


def answer(question_id: str, question: str) -> dict[str, str]:
    """질의 하나를 처리한다. 예외를 밖으로 던지지 않는다."""
    if not question.strip():
        return _envelope(
            question_id,
            question,
            answer="질의가 비어 있어 답변할 수 없습니다. question 파라미터에 질문을 담아 주세요.",
            think_trace="입력 검증: question 파라미터 없음 또는 공백",
        )

    if _APP is None:
        return _envelope(
            question_id,
            question,
            answer="제공된 데이터로는 이 질문에 답변할 수 없습니다. (일시적으로 조회 파이프라인을 사용할 수 없습니다)",
            think_trace=f"파이프라인 미기동: {_IMPORT_ERROR or '원인 미상'}",
        )

    started = time.monotonic()
    try:
        state = _APP.invoke({"question": question, "question_id": question_id})
    except Exception as exc:  # noqa: BLE001 - 어떤 실패도 200 으로 돌려준다
        LOG.exception("파이프라인 실행 실패 qid=%s", question_id)
        return _envelope(
            question_id,
            question,
            answer="제공된 데이터로는 이 질문에 답변할 수 없습니다. (조회 중 오류가 발생했습니다)",
            think_trace=f"실행 오류: {type(exc).__name__}: {exc}",
        )

    elapsed = time.monotonic() - started
    LOG.info("처리 완료 qid=%s %.2fs", question_id, elapsed)
    return _parse_pipeline_answer(state, question_id, question)


class AnswerHandler(BaseHTTPRequestHandler):
    server_version = "MiraeAssetFinancialAgent/1.0"
    protocol_version = "HTTP/1.1"

    # BaseHTTPRequestHandler 의 기본 로그는 stderr 로 직접 쓴다. logging 으로
    # 통일해 배포 시 한 곳만 보면 되게 한다.
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - 기반 클래스 시그니처
        LOG.info("%s - %s", self.client_address[0], format % args)

    def _send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # 채점자가 타임아웃으로 먼저 끊은 경우. 서버는 계속 살아야 한다.
            LOG.warning("클라이언트가 응답 수신 전에 연결을 끊음")

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 규약
        try:
            parsed = urlparse(self.path)
            # parse_qs 는 URL 디코딩까지 해준다. 미정의 파라미터는 그냥 무시한다
            # (규격: 미정의 파라미터가 들어와도 500 없이 처리되어야 한다).
            params = parse_qs(parsed.query, keep_blank_values=True)
            question_id = (params.get("question_id") or [""])[0]
            question = (params.get("question") or [""])[0]

            if parsed.path.rstrip("/") in ("/answer", ""):
                fut = self.server.pool.submit(answer, question_id, question)  # type: ignore[attr-defined]
                try:
                    payload = fut.result(timeout=TIMEOUT_SECONDS)
                except FutureTimeout:
                    LOG.warning("타임아웃 %.0fs qid=%s", TIMEOUT_SECONDS, question_id)
                    payload = _envelope(
                        question_id,
                        question,
                        answer="제공된 데이터로는 제한 시간 안에 답변을 완성하지 못했습니다.",
                        think_trace=f"제한 시간 {TIMEOUT_SECONDS:.0f}초 초과로 중단",
                    )
                self._send_json(payload)
                return

            if parsed.path.rstrip("/") == "/health":
                self._send_json(
                    {
                        "status": "ok" if _APP is not None else "degraded",
                        "pipeline_loaded": _APP is not None,
                        "pipeline_error": _IMPORT_ERROR,
                        "timeout_seconds": TIMEOUT_SECONDS,
                    }
                )
                return

            # 알 수 없는 경로도 5필드 스키마로 돌려준다. 채점자가 경로를
            # 잘못 불렀을 때 404 본문을 파싱하다 실패하는 것보다 낫다.
            self._send_json(
                _envelope(
                    question_id,
                    question,
                    answer="알 수 없는 경로입니다. GET /answer 를 사용해 주세요.",
                    think_trace=f"요청 경로: {parsed.path}",
                ),
                status=HTTPStatus.NOT_FOUND,
            )
        except Exception as exc:  # noqa: BLE001 - 핸들러에서 예외가 새면 500 이 된다
            LOG.exception("핸들러 오류")
            self._send_json(
                _envelope("", "", answer="요청을 처리할 수 없습니다.", think_trace=f"{type(exc).__name__}: {exc}")
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="평가용 API 서버 (GET /answer)")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )

    _load_pipeline()

    server = ThreadingHTTPServer((args.host, args.port), AnswerHandler)
    server.daemon_threads = True
    server.pool = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="answer")  # type: ignore[attr-defined]

    LOG.info(
        "listening on http://%s:%d/answer (timeout=%.0fs, workers=%d, pipeline=%s)",
        args.host,
        args.port,
        TIMEOUT_SECONDS,
        MAX_WORKERS,
        "loaded" if _APP is not None else "DEGRADED",
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOG.info("종료 요청 수신")
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
