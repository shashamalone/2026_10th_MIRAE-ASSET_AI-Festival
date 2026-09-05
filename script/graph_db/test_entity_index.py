"""graph_entity 3단계 인덱스(_entity_index) 계약 테스트.

목적: 정규형·세그먼트 인덱스가 원래 SPARQL 스캔(_normalized_literal_candidates_sparql)과
같은 후보·모호성 판정을 내는지 고정한다. 흐름: graph_engine.sparql 을 소형 가짜 스토어로
바꿔 클래스 폐쇄·세그먼트·고유 entity 계약·폴백·type-suffix 경로를 검사한다.
실 스토어 회귀(RUN_STORE_REGRESSION=1)는 두 구현을 같은 입력으로 직접 대조한다.
실행: repo 루트에서 `python script/graph_db/test_entity_index.py`.
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from agent.graph_logic import graph_entity as ge  # noqa: E402

FP = ge.FP
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
SKOS = "http://www.w3.org/2004/02/skos/core#"
I = "http://mafest.ai/instance/"

# 가짜 스토어: (entity, predicate IRI) → 값 목록. rdf:type 은 TYPES 에.
TYPES = {
    I + "etf-069500": FP + "ETF",
    I + "etf-lev": FP + "LeveragedETF",   # ETF 의 하위 클래스 → 폐쇄로 포함돼야 한다
    I + "theme-space": FP + "Theme",
    I + "theme-defense": FP + "Theme",
    I + "sec-005930": FP + "Security",
}
SUBCLASS = {"ETF": {FP + "ETF", FP + "LeveragedETF"}}
VALUES = {
    (I + "etf-069500", FP + "productShortName"): ["KODEX 200"],
    (I + "etf-069500", RDFS + "label"): ["KODEX 200"],
    (I + "etf-069500", SKOS + "altLabel"): ["코덱스200"],
    (I + "etf-069500", FP + "productCode"): ["069500"],
    (I + "etf-lev", FP + "productShortName"): ["KODEX 레버리지"],
    (I + "etf-lev", FP + "productCode"): ["122630"],
    (I + "theme-space", FP + "themeName"): ["우주항공/방산"],
    (I + "theme-space", RDFS + "label"): ["우주항공/방산"],
    (I + "theme-defense", FP + "themeName"): ["방산"],
    (I + "sec-005930", RDFS + "label"): ["삼성전자"],
    (I + "sec-005930", FP + "securityCode"): ["005930"],
}
CALLS: list[str] = []


def _vals(entity: str, *preds: str) -> list[str]:
    return sorted({v for p in preds for v in VALUES.get((entity, p), [])})


def _emulate_filter_query(query: str) -> list[dict]:
    """VALUES 로 제한된 3단계 SPARQL 을 흉내 낸다: OPTIONAL 곱 행에 FILTER(OR)를
    행 단위로 적용하고 DISTINCT 한다. 실제 Oxigraph 와 같은 규칙이다."""
    cls = re.search(r"subClassOf\* fp:(\w+)", query).group(1)
    lit = re.search(r'LCASE\("([^"]*)"\)', query).group(1).lower()
    uris = re.findall(r"<([^>]+)>", query.split("VALUES ?entity {", 1)[1].split("}", 1)[0])
    spec = {"ETF": ((FP + "productName", FP + "productShortName"), (FP + "productCode",)),
            "Theme": ((FP + "themeName", RDFS + "label"), (FP + "themeName",)),
            "Security": ((RDFS + "label",), (FP + "securityCode",))}
    name_p, code_p = spec[cls]
    out, seen = [], set()
    for ent in uris:
        for n in _vals(ent, *name_p) or [None]:
            for l in _vals(ent, RDFS + "label") or [None]:
                for a in _vals(ent, SKOS + "altLabel") or [None]:
                    for c in _vals(ent, *code_p) or [None]:
                        cols = [v for v in (n, l, a, c) if v is not None]
                        if any(lit in ge._segment_keys(ge._sparql_norm(v)) for v in cols):
                            row = (ent, n, l, a, c)
                            if row not in seen:
                                seen.add(row)
                                out.append({"entity": ent, "name": n, "label": l, "alt": a, "code": c})
    return out


def fake_sparql(query: str, *, max_rows=10_000):
    """graph_entity 가 만드는 질의 종류를 문자열 패턴으로 구분해 응답한다."""
    CALLS.append(query)
    m = re.search(r"subClassOf\* fp:(\w+)", query)
    if m and "?entity" not in query:
        cls = m.group(1)
        return [{"c": c} for c in SUBCLASS.get(cls, {FP + cls})]
    if "?entity rdf:type ?type }" in query:
        return [{"entity": e, "type": t} for e, t in TYPES.items()]
    m = re.search(r"\?entity <([^>]+)> \?v", query)
    if m:
        iri = m.group(1)
        return [{"entity": e, "v": v} for (e, p), vs in VALUES.items() if p == iri for v in vs]
    if "UNION" in query:          # 1단계 exact - 이 테스트에서는 항상 실패시킨다
        return []
    if "FILTER(" in query and "VALUES ?entity" in query:   # 인덱스로 좁힌 3단계 질의
        return _emulate_filter_query(query)
    if "FILTER(" in query:        # 클래스 전체 스캔 - 폴백 테스트용 고정 응답
        return [{"entity": I + "from-sparql", "name": "SPARQL", "label": None, "alt": None, "code": None}]
    raise AssertionError(f"예상 밖 질의: {query[:120]}")


class EntityIndexTest(unittest.TestCase):
    def setUp(self):
        CALLS.clear()
        ge.clear_entity_cache()
        self._p = patch.object(ge.graph_engine, "sparql", side_effect=fake_sparql)
        self._p.start()
        # 가짜 스토어 인덱스가 artifacts/ 의 실제 캐시를 읽거나 덮어쓰면 안 된다
        self._c = patch.object(ge, "_store_signature", return_value=None)
        self._c.start()

    def tearDown(self):
        self._p.stop()
        self._c.stop()
        ge.clear_entity_cache()

    def test_segment_keys_cover_all_contiguous_runs(self):
        self.assertEqual(ge._segment_keys("a/b/c"), {"a", "b", "c", "a/b", "b/c", "a/b/c"})
        self.assertEqual(ge._segment_keys("kodex200"), {"kodex200"})
        self.assertNotIn("", ge._segment_keys("a//b"))

    def test_sparql_norm_matches_filter_semantics(self):
        self.assertEqual(ge._sparql_norm("KODEX 200"), "kodex200")
        self.assertEqual(ge._sparql_norm("Kodex-200_ETF x"), "kodex200etfx")

    def test_normalized_exact_hit(self):
        out = ge._normalized_literal_candidates("kodex 200", "ETF")
        self.assertEqual([c["uri"] for c in out], [I + "etf-069500"])
        self.assertEqual(out[0]["codes"], ("069500",))
        # 이름·label·alt 가 모두 같은 키를 내도 entity 하나 → 후보 하나
        self.assertIn("KODEX 200", out[0]["names"])

    def test_code_is_a_key(self):
        out = ge._normalized_literal_candidates("069500", "ETF")
        self.assertEqual(len(out), 1)

    def test_segment_match_partial_theme(self):
        out = ge._normalized_literal_candidates("우주항공", "Theme")
        self.assertEqual([c["uri"] for c in out], [I + "theme-space"])

    def test_multi_segment_literal(self):
        out = ge._normalized_literal_candidates("우주항공/방산", "Theme")
        self.assertEqual([c["uri"] for c in out], [I + "theme-space"])

    def test_ambiguity_counts_unique_entities(self):
        # "방산" 은 theme-space 의 세그먼트이자 theme-defense 의 전체 이름 → entity 2개
        out = ge._normalized_literal_candidates("방산", "Theme")
        self.assertEqual(len(out), 2)
        res = ge.resolve_entity("방산", "Theme")
        self.assertEqual(res["status"], "ambiguous")

    def test_subclass_closure_included(self):
        out = ge._normalized_literal_candidates("kodex레버리지", "ETF")
        self.assertEqual([c["uri"] for c in out], [I + "etf-lev"])

    def test_class_scoping(self):
        self.assertEqual(ge._normalized_literal_candidates("삼성전자", "ETF"), [])
        self.assertEqual(len(ge._normalized_literal_candidates("삼성전자", "Security")), 1)

    def test_no_match(self):
        self.assertEqual(ge._normalized_literal_candidates("없는이름", "ETF"), [])

    def test_type_suffix_retry_resolves_via_index(self):
        res = ge.resolve_entity("KODEX 200 ETF", "ETF")
        self.assertEqual(res["status"], "resolved")
        self.assertEqual(res["uri"], I + "etf-069500")
        self.assertTrue(res["match_mode"].endswith("_type_stripped"))

    def test_index_built_once_and_no_full_scan(self):
        ge._normalized_literal_candidates("kodex 200", "ETF")
        ge._normalized_literal_candidates("삼성전자", "Security")
        ge._normalized_literal_candidates("방산", "Theme")
        self.assertEqual(sum("?entity rdf:type ?type" in q for q in CALLS), 1)
        # 전체 스캔(VALUES 없는 FILTER 질의)은 한 번도 없어야 한다
        self.assertEqual(sum("FILTER(" in q and "VALUES ?entity" not in q for q in CALLS), 0)

    def test_no_hit_skips_sparql_entirely(self):
        before = len(CALLS)
        ge._normalized_literal_candidates("kodex 200", "ETF")   # 인덱스 구축 포함
        built = len(CALLS)
        self.assertEqual(ge._normalized_literal_candidates("없는이름", "ETF"), [])
        self.assertEqual(len(CALLS), built, "인덱스 미스는 SPARQL 을 부르지 않는다")
        self.assertGreater(built, before)

    def test_filter_applies_per_row(self):
        # 실 스토어의 KODEX 200 과 같은 배치: productShortName 만 키에 걸리고
        # productName·label 은 안 걸린다. 원래 SPARQL 처럼 걸린 행만 살아남아
        # 안 걸린 productName 은 names 에 들어오지 않고 canonical_name 도 걸린 행의 것이다.
        saved_label = VALUES[(I + "etf-069500", RDFS + "label")]
        VALUES[(I + "etf-069500", FP + "productName")] = ["DROPPED-NAME"]
        VALUES[(I + "etf-069500", RDFS + "label")] = ["삼성 KODEX200 증권상장지수투자신탁[주식]"]
        try:
            ge.clear_entity_cache()
            out = ge._normalized_literal_candidates("kodex 200", "ETF")
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0]["canonical_name"], "KODEX 200")
            self.assertNotIn("DROPPED-NAME", out[0]["names"])
            self.assertIn("삼성 KODEX200 증권상장지수투자신탁[주식]", out[0]["names"])  # 살아남은 행의 label
        finally:
            VALUES.pop((I + "etf-069500", FP + "productName"))
            VALUES[(I + "etf-069500", RDFS + "label")] = saved_label

    def test_fallback_to_sparql_when_index_fails(self):
        with patch.object(ge, "_entity_index", side_effect=RuntimeError("store down")):
            with self.assertLogs(ge.logger, level="WARNING"):
                out = ge._normalized_literal_candidates("kodex 200", "ETF")
            self.assertEqual([c["uri"] for c in out], [I + "from-sparql"])
            self.assertIsNotNone(ge._INDEX_FAILURE)
            # 실패 뒤에는 다시 구축을 시도하지 않고 바로 폴백한다
            out2 = ge._normalized_literal_candidates("삼성전자", "Security")
            self.assertEqual([c["uri"] for c in out2], [I + "from-sparql"])
        ge.clear_entity_cache()
        self.assertIsNone(ge._INDEX_FAILURE)

    def test_clear_cache_rebuilds(self):
        ge._normalized_literal_candidates("kodex 200", "ETF")
        ge.clear_entity_cache()
        ge._normalized_literal_candidates("kodex 200", "ETF")
        self.assertEqual(sum("?entity rdf:type ?type" in q for q in CALLS), 2)


# 실측 fixture: 2026-09-03 골든셋 seed 텍스트 + 클래스 대표. 인덱스와 원래 SPARQL
# 스캔이 같은 후보를 내는지 실 스토어에서 대조한다. 스캔 한 번에 3~6s 라 기본은 건너뛴다.
REGRESSION_FIXTURE = [
    ("우리반도체BIG2플러스", "PublicFund"), ("우리반도체BIG2플러스", "ETF"),   # Q10
    ("우주항공", "Theme"), ("우주항공/방산", "Theme"),                       # Q23
    ("SK하이닉스", "Security"), ("에스케이하이닉스", "Bond"),               # Q26
    ("LG에너지솔루션", "Security"), ("엘지에너지솔루션", "Bond"),            # Q27
    ("KODEX 200", "ETF"), ("삼성전자", "Security"), ("VOO", "ETF"),
    ("캠브리콘", "Security"), ("에코프로", "Security"),
]


@unittest.skipUnless(os.getenv("RUN_STORE_REGRESSION") == "1", "RUN_STORE_REGRESSION=1 일 때만 실 스토어 대조")
class RealStoreRegressionTest(unittest.TestCase):
    def test_index_equals_sparql_scan(self):
        from dotenv import load_dotenv
        load_dotenv()
        ge.clear_entity_cache()
        for text, cls in REGRESSION_FIXTURE:
            with self.subTest(text=text, cls=cls):
                expected = ge._normalized_literal_candidates_sparql(text, cls)
                actual = ge._normalized_literal_candidates(text, cls)
                self.assertEqual([c["uri"] for c in actual], [c["uri"] for c in expected])
                self.assertEqual(actual, expected)   # names·codes·canonical_name 까지 전부
        self.assertIsNone(ge._INDEX_FAILURE, "인덱스 구축이 실패해 폴백으로 통과한 것은 회귀 확인이 아니다")


if __name__ == "__main__":
    unittest.main(verbosity=1)
