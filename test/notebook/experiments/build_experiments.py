# -*- coding: utf-8 -*-
"""실험 노트북 4종 생성기 (계획 v4).

현재 src/ 를 %%module 셀로 복사한 독립 실험 노트북을 만든다.
재실행하면 src 최신본 기준으로 재생성되므로, 노트북에서 수정 중이면 먼저 백업할 것.

    python test/notebook/experiments/build_experiments.py [main|graph|vector|integrated ...]

인자 없으면 정의된 노트북 전부 생성.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
SRC = ROOT / "src"

SETUP_TMPL = '''\
# === 셀 매직 정의: 각 셀을 실제 모듈로 등록한다 ===
# 사용법: 셀 첫 줄에 `%%module <모듈명> <src 기준 경로>`.
# 셀을 수정하고 재실행하면 sys.modules 가 교체되므로,
# 그 모듈을 import 하는 하위 셀들을 다시 실행하면 수정본이 반영된다.
import json as _json
import sys as _sys
import types as _types
from pathlib import Path

from IPython.core.magic import register_cell_magic

REPO_ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "src").is_dir())
NB_PATH = REPO_ROOT / "test" / "notebook" / "experiments" / "{nb_name}"
RESULTS_DIR = REPO_ROOT / "test" / "notebook" / "experiments" / "results"
RESULTS_DIR.mkdir(exist_ok=True)


@register_cell_magic("module")
def _module_magic(line, cell):
    name, relpath = line.split()
    mod = _types.ModuleType(name)
    mod.__file__ = str(REPO_ROOT / "src" / relpath)
    _sys.modules[name] = mod
    parts = name.split(".")
    for i in range(1, len(parts)):
        pkg = ".".join(parts[:i])
        parent = _sys.modules.setdefault(pkg, _types.ModuleType(pkg))
        setattr(parent, parts[i], _sys.modules.get(name) if i == len(parts) - 1 else _sys.modules.setdefault(".".join(parts[:i + 1]), _types.ModuleType(".".join(parts[:i + 1]))))
    exec(compile(cell, mod.__file__, "exec"), mod.__dict__)
    print(f"registered: {{name}}")


def sync_to_py(dry_run=True):
    """%%module 셀을 src/*.py 로 되쓴다. 최종 채택 시에만 사용 (계획 v4 §10)."""
    nb = _json.loads(NB_PATH.read_text(encoding="utf-8"))
    for c in nb["cells"]:
        src = "".join(c["source"])
        if c["cell_type"] != "code" or not src.startswith("%%module "):
            continue
        first, _, body = src.partition("\\n")
        _, name, relpath = first.split()
        target = REPO_ROOT / "src" / relpath
        old = target.read_text(encoding="utf-8") if target.exists() else None
        if old == body:
            print(f"  same: {{relpath}}")
        elif dry_run:
            print(f"CHANGED: {{relpath}}  (dry_run — 반영하려면 sync_to_py(dry_run=False))")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
            print(f"WROTE: {{relpath}}")
'''


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def code(text):
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": text.splitlines(keepends=True)}


def module_cell(name, rel, body=None):
    body = body if body is not None else (SRC / rel).read_text(encoding="utf-8")
    return code(f"%%module {name} {rel}\n" + body)


def header(exp_id, purpose):
    return md(f"""# {exp_id}

```text
실험 ID: {exp_id}
생성 기준일: 2026-08-28
기준 소스: src 최신본
실험 목적: {purpose}
```

이 노트북은 생성 당시 `src/` 의 복사본을 가진 독립 실험 공간이다 (계획 v4 §3).
`%%module` 셀 수정은 `src/` 에 자동 반영되지 않으며, `sync_to_py(dry_run=False)` 는 최종 채택 시에만 실행한다.""")


def write_nb(name, cells):
    nb = {"cells": cells,
          "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                       "language_info": {"name": "python"}},
          "nbformat": 4, "nbformat_minor": 5}
    out = HERE / name
    out.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out} ({len(cells)} cells)")


# ---------------------------------------------------------------- main baseline

MAIN_QUESTIONS_CELL = '''\
MAIN_TEST_QUESTIONS = [
    {
        "id": "Q01",
        "question": "현재 판매 가능한 원화채권 중 AA- 이상 종목 알려줘",
    },
    {
        "id": "Q06",
        "question": "신용등급 AAAA인 채권 찾아줘",
    },
    {
        "id": "Q08",
        "question": "KODEX AI로봇 ETF 정보 알려줘",
    },
]'''

MAIN_RUN_CELL = '''\
import json
import time

from agent.agent_core import APP


def run_agent(question, qid):
    state = {"question_id": qid, "question": question, "intent": {}, "metadata_context": {},
             "plan": {}, "route": {}, "results": {}, "evidence": [], "abstain": None,
             "trace": [], "answer": ""}
    t0 = time.perf_counter()
    final = APP.invoke(state)
    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    res = final.get("results") or {}
    rows = res.get("rows") or []
    return {
        "question_id": qid,
        "question": question,
        "route": (final.get("route") or {}).get("query_type", ""),
        "intent": final.get("intent") or {},
        "grounding": final.get("metadata_context") or {},
        "validation": final.get("abstain"),
        "results": {"row_count": len(rows), "columns": res.get("columns") or [],
                    "rows_head": rows[:3]},
        "evidence": final.get("evidence") or [],
        "trace": final.get("trace") or [],
        "answer": final.get("answer", ""),
        "elapsed_ms": elapsed,
    }


BASELINE = []
for item in MAIN_TEST_QUESTIONS:
    rec = run_agent(item["question"], item["id"])
    BASELINE.append(rec)
    print(f"[{rec['question_id']}] {rec['elapsed_ms']} ms  route={rec['route'] or '-'}")
    print("  answer:", rec["answer"][:160])
    print("  trace :", " | ".join(rec["trace"]))
    print("-" * 80)'''

MAIN_SAVE_CELL = '''\
out_path = RESULTS_DIR / "main_baseline_0828.json"
out_path.write_text(json.dumps({"experiment_id": "EXP-20260828-main-01",
                                "created": "2026-08-28",
                                "records": BASELINE},
                               ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8")
print("saved:", out_path)'''


def build_main():
    files = [
        ("config", "config.py"),
        ("clova", "clova.py"),
        ("agent.state", "agent/state.py"),
        ("agent.prompt", "agent/prompt.py"),
        ("agent.query_frame", "agent/query_frame.py"),
        ("tools.schema_context", "tools/schema_context.py"),
        ("tools.validate", "tools/validate.py"),
        ("tools.route", "tools/route.py"),
        ("tools.rdb", "tools/rdb.py"),
        ("agent.nodes", "agent/nodes.py"),
        ("agent.agent_core", "agent/agent_core.py"),
    ]
    cells = [
        header("EXP-20260828-main-01", "현재 RDB Agent 결과를 기준선으로 보관 (코드 수정 없음)"),
        code(SETUP_TMPL.format(nb_name="agent_main_0828.ipynb")),
    ]
    for name, rel in files:
        cells.append(md(f"## `src/{rel}`"))
        cells.append(module_cell(name, rel))
    cells += [
        md("# RDB 기준선 실험 (계획 v4 §4)\n\n"
           "이 단계의 목적은 코드를 고치는 것이 아니라 **현재 결과를 기준선으로 보관**하는 것이다.\n"
           "RDB 결과가 실패하더라도 실패 사실을 기록만 한다."),
        code(MAIN_QUESTIONS_CELL),
        code(MAIN_RUN_CELL),
        code(MAIN_SAVE_CELL),
    ]
    write_nb("agent_main_0828.ipynb", cells)


# ---------------------------------------------------------------- vector

DATA_API_BODY = '''\
# -*- coding: utf-8 -*-
"""로컬 pgvector 콘텐츠 인덱스(vec.document_chunk) 적재·검색.

계획서의 `tools.data_api.FinancialDataClient` 는 Azure Data API 클라이언트로 문서에만 있고
구현이 없다. Azure `/db` 는 2026-08-29 만료 + 원격 vec 테이블 0행이므로(사용자 결정)
동일한 호출 형태(`FinancialDataClient.from_env().semantic_search(vec, top_k)`)를
로컬 pgvector 로 구현한다. DDL 은 Azure vec.document_chunk 12컬럼을 미러링한다.
"""
import hashlib
from pathlib import Path

import psycopg

import clova
from config import BOND_DSN

EMBED_DIM = 1024
SCORE_FLOOR = 0.45
DATA_CUTOFF = "2026-08-24"

DDL = """
CREATE SCHEMA IF NOT EXISTS vec;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS vec.document_chunk (
  chunk_id        text PRIMARY KEY,
  document_id     text NOT NULL,
  product_id      text,
  page_number     integer,
  citation_text   text NOT NULL,
  chunk_text      text NOT NULL,
  published_at    date NOT NULL CHECK (published_at <= DATE '2026-08-24'),
  source_url      text NOT NULL,
  content_hash    text NOT NULL,
  embedding_model text NOT NULL,
  embedding_dim   smallint NOT NULL,
  embedding       vector(1024) NOT NULL
);
CREATE INDEX IF NOT EXISTS document_chunk_embedding_hnsw
  ON vec.document_chunk USING hnsw (embedding vector_cosine_ops);
"""

PRODUCT_TABLES = {"fund_pub": ("raw.fund_pub_master", "itm_no"),
                  "etf_kr": ("raw.etf_kr_master", "pd_itm_no")}


def _conn():
    return psycopg.connect(BOND_DSN, autocommit=True)


def _pages(pdf_path: Path) -> list:
    from pypdf import PdfReader
    reader = PdfReader(str(pdf_path))
    return [(page.extract_text() or "").strip() for page in reader.pages]


def _chunks(text: str, limit: int = 2000, piece: int = 1200) -> list:
    # ponytail: 1페이지=1청크, 2000자 초과만 문단 경계 분할. 검색 품질 부족이 실측되면 슬라이딩 윈도우.
    if len(text) <= limit:
        return [text] if text else []
    out, buf = [], ""
    for para in text.split("\\n"):
        if len(buf) + len(para) + 1 > piece and buf:
            out.append(buf.strip())
            buf = ""
        buf += para + "\\n"
    if buf.strip():
        out.append(buf.strip())
    return out


def _assert_product(cur, meta):
    """상품코드가 로컬 RDB 에 실재하는지 검증 — 조용한 오매핑 방지 (빌드 게이트)."""
    table, col = PRODUCT_TABLES[meta["domain"]]
    cur.execute(f"SELECT count(*) FROM {table} WHERE {col} = %s", (meta["product_id"],))
    n = cur.fetchone()[0]
    assert n > 0, f"RDB 에 없는 상품코드: {meta['product_id']} ({table}.{col})"


def ingest(pdf_dir, manifest: dict) -> dict:
    """manifest: {파일명: {product_id, domain, published_at}}. TRUNCATE 후 재적재(멱등)."""
    rows = []
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(DDL)
        for fname, meta in manifest.items():
            path = Path(pdf_dir) / fname
            assert path.is_file(), f"PDF 없음: {path}"
            assert str(meta["published_at"]) <= DATA_CUTOFF, f"look-ahead: {fname}"
            _assert_product(cur, meta)
            doc_id = path.stem
            for pno, page_text in enumerate(_pages(path), start=1):
                for i, chunk in enumerate(_chunks(page_text)):
                    rows.append({
                        "chunk_id": f"{doc_id}:p{pno}:{i}",
                        "document_id": doc_id,
                        "product_id": meta["product_id"],
                        "page_number": pno,
                        "citation_text": f"{doc_id} p.{pno}",
                        "chunk_text": chunk,
                        "published_at": meta["published_at"],
                        "source_url": path.resolve().as_uri(),
                        "content_hash": hashlib.sha256(chunk.encode()).hexdigest(),
                    })
        assert rows, "추출된 텍스트 청크가 없다 — PDF 텍스트 추출 실패 여부를 확인할 것"
        vectors = clova.embed_many([r["chunk_text"] for r in rows])
        cur.execute("TRUNCATE vec.document_chunk")
        cur.executemany(
            "INSERT INTO vec.document_chunk (chunk_id, document_id, product_id, page_number,"
            " citation_text, chunk_text, published_at, source_url, content_hash,"
            " embedding_model, embedding_dim, embedding)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'bge-m3',1024,%s::vector)",
            [(r["chunk_id"], r["document_id"], r["product_id"], r["page_number"],
              r["citation_text"], r["chunk_text"], r["published_at"], r["source_url"],
              r["content_hash"], str([float(x) for x in v]))
             for r, v in zip(rows, vectors)])
        cur.execute("SELECT count(*), count(DISTINCT document_id),"
                    " max(vector_dims(embedding)) FROM vec.document_chunk")
        n, docs, dim = cur.fetchone()
    assert n == len(rows) and dim == EMBED_DIM, (n, dim)
    return {"chunks": n, "documents": docs, "dim": dim}


def index_count() -> int:
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM vec.document_chunk")
            return cur.fetchone()[0]
    except psycopg.errors.UndefinedTable:
        return 0


class FinancialDataClient:
    """계획서 호출 형태 유지 어댑터 — 로컬 pgvector 조회."""

    @classmethod
    def from_env(cls):
        return cls()

    def semantic_search(self, query_vector, top_k: int = 3) -> dict:
        vec_literal = str([float(x) for x in query_vector])
        try:
            with _conn() as conn, conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM vec.document_chunk")
                if cur.fetchone()[0] == 0:
                    return {"status": "pending", "results": [], "raw_top": [],
                            "reason": "content index 미구축 — 근거 없음"}
                cur.execute(
                    "SELECT document_id, product_id, page_number, citation_text, chunk_text,"
                    " published_at, 1 - (embedding <=> %(v)s::vector) AS score"
                    " FROM vec.document_chunk"
                    " ORDER BY embedding <=> %(v)s::vector LIMIT %(k)s",
                    {"v": vec_literal, "k": top_k})
                raw = [{"document_id": r[0], "product_id": r[1], "page_number": r[2],
                        "title": r[3], "quote": r[4][:300],
                        "published_at": str(r[5]), "effective_as_of": str(r[5]),
                        "score": round(float(r[6]), 4)}
                       for r in cur.fetchall()]
        except psycopg.errors.UndefinedTable:
            return {"status": "pending", "results": [], "raw_top": [],
                    "reason": "vec.document_chunk 없음"}
        except psycopg.Error as exc:
            return {"status": "error", "results": [], "raw_top": [], "reason": str(exc)}
        hits = [h for h in raw if h["score"] >= SCORE_FLOOR]
        return {"status": "ok" if hits else "empty", "results": hits,
                "raw_top": [{"document_id": h["document_id"], "score": h["score"]} for h in raw]}
'''

VECTOR_MANIFEST_CELL = '''\
# data/pdf_demo 의 실제 PDF 2개 ↔ 로컬 RDB 실재 상품코드 매핑 (사용자 지정)
# - 국민성장펀드: raw.fund_pub_master.itm_no, 클래스 4개(KR5153480100~103) 중 대표 클래스 종류C
# - TIGER MSCI Korea TR: raw.etf_kr_master.pd_itm_no
PDF_DIR = REPO_ROOT / "data" / "pdf_demo"
MANIFEST = {
    "국민참여형 국민성장펀드.pdf": {
        "product_id": "KR5153480100", "domain": "fund_pub", "published_at": "2026-08-24"},
    "미래에셋TIGERMSCIKOREATotalReturn증권상장지수투자신탁(주식).pdf": {
        "product_id": "KR7310970009", "domain": "etf_kr", "published_at": "2026-08-24"},
}'''

VECTOR_INGEST_CELL = '''\
from tools import data_api

# 멱등 적재: 이미 적재돼 있으면 건너뛴다 (임베딩은 artifacts/embed_cache.json 캐시로 재실행도 저렴)
n = data_api.index_count()
if n == 0:
    print("ingest:", data_api.ingest(PDF_DIR, MANIFEST))
else:
    print(f"index 이미 적재됨: {n} chunks — 재적재하려면 data_api.ingest(PDF_DIR, MANIFEST)")'''

VECTOR_QUESTIONS_CELL = '''\
VECTOR_TEST_QUESTIONS = [
    {
        "id": "V01",
        "question": "국민참여형 국민성장펀드는 어떤 모펀드와 자펀드 구조로 운용되나요?",
        "expected_document": "국민참여형 국민성장펀드",
    },
    {
        "id": "V02",
        "question": "국민참여형 국민성장펀드에서 재정은 손실을 어떻게 우선 부담하나요?",
        "expected_document": "국민참여형 국민성장펀드",
    },
    {
        "id": "V03",
        "question": "국민참여형 국민성장펀드의 주요 투자 대상 산업과 투자 비율을 알려줘",
        "expected_document": "국민참여형 국민성장펀드",
    },
    {
        "id": "V04",
        "question": "국민참여형 국민성장펀드의 자펀드 운용사는 몇 곳이 선정되었나요?",
        "expected_document": "국민참여형 국민성장펀드",
    },
    {
        "id": "V05",
        "question": "TIGER MSCI Korea TR ETF가 추종하는 지수와 기초자산은 무엇인가요?",
        "expected_document": "TIGER MSCI Korea TR",
    },
    {
        "id": "V06",
        "question": "TIGER MSCI Korea TR의 상위 편입 종목과 종목별 비중을 알려줘",
        "expected_document": "TIGER MSCI Korea TR",
    },
    {
        "id": "V07",
        "question": "TIGER MSCI Korea TR 투자 시 발생할 수 있는 주요 위험과 주의사항은 무엇인가요?",
        "expected_document": "TIGER MSCI Korea TR",
    },
    {
        "id": "V08",
        "question": "Kimi 관련 투자상품 정보를 공식 문서에서 찾아줘",
        "expected_document": None,
    },
]'''

VECTOR_FLOW_CELL = '''\
import clova
from tools.data_api import FinancialDataClient

client = FinancialDataClient.from_env()

VECTOR_RESULTS = []

for item in VECTOR_TEST_QUESTIONS:
    query_vector = clova.embed(item["question"])
    result = client.semantic_search(query_vector, top_k=3)

    VECTOR_RESULTS.append({
        "id": item["id"],
        "question": item["question"],
        "expected_document": item["expected_document"],
        "result": result,
    })

    print(f"[{item['id']}] {item['question']}")
    print(" status:", result["status"], "| top:",
          [(h["document_id"][:20], h["score"]) for h in result.get("raw_top", [])])
    print("-" * 80)'''

VECTOR_EVAL_CELL = '''\
import json

# 성공 기준 (계획 v4 §6):
#   V01~V04 → 국민성장펀드 문서가 Top-3 에 포함
#   V05~V07 → TIGER MSCI Korea TR 문서가 Top-3 에 포함
#   V08     → 검색 결과가 없거나 score threshold 미달
DOC_KEY = {"국민참여형 국민성장펀드": "국민성장",
           "TIGER MSCI Korea TR": "tigermscikorea"}


def matches(expected, doc_id):
    return DOC_KEY[expected] in doc_id.replace(" ", "").casefold()


records = []
for r in VECTOR_RESULTS:
    res = r["result"]
    top3 = [h["document_id"] for h in res.get("results", [])]
    if r["expected_document"] is None:
        verdict = "PASS" if res["status"] in ("empty", "pending") or not top3 else "FAIL"
    else:
        verdict = "PASS" if any(matches(r["expected_document"], d) for d in top3) else "FAIL"
    records.append({
        "experiment_id": "EXP-20260828-vector-01",
        "question_id": r["id"],
        "question": r["question"],
        "status": res["status"],
        "verdict": verdict,
        "retrieved_documents": res.get("results", []),
        "raw_top": res.get("raw_top", []),
    })
    print(f"[{r['id']}] {verdict}  status={res['status']}")

out_path = RESULTS_DIR / "vector_0828.json"
out_path.write_text(json.dumps(records, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8")
print("saved:", out_path)'''


def build_vector():
    cells = [
        header("EXP-20260828-vector-01", "PDF 적재와 Vector 검색 단독 검증 (로컬 pgvector)"),
        md("**계획과의 차이(사유)**: 계획 §6의 `tools.data_api.FinancialDataClient` 는 저장소에 구현이 없다.\n"
           "Azure `/db` 는 2026-08-29 만료 + 원격 vec 테이블 0행이므로(사용자 결정: 로컬 테스트)\n"
           "같은 호출 형태를 유지한 채 **로컬 pgvector** 로 구현해 `tools.data_api` 모듈로 등록한다."),
        code(SETUP_TMPL.format(nb_name="agent_vector_0828.ipynb")),
        md("## `src/config.py` / `src/clova.py` (verbatim)"),
        module_cell("config", "config.py"),
        module_cell("clova", "clova.py"),
        md("## `tools.data_api` (신규 — 노트북에서만 존재, 채택 시 `src/tools/data_api.py` 로 승격)"),
        module_cell("tools.data_api", "tools/data_api.py", body=DATA_API_BODY),
        md("# PDF 적재 (계획 v4 §6)\n\nPDF 읽기 → 텍스트 추출(pypdf) → 임베딩(bge-m3) → VectorDB 적재"),
        code(VECTOR_MANIFEST_CELL),
        code(VECTOR_INGEST_CELL),
        md("# Vector 테스트 질문 V01~V08"),
        code(VECTOR_QUESTIONS_CELL),
        code(VECTOR_FLOW_CELL),
        md("# 성공 기준 평가·기록"),
        code(VECTOR_EVAL_CELL),
    ]
    write_nb("agent_vector_0828.ipynb", cells)


# ---------------------------------------------------------------- graph

GRAPH_EXT = '''


# === 실험 확장 (EXP-20260828-graph-01) — 채택 전까지 노트북에만 존재 ===
# 아래 템플릿의 어휘(predicate·URI 패턴)는 로컬 store(1,628,311 triples, cutoff 2026-08-24)
# 실측 프로브로 검증된 것이다:
#   상품: fpi:{etfkr|etfgl|fund|bond}-<코드>, fp:productShortName/productName/productCode
#   기업: fpi:corp-<코드>, fp:organizationName + rdfs:label + skos:altLabel
#   편입: 상품 -fp:hasHolding-> Holding{holdingSecurity, weight, asOf, sourceId, supportedBy}
#   자회사: 기업 -fp:hasSubsidiary-> SubsidiaryRelation{subsidiaryCompany, ownershipPct, asOf, supportedBy}
#   증권↔기업: ?sec fp:issuedByCompany ?corp / 채권 발행: ?bond fp:issuedBy ?issuer
PREFIXES = (
    "PREFIX fp: <http://mafest.ai/product#>\\n"
    "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\\n"
    "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\\n"
    "PREFIX skos: <http://www.w3.org/2004/02/skos/core#>\\n"
    "PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\\n"
)
DATA_CUTOFF = "2026-08-24"


def _lit(text: str) -> str:
    return '"' + str(text).replace("\\\\", "\\\\\\\\").replace('"', '\\\\"') + '"'


def _q(body: str) -> list:
    return sparql(PREFIXES + body)


def _result(rows, status=None, **extra):
    out = {"status": status or ("ok" if rows else "empty"), "rows": rows}
    out.update(extra)
    return out


def product_info(short_name: str) -> dict:
    """G01/G02: 상품 URI·정식명·코드·투자지역."""
    rows = _q(f"""
SELECT ?product ?name ?code ?region_label WHERE {{
  ?product fp:productShortName {_lit(short_name)} .
  OPTIONAL {{ ?product fp:productName ?name }}
  OPTIONAL {{ ?product fp:productCode ?code }}
  OPTIONAL {{ ?product fp:hasInvestmentRegion ?r . ?r rdfs:label ?region_label .
             FILTER(lang(?region_label) = "ko") }}
}}""")
    return _result(rows)


def product_classifications(short_name: str) -> dict:
    """G08: 상품에 연결된 분류 개체(투자지역·자산유형·테마·위험등급 등)."""
    rows = _q(f"""
SELECT ?pred ?node ?node_label ?node_type WHERE {{
  ?product fp:productShortName {_lit(short_name)} ; ?pred ?node .
  ?node rdf:type ?node_type .
  FILTER(?node_type IN (fp:InvestmentRegion, fp:AssetType, fp:Theme, fp:RiskGrade,
                        fp:FundType, fp:Currency, fp:ManagementStrategy, fp:LeverageType))
  OPTIONAL {{ ?node rdfs:label ?node_label . FILTER(lang(?node_label) = "ko") }}
}}""")
    return _result(rows)


def company_info(name: str) -> dict:
    """G03: 기업 URI + 등록된 다른 이름(rdfs:label, skos:altLabel)."""
    rows = _q(f"""
SELECT ?company ?label ?alt WHERE {{
  ?company rdf:type fp:Company ; fp:organizationName {_lit(name)} .
  OPTIONAL {{ ?company rdfs:label ?label }}
  OPTIONAL {{ ?company skos:altLabel ?alt }}
}}""")
    return _result(rows)


def subsidiaries(company_name: str, limit: int = 30) -> dict:
    """G04: 자회사 관계 + 기준일(asOf)·출처(sourceId, supportedBy 문서 제목)."""
    rows = _q(f"""
SELECT ?relation ?child_name ?ownership_pct ?as_of ?source ?doc_title WHERE {{
  ?parent rdf:type fp:Company ; fp:organizationName {_lit(company_name)} ;
          fp:hasSubsidiary ?relation .
  ?relation fp:subsidiaryCompany ?child .
  ?child fp:organizationName ?child_name .
  OPTIONAL {{ ?relation fp:ownershipPct ?ownership_pct }}
  OPTIONAL {{ ?relation fp:asOf ?as_of }}
  OPTIONAL {{ ?relation fp:sourceId ?source }}
  OPTIONAL {{ ?relation fp:supportedBy ?doc . ?doc fp:documentTitle ?doc_title }}
  FILTER(!BOUND(?as_of) || ?as_of <= "{DATA_CUTOFF}"^^xsd:date)
}} ORDER BY ?child_name LIMIT {int(limit)}""")
    return _result(rows)


def product_holdings(short_name: str, limit: int = 10) -> dict:
    """G05: 상품 → 편입 증권 + 비중 + 기준일."""
    rows = _q(f"""
SELECT ?security_label ?weight ?as_of ?source WHERE {{
  ?product fp:productShortName {_lit(short_name)} ; fp:hasHolding ?h .
  ?h fp:holdingSecurity ?sec .
  OPTIONAL {{ ?sec rdfs:label ?security_label }}
  OPTIONAL {{ ?h fp:weight ?weight }}
  OPTIONAL {{ ?h fp:asOf ?as_of }}
  OPTIONAL {{ ?h fp:sourceId ?source }}
  FILTER(!BOUND(?as_of) || ?as_of <= "{DATA_CUTOFF}"^^xsd:date)
}} ORDER BY DESC(?weight) LIMIT {int(limit)}""")
    return _result(rows)


def etfs_holding_security(security_label: str, limit: int = 20) -> dict:
    """G06/G12: 증권 라벨 → 역방향 → 편입 ETF."""
    rows = _q(f"""
SELECT DISTINCT ?etf ?etf_name ?weight ?as_of WHERE {{
  ?sec rdf:type fp:Security ; rdfs:label {_lit(security_label)} .
  ?h fp:holdingSecurity ?sec .
  ?etf rdf:type fp:ETF ; fp:hasHolding ?h ; fp:productShortName ?etf_name .
  OPTIONAL {{ ?h fp:weight ?weight }}
  OPTIONAL {{ ?h fp:asOf ?as_of }}
}} ORDER BY DESC(?weight) LIMIT {int(limit)}""")
    return _result(rows)


def subsidiary_holding_etfs(company_name: str, limit: int = 50) -> dict:
    """G07: 기업 → 자회사 → (자회사 발행 증권) → 편입 ETF. (ecopro 하드코딩 일반화)"""
    rows = _q(f"""
SELECT DISTINCT ?etf_name ?child_name ?security_label ?weight ?holding_as_of WHERE {{
  ?parent rdf:type fp:Company ; fp:organizationName {_lit(company_name)} ;
          fp:hasSubsidiary ?relation .
  ?relation fp:subsidiaryCompany ?child .
  ?child fp:organizationName ?child_name .
  ?sec fp:issuedByCompany ?child .
  OPTIONAL {{ ?sec rdfs:label ?security_label }}
  ?h fp:holdingSecurity ?sec .
  OPTIONAL {{ ?h fp:weight ?weight }}
  OPTIONAL {{ ?h fp:asOf ?holding_as_of }}
  ?etf rdf:type fp:ETF ; fp:hasHolding ?h ; fp:productShortName ?etf_name .
  FILTER(!BOUND(?holding_as_of) || ?holding_as_of <= "{DATA_CUTOFF}"^^xsd:date)
}} ORDER BY ?etf_name LIMIT {int(limit)}""")
    return _result(rows)


def bond_info(product_name: str) -> dict:
    """G09: 채권 종류(rdf:type)·발행사·신용등급."""
    rows = _q(f"""
SELECT ?bond ?cls ?issuer_name ?rating WHERE {{
  ?bond fp:productName {_lit(product_name)} ; rdf:type ?cls .
  FILTER(?cls IN (fp:CorporateBond, fp:GovernmentBond, fp:SpecialBond, fp:Bond))
  OPTIONAL {{ ?bond fp:issuedBy ?issuer . ?issuer fp:organizationName ?issuer_name }}
  OPTIONAL {{ ?bond fp:hasCreditRating ?r . BIND(REPLACE(STR(?r), ".*#Rating_", "") AS ?rating) }}
}}""")
    return _result(rows)


def fund_holdings_check() -> dict:
    """G10: 펀드 편입 데이터 적재 여부 — empty(관계 없음)와 data_gap(미적재)을 구분."""
    funds = int(_q("SELECT (COUNT(DISTINCT ?f) AS ?n) WHERE { ?f rdf:type fp:PublicFund . ?f fp:hasHolding ?h }")[0]["n"])
    products = int(_q("SELECT (COUNT(DISTINCT ?p) AS ?n) WHERE { ?p fp:hasHolding ?h }")[0]["n"])
    total_funds = int(_q("SELECT (COUNT(DISTINCT ?f) AS ?n) WHERE { ?f rdf:type fp:PublicFund }")[0]["n"])
    status = "ok" if funds else ("data_gap" if products else "empty")
    note = (f"편입 관계 보유 상품 {products}개(전부 ETF), 펀드 {total_funds}개 중 0개 → "
            "펀드 편입 데이터 미적재(data_gap). '펀드가 주식을 편입하지 않는다'가 아니다."
            if status == "data_gap" else "")
    return {"status": status, "rows": [], "funds_with_holdings": funds,
            "products_with_holdings": products, "total_funds": total_funds, "note": note}


def domain_violation(short_name: str, prop: str = "issuedBy") -> dict:
    """G11: TBox rdfs:domain 과 주어 클래스 비교 — 잘못된 온톨로지 관계 거부."""
    subj = _q(f"SELECT DISTINCT ?product ?cls WHERE {{ ?product fp:productShortName {_lit(short_name)} ; rdf:type ?cls }}")
    if not subj:
        return {"status": "empty", "rows": [], "note": "주어 상품 부재"}
    domains = [d["d"] for d in _q(f"SELECT ?d WHERE {{ fp:{prop} rdfs:domain ?d }}")]
    ok_rows = []
    for s in subj:
        for dom in domains:
            if sparql(PREFIXES + f"ASK {{ <{s['cls']}> rdfs:subClassOf* <{dom}> }}"):
                ok_rows.append({"cls": s["cls"], "domain": dom})
    if ok_rows:
        return {"status": "ok", "rows": ok_rows}
    comment = _q(f"SELECT ?c WHERE {{ fp:{prop} rdfs:comment ?c }}")
    return {"status": "abstain_domain_error", "rows": [],
            "subject_classes": sorted({s["cls"] for s in subj}),
            "required_domain": domains,
            "tbox_comment": (comment[0]["c"][:300] if comment else "")}


def product_info_by_code(code: str) -> dict:
    """통합실험 Q02: productCode 로 상품 조회 (shortName 이 모호한 펀드용)."""
    rows = _q(f"""
SELECT ?product ?short_name ?name ?region_label ?risk WHERE {{
  ?product fp:productCode {_lit(code)} .
  OPTIONAL {{ ?product fp:productShortName ?short_name }}
  OPTIONAL {{ ?product fp:productName ?name }}
  OPTIONAL {{ ?product fp:hasInvestmentRegion ?r . ?r rdfs:label ?region_label .
             FILTER(lang(?region_label) = "ko") }}
  OPTIONAL {{ ?product fp:hasRiskGrade ?rg . BIND(REPLACE(STR(?rg), ".*#", "") AS ?risk) }}
}}""")
    return _result(rows)


def etfs_holding_security_like(substr: str, limit: int = 30) -> dict:
    """통합실험 Q03: 증권 라벨 부분일치(영문 별칭 대응) → 편입 ETF + 코드."""
    rows = _q(f"""
SELECT DISTINCT ?etf_name ?etf_code ?security_label ?weight ?as_of WHERE {{
  ?sec rdf:type fp:Security ; rdfs:label ?security_label .
  FILTER(CONTAINS(LCASE(STR(?security_label)), LCASE({_lit(substr)})))
  ?h fp:holdingSecurity ?sec .
  ?etf fp:hasHolding ?h ; fp:productShortName ?etf_name .
  OPTIONAL {{ ?etf fp:productCode ?etf_code }}
  OPTIONAL {{ ?h fp:weight ?weight }}
  OPTIONAL {{ ?h fp:asOf ?as_of }}
}} ORDER BY DESC(?weight) LIMIT {int(limit)}""")
    return _result(rows)


def subsidiary_holding_etf_codes(company_name: str, limit: int = 100) -> dict:
    """통합실험 Q05: 자회사 편입 ETF 의 상품코드 목록 (RDB 랭킹 입력)."""
    rows = _q(f"""
SELECT DISTINCT ?etf_name ?etf_code ?child_name WHERE {{
  ?parent rdf:type fp:Company ; fp:organizationName {_lit(company_name)} ;
          fp:hasSubsidiary ?relation .
  ?relation fp:subsidiaryCompany ?child .
  ?child fp:organizationName ?child_name .
  ?sec fp:issuedByCompany ?child .
  ?h fp:holdingSecurity ?sec .
  ?etf rdf:type fp:ETF ; fp:hasHolding ?h ;
       fp:productShortName ?etf_name ; fp:productCode ?etf_code .
}} ORDER BY ?etf_name LIMIT {int(limit)}""")
    return _result(rows)


def class_counts() -> dict:
    """체크리스트 3번: 주식·ETF·펀드·채권·기업이 모두 조회되는가."""
    out = {}
    for cls in ("Security", "ETF", "PublicFund", "CorporateBond",
                "GovernmentBond", "SpecialBond", "Company"):
        out[cls] = int(_q(f"SELECT (COUNT(?s) AS ?n) WHERE {{ ?s rdf:type fp:{cls} }}")[0]["n"])
    return out
'''

GRAPH_STORE_CELL = '''\
import json

man_path = REPO_ROOT / "artifacts" / "oxigraph" / "manifest.json"
man = json.loads(man_path.read_text(encoding="utf-8"))
assert man["cutoff"] == "2026-08-24", (
    f"store cutoff={man['cutoff']} — 2026-08-24 재빌드 필요 "
    "(kb.build_graph 의 CUTOFF 를 08-24 로 바꿔 build(); 기존 store 는 백업 후)")
print("store:", f"{man['triple_count']:,} triples, cutoff", man["cutoff"],
      "| excluded_future:", man["excluded_future_nodes"])'''

GRAPH_QUESTIONS_CELL = '''\
GRAPH_TEST_QUESTIONS = [
    {"id": "G01", "question": "KODEX 200의 상품 URI, 정식 상품명, 상품 코드, 투자지역을 알려줘", "expected": "success"},
    {"id": "G02", "question": "해외 ETF VOO의 상품명, 상품 코드, 투자지역을 알려줘", "expected": "success"},
    {"id": "G03", "question": "삼성전자라는 기업의 Graph URI와 등록된 다른 이름을 알려줘", "expected": "success"},
    {"id": "G04", "question": "에코프로와 연결된 자회사 관계를 알려줘. 관계 기준일과 출처도 함께 보여줘", "expected": "success_or_partial"},
    {"id": "G05", "question": "KODEX 200이 편입한 증권 10개와 각각의 편입 비중을 알려줘", "expected": "success"},
    {"id": "G06", "question": "삼성전자를 편입한 국내 ETF를 알려줘", "expected": "success_or_partial"},
    {"id": "G07", "question": "에코프로의 자회사를 편입한 국내 ETF를 찾아줘", "expected": "success_or_partial"},
    {"id": "G08", "question": "KODEX 200에 연결된 투자지역과 자산유형 분류를 알려줘", "expected": "success"},
    {"id": "G09", "question": "현대해상화재보험7(후)(콜/후)의 채권 종류와 발행사를 알려줘", "expected": "success_or_partial"},
    {"id": "G10", "question": "공모펀드가 편입한 개별 주식과 편입 비중을 알려줘", "expected": "data_gap"},
    {"id": "G11", "question": "VOO가 직접 발행한 회사채를 찾아줘", "expected": "abstain_domain_error"},
    {"id": "G12", "question": "존재하지 않는 가상의 ETF가 편입한 종목을 알려줘", "expected": "empty"},
]'''

GRAPH_RUN_CELL = '''\
import time

from tools import graph as G

CALLS = {
    "G01": lambda: G.product_info("KODEX 200"),
    "G02": lambda: G.product_info("VOO"),
    "G03": lambda: G.company_info("삼성전자"),
    "G04": lambda: G.subsidiaries("에코프로"),
    "G05": lambda: G.product_holdings("KODEX 200", 10),
    "G06": lambda: G.etfs_holding_security("삼성전자"),
    "G07": lambda: G.subsidiary_holding_etfs("에코프로"),
    "G08": lambda: G.product_classifications("KODEX 200"),
    "G09": lambda: G.bond_info("현대해상화재보험7(후)(콜/후)"),
    "G10": lambda: G.fund_holdings_check(),
    "G11": lambda: G.domain_violation("VOO", "issuedBy"),
    "G12": lambda: G.etfs_holding_security("존재하지 않는 가상의 ETF 편입 종목"),
}

# expected → 허용 status (success_or_partial 도 관계가 조회되면 ok 로 본다)
ACCEPT = {"success": {"ok"}, "success_or_partial": {"ok"},
          "data_gap": {"data_gap"}, "abstain_domain_error": {"abstain_domain_error"},
          "empty": {"empty"}}

GRAPH_RESULTS = []
for item in GRAPH_TEST_QUESTIONS:
    t0 = time.perf_counter()
    try:
        res = CALLS[item["id"]]()
    except Exception as exc:
        res = {"status": "error", "rows": [], "note": f"{type(exc).__name__}: {exc}"}
    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    verdict = "PASS" if res["status"] in ACCEPT[item["expected"]] else "FAIL"
    GRAPH_RESULTS.append({"item": item, "res": res, "elapsed_ms": elapsed, "verdict": verdict})
    head = res["rows"][0] if res.get("rows") else res.get("note", "")
    print(f"[{item['id']}] {verdict}  status={res['status']}  rows={len(res.get('rows', []))}"
          f"  {elapsed}ms")
    print("   ", str(head)[:160])
    print("-" * 80)'''

GRAPH_CHECKLIST_CELL = '''\
# 계획 v4 §5 체크리스트 10항 자동 평가
S = {r["item"]["id"]: r["res"] for r in GRAPH_RESULTS}
counts = G.class_counts()

def rows(gid):
    return S[gid].get("rows") or []

checklist = [
    ("1. Store가 열리는가", man["triple_count"] > 0),
    ("2. Triple을 조회할 수 있는가", bool(rows("G01"))),
    ("3. 주식·ETF·펀드·채권·기업 모두 조회", all(v > 0 for v in counts.values())),
    ("4. 상품→편입 증권 이동", S["G05"]["status"] == "ok"),
    ("5. 기업→자회사 이동", S["G04"]["status"] == "ok"),
    ("6. 증권→ETF 역방향 이동", S["G06"]["status"] == "ok"),
    ("7. as_of가 관계 데이터에 포함", any(r.get("as_of") for r in rows("G04"))
        and any(r.get("as_of") for r in rows("G05"))),
    ("8. supportedBy 문서 근거 포함", any(r.get("doc_title") for r in rows("G04"))),
    ("9. empty와 data_gap 구분", S["G10"]["status"] == "data_gap" and S["G12"]["status"] == "empty"),
    ("10. 잘못된 온톨로지 관계 거부", S["G11"]["status"] == "abstain_domain_error"),
]
print("class counts:", counts)
for name, ok in checklist:
    print(("PASS " if ok else "FAIL "), name)'''

GRAPH_SAVE_CELL = '''\
records = []
for r in GRAPH_RESULTS:
    res = dict(r["res"])
    res["rows"] = res.get("rows", [])[:10]
    records.append({"experiment_id": "EXP-20260828-graph-01",
                    "question_id": r["item"]["id"],
                    "question": r["item"]["question"],
                    "expected": r["item"]["expected"],
                    "verdict": r["verdict"],
                    "elapsed_ms": r["elapsed_ms"],
                    **res})
out_path = RESULTS_DIR / "graph_0828.json"
out_path.write_text(json.dumps({"records": records,
                                "checklist": [{"item": n, "ok": ok} for n, ok in checklist],
                                "class_counts": counts},
                               ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8")
print("saved:", out_path)'''


def build_graph_nb():
    graph_body = (SRC / "tools/graph.py").read_text(encoding="utf-8") + GRAPH_EXT
    cells = [
        header("EXP-20260828-graph-01", "Graph 검색 가능 범위 확인 (로컬 pyoxigraph, cutoff 2026-08-24)"),
        md("**전제**: `artifacts/oxigraph` 가 cutoff 2026-08-24 로 재빌드돼 있어야 한다\n"
           "(기존 07-11 cutoff 빌드는 08-24 릴리스 관계 573노드를 제외하고 있었다 — 백업: `artifacts/oxigraph.pre_0828_cutoff0711`)."),
        code(SETUP_TMPL.format(nb_name="agent_graph_0828.ipynb")),
        code(GRAPH_STORE_CELL),
        md("## `src/config.py` (verbatim)"),
        module_cell("config", "config.py"),
        md("## `tools.graph` = src verbatim + 실험 확장(템플릿 함수)"),
        module_cell("tools.graph", "tools/graph.py", body=graph_body),
        md("# Graph 테스트 질문 G01~G12 (계획 v4 §5)"),
        code(GRAPH_QUESTIONS_CELL),
        code(GRAPH_RUN_CELL),
        md("## 체크리스트 (계획 v4 §5)\n\n"
           "`G10` 결과가 빈 배열이라고 해서 \"공모펀드가 주식을 편입하지 않는다\"고 판단하지 않는다 —\n"
           "편입 데이터 미적재(data_gap)인지 먼저 구분한다."),
        code(GRAPH_CHECKLIST_CELL),
        code(GRAPH_SAVE_CELL),
    ]
    write_nb("agent_graph_0828.ipynb", cells)


# ---------------------------------------------------------------- integrated

INT_Q02_CELL = '''\
# Q02: 독립 병렬 검색 — Graph 상품 속성 ∥ Vector 정책 문서 (계획 v4 §7)
import time
from concurrent.futures import ThreadPoolExecutor

import clova
from tools import graph as G
from tools.data_api import FinancialDataClient

client = FinancialDataClient.from_env()
Q02 = "국민성장펀드의 구조와 투자전략 동향 등 찾아서 알려줘"
Q02_CODE = "KR5153480100"  # 국민참여형 국민성장펀드 대표 클래스(종류C) — RDB·Graph 실재 확인됨


def q02_graph():
    info = G.product_info_by_code(Q02_CODE)
    short = (info["rows"][0].get("short_name") if info["rows"] else None)
    cls = G.product_classifications(short) if short else {"status": "empty", "rows": []}
    return {"info": info, "cls": cls}


def q02_vector():
    return client.semantic_search(clova.embed(Q02), top_k=3)


t0 = time.perf_counter()
with ThreadPoolExecutor(max_workers=2) as ex:
    f_g, f_v = ex.submit(q02_graph), ex.submit(q02_vector)
    g_res, v_res = f_g.result(timeout=30), f_v.result(timeout=60)
q02_elapsed = round((time.perf_counter() - t0) * 1000, 1)

# 결과 병합 — 근거가 있는 내용만 (규칙 4)
q02_evidence = []
for r in g_res["info"]["rows"]:
    q02_evidence.append({"source": "graph", "subject": r["product"],
                         "predicate": "productName/region/riskGrade",
                         "object": f"{r.get('name')} | {r.get('region_label')} | {r.get('risk')}",
                         "as_of": "2026-08-21 (fund_pub 실질 기준일)"})
for r in g_res["cls"]["rows"]:
    q02_evidence.append({"source": "graph", "subject": Q02_CODE, "predicate": r["pred"],
                         "object": r.get("node_label") or r["node"], "as_of": None})
for h in v_res.get("results", []):
    q02_evidence.append({"source": "vector", "text": h["quote"], "score": h["score"],
                         "document_id": h["document_id"], "as_of": h["published_at"]})

q02_record = {
    "question_id": "Q02", "question": Q02,
    "mode": "parallel(graph, vector)",
    "graph_status": g_res["info"]["status"], "vector_status": v_res["status"],
    "status": "ok" if q02_evidence else "empty",
    "evidence_n": len(q02_evidence), "elapsed_ms": q02_elapsed,
}
print(q02_record)
for e in q02_evidence[:6]:
    print(" ", {k: (str(v)[:80] if v else v) for k, v in e.items()})'''

INT_Q03_CELL = '''\
# Q03: Graph 또는 Graph → RDB — 실측 전에 경로를 확정하지 않는다 (계획 v4 §7)
import psycopg

from config import BOND_DSN

Q03 = "캠브리콘이 편입된 중국 반도체 ETF를 알려줘"
# 그래프에 '캠브리콘' 한글 라벨은 없다(실측) — 증권 라벨은 영문뿐이므로 한→영 별칭이 필요하다.
ALIAS = {"캠브리콘": "Cambricon"}  # ponytail: 별칭 2~3개 dict. 늘어나면 RDB 영문명 매핑으로 교체

t0 = time.perf_counter()
q03_hits = G.etfs_holding_security_like(ALIAS["캠브리콘"])
etf_names = sorted({r["etf_name"] for r in q03_hits["rows"]})

# 중국·반도체 조건 확인 1차: Graph 분류(Theme·InvestmentRegion)
cond_in_graph = {}
for name in etf_names:
    cls = G.product_classifications(name)
    labels = " ".join(str(r.get("node_label") or r.get("node")) for r in cls["rows"])
    cond_in_graph[name] = {"china": ("중국" in labels or "차이나" in labels or "China" in labels),
                           "semi": ("반도체" in labels)}

# Graph 에 조건이 없는 ETF는 RDB(relations.etf_theme)로 2차 확인 → graph_then_rdb
need_rdb = [n for n, c in cond_in_graph.items() if not (c["china"] and c["semi"])]
rdb_cond = {}
if need_rdb:
    codes = sorted({r["etf_code"] for r in q03_hits["rows"]
                    if r.get("etf_code") and r["etf_name"] in need_rdb})
    with psycopg.connect(BOND_DSN) as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute("SELECT pd_itm_no, string_agg(theme, ',') FROM relations.etf_theme"
                    " WHERE pd_itm_no = ANY(%s) GROUP BY pd_itm_no", (codes,))
        themes = dict(cur.fetchall())
    for r in q03_hits["rows"]:
        if r["etf_name"] in need_rdb and r.get("etf_code") in themes:
            t = themes[r["etf_code"]]
            rdb_cond[r["etf_name"]] = {"china": ("중국" in t or "차이나" in t), "semi": "반도체" in t}
q03_elapsed = round((time.perf_counter() - t0) * 1000, 1)

matched = [n for n in etf_names
           if (cond_in_graph[n]["china"] and cond_in_graph[n]["semi"])
           or (rdb_cond.get(n, {}).get("china") and rdb_cond.get(n, {}).get("semi"))]
route = "graph_only" if matched and not rdb_cond else ("graph_then_rdb" if matched else "graph_then_rdb(조건 미충족)")

q03_record = {
    "question_id": "Q03", "question": Q03, "route_observed": route,
    "holding_etfs": etf_names, "matched_china_semi": matched,
    "cond_in_graph": cond_in_graph, "cond_in_rdb": rdb_cond,
    "status": "ok" if matched else "empty", "elapsed_ms": q03_elapsed,
}
print("route_observed:", route)
print("편입 ETF:", etf_names)
print("중국+반도체 충족:", matched)'''

INT_Q05_CELL = '''\
# Q05: 순차 검색 — 에코프로 →(Graph) 자회사 →(Graph) 편입 ETF →(RDB) 순자산 최대 →(Vector) 위험요인
# 앞 단계 결과가 다음 단계 조건이므로 병렬로 실행하지 않는다 (계획 v4 §7).
Q05 = "에코프로의 자회사를 편입한 ETF 중 순자산이 큰 상품의 위험요인 알려줘"

t0 = time.perf_counter()
step1 = G.subsidiaries("에코프로")                       # Graph: 자회사
step2 = G.subsidiary_holding_etf_codes("에코프로")        # Graph: 자회사 편입 ETF + 코드
codes = sorted({r["etf_code"] for r in step2["rows"] if r.get("etf_code")})

# RDB: 순자산(pd_net_tamt, 실질 기준일 2026-08-21) 최대 — 후보 IN-list 랭킹은
# LogicalPlan compiler 미지원이라 실험에서는 직접 read-only SQL 로 확인한다.
top_etf = None
if codes:
    with psycopg.connect(BOND_DSN) as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute("SELECT pd_itm_no, pd_abrv_nm, pd_net_tamt, du_nav_base_dt"
                    " FROM raw.etf_kr_master WHERE pd_itm_no = ANY(%s)"
                    " ORDER BY pd_net_tamt DESC NULLS LAST LIMIT 1", (codes,))
        row = cur.fetchone()
        if row:
            top_etf = {"code": row[0], "name": row[1], "net_assets": str(row[2]),
                       "as_of": row[3], "source": "raw.etf_kr_master.pd_net_tamt"}

# Vector: 위험요인 문서 — 검색 결과의 product_id 가 해당 ETF 와 다르면 근거로 쓰지 않는다 (규칙 4)
risk = {"status": "skipped", "results": []}
risk_evidence = []
if top_etf:
    risk = client.semantic_search(clova.embed(f"{top_etf['name']} ETF 투자 위험요인"), top_k=3)
    risk_evidence = [h for h in risk.get("results", []) if h.get("product_id") == top_etf["code"]]
q05_elapsed = round((time.perf_counter() - t0) * 1000, 1)

q05_record = {
    "question_id": "Q05", "question": Q05, "mode": "sequential(graph→graph→rdb→vector)",
    "subsidiaries_n": len(step1["rows"]), "candidate_etfs_n": len(codes),
    "candidate_codes": codes[:20], "top_etf": top_etf,
    "vector_status": risk["status"], "risk_evidence_n": len(risk_evidence),
    "risk_note": ("" if risk_evidence else
                  "해당 ETF 의 위험요인 문서가 콘텐츠 인덱스에 미적재 → 이 부분은 '확인할 수 없음' (data_gap)"),
    "status": "partial" if (top_etf and not risk_evidence) else ("ok" if risk_evidence else "empty"),
    "elapsed_ms": q05_elapsed,
}
for k, v in q05_record.items():
    print(f"{k}: {v}")'''

INT_SAVE_CELL = '''\
import json

records = [q02_record, q03_record, q05_record]
out_path = RESULTS_DIR / "integrated_0828.json"
out_path.write_text(json.dumps({"experiment_id": "EXP-20260828-integrated-01",
                                "records": records},
                               ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8")
print("saved:", out_path)

# 실험 종료 후 비교 (계획 v4 §9)
def load(name):
    p = RESULTS_DIR / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

graph_res = load("graph_0828.json")
vector_res = load("vector_0828.json")
main_res = load("main_baseline_0828.json")

print()
print("=== 계획 v4 §9 비교 ===")
if graph_res:
    ok = [r["question_id"] for r in graph_res["records"] if r["verdict"] == "PASS" and r["status"] == "ok"]
    print("1. 답변 가능한 Graph 질문:", ok)
if vector_res:
    print("2. 문서를 검색한 Vector 질문:",
          [r["question_id"] for r in vector_res if r["status"] == "ok"])
if graph_res:
    g04 = next(r for r in graph_res["records"] if r["question_id"] == "G04")
    print("3. Graph 결과 문서 근거(supportedBy):",
          any(row.get("doc_title") for row in g04.get("rows", [])))
if vector_res:
    v_ok = [r for r in vector_res if r["status"] == "ok"]
    print("4. Vector 결과 기준일·출처:",
          all(h.get("published_at") and h.get("title") for r in v_ok
              for h in r["retrieved_documents"]))
print("5. Q03 조건 확인 저장소:", q03_record["route_observed"])
print("6. Q05 순차 실행 가능:", bool(q05_record["top_etf"]))
if main_res:
    print("7. 기존 RDB 결과 유지:",
          [ (r["question_id"], (r["validation"] or {}).get("code", "OK")) for r in main_res["records"] ])'''


def build_integrated():
    graph_body = (SRC / "tools/graph.py").read_text(encoding="utf-8") + GRAPH_EXT
    cells = [
        header("EXP-20260828-integrated-01", "Graph·Vector 단독 검증 결과를 Agent 흐름(Q02·Q03·Q05)에 연결"),
        md("**전제**: `agent_graph_0828.ipynb`(G01~G12)와 `agent_vector_0828.ipynb`(V01~V08) 단독 검증 통과 후 실행한다.\n"
           "RDB 단계는 LogicalPlan compiler 가 IN-list 후보 랭킹을 지원하지 않아 실험에서는 read-only 직접 SQL 로 확인한다\n"
           "(승격 시 binding `etf_kr.net_assets` 경로로 전환)."),
        code(SETUP_TMPL.format(nb_name="agent_integrated_0828.ipynb")),
        md("## 모듈 (graph·vector 노트북과 동일 본문)"),
        module_cell("config", "config.py"),
        module_cell("clova", "clova.py"),
        module_cell("tools.graph", "tools/graph.py", body=graph_body),
        module_cell("tools.data_api", "tools/data_api.py", body=DATA_API_BODY),
        md("# Q02: 독립 병렬 검색 (Graph ∥ Vector)"),
        code(INT_Q02_CELL),
        md("# Q03: Graph 또는 Graph → RDB"),
        code(INT_Q03_CELL),
        md("# Q05: 순차 검색 (Graph → RDB → Vector)"),
        code(INT_Q05_CELL),
        md("# 기록 저장 + 실험 종료 후 비교 (계획 v4 §8·§9)"),
        code(INT_SAVE_CELL),
    ]
    write_nb("agent_integrated_0828.ipynb", cells)


BUILDERS = {"main": build_main, "vector": build_vector, "graph": build_graph_nb,
            "integrated": build_integrated}

if __name__ == "__main__":
    targets = sys.argv[1:] or list(BUILDERS)
    for t in targets:
        if t not in BUILDERS:
            sys.exit(f"unknown notebook: {t} (알려진 것: {', '.join(BUILDERS)})")
        BUILDERS[t]()
