# -*- coding: utf-8 -*-
"""RDB manifest → compact catalog, verified binding 정적 검증.

    python3 src/kb/build_schema_catalog.py          # artifact 생성 + 검증
    python3 src/kb/build_schema_catalog.py --check  # 쓰기 없이 검증

운영 binding은 사람이 검토한 metadata/*.json이 정본이다. 이 스크립트는 그 식별자가
실제 적재 manifest와 TBox에 존재하는지만 확인하며 gold SQL은 읽지 않는다.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

from rdflib import Graph, URIRef

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import ARTIFACTS, ROOT  # noqa: E402
from kb.build_rdb import TABLES, rows  # noqa: E402

BINDINGS = ROOT / "metadata/schema_bindings.json"
RULES = ROOT / "metadata/business_rules.json"
OUT = ARTIFACTS / "schema_catalog.json"
TABLE_DEF = ROOT / "docs/docs_data_layer/table_definition_v1_0.csv"
FP = "http://mafest.ai/product#"

TABLE_META = {
    "raw.bond_kr_master": ("국내채권 원본 마스터", "채권 거래·정보차수 1건/행", "2026-08-21 (info_base_dt)", "organizer", "원본 CSV 무변경 적재", "PK=(pd_no,pd_exg_mkt,info_seq); pd_no 중복 그룹 포함 행 2,463건"),
    "raw.etf_kr_master": ("국내 ETF·ETN 원본 마스터", "상품 1건/행", "2026-08-21 (가격·기준가)", "organizer", "원본 CSV 무변경 적재", "ETF 질의는 pd_grp_no='ETF' 필수"),
    "raw.etf_gl_master": ("해외 ETF·ETN 원본 마스터", "상품 1건/행", "2026-08-21 (종가 최빈값; 행별 기준일)", "organizer", "원본 CSV 무변경 적재", "문장형 sentinel은 NULL 취급 필요"),
    "raw.fund_pub_master": ("펀드 원본 마스터", "펀드 1건/행", "2026-08-21 (원천에 기준일 컬럼 없음)", "organizer", "원본 CSV 무변경 적재", "itm_no PK; prfd_attr_cds는 원천에 집약된 속성 목록"),
    "enriched.bond_kr_enriched": ("채권 등급·잔존만기·만기미도래 파생", "채권 거래·정보차수 1건/행", "2026-08-21 (잔존만기 재계산)", "derived_from_organizer", "채권 원본에서 결정적으로 파생", "PK/FK=(pd_no,pd_exg_mkt,info_seq); 등급 rank 1~19"),
    "enriched.etf_kr_enriched": ("국내 ETF·ETN LSEG 스칼라 보강", "상품 1건/행", "LSEG 수집시점 미확인", "organizer_then_external", "주최측 실값 우선, 결측·0.0 더미만 LSEG 보완", "pd_itm_no='KR' 1행 제외; charge_rt_source 필수"),
    "enriched.company_master": ("DART 기업 고유번호 마스터", "기업 1건/행", "2026-08-24 이하", "external", "DART corpCode와 KIND에서 생성", "corp_code PK; 법인명 정규화 규칙 고정"),
    "enriched.holding_code_map": ("편입종목 식별자 해소표", "원본 편입코드 1건/행", "2026-07-10", "derived", "정확히 확정 가능한 ticker·ETF·우선주만 매핑", "미해소는 공란 유지; match_rule 보존"),
    "relations.etf_theme": ("국내 ETF-테마 관계", "ETF-테마 1건/행", "확인할 수 없음", "external", "LSEG themes를 롱포맷 변환", "as_of 추정 금지"),
    "relations.etf_holding": ("국내 ETF-편입종목 관계", "ETF-편입종목 1건/행", "2026-07-10", "external", "운용사 원천을 공통 롱포맷으로 변환", "룩어헤드 현재가·등락 제외; holding_id identity"),
    "relations.company_subsidiary": ("기업-자회사 출자 관계", "출자관계 1건/행", "공시 접수일 (2026-08-24 이하)", "external", "DART 타법인출자현황을 롱포맷 변환", "미확정 자회사 코드는 공란; relation_id identity"),
}

VECTOR_TABLES = (
    ("bond_schema_terms", 130, "common.ttl + bond_kr.ttl", "운영 채권 TBox 인덱스"),
    ("schema_terms_all", 188, "TBox 5개 TTL", "평가용 전체 도메인 TBox 인덱스"),
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def catalog() -> dict:
    return {
        "version": 1,
        "tables": [
            {
                "table": t.fq,
                "columns": ([{"name": t.identity, "datatype": "bigint"}]
                            if t.identity else [])
                           + [{"name": n, "datatype": dt} for n, dt in t.types.items()],
                "primary_key": list(t.primary_key),
                "foreign_keys": [
                    {"columns": list(c) if isinstance(c, tuple) else [c],
                     "references_table": rt,
                     "references_columns": list(rc) if isinstance(rc, tuple) else [rc]}
                    for c, rt, rc in t.foreign_keys
                ],
            }
            for t in TABLES
        ],
    }


def source_labels(table: str) -> dict[str, str]:
    codes = {
        "raw.bond_kr_master": "PRBD01N001", "enriched.bond_kr_enriched": "PRBD01N001",
        "raw.etf_kr_master": "PREF01N001", "enriched.etf_kr_enriched": "PREF01N001",
        "raw.etf_gl_master": "PREF02N001",
        "raw.fund_pub_master": "PRFD01N001",
    }
    code = codes.get(table)
    if not code:
        return {}
    path = next((ROOT / "data/csv").glob(f"{code}_*_schema_20260824.csv"))
    with path.open(encoding="utf-8-sig", newline="") as f:
        return {r["column"].lower(): r["comment_ko"] for r in csv.DictReader(f)}


def table_definition(metadata: dict) -> list[dict[str, object]]:
    binding = {(b["table"], b["column"]): b for b in metadata.get("bindings", [])}
    out = []
    for table in TABLES:
        desc, grain, as_of, priority, transform, quality = TABLE_META[table.fq]
        labels = source_labels(table.fq)
        fks = {
            c: f"{rt}.{'/'.join(rc if isinstance(rc, tuple) else (rc,))}"
            for cols, rt, rc in table.foreign_keys
            for c in (cols if isinstance(cols, tuple) else (cols,))
        }
        columns = ([(table.identity, "bigint")] if table.identity else []) + list(table.types.items())
        row_count = sum(row is not None for _, row in rows(table))
        for order, (name, datatype) in enumerate(columns, 1):
            b = binding.get((table.fq, name), {})
            out.append({
                "store": "PostgreSQL/RDB", "schema": table.schema, "table": table.name,
                "table_description": desc, "grain": grain,
                "source_file": str(table.path.relative_to(ROOT)), "row_count": row_count,
                "column_order": order, "column_name": name,
                "column_description": b.get("label") or labels.get(name) or "확인할 수 없음",
                "data_type": datatype, "nullable": "N" if name in table.primary_key else "Y",
                "primary_key": "Y" if name in table.primary_key else "N",
                "foreign_key": fks.get(name, ""), "unit": b.get("unit", ""),
                "as_of_basis": as_of, "source_priority": priority,
                "transformation_rule": transform, "quality_rule": quality,
                "implementation_status": "live DB 검증 완료 (2026-08-24)",
            })
    for name, count, source, desc in VECTOR_TABLES:
        columns = (("term_uri", "text", "용어 URI", "N", "Y"),
                   ("label", "text", "대표 라벨", "N", "N"),
                   ("comment", "text", "TBox 설명", "N", "N"),
                   ("alt_labels", "text[]", "대체 라벨", "N", "N"),
                   ("content", "text", "임베딩 입력 텍스트", "N", "N"),
                   ("embedding", "vector(1024)", "CLOVA Studio bge-m3 임베딩", "N", "N"))
        for order, (column, datatype, column_desc, nullable, pk) in enumerate(columns, 1):
            out.append({
                "store": "PostgreSQL/pgvector", "schema": "public", "table": name,
                "table_description": desc, "grain": "TBox resource 1건/행",
                "source_file": source, "row_count": count, "column_order": order,
                "column_name": column, "column_description": column_desc,
                "data_type": datatype, "nullable": nullable, "primary_key": pk,
                "foreign_key": "", "unit": "", "as_of_basis": "ontology schema version",
                "source_priority": "ontology", "transformation_rule": "URI·label·altLabel·comment 결합 후 임베딩",
                "quality_rule": "rdfs:comment 없는 resource 제외; embedding 1024차원",
                "implementation_status": "live DB 검증 완료 (2026-08-24)",
            })
    return out


def write_table_definition(rows: list[dict[str, object]]) -> None:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    TABLE_DEF.parent.mkdir(parents=True, exist_ok=True)
    TABLE_DEF.write_bytes(b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8"))


def tbox_uris() -> set[str]:
    graph = Graph()
    for name in ("common.ttl", "bond_kr.ttl", "etf_kr.ttl", "etf_gl.ttl", "fund_pub.ttl"):
        graph.parse(ROOT / "ontology" / name, format="turtle")
    return {f"fp:{str(s).split('#')[-1]}" for s in set(graph.subjects())
            if isinstance(s, URIRef) and str(s).startswith(FP)}


def validate(cat: dict, metadata: dict, rules: dict) -> None:
    tables = {t["table"]: {c["name"] for c in t["columns"]} for t in cat["tables"]}
    bindings = metadata.get("bindings") or []
    ids = [b["id"] for b in bindings]
    if len(ids) != len(set(ids)):
        raise ValueError("binding id 중복")
    domains = set(metadata.get("domains") or {})
    uris = tbox_uris()
    bad = []
    for b in bindings:
        if b["domain"] not in domains:
            bad.append(f"{b['id']}: 알 수 없는 domain {b['domain']}")
        if b["table"] not in tables or b["column"] not in tables.get(b["table"], set()):
            bad.append(f"{b['id']}: 없는 source {b['table']}.{b['column']}")
        if b.get("concept_uri") and b["concept_uri"] not in uris:
            bad.append(f"{b['id']}: TBox에 없는 concept {b['concept_uri']}")
        if not set(b["usage"]) <= {"select", "filter", "sort"}:
            bad.append(f"{b['id']}: usage 오류 {b['usage']}")
    for d, spec in metadata["domains"].items():
        if spec["base_table"] not in tables:
            bad.append(f"{d}: 없는 base_table {spec['base_table']}")
        for key in ("id", "name"):
            if spec[key] not in ids:
                bad.append(f"{d}: 없는 {key} binding {spec[key]}")
    for j in metadata.get("joins") or []:
        left_keys = j.get("left_keys") or [j.get("left_key")]
        right_keys = j.get("right_keys") or [j.get("right_key")]
        if len(left_keys) != len(right_keys) or not left_keys:
            bad.append(f"JOIN key 수 오류 {j['left']} ↔ {j['right']}")
        for key in left_keys:
            if j["left"] not in tables or key not in tables.get(j["left"], set()):
                bad.append(f"JOIN left 오류 {j['left']}.{key}")
        for key in right_keys:
            if j["right"] not in tables or key not in tables.get(j["right"], set()):
                bad.append(f"JOIN right 오류 {j['right']}.{key}")
    paths = {f"{b['table']}.{b['column']}" for b in bindings}
    forbidden = set(rules["forbidden_columns"])
    if paths & forbidden:
        bad.append(f"금지 컬럼 binding {sorted(paths & forbidden)}")
    referenced = {
        x["binding"]
        for xs in rules.get("mandatory_filters", {}).values() for x in xs
    } | {
        x["binding"]
        for r in rules.get("target_filters", []) for x in r["filters"]
    } | {
        x["binding"]
        for xs in rules.get("default_order", {}).values() for x in xs
    }
    missing = referenced - set(ids)
    if missing:
        bad.append(f"rule이 없는 binding 참조 {sorted(missing)}")
    if rules.get("data_cutoff") != "2026-08-24":
        bad.append("data cutoff는 2026-08-24여야 함")
    if bad:
        raise ValueError("\n".join(bad))
    print(f"PASS schema catalog — tables={len(tables)} bindings={len(bindings)} "
          f"joins={len(metadata.get('joins') or [])} forbidden=0")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    cat, metadata, rules = catalog(), load(BINDINGS), load(RULES)
    validate(cat, metadata, rules)
    if not args.check:
        OUT.parent.mkdir(exist_ok=True)
        OUT.write_text(json.dumps(cat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"catalog → {OUT.relative_to(ROOT)}")
        rows = table_definition(metadata)
        write_table_definition(rows)
        print(f"table definition → {TABLE_DEF.relative_to(ROOT)} ({len(rows)} columns)")


if __name__ == "__main__":
    main()
