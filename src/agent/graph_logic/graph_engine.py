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
from functools import lru_cache
from pyoxigraph import Store
from kb.config import ARTIFACTS

STORE_PATH = ARTIFACTS / "oxigraph"
MAX_ROWS = 10_000
_FORBIDDEN = re.compile(
    r"\b(?:ADD|CLEAR|COPY|CREATE|DELETE|DROP|INSERT|LOAD|MOVE|SERVICE|WITH)\b",
    re.IGNORECASE,
)


@lru_cache(maxsize=1)
def _store() -> Store:
    if not STORE_PATH.is_dir():
        raise RuntimeError(f"Graph store 미구축 — python3 build_graph.py 먼저 실행 ({STORE_PATH})")
    return Store.read_only(str(STORE_PATH))


def _value(term):
    if term is None:
        return None
    return term.value


def sparql(query: str) -> bool | list[dict]:
    """SELECT/ASK만 허용한다."""
    text = query.lstrip()
    text = re.sub(r"(?is)^(?:PREFIX\s+\w*:\s*<[^>]+>\s*)+", "", text).lstrip()
    kind = text.split(None, 1)[0].upper() if text else ""
    if kind not in {"SELECT", "ASK"} or _FORBIDDEN.search(query):
        raise ValueError("Graph query는 SERVICE 없는 SELECT/ASK만 허용합니다")
    result = _store().query(query)
    if kind == "ASK":
        return bool(result)
    variables = [v.value for v in result.variables]
    rows = []
    for solution in result:
        if len(rows) >= MAX_ROWS:
            raise ValueError(f"Graph 결과가 상한 {MAX_ROWS:,}행을 초과했습니다")
        rows.append({name: _value(solution[name]) for name in variables})
    return rows


def triple_count() -> int:
    """store에 적재된 전체 트리플 수. 연결 확인용."""
    return len(_store())
