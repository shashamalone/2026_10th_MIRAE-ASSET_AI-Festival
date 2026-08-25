# -*- coding: utf-8 -*-
"""v2 물리 카탈로그의 단일 정의.

raw 컬럼은 공식 schema XLSX에서 읽고, 파생 테이블은 아래 선언에서 읽는다. SQL DDL,
Markdown/CSV 정의서와 Agent용 JSON이 같은 객체를 소비한다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Iterable

from kb.v2_manifest import SourceInspection


@dataclass(frozen=True)
class ColumnDef:
    name: str
    data_type: str
    nullable: bool
    description: str
    unit: str = ""
    as_of_column: str = ""
    zero_null_rule: str = "빈 값=NULL; 0은 원본 값으로 보존"
    source_priority: str = "주최측(1순위)"
    transform_expression: str = "원본 그대로"
    pk_ordinal: int | None = None
    fk_target: str = ""


@dataclass(frozen=True)
class TableDef:
    schema: str
    name: str
    kind: str
    grain: str
    description: str
    columns: tuple[ColumnDef, ...]
    implementation_status: str = "구현"
    deployment_status: str = "미배포"
    indexes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def fq_name(self) -> str:
        return f"{self.schema}.{self.name}"

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["fq_name"] = self.fq_name
        return value


def c(
    name: str,
    data_type: str,
    description: str,
    *,
    nullable: bool = True,
    unit: str = "",
    as_of: str = "",
    zero: str = "빈 값=NULL; 0은 원본 값으로 보존",
    priority: str = "주최측(1순위)",
    transform: str = "파생",
    pk: int | None = None,
    fk: str = "",
) -> ColumnDef:
    return ColumnDef(
        name,
        data_type,
        nullable,
        description,
        unit,
        as_of,
        zero,
        priority,
        transform,
        pk,
        fk,
    )


METRIC_ZERO = "NULL 또는 0이면 is_available=false; 비교·랭킹 제외 및 '값 없음' 표시"
CODE_ZERO = "빈 값=NULL; 0은 공식 코드/플래그 원문 보존; 의미 추측·임의 필터 금지"
EXTERNAL_PRIORITY = "주최측 축 미존재 시 검증된 외부 원천(2순위)"


STATIC_TABLES: tuple[TableDef, ...] = (
    TableDef(
        "meta",
        "dataset_snapshot",
        "table",
        "데이터셋 빌드 스냅샷",
        "버전·배포일·도메인별 실질 기준일·8개 원천 해시",
        (
            c("snapshot_id", "uuid", "스냅샷 식별자", nullable=False, pk=1),
            c("dataset_version", "text", "데이터 버전", nullable=False),
            c("release_date", "date", "주최측 배포일", nullable=False),
            c("cutoff_date", "date", "외부 근거 허용 상한", nullable=False),
            c("domain_as_of", "jsonb", "도메인별 실질 기준일", nullable=False),
            c("source_files", "jsonb", "원천 파일명·행/열·SHA-256", nullable=False),
            c("source_hash", "text", "전체 원천 manifest SHA-256", nullable=False),
            c("built_at", "timestamptz", "빌드 완료 시각", nullable=False),
        ),
    ),
    TableDef(
        "meta",
        "load_run",
        "table",
        "1회 적재 실행",
        "단계·시작/종료·행 수·검증 결과와 실패 사유",
        (
            c("run_id", "uuid", "적재 실행 식별자", nullable=False, pk=1),
            c("snapshot_id", "uuid", "대상 스냅샷", nullable=False, fk="meta.dataset_snapshot.snapshot_id"),
            c("started_at", "timestamptz", "적재 시작 시각", nullable=False),
            c("finished_at", "timestamptz", "적재 종료 시각"),
            c("status", "text", "running/passed/failed", nullable=False),
            c("phase", "text", "마지막 빌드 단계", nullable=False),
            c("source_rows", "jsonb", "원천 행 수", nullable=False),
            c("loaded_rows", "jsonb", "적재 행 수", nullable=False),
            c("validation_result", "jsonb", "검증 결과", nullable=False),
            c("error_message", "text", "실패 사유"),
        ),
    ),
    TableDef(
        "meta",
        "column_catalog",
        "table",
        "물리 컬럼 1개",
        "공식 설명·타입·단위·기준일·처리 규칙·출처 우선순위",
        (
            c("table_schema", "text", "물리 스키마", nullable=False, pk=1),
            c("table_name", "text", "물리 테이블", nullable=False, pk=2),
            c("ordinal_position", "integer", "컬럼 순번", nullable=False, pk=3),
            c("column_name", "text", "물리 컬럼", nullable=False),
            c("data_type", "text", "PostgreSQL 타입", nullable=False),
            c("is_nullable", "boolean", "NULL 허용 여부", nullable=False),
            c("description", "text", "공식 또는 파생 설명", nullable=False),
            c("unit", "text", "단위; 미표기는 '공식 문서 미표기'", nullable=False),
            c("as_of_column", "text", "실질 기준일 컬럼", nullable=False),
            c("zero_null_rule", "text", "0/결측 처리", nullable=False),
            c("source_priority", "text", "출처 우선순위", nullable=False),
            c("transform_expression", "text", "변환식", nullable=False),
            c("implementation_status", "text", "구현 상태", nullable=False),
            c("deployment_status", "text", "배포 상태", nullable=False),
            c("pk_ordinal", "integer", "PK 내 순번"),
            c("fk_target", "text", "참조 대상 schema.table.column", nullable=False),
            c("grain", "text", "테이블 그레인", nullable=False),
        ),
    ),
    TableDef(
        "meta",
        "product_coverage",
        "table",
        "상품×스냅샷",
        "관계·문서·성과 확보/미확보 상태와 사유",
        (
            c("product_id", "text", "공통 상품 ID", nullable=False, pk=1, fk="enriched.product_master.product_id"),
            c("holdings_status", "text", "available/unavailable/not_applicable", nullable=False),
            c("holdings_reason", "text", "편입내역 상태 사유", nullable=False),
            c("document_status", "text", "available/unavailable", nullable=False),
            c("document_reason", "text", "문서 상태 사유", nullable=False),
            c("performance_status", "text", "available/unavailable", nullable=False),
            c("performance_reason", "text", "성과 상태 사유", nullable=False),
            c("as_of", "date", "커버리지 판정 기준일", nullable=False, as_of="as_of"),
            c("source_document_id", "text", "상태 근거 문서", fk="relations.source_document.document_id"),
        ),
    ),
    TableDef(
        "enriched",
        "product_master",
        "table",
        "공통 상품 1개",
        "전 상품 공통 식별자와 유형·국내/해외·통화·활성 상태",
        (
            c("product_id", "text", "도메인 접두 공통 ID", nullable=False, pk=1),
            c("source_table", "text", "주최측 코드 테이블", nullable=False),
            c("source_key", "text", "원천 상품키", nullable=False),
            c("product_type", "text", "BOND/ETF/ETN/FUND_PUB/FUND_PRIVATE", nullable=False),
            c("market_scope", "text", "KR/GL", nullable=False),
            c("name", "text", "정식 상품명", nullable=False),
            c("short_name", "text", "상품 약칭"),
            c("currency", "text", "원천 통화 코드"),
            c("is_active", "boolean", "명시 만기·상장종료 여부 기반", nullable=False),
            c("active_rule", "text", "활성 판정 근거 규칙", nullable=False),
            c("snapshot_date", "date", "주최측 배포일", nullable=False, as_of="effective_as_of"),
            c("effective_as_of", "date", "도메인 실질 기준일", nullable=False, as_of="effective_as_of"),
        ),
        indexes=("product_type", "name", "source_table,source_key"),
    ),
    TableDef(
        "enriched",
        "bond_kr_product",
        "table",
        "국내채권 pd_no 1개",
        "최신 offer에서 접은 상품 속성과 보수적 구매가능 가정",
        (
            c("product_id", "text", "공통 상품 ID", nullable=False, pk=1, fk="enriched.product_master.product_id"),
            c("pd_no", "text", "채권 상품번호", nullable=False),
            c("name", "text", "상품명", nullable=False),
            c("issuer", "text", "발행사"),
            c("credit_rating", "text", "신용등급 원문"),
            c("currency", "text", "통화 코드"),
            c("issue_date", "date", "발행일"),
            c("maturity_date", "date", "만기일"),
            c("risk_code", "text", "위험등급 코드 원문", zero=CODE_ZERO),
            c("risk_name", "text", "위험등급명"),
            c("is_assumed_purchasable", "boolean", "최신 존재·명시 만기/종료만 제외", nullable=False),
            c("purchasable_rule", "text", "BUYABLE_QUANTITY 미사용 판정 규칙", nullable=False),
            c("effective_as_of", "date", "채권 정보 기준일", nullable=False, as_of="effective_as_of"),
        ),
    ),
    TableDef(
        "enriched",
        "bond_kr_offer",
        "table",
        "채권×시장×기준일×판매 LOT",
        "채권 수익률·가격·판매 LOT; BUYABLE_QUANTITY는 저장 전용",
        (
            c("pd_no", "text", "상품번호", nullable=False, pk=1),
            c("exchange_market", "text", "시장 원문", nullable=False, pk=2),
            c("info_base_dt", "date", "정보 기준일", nullable=False, pk=3, as_of="info_base_dt"),
            c("info_seq", "integer", "정보 순번", nullable=False, pk=4),
            c("product_id", "text", "공통 상품 ID", nullable=False, fk="enriched.product_master.product_id"),
            c("applied_yield", "double precision", "민평수익률", unit="percent", zero=METRIC_ZERO),
            c("after_tax_yield", "double precision", "개인 세후 운용수익률", unit="percent", zero=METRIC_ZERO),
            c("buy_yield", "double precision", "매수수익률", unit="percent", zero=METRIC_ZERO),
            c("sale_yield_base_dt", "date", "수익률 기준일", as_of="sale_yield_base_dt"),
            c("eval_price", "double precision", "평가가격", zero=METRIC_ZERO),
            c("trade_price", "double precision", "거래가격", zero=METRIC_ZERO),
            c("buyable_quantity", "numeric(26,8)", "저장 전용 매수가능수량; 판매 판정 사용 금지", zero="원본 0/NULL 보존; 판정·필터·정렬 사용 금지"),
        ),
    ),
    TableDef(
        "enriched",
        "etf_kr",
        "table",
        "국내 ETF 1개",
        "pd_grp_no='ETF'만 명시 분리",
        (
            c("product_id", "text", "공통 상품 ID", nullable=False, pk=1, fk="enriched.product_master.product_id"),
            c("pd_itm_no", "text", "원천 상품번호", nullable=False),
            c("name", "text", "상품명", nullable=False),
            c("ticker", "text", "국내 티커"),
            c("isin", "text", "ISIN"),
            c("manager", "text", "운용사"),
            c("base_index", "text", "기초지수"),
            c("currency", "text", "통화 코드"),
            c("listing_date", "date", "상장일"),
            c("delisting_date", "date", "상장종료일"),
            c("effective_as_of", "date", "실질 기준일", nullable=False, as_of="effective_as_of"),
        ),
    ),
    TableDef(
        "enriched",
        "etf_gl",
        "table",
        "해외 ETF 1개",
        "pd_grp_no='ETF'만 명시 분리",
        (
            c("product_id", "text", "공통 상품 ID", nullable=False, pk=1, fk="enriched.product_master.product_id"),
            c("pd_itm_no", "text", "원천 RIC 상품번호", nullable=False),
            c("name", "text", "상품명", nullable=False),
            c("ticker", "text", "티커"),
            c("isin", "text", "ISIN(비유일 보조 식별자)"),
            c("manager", "text", "운용사"),
            c("base_index", "text", "기초지수; sentinel은 NULL"),
            c("currency", "text", "거래 통화"),
            c("inception_date", "date", "설정일", as_of="pd_lstg_dt", transform="yyyymmdd(pd_lstg_dt); 상장일로 해석 금지"),
            c("effective_as_of", "date", "실질 기준일", nullable=False, as_of="effective_as_of"),
        ),
    ),
    TableDef(
        "enriched",
        "etn_kr",
        "table",
        "국내 ETN 1개",
        "국내 ETF 원천의 pd_grp_no='ETN' 분리",
        (
            c("product_id", "text", "공통 상품 ID", nullable=False, pk=1, fk="enriched.product_master.product_id"),
            c("pd_itm_no", "text", "원천 상품번호", nullable=False),
            c("name", "text", "상품명", nullable=False),
            c("ticker", "text", "국내 티커"),
            c("isin", "text", "ISIN"),
            c("issuer", "text", "발행사"),
            c("currency", "text", "통화 코드"),
            c("listing_date", "date", "상장일"),
            c("delisting_date", "date", "상장종료일"),
            c("effective_as_of", "date", "실질 기준일", nullable=False, as_of="effective_as_of"),
        ),
    ),
    TableDef(
        "enriched",
        "etn_gl",
        "table",
        "해외 ETN 1개",
        "해외 ETF 원천의 pd_grp_no='ETN' 분리",
        (
            c("product_id", "text", "공통 상품 ID", nullable=False, pk=1, fk="enriched.product_master.product_id"),
            c("pd_itm_no", "text", "원천 RIC 상품번호", nullable=False),
            c("name", "text", "상품명", nullable=False),
            c("ticker", "text", "티커"),
            c("isin", "text", "ISIN"),
            c("issuer", "text", "발행사"),
            c("currency", "text", "거래 통화"),
            c("inception_date", "date", "설정일", as_of="pd_lstg_dt", transform="yyyymmdd(pd_lstg_dt); 상장일로 해석 금지"),
            c("effective_as_of", "date", "실질 기준일", nullable=False, as_of="effective_as_of"),
        ),
    ),
    TableDef(
        "enriched",
        "fund",
        "table",
        "펀드 itm_no 1개",
        "공모·사모 전체 보존; fund_pub 뷰에서 공모만 노출",
        (
            c("product_id", "text", "공통 상품 ID", nullable=False, pk=1, fk="enriched.product_master.product_id"),
            c("itm_no", "text", "펀드 상품번호", nullable=False),
            c("name", "text", "펀드명", nullable=False),
            c("short_name", "text", "펀드 약칭"),
            c("offering_type", "text", "공모/사모 원문", nullable=False),
            c("manager_org_code", "text", "운용사 기관코드"),
            c("benchmark", "text", "벤치마크"),
            c("currency", "text", "통화 코드"),
            c("effective_as_of", "date", "성과 실질 기준일", nullable=False, as_of="effective_as_of"),
        ),
    ),
    TableDef(
        "enriched",
        "product_metric",
        "table",
        "상품×지표×기준일×출처×방법",
        "AUM·수익률·보수 등 공통 지표와 값 미확보 상태",
        (
            c("metric_id", "text", "결정적 지표 ID", nullable=False, pk=1),
            c("product_id", "text", "공통 상품 ID", nullable=False, fk="enriched.product_master.product_id"),
            c("metric_code", "text", "AUM/RETURN_1Y/EXPENSE_RATIO 등", nullable=False),
            c("value", "numeric", "측정값; 0도 보존", zero=METRIC_ZERO),
            c("unit", "text", "KRW/USD/percent 등", nullable=False),
            c("as_of", "date", "측정 기준일; 없으면 지표 미확보", as_of="as_of"),
            c("source", "text", "주최측 코드 또는 검증된 외부 원천", nullable=False),
            c("source_column", "text", "직접 출처 컬럼/필드", nullable=False),
            c("method", "text", "raw/calculated_total_return 등", nullable=False),
            c("is_available", "boolean", "랭킹·비교 사용 가능 여부", nullable=False),
            c("unavailable_reason", "text", "NULL/0/권한 미확보 등 사유"),
            c("source_priority", "smallint", "1=주최측, 2=외부", nullable=False),
        ),
        indexes=("product_id,metric_code", "metric_code,value DESC WHERE is_available"),
    ),
    TableDef(
        "enriched",
        "security_master",
        "table",
        "증권 1개",
        "편입증권·기업의 통합 식별자",
        (
            c("security_id", "text", "결정적 증권 ID", nullable=False, pk=1),
            c("display_name", "text", "표시명", nullable=False),
            c("security_type", "text", "equity/bond/company/unknown", nullable=False),
            c("issuer_name", "text", "발행사명"),
            c("country_code", "text", "국가 코드"),
        ),
    ),
    TableDef(
        "enriched",
        "security_identifier",
        "table",
        "증권×식별자 유형×값",
        "ISIN·국내 티커·RIC·Bloomberg 표기 통합",
        (
            c("security_id", "text", "증권 ID", nullable=False, pk=1, fk="enriched.security_master.security_id"),
            c("id_type", "text", "ISIN/KR_TICKER/RIC/BLOOMBERG", nullable=False, pk=2),
            c("id_value", "text", "식별자 원문", nullable=False, pk=3),
            c("is_primary", "boolean", "해당 유형의 대표 식별자", nullable=False),
        ),
        indexes=("id_type,id_value",),
    ),
    TableDef(
        "relations",
        "source_document",
        "table",
        "외부 근거 문서 1개",
        "문서명·발행기관·발행일·URL·원천 해시",
        (
            c("document_id", "text", "결정적 문서 ID", nullable=False, pk=1),
            c("title", "text", "문서명", nullable=False, priority=EXTERNAL_PRIORITY),
            c("publisher", "text", "발행기관", nullable=False, priority=EXTERNAL_PRIORITY),
            c("published_at", "date", "발행일(상한 검증)", nullable=False, as_of="published_at", priority=EXTERNAL_PRIORITY),
            c("url", "text", "공식 원문 URL", nullable=False, priority=EXTERNAL_PRIORITY),
            c("source_hash", "text", "원문 SHA-256", nullable=False, priority=EXTERNAL_PRIORITY),
            c("source_type", "text", "DART/manager/policy/LSEG", nullable=False, priority=EXTERNAL_PRIORITY),
            c("as_of", "date", "문서가 증명하는 기준일", as_of="as_of", priority=EXTERNAL_PRIORITY),
            c("ingested_at", "timestamptz", "수집 시각", nullable=False, priority=EXTERNAL_PRIORITY),
        ),
    ),
    TableDef(
        "relations",
        "product_holding",
        "table",
        "상품×편입증권×기준일×문서",
        "ETF·펀드 공통 편입관계; 미확보는 coverage로 분리",
        (
            c("holding_id", "text", "결정적 관계 ID", nullable=False, pk=1),
            c("product_id", "text", "상품 ID", nullable=False, fk="enriched.product_master.product_id"),
            c("security_id", "text", "편입증권 ID", nullable=False, fk="enriched.security_master.security_id"),
            c("weight", "numeric", "편입비중", unit="percent", zero=METRIC_ZERO),
            c("unit", "text", "비중 단위", nullable=False),
            c("as_of", "date", "편입 기준일", nullable=False, as_of="as_of", priority=EXTERNAL_PRIORITY),
            c("source_document_id", "text", "직접 근거 문서", nullable=False, fk="relations.source_document.document_id", priority=EXTERNAL_PRIORITY),
            c("source", "text", "운용사/DART 원천", nullable=False, priority=EXTERNAL_PRIORITY),
        ),
        indexes=("product_id,as_of", "security_id,as_of"),
    ),
    TableDef(
        "relations",
        "product_classification",
        "table",
        "상품×분류 유형×값×기준일",
        "상품↔테마·섹터·지역 관계",
        (
            c("classification_id", "text", "결정적 관계 ID", nullable=False, pk=1),
            c("product_id", "text", "상품 ID", nullable=False, fk="enriched.product_master.product_id"),
            c("classification_type", "text", "theme/sector/region", nullable=False),
            c("classification_value", "text", "원천 분류값", nullable=False),
            c("as_of", "date", "분류 기준일", nullable=False, as_of="as_of"),
            c("source_document_id", "text", "직접 근거 문서", fk="relations.source_document.document_id"),
            c("source", "text", "원천", nullable=False),
        ),
    ),
    TableDef(
        "relations",
        "company_subsidiary",
        "table",
        "기업×자회사×기준일×문서",
        "기업↔자회사 n-ary 관계와 지분율",
        (
            c("relation_id", "text", "결정적 관계 ID", nullable=False, pk=1),
            c("parent_security_id", "text", "모회사 ID", nullable=False, fk="enriched.security_master.security_id"),
            c("child_security_id", "text", "자회사 ID", nullable=False, fk="enriched.security_master.security_id"),
            c("ownership_pct", "numeric", "지분율", unit="percent", zero=METRIC_ZERO),
            c("as_of", "date", "공시 기준일", nullable=False, as_of="as_of", priority=EXTERNAL_PRIORITY),
            c("source_document_id", "text", "DART 근거 문서", nullable=False, fk="relations.source_document.document_id", priority=EXTERNAL_PRIORITY),
            c("source", "text", "원천", nullable=False, priority=EXTERNAL_PRIORITY),
        ),
    ),
    TableDef(
        "relations",
        "product_document",
        "table",
        "상품×문서×관계유형",
        "상품과 투자설명서·보고서·구성내역 연결",
        (
            c("product_id", "text", "상품 ID", nullable=False, pk=1, fk="enriched.product_master.product_id"),
            c("document_id", "text", "문서 ID", nullable=False, pk=2, fk="relations.source_document.document_id"),
            c("relation_type", "text", "prospectus/report/holdings", nullable=False, pk=3),
        ),
    ),
    TableDef(
        "vec",
        "bond_schema_terms",
        "table",
        "채권 TBox grounding term 1개",
        "common+bond TBox 주석 130행 CLOVA bge-m3 임베딩",
        (
            c("term_uri", "text", "TBox URI", nullable=False, pk=1),
            c("label", "text", "라벨", nullable=False),
            c("comment", "text", "설명", nullable=False),
            c("alt_labels", "text[]", "대체 표기", nullable=False),
            c("content", "text", "임베딩 원문", nullable=False),
            c("content_hash", "text", "원문 SHA-256", nullable=False),
            c("embedding_model", "text", "bge-m3", nullable=False),
            c("embedding_dim", "smallint", "1024", nullable=False),
            c("embedding", "vector(1024)", "CLOVA 임베딩", nullable=False),
        ),
        indexes=("embedding vector_cosine_ops (HNSW)", "content_hash,embedding_model"),
    ),
    TableDef(
        "vec",
        "schema_terms_all",
        "table",
        "전체 TBox grounding term 1개",
        "5개 TBox 주석 189행 CLOVA bge-m3 임베딩",
        (
            c("term_uri", "text", "TBox URI", nullable=False, pk=1),
            c("label", "text", "라벨", nullable=False),
            c("comment", "text", "설명", nullable=False),
            c("alt_labels", "text[]", "대체 표기", nullable=False),
            c("content", "text", "임베딩 원문", nullable=False),
            c("content_hash", "text", "원문 SHA-256", nullable=False),
            c("embedding_model", "text", "bge-m3", nullable=False),
            c("embedding_dim", "smallint", "1024", nullable=False),
            c("embedding", "vector(1024)", "CLOVA 임베딩", nullable=False),
        ),
        indexes=("embedding vector_cosine_ops (HNSW)", "content_hash,embedding_model"),
    ),
    TableDef(
        "vec",
        "document_chunk",
        "table",
        "문서 청크 1개",
        "문서·상품·페이지·발행일·인용 위치가 있는 콘텐츠 임베딩",
        (
            c("chunk_id", "text", "결정적 청크 ID", nullable=False, pk=1),
            c("document_id", "text", "근거 문서 ID", nullable=False, fk="relations.source_document.document_id"),
            c("product_id", "text", "연결 상품 ID", fk="enriched.product_master.product_id"),
            c("page_number", "integer", "원문 페이지"),
            c("citation_text", "text", "인용 위치/문장", nullable=False),
            c("chunk_text", "text", "임베딩 원문", nullable=False),
            c("published_at", "date", "문서 발행일", nullable=False, as_of="published_at", priority=EXTERNAL_PRIORITY),
            c("source_url", "text", "원문 URL", nullable=False, priority=EXTERNAL_PRIORITY),
            c("content_hash", "text", "원문 SHA-256", nullable=False),
            c("embedding_model", "text", "bge-m3", nullable=False),
            c("embedding_dim", "smallint", "1024", nullable=False),
            c("embedding", "vector(1024)", "CLOVA 임베딩", nullable=False),
        ),
        indexes=("embedding vector_cosine_ops (HNSW)", "document_id", "product_id"),
    ),
)


VIEW_DEFINITIONS = (
    {"name": "raw.prbd01n001", "source": "raw.bond_kr_master", "purpose": "코드명 호환"},
    {"name": "raw.pref01n001", "source": "raw.etf_kr_master", "purpose": "코드명 호환"},
    {"name": "raw.pref02n001", "source": "raw.etf_gl_master", "purpose": "코드명 호환"},
    {"name": "raw.prfd01n001", "source": "raw.fund_pub_master", "purpose": "코드명 호환"},
    {"name": "enriched.fund_pub", "source": "enriched.fund", "filter": "offering_type='공모'"},
    {"name": "core.bond_kr", "source": "enriched.bond_kr_product", "purpose": "Agent 호환"},
    {"name": "core.etf_kr", "source": "enriched.etf_kr", "purpose": "Agent 호환"},
    {"name": "core.etf_gl", "source": "enriched.etf_gl", "purpose": "Agent 호환"},
    {"name": "core.fund_pub", "source": "enriched.fund_pub", "purpose": "Agent 호환"},
    {"name": "core.etn", "source": "enriched.etn_kr UNION ALL enriched.etn_gl", "purpose": "Agent 호환"},
    {"name": "enriched.product_search", "source": "product_master+product_metric+product_coverage", "kind": "materialized view"},
)


def raw_zero_rule(name: str, description: str) -> str:
    lowered = f"{name} {description}".lower()
    metric_words = (
        "yield",
        "_rt",
        "_r",
        "price",
        "amt",
        "aum",
        "nav",
        "수익률",
        "금리",
        "비율",
        "보수",
        "가격",
        "금액",
    )
    if any(word in lowered for word in metric_words):
        return "빈 값=NULL; 0은 raw에 보존하되 측정값 비교·랭킹에서는 값 없음"
    if name.endswith(("_cd", "_tcd", "_gcd", "_yn", "_no")):
        return CODE_ZERO
    return "빈 값=NULL; 0은 원본 값으로 보존"


def raw_tables(inspections: Iterable[SourceInspection]) -> tuple[TableDef, ...]:
    tables: list[TableDef] = []
    for item in inspections:
        pk_order = {name: index for index, name in enumerate(item.spec.primary_key, 1)}
        as_of = ",".join(item.spec.effective_as_of_columns)
        columns = tuple(
            ColumnDef(
                name=column.name,
                data_type=column.data_type,
                nullable=(
                    column.nullable
                    or item.null_counts[column.ordinal - 1] > 0
                ) and column.name not in pk_order,
                description=(
                    column.description
                    + (
                        f" [공식 Nullable=NO이나 정본 NULL {item.null_counts[column.ordinal - 1]:,}건을 손실 없이 허용]"
                        if not column.nullable
                        and item.null_counts[column.ordinal - 1] > 0
                        and column.name not in pk_order
                        else ""
                    )
                ),
                unit="공식 문서 미표기",
                as_of_column=as_of if column.name not in item.spec.effective_as_of_columns else column.name,
                zero_null_rule=raw_zero_rule(column.name, column.description),
                source_priority="주최측(1순위)",
                transform_expression="승인 CSV 값 그대로; 공백만 NULL; PK는 NOT NULL",
                pk_ordinal=pk_order.get(column.name),
            )
            for column in item.columns
        )
        tables.append(
            TableDef(
                schema="raw",
                name=item.spec.raw_table,
                kind="table",
                grain=item.spec.grain,
                description=f"{item.spec.code} 공식 원천 {item.row_count:,}행",
                columns=columns,
                indexes=(",".join(item.spec.primary_key),),
            )
        )
    return tuple(tables)


def build_catalog(inspections: Iterable[SourceInspection]) -> tuple[TableDef, ...]:
    return raw_tables(inspections) + STATIC_TABLES
