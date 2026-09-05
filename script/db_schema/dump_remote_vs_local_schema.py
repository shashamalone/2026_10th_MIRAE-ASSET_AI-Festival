"""
원격 RDB(SQL API 뒤 PostgreSQL)의 실제 스키마와, RDB 로직(src/tools/rdb_schema.py)이 전제하는 로컬 스키마를
각각 덤프해 대조 문서를 만든다. 원격은 information_schema로 테이블·행수·컬럼·타입을, 로컬은 RDB_SCHEMA·
ATTRIBUTE_CATALOG·JOIN 보강 테이블 정의를 읽는다. 출력: docs/docs_DB/<날짜>_remote_vs_local_db_schema.md.
실행: repo 루트에서 `python script/db_schema/dump_remote_vs_local_schema.py` (mirea python, .env의 RDB_API_BASE_URL 사용).
제약: 행수는 COUNT(*)라 대형 테이블(vec.*)에서 수 초 걸린다. 값(데이터)은 덤프하지 않는다.
"""
from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from dotenv import load_dotenv  # noqa: E402

load_dotenv()
from agent import utils  # noqa: E402
from tools import rdb_schema as r  # noqa: E402

conn = utils.get_pg_connection()
q = lambda s: utils.run_sql(conn, s)  # noqa: E731

# ---------------------------------------------------------------------------
# 원격
# ---------------------------------------------------------------------------
# SQL API는 분당 요청 한도(실측 429)와 응답 100행 상한이 있다. 테이블마다 질의하지 않고 최소 횟수로 끝낸다:
# 테이블 목록 1회, 전체 컬럼 1회, 행수는 UNION ALL 한 문장.
# 원본 4개(raw.prbd01n001 등)는 원격에서 VIEW라 BASE TABLE만 고르면 빠진다(2026-09-05 실측). 뷰도 포함한다.
tables = q("SELECT table_schema, table_name, table_type FROM information_schema.tables "
           "WHERE table_schema NOT IN ('pg_catalog','information_schema') AND table_type IN ('BASE TABLE','VIEW') "
           "ORDER BY table_schema, table_name")
# SQL API가 결과 행수를 자른다(2026-09-05 실측: 컬럼 목록 한 번에 다 안 옴). 총건수를 먼저 확인하고
# OFFSET 페이지로 나눠 받는다. 요청 간 간격은 분당 한도 때문이다.
import time  # noqa: E402

COL_WHERE = "WHERE table_schema NOT IN ('pg_catalog','information_schema')"
total_cols = int(q(f"SELECT COUNT(*) AS n FROM information_schema.columns {COL_WHERE}")[0]["n"])
all_cols: list[dict] = []
PAGE = 100  # SQL API가 응답을 100행으로 자른다(실측)
for offset in range(0, total_cols, PAGE):
    all_cols.extend(q(f"SELECT table_schema, table_name, column_name, data_type FROM information_schema.columns {COL_WHERE} "
                      f"ORDER BY table_schema, table_name, ordinal_position LIMIT {PAGE} OFFSET {offset}"))
    time.sleep(1.2)
assert len(all_cols) == total_cols, f"컬럼 목록 불완전: {len(all_cols)}/{total_cols}"
remote: dict[str, dict] = {f"{t['table_schema']}.{t['table_name']}": {"rows": None, "cols": [], "type": t["table_type"]} for t in tables}
for c in all_cols:
    full = f"{c['table_schema']}.{c['table_name']}"
    if full in remote:
        remote[full]["cols"].append((c["column_name"], c["data_type"]))
count_sql = " UNION ALL ".join(f"SELECT '{full}' AS t, COUNT(*) AS n FROM {full}" for full in remote)
try:
    for row in q(count_sql):
        remote[row["t"]]["rows"] = int(row["n"])
except Exception as exc:  # noqa: BLE001
    for full in remote:
        remote[full]["rows"] = f"집계 실패({type(exc).__name__})"

# ---------------------------------------------------------------------------
# 로컬(RDB 로직 전제)
# ---------------------------------------------------------------------------
local_tables = {dom: info["table"] for dom, info in r.DOMAIN_TABLE_INFO.items()}
join_specs = {(s.join_table, s.join_alias, s.join_on): [] for d in r.ATTRIBUTE_CATALOG.values() for s in d.values() if s.join_table}
for dom, cat in r.ATTRIBUTE_CATALOG.items():
    for concept, s in cat.items():
        if s.join_table:
            join_specs[(s.join_table, s.join_alias, s.join_on)].append((dom, concept, s.column))
csv_headers = {}
for p in sorted((ROOT / "data" / "enriched").glob("*.csv")):
    with p.open(encoding="utf-8-sig", newline="") as fh:
        header = next(csv.reader(fh))
        rows = sum(1 for _ in fh)
    csv_headers[p.name] = (rows, header)

# ---------------------------------------------------------------------------
# 문서
# ---------------------------------------------------------------------------
today = date.today().isoformat()
out = ROOT / "docs" / "docs_DB" / f"{today}_remote_vs_local_db_schema.md"
out.parent.mkdir(parents=True, exist_ok=True)
L: list[str] = []
w = L.append
w(f"# 원격 DB vs 로컬 RDB 로직 스키마 대조\n")
w(f"작성일 {today} · 원격: `{utils.RDB_API_BASE_URL}` (information_schema 실측) · 로컬: `src/tools/rdb_schema.py` 정의 · "
  f"데이터 기준일 {r.DATA_SNAPSHOT_DATE}\n")
w("이 문서는 스크립트 `script/db_schema/dump_remote_vs_local_schema.py`가 생성한다. 값(데이터)은 담지 않고 구조만 담는다.\n")

# 1. 요약
w("## 1. 요약\n")
w("| 구분 | 내용 |\n|---|---|")
w(f"| 원격 테이블 수 | {len(remote)}개 (스키마 {len({k.split('.')[0] for k in remote})}종: "
  + ", ".join(sorted({k.split('.')[0] for k in remote})) + ") |")
w(f"| 로컬 로직이 조회하는 원본 테이블 | {len(local_tables)}개: " + ", ".join(f"`{t}`({d})" for d, t in local_tables.items()) + " |")
w(f"| 로컬 로직이 JOIN하는 보강 테이블 | " + ", ".join(f"`{jt}`" for jt, _, _ in join_specs) + " |")
diffs = []
for dom, tbl in local_tables.items():
    rc = {c for c, _ in remote.get(tbl, {}).get("cols", [])}
    lc = set(r.RDB_SCHEMA[dom]["properties"].keys())
    diffs.append((dom, tbl, sorted(lc - rc), sorted(rc - lc)))
w("| 원본 테이블 컬럼 불일치 | " + ("없음 (4개 테이블 전부 컬럼 집합 동일)" if all(not a and not b for _, _, a, b in diffs)
  else "; ".join(f"{d}: 로컬만 {a} / 원격만 {b}" for d, _, a, b in diffs if a or b)) + " |")
missing_joins = [jt for jt, _, _ in join_specs if jt not in remote]
w("| 보강 테이블 불일치 | " + (", ".join(f"`{jt}` 원격 부재" for jt in missing_joins) if missing_joins else "없음") + " |")
w("")

# 2. 원격
w("## 2. 원격 DB (실측)\n")
w("### 2.1 테이블 목록과 행수\n")
w("| 스키마.테이블 | 종류 | 행수 | 컬럼 수 | 로컬 로직 사용 |\n|---|---|---:|---:|---|")
used = set(local_tables.values()) | {jt for jt, _, _ in join_specs}
for full, info in remote.items():
    use = "원본 조회" if full in local_tables.values() else ("JOIN 보강" if full in used else "-")
    rows = f"{info['rows']:,}" if isinstance(info["rows"], int) else str(info["rows"])
    w(f"| `{full}` | {'뷰' if info.get('type') == 'VIEW' else '테이블'} | {rows} | {len(info['cols'])} | {use} |")
w("")
w("### 2.2 테이블별 컬럼 구성\n")
for full, info in remote.items():
    rows = f"{info['rows']:,}" if isinstance(info["rows"], int) else str(info["rows"])
    w(f"#### `{full}` ({rows}행, {len(info['cols'])}열)\n")
    w("| 컬럼 | 타입 |\n|---|---|")
    for c, t in info["cols"]:
        w(f"| `{c}` | {t} |")
    w("")

# 3. 로컬
w("## 3. 로컬 RDB 로직 스키마 (`src/tools/rdb_schema.py`)\n")
w("RDB 검색 노드는 이 정의를 유일한 스키마 진실로 쓴다. 개념(한국어) → 컬럼 매핑은 ATTRIBUTE_CATALOG, 컬럼 설명은 RDB_SCHEMA, "
  "하위유형 조건은 SUBTYPE_CONDITION_MAP, 실질 기준일은 DOMAIN_AS_OF다.\n")
w("### 3.1 도메인 → 테이블 · 실질 기준일\n")
w("| 도메인 | 테이블 | 실질 기준일 | 판매가능 정책 | 원격 행수 |\n|---|---|---|---|---:|")
for dom, tbl in local_tables.items():
    pol = r.DOMAIN_SALE_POLICY.get(dom, {})
    n = remote.get(tbl, {}).get("rows", "?")
    w(f"| {dom} | `{tbl}` | {getattr(r, 'DOMAIN_AS_OF', {}).get(dom, '-')} | {pol.get('mode','-')}"
      f"{(' ('+pol['condition']+')') if pol.get('condition') else ''} | {n:,} |" if isinstance(n, int) else
      f"| {dom} | `{tbl}` | {getattr(r, 'DOMAIN_AS_OF', {}).get(dom, '-')} | {pol.get('mode','-')} | {n} |")
w("")
w("### 3.2 도메인별 컬럼 정의 (RDB_SCHEMA) 와 카탈로그 개념 매핑\n")
for dom, tbl in local_tables.items():
    props = r.RDB_SCHEMA[dom]["properties"]
    cat = r.ATTRIBUTE_CATALOG[dom]
    col_to_concepts: dict[str, list[str]] = {}
    for concept, s in cat.items():
        col_to_concepts.setdefault(s.column.split(".")[-1], []).append(concept)
    rc = dict(remote.get(tbl, {}).get("cols", []))
    w(f"#### {dom} · `{tbl}` ({len(props)}열 정의, 카탈로그 개념 {len(cat)}개)\n")
    w("| 컬럼 | 원격 타입 | 로컬 타입 | 카탈로그 개념(별칭 포함) | 설명(로컬) |\n|---|---|---|---|---|")
    for col, p in props.items():
        concepts = ", ".join(col_to_concepts.get(col, [])) or "-"
        desc = str(p.get("description", "")).replace("|", "／").replace("\n", " ")[:90]
        w(f"| `{col}` | {rc.get(col, '**원격 없음**')} | {p.get('type','')} | {concepts} | {desc} |")
    w("")
    subs = r.SUBTYPE_CONDITION_MAP.get(dom, {})
    if subs:
        by_col: dict[str, list[str]] = {}
        for k, v in subs.items():
            by_col.setdefault(v["column"], []).append(f"{k}→{v['operator']} {v['value']}")
        w(f"하위유형(subtype) 조건 {len(subs)}개가 쓰는 컬럼: " + "; ".join(f"`{c}`({len(v)}개: {', '.join(v[:4])}{'…' if len(v) > 4 else ''})" for c, v in by_col.items()) + "\n")
w("### 3.3 JOIN 보강 테이블 정의 vs 원격\n")
for (jt, alias, on), users in join_specs.items():
    exists = jt in remote
    w(f"#### `{jt}` AS {alias} ON {on} — 원격 존재: **{'예' if exists else '아니오'}**\n")
    w("| 사용 도메인 | 개념 | 컬럼 |\n|---|---|---|")
    for dom, concept, col in users:
        w(f"| {dom} | {concept} | `{col}` |")
    src_csv = jt.split(".")[-1] + ".csv"
    if src_csv in csv_headers:
        rows, header = csv_headers[src_csv]
        w(f"\n로컬 원천 CSV `data/enriched/{src_csv}`: {rows:,}행, 컬럼 {len(header)}개: " + ", ".join(f"`{h}`" for h in header) + "\n")
    else:
        w("")
    similar = [k for k in remote if k.split(".")[-1] in jt or jt.split(".")[-1].startswith(k.split(".")[-1])]
    if not exists and similar:
        w(f"이름이 비슷한 원격 테이블: " + ", ".join(f"`{k}`({', '.join(c for c, _ in remote[k]['cols'])})" for k in similar) + " — 컬럼 구성이 달라 대체 불가.\n")
w("### 3.4 로컬에만 있는 보강 CSV (`data/enriched/`)\n")
w("| 파일 | 행수 | 컬럼 | 원격 적재 |\n|---|---:|---|---|")
for name, (rows, header) in csv_headers.items():
    stem = name[:-4]
    loaded = any(k.split(".")[-1] == stem or k.split(".")[-1] == stem.replace("_enriched", "") for k in remote)
    w(f"| `{name}` | {rows:,} | {', '.join(header[:12])}{'…' if len(header) > 12 else ''} | {'유사 이름 존재(내용 확인 필요)' if loaded else '없음'} |")
w("")

# 4. 대조 결론
w("## 4. 대조 결론\n")
for dom, tbl, only_local, only_remote in diffs:
    w(f"- {dom} `{tbl}`: " + ("컬럼 집합 동일." if not only_local and not only_remote
      else f"로컬에만 {only_local}, 원격에만 {only_remote}."))
for jt in missing_joins:
    w(f"- 보강 테이블 `{jt}`는 원격에 없다. 이 테이블을 쓰는 카탈로그 개념은 실행 전 `utils.missing_join_tables`가 걸러 "
      f"'보강 테이블 없음'으로 건너뛴다. 해결은 `data/enriched/` CSV를 원격에 적재(`src/kb/build_data_platform.py`, 쓰기 계정 필요)하거나 "
      f"카탈로그를 원본 컬럼으로 되돌리는 것이다.")
w("- 원격에는 로컬 로직이 쓰지 않는 `relations.*`(편입·자회사·테마), `enriched.product_master`·`security_master`, `vec.*`가 있다. "
  "Graph 스토어의 관계 데이터가 RDB에도 있으므로 Graph 경로가 막힐 때 RDB 조인으로 우회할 수 있다.")
out.write_text("\n".join(L), encoding="utf-8")
print(f"wrote {out} ({len(L)} lines, remote tables {len(remote)})")
