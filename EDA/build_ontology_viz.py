#!/usr/bin/env python3
"""ontology/*.ttl 5종을 인터랙티브 그래프 3종으로 시각화한다.

  viz/ontology_schema.html    뷰1 클래스 계층 + ObjectProperty(domain→range) + disjointWith
  viz/ontology_domains.html   뷰2 파일 출처별 색 구분 — common과 도메인 4파일의 경계
  viz/ontology_codelists.html 뷰3 코드리스트 개체 297종을 소속 클래스별로 배치

리터럴은 노드로 만들지 않는다(툴팁으로만). ObjectProperty도 노드가 아니라 엣지 라벨이다.
실행: python3 EDA/build_ontology_viz.py
"""
import json
import math
from pathlib import Path

from pyvis.network import Network
from rdflib import Graph, RDF, RDFS, OWL, URIRef, Literal

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "EDA" / "viz"
FILES = ["common.ttl", "bond_kr.ttl", "etf_kr.ttl", "etf_gl.ttl", "fund_pub.ttl"]

# 파일 출처별 색 (뷰2) — common만 회색 계열로 눌러 도메인 4개가 튀어 보이게 한다
FILE_COLOR = {
    "common.ttl": "#8d99ae",
    "bond_kr.ttl": "#e07a5f",
    "etf_kr.ttl": "#3d84a8",
    "etf_gl.ttl": "#46b29d",
    "fund_pub.ttl": "#c17fb8",
}
# 역할별 색 (뷰1)
ROLE_COLOR = {
    "상품": "#4c78a8",
    "조직": "#e45756",
    "분류축(코드리스트)": "#59a14f",
    "n-ary 패턴": "#f28e2b",
    "기타": "#9c9c9c",
}
EDGE_COLOR = {"subClassOf": "#555555", "objectProperty": "#4c78a8", "disjointWith": "#d62728"}


# --- 공통 헬퍼 --------------------------------------------------------------
def load():
    """병합 그래프와 '엔티티 → 선언 파일' 맵을 함께 반환한다."""
    merged, origin = Graph(), {}
    for name in FILES:
        g = Graph()
        g.parse((ROOT / "ontology" / name).as_posix(), format="turtle")
        merged += g
        for s in set(g.subjects()):
            origin.setdefault(s, name)
    return merged, origin


def local(u):
    return str(u).split("#")[-1].split("/")[-1]


def label(g, u, lang="ko"):
    for lit in g.objects(u, RDFS.label):
        if isinstance(lit, Literal) and lit.language == lang:
            return str(lit)
    return local(u)


def tooltip(g, u):
    """rdfs:label(@ko/@en) + rdfs:comment 를 툴팁 문자열로. 리터럴은 여기서만 쓴다."""
    parts = [f"<b>{local(u)}</b>", f"label: {label(g, u)} / {label(g, u, 'en')}"]
    for c in g.objects(u, RDFS.comment):
        parts.append(str(c))
    return "<br>".join(parts)  # vis-network 툴팁은 innerHTML로 들어간다


def expand(g, node):
    """rdfs:domain/range 값을 명명 클래스 집합으로 편다(owl:unionOf 블랭크노드 처리)."""
    if isinstance(node, URIRef):
        return [node]
    return [x for x in g.items(next(g.objects(node, OWL.unionOf), None) or []) if isinstance(x, URIRef)]


def named_classes(g):
    return sorted({s for s in g.subjects(RDF.type, OWL.Class) if isinstance(s, URIRef)}, key=local)


def class_edges(g, classes):
    """(from, to, 라벨, 종류) 목록. 양끝이 모두 명명 클래스인 것만."""
    cs, edges = set(classes), []
    for s, o in g.subject_objects(RDFS.subClassOf):
        if s in cs and o in cs:
            edges.append((s, o, "subClassOf", "subClassOf"))
    for p in g.subjects(RDF.type, OWL.ObjectProperty):
        for d in expand(g, next(g.objects(p, RDFS.domain), None)):
            for r in expand(g, next(g.objects(p, RDFS.range), None)):
                if d in cs and r in cs:
                    edges.append((d, r, local(p), "objectProperty"))
    seen = set()
    for s, o in g.subject_objects(OWL.disjointWith):
        if s in cs and o in cs and (o, s) not in seen:
            seen.add((s, o))
            edges.append((s, o, "disjointWith", "disjointWith"))
    return edges


def descendants(g, root):
    """rdfs:subClassOf 로 root 아래 달린 모든 클래스(root 포함)."""
    out, stack = {root}, [root]
    while stack:
        cur = stack.pop()
        for s in g.subjects(RDFS.subClassOf, cur):
            if s not in out:
                out.add(s)
                stack.append(s)
    return out


def fp(name):
    return URIRef("http://mafest.ai/product#" + name)


def codelist_map(g, classes):
    """코드리스트 클래스 → 개체 목록. 개체가 하나라도 있는 클래스만."""
    out = {}
    for c in classes:
        inds = sorted((s for s in g.subjects(RDF.type, c) if isinstance(s, URIRef)), key=local)
        if inds:
            out[c] = inds
    return out


def net(directed=True, physics=True):
    # font_color / group 은 넘기지 않는다 — pyvis가 노드별 font·color 를 덮어쓴다
    n = Network(height="900px", width="100%", directed=directed, cdn_resources="in_line",
                bgcolor="#ffffff")
    n.toggle_physics(physics)
    return n


def add_edge(n, s, o, text, kind):
    dashes = kind != "subClassOf"
    n.add_edge(local(s), local(o), title=text, label="" if kind == "subClassOf" else text,
               color=EDGE_COLOR[kind], dashes=dashes, arrows="to" if kind != "disjointWith" else "",
               width=2 if kind == "subClassOf" else 1, font={"size": 11, "color": EDGE_COLOR[kind]})


def save(n, name):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    n.write_html(path.as_posix(), notebook=False)
    print(f"  {name:26s} {path.stat().st_size / 1024:8.0f} KB  "
          f"nodes={len(n.nodes)} edges={len(n.edges)}")
    return len(n.nodes), len(n.edges)


# --- 뷰1: 스키마 구조 -------------------------------------------------------
def view_schema(g):
    classes = named_classes(g)
    products = descendants(g, fp("Product"))
    orgs = descendants(g, fp("Organization"))
    nary = {fp("Holding"), fp("MetricSnapshot")}
    codelists = set(codelist_map(g, classes))

    def role(c):
        if c in nary:
            return "n-ary 패턴"
        if c in products:
            return "상품"
        if c in orgs:
            return "조직"
        if c in codelists:
            return "분류축(코드리스트)"
        return "기타"

    n = net()
    for c in classes:
        r = role(c)
        n.add_node(local(c), label=label(g, c), title=tooltip(g, c), color=ROLE_COLOR[r],
                   shape="box", size=20)
    for s, o, text, kind in class_edges(g, classes):
        add_edge(n, s, o, text, kind)
    n.set_options(json.dumps({
        "physics": {"solver": "forceAtlas2Based",
                    "forceAtlas2Based": {"gravitationalConstant": -80, "springLength": 160},
                    "stabilization": {"iterations": 300}},
        "nodes": {"font": {"size": 16, "color": "#222222"}},
        "interaction": {"hover": True, "tooltipDelay": 100, "navigationButtons": True},
    }))
    return save(n, "ontology_schema.html")


# --- 뷰2: 도메인별 출처 -----------------------------------------------------
def view_domains(g, origin):
    classes = named_classes(g)
    n = net()
    for f, color in FILE_COLOR.items():  # 파일 허브 노드
        n.add_node(f, label=f, title=f"{f} 선언 엔티티", color=color, shape="star", size=40)
    for c in classes:
        src = origin.get(c, "common.ttl")
        n.add_node(local(c), label=label(g, c), title=f"[{src}]<br>{tooltip(g, c)}",
                   color=FILE_COLOR[src], shape="box", size=18)
        n.add_edge(src, local(c), color="#dddddd", dashes=True, width=1, arrows="")
    for s, o, text, kind in class_edges(g, classes):
        add_edge(n, s, o, text, kind)
    n.set_options(json.dumps({
        "physics": {"solver": "forceAtlas2Based",
                    "forceAtlas2Based": {"gravitationalConstant": -120, "springLength": 180},
                    "stabilization": {"iterations": 300}},
        "nodes": {"font": {"size": 15, "color": "#222222"}},
        "interaction": {"hover": True, "tooltipDelay": 100, "navigationButtons": True},
    }))
    return save(n, "ontology_domains.html")


# --- 뷰3: 코드리스트 --------------------------------------------------------
def view_codelists(g, origin):
    """physics를 끄고 클래스별 블록(그리드)으로 직접 좌표를 잡는다. 176개 테마도 읽힌다."""
    cmap = codelist_map(g, named_classes(g))
    n = net(physics=False)
    x = 0
    for c, inds in sorted(cmap.items(), key=lambda kv: -len(kv[1])):
        cols = max(1, math.ceil(math.sqrt(len(inds))))
        w = cols * 190
        n.add_node(local(c), label=f"{label(g, c)} ({len(inds)})", title=tooltip(g, c),
                   color="#22333b", shape="box", size=28, x=int(x + w / 2), y=0,
                   font={"size": 26, "color": "#ffffff"}, fixed=True)
        for i, ind in enumerate(inds):
            n.add_node(local(ind), label=label(g, ind), title=tooltip(g, ind),
                       color=FILE_COLOR[origin.get(ind, "common.ttl")], shape="ellipse", size=12,
                       x=int(x + (i % cols) * 190), y=int(220 + (i // cols) * 90), fixed=True)
            n.add_edge(local(c), local(ind), color="#cccccc", width=1, arrows="")
        x += w + 260
    n.set_options(json.dumps({
        "physics": {"enabled": False},
        "nodes": {"font": {"size": 14, "color": "#222222"}},
        "interaction": {"hover": True, "tooltipDelay": 100, "navigationButtons": True,
                        "dragNodes": False},
    }))
    return save(n, "ontology_codelists.html")


def main():
    g, origin = load()
    print(f"병합 그래프 {len(g)} triples / 클래스 {len(named_classes(g))}개")
    view_schema(g)
    view_domains(g, origin)
    view_codelists(g, origin)


if __name__ == "__main__":
    main()
    # 자체 점검: 뷰1 노드 수 == 명명 클래스 수, unionOf domain이 실제로 펴지는지
    _g, _ = load()
    _cls = named_classes(_g)
    assert len(_cls) == 49, f"클래스 수 {len(_cls)} != 49"
    _e = class_edges(_g, _cls)
    assert any(t == "issuedBy" for _, _, t, _ in _e), "issuedBy 엣지 없음"
    assert {local(d) for d, _, t, _ in _e if t == "managedBy"} == {"ETF", "ETN", "PublicFund"}, \
        "owl:unionOf domain 전개 실패"
    assert any(k == "disjointWith" for *_, k in _e), "disjointWith 엣지 없음"
    for f in ("ontology_schema.html", "ontology_domains.html", "ontology_codelists.html"):
        assert (OUT / f).stat().st_size > 200_000, f"{f} 너무 작다(인라인 JS 누락 의심)"
    print("self-check OK")
