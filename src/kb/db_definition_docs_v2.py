# -*- coding: utf-8 -*-
"""RDB·VectorDB·GraphDB 정의서 3종의 결정적 Markdown 렌더러."""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from rdflib import BNode, Graph, Literal, Namespace, RDF, RDFS, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, XSD

from kb.catalog_v2 import VIEW_DEFINITIONS, TableDef
from kb.v2_manifest import (
    DATASET_VERSION,
    EXPECTED_ABOX_TRIPLES,
    EXTERNAL_CUTOFF,
    RELEASE_DATE,
    RELEASE_ID,
    ROOT,
    snapshot_hash,
)

FP = Namespace("http://mafest.ai/product#")
FPI = "http://mafest.ai/instance/"
TBOX_FILES = ("common.ttl", "bond_kr.ttl", "etf_kr.ttl", "etf_gl.ttl", "fund_pub.ttl")
ABOX_DOMAINS = ("bond_kr", "etf_kr", "etf_gl", "fund_pub", "company")


def md(value: object) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def automatic_header(title: str, source_text: str) -> list[str]:
    return [
        f"# {title}",
        "",
        "이 문서는 팀원과 Agent/LLM이 별도 구두 설명 없이 물리 구조와 의미 계약을 재구성할 수 있도록 만든 자급형 정의서입니다.",
        "자동 생성 파일이므로 직접 편집하지 말고 `python src/kb/build_catalog_v2.py`를 실행합니다.",
        source_text,
        "",
        f"- 데이터 버전: `{DATASET_VERSION}`",
        f"- release ID: `{RELEASE_ID}`",
        f"- 배포일: `{RELEASE_DATE.isoformat()}`",
        f"- 외부 근거 cutoff: `{EXTERNAL_CUTOFF.isoformat()}`",
        "",
    ]


def table_inventory(tables: Iterable[TableDef]) -> list[str]:
    rows = [
        "| 스키마 | 테이블 | 종류 | grain | PK | 인덱스 | 상태 |",
        "|---|---|---|---|---|---|---|",
    ]
    for table in tables:
        pk = ", ".join(
            column.name
            for column in sorted(
                (column for column in table.columns if column.pk_ordinal),
                key=lambda value: value.pk_ordinal or 0,
            )
        ) or "없음"
        rows.append(
            f"| `{table.schema}` | `{table.name}` | {md(table.kind)} | {md(table.grain)} | "
            f"`{md(pk)}` | {md(', '.join(table.indexes) or 'PK만')} | "
            f"구현={md(table.implementation_status)}, 배포={md(table.deployment_status)} |"
        )
    rows.append("")
    return rows


def table_details(tables: Iterable[TableDef]) -> list[str]:
    sections: list[str] = []
    for table in tables:
        pk = ", ".join(
            column.name
            for column in sorted(
                (column for column in table.columns if column.pk_ordinal),
                key=lambda value: value.pk_ordinal or 0,
            )
        ) or "없음"
        sections.extend(
            [
                f"### `{table.fq_name}`",
                "",
                f"- 종류: {table.kind}",
                f"- 설명: {table.description}",
                f"- grain: {table.grain}",
                f"- PK: `{pk}`",
                f"- 인덱스: {', '.join(table.indexes) or 'PK만'}",
                f"- 상태: 구현={table.implementation_status}, 배포={table.deployment_status}",
                "",
                "| # | 컬럼 | 타입 | NULL | PK | FK | 단위 | 기준일 축 | 설명 | 0/결측 | 출처 우선순위 | 변환식 |",
                "|---:|---|---|:---:|---:|---|---|---|---|---|---|---|",
            ]
        )
        for ordinal, column in enumerate(table.columns, 1):
            sections.append(
                "| "
                + " | ".join(
                    md(value)
                    for value in (
                        ordinal,
                        f"`{column.name}`",
                        f"`{column.data_type}`",
                        "Y" if column.nullable else "N",
                        column.pk_ordinal or "",
                        column.fk_target,
                        column.unit,
                        column.as_of_column,
                        column.description,
                        column.zero_null_rule,
                        column.source_priority,
                        column.transform_expression,
                    )
                )
                + " |"
            )
        sections.append("")
    return sections


def rdb_definition_markdown(inspections, catalog: tuple[TableDef, ...]) -> str:
    tables = tuple(table for table in catalog if table.schema != "vec")
    counts = Counter(table.schema for table in tables)
    view_counts = Counter(str(view["name"]).split(".", 1)[0] for view in VIEW_DEFINITIONS)
    sections = automatic_header(
        "RDB DEFINITION V2.0",
        "물리 정의의 정본은 [단일 카탈로그](../../src/kb/catalog_v2.py)와 "
        "[PostgreSQL DDL](../../sql/v2/001_platform_schema.sql)입니다. `vec.*` 상세는 "
        "[VectorDB 정의서](VECTORDB_DEFINITION_V2_0.md)가 소유합니다.",
    )
    sections.extend(
        [
            "## 이 문서를 읽는 순서",
            "",
            "1. `범위와 엔진`에서 이 DB가 담당하는 계산을 확인합니다.",
            "2. `식별자와 조인 지도`에서 기준 엔티티와 조인키를 정합니다.",
            "3. `지표 의미 사전`과 `핵심 데이터 규칙`으로 단위·기준일·결측 의미를 적용합니다.",
            "4. `테이블 목록`에서 grain을 고른 뒤 `물리 테이블 상세`의 컬럼명만 사용해 SQL을 만듭니다.",
            "5. 결과에는 `LLM/Agent evidence 계약`의 식별자·출처·실질 기준일을 항상 포함합니다.",
            "",
            "## 범위와 엔진",
            "",
            "- 엔진: PostgreSQL 17",
            "- 물리 스키마: `meta`, `raw`, `enriched`, `relations`",
            "- 공개 호환 스키마: `core` 및 코드명 `raw.*` 뷰",
            "- stage 배포: 동일 DB의 `*_next`에서 검증 후 트랜잭션으로 정식 이름에 승격",
            "- API 계정: `agent_reader`; 읽기 전용, statement timeout 2초, 최대 100행",
            "- 담당 연산: 정확 조회, 숫자 필터·정렬·집계, 상품·지표·관계의 물리 조인",
            "- 비담당 연산: 자연어 의미 매핑은 VectorDB, 다중 홉 관계·온톨로지 유효성은 GraphDB가 담당",
            "",
            "## 읽기 인터페이스",
            "",
            "| API | 용도 |",
            "|---|---|",
            "| `GET /db/version` | dataset version, release/cutoff, snapshot hash |",
            "| `GET /db/tables` / `GET /db/columns` / `GET /db/columns/{schema}/{table}` | 물리 테이블·컬럼 탐색 |",
            "| `GET /db/stats` | raw·상품·관계·vector 행 수 |",
            "| `GET /db/catalog` | Agent용 전체 schema catalog |",
            "| `GET /db/coverage` | 상품별 holdings·문서·성과 확보 상태 |",
            "| `POST /db`, `POST /db/sql` | 읽기 전용 SELECT/CTE 실행; `sql`/`query` 별칭 |",
            "| `POST /db/sparql` | 읽기 전용 SPARQL; `sparql`/`query` 별칭 |",
            "",
            "직접 연결과 API 모두 쓰기 쿼리를 허용하지 않습니다. 운영 쓰기·스키마 승격은 서버 운영자 계정만 수행합니다.",
            "",
            "## 데이터 스냅샷 계약",
            "",
            f"- 전체 snapshot SHA-256: `{snapshot_hash(inspections)}`",
            "- 공백만 NULL로 변환하고 숫자 0과 내부 코드는 원문 그대로 보존합니다.",
            "- 원천별 실질 기준일은 파일명 날짜가 아니라 실제 날짜축의 최댓값입니다.",
            "",
            "| 코드 | 원천 파일 | 원천 행 | 적재 행 | 열 | PK | 실질 기준일 | SHA-256 |",
            "|---|---|---:|---:|---:|---|---|---|",
        ]
    )
    for item in inspections:
        sections.append(
            f"| {item.spec.code} | `{item.data_path.name}` | {item.row_count:,} | "
            f"{item.row_count - item.excluded_rows:,} | {len(item.columns)} | "
            f"`{', '.join(item.spec.primary_key)}` | {item.effective_as_of or '미표기'} | "
            f"`{item.data_sha256}` |"
        )
    sections.extend(
        [
            "",
            "## 스키마별 책임",
            "",
            "| 스키마 | 책임 | 물리 테이블 | 뷰/MV |",
            "|---|---|---:|---:|",
            f"| `meta` | snapshot, 적재 이력, 컬럼 카탈로그, 상품별 coverage | {counts['meta']} | {view_counts['meta']} |",
            f"| `raw` | 공식 XLSX의 컬럼·타입·grain 보존 | {counts['raw']} | {view_counts['raw']} |",
            f"| `enriched` | 공통 상품·지표·식별자와 도메인별 1상품 grain | {counts['enriched']} | {view_counts['enriched']} |",
            f"| `relations` | 문서·편입·분류·자회사·상품문서 관계 | {counts['relations']} | {view_counts['relations']} |",
            f"| `core` | 기존 Agent 호환 읽기 뷰 | {counts['core']} | {view_counts['core']} |",
            "",
            "## 식별자와 조인 지도",
            "",
            "`enriched.product_master.product_id`가 세 DB를 잇는 정규 식별자입니다. 원천 식별자를 직접 섞어 조인하지 않습니다.",
            "",
            "| 상품유형 | `product_id` 규칙 | 원천 식별자 | 도메인 테이블 |",
            "|---|---|---|---|",
            "| 국내채권 | `bond_kr:{pd_no}` | `raw.bond_kr_master.pd_no` | `enriched.bond_kr_product`, `enriched.bond_kr_offer` |",
            "| 국내 ETF | `etf_kr:{pd_itm_no}` | `raw.etf_kr_master.pd_itm_no` | `enriched.etf_kr` |",
            "| 국내 ETN | `etn_kr:{pd_itm_no}` | `raw.etf_kr_master.pd_itm_no` | `enriched.etn_kr` |",
            "| 해외 ETF | `etf_gl:{pd_itm_no}` | `raw.etf_gl_master.pd_itm_no` | `enriched.etf_gl` |",
            "| 해외 ETN | `etn_gl:{pd_itm_no}` | `raw.etf_gl_master.pd_itm_no` | `enriched.etn_gl` |",
            "| 공모펀드 | `fund:{itm_no}` | `raw.fund_pub_master.itm_no` | `enriched.fund` 및 `enriched.fund_pub` 뷰 |",
            "| 사모펀드 | `fund:{itm_no}` | `raw.fund_pub_master.itm_no` | `enriched.fund` |",
            "",
            "| 시작 테이블 | 조인 대상 | 조인 조건 | 의미 |",
            "|---|---|---|---|",
            "| `enriched.product_master p` | 도메인 테이블 `d` | `d.product_id = p.product_id` | 상품 공통 속성 + 유형별 속성 |",
            "| `enriched.product_master p` | `enriched.product_metric m` | `m.product_id = p.product_id` | AUM·수익률·보수 등 장형 지표 |",
            "| `enriched.product_master p` | `meta.product_coverage c` | `c.product_id = p.product_id` | holdings·문서·성과 확보 상태 |",
            "| `enriched.product_master p` | `relations.product_classification c` | `c.product_id = p.product_id` | 지역·자산군·섹터·테마 분류 |",
            "| `enriched.product_master p` | `relations.product_holding h` | `h.product_id = p.product_id` | 상품 편입증권과 비중 |",
            "| `relations.product_holding h` | `enriched.security_master s` | `s.security_id = h.security_id` | 편입증권 표준명 |",
            "| `enriched.security_master s` | `enriched.security_identifier i` | `i.security_id = s.security_id` | ISIN·티커·RIC 등 대체 식별자 |",
            "| `relations.product_document pd` | `relations.source_document d` | `d.document_id = pd.document_id` | 상품별 공식 문서와 provenance |",
            "",
            "같은 상품의 다중 행이 정상인 테이블(`bond_kr_offer`, `product_metric`, `product_holding`, `product_classification`)은 먼저 grain과 기준일을 제한한 뒤 조인합니다. 그렇지 않으면 행이 곱집합으로 부풀어납니다.",
            "",
            "## 지표 의미 사전",
            "",
            "`product_metric`은 `(product_id, metric_code, as_of, source, method)` grain입니다. 비교·랭킹에는 `is_available=true AND value IS NOT NULL AND value <> 0`을 모두 적용합니다.",
            "",
            "| 상품군 | metric | 값 원천 | 실제 기준일 축 | 단위/주의 |",
            "|---|---|---|---|---|",
            "| 국내 ETF/ETN | `AUM` | `du_last_aum` | `du_upt_dt` | 원천 명시 통화; 0은 값 없음 |",
            "| 국내 ETF/ETN | `RETURN_1Y` | `du_er_1y` | `du_upt_dt` | `%`; 0은 값 없음 |",
            "| 국내 ETF/ETN | `EXPENSE_RATIO` | `cu_charge_rt` | `cu_upt_dt` | `%`; AUM/수익률과 기준일 축이 다름 |",
            "| 해외 ETF/ETN | `AUM` | `du_last_aum` | `du_upt_dt` | 원천 명시 통화; 0은 값 없음 |",
            "| 해외 ETF/ETN | `EXPENSE_RATIO` | `cu_charge_rt` | `cu_upt_dt` | `%` |",
            "| 해외 ETF | `RETURN_1Y` | LSEG 조정가격/total-return | 관측 종료일 | 1년 관측창과 권한이 충족될 때만 외부 2순위 |",
            "| 펀드 | `AUM` | `fd_nast_suma` | `fd_daily_bas_dt` | 원천 명시 통화; 0은 값 없음 |",
            "| 펀드 | `RETURN_1Y` | `fd_yr1_ern_r` | `fd_price_bas_dt` | `%`; 0은 값 없음 |",
            "| 펀드 | `EXPENSE_RATIO` | `ofwk_trus_rwrd_r + or_co_rwrd_r + sale_co_rwrd_r + trusc_rwrd_r` | `fd_price_bas_dt` | 네 구성요소가 모두 있을 때만 계산; `zrin_fd_cmst_rt`는 펀드구성비율이므로 절대 보수로 쓰지 않음 |",
            "",
            "## 테이블 목록",
            "",
        ]
    )
    sections.extend(table_inventory(tables))
    sections.extend(
        [
            "## 뷰와 materialized view",
            "",
            "| 이름 | 종류 | 원천 | 목적/필터 |",
            "|---|---|---|---|",
        ]
    )
    for view in VIEW_DEFINITIONS:
        sections.append(
            f"| `{md(view['name'])}` | {md(view.get('kind', 'view'))} | "
            f"`{md(view['source'])}` | {md(view.get('purpose') or view.get('filter', ''))} |"
        )
    sections.extend(
        [
            "",
            "## 핵심 데이터 규칙",
            "",
            "- `buyable_quantity`는 저장·표시 전용이며 구매가능 판정, 필터, 정렬에 사용하지 않습니다.",
            "- 채권 구매가능 가정은 최신 정본 존재와 명시적 만기 여부만 사용하고 판정 규칙을 함께 저장합니다.",
            "- 국내 원천의 ETF/ETN은 `pd_grp_no`로 분리하고 ETN에는 편입종목 개념을 적용하지 않습니다.",
            "- 260824 펀드는 `itm_no`당 1행이며 공모·사모를 모두 보존하고 `fund_pub` 뷰만 공모를 노출합니다.",
            "- 지표의 0/NULL/기준일 미확보는 `is_available=false`이며 랭킹과 비교에서 제외합니다.",
            "- `product_coverage.unavailable`은 관계 미확보이며 ‘보유하지 않음’을 뜻하지 않습니다.",
            "- 주최측에 존재하는 지표 축이 우선이며 축 자체가 없을 때만 cutoff를 통과한 외부값을 사용합니다.",
            "- 해외 ETF의 `pd_lstg_dt` 공식 의미는 설정일이며 `inception_date`에 저장합니다. 실제 상장일로 답하지 않습니다.",
            "- 내부 코드에 이름 컬럼이나 공식 코드표가 없으면 원문만 반환하고 의미를 추정하지 않습니다.",
            "",
            "## 안전한 SQL 패턴",
            "",
            "상품명 정확 조회 후 지표를 붙이는 기본 패턴입니다.",
            "",
            "```sql",
            "SELECT p.product_id, p.product_name, m.metric_code, m.value, m.unit,",
            "       m.as_of, m.source, m.source_column",
            "FROM enriched.product_master p",
            "LEFT JOIN enriched.product_metric m ON m.product_id = p.product_id",
            "WHERE p.product_name = %(product_name)s",
            "ORDER BY m.metric_code, m.as_of DESC NULLS LAST;",
            "```",
            "",
            "TOP-N 지표는 0·결측·미확보를 먼저 제외합니다.",
            "",
            "```sql",
            "SELECT p.product_id, p.product_name, m.value, m.unit, m.as_of, m.source",
            "FROM enriched.product_metric m",
            "JOIN enriched.product_master p USING (product_id)",
            "WHERE p.product_type = 'ETF_KR' AND m.metric_code = 'AUM'",
            "  AND m.is_available AND m.value IS NOT NULL AND m.value <> 0",
            "ORDER BY m.value DESC",
            "LIMIT 10;",
            "```",
            "",
            "채권 판매가능 질의는 `buyable_quantity`를 조건으로 쓰지 않습니다. `is_assumed_purchasable`과 `purchasability_rule`을 함께 반환합니다. 편입 검색 결과가 0행이면 먼저 `meta.product_coverage.holdings_status`를 확인해 `available`일 때만 ‘보유하지 않음’으로 해석합니다.",
            "",
            "## LLM/Agent evidence 계약",
            "",
            "모든 답변 레코드는 최소한 `product_id`, 표시명, 사용한 물리 컬럼 또는 `metric_code`, `value`, `unit`, 실제 `as_of`, `source`를 보존합니다. 관계 답변은 `document_id` 또는 원천 관계 ID와 관계 `as_of`를 추가합니다.",
            "",
            "- 값을 찾지 못하면 `NULL`을 임의의 0으로 바꾸지 말고 ‘값 없음’으로 답합니다.",
            "- 이름 유사도만으로 상품·증권·기업 식별자를 합치지 않습니다. 식별자가 해소되지 않으면 `unresolved` 또는 ABSTAIN입니다.",
            "- 코드 문자열의 뜻, 해외 ETF 설정일과 상장일, 관계 triple 부재를 추측하지 않습니다.",
            "- Graph 후보를 RDB에 넘길 때 문자열로 `IN (...)`을 조립하지 말고 배열 파라미터 `product_id = ANY(%s)`를 사용합니다.",
            "- 숫자 주장마다 서로 다른 실제 기준일 축을 유지합니다. 한 행의 snapshot 날짜를 모든 지표 날짜로 복사하지 않습니다.",
            "",
            "## 물리 테이블 상세",
            "",
        ]
    )
    sections.extend(table_details(tables))
    sections.extend(
        [
            "## 적재·검증·권한",
            "",
            "1. 정상 XLSX 8개 집합, SHA-256, 행·열, 헤더, PK, cutoff를 검사합니다.",
            "2. `raw_next` 적재 후 `meta_next`, `enriched_next`, `relations_next`, `core_next`를 생성합니다.",
            "3. PK 유일성, FK orphan, 지표 날짜축, 0/NULL, 구매가능 규칙을 검증합니다.",
            "4. 모든 계층 검증 후 `*_next`를 정식 이름으로 승격하고 기존 정식 스키마는 `*_prev`로 보존합니다.",
            "5. 승격 직후 [읽기 권한 SQL](../../sql/v2/100_readonly_grants.sql)을 다시 적용합니다.",
            "",
        ]
    )
    return "\n".join(sections)


def load_tbox() -> tuple[Graph, dict[str, Graph], dict[URIRef, set[str]]]:
    combined = Graph()
    per_file: dict[str, Graph] = {}
    origins: dict[URIRef, set[str]] = defaultdict(set)
    for name in TBOX_FILES:
        one = Graph()
        one.parse(ROOT / "ontology" / name, format="turtle")
        per_file[name] = one
        combined += one
        for subject in set(one.subjects()):
            if isinstance(subject, URIRef):
                origins[subject].add(name)
    return combined, per_file, origins


def vector_definition_markdown(catalog: tuple[TableDef, ...]) -> str:
    tables = tuple(table for table in catalog if table.schema == "vec")
    graph, _, _ = load_tbox()
    all_terms = {
        subject
        for subject in graph.subjects(RDFS.comment, None)
        if isinstance(subject, URIRef) and str(subject).startswith(str(FP))
    }
    bond_graph = Graph()
    for name in ("common.ttl", "bond_kr.ttl"):
        bond_graph += Graph().parse(ROOT / "ontology" / name, format="turtle")
    bond_terms = {
        subject
        for subject in bond_graph.subjects(RDFS.comment, None)
        if isinstance(subject, URIRef) and str(subject).startswith(str(FP))
    }
    sections = automatic_header(
        "VECTORDB DEFINITION V2.0",
        "물리 정의의 정본은 [단일 카탈로그](../../src/kb/catalog_v2.py), "
        "[Vector DDL](../../sql/v2/001_platform_schema.sql), "
        "[임베딩 빌더](../../src/kb/build_vectors_v2.py)입니다.",
    )
    sections.extend(
        [
            "## 이 문서를 읽는 순서",
            "",
            "1. 질의가 스키마 의미 검색인지 문서 근거 검색인지 `라우팅 계약`으로 결정합니다.",
            "2. 해당 테이블의 메타데이터 필드로 RDB/Graph 후보 범위를 제한합니다.",
            "3. cosine 결과는 관련도 후보일 뿐 사실 판정이 아니므로 출처·날짜·인용문을 검증합니다.",
            "4. 답변에는 검색 점수만 제시하지 말고 `근거 반환 계약`의 식별자와 provenance를 보존합니다.",
            "",
            "## 범위와 엔진",
            "",
            "- 엔진: PostgreSQL 17의 pgvector 확장",
            "- 임베딩 계약: CLOVA Studio `bge-m3`, 1024차원(이번 릴리스 신규 호출 없음)",
            "- 거리: cosine distance (`<=>`), 점수 표시는 `1 - distance`",
            "- ANN 인덱스: 유효 벡터가 재사용된 테이블에만 HNSW + `vector_cosine_ops`",
            "- 저장 위치: PostgreSQL `vec` 스키마; 별도 FAISS 운영 경로 없음",
            "- 임베딩 원문과 벡터 산출물은 Git에 커밋하지 않습니다.",
            "- 담당 연산: 자연어↔TBox 용어 grounding, 후보 상품에 한정한 공식 문서 근거 검색",
            "- 비담당 연산: 숫자 정렬·집계는 RDB, 관계 존재와 domain/range 판정은 GraphDB가 담당",
            "",
            "## 읽기 인터페이스",
            "",
            "Vector 검색은 PostgreSQL 읽기 경로를 공유합니다. 이번 릴리스는 테이블과 `vector(1024)` 계약만 배포하며 신규 CLOVA 호출을 하지 않습니다. 동일 `content_hash`·`bge-m3`·1024차원·cutoff/FK 계약의 운영 벡터를 전부 재사용할 수 있을 때만 `ready`, 아니면 세 테이블을 비우고 `pending`으로 둡니다. API나 팀 계정은 vector INSERT/UPDATE와 인덱스 재생성을 할 수 없습니다.",
            "",
            "## 라우팅 계약",
            "",
            "| 사용자 의도 | 검색 테이블 | 필수 사전 필터 | 후속 처리 |",
            "|---|---|---|---|",
            "| ‘안전한’, ‘패시브’, ‘발행사’처럼 물리 컬럼이 불명확 | `vec.schema_terms_all` | 선택적 도메인/TBox 파일 | 반환 `term_uri`를 Graph/RDB 메타데이터에 연결 |",
            "| 채권 용어만 grounding | `vec.bond_schema_terms` | 없음 | 채권 TBox 허용값·속성 검사 |",
            "| 상품 투자전략·위험요인·근거문장 | `vec.document_chunk` | `product_id = ANY(...)`, cutoff | `document_id`로 문서 provenance 결합 |",
            "| 숫자 TOP-N·정확 필터 | 검색하지 않음 | 해당 없음 | RDB로 라우팅 |",
            "| 자회사·편입 다중 홉 | 검색하지 않음 | 해당 없음 | Graph로 후보를 정한 뒤 필요할 때 문서 검색 |",
            "",
            "RDB/Graph의 정규 상품 식별자와 Vector의 `product_id`는 동일 문자열입니다. `document_id`는 `relations.source_document.document_id`와 동일하며, 페이지·인용문은 `vec.document_chunk`가 소유합니다.",
            "",
            "## 인덱스 분리",
            "",
            "| 논리 인덱스 | 물리 테이블 | 현재 정의 행 수 | 용도 | 갱신 조건 |",
            "|---|---|---:|---|---|",
            f"| 채권 schema grounding | `vec.bond_schema_terms` | {len(bond_terms):,} | 채권 질의의 TBox 의미 검색 | `common.ttl` 또는 `bond_kr.ttl` 변경 |",
            f"| 전체 schema grounding | `vec.schema_terms_all` | {len(all_terms):,} | 전 상품군 ontology grounding | TBox 5개 중 하나 변경 |",
            "| content grounding | `vec.document_chunk` | 배포 시 산출 | 문서 근거·인용 검색 | 공식 문서 수집 또는 청크 변경 |",
            "",
            "Ontology Index와 Content Index는 목적·필터·갱신주기가 다르므로 같은 테이블에 섞지 않습니다.",
            "",
            "## 임베딩 텍스트와 식별 규칙",
            "",
            "- TBox term은 `term_uri | rdfs:label | skos:altLabel | rdfs:comment` 순서로 결합합니다.",
            "- 각 TBox term은 `domain_file`과 `property_type`(class/object_property/datatype_property/individual/other)을 별도 메타데이터로 보존합니다.",
            "- 문서 청크는 `document_id`, `product_id`, `page_number`, `citation_text`, `published_at`, `source_url`을 보존합니다.",
            "- `content_hash=SHA-256(원문)`와 `embedding_model`이 같으면 기존 벡터를 재사용합니다.",
            "- 같은 테이블에서 원문 해시 중복을 허용하지 않으며 임베딩 NULL과 1024차원 불일치를 빌드 실패로 처리합니다.",
            "- 문서에는 페이지와 인용문을 저장하지만 별도 문자 offset 컬럼은 아직 구현되지 않았습니다.",
            "- `published_at`이 cutoff를 초과하는 청크가 하나라도 있으면 전체 적재를 중단합니다.",
            "- 자연어 유사도는 관계의 존재, 수치의 참값, 시점 유효성을 증명하지 않습니다. 이 세 가지는 각각 Graph/RDB/날짜 검증으로 확정합니다.",
            "",
            "## 테이블 목록",
            "",
        ]
    )
    sections.extend(table_inventory(tables))
    sections.extend(["## 물리 테이블 상세", ""])
    sections.extend(table_details(tables))
    sections.extend(
        [
            "## 검색 계약",
            "",
            "```sql",
            "SELECT term_uri, label, comment, domain_file, property_type,",
            "       1 - (embedding <=> %(query_embedding)s::vector) AS cosine_similarity",
            "FROM vec.schema_terms_all",
            "ORDER BY embedding <=> %(query_embedding)s::vector",
            "LIMIT %(top_k)s;",
            "```",
            "",
            "상품 후보가 이미 정해진 content 검색은 `product_id = ANY(...)` 조건으로 범위를 먼저 제한합니다.",
            "전용 `tsvector`/GIN 컬럼은 현재 v2 DDL에 없으므로 FTS 하이브리드는 구현 상태로 표기하지 않습니다.",
            "",
            "문서 근거 검색의 안전한 형태입니다.",
            "",
            "```sql",
            "SELECT chunk_id, document_id, product_id, page_number, citation_text,",
            "       published_at, source_url, 1 - (embedding <=> %(query_embedding)s::vector) AS score",
            "FROM vec.document_chunk",
            "WHERE product_id = ANY(%(candidate_product_ids)s)",
            f"  AND published_at <= DATE '{EXTERNAL_CUTOFF.isoformat()}'",
            "ORDER BY embedding <=> %(query_embedding)s::vector",
            "LIMIT %(top_k)s;",
            "```",
            "",
            "## 근거 반환 계약",
            "",
            "- schema grounding: `term_uri`, `label`, `comment`, `domain_file`, cosine score를 반환합니다.",
            "- content grounding: `chunk_id`, `document_id`, `product_id`, `citation_text`, `page_number`, `published_at`, `source_url`, cosine score를 반환합니다.",
            "- 인용문은 저장된 `citation_text` 범위만 사용하며 검색 점수나 모델 추론을 원문 주장처럼 표현하지 않습니다.",
            "- 문서가 없거나 상품 coverage가 `unavailable`이면 ‘위험이 없음’이 아니라 ‘근거 문서 미확보’로 답합니다.",
            "- schema hit만 있는 국내 ETF는 분류 의미까지만 설명하고 투자설명서에 있을 법한 전략 문장을 생성하지 않습니다.",
            "",
            "## Graph → RDB → Vector 결합 예",
            "",
            "1. Graph가 분류·관계 조건으로 `product_id` 후보를 반환합니다.",
            "2. RDB가 동일 ID의 가용 지표만 정렬해 TOP-N을 정합니다.",
            "3. Vector는 TOP-N ID로 `document_chunk`를 제한해 인용 근거를 찾습니다.",
            "4. 통합기는 상품 ID, 수치별 기준일, 문서 발행일을 서로 덮어쓰지 않고 별도 evidence로 유지합니다.",
            "",
            "## 빌드와 검증",
            "",
            "1. TBox 5개와 cutoff 이하 문서 청크를 읽고 원문 해시 중복을 검사합니다.",
            "2. 정식 `vec`에서 같은 모델·원문 해시·1024차원의 임베딩만 조회합니다.",
            "3. 모든 입력을 재사용할 수 있으면 적재하고, 하나라도 없으면 세 테이블을 빈 상태로 둡니다.",
            "4. 유효 벡터가 있는 테이블에만 cosine HNSW 인덱스를 생성합니다.",
            "5. 행 수, embedding NULL, 차원, 중복 해시, HNSW, `vector_status`와 읽기 전용 권한을 검증합니다.",
            "",
            "신규 임베딩 생성은 별도 후속 릴리스입니다. 이번 단계는 `CLOVA_API_KEY`를 요구하거나 호출하지 않으며 빈 검색 결과를 근거 부재로 해석하지 않습니다.",
            "",
        ]
    )
    return "\n".join(sections)


def short_uri(value: object) -> str:
    if isinstance(value, Literal):
        return str(value)
    if not isinstance(value, URIRef):
        return str(value)
    text = str(value)
    prefixes = (
        (str(FP), "fp:"),
        (FPI, "fpi:"),
        (str(RDF), "rdf:"),
        (str(RDFS), "rdfs:"),
        (str(OWL), "owl:"),
        (str(XSD), "xsd:"),
    )
    for namespace, prefix in prefixes:
        if text.startswith(namespace):
            return prefix + text[len(namespace) :]
    return f"<{text}>"


def render_node(graph: Graph, node: object) -> str:
    if not isinstance(node, BNode):
        return short_uri(node)
    for predicate, separator in ((OWL.unionOf, " ∪ "), (OWL.intersectionOf, " ∩ "), (OWL.oneOf, ", ")):
        list_nodes = list(graph.objects(node, predicate))
        if list_nodes:
            values = [render_node(graph, value) for value in Collection(graph, list_nodes[0])]
            return "(" + separator.join(values) + ")"
    on_property = next(iter(graph.objects(node, OWL.onProperty)), None)
    if on_property is not None:
        target = next(iter(graph.objects(node, OWL.someValuesFrom)), None)
        target = target or next(iter(graph.objects(node, OWL.allValuesFrom)), None)
        return f"restriction({render_node(graph, on_property)} → {render_node(graph, target)})"
    return "anonymous class"


def preferred_literal(graph: Graph, subject: URIRef, predicate: URIRef) -> str:
    values = list(graph.objects(subject, predicate))
    korean = [value for value in values if isinstance(value, Literal) and value.language == "ko"]
    return str((korean or values or [""])[0])


def object_list(graph: Graph, subject: URIRef, predicate: URIRef) -> str:
    return ", ".join(sorted(render_node(graph, value) for value in graph.objects(subject, predicate))) or "-"


def graph_definition_markdown() -> str:
    graph, per_file, origins = load_tbox()
    is_fp = lambda value: isinstance(value, URIRef) and str(value).startswith(str(FP))
    classes = sorted({value for value in graph.subjects(RDF.type, OWL.Class) if is_fp(value)}, key=str)
    object_properties = sorted(
        {value for value in graph.subjects(RDF.type, OWL.ObjectProperty) if is_fp(value)}, key=str
    )
    datatype_properties = sorted(
        {value for value in graph.subjects(RDF.type, OWL.DatatypeProperty) if is_fp(value)}, key=str
    )
    declared_terms = set(classes) | set(object_properties) | set(datatype_properties)
    individuals = sorted(
        {
            subject
            for subject, object_ in graph.subject_objects(RDF.type)
            if is_fp(subject) and is_fp(object_) and subject not in declared_terms
        },
        key=lambda value: (object_list(graph, value, RDF.type), str(value)),
    )
    grounding_terms = {subject for subject in graph.subjects(RDFS.comment, None) if is_fp(subject)}
    sections = automatic_header(
        "GRAPHDB DEFINITION V2.0",
        "의미 정의의 정본은 [TBox TTL 5개](../../ontology/)이며 ABox 생성 규칙은 "
        "[Graph 빌더](../../src/kb/build_graph_v2.py)가 소유합니다.",
    )
    sections.extend(
        [
            "## 이 문서를 읽는 순서",
            "",
            "1. `named graph` 범위와 URI 규칙을 먼저 확인합니다.",
            "2. `클래스/속성 정의`의 domain·range와 `통제어휘`로 질의 자체가 유효한지 판정합니다.",
            "3. `관계와 분류 매핑`에서 n-ary 경로와 provenance를 따라 후보 `product_id`를 얻습니다.",
            "4. 숫자 비교가 필요하면 URI의 상품 ID를 RDB로 넘기고, 설명 근거가 필요하면 VectorDB로 넘깁니다.",
            "",
            "## 범위와 엔진",
            "",
            "- 엔진: Oxigraph, SPARQL 1.1 읽기 전용 서비스",
            "- ontology namespace: `fp: <http://mafest.ai/product#>`",
            "- instance namespace: `fpi: <http://mafest.ai/instance/>`",
            "- TBox와 ABox는 별도 named graph로 벌크 로드하며 런타임에 TTL을 파싱하지 않습니다.",
            f"- ABox는 결정적으로 `{EXPECTED_ABOX_TRIPLES:,}` 트리플이며 `graph_manifest.json`의 파일별 SHA-256과 `/health`로 확인합니다.",
            "- 담당 연산: 상품 분류, 편입·자회사·문서 연결, TBox 허용값과 domain/range 검증",
            "- 비담당 연산: AUM·수익률·보수의 정렬/집계는 RDB, 서술 문서의 의미 검색은 VectorDB가 담당",
            "",
            "## 읽기 인터페이스",
            "",
            "Agent는 `POST /db/sparql`로 SPARQL 1.1 `SELECT`/`ASK`/`CONSTRUCT`/`DESCRIBE`만 실행합니다. `INSERT`, `DELETE`, `LOAD` 등 update는 차단되며 Oxigraph 쓰기와 TTL reload는 서버 운영자만 수행합니다.",
            "",
            "## namespace와 named graph 질의 계약",
            "",
            "| prefix | URI | 용도 |",
            "|---|---|---|",
            "| `fp:` | `http://mafest.ai/product#` | TBox 클래스·속성·통제어휘 |",
            "| `fpi:` | `http://mafest.ai/instance/` | ABox 상품·증권·관계·문서 인스턴스 |",
            "| `rdf:` | `http://www.w3.org/1999/02/22-rdf-syntax-ns#` | 타입 |",
            "| `rdfs:` | `http://www.w3.org/2000/01/rdf-schema#` | 라벨·설명·domain·range |",
            "",
            "TBox 검증은 `GRAPH <http://mafest.ai/graph/tbox/{domain}>`, 상품 조회는 `GRAPH <http://mafest.ai/graph/abox/{domain}>`을 명시합니다. 편입·자회사·문서 관계는 `abox/company`에 있으므로 상품 graph와 company graph를 같은 SPARQL에서 조인할 수 있습니다.",
            "",
            "## TBox 요약",
            "",
            f"- 전체 TBox 트리플: {len(graph):,}",
            f"- grounding term(`rdfs:comment` 보유): {len(grounding_terms):,}",
            f"- 클래스: {len(classes):,}",
            f"- ObjectProperty: {len(object_properties):,}",
            f"- DatatypeProperty: {len(datatype_properties):,}",
            f"- 통제어휘 개체: {len(individuals):,}",
            "",
            "| TBox 파일 | named graph | 트리플 | 역할 |",
            "|---|---|---:|---|",
        ]
    )
    roles = {
        "common.ttl": "공통 상품·문서·관계·분류·위험등급 어휘",
        "bond_kr.ttl": "국내채권 속성·등급·만기·담보·발행 어휘",
        "etf_kr.ttl": "국내 ETF/ETN 분류·거래·위험 속성",
        "etf_gl.ttl": "해외 ETF/ETN 전략·설정일·식별 속성",
        "fund_pub.ttl": "공모펀드·클래스·판매·수익률 속성",
    }
    for name in TBOX_FILES:
        domain = Path(name).stem
        sections.append(
            f"| [`{name}`](../../ontology/{name}) | `http://mafest.ai/graph/tbox/{domain}` | "
            f"{len(per_file[name]):,} | {roles[name]} |"
        )
    sections.extend(
        [
            "",
            "## ABox named graph와 원천",
            "",
            "| ABox 파일 | named graph | 주요 원천 | 포함 개체/관계 |",
            "|---|---|---|---|",
            "| `instances_bond_kr.ttl` | `http://mafest.ai/graph/abox/bond_kr` | `enriched.product_master` | `fp:Bond` 상품 |",
            "| `instances_etf_kr.ttl` | `http://mafest.ai/graph/abox/etf_kr` | 상품·`relations.product_classification` | `fp:KoreanETF`, `fp:KoreanETN`, 분류 |",
            "| `instances_etf_gl.ttl` | `http://mafest.ai/graph/abox/etf_gl` | 상품·`relations.product_classification` | `fp:GlobalETF`, `fp:GlobalETN`, 분류 |",
            "| `instances_fund_pub.ttl` | `http://mafest.ai/graph/abox/fund_pub` | 상품·`relations.product_classification` | `fp:PublicFund`, 분류 |",
            "| `instances_company.ttl` | `http://mafest.ai/graph/abox/company` | 문서·편입·자회사·상품문서 관계 | 기업, 증권, 문서, n-ary 관계 |",
            "",
            "사모펀드는 RDB에 보존하지만 현재 ABox 상품 클래스에는 올리지 않습니다. 미확보 관계는 triple 부재를 비보유로 해석하지 않고 `meta.product_coverage`에서 상태를 확인합니다.",
            "",
            "## RDB → ABox 상품 매핑",
            "",
            "| `product_type` | RDF 클래스 | ABox 파일 | URI 규칙 |",
            "|---|---|---|---|",
            "| `BOND` | `fp:Bond` | `instances_bond_kr.ttl` | `fpi:{product_id}` |",
            "| `ETF_KR` | `fp:KoreanETF` | `instances_etf_kr.ttl` | `fpi:{product_id}` |",
            "| `ETN_KR` | `fp:KoreanETN` | `instances_etf_kr.ttl` | `fpi:{product_id}` |",
            "| `ETF_GL` | `fp:GlobalETF` | `instances_etf_gl.ttl` | `fpi:{product_id}` |",
            "| `ETN_GL` | `fp:GlobalETN` | `instances_etf_gl.ttl` | `fpi:{product_id}` |",
            "| `FUND_PUB` | `fp:PublicFund` | `instances_fund_pub.ttl` | `fpi:{product_id}` |",
            "",
            "## 관계와 분류 매핑",
            "",
            "| RDB 원천/유형 | RDF 구조 | 대상 클래스 | provenance |",
            "|---|---|---|---|",
            "| `product_classification.theme` | `fp:relatedToTheme` | `fp:Theme` | 선택적 `fp:hasDocument` |",
            "| `product_classification.sector` | `fp:hasSector` | `fp:Sector` | 선택적 `fp:hasDocument` |",
            "| `product_classification.region` | `fp:hasInvestmentRegion` | `fp:InvestmentRegion` | 선택적 `fp:hasDocument` |",
            "| `product_classification.asset_type` | `fp:hasAssetType` | `fp:AssetType` | 선택적 `fp:hasDocument` |",
            "| `product_holding` | 상품 → `fp:hasHolding` → `fp:Holding` → `fp:holdingSecurity` → 증권 | `fp:Holding` | `fp:weight`, `fp:asOf`, `fp:supportedBy`, `fp:sourceId` |",
            "| `company_subsidiary` | 모기업 → `fp:hasSubsidiary` → `fp:SubsidiaryRelation` → `fp:subsidiaryCompany` → 자회사 | `fp:SubsidiaryRelation` | `fp:ownershipPct`, `fp:asOf`, `fp:supportedBy`, `fp:sourceId` |",
            "| `product_document` | 상품 → `fp:hasDocument` → 문서 | `fp:Document` | 문서명·발행기관·발행일·URL |",
            "",
            "## URI 안정성 규칙",
            "",
            "- 상품: `fpi:{product_id}`",
            "- 분류: `fpi:classification:{classification_type}:{classification_value}`",
            "- 증권/기업: `fpi:security:{security_id}`",
            "- 문서: `fpi:document:{document_id}`",
            "- 편입관계: `fpi:holding:{holding_id}`",
            "- 자회사관계: `fpi:subsidiary:{relation_id}`",
            "- URI 구성요소는 UTF-8 percent encoding하며 입력 정렬과 triple 정렬로 같은 입력에서 byte-for-byte 같은 TTL을 생성합니다.",
            "- `fpi:` 뒤 상품 URI 값은 RDB `enriched.product_master.product_id`와 동일하므로 prefix를 제거해 교차 DB 조인합니다.",
            "",
            "## 클래스 정의",
            "",
            "| 클래스 | 라벨 | 상위 클래스 | disjointWith | 설명 | 원천 TTL |",
            "|---|---|---|---|---|---|",
        ]
    )
    for term in classes:
        sections.append(
            f"| `{short_uri(term)}` | {md(preferred_literal(graph, term, RDFS.label))} | "
            f"{md(object_list(graph, term, RDFS.subClassOf))} | "
            f"{md(object_list(graph, term, OWL.disjointWith))} | "
            f"{md(preferred_literal(graph, term, RDFS.comment))} | "
            f"{md(', '.join(sorted(origins[term])))} |"
        )
    sections.extend(
        [
            "",
            "## ObjectProperty 정의",
            "",
            "| 속성 | 라벨 | domain | range | 설명 | 원천 TTL |",
            "|---|---|---|---|---|---|",
        ]
    )
    for term in object_properties:
        sections.append(
            f"| `{short_uri(term)}` | {md(preferred_literal(graph, term, RDFS.label))} | "
            f"{md(object_list(graph, term, RDFS.domain))} | {md(object_list(graph, term, RDFS.range))} | "
            f"{md(preferred_literal(graph, term, RDFS.comment))} | {md(', '.join(sorted(origins[term])))} |"
        )
    sections.extend(
        [
            "",
            "## DatatypeProperty 정의",
            "",
            "| 속성 | 라벨 | domain | range | 공식 원천 | 설명 | 원천 TTL |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for term in datatype_properties:
        source_table = object_list(graph, term, FP.sourceTable)
        source_column = object_list(graph, term, FP.sourceColumn)
        source = "-" if source_table == source_column == "-" else f"{source_table}.{source_column}"
        sections.append(
            f"| `{short_uri(term)}` | {md(preferred_literal(graph, term, RDFS.label))} | "
            f"{md(object_list(graph, term, RDFS.domain))} | {md(object_list(graph, term, RDFS.range))} | "
            f"{md(source)} | {md(preferred_literal(graph, term, RDFS.comment))} | "
            f"{md(', '.join(sorted(origins[term])))} |"
        )
    sections.extend(
        [
            "",
            "## 통제어휘와 허용값",
            "",
            "질의값 검증은 아래 명명 개체의 존재 여부와 등급/레벨 속성을 사용합니다. 없는 값을 유사값으로 대체하지 않습니다.",
            "",
            "| 유형 | 개체 | 라벨 | 정렬·코드 속성 | 원천 TTL |",
            "|---|---|---|---|---|",
        ]
    )
    for term in individuals:
        value_types = [value for value in graph.objects(term, RDF.type) if is_fp(value)]
        attributes = []
        for predicate, value in graph.predicate_objects(term):
            if is_fp(predicate) and isinstance(value, Literal):
                attributes.append(f"{short_uri(predicate)}={value}")
        sections.append(
            f"| {md(', '.join(sorted(short_uri(value) for value in value_types)))} | "
            f"`{short_uri(term)}` | {md(preferred_literal(graph, term, RDFS.label))} | "
            f"{md(', '.join(sorted(attributes)) or '-')} | {md(', '.join(sorted(origins[term])))} |"
        )
    sections.extend(
        [
            "",
            "## 관계 부재와 ABSTAIN 계약",
            "",
            "- 허용 신용등급 개체가 없으면 `ABSTAIN_INVALID_TAXONOMY`입니다. 예: `AAAA`를 `AAA`로 교정하지 않습니다.",
            "- 질의 주체의 RDF 타입이 속성 domain과 맞지 않으면 `ABSTAIN_DOMAIN_MISMATCH`입니다. 예: ETF가 회사채를 직접 발행했다는 경로를 만들지 않습니다.",
            "- 상품 URI와 공식 식별자가 없으면 `ABSTAIN_ENTITY_NOT_FOUND`이며 이름 유사 매칭으로 새 URI를 만들지 않습니다.",
            "- ABox 관계가 0건이어도 coverage가 미확보면 관계 부재가 아니라 `unknown`입니다. RDB `meta.product_coverage`를 함께 확인합니다.",
            "- Graph는 문서에 뒷받침된 관계만 저장합니다. `fp:supportedBy`가 필요한 관계의 provenance가 없으면 답변 근거로 승격하지 않습니다.",
            "",
            "## 검증과 대표 SPARQL",
            "",
            "- TBox/ABox 10개 TTL 파싱, 클래스·속성 존재, domain/range, n-ary 필수 predicate를 검사합니다.",
            "- 모든 ABox subject URI가 `http://mafest.ai/instance/`로 시작하는지 검사합니다.",
            "- 외부 근거가 없는 편입·자회사·문서 관계는 생성하지 않습니다.",
            "- named graph별 triple 수와 SHA-256은 빌드 시 생성되는 `artifacts/graph_v2/graph_manifest.json`이 정본입니다.",
            "",
            "```sparql",
            "PREFIX fp: <http://mafest.ai/product#>",
            "SELECT ?product ?name ?classification WHERE {",
            "  GRAPH <http://mafest.ai/graph/abox/etf_kr> {",
            "    ?product a fp:KoreanETF ;",
            "             fp:productName ?name ;",
            "             fp:hasAssetType ?classification .",
            "  }",
            "}",
            "LIMIT 100",
            "```",
            "",
            "편입 관계는 n-ary 노드를 경유하고 근거 문서와 기준일을 함께 반환합니다.",
            "",
            "```sparql",
            "PREFIX fp: <http://mafest.ai/product#>",
            "SELECT ?product ?security ?weight ?asOf ?document WHERE {",
            "  GRAPH <http://mafest.ai/graph/abox/company> {",
            "    ?product fp:hasHolding ?holding .",
            "    ?holding fp:holdingSecurity ?security ; fp:asOf ?asOf ; fp:supportedBy ?document .",
            "    OPTIONAL { ?holding fp:weight ?weight }",
            "  }",
            "}",
            "```",
            "",
            "TBox domain 검증은 ABox 결과를 찾기 전에 수행합니다.",
            "",
            "```sparql",
            "PREFIX fp: <http://mafest.ai/product#>",
            "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>",
            "ASK { GRAPH <http://mafest.ai/graph/tbox/common> { fp:issuedBy rdfs:domain ?domain } }",
            "```",
            "",
            "## LLM/Agent 반환 계약",
            "",
            "관계 답변은 시작 엔티티 URI, 사용한 predicate 경로, 도착 엔티티 URI, 관계 기준일, `fp:supportedBy` 문서 URI를 보존합니다. 분류 답변은 분류 개체 URI와 라벨을 둘 다 반환합니다. URI local part를 사람이 읽는 의미로 임의 해석하지 않습니다.",
            "",
        ]
    )
    return "\n".join(sections)
