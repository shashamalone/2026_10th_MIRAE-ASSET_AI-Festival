"""
평가용 API(GET /answer) 규격 회귀 테스트.

주최측 규격(과제설명 p11)에서 채점에 직접 영향을 주는 계약만 검증한다.

  1. 응답은 항상 200 + 5필드(question_id, question, retrieved_context,
     think_trace, answer)이고 값은 전부 문자열이다.
  2. 확인 불가 질의도 200 + 동일 스키마다.
  3. 미정의 파라미터가 들어와도 500 이 나지 않는다.
  4. 파이프라인이 예외를 던지거나 계약을 어겨도 500 이 나지 않는다.
  5. 제한 시간을 넘겨도 500 이 아니라 스키마를 지킨 응답을 준다.

실행:
    PYTHONPATH=src python -m unittest discover -s test/answer-api -v
"""
from __future__ import annotations

import json
import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import serve_answer  # noqa: E402

REQUIRED_FIELDS = ("question_id", "question", "retrieved_context", "think_trace", "answer")


def assert_envelope(case: unittest.TestCase, payload: dict) -> None:
    case.assertEqual(set(payload), set(REQUIRED_FIELDS), "5필드 정확히 일치해야 한다")
    for key in REQUIRED_FIELDS:
        case.assertIsInstance(payload[key], str, f"{key} 는 문자열이어야 한다")


class FakeApp:
    """agent.graph.app 대역. invoke 의 반환/예외를 시험별로 바꾼다."""

    def __init__(self, result=None, exc: Exception | None = None, delay: float = 0.0):
        self.result = result
        self.exc = exc
        self.delay = delay
        self.calls: list[dict] = []

    def invoke(self, state: dict) -> dict:
        self.calls.append(state)
        if self.delay:
            time.sleep(self.delay)
        if self.exc:
            raise self.exc
        return self.result or {}


class EnvelopeUnitTest(unittest.TestCase):
    def test_envelope_forces_strings(self):
        payload = serve_answer._envelope(None, None, answer=None)
        assert_envelope(self, payload)
        self.assertEqual(payload["answer"], "")

    def test_parses_pipeline_json_contract(self):
        state = {
            "answer": json.dumps(
                {
                    "question_id": "Q-1",
                    "question": "질문",
                    "retrieved_context": "PREF02N001 · 2026-08-24",
                    "think_trace": "조건 파싱 → 필터",
                    "answer": "총보수 0.03%",
                },
                ensure_ascii=False,
            )
        }
        payload = serve_answer._parse_pipeline_answer(state, "Q-1", "질문")
        assert_envelope(self, payload)
        self.assertEqual(payload["retrieved_context"], "PREF02N001 · 2026-08-24")
        self.assertEqual(payload["answer"], "총보수 0.03%")

    def test_plain_string_answer_still_yields_envelope(self):
        """generate_answer_node 가 JSON 계약을 어기고 평문을 넣어도 스키마는 지킨다."""
        state = {"answer": "그냥 평문 답변", "trace": ["단계1", "단계2"]}
        payload = serve_answer._parse_pipeline_answer(state, "Q-2", "질문")
        assert_envelope(self, payload)
        self.assertEqual(payload["answer"], "그냥 평문 답변")
        self.assertIn("단계1", payload["think_trace"])

    def test_missing_answer_key_yields_abstain(self):
        payload = serve_answer._parse_pipeline_answer({"trace": ["x"]}, "Q-3", "질문")
        assert_envelope(self, payload)
        self.assertIn("답변할 수 없습니다", payload["answer"])


class AnswerFunctionTest(unittest.TestCase):
    def setUp(self):
        self._saved_app = serve_answer._APP
        self._saved_err = serve_answer._IMPORT_ERROR

    def tearDown(self):
        serve_answer._APP = self._saved_app
        serve_answer._IMPORT_ERROR = self._saved_err

    def test_blank_question_is_answered_not_crashed(self):
        payload = serve_answer.answer("Q-1", "   ")
        assert_envelope(self, payload)
        self.assertIn("비어 있어", payload["answer"])

    def test_degraded_mode_returns_envelope(self):
        serve_answer._APP = None
        serve_answer._IMPORT_ERROR = "ModuleNotFoundError: x"
        payload = serve_answer.answer("Q-1", "질문")
        assert_envelope(self, payload)
        self.assertIn("ModuleNotFoundError", payload["think_trace"])

    def test_pipeline_exception_is_contained(self):
        serve_answer._APP = FakeApp(exc=RuntimeError("DB 폭발"))
        payload = serve_answer.answer("Q-1", "질문")
        assert_envelope(self, payload)
        self.assertIn("RuntimeError", payload["think_trace"])
        self.assertIn("답변할 수 없습니다", payload["answer"])

    def test_question_id_is_passed_into_pipeline(self):
        fake = FakeApp(result={"answer": json.dumps({"answer": "ok"}, ensure_ascii=False)})
        serve_answer._APP = fake
        serve_answer.answer("Q-042", "질문")
        self.assertEqual(fake.calls[0]["question_id"], "Q-042")
        self.assertEqual(fake.calls[0]["question"], "질문")


class HttpContractTest(unittest.TestCase):
    """실제 소켓으로 띄워 HTTP 계약을 검증한다."""

    @classmethod
    def setUpClass(cls):
        cls._saved_app = serve_answer._APP
        cls._saved_timeout = serve_answer.TIMEOUT_SECONDS
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), serve_answer.AnswerHandler)
        cls.server.daemon_threads = True
        cls.server.pool = ThreadPoolExecutor(max_workers=2)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        serve_answer._APP = cls._saved_app
        serve_answer.TIMEOUT_SECONDS = cls._saved_timeout

    def _get(self, path: str):
        url = f"http://127.0.0.1:{self.port}{path}"
        try:
            with urlopen(url, timeout=30) as resp:  # noqa: S310 - 로컬 테스트 서버
                return resp.status, resp.headers.get("Content-Type"), json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:  # 404 도 본문을 검사해야 한다
            return exc.code, exc.headers.get("Content-Type"), json.loads(exc.read().decode("utf-8"))

    def test_normal_query_returns_json_envelope(self):
        serve_answer._APP = FakeApp(
            result={"answer": json.dumps({"answer": "답", "retrieved_context": "PREF01N001"}, ensure_ascii=False)}
        )
        status, ctype, payload = self._get("/answer?question_id=Q-1&question=%ED%85%8C%EC%8A%A4%ED%8A%B8")
        self.assertEqual(status, 200)
        self.assertEqual(ctype, "application/json; charset=utf-8")
        assert_envelope(self, payload)
        self.assertEqual(payload["question"], "테스트", "URL 인코딩된 한글이 복원되어야 한다")

    def test_undefined_parameters_do_not_break(self):
        serve_answer._APP = FakeApp(result={"answer": json.dumps({"answer": "답"}, ensure_ascii=False)})
        status, _, payload = self._get("/answer?question_id=Q-2&question=x&foo=bar&limit=99")
        self.assertEqual(status, 200)
        assert_envelope(self, payload)

    def test_pipeline_exception_returns_200(self):
        serve_answer._APP = FakeApp(exc=ValueError("boom"))
        status, _, payload = self._get("/answer?question_id=Q-3&question=x")
        self.assertEqual(status, 200, "파이프라인이 터져도 500 이 나면 안 된다")
        assert_envelope(self, payload)

    def test_timeout_returns_200_envelope(self):
        serve_answer.TIMEOUT_SECONDS = 0.3
        serve_answer._APP = FakeApp(result={"answer": "늦은 답"}, delay=3.0)
        try:
            status, _, payload = self._get("/answer?question_id=Q-4&question=x")
        finally:
            serve_answer.TIMEOUT_SECONDS = self._saved_timeout
        self.assertEqual(status, 200, "제한 시간 초과도 500 이 아니어야 한다")
        assert_envelope(self, payload)
        self.assertIn("제한 시간", payload["think_trace"])

    def test_unknown_path_keeps_schema(self):
        status, ctype, payload = self._get("/wrong?question_id=Q-5&question=x")
        self.assertEqual(status, 404)
        self.assertEqual(ctype, "application/json; charset=utf-8")
        assert_envelope(self, payload)

    def test_health_reports_pipeline_state(self):
        serve_answer._APP = FakeApp(result={})
        status, _, payload = self._get("/health")
        self.assertEqual(status, 200)
        self.assertTrue(payload["pipeline_loaded"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
