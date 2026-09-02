import json
import psycopg

# q06-single-test.py -> 6_rdb_vertical_slice -> vectordb_test -> 프로젝트 루트
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from agent.query_frame import extract
from config import BOND_DSN
from tools import rdb
from tools.schema_context import ground

question = (
    "VOO의 정식 상품명, 기초지수, 운용사, 총보수, AUM, 현재가와 거래량을 알려줘. "
    "ISIN, 가격 기준일, AUM 기준일을 근거로 제시해줘."
)

frame = extract(question, use_audit=False)
plan = ground(question, frame)

print("\n[1] HCX Query Frame")
print(json.dumps({
    "domain_candidates": frame.get("domain_candidates"),
    "task": frame.get("task"),
    "entities": frame.get("entities"),
    "requested_fields": frame.get("requested_fields"),
    "guard": frame.get("_guard"),
}, ensure_ascii=False, indent=2))

print("\n[2] Grounding 결과")
print(json.dumps({
    "domain": plan.get("domain"),
    "entities": plan.get("entities"),
    "unresolved": plan.get("unresolved"),
}, ensure_ascii=False, indent=2))

with psycopg.connect(BOND_DSN, autocommit=True) as conn:
    print("\n[3] DB에서 VOO 존재 확인")
    rows = conn.execute("""
        SELECT pd_itm_no, pd_abrv_nm, pd_nm, pd_grp_no
        FROM raw.etf_gl_master
        WHERE pd_itm_no = %s OR pd_abrv_nm = %s
    """, ["VOO", "VOO"]).fetchall()
    print(rows)

    print("\n[4] 생성 Plan 실제 실행")
    result = rdb.execute(plan, conn=conn)
    print(json.dumps({
        "abstain": result.get("abstain"),
        "columns": result.get("columns"),
        "row_count": len(result.get("rows") or []),
    }, ensure_ascii=False, indent=2, default=str))