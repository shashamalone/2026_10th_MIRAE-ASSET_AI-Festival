# -*- coding: utf-8 -*-
"""vectordb_test 전용 상수.

이름이 config 인 이유: 저장소의 검증된 clova.py 가 `from config import ...` 로
CLOVA_HOST / EMBEDDING_MODEL / ROOT / ARTIFACTS 를 받아간다. 그 계약을 그대로 만족시킨다.
test_*.py 를 이 디렉터리에서 실행하면 sys.path[0] 가 여기라 이 모듈이 잡힌다.
"""
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent      # vectordb_test/1_pgvector_test
VDB = HERE.parent                           # vectordb_test — 하위 폴더로 나뉜 뒤의 공통 뿌리
ROOT = VDB.parent                           # 저장소 루트 — src/clova.py 가 여기서 .env 를 읽는다

# 임베딩 캐시·결과는 vectordb_test 아래 공유한다. 저장소 artifacts/embed_cache.json 을
# 건드리지 않기 위해서다(이 테스트는 기존 파일을 읽기만 한다).
ARTIFACTS = VDB / "artifacts"
RESULTS = VDB / "results"

CLOVA_HOST = "https://clovastudio.stream.ntruss.com"
EMBEDDING_MODEL = "bge-m3"         # 1024차원, cosine (CLOVA Studio)
EMBED_DIM = 1024

# 접속 정보. 예전엔 os.environ 을 건드렸는데, config 를 import 하지 않은 파일에서
# 조용히 유닉스 소켓으로 새는 버그가 났다(peer 인증 실패). 명시적 DSN 으로 바꿔
# 잊어버릴 여지를 없앤다. unix socket 은 peer 인증이라 반드시 TCP(host 명시)를 쓴다.
def _env(k, default):
    return os.environ.get(k) or default


PGHOST = _env("PGHOST", "127.0.0.1")
PGPORT = _env("PGPORT", "5432")
PGUSER = _env("PGUSER", "postgres")
PGDATABASE = _env("PGDATABASE", "vectordb_test")

# 비밀번호는 DSN 안에만 두고 어디에서도 출력하지 않는다.
DSN = (f"host={PGHOST} port={PGPORT} user={PGUSER} "
       f"password={_env('PGPASSWORD', 'postgres')} dbname={PGDATABASE}")
TARGET = f"host={PGHOST} port={PGPORT} user={PGUSER} db={PGDATABASE}"   # 로그용(무비번)

RRF_K = 60                         # RRF 상수 — 원 논문 기본값
TOP_K = 5
