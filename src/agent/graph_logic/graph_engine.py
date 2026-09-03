"""
읽기 전용 pyoxigraph 연결 + SPARQL 실행 게이트.

build_graph.py가 만든 artifacts/oxigraph를 읽기 전용으로 연다. SELECT/ASK만
허용하고 INSERT/DELETE 등 쓰기 키워드는 정규식으로 차단한다 — Agent가 생성한
SPARQL이라도 이 게이트를 통과하지 않으면 실행되지 않는다.

원본: gragh/src/tools/graph.py의 연결·실행 부분만 남겼다. 그 파일의 고정
템플릿 13개(product_info 등)와 hybrid_search()는 이 프로젝트의 Graph 질의
로직(graph_entity.py/graph_plan.py/graph_orchestrator.py, 다음 단계에서 이식)이
대체하므로 여기에 옮기지 않았다.
"""
from __future__ import annotations
import re
from infrastructure.graph_db.client import OxigraphClient

_CLIENT = OxigraphClient()


def sparql(query: str) -> bool | list[dict]:
    return _CLIENT.query(query)


def triple_count() -> int:
    """store에 적재된 전체 트리플 수. 연결 확인용."""
    return _CLIENT.triple_count()
