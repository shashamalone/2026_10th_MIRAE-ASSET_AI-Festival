# -*- coding: utf-8 -*-
"""접속 + 버전 + 확장 확인."""
import psycopg

from checks import check, finish
from config import DSN, TARGET

print("test_connection")
print(f"  대상: {TARGET}")

try:
    conn = psycopg.connect(DSN, autocommit=True)
except Exception as e:
    check("접속", False, repr(e))
    finish("test_connection")

ver = conn.execute("SHOW server_version").fetchone()[0]
check("접속", True, f"PostgreSQL {ver}")

exts = dict(conn.execute("SELECT extname, extversion FROM pg_extension").fetchall())
check("pgvector 설치", "vector" in exts, f"vector {exts.get('vector')}")
check("pg_trgm 설치", "pg_trgm" in exts, f"pg_trgm {exts.get('pg_trgm')}")

# 한국어 FTS 설정이 있는지 — 이번 테스트의 핵심 전제
cfgs = [r[0] for r in conn.execute("SELECT cfgname FROM pg_ts_config").fetchall()]
check("simple 설정 존재", "simple" in cfgs)
check("english 설정 존재", "english" in cfgs)
print(f"  참고: 설치된 text search 설정 {len(cfgs)}종 — "
      f"korean 존재 여부 = {'korean' in cfgs}")

finish("test_connection")
