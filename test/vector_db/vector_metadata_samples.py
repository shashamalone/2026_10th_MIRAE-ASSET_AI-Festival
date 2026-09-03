# %% [markdown]
# # VectorDB 메타데이터·샘플 점검
#
# VS Code/Jupyter에서 이 파일을 열고 `# %%` 셀 단위로 실행한다.
# 비밀값과 1024차원 embedding 원문은 출력하지 않는다.
# python test\vector_db\vector_metadata_samples.py



# %% 1. 프로젝트·환경 설정
from __future__ import annotations

import importlib
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from IPython.display import display

ROOT = Path.cwd()
while not (ROOT / "src").exists() and ROOT != ROOT.parent:
    ROOT = ROOT.parent
if not (ROOT / "src").exists():
    raise RuntimeError("프로젝트 루트의 src 폴더를 찾을 수 없습니다")

sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env")

# 공개 read-only SQL API를 검사한다. 직접 PostgreSQL을 검사하려면 False로
# 바꾸고 DATABASE_URL 또는 PG* 값을 실제 DSN으로 설정한다.
USE_SQL_API = True
if USE_SQL_API:
    for key in ("DATABASE_URL", "PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGDATABASE"):
        os.environ.pop(key, None)
    os.environ.setdefault("RDB_API_BASE_URL", "http://40.82.145.44:8000")
    os.environ.setdefault("RDB_API_TIMEOUT", "60")

os.environ.setdefault("VECTOR_SCHEMA", "vec")
os.environ.setdefault("VECTOR_DB_TIMEOUT", "60")

from agent import utils as _utils  # noqa: E402

# 이미 import된 노트북 커널에서도 위 환경변수가 모듈 상수에 반영되게 한다.
utils = importlib.reload(_utils)

SCHEMA = os.environ["VECTOR_SCHEMA"]
SAMPLE_LIMIT = 3
TABLES = (
    "vector_deploy_run",
    "vector_deploy_event",
    "schema_terms_all",
    "source_document",
    "document_product",
    "product_coverage",
    "chunk_embedding",
    "document_chunk",
)
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
assert IDENTIFIER.fullmatch(SCHEMA)
assert all(IDENTIFIER.fullmatch(table) for table in TABLES)

session = utils.get_pg_connection()


def run_sql(statement: str) -> list[dict]:
    """현재 notebook session으로 read-only SQL을 실행한다."""
    return utils.run_sql(session, statement.strip())


print("PROJECT_ROOT:", ROOT)
print("VECTOR_SCHEMA:", SCHEMA)
print("TRANSPORT:", "read-only SQL API" if USE_SQL_API else "direct PostgreSQL")

# %% 2. 테이블별 컬럼·타입 메타데이터
table_list_sql = ", ".join(f"'{table}'" for table in TABLES)
column_rows = run_sql(
    f"""
    SELECT table_name, ordinal_position, column_name, data_type, udt_name,
           is_nullable, column_default
    FROM information_schema.columns
    WHERE table_schema = '{SCHEMA}'
      AND table_name IN ({table_list_sql})
    ORDER BY table_name, ordinal_position
    """
)

display(pd.DataFrame(column_rows))

# %% 3. PK·FK·UNIQUE 제약조건
constraint_rows = run_sql(
    f"""
    SELECT tc.table_name, tc.constraint_name, tc.constraint_type,
           kcu.column_name, kcu.ordinal_position
    FROM information_schema.table_constraints AS tc
    LEFT JOIN information_schema.key_column_usage AS kcu
      ON kcu.constraint_catalog = tc.constraint_catalog
     AND kcu.constraint_schema = tc.constraint_schema
     AND kcu.constraint_name = tc.constraint_name
    WHERE tc.table_schema = '{SCHEMA}'
      AND tc.table_name IN ({table_list_sql})
      AND tc.constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY', 'UNIQUE')
    ORDER BY tc.table_name, tc.constraint_name, kcu.ordinal_position
    """
)

if constraint_rows:
    display(pd.DataFrame(constraint_rows))
else:
    print(
        "information_schema에서 노출된 제약조건이 없습니다. "
        "PK·UNIQUE 인덱스는 다음 인덱스 셀에서 확인하세요."
    )

# %% 4. 인덱스 확인
# guarded API 정책에 따라 pg_indexes가 차단될 수 있으므로 별도 셀로 둔다.
try:
    index_rows = run_sql(
        f"""
        SELECT tablename AS table_name, indexname AS index_name, indexdef AS index_definition
        FROM pg_indexes
        WHERE schemaname = '{SCHEMA}'
          AND tablename IN ({table_list_sql})
        ORDER BY tablename, indexname
        """
    )
    display(pd.DataFrame(index_rows))
except RuntimeError as exc:
    print("인덱스 메타데이터 조회 불가:", exc)

# %% 5. 테이블별 행 수
count_sql = "\nUNION ALL\n".join(
    f"SELECT '{table}' AS table_name, COUNT(*) AS row_count FROM \"{SCHEMA}\".\"{table}\""
    for table in TABLES
)
count_rows = run_sql(count_sql)
display(pd.DataFrame(count_rows).sort_values("table_name").reset_index(drop=True))

# %% 6. 임베딩 모델·차원 품질
embedding_health = run_sql(
    f"""
    SELECT embedding_model, model_revision, embedding_dim,
           COUNT(*) AS row_count,
           COUNT(*) FILTER (WHERE embedding IS NULL) AS null_embeddings,
           MIN(vector_dims(embedding)) AS min_vector_dimension,
           MAX(vector_dims(embedding)) AS max_vector_dimension
    FROM "{SCHEMA}"."chunk_embedding"
    GROUP BY embedding_model, model_revision, embedding_dim
    ORDER BY embedding_model, model_revision
    """
)
display(pd.DataFrame(embedding_health))

# %% 7. 청크–임베딩–상품 연결 상태
join_health = run_sql(
    f"""
    SELECT
      (SELECT COUNT(*) FROM "{SCHEMA}"."document_chunk") AS document_chunks,
      (SELECT COUNT(*) FROM "{SCHEMA}"."chunk_embedding") AS unique_embeddings,
      (
        SELECT COUNT(*)
        FROM "{SCHEMA}"."document_chunk" AS dc
        JOIN "{SCHEMA}"."chunk_embedding" AS ce
          ON ce.content_hash = dc.content_hash
         AND ce.embedding_model = dc.embedding_model
         AND ce.model_revision IS NOT DISTINCT FROM dc.model_revision
      ) AS chunks_with_embedding,
      (
        SELECT COUNT(DISTINCT dc.chunk_id)
        FROM "{SCHEMA}"."document_chunk" AS dc
        JOIN "{SCHEMA}"."document_product" AS dp
          ON dp.document_id = dc.document_id
      ) AS chunks_with_product,
      (SELECT COUNT(*) FROM "{SCHEMA}"."product_coverage") AS product_coverage_rows
    """
)
display(pd.DataFrame(join_health))

# status 값은 배포 환경에서 실제 사용 중인 값을 그대로 집계한다.
coverage_status = run_sql(
    f"""
    SELECT status, COUNT(*) AS row_count
    FROM "{SCHEMA}"."product_coverage"
    GROUP BY status
    ORDER BY row_count DESC, status
    """
)
display(pd.DataFrame(coverage_status))

# %% 8. 테이블별 안전한 출력 샘플
columns_by_table: dict[str, list[dict]] = defaultdict(list)
for row in column_rows:
    columns_by_table[row["table_name"]].append(row)

LONG_TEXT_COLUMNS = {
    "comment",
    "content",
    "embedding_text",
    "citation_text",
    "chunk_text",
    "heading_path",
    "reason",
    "source_url",
}
API_GUARD_BLOCKED_SAMPLE_COLUMNS = {"comment"}


def sample_expressions(table: str) -> tuple[list[str], list[str]]:
    expressions = []
    skipped_columns = []
    for column in columns_by_table.get(table, []):
        name = column["column_name"]
        if USE_SQL_API and name.casefold() in API_GUARD_BLOCKED_SAMPLE_COLUMNS:
            # 서버 SQL guard가 SELECT 컬럼명도 COMMENT 명령으로 판정한다.
            skipped_columns.append(name)
        elif name == "embedding":
            expressions.append('vector_dims("embedding") AS "embedding_dimensions"')
        elif name in LONG_TEXT_COLUMNS:
            expressions.append(f'LEFT("{name}", 300) AS "{name}"')
        else:
            expressions.append(f'"{name}"')
    return expressions, skipped_columns


table_samples: dict[str, list[dict]] = {}
for table in TABLES:
    expressions, skipped_columns = sample_expressions(table)
    if not expressions:
        print(f"[{table}] 서버에 테이블 또는 컬럼이 없습니다")
        continue
    if skipped_columns:
        print(
            f"[{SCHEMA}.{table}] SQL API guard 때문에 샘플에서 제외: "
            + ", ".join(skipped_columns)
        )
    try:
        rows = run_sql(
            f"""
            SELECT {', '.join(expressions)}
            FROM "{SCHEMA}"."{table}"
            LIMIT {SAMPLE_LIMIT}
            """
        )
    except RuntimeError as exc:
        print(f"[{SCHEMA}.{table}] 샘플 조회 실패, 다음 테이블로 계속: {exc}")
        continue
    table_samples[table] = rows
    print(f"\n[{SCHEMA}.{table}] sample={len(rows)}")
    display(pd.DataFrame(rows))

# %% 9. 선택 실행: 실제 의미 검색 샘플
# HyperCLOVA embedding API 호출 비용이 발생하므로 필요할 때만 True로 바꾼다.
RUN_SEMANTIC_SEARCH = False

if RUN_SEMANTIC_SEARCH:
    from agent.get_clova import embed
    from infrastructure.vector_db.client import VectorDBClient

    question = "ETF 투자 시 확인해야 할 주요 위험 요인은 무엇인가?"
    query_vector = embed(question)
    assert len(query_vector) == 1024

    search_results = VectorDBClient(schema=SCHEMA).search(query_vector, top_k=5)
    display(pd.DataFrame(search_results))
else:
    print("실제 의미 검색은 비활성화되어 있습니다")

# %% 10. 세션 정리
session.close()
print("VectorDB metadata session closed")
