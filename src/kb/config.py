"""
GraphDB(pyoxigraph) 전용 저장소 경로 상수.

RDB 경로(utils.py의 RDB_API_BASE_URL)나 LLM 클라이언트(get_clova.py)는 이미
각자 자기 파일 안에서 필요한 상수를 직접 정의하고 있어 여기서 다루지 않는다.
이 파일은 GraphDB 빌드·조회 코드(build_graph.py, graph_engine.py 등)가 공유하는
경로만 담는다.

config.py는 ``<repo>/src/kb/config.py``에 있다. ontology와 artifacts는 src/kb
아래가 아니라 저장소 최상위의 정본 디렉터리이므로 두 단계 위를 ROOT로 삼는다.
현재 작업 디렉터리와 무관하게 같은 절대 경로가 계산되어야 한다.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY_DIR = ROOT / "ontology"
ARTIFACTS = ROOT / "artifacts"
