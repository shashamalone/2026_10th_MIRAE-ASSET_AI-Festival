# -*- coding: utf-8 -*-
"""Gold 3종과 B/C Semantic Schema Context를 결정적으로 생성한다."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

from rdflib import Graph, OWL, RDF, RDFS, Namespace, URIRef

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
GOLD = HERE / "gold"
CONTEXTS = HERE / "contexts"
FP = Namespace("http://mafest.ai/product#")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")
TBOX = [ROOT / f"ontology/{x}.ttl" for x in
        ("common", "bond_kr", "etf_kr", "etf_gl", "fund_pub")]
ABOX = sorted((ROOT / "ontology").glob("instances_*.ttl"))
DATA_CUTOFF = "2026-08-24"
CSV_INPUTS = sorted((ROOT / "data/csv").glob("*_master_20260824.csv")) + \
             sorted(p for p in (ROOT / "data/enriched").glob("*.csv")
                    if p.name != "fund_pub_dedup.csv") + \
             sorted((ROOT / "data/relations").glob("*.csv"))


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def jdump(data, path: Path) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


SQL = {
1: """SELECT b.pd_no,b.pd_nm,b.pd_pbcm,b.crd_grd,b.srfc_irt,b.mat_dt,b.buy_yield,b.info_base_dt FROM raw.bond_kr_master b WHERE b.pd_nm='에스케이하이닉스224-2'""",
2: """SELECT b.pd_no,b.pd_nm,b.isu_dt,b.mat_dt,e.remaining_days,b.srfc_irt,b.after_tax_yield,b.info_base_dt FROM raw.bond_kr_master b JOIN enriched.bond_kr_enriched e USING(pd_no,pd_exg_mkt,info_seq) WHERE b.pd_nm='국고채권 02000-3106(21-5)'""",
3: """SELECT b.pd_no,b.pd_nm,b.bd_knd,b.pd_pbcm,b.crd_grd,e.crd_grd_norm,e.maturity_bucket,b.dur FROM raw.bond_kr_master b JOIN enriched.bond_kr_enriched e USING(pd_no,pd_exg_mkt,info_seq) WHERE b.pd_nm='현대해상화재보험7(후)(콜/후)'""",
4: """SELECT k.pd_itm_no,k.pd_nm,k.cu_fund_mgmt_co,k.cu_base_index,k.du_last_aum,k.du_last_nav,k.du_clpr,CASE WHEN k.du_last_nav<>0 THEN (k.du_clpr-k.du_last_nav)/k.du_last_nav*100 END AS diff_rate_recalculated,k.du_er_1y,k.du_upt_dt FROM raw.etf_kr_master k WHERE k.pd_abrv_nm='KODEX 200' AND k.pd_grp_no='ETF'""",
5: """SELECT k.pd_itm_no,k.pd_nm,k.wu_inv_ast_type,k.wu_inv_rgn,k.cu_strtegy,e.replication,e.charge_rt_final,e.charge_rt_source,k.du_er_1m,k.du_er_3m,k.du_er_6m,k.du_upt_dt FROM raw.etf_kr_master k JOIN enriched.etf_kr_enriched e USING(pd_itm_no) WHERE k.pd_abrv_nm='TIGER 미국S&P500' AND k.pd_grp_no='ETF'""",
6: """SELECT g.pd_itm_no,g.pd_nm,g.pd_isin_cd,g.cu_base_index,g.cu_fund_mgmt_co,g.cu_charge_rt,g.du_last_aum,g.ru_mkt_price,g.du_vol_1d,g.du_clpr_base_dt,g.du_nav_base_dt FROM raw.etf_gl_master g WHERE g.pd_itm_no='VOO' AND g.pd_grp_no='ETF'""",
7: """SELECT g.pd_itm_no,g.pd_nm,g.wu_inv_ast_type,g.wu_inv_rgn,g.cu_base_index,g.cu_index_repl_mthd,g.cu_strtegy,g.cu_charge_rt FROM raw.etf_gl_master g WHERE g.pd_abrv_nm='BND' AND g.pd_grp_no='ETF'""",
8: """SELECT f.itm_no,f.itm_nm,f.or_attr_desc,f.fd_nast_suma,f.fd_mm1_ern_r,f.fd_mm3_ern_r,f.fd_mm6_ern_r,f.fd_yr1_ern_r,f.zrin_fd_ivst_risk_grd_nm,f.sale_yn FROM raw.fund_pub_master f WHERE f.itm_nm='미래에셋코어테크증권자투자신탁(주식) 종류A'""",
9: """SELECT f.itm_no,f.itm_nm,f.bmrk_nm,f.curr_cd,f.fd_ivst_rgn_desc,f.pers_corp_desc,f.zrin_fd_ivst_risk_grd_nm,f.fd_nast_suma FROM raw.fund_pub_master f WHERE f.itm_nm='삼성 베스트 MMF 법인 제1호'""",
10: """SELECT f.itm_no,f.itm_nm,f.mtco_itm_no,f.rptt_ksd_itm_no,f.sale_yn,f.fd_nast_suma,f.fd_yr1_ern_r FROM raw.fund_pub_master f WHERE f.itm_nm IN ('우리반도체BIG2플러스증권투자신탁(채권혼합)ClassC-P','우리반도체BIG2플러스증권투자신탁(채권혼합)ClassC-Pe') ORDER BY f.itm_no""",
11: """SELECT b.pd_no,b.pd_nm,b.pd_pbcm,b.crd_grd,b.mat_dt,b.applied_yield,b.info_base_dt FROM raw.bond_kr_master b JOIN enriched.bond_kr_enriched e USING(pd_no,pd_exg_mkt,info_seq) WHERE b.curr_cd='KRW' AND e.remaining_days>0 AND e.crd_grd_rank<=4 ORDER BY b.applied_yield DESC NULLS LAST,b.pd_no""",
12: """SELECT k.pd_itm_no,k.pd_nm,k.pd_pen_risk_nm,k.pd_risk_nm,k.pd_net_tamt,k.du_upt_dt FROM raw.etf_kr_master k WHERE k.pd_grp_no='ETF' AND k.pd_sale_yn='1' AND k.pd_tr_yn='0' AND k.pd_pen_tr_yn='Y' ORDER BY k.pd_net_tamt DESC NULLS LAST,k.pd_itm_no""",
13: """SELECT b.pd_no,b.pd_nm,b.crd_grd,e.crd_grd_rank,e.remaining_days,b.applied_yield FROM raw.bond_kr_master b JOIN enriched.bond_kr_enriched e USING(pd_no,pd_exg_mkt,info_seq) WHERE b.std_pd_mcls_nm='회사채' AND e.remaining_days>0 AND e.crd_grd_rank<=4 AND e.remaining_days<=1095 ORDER BY b.applied_yield DESC NULLS LAST,b.pd_no LIMIT 10""",
15: """SELECT k.pd_itm_no,k.pd_nm,k.du_last_aum,k.du_er_1y,e.charge_rt_final,k.cu_base_index,k.du_upt_dt FROM raw.etf_kr_master k JOIN enriched.etf_kr_enriched e USING(pd_itm_no) WHERE k.pd_grp_no='ETF' AND e.base_market='해외' AND e.base_asset='주식' AND e.replication='실물(패시브)' AND k.cu_lev_fector='1' AND k.du_last_aum>=1000000000000 ORDER BY k.du_er_1y DESC NULLS LAST,k.pd_itm_no LIMIT 5""",
16: """SELECT k.pd_itm_no,k.pd_nm,string_agg(t.theme,', ' ORDER BY t.theme) AS themes,k.du_last_aum,k.du_er_6m,e.charge_rt_final,k.pd_risk_nm,k.du_upt_dt FROM raw.etf_kr_master k JOIN enriched.etf_kr_enriched e USING(pd_itm_no) JOIN relations.etf_theme t USING(pd_itm_no) WHERE k.pd_grp_no='ETF' AND e.replication IN ('실물(액티브)','합성(액티브)') AND k.du_last_aum>=500000000000 GROUP BY k.pd_itm_no,k.pd_nm,k.du_last_aum,k.du_er_6m,e.charge_rt_final,k.pd_risk_nm,k.du_upt_dt ORDER BY k.du_last_aum DESC,k.pd_itm_no""",
17: """SELECT g.pd_itm_no,g.pd_nm,g.cu_base_index,g.cu_index_repl_mthd,g.du_last_aum,g.cu_charge_rt,g.pd_trd_ccy FROM raw.etf_gl_master g WHERE g.pd_grp_no='ETF' AND g.wu_inv_ast_type='Equity' AND g.wu_inv_rgn='United States of America' AND g.du_last_aum>=100000000000 AND g.cu_charge_rt<=0.05 ORDER BY g.du_last_aum DESC,g.pd_itm_no""",
18: """SELECT g.pd_itm_no,g.pd_nm,g.cu_base_index,g.wu_inv_rgn,g.cu_index_repl_mthd,g.cu_charge_rt,g.du_last_aum,g.ru_mkt_price,g.du_vol_1d,g.du_clpr_base_dt FROM raw.etf_gl_master g WHERE g.pd_grp_no='ETF' AND g.wu_inv_ast_type='Bond' AND g.cu_charge_rt<=0.10 ORDER BY g.du_last_aum DESC NULLS LAST,g.pd_itm_no LIMIT 10""",
19: """SELECT f.itm_no,f.itm_nm,f.fd_yr1_ern_r,f.fd_nast_suma,f.exchdg_yn,f.fd_ivst_rgn_desc,f.zrin_fd_ivst_risk_grd_nm FROM raw.fund_pub_master f WHERE f.prvo_pbff_desc='공모' AND f.sale_yn='판매중' AND f.fd_yr1_ern_r>0 AND f.fd_nast_suma>=100000000000 ORDER BY f.fd_yr1_ern_r DESC,f.itm_no""",
20: """SELECT 'ETF' AS product_type,k.pd_itm_no AS product_id,k.pd_nm AS product_name,k.du_last_aum AS aum,k.du_er_1y AS return_1y,t.theme AS evidence FROM raw.etf_kr_master k JOIN relations.etf_theme t USING(pd_itm_no) WHERE k.pd_grp_no='ETF' AND t.theme ILIKE '%반도체%' UNION ALL SELECT 'FUND',f.itm_no,f.itm_nm,f.fd_nast_suma,f.fd_yr1_ern_r,COALESCE(f.bmrk_nm,f.or_attr_desc) FROM raw.fund_pub_master f WHERE f.prvo_pbff_desc='공모' AND (f.bmrk_nm ILIKE '%반도체%' OR f.or_attr_desc ILIKE '%반도체%') ORDER BY aum DESC NULLS LAST,product_id""",
22: """SELECT k.pd_itm_no,k.pd_nm,h.holding_code_raw,h.holding_name,h.weight,h.as_of,h.source FROM relations.etf_holding h JOIN raw.etf_kr_master k USING(pd_itm_no) WHERE k.pd_grp_no='ETF' AND (h.holding_name ILIKE '%캠브리콘%' OR h.holding_name ILIKE '%CAMBRICON%') ORDER BY h.weight DESC NULLS LAST,k.pd_itm_no""",
23: """SELECT k.pd_itm_no,k.pd_nm,t.theme,t.as_of,t.source FROM relations.etf_theme t JOIN raw.etf_kr_master k USING(pd_itm_no) WHERE k.pd_grp_no='ETF' AND (t.theme ILIKE '%우주%' OR t.theme ILIKE '%항공%') ORDER BY k.pd_itm_no,t.theme""",
24: """SELECT k.pd_itm_no,k.pd_nm,k.du_last_aum,h.holding_name,h.weight,h.as_of,s.parent_name,s.child_name,s.source FROM relations.company_subsidiary s JOIN enriched.company_master c ON c.corp_code=s.child_corp_code JOIN relations.etf_holding h ON h.holding_code_raw=c.stock_code JOIN raw.etf_kr_master k USING(pd_itm_no) WHERE s.parent_name='에코프로' AND (s.ownership_pct>50 OR s.invest_purpose IN ('경영참여','경영참가','경영 참여')) AND k.pd_grp_no='ETF' ORDER BY k.du_last_aum DESC NULLS LAST,h.weight DESC NULLS LAST LIMIT 1""",
25: """SELECT f.itm_no,f.itm_nm,f.or_co_xtn_itt_cd,f.or_attr_desc,f.fd_nast_suma,f.sale_yn FROM raw.fund_pub_master f WHERE f.itm_nm ILIKE '%국민성장%' ORDER BY f.itm_no""",
26: """SELECT 'BOND' AS product_type,b.pd_no AS product_id,b.pd_nm AS product_name,b.crd_grd AS rating,b.applied_yield AS yield_value,(e.remaining_days>0) AS sellable,NULL::numeric AS weight,NULL::numeric AS aum FROM raw.bond_kr_master b JOIN enriched.bond_kr_enriched e USING(pd_no,pd_exg_mkt,info_seq) WHERE b.pd_pbcm='에스케이하이닉스(주)' AND e.remaining_days>0 UNION ALL SELECT 'ETF',k.pd_itm_no,k.pd_nm,NULL,NULL,NULL,h.weight,k.du_last_aum FROM relations.etf_holding h JOIN raw.etf_kr_master k USING(pd_itm_no) WHERE h.holding_code_raw='000660' AND k.pd_grp_no='ETF' ORDER BY aum DESC NULLS LAST,product_id""",
27: """WITH targets AS (SELECT stock_code FROM enriched.company_master WHERE corp_name_norm IN ('LG에너지솔루션','엘지에너지솔루션') UNION SELECT c.stock_code FROM relations.company_subsidiary s JOIN enriched.company_master c ON c.corp_code=s.child_corp_code WHERE s.parent_name IN ('LG에너지솔루션','엘지에너지솔루션') AND (s.ownership_pct>50 OR s.invest_purpose IN ('경영참여','경영참가','경영 참여'))) SELECT k.pd_itm_no,k.pd_nm,h.holding_name,h.weight,h.as_of,k.du_last_aum FROM relations.etf_holding h JOIN raw.etf_kr_master k USING(pd_itm_no) WHERE h.holding_code_raw IN (SELECT stock_code FROM targets WHERE stock_code IS NOT NULL) AND k.pd_grp_no='ETF' ORDER BY k.du_last_aum DESC NULLS LAST,k.pd_itm_no""",
28: """SELECT k.pd_itm_no,k.pd_nm,k.pd_abrv_nm,k.du_last_aum,k.cu_strtegy,h.holding_name,h.weight,h.as_of FROM relations.etf_holding h JOIN raw.etf_kr_master k USING(pd_itm_no) WHERE k.pd_grp_no='ETF' AND (h.holding_name ILIKE '%NVIDIA%' OR h.holding_name ILIKE '%엔비디아%') ORDER BY k.du_last_aum DESC NULLS LAST,k.pd_itm_no""",
29: """SELECT g.pd_itm_no,g.pd_nm,g.cu_base_index,g.cu_charge_rt,g.du_last_aum,g.pd_trd_ccy FROM raw.etf_gl_master g WHERE g.pd_itm_no IN ('VOO','IVV','SPY') AND g.pd_grp_no='ETF' ORDER BY g.pd_itm_no""",
30: """SELECT 'FUND' AS product_type,f.itm_no AS product_id,f.itm_nm AS product_name,f.fd_nast_suma AS aum,f.mtco_itm_no AS group_key FROM raw.fund_pub_master f WHERE f.itm_nm ILIKE '우리반도체BIG2플러스%' UNION ALL SELECT 'ETF',k.pd_itm_no,k.pd_nm,k.du_last_aum,NULL FROM raw.etf_kr_master k JOIN relations.etf_theme t USING(pd_itm_no) WHERE k.pd_grp_no='ETF' AND t.theme ILIKE '%반도체%' ORDER BY aum DESC NULLS LAST,product_id""",
}

FILTERS = {
11: [{"column": "remaining_days", "operator": ">", "value": 0},
     {"column": "crd_grd_rank", "operator": "<=", "value": 4}],
12: [{"column": "pd_grp_no", "operator": "=", "value": "ETF"},
     {"column": "pd_tr_yn", "operator": "=", "value": "0"}],
13: [{"column": "remaining_days", "operator": ">", "value": 0},
     {"column": "crd_grd_rank", "operator": "<=", "value": 4},
     {"column": "remaining_days", "operator": "<=", "value": 1095}],
15: [{"column": "pd_grp_no", "operator": "=", "value": "ETF"},
     {"column": "du_last_aum", "operator": ">=", "value": 1000000000000}],
17: [{"column": "cu_charge_rt", "operator": "<=", "value": 0.05}],
18: [{"column": "cu_charge_rt", "operator": "<=", "value": 0.10}],
19: [{"column": "fd_yr1_ern_r", "operator": ">", "value": 0},
     {"column": "fd_nast_suma", "operator": ">=", "value": 100000000000}],
}

TYPE1 = {1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 17, 18}
TYPE2 = {15, 16, 19, 20}
TYPE3 = {4, 26}
TYPE4 = {22, 23, 24, 25, 27, 28, 29, 30}
TYPE5 = {14, 21}
TYPE6 = {31, 32, 33, 34, 35}

EXTRA_CONCEPTS = {
14: ["fp:CreditRating", "fp:issuedBy"], 21: ["fp:hasShareClass", "fp:sameVehicleAs"],
22: ["fp:hasHolding", "fp:heldSecurity", "fp:weight", "fp:asOf", "fp:supportedBy"],
23: ["fp:hasHolding", "fp:relatedToTheme", "fp:asOf", "fp:Document"],
24: ["fp:hasSubsidiary", "fp:hasHolding", "fp:weight", "fp:Risk", "fp:Document"],
25: ["fp:Document", "fp:supportedBy"], 26: ["fp:issuedBy", "fp:hasHolding", "fp:weight"],
27: ["fp:hasSubsidiary", "fp:issuedBy", "fp:hasHolding", "fp:Risk"],
28: ["fp:hasHolding", "fp:investmentStrategy", "fp:Risk", "fp:Document"],
29: ["fp:tracksIndex", "fp:hasHolding", "fp:weight", "fp:Risk"],
30: ["fp:hasShareClass", "fp:hasHolding", "fp:hasSubsidiary", "fp:Risk"],
31: ["fp:CreditRating", "fp:ratingRank"], 32: ["fp:asOf"],
33: ["fp:Product", "fp:productName"], 34: ["fp:asOf", "fp:return1Y"],
35: ["fp:ETF", "fp:Bond", "fp:issuedBy"],
}


def snapshot() -> dict:
    files = CSV_INPUTS + TBOX + ABOX
    return {str(p.relative_to(ROOT)).replace("\\", "/"): sha(p) for p in files}


def route(qid: int) -> tuple[str, list[dict]]:
    def step(i, engine, deps=()):
        return {"id": i, "engine": engine, "depends_on": list(deps)}
    if qid in TYPE1:
        return "유형1_RDB단독", [step("A", "rdb")]
    if qid in TYPE2:
        return "유형2_Graph순차RDB", [step("A", "graph"), step("B", "rdb", ("A",))]
    if qid in TYPE3:
        return "유형3_Graph후RDBVector병렬", [step("A", "graph"), step("B", "rdb", ("A",)),
                                               step("C", "vector", ("A",))]
    if qid in TYPE4:
        return "유형4_Graph다단계순차전체", [step("A", "graph"), step("B", "rdb", ("A",)),
                                             step("C", "vector", ("B",))]
    if qid in TYPE5:
        return "유형5_Graph단독", [step("A", "graph")]
    return "유형6_TBox검증단독", []


def parse_terms() -> tuple[Graph, dict[str, dict]]:
    g = Graph()
    for p in TBOX:
        g.parse(p, format="turtle")
    terms = {}
    for s in set(g.subjects(RDFS.comment, None)):
        if not isinstance(s, URIRef) or not str(s).startswith(str(FP)):
            continue
        uri = f"fp:{str(s).split('#')[-1]}"
        labels = list(g.objects(s, RDFS.label))
        comments = list(g.objects(s, RDFS.comment))
        label = next((str(x) for x in labels if x.language == "ko"), str(labels[0]) if labels else "")
        comment = next((str(x) for x in comments if x.language == "ko"), str(comments[0]) if comments else "")
        terms[uri] = {"concept_uri": uri, "label": label, "description": comment,
                      "domain": [f"fp:{str(x).split('#')[-1]}" for x in g.objects(s, RDFS.domain)],
                      "range": [f"fp:{str(x).split('#')[-1]}" for x in g.objects(s, RDFS.range)],
                      "source_tables": [str(x) for x in g.objects(s, FP.sourceTable)],
                      "source_columns": [str(x) for x in g.objects(s, FP.sourceColumn)],
                      "is_object_property": (s, RDF.type, OWL.ObjectProperty) in g}
    return g, terms


def identifiers(sql_text: str, catalog: dict) -> tuple[list[str], list[str]]:
    table_names = [t["table"] for t in catalog["tables"]]
    used_tables = [t for t in table_names if re.search(rf"(?i)(?<![\w.]){re.escape(t)}(?!\w)", sql_text)]
    cols = sorted({c["name"] for t in catalog["tables"] for c in t["columns"]}, key=len, reverse=True)
    used_cols = [c for c in cols if re.search(rf"(?i)(?<!\w){re.escape(c)}(?!\w)", sql_text)]
    return used_tables, sorted(used_cols)


def make_gold(catalog: dict, terms: dict[str, dict]) -> tuple[list[dict], list[dict], list[dict]]:
    source = ROOT / "expected_qa/2026_expected_qa.csv"
    with source.open(encoding="utf-8-sig", newline="") as f:
        questions = [{k: row[k] for k in (
            "id", "type", "evaluation_type", "answerability", "product_category",
            "difficulty", "question", "required_evidence", "expected_behavior",
        )} for row in csv.DictReader(f)]
    expected = {"source": str(source.relative_to(ROOT)), "source_sha256": sha(source),
                "count": len(questions), "questions": questions}
    jdump(expected, GOLD / "expected_queries_35.json")
    snap = snapshot()
    nl, routing = [], []
    for row in questions:
        qid = int(row["id"])
        qtype, plan = route(qid)
        concepts = set(EXTRA_CONCEPTS.get(qid, []))
        if qid in SQL:
            tables, cols = identifiers(SQL[qid], catalog)
            for uri, term in terms.items():
                source_cols = {x.rsplit(".", 1)[-1].lower() for x in term["source_columns"]}
                if source_cols & set(cols):
                    concepts.add(uri)
            result_cols = []
            # Gold query의 실제 column contract는 실행기에서 cursor.description으로 다시 고정한다.
            nl.append({"question_id": f"q{qid:03d}", "question": row["question"],
                       "required_tables": tables, "required_columns": {"all": cols},
                       "required_filters": FILTERS.get(qid, []), "required_joins": [],
                       "required_sort": bool(re.search(r"(?i)\border\s+by\b", SQL[qid])),
                       "required_limit": (int(m.group(1)) if (m := re.search(r"(?i)\blimit\s+(\d+)", SQL[qid])) else None),
                       "result_columns": result_cols, "order_sensitive": "ORDER BY" in SQL[qid].upper(),
                       "gold_sql": SQL[qid], "grounded_concepts": sorted(concepts)})
        routing.append({"question_id": f"q{qid:03d}", "question": row["question"],
                        "expected_behavior": row["expected_behavior"], "query_type": qtype,
                        "execution_plan": plan, "grounded_concepts": sorted(concepts)})
    meta = {"data_cutoff": DATA_CUTOFF, "expected_queries_sha256": sha(source),
            "catalog_sha256": catalog["catalog_sha256"], "snapshot": snap}
    nl_doc = {"meta": meta, "count": len(nl), "questions": nl}
    routing_doc = {"meta": meta, "count": len(routing), "questions": routing}
    jdump(nl_doc, GOLD / "gold_nl2sql.json")
    jdump(routing_doc, GOLD / "gold_routing.json")
    return questions, nl, routing


TABLE_CODE = {
    "PRBD01N001": ["raw.bond_kr_master"],
    "PREF01N001": ["raw.etf_kr_master"],
    "PREF02N001": ["raw.etf_gl_master"],
    "PRFD01N001": ["raw.fund_pub_master"],
    "derived:bond_kr_enriched": ["enriched.bond_kr_enriched"],
    "derived:etf_kr_enriched": ["enriched.etf_kr_enriched"],
    "derived:company_master": ["enriched.company_master"],
    "derived:holding_code_map": ["enriched.holding_code_map"],
    "derived:etf_holding": ["relations.etf_holding"],
    "derived:etf_theme": ["relations.etf_theme"],
    "derived:company_subsidiary": ["relations.company_subsidiary"],
    "derived:relations": ["relations.etf_holding", "relations.etf_theme",
                          "relations.company_subsidiary"],
}

RULES = {
    "fp:ratingRank": {"usage": ["FILTER", "SORT"], "unit": "rank",
                      "filter_rule": "신용등급 범위는 crd_grd_rank로 비교하며 AA- 이상은 <= 4"},
    "fp:expenseRatio": {"usage": ["SELECT", "FILTER", "SORT"], "unit": "%",
                        "value_rule": "국내ETF는 charge_rt_final과 charge_rt_source를 사용"},
    "fp:remainingDays": {"usage": ["SELECT", "FILTER"], "unit": "day"},
    "fp:productName": {"usage": ["SELECT", "FILTER"],
                       "value_rule": "상품명은 완전일치 우선; 유사명 대체 금지"},
    "fp:weight": {"usage": ["SELECT", "FILTER", "SORT"], "unit": "%"},
    "fp:hasHolding": {"join_rule": "ETF만 편입관계 사용; ETN(pd_grp_no!='ETF') 제외"},
    "fp:netAssets": {"value_rule": "공모펀드는 raw.fund_pub_master를 사용하고 itm_no 단위로 집계"},
}


def physical_sources(term: dict, catalog: dict) -> list[dict]:
    by_table = {t["table"]: {c["name"]: c for c in t["columns"]} for t in catalog["tables"]}
    out = []
    for source_table in term["source_tables"]:
        keys = [source_table]
        if source_table.startswith("derived:") and "." in source_table:
            keys.append(source_table.rsplit(".", 1)[0])
        for table in {x for key in keys for x in TABLE_CODE.get(key, [])}:
            for annotated in term["source_columns"]:
                col = annotated.rsplit(".", 1)[-1].lower()
                if col not in by_table.get(table, {}):
                    continue
                item = by_table[table][col]
                out.append({"engine": "rdb", "path": f"{table}.{col}",
                            "datatype": item["datatype"], "usage": ["SELECT"]})
    if term["is_object_property"]:
        out.append({"engine": "graph", "predicate": term["concept_uri"]})
    return list({json.dumps(x, sort_keys=True): x for x in out}.values())


def make_contexts(catalog: dict, nl: list[dict], routing: list[dict], terms: dict[str, dict]) -> None:
    by_q = {x["question_id"]: x for x in routing}
    bq, cq = {}, {}
    for qid, gold in by_q.items():
        selected = [terms[u] for u in gold["grounded_concepts"] if u in terms]
        bq[qid] = [{k: t[k] for k in ("concept_uri", "label", "description", "domain", "range")}
                   for t in selected]
        citems = []
        for term in selected:
            item = {"concept_uri": term["concept_uri"], "label": term["label"],
                    "business_meaning": term["description"],
                    "sources": physical_sources(term, catalog)}
            rule = RULES.get(term["concept_uri"], {})
            for source in item["sources"]:
                source.update(rule)
            if term["concept_uri"] in {"fp:Document", "fp:Risk", "fp:supportedBy"}:
                item["sources"].append({"engine": "vector", "collection": "content_embeddings",
                                        "availability": "not_built",
                                        "value_rule": "근거 문서 미확보 시 확인할 수 없음"})
            citems.append(item)
        cq[qid] = citems
    meta = {"data_cutoff": DATA_CUTOFF, "catalog_sha256": catalog["catalog_sha256"],
            "tbox_sha256": {str(p.relative_to(ROOT)): sha(p) for p in TBOX},
            "graph_snapshot_sha256": {str(p.relative_to(ROOT)): sha(p) for p in TBOX + ABOX}}
    b = {"condition": "B", "meta": meta, "physical_schema": catalog["tables"],
         "question_contexts": bq}
    c = {"condition": "C", "meta": meta, "physical_schema": catalog["tables"],
         "question_contexts": cq,
         "global_rules": [f"data cutoff <= {DATA_CUTOFF}", "주최측 값 우선",
                          "근거 없으면 확인할 수 없음", "괴리율 더미 컬럼 사용 금지"]}
    jdump(b, CONTEXTS / "schema_tbox.json")
    jdump(c, CONTEXTS / "schema_tbox_business.json")


def validate(catalog: dict) -> None:
    a = json.loads((CONTEXTS / "schema_only.json").read_text(encoding="utf-8"))
    b = json.loads((CONTEXTS / "schema_tbox.json").read_text(encoding="utf-8"))
    c = json.loads((CONTEXTS / "schema_tbox_business.json").read_text(encoding="utf-8"))
    assert "question_contexts" not in a
    assert "sources" not in json.dumps(b, ensure_ascii=False)
    valid = {f"{t['table']}.{col['name']}" for t in catalog["tables"] for col in t["columns"]}
    paths = [s["path"] for xs in c["question_contexts"].values() for x in xs
             for s in x["sources"] if s["engine"] == "rdb"]
    bad = set(paths) - valid
    assert not bad, f"존재하지 않는 C binding: {bad}"
    assert len(json.loads((GOLD / "gold_nl2sql.json").read_text())["questions"]) == 28
    assert len(json.loads((GOLD / "gold_routing.json").read_text())["questions"]) == 35
    nl = json.loads((GOLD / "gold_nl2sql.json").read_text())["questions"]
    assert all("enriched.fund_pub_dedup" not in q["gold_sql"] for q in nl)
    assert all("buyable_quantity" not in q["gold_sql"] for q in nl)
    assert all("fp:buyableQuantity" not in q["grounded_concepts"] for q in nl)
    print(f"PASS Gold 28/35, context leakage/path 검증, C bindings {len(paths)}")


def main() -> None:
    catalog = json.loads((CONTEXTS / "schema_only.json").read_text(encoding="utf-8"))
    _, terms = parse_terms()
    _, nl, routing = make_gold(catalog, terms)
    make_contexts(catalog, nl, routing, terms)
    validate(catalog)


if __name__ == "__main__":
    main()
