"""
ETF 편입내역 출처 조회 회귀 테스트.

골드셋 22번("편입내역 문서명과 근거 문장")이 요구하는 근거를 실제로 붙일 수
있는지 검증한다. 그래프 결과 행에서 출처를 찾는 경로와, 인덱스가 없거나
깨졌을 때도 답변을 막지 않는지를 함께 본다.

실행:
    python test/holdings-provenance/test_holdings_provenance.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from tools import holdings_provenance as hp  # noqa: E402

CUTOFF = "2026-08-24"


class IndexIntegrityTest(unittest.TestCase):
    """커밋된 인덱스 자체의 계약."""

    @classmethod
    def setUpClass(cls):
        hp.clear_cache()
        path = _ROOT / "metadata" / "etf_holdings_provenance.json"
        cls.payload = json.loads(path.read_text(encoding="utf-8"))
        cls.entries = cls.payload["entries"]

    def test_count_matches_entries(self):
        self.assertEqual(self.payload["count"], len(self.entries))
        self.assertGreater(len(self.entries), 500, "수록량이 급감했으면 수집이 깨진 것이다")

    def test_every_entry_is_within_cutoff(self):
        """기준일 이후 외부값은 데이터 규칙상 쓸 수 없다."""
        late = {k: v["as_of"] for k, v in self.entries.items() if v.get("as_of", "") > CUTOFF}
        self.assertEqual(late, {}, f"cutoff({CUTOFF}) 초과 항목: {late}")

    def test_every_entry_has_citable_fields(self):
        """문서명과 URL 이 없으면 인용할 수 없다."""
        broken = [k for k, v in self.entries.items() if not v.get("document") or not v.get("url")]
        self.assertEqual(broken, [], f"문서명/URL 누락: {broken[:5]}")

    def test_ticker_is_the_index_key(self):
        mismatched = [k for k, v in self.entries.items() if v.get("ticker") != k]
        self.assertEqual(mismatched, [], f"키와 ticker 불일치: {mismatched[:5]}")


class LookupTest(unittest.TestCase):
    def setUp(self):
        hp.clear_cache()

    def test_lookup_by_ticker(self):
        entry = hp.lookup(ticker="396520")  # TIGER 차이나반도체FACTSET
        self.assertIsNotNone(entry)
        self.assertIn("TIGER", entry["name"])

    def test_lookup_by_isin(self):
        entry = hp.lookup(isin="KR7396520009")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["ticker"], "396520")

    def test_lookup_by_full_product_name(self):
        """그래프의 정식 명칭은 사이드카 통칭보다 길다. 포함 관계로 붙어야 한다."""
        entry = hp.lookup(name="미래에셋 TIGER 차이나반도체FACTSET증권상장지수투자신탁(주식-파생형)")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["ticker"], "396520")

    def test_unknown_identifiers_return_none(self):
        self.assertIsNone(hp.lookup(ticker="999999"))
        self.assertIsNone(hp.lookup(isin="XX0000000000"))
        self.assertIsNone(hp.lookup(name="존재하지 않는 상품명 zzz"))

    def test_lookup_with_no_arguments_is_none(self):
        self.assertIsNone(hp.lookup())


class RowMatchingTest(unittest.TestCase):
    def setUp(self):
        hp.clear_cache()

    def test_finds_by_product_name_column(self):
        row = {"etfName": "삼성 KODEX 차이나AI반도체TOP10증권상장지수투자신탁[주식]", "weight": "10.45"}
        entry = hp.find_for_row(row)
        self.assertIsNotNone(entry)
        self.assertIn("KODEX", entry["document"])

    def test_column_name_is_not_assumed(self):
        """컬럼명이 달라도 값만 맞으면 찾아야 한다."""
        row = {"제멋대로컬럼": "396520"}
        self.assertIsNotNone(hp.find_for_row(row))

    def test_row_without_identifier_returns_none(self):
        self.assertIsNone(hp.find_for_row({"weight": "1.5", "asOf": "2026-07-10"}))

    def test_short_values_do_not_false_match(self):
        self.assertIsNone(hp.find_for_row({"code": "AI", "n": "1"}))

    def test_find_for_rows_dedupes_and_limits(self):
        rows = [{"etfName": "미래에셋 TIGER 차이나반도체FACTSET증권상장지수투자신탁(주식-파생형)"}] * 4
        found = hp.find_for_rows(rows, limit=3)
        self.assertEqual(len(found), 1, "같은 문서는 한 번만 담아야 한다")

    def test_find_for_rows_respects_limit(self):
        rows = [
            {"etfName": "미래에셋 TIGER 차이나반도체FACTSET증권상장지수투자신탁(주식-파생형)"},
            {"etfName": "삼성 KODEX 차이나AI반도체TOP10증권상장지수투자신탁[주식]"},
            {"etfName": "KB RISE 차이나AI반도체TOP4Plus증권상장지수투자신탁(주식)"},
        ]
        self.assertEqual(len(hp.find_for_rows(rows, limit=2)), 2)

    def test_non_dict_rows_are_ignored(self):
        self.assertEqual(hp.find_for_rows(["문자열", None, 3]), [])


class CitationTest(unittest.TestCase):
    def setUp(self):
        hp.clear_cache()

    def test_citation_carries_document_and_date(self):
        entry = hp.lookup(ticker="396520")
        line = hp.citation(entry)
        self.assertIn(entry["document"], line)
        self.assertIn(entry["as_of"], line)
        self.assertIn(entry["url"], line)

    def test_citation_survives_sparse_entry(self):
        line = hp.citation({"ticker": "000000"})
        self.assertIn("000000", line)
        self.assertIn("기준일 미상", line)

    def test_describe_rows_returns_strings(self):
        rows = [{"etfName": "삼성 KODEX 차이나CSI300증권상장지수투자신탁[주식-파생형]"}]
        lines = hp.describe_rows(rows)
        self.assertTrue(lines and all(isinstance(x, str) for x in lines))


class DegradedIndexTest(unittest.TestCase):
    """인덱스를 못 읽어도 답변을 막지 않아야 한다."""

    def tearDown(self):
        hp._INDEX_PATH = self._saved
        hp.clear_cache()

    def setUp(self):
        self._saved = hp._INDEX_PATH
        hp.clear_cache()

    def test_missing_index_is_silent(self):
        hp._INDEX_PATH = Path(tempfile.gettempdir()) / "does-not-exist-provenance.json"
        hp.clear_cache()
        self.assertIsNone(hp.lookup(ticker="396520"))
        self.assertEqual(hp.describe_rows([{"etfName": "무엇이든"}]), [])

    def test_corrupt_index_is_silent(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            fh.write("{ this is not json")
            broken = Path(fh.name)
        hp._INDEX_PATH = broken
        hp.clear_cache()
        try:
            self.assertIsNone(hp.lookup(ticker="396520"))
            self.assertEqual(hp.find_for_rows([{"a": "396520"}]), [])
        finally:
            broken.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
