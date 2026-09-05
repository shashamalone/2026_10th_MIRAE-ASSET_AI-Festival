"""sql_builder 결정론 컴파일 계약 테스트.

목적: 2026-09-03 측정에서 RDB 오답 52회차를 만든 네 패턴(플래그 리터럴, 폐기 컬럼, 단위 오환산,
상품명 부분일치)이 빌더에서 재발하지 않음을 고정한다. LLM·DB 없이 resolved_schema dict만으로 돈다.
실행: repo 루트에서 `python script/agent_test/test_sql_builder.py`.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from agent import sql_builder as sb  # noqa: E402
from tools import rdb_schema  # noqa: E402
from tools.rdb_schema import AttributeSpec  # noqa: E402

CAT = rdb_schema.ATTRIBUTE_CATALOG


def cond(attribute, operator, value, spec, column=None, value_2="", **extra):
    return {"attribute": attribute, "operator": operator, "value": value, "value_2": value_2,
            "column": column or (spec.column if spec else None), "spec": spec, "valid": True,
            "invalid_reason": None, "matched_values": None, "org_name_variants": None, **extra}


def schema(domain, conditions=(), sort=None, fields=("상품명",), joins=()):
    cat = CAT[domain]
    return {"domain": domain, "table": rdb_schema.DOMAIN_TABLE_INFO[domain]["table"],
            "conditions": list(conditions), "sort": sort,
            "fields": [{"attribute": f, "column": cat[f].column, "spec": cat[f]} for f in fields if f in cat],
            "unresolved_concepts": [], "invalid_conditions": [], "notes": [], "joins": list(joins)}


class KoreanNumberTest(unittest.TestCase):
    def test_units(self):
        cases = {"1천억 달러": 1e11, "1000억 원": 1e11, "1,000억": 1e11, "5천억 원": 5e11, "1조": 1e12,
                 "1조 5천억": 1.5e12, "0.05%": 0.05, "0.10%": 0.10, "3년": 3, "100": 100, "2억5천만": 2.5e8}
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertAlmostEqual(sb.parse_korean_number(text), want)
        self.assertIsNone(sb.parse_korean_number("양수"))
        self.assertIsNone(sb.parse_korean_number(""))


class ConditionTest(unittest.TestCase):
    q = staticmethod(lambda c: c)

    def test_flag_literal_becomes_code_value(self):
        # Q12: LLM은 pd_sale_yn = '판매 중'을 썼다(0행). 카탈로그 true_condition으로 컴파일해야 한다.
        spec = CAT["국내ETF"]["판매가능여부"]
        frag, _ = sb.compile_condition(cond("판매상태", "eq", "판매 중", spec), self.q)
        self.assertEqual(frag, "pd_sale_yn = '1'")
        frag, _ = sb.compile_condition(cond("판매상태", "eq", "판매 불가", spec), self.q)
        self.assertEqual(frag, "NOT (pd_sale_yn = '1')")

    def test_fund_sale_flag_text_value(self):
        # Q19: sale_yn = '판매 중'(공백) → 실값 '판매중'
        spec = CAT["펀드"]["판매가능여부"]
        frag, _ = sb.compile_condition(cond("판매상태", "eq", "판매 중", spec), self.q)
        self.assertEqual(frag, "sale_yn = '판매중'")

    def test_yn_categorical_as_flag(self):
        spec = CAT["국내ETF"]["연금거래가능여부"]
        frag, _ = sb.compile_condition(cond("연금거래 가능 여부", "eq", "가능", spec), self.q)
        self.assertEqual(frag, "pd_pen_tr_yn = 'Y'")
        frag, _ = sb.compile_condition(cond("연금거래 가능 여부", "eq", "N", spec), self.q)
        self.assertEqual(frag, "pd_pen_tr_yn = 'N'")

    def test_negation_wins_over_truthy_token(self):
        spec = AttributeSpec(column="pd_tr_yn", value_type="numeric_flag", true_condition="= '1'")
        frag, _ = sb.compile_condition(cond("거래정지 여부", "eq", "거래정지 아님", spec), self.q)
        self.assertEqual(frag, "NOT (pd_tr_yn = '1')")

    def test_numeric_units_usd(self):
        # Q17: LLM은 1천억 달러를 1e17로 썼다. 컬럼이 USD라 1e11이어야 한다.
        spec = CAT["해외ETF"]["순자산"]
        frag, _ = sb.compile_condition(cond("AUM", "gte", "1천억 달러", spec), self.q)
        self.assertEqual(frag, "du_last_aum >= 1e+11")

    def test_numeric_units_krw_and_percent(self):
        frag, _ = sb.compile_condition(cond("순자산", "gte", "1000억 원", CAT["펀드"]["순자산"]), self.q)
        self.assertEqual(frag, "fd_nast_suma >= 1e+11")
        frag, _ = sb.compile_condition(cond("총보수", "lte", "0.05%", CAT["해외ETF"]["총보수율"]), self.q)
        self.assertEqual(frag, "cu_charge_rt <= 0.05")

    def test_currency_mismatch_is_not_compiled(self):
        # 원화 컬럼에 달러 값: 환산이 필요하므로 빌더가 손대지 않고 LLM 경로로 넘긴다
        frag, _ = sb.compile_condition(cond("순자산", "gte", "1천억 달러", CAT["펀드"]["순자산"]), self.q)
        self.assertIsNone(frag)

    def test_duration_to_days(self):
        # Q13: 잔존기간 3년 → remaining_days <= 1095
        frag, _ = sb.compile_condition(cond("잔존기간", "lte", "3년", CAT["채권"]["잔존기간"]), self.q)
        self.assertEqual(frag, "remaining_days <= 1095")

    def test_forbidden_column_dropped_with_note(self):
        # Q11: 매수가능수량 조건은 buyable_quantity(무효 공지)로 매핑된다 → 조건 제외 + 사유
        spec = AttributeSpec(column="buyable_quantity", value_type="numeric")
        frag, note = sb.compile_condition(cond("매수가능수량", "gte", "0", spec), self.q)
        self.assertEqual(frag, "")
        self.assertIn("무효", note)

    def test_unknown_value_type_not_compiled(self):
        spec = AttributeSpec(column="pd_sale_yn", value_type="unknown", note="LLM 폴백")
        frag, _ = sb.compile_condition(cond("판매상태", "eq", "판매 중", spec), self.q)
        self.assertIsNone(frag)

    def test_ordinal_matched_values(self):
        c = cond("신용등급", "gte", "AA-", CAT["채권"]["신용등급"], matched_values=["AA-", "AA0", "AA+", "AAA"])
        frag, _ = sb.compile_condition(c, self.q)
        self.assertEqual(frag, "crd_grd IN ('AA-', 'AA0', 'AA+', 'AAA')")

    def test_org_name_variants(self):
        c = cond("발행사", "eq", "SK하이닉스", CAT["채권"]["발행사"], org_name_variants=["SK하이닉스", "에스케이하이닉스"])
        frag, _ = sb.compile_condition(c, self.q)
        self.assertEqual(frag, "(TRIM(pd_pbcm) LIKE '%SK하이닉스%' OR TRIM(pd_pbcm) LIKE '%에스케이하이닉스%')")

    def test_in_operator_for_product_codes(self):
        frag, _ = sb.compile_condition(cond("상품코드", "in", "KR7069500007, KR7069500015", CAT["국내ETF"]["상품코드"]), self.q)
        self.assertEqual(frag, "pd_itm_no IN ('KR7069500007', 'KR7069500015')")

    def test_categorical_known_value_normalized(self):
        frag, _ = sb.compile_condition(cond("투자지역", "eq", "미국 ", CAT["국내ETF"]["투자지역"]), self.q)
        self.assertEqual(frag, "wu_inv_rgn = '미국'")
        frag, _ = sb.compile_condition(cond("투자지역", "eq", "화성", CAT["국내ETF"]["투자지역"]), self.q)
        self.assertIsNone(frag)

    def test_text_contains_and_eq(self):
        frag, _ = sb.compile_condition(cond("상품명", "contains", "반도체", CAT["국내ETF"]["상품명"]), self.q)
        self.assertEqual(frag, "pd_nm LIKE '%반도체%'")
        frag, _ = sb.compile_condition(cond("발행사", "eq", "에스케이하이닉스(주)", CAT["채권"]["발행기관"]), self.q)
        self.assertEqual(frag, "TRIM(pd_pbcm) = '에스케이하이닉스(주)'")

    def test_date_parsing(self):
        # 컬럼이 numeric이라고 알려진 경우: CAST 없이 숫자 비교
        spec = CAT["채권"]["만기일"]; num = {"mat_dt": "numeric"}
        self.assertEqual(sb.compile_condition(cond("만기일", "lte", "2027-12-31", spec), self.q, num)[0], "mat_dt <= 20271231")
        self.assertEqual(sb.compile_condition(cond("만기일", "eq", "2027년", spec), self.q, num)[0], "mat_dt BETWEEN 20270101 AND 20271231")
        self.assertEqual(sb.compile_condition(cond("만기일", "gte", "20260824", spec), self.q, num)[0], "mat_dt >= 20260824")

    def test_subtype_condition_without_spec(self):
        # utils.resolve_subtype_conditions 가 만드는 레코드: column·operator·value 확정, spec None
        rec = {"attribute": "상품유형(회사채)", "operator": "eq", "value": "회사채", "value_2": "",
               "column": "std_pd_mcls_nm", "spec": None, "valid": True, "invalid_reason": None, "matched_values": None}
        self.assertEqual(sb.compile_condition(rec, self.q)[0], "std_pd_mcls_nm = '회사채'")
        rec = {**rec, "column": "cu_lev_fector", "operator": ">", "value": "1"}
        self.assertEqual(sb.compile_condition(rec, self.q)[0], "cu_lev_fector > 1")
        rec = {**rec, "column": "pd_nm", "operator": "contains", "value": "(녹)"}
        self.assertEqual(sb.compile_condition(rec, self.q)[0], "pd_nm LIKE '%(녹)%'")

    def test_subtype_map_asset_class(self):
        self.assertEqual(rdb_schema.resolve_subtype_condition("해외ETF", "채권 ETF")["value"], "Bond")
        self.assertEqual(rdb_schema.resolve_subtype_condition("해외ETF", "주식형")["value"], "Equity")
        self.assertEqual(rdb_schema.resolve_subtype_condition("국내ETF", "채권형")["value"], "채권")
        self.assertEqual(rdb_schema.resolve_subtype_condition("채권", "원화채권")["column"], "curr_cd")

    def test_text_typed_numeric_columns_are_cast(self):
        # 원격에서 mat_dt·cu_lev_fector 등은 text다(2026-09-05 실측). 숫자 비교는 CAST해야 한다.
        types = {"mat_dt": "text", "cu_lev_fector": "text", "remaining_days": "double precision"}
        frag, _ = sb.compile_condition(cond("만기일", "lte", "2027-12-31", CAT["채권"]["만기일"]), self.q, types)
        self.assertEqual(frag, "CAST(mat_dt AS NUMERIC) <= 20271231")
        rec = {"attribute": "상품유형(레버리지)", "operator": ">", "value": "1", "value_2": "", "column": "cu_lev_fector",
               "spec": None, "valid": True, "invalid_reason": None, "matched_values": None}
        self.assertEqual(sb.compile_condition(rec, self.q, types)[0], "CAST(cu_lev_fector AS NUMERIC) > 1")
        # 진짜 numeric 컬럼은 캐스팅하지 않는다
        frag, _ = sb.compile_condition(cond("잔존기간", "lte", "3년", CAT["채권"]["잔존기간"]), self.q, types)
        self.assertEqual(frag, "remaining_days <= 1095")
        # 타입을 모르면 날짜류만 CAST(양쪽 타입에 안전), 일반 numeric은 그대로
        frag, _ = sb.compile_condition(cond("만기일", "gte", "20260824", CAT["채권"]["만기일"]), self.q, None)
        self.assertEqual(frag, "CAST(mat_dt AS NUMERIC) >= 20260824")

    def test_sort_on_text_numeric_column_is_cast(self):
        s = schema("국내ETF", sort={"attribute": "상장일", "column": "pd_lstg_dt", "order": "desc", "limit": "5", "spec": CAT["국내ETF"]["상장일"]})
        sql = sb.compile_sql(s, column_types={"pd_lstg_dt": "text"})["sql"]
        self.assertIn("ORDER BY CAST(pd_lstg_dt AS NUMERIC) DESC NULLS LAST", sql)

    def test_quote_escape(self):
        frag, _ = sb.compile_condition(cond("상품명", "contains", "O'Neil", CAT["해외ETF"]["상품명"]), self.q)
        self.assertEqual(frag, "pd_nm LIKE '%O''Neil%'")


class CompileSqlTest(unittest.TestCase):
    def test_domestic_etf_adds_etn_filter_and_sort(self):
        s = schema("국내ETF", [cond("순자산", "gte", "5천억 원", CAT["국내ETF"]["순자산"])],
                   sort={"attribute": "순자산", "column": "pd_net_tamt", "order": "desc", "limit": "10", "spec": CAT["국내ETF"]["순자산"]},
                   fields=("상품명", "순자산"))
        out = sb.compile_sql(s)
        self.assertEqual(out["source"], "deterministic")
        sql = out["sql"]
        self.assertIn("SELECT pd_nm, pd_net_tamt", sql)
        self.assertIn("pd_net_tamt >= 5e+11", sql)
        self.assertIn("pd_grp_no = 'ETF'", sql)
        self.assertIn("pd_net_tamt IS NOT NULL", sql)
        self.assertTrue(sql.rstrip().endswith("ORDER BY pd_net_tamt DESC NULLS LAST\nLIMIT 10"))

    def test_no_limit_when_merge_rank(self):
        s = schema("펀드", sort={"attribute": "순자산", "column": "fd_nast_suma", "order": "desc", "limit": "5", "spec": CAT["펀드"]["순자산"]})
        self.assertNotIn("LIMIT", sb.compile_sql(s, apply_limit=False)["sql"])

    def test_ordinal_sort_uses_case(self):
        spec = CAT["채권"]["신용등급"]
        s = schema("채권", sort={"attribute": "신용등급", "column": "crd_grd", "order": "asc", "limit": "", "spec": spec})
        sql = sb.compile_sql(s)["sql"].replace("\n", " ")
        self.assertIn(f"ORDER BY CASE WHEN crd_grd = '{spec.value_order[0]}' THEN 0", sql)
        self.assertIn(f"ELSE {len(spec.value_order)} END ASC NULLS LAST", sql)

    def test_uncompilable_condition_returns_none(self):
        spec = AttributeSpec(column="x", value_type="unknown")
        s = schema("채권", [cond("이상한개념", "eq", "값", spec)])
        self.assertIsNone(sb.compile_sql(s))

    def test_forbidden_everywhere(self):
        bq = AttributeSpec(column="buyable_quantity", value_type="numeric")
        s = schema("채권", [cond("매수가능수량", "gte", "0", bq)],
                   sort={"attribute": "매수가능수량", "column": "buyable_quantity", "order": "desc", "limit": "", "spec": bq},
                   fields=("상품명", "발행사"))
        s["fields"].append({"attribute": "매수가능수량", "column": "buyable_quantity", "spec": bq})
        out = sb.compile_sql(s)
        self.assertNotIn("buyable_quantity", out["sql"])
        self.assertTrue(any("무효" in a for a in out["assumptions"]))
        self.assertNotIn("ORDER BY", out["sql"])

    def test_joins_qualify_base_columns(self):
        spec = CAT["국내ETF"]["총보수율"]
        s = schema("국내ETF", [cond("총보수", "lte", "0.1%", spec)], fields=("상품명", "총보수율"),
                   joins=[f"LEFT JOIN {spec.join_table} AS {spec.join_alias} ON {spec.join_on}"])
        sql = sb.compile_sql(s)["sql"]
        self.assertIn("FROM raw.pref01n001 AS base", sql)
        self.assertIn("SELECT base.pd_nm, ee.charge_rt_final", sql)
        self.assertIn("ee.charge_rt_final <= 0.1", sql)
        self.assertIn("base.pd_grp_no = 'ETF'", sql)

    def test_union_mode(self):
        s = schema("펀드", [cond("공모사모구분", "eq", "공모", CAT["펀드"]["공모사모구분"])],
                   sort={"attribute": "순자산", "column": "fd_nast_suma", "order": "desc", "limit": "5", "spec": CAT["펀드"]["순자산"]},
                   fields=("상품코드", "상품명"))
        sql = sb.compile_sql(s, apply_limit=False, union_mode=True)["sql"]
        self.assertTrue(sql.startswith("SELECT itm_no AS code, itm_nm AS name, '펀드' AS domain, fd_nast_suma AS sort_value"))
        self.assertNotIn("ORDER BY", sql)
        self.assertIn("prvo_pbff_desc = '공모'", sql)

    def test_no_fields_returns_none(self):
        s = schema("채권", fields=())
        self.assertIsNone(sb.compile_sql(s))


if __name__ == "__main__":
    unittest.main(verbosity=1)
