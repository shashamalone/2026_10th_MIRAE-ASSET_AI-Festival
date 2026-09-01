# -*- coding: utf-8 -*-
"""TBox class 선별과 1~2홉 schema fragment 생성.

벡터 인덱스는 재생성 가능한 ``artifacts/graph_schema_index.json``에 둔다.
인덱스가 없으면 테스트·복구용 lexical fallback을 쓰되 반환값에 selection_mode를
남겨 운영에서 임베딩 경로가 조용히 빠지지 않게 한다.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from rdflib import BNode, Graph, Literal, OWL, RDF, RDFS, URIRef

from config import ARTIFACTS, ROOT
from kb.ids import normalize_text


FP = "http://mafest.ai/product#"
FP_URI = URIRef(FP)
TBOX_FILES = ("common.ttl", "bond_kr.ttl", "etf_kr.ttl", "etf_gl.ttl", "fund_pub.ttl")
SCHEMA_INDEX_PATH = ARTIFACTS / "graph_schema_index.json"
_TOKEN = re.compile(r"[0-9A-Za-z가-힣]{2,}")


def compact_uri(value: URIRef | str) -> str:
    text = str(value)
    if text.startswith(FP):
        return "fp:" + text[len(FP):]
    if text == str(RDF.type):
        return "rdf:type"
    if text == str(RDFS.label):
        return "rdfs:label"
    return f"<{text}>"


def expand_uri(value: str) -> URIRef:
    if value.startswith("fp:"):
        return URIRef(FP + value[3:])
    if value == "rdf:type":
        return RDF.type
    if value == "rdfs:label":
        return RDFS.label
    if value.startswith("<") and value.endswith(">"):
        return URIRef(value[1:-1])
    return URIRef(value)


def _label(graph: Graph, node: URIRef) -> str:
    labels = list(graph.objects(node, RDFS.label))
    korean = next((str(x) for x in labels if getattr(x, "language", None) == "ko"), None)
    return korean or (str(labels[0]) if labels else compact_uri(node))


def _annotation(graph: Graph, node: URIRef, name: str) -> str:
    """fp: 애노테이션 값. 다중 원천은 정렬 후 ", "로 합쳐 결정적으로 표기한다."""
    return ", ".join(sorted(str(x) for x in graph.objects(node, URIRef(FP + name))))


def _comment(graph: Graph, node: URIRef) -> str:
    comments = list(graph.objects(node, RDFS.comment))
    korean = next((str(x) for x in comments if getattr(x, "language", None) == "ko"), None)
    return korean or (str(comments[0]) if comments else "")


@dataclass(frozen=True)
class PropertySignature:
    uri: str
    label: str
    kind: str
    domains: tuple[str, ...]
    ranges: tuple[str, ...]
    comment: str
    source_table: str = ""
    source_column: str = ""

    @property
    def curie(self) -> str:
        return compact_uri(self.uri)


@dataclass(frozen=True)
class SchemaFragment:
    seed_classes: tuple[str, ...]
    classes: tuple[str, ...]
    properties: tuple[PropertySignature, ...]
    selection_mode: str
    class_hits: tuple[dict, ...]

    @property
    def property_uris(self) -> set[str]:
        return {p.uri for p in self.properties}

    def to_prompt(self) -> str:
        lines = ["[허용 클래스]"]
        lines.extend(f"- {compact_uri(uri)}" for uri in self.classes)
        lines.append("[허용 속성: 반드시 아래 방향 그대로 사용]")
        for prop in self.properties:
            domains = " | ".join(compact_uri(x) for x in prop.domains)
            ranges = " | ".join(compact_uri(x) for x in prop.ranges)
            lines.append(f"- {domains} --{prop.curie}--> {ranges}  # {prop.label}")
        # 자체 datatype property가 없는 class(투자지역·자산유형·위험등급 등 분류 개체)의
        # 이름은 rdfs:label로만 얻는다. 이 줄이 없으면 모델이 "fragment 값만 복사" 규칙을
        # 지키느라 분류 개체 경로 자체를 포기하고 이름이 비슷한 datatype property를 고른다.
        with_datatype = {d for p in self.properties if p.kind == "datatype" for d in p.domains}
        label_only = [c for c in self.classes if c.startswith(FP) and c not in with_datatype]
        if label_only:
            lines.append("- " + " | ".join(compact_uri(x) for x in label_only) +
                         " --rdfs:label--> xsd:string  # 분류 개체의 이름은 rdfs:label로만 얻는다")
        return "\n".join(lines)

    def as_dict(self) -> dict:
        return {
            "seed_classes": list(self.seed_classes),
            "classes": list(self.classes),
            "properties": [
                {"uri": p.uri, "curie": p.curie, "label": p.label,
                 "kind": p.kind, "domains": list(p.domains), "ranges": list(p.ranges),
                 "source_table": p.source_table, "source_column": p.source_column}
                for p in self.properties
            ],
            "selection_mode": self.selection_mode,
            "class_hits": list(self.class_hits),
        }


class SchemaCatalog:
    def __init__(self, graph: Graph):
        self.graph = graph
        self.classes = {
            str(x) for x in graph.subjects(RDF.type, OWL.Class)
            if isinstance(x, URIRef)
        }
        self.properties: dict[str, PropertySignature] = {}
        for kind_node, kind in ((OWL.ObjectProperty, "object"),
                                (OWL.DatatypeProperty, "datatype")):
            for prop in graph.subjects(RDF.type, kind_node):
                if not isinstance(prop, URIRef):
                    continue
                domains = self._expanded_values(prop, RDFS.domain)
                ranges = self._expanded_values(prop, RDFS.range)
                self.properties[str(prop)] = PropertySignature(
                    uri=str(prop), label=_label(graph, prop), kind=kind,
                    domains=tuple(sorted(domains)), ranges=tuple(sorted(ranges)),
                    comment=_comment(graph, prop),
                    source_table=_annotation(graph, prop, "sourceTable"),
                    source_column=_annotation(graph, prop, "sourceColumn"),
                )

    @classmethod
    def load(cls) -> "SchemaCatalog":
        graph = Graph()
        for name in TBOX_FILES:
            graph.parse((ROOT / "ontology" / name).as_posix(), format="turtle")
        return cls(graph)

    def _expand_class_expression(self, node) -> set[str]:
        if isinstance(node, URIRef):
            return {str(node)}
        if isinstance(node, BNode):
            out = set()
            for collection in self.graph.objects(node, OWL.unionOf):
                out |= {str(x) for x in self.graph.items(collection)
                        if isinstance(x, URIRef)}
            return out
        return set()

    def _expanded_values(self, subject, predicate) -> set[str]:
        out = set()
        for node in self.graph.objects(subject, predicate):
            out |= self._expand_class_expression(node)
        return out

    def is_subclass(self, child: str, parent: str) -> bool:
        if child == parent:
            return True
        todo, seen = [URIRef(child)], set()
        target = URIRef(parent)
        while todo:
            node = todo.pop()
            if node in seen:
                continue
            seen.add(node)
            for upper in self.graph.objects(node, RDFS.subClassOf):
                if upper == target:
                    return True
                if isinstance(upper, URIRef):
                    todo.append(upper)
        return False

    def compatible(self, actual: str, allowed: tuple[str, ...] | set[str]) -> bool:
        return any(self.is_subclass(actual, expected) for expected in allowed)

    def class_resources(self) -> list[dict]:
        rows = []
        for uri in sorted(self.classes):
            node = URIRef(uri)
            rows.append({"uri": uri, "label": _label(self.graph, node),
                         "comment": _comment(self.graph, node)})
        return rows

    def fingerprint(self) -> str:
        payload = json.dumps(self.class_resources(), ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _lexical_hits(self, question: str, k: int) -> list[dict]:
        q = normalize_text(question)
        q_compact = q.replace(" ", "")
        q_tokens = set(_TOKEN.findall(q))
        scored = []
        aliases = {
            FP + "Company": ("기업", "회사", "모회사", "자회사", "법인"),
            FP + "SubsidiaryRelation": ("자회사", "출자", "지배", "관계"),
            FP + "ETF": ("ETF", "상장지수펀드"),
            FP + "Holding": ("편입", "보유", "구성종목"),
            FP + "Security": ("증권", "종목", "주식", "채권"),
            FP + "Document": ("출처", "근거", "문서", "공시"),
            FP + "Bond": ("채권", "회사채", "국채", "국공채"),
            FP + "PublicFund": ("펀드", "공모펀드", "투자신탁"),
            FP + "Theme": ("테마",),
            FP + "Issuer": ("발행사", "발행기업", "발행회사"),
            FP + "AssetManager": ("운용사", "자산운용"),
        }
        for row in self.class_resources():
            text = normalize_text(row["label"] + " " + row["comment"])
            tokens = set(_TOKEN.findall(text))
            score = 2.0 * len(q_tokens & tokens)
            label = normalize_text(row["label"]).replace(" ", "")
            if label and label in q_compact:
                score += 5.0
            score += sum(3.0 for alias in aliases.get(row["uri"], ())
                         if normalize_text(alias).replace(" ", "") in q_compact)
            if score:
                scored.append({**row, "score": round(score, 4)})
        scored.sort(key=lambda x: (-x["score"], x["uri"]))
        return scored[:k]

    def _vector_hits(self, question: str, k: int) -> list[dict] | None:
        if not SCHEMA_INDEX_PATH.is_file():
            return None
        payload = json.loads(SCHEMA_INDEX_PATH.read_text(encoding="utf-8"))
        if payload.get("tbox_fingerprint") != self.fingerprint():
            return None
        from clova import embed  # 지연 import: lexical 테스트는 API 키가 필요 없다.

        query = list(map(float, embed(question)))
        qnorm = math.sqrt(sum(x * x for x in query)) or 1.0
        hits = []
        for row in payload.get("classes") or []:
            vector = row["embedding"]
            vnorm = math.sqrt(sum(x * x for x in vector)) or 1.0
            score = sum(a * b for a, b in zip(query, vector)) / (qnorm * vnorm)
            hits.append({"uri": row["uri"], "label": row["label"],
                         "comment": row.get("comment", ""), "score": round(score, 4)})
        hits.sort(key=lambda x: (-x["score"], x["uri"]))
        return hits[:k]

    def select_fragment(self, question: str, *, seed_classes: list[str] | None = None,
                        hops: int = 2, class_k: int = 4,
                        max_classes: int = 12, max_properties: int = 36) -> SchemaFragment:
        if not 1 <= hops <= 3:
            raise ValueError("schema fragment hops는 1~3만 허용합니다")
        vector_hits = self._vector_hits(question, class_k)
        hits = vector_hits if vector_hits is not None else self._lexical_hits(question, class_k)
        base_mode = "embedding" if vector_hits is not None else "lexical_fallback"
        mode = base_mode + "+explicit" if seed_classes else base_mode
        seed_values = list(seed_classes or []) + [h["uri"] for h in hits]
        seeds = [str(expand_uri(x)) for x in seed_values]
        seeds = list(dict.fromkeys(x for x in seeds if x in self.classes))
        if not seeds:
            raise ValueError("질문과 연결할 TBox class를 찾지 못했습니다")

        selected, frontier, chosen = set(seeds), set(seeds), {}
        qnorm = normalize_text(question).replace(" ", "")
        required = {FP + name for name in (
            "hasSubsidiary", "subsidiaryCompany", "asOf", "sourceId", "supportedBy",
            "documentTitle", "documentPublisher", "documentPublishedDate", "documentQuote",
            "organizationName", "corpCode", "productCode", "productShortName",
            "issuedBy", "issuedByCompany", "hasCreditRating", "ratingRank", "hasRatingBand",
            "relatedToTheme", "themeName", "hasRiskGrade", "hasInvestmentRegion",
            "hasAssetType", "hasFundType", "hasHolding", "holdingSecurity", "weight",
            "ticker", "securityCode",
        )}
        for _ in range(hops):
            candidates = []
            for prop in self.properties.values():
                scope = set(prop.domains) | set(prop.ranges)
                # 정확 교집합만 보면 domain이 상위 class인 속성이 1홉에서 빠진다.
                # fp:hasRiskGrade·fp:hasAssetType·fp:hasInvestmentRegion은 domain이
                # fp:Product라 fp:PublicFund seed에서 영영 안 잡혔다(실측 F1·F2 전멸).
                if not any(cls in scope or self.compatible(cls, scope) for cls in frontier):
                    continue
                lexical = sum(1 for token in _TOKEN.findall(normalize_text(prop.label + " " + prop.comment))
                              if token in qnorm)
                bonus = 20 if prop.uri in required else 0
                # seed class 자신의 속성은 max_properties 컷에 밀리면 안 된다
                # (subsidiary fast path의 fp:ownershipPct가 실제로 밀려났다).
                bonus += 10 if set(prop.domains) & set(seeds) else 0
                candidates.append((bonus + lexical, prop.uri, prop))
            candidates.sort(key=lambda x: (-x[0], x[1]))
            # 도착 순서 = 속성 점수 순서. 알파벳 순으로 자르면 required 속성의 range
            # class(fp:RiskGrade 등)가 max_classes 컷에 밀려 plan에서 못 쓰게 된다.
            next_frontier = []
            for _, _, prop in candidates:
                if len(chosen) >= max_properties:
                    break
                chosen[prop.uri] = prop
                for cls in sorted(set(prop.domains) | set(prop.ranges)):
                    if cls not in selected and cls not in next_frontier:
                        next_frontier.append(cls)
            room = max(0, max_classes - len(selected))
            frontier = set(next_frontier[:room])
            selected |= frontier
            if not frontier:
                break

        # 선택된 관계 노드의 datatype/evidence 속성은 마지막 hop에서 도착했더라도 포함한다.
        for prop in sorted(self.properties.values(), key=lambda x: x.uri):
            if len(chosen) >= max_properties:
                break
            if set(prop.domains) & selected and (prop.kind == "datatype" or prop.uri in required):
                chosen.setdefault(prop.uri, prop)
                selected |= set(prop.ranges) & self.classes

        return SchemaFragment(
            seed_classes=tuple(seeds), classes=tuple(sorted(selected)),
            properties=tuple(sorted(chosen.values(), key=lambda x: x.uri)),
            selection_mode=mode, class_hits=tuple(hits),
        )


@lru_cache(maxsize=1)
def catalog() -> SchemaCatalog:
    return SchemaCatalog.load()
