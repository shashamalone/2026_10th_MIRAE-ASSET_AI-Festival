"""
GraphDB(pyoxigraph) 전용 경로 상수.

RDB 경로(utils.py의 RDB_API_BASE_URL)나 LLM 클라이언트(get_clova.py)는 이미
각자 자기 파일 안에서 필요한 상수를 직접 정의하고 있어 여기서 다루지 않는다.
이 파일은 GraphDB 빌드·조회 코드(build_graph.py, graph_engine.py 등)가 공유하는
경로만 담는다.

config.py는 sql_gen_test/ 바로 아래에 있다. .parent 한 번이면 sql_gen_test/다.
(gragh/src/config.py는 gragh/src/ 안에 있어 .parent.parent가 맞았지만, 이 파일은
중첩 없이 sql_gen_test/ 최상위에 두므로 한 번만 올려야 한다 — 두 번 올리면 ROOT가
Test/가 되어 ontology/·artifacts/를 엉뚱한 곳에서 찾게 된다.)
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ONTOLOGY_DIR = ROOT / "ontology"
ARTIFACTS = ROOT / "artifacts"
