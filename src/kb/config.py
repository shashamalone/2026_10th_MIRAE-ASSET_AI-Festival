"""
GraphDB(pyoxigraph) 전용 경로 상수.

RDB 경로(utils.py의 RDB_API_BASE_URL)나 LLM 클라이언트(get_clova.py)는 이미
각자 자기 파일 안에서 필요한 상수를 직접 정의하고 있어 여기서 다루지 않는다.
이 파일은 GraphDB 빌드·조회 코드(build_graph.py, graph_engine.py 등)가 공유하는
경로만 담는다.

config.py는 src/kb/ 안에 있으므로 ROOT는 두 단계 위(저장소 루트)다.
ontology/·artifacts/·data/는 저장소 루트에 있고 src/kb/ 아래에는 없다.
kb/manifest.py의 ROOT 정의(parents[2])와 같은 기준이다. (예전 sql_gen_test/
시절 주석은 .parent 한 번이었는데, 파일이 src/kb/로 옮겨진 뒤 갱신되지 않아
graph_entity·graph_schema·graph_db client가 src/kb/ontology 같은 없는 경로를
찾다가 조용히 abstain하던 원인이었다 — 2026-09-03 실측.)
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY_DIR = ROOT / "ontology"
ARTIFACTS = ROOT / "artifacts"
