"""도메인별 실질 기준일(rdb_schema.get_domain_as_of) 단위 테스트(DB·LLM 호출 없음).

python script/agent_test/test_domain_as_of.py

4개 도메인·UNION 합성("채권+국내ETF")·미지 도메인 폴백과,
_build_retrieved_context의 RDB 근거가 배포일 대신 도메인 기준일을 쓰는지 확인한다.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

# nodes는 import 시점에 ChatClovaX를 만들기 때문에 API 키가 필요하다.
load_dotenv(REPO_ROOT / ".env")

from agent import nodes  # noqa: E402
from tools import rdb_schema  # noqa: E402


class GetDomainAsOfTest(unittest.TestCase):
    def test_single_domains(self):
        self.assertEqual(rdb_schema.get_domain_as_of("채권"), "2026-08-21")
        self.assertEqual(rdb_schema.get_domain_as_of("국내ETF"), "2026-08-22")
        self.assertEqual(rdb_schema.get_domain_as_of("해외ETF"), "2026-08-22")
        self.assertEqual(rdb_schema.get_domain_as_of("펀드"), "2026-08-21")

    def test_union_group(self):
        self.assertEqual(
            rdb_schema.get_domain_as_of("채권+국내ETF"),
            "채권 2026-08-21·국내ETF 2026-08-22",
        )

    def test_unknown_domain_falls_back_to_snapshot(self):
        self.assertEqual(rdb_schema.get_domain_as_of("주식"), rdb_schema.DATA_SNAPSHOT_DATE)
        self.assertEqual(rdb_schema.get_domain_as_of(""), rdb_schema.DATA_SNAPSHOT_DATE)


class BuildRetrievedContextTest(unittest.TestCase):
    def test_rdb_step_uses_domain_as_of(self):
        state = {
            "plan": [],
            "step_results": {
                "s1": {"engine": "rdb", "domain": "채권", "count": 3, "sql": "SELECT 1"},
                "s2": {"engine": "rdb", "domain": "국내ETF+해외ETF", "count": 1, "sql": "SELECT 2"},
            },
        }
        text = nodes._build_retrieved_context(state)
        self.assertIn("[RDB:채권] 3건 조회, 기준일 2026-08-21, SQL: SELECT 1", text)
        self.assertIn("기준일 국내ETF 2026-08-22·해외ETF 2026-08-22, SQL: SELECT 2", text)
        self.assertNotIn("기준일 2026-08-24", text)


if __name__ == "__main__":
    unittest.main()
