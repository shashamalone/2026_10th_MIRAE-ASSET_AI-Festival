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
    EXTERNAL_CUTOFF,
    RELEASE_DATE,
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
        "자동 생성 파일입니다. 직접 편집하지 말고 `python src/kb/build_catalog_v2.py`를 실행합니다.",
        source_text,
        "",
        f"- 데이터 버전: `{DATASET_VERSION}`",
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
            "## 범위와 엔진",
            "",
            "- 엔진: PostgreSQL 17",
            "- 물리 스키마: `meta`, `raw`, `enriched`, `relations`",
            "- 공개 호환 스키마: `core` 및 코드명 `raw.*` 뷰",
            "- stage 배포: 동일 DB의 `*_next`에서 검증 후 트랜잭션으로 정식 이름에 승격",
            "- API 계정: `agent_reader`; 읽기 전용, statement timeout 2초, 최대 100행",
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
            f"| `raw` | 승인 CSV의 공식 컬럼·타입·grain 보존 | {counts['raw']} | {view_counts['raw']} |",
            f"| `enriched` | 공통 상품·지표·식별자와 도메인별 1상품 grain | {counts['enriched']} | {view_counts['enriched']} |",
            f"| `relations` | 문서·편입·분류·자회사·상품문서 관계 | {counts['relations']} | {view_counts['relations']} |",
            f"| `core` | 기존 Agent 호환 읽기 뷰 | {counts['core']} | {view_counts['core']} |",
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
            "- 펀드는 `(itm_no, prfd_attr_cd)` 원천 grain을 보존하고 상품 비교는 `itm_no` 대표행으로 중복 제거합니다.",
            "- 지표의 0/NULL/기준일 미확보는 `is_available=false`이며 랭킹과 비교에서 제외합니다.",
            "- `product_coverage.unavailable`은 관계 미확보이며 ‘보유하지 않음’을 뜻하지 않습니다.",
            "- 주최측에 존재하는 지표 축이 우선이며 축 자체가 없을 때만 cutoff를 통과한 외부값을 사용합니다.",
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
            "1. 승인 manifest, SHA-256, 행·열, 헤더, PK, cutoff를 검사합니다.",
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
            "## 범위와 엔진",
            "",
            "- 엔진: PostgreSQL 17의 pgvector 확장",
            "- 임베딩: CLOVA Studio `bge-m3`, 1024차원",
            "- 거리: cosine distance (`<=>`), 점수 표시는 `1 - distance`",
            "- ANN 인덱스: HNSW + `vector_cosine_ops`",
            "- 저장 위치: PostgreSQL `vec` 스키마; 별도 FAISS 운영 경로 없음",
            "- 임베딩 원문과 벡터 산출물은 Git에 커밋하지 않습니다.",
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
            "- 문서 청크는 `document_id`, `product_id`, `page_number`, `citation_text`, `published_at`, `source_url`을 보존합니다.",
            "- `content_hash=SHA-256(원문)`와 `embedding_model`이 같으면 기존 벡터를 재사용합니다.",
            "- 같은 테이블에서 원문 해시 중복을 허용하지 않으며 임베딩 NULL과 1024차원 불일치를 빌드 실패로 처리합니다.",
            "- 문서에는 페이지와 인용문을 저장하지만 별도 문자 offset 컬럼은 아직 구현되지 않았습니다.",
            "- `published_at`이 cutoff를 초과하는 청크가 하나라도 있으면 전체 적재를 중단합니다.",
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
            "SELECT term_uri, label, comment,",
            "       1 - (embedding <=> %(query_embedding)s::vector) AS cosine_similarity",
            "FROM vec.schema_terms_all",
            "ORDER BY embedding <=> %(query_embedding)s::vector",
            "LIMIT %(top_k)s;",
            "```",
            "",
            "상품 후보가 이미 정해진 content 검색은 `product_id = ANY(...)` 조건으로 범위를 먼저 제한합니다.",
            "전용 `tsvector`/GIN 컬럼은 현재 v2 DDL에 없으므로 FTS 하이브리드는 구현 상태로 표기하지 않습니다.",
            "",
            "## 빌드와 검증",
            "",
            "1. TBox 5개와 cutoff 이하 문서 청크를 읽고 원문 해시 중복을 검사합니다.",
            "2. 기존 `vec_next`와 정식 `vec`에서 같은 모델·원문 해시의 임베딩 캐시를 조회합니다.",
            "3. 누락된 원문만 CLOVA에 보내고 결과가 정확히 1024차원인지 확인합니다.",
            "4. 세 테이블을 upsert한 뒤 cosine HNSW 인덱스를 생성합니다.",
            "5. 행 수, embedding NULL, 차원, 중복 해시, HNSW 인덱스 3개를 검증합니다.",
            "",
            "필수 비밀값은 `CLOVA_API_KEY`이며 host는 `CLOVA_HOST`로 주입합니다. 비밀값은 문서·로그·DB에 저장하지 않습니다.",
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
            "## 범위와 엔진",
            "",
            "- 엔진: Oxigraph, SPARQL 1.1 읽기 전용 서비스",
            "- ontology namespace: `fp: <http://mafest.ai/product#>`",
            "- instance namespace: `fpi: <http://mafest.ai/instance/>`",
            "- TBox와 ABox는 별도 named graph로 벌크 로드하며 런타임에 TTL을 파싱하지 않습니다.",
            "- ABox 트리플 수는 입력 관계 데이터에 따라 달라지므로 정의서에 고정하지 않고 `graph_manifest.json`과 `/health`로 확인합니다.",
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
        ]
    )
    return "\n".join(sections)
