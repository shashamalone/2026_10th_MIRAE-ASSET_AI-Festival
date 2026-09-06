"""
타입이 있는 GraphLogicalPlan 검증·SPARQL 컴파일.

팀원의 gragh-test 노트북 `tools/graph_plan.py`(셀 37)를 이식했다.
`validate_graph_plan`/`compile_graph_plan`/`subsidiary_relation_plan`/
`subsidiary_holding_etf_plan`만 옮겼다 - `tools/rdb.py`에 의존하는
`build_etf_rdb_handoff`/`execute_etf_rdb_handoff`/`_order_binding`은 제외했다
(우리 프로젝트의 Graph->RDB 핸드오프는 팀원의 별도 SQL 컴파일러가 아니라
기존 RDB 파이프라인에 조건 하나를 주입하는 방식을 쓴다 - nodes.py의
`rdb_search_node` 참고).
"""
from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass
from functools import lru_cache

from rdflib import Literal, RDFS, URIRef

from tools.graph_schema import FP, SchemaCatalog, SchemaFragment, compact_uri, expand_uri


DATA_CUTOFF = "2026-08-24"
MAX_GRAPH_STEPS = 8
MAX_QUERY_LIMIT = 500
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,39}$")
# 분류 개체(fp:InvestmentRegion·fp:AssetType·fp:RiskGrade·fp:Theme …)에는 datatype
# property가 없다. "투자지역은?" 류의 답은 그 개체의 rdfs:label이므로 output property로
# 허용하되 TBox 애노테이션이 없어 provenance 항목으로는 넣지 않는다.
LABEL_PROPERTY = str(RDFS.label)
_EVIDENCE_CLASSES = {
    FP + "Holding", FP + "MetricSnapshot", FP + "SubsidiaryRelation", FP + "Risk",
}
_EVIDENCE_PROPERTIES = {
    "as_of": FP + "asOf",
    "source": FP + "sourceId",
    "document": FP + "supportedBy",
    "document_title": FP + "documentTitle",
    "document_publisher": FP + "documentPublisher",
    "document_date": FP + "documentPublishedDate",
    "document_quote": FP + "documentQuote",
}


@dataclass(frozen=True)
class PlanValidation:
    errors: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict:
        return {"status": "PASS" if self.ok else "ABSTAIN", "errors": list(self.errors)}


@dataclass(frozen=True)
class CompiledGraphQuery:
    sparql: str
    columns: tuple[str, ...]
    evidence_columns: tuple[str, ...]
    # (curie, sourceTable, sourceColumn). row-level evidence가 없는 분류형 조회의
    # 근거는 TBox 애노테이션 + 적재 스냅샷 기준일이다.
    tbox_provenance: tuple[tuple[str, str, str], ...] = ()


def _uri(value: str) -> str:
    return str(expand_uri(str(value)))


def _term(uri: str) -> str:
    if not uri.startswith(("http://", "https://")) or ">" in uri:
        raise ValueError(f"안전하지 않은 URI: {uri!r}")
    return URIRef(uri).n3()


@lru_cache(maxsize=512)
def _populated(uri: str) -> bool:
    """이 속성이 ABox에 한 건이라도 있는가.

    TBox에는 선언됐지만 store에 값이 0건인 속성이 있다. 이런 속성을 output으로
    쓰면 형태가 멀쩡한 plan이 조용히 0행이 되고, LLM은 오류를 못 받아 고칠
    기회가 없다. predicate 인덱스 조회라 비용은 무시할 수준이고 프로세스당
    1회만 돈다."""
    from agent.graph_logic import graph_engine  # 지연 import — 순수 TBox 테스트는 store가 필요 없다.
    try:
        return bool(graph_engine.sparql(f"SELECT ?o WHERE {{ ?s {_term(uri)} ?o }} LIMIT 1"))
    except Exception:
        return True           # store를 못 읽으면 TBox 판정만으로 통과시킨다.


def _node_map(plan: dict) -> dict[str, str]:
    return {str(node.get("id")): _uri(node.get("class_uri", ""))
            for node in plan.get("nodes") or [] if isinstance(node, dict)}


def validate_graph_plan(plan: dict, entity: dict, fragment: SchemaFragment,
                        catalog: SchemaCatalog) -> PlanValidation:
    errors = []
    if not isinstance(plan, dict):
        return PlanValidation(("GraphLogicalPlan이 JSON object가 아닙니다",))
    nodes = plan.get("nodes") or []
    edges = plan.get("edges") or []
    outputs = plan.get("outputs") or []
    if not nodes:
        errors.append("nodes가 비어 있습니다")
    # seed 하나의 속성만 묻는 질문(투자지역·위험등급 등)은 관계가 없다. 이 형태에
    # edge를 요구하면 LLM이 없는 관계를 지어내다 domain 위반으로 끝난다(실측).
    if not edges and not (len(nodes) == 1 and outputs):
        errors.append("edges가 비어 있습니다")
    if not outputs:
        # 투영할 변수가 없으면 SPARQL이 `SELECT WHERE`가 되어 파서에서 터진다(실측).
        errors.append("outputs가 비어 있습니다")
    elif all(o.get("node") == "seed" and _uri(o.get("property", "")) == LABEL_PROPERTY
             for o in outputs if isinstance(o, dict)):
        # seed 이름은 사용자가 이미 말한 값이다. 이것만 돌려주면 답이 아니고 TBox
        # provenance도 없어 무근거가 된다. 관계형 질문을 seed 1개로 접는 실패 모드.
        errors.append("seed의 rdfs:label만으로는 답이 되지 않습니다. "
                      "질문이 요구하는 다른 개체를 node·edge로 잡고 그 값을 outputs에 넣으십시오")
    if len(edges) > MAX_GRAPH_STEPS:
        errors.append(f"Graph edge 상한 {MAX_GRAPH_STEPS}개 초과")

    ids, node_types = [], {}
    for node in nodes:
        node_id = str(node.get("id", ""))
        if not _ID.fullmatch(node_id):
            errors.append(f"허용하지 않는 node id: {node_id!r}")
            continue
        if node_id in ids:
            errors.append(f"중복 node id: {node_id}")
        ids.append(node_id)
        cls = _uri(node.get("class_uri", ""))
        if cls not in catalog.classes:
            errors.append(f"존재하지 않는 class: {compact_uri(cls)}")
        elif cls not in set(fragment.classes):
            errors.append(f"schema fragment 밖 class: {compact_uri(cls)}")
        node_types[node_id] = cls
    if "seed" not in node_types:
        errors.append("해소된 엔티티를 묶을 seed node가 없습니다")
    elif entity.get("class_uri") and not catalog.compatible(
            entity["class_uri"], {node_types["seed"]}):
        errors.append("seed class와 해소된 엔티티 class가 호환되지 않습니다: "
                      f"{compact_uri(entity['class_uri'])} != {compact_uri(node_types['seed'])}")

    allowed_properties = fragment.property_uris
    adjacency = defaultdict(set)
    for edge in edges:
        subject, obj = edge.get("subject"), edge.get("object")
        predicate = _uri(edge.get("predicate", ""))
        if subject not in node_types or obj not in node_types:
            errors.append(f"edge가 미등록 node를 참조합니다: {subject} -> {obj}")
            continue
        signature = catalog.properties.get(predicate)
        if not signature:
            errors.append(f"존재하지 않는 predicate: {compact_uri(predicate)}")
            continue
        if predicate not in allowed_properties:
            errors.append(f"schema fragment 밖 predicate: {compact_uri(predicate)}")
        if signature.kind != "object":
            errors.append(f"edge predicate는 ObjectProperty여야 합니다: {compact_uri(predicate)}")
            continue
        if not catalog.compatible(node_types[subject], set(signature.domains)):
            errors.append(
                f"domain 위반: {subject}({compact_uri(node_types[subject])}) --"
                f"{compact_uri(predicate)}-->; 허용 domain="
                f"{[compact_uri(x) for x in signature.domains]}"
            )
        if not catalog.compatible(node_types[obj], set(signature.ranges)):
            errors.append(
                f"range 위반: --{compact_uri(predicate)}--> "
                f"{obj}({compact_uri(node_types[obj])}); 허용 range="
                f"{[compact_uri(x) for x in signature.ranges]}"
            )
        adjacency[subject].add(obj)
        adjacency[obj].add(subject)

    if "seed" in node_types:
        reached, queue = {"seed"}, deque(["seed"])
        while queue:
            current = queue.popleft()
            for nxt in adjacency[current] - reached:
                reached.add(nxt)
                queue.append(nxt)
        disconnected = sorted(set(node_types) - reached)
        if disconnected:
            errors.append(f"seed와 연결되지 않은 node: {disconnected}")

    aliases = set(node_types)
    for output in outputs:
        node_id = output.get("node")
        alias = str(output.get("alias", ""))
        predicate = _uri(output.get("property", ""))
        if node_id not in node_types:
            errors.append(f"output이 미등록 node를 참조합니다: {node_id}")
            continue
        if not _ID.fullmatch(alias):
            errors.append(f"허용하지 않는 output alias: {alias!r}")
        elif alias in aliases:
            errors.append(f"중복 output alias: {alias}")
        aliases.add(alias)
        if predicate == LABEL_PROPERTY:
            continue    # 분류 개체의 이름. catalog(datatype/domain) 검사 대상이 아니다.
        signature = catalog.properties.get(predicate)
        if not signature:
            errors.append(f"존재하지 않는 output property: {compact_uri(predicate)}")
            continue
        if predicate not in allowed_properties:
            errors.append(f"schema fragment 밖 output property: {compact_uri(predicate)}")
        if signature.kind != "datatype":
            errors.append(f"output property는 DatatypeProperty여야 합니다: {compact_uri(predicate)}")
        elif not catalog.compatible(node_types[node_id], set(signature.domains)):
            errors.append(f"output domain 위반: {node_id}({compact_uri(node_types[node_id])}) "
                          f"--{compact_uri(predicate)}")
        elif not _populated(predicate):
            errors.append(f"ABox에 값이 0건인 output property: {compact_uri(predicate)}. "
                          "이 속성으로는 답을 만들 수 없으니 다른 경로를 쓰십시오")

    limit = plan.get("limit", 100)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_QUERY_LIMIT:
        errors.append(f"limit은 1~{MAX_QUERY_LIMIT} 정수여야 합니다")
    return PlanValidation(tuple(dict.fromkeys(errors)))


def compile_graph_plan(plan: dict, entity: dict, fragment: SchemaFragment,
                       catalog: SchemaCatalog) -> CompiledGraphQuery:
    validation = validate_graph_plan(plan, entity, fragment, catalog)
    if not validation.ok:
        raise ValueError("; ".join(validation.errors))
    node_types = _node_map(plan)
    seed_uri = entity["uri"]
    select_vars, where, evidence_vars = [], [], []

    seed_variable = False
    codes = entity.get("codes") or []
    seed_class = entity.get("class_uri", "")
    canonical_name = entity.get("canonical_name")
    if canonical_name and seed_class.endswith(("Company", "Organization", "Issuer", "AssetManager")):
        # 이 값은 사용자 문자열이 아니라 entity resolver가 유일 URI에 대해 확정한
        # canonical organizationName이다. 이 Store에서는 해당 literal index가 URI/code
        # seed보다 훨씬 빠르다.
        where.append(f"?seed {_term(FP + 'organizationName')} {Literal(canonical_name).n3()} .")
        where.append(f"?seed a {_term(seed_class)} .")
        seed_variable = True
    elif codes:
        identifier_property = (FP + "securityCode" if seed_class.endswith("Security")
                               else FP + "productCode")
        # fp:Theme 같은 분류 개체도 resolver가 codes를 채운다(canonical_name과 동일).
        # 그 class에 없는 식별자로 묶으면 정답 plan도 조용히 0행이 된다.
        signature = catalog.properties.get(identifier_property)
        if signature and catalog.compatible(seed_class, set(signature.domains)):
            where.append(f"?seed {_term(identifier_property)} {Literal(codes[0]).n3()} .")
            seed_variable = True

    def ref(node_id: str) -> str:
        if node_id == "seed":
            return "?seed" if seed_variable else _term(seed_uri)
        return f"?{node_id}"

    # 타입은 plan validator가 TBox로 검사한다. 모든 변수에 rdf:type 조인을 넣으면
    # Oxigraph가 넓은 class scan부터 시작할 수 있다. ETN 혼입을 막아야 하는 상품
    # 경계만 실행 쿼리에도 명시하고, seed는 해소된 URI 자체를 사용한다.
    # fp:Bond는 여기 넣지 않는다. 채권은 전부 CorporateBond·SpecialBond·
    # GovernmentBond로만 적재돼 있어 이 게이트가 정답 plan을 조용히 0행으로
    # 만든다. Oxigraph는 추론하지 않는다.
    runtime_type_gate = {FP + "ETF", FP + "ETN", FP + "PublicFund"}
    for node_id, cls in node_types.items():
        if node_id != "seed" and cls in runtime_type_gate:
            where.append(f"{ref(node_id)} a {_term(cls)} .")
    edges = plan.get("edges") or []
    for edge in edges:
        where.append(f"{ref(edge['subject'])} {_term(_uri(edge['predicate']))} "
                     f"{ref(edge['object'])} .")
    if not edges:
        # edge 없는 속성 조회는 output이 전부 OPTIONAL일 수 있다. 해소된 class로
        # seed를 고정해 두지 않으면 미바인딩 1행이 "결과 있음"으로 새어 나간다.
        grounding = f"{ref('seed')} a {_term(seed_class)} ."
        if grounding not in where:
            where.append(grounding)

    output_nodes = []
    for output in plan.get("outputs") or []:
        node_id, alias = output["node"], output["alias"]
        property_uri = _uri(output["property"])
        if property_uri == LABEL_PROPERTY:
            where.append(
                f"OPTIONAL {{ {ref(node_id)} {_term(LABEL_PROPERTY)} ?{alias} . "
                f'FILTER (langMatches(lang(?{alias}), "ko") || lang(?{alias}) = "") }}')
        else:
            triple = f"{ref(node_id)} {_term(property_uri)} ?{alias} ."
            where.append(f"OPTIONAL {{ {triple} }}" if output.get("optional") else triple)
        if node_id not in output_nodes:
            output_nodes.append(node_id)
        select_vars.append(alias)

    # 관계·스냅샷 노드는 출처 계약을 LLM 출력과 무관하게 강제한다.
    for node_id, cls in node_types.items():
        if cls not in _EVIDENCE_CLASSES:
            continue
        prefix = node_id
        aliases = {key: f"{prefix}_{key}" for key in _EVIDENCE_PROPERTIES}
        where.extend([
            f"OPTIONAL {{ {ref(node_id)} {_term(_EVIDENCE_PROPERTIES['as_of'])} "
            f"?{aliases['as_of']} . }}",
            f"OPTIONAL {{ {ref(node_id)} {_term(_EVIDENCE_PROPERTIES['source'])} "
            f"?{aliases['source']} . }}",
            f"OPTIONAL {{ {ref(node_id)} {_term(_EVIDENCE_PROPERTIES['document'])} "
            f"?{aliases['document']} . ?{aliases['document']} "
            f"{_term(_EVIDENCE_PROPERTIES['document_title'])} ?{aliases['document_title']} . }}",
            f"FILTER (!BOUND(?{aliases['as_of']}) || ?{aliases['as_of']} <= "
            f"\"{DATA_CUTOFF}\"^^<http://www.w3.org/2001/XMLSchema#date>)",
        ])
        evidence_vars.extend(aliases[key] for key in
                             ("as_of", "source", "document", "document_title"))
        for key in ("document_publisher", "document_date", "document_quote"):
            where.append(f"OPTIONAL {{ {ref(node_id)} {_term(_EVIDENCE_PROPERTIES['document'])} ?{aliases['document']} . "
                         f"?{aliases['document']} {_term(_EVIDENCE_PROPERTIES[key])} ?{aliases[key]} . }}")
            select_vars.append(aliases[key])

    projected = select_vars + evidence_vars
    projected = list(dict.fromkeys(projected))
    query = "SELECT " + " ".join(f"?{x}" for x in projected) + " WHERE {\n  "
    query += "\n  ".join(where)
    query += f"\n}}\nLIMIT {plan.get('limit', 100)}"

    provenance = []
    used = ([_uri(edge["predicate"]) for edge in edges] +
            [_uri(output["property"]) for output in plan.get("outputs") or []])
    for uri in used:
        signature = catalog.properties.get(uri)
        if signature and (signature.source_table or signature.source_column):
            provenance.append((signature.curie, signature.source_table,
                               signature.source_column))
    return CompiledGraphQuery(query, tuple(projected), tuple(evidence_vars),
                              tuple(dict.fromkeys(provenance)))


def subsidiary_relation_plan(limit: int = 100) -> dict:
    return {
        "nodes": [
            {"id": "seed", "class_uri": "fp:Company"},
            {"id": "relation", "class_uri": "fp:SubsidiaryRelation"},
            {"id": "child", "class_uri": "fp:Company"},
        ],
        "edges": [
            {"subject": "seed", "predicate": "fp:hasSubsidiary", "object": "relation"},
            {"subject": "relation", "predicate": "fp:subsidiaryCompany", "object": "child"},
        ],
        "outputs": [
            {"node": "child", "property": "fp:organizationName", "alias": "child_name"},
            {"node": "child", "property": "fp:corpCode", "alias": "child_corp_code", "optional": True},
            {"node": "relation", "property": "fp:ownershipPct", "alias": "ownership_pct", "optional": True},
        ],
        "limit": min(max(int(limit), 1), MAX_QUERY_LIMIT),
    }


def company_holding_etf_plan(limit: int = 500) -> dict:
    """"<회사>를 편입/보유한 ETF" - 자회사 체인 없이 회사가 발행한 증권을
    직접 보유한 ETF를 찾는 결정적 plan. 2026-09-02 실측: "SK하이닉스를
    편입한 ETF"류 질문에서 HCX가 생성하는 GraphLogicalPlan이 역방향 관계
    (증권->발행기업, edge subject/object 방향)를 자주 틀려 3회 교정 안에
    abstain하는 사례가 반복됐다 - 실제로는 이 관계가 그래프에 이미
    있는데도(직접 SPARQL로 ETF 10건 이상 확인) LLM 생성 경로가 못 찾는
    것이었다. subsidiary_holding_etf_plan에서 자회사 홉(hasSubsidiary/
    subsidiaryCompany)만 뺀 것과 같다."""
    return {
        "nodes": [
            {"id": "seed", "class_uri": "fp:Company"},
            {"id": "security", "class_uri": "fp:Security"},
            {"id": "holding", "class_uri": "fp:Holding"},
            {"id": "etf", "class_uri": "fp:ETF"},
        ],
        "edges": [
            {"subject": "security", "predicate": "fp:issuedByCompany", "object": "seed"},
            {"subject": "holding", "predicate": "fp:holdingSecurity", "object": "security"},
            {"subject": "etf", "predicate": "fp:hasHolding", "object": "holding"},
        ],
        "outputs": [
            {"node": "etf", "property": "fp:productCode", "alias": "etf_code"},
            {"node": "etf", "property": "fp:productShortName", "alias": "etf_name"},
            {"node": "holding", "property": "fp:weight", "alias": "weight", "optional": True},
        ],
        "limit": min(max(int(limit), 1), MAX_QUERY_LIMIT),
    }


def theme_membership_plan(limit: int = 500) -> dict:
    """"<테마> 테마 ETF" - 특정 테마(fp:Theme, LSEG 176테마 taxonomy)에
    연관된 모든 ETF를 찾는 결정적 plan. seed가 될 Theme 후보 자체는 이
    plan이 정하지 않는다 - orchestrator의 run_theme_membership()이
    resolve_entity(allow_partial=True)로 후보 테마를 전부 찾아 후보마다
    이 plan을 반복 실행해서 합친다. "반도체"처럼 사용자가 실제로 쓰는
    키워드가 정확히 하나의 테마명과 같지 않고 여러 하위 테마("K-반도체",
    "글로벌반도체" 등)에 걸쳐 있는 게 흔하기 때문이다(2026-09-02 실측).

    fp:relatedToTheme의 원천은 ontology/common.ttl 주석대로 국내ETF
    1,099종(LSEG)뿐이다 - 해외ETF/펀드/채권 쪽 테마 질문은 이 plan으로는
    항상 0건이다(데이터 범위 제약이지 버그가 아니다)."""
    return {
        "nodes": [
            {"id": "seed", "class_uri": "fp:Theme"},
            {"id": "etf", "class_uri": "fp:ETF"},
        ],
        "edges": [
            {"subject": "etf", "predicate": "fp:relatedToTheme", "object": "seed"},
        ],
        "outputs": [
            {"node": "etf", "property": "fp:productCode", "alias": "etf_code"},
            {"node": "etf", "property": "fp:productShortName", "alias": "etf_name"},
        ],
        "limit": min(max(int(limit), 1), MAX_QUERY_LIMIT),
    }


def subsidiary_holding_etf_plan(limit: int = 500) -> dict:
    return {
        "nodes": [
            {"id": "seed", "class_uri": "fp:Company"},
            {"id": "relation", "class_uri": "fp:SubsidiaryRelation"},
            {"id": "child", "class_uri": "fp:Company"},
            {"id": "security", "class_uri": "fp:Security"},
            {"id": "holding", "class_uri": "fp:Holding"},
            {"id": "etf", "class_uri": "fp:ETF"},
        ],
        "edges": [
            {"subject": "seed", "predicate": "fp:hasSubsidiary", "object": "relation"},
            {"subject": "relation", "predicate": "fp:subsidiaryCompany", "object": "child"},
            {"subject": "security", "predicate": "fp:issuedByCompany", "object": "child"},
            {"subject": "holding", "predicate": "fp:holdingSecurity", "object": "security"},
            {"subject": "etf", "predicate": "fp:hasHolding", "object": "holding"},
        ],
        "outputs": [
            {"node": "child", "property": "fp:organizationName", "alias": "child_name"},
            {"node": "etf", "property": "fp:productCode", "alias": "etf_code"},
            {"node": "etf", "property": "fp:productShortName", "alias": "etf_name"},
            {"node": "holding", "property": "fp:weight", "alias": "weight", "optional": True},
        ],
        "limit": min(max(int(limit), 1), MAX_QUERY_LIMIT),
    }
