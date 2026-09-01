# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.5
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Graph-only QA 파이프라인 — 13문항 스테이지 배터리
#
# S1 frame → S2 validate → S3 route → S4 seed → S5 fragment → S6~S9
# text2sparql.run → S10 render 를 13문항에 대해 실행하고 문항×스테이지
# 매트릭스를 출력한다. `src/`는 수정하지 않고 이 디렉터리 안의 파일만 새로 만든다.
#
# CLI:
#   python3 stage_battery.py --stages deterministic   # S1(캐시)~S5만, 캐시 없을 때만 HCX
#   python3 stage_battery.py --all                     # 전 스테이지(S1~S10), battery_results.json 저장
#   python3 stage_battery.py --ids B1,E1                # 선택 문항만
#
# 노트북(jupytext --to ipynb 로 변환 후 실행)에서는 인자 없이 deterministic
# 모드로 돌고, battery_results.json 이 있으면 S6~S10 결과를 그 캐시에서 읽어
# 매트릭스에 합쳐 보여준다(HCX 재호출 없이 출력 포함 기록을 남기기 위함).

# %%
import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

# 연속 --all 실행에서 E2·E3·E4 가 HTTP 429(rate exceeded)로 오염됐다. 문항 하나가
# HCX 를 최대 4회(frame 1 + plan 3) 부르므로 문항 사이에 간격을 둔다.
SLEEP_BETWEEN_ITEMS = 10.0


def _find_repo_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / "AGENTS.md").is_file():
            return p
    raise RuntimeError("repo root를 찾지 못함 (AGENTS.md 마커 기준)")


REPO = _find_repo_root(Path.cwd())
sys.path.insert(0, str(REPO / "src"))
DATA_DIR = REPO / "test" / "agent_test" / "Gragh-test"
FRAME_CACHE_PATH = DATA_DIR / "frames_cache.json"
RESULTS_PATH = DATA_DIR / "battery_results.json"

from agent import nodes, query_frame, text2sparql  # noqa: E402
from tools import graph, schema_context  # noqa: E402
from tools import route as route_mod  # noqa: E402
from tools import validate as validate_mod  # noqa: E402
from tools.graph_entity import resolve_entity, resolve_frame_seed  # noqa: E402
from tools.graph_schema import catalog  # noqa: E402

print(f"REPO={REPO}")

# %% [markdown]
# ## {FUND} 선정
#
# `agent_test` 지시서 규칙: oxigraph 에서 `fp:PublicFund` 이면서
# `productShortName`·`hasRiskGrade`·`hasInvestmentRegion`·`hasAssetType`
# 를 모두 가진 실존 펀드를 SELECT 로 뽑고, `resolve_entity` 로 유일 해소되는지
# 확인한 첫 후보를 쓴다. 임의 지정 금지 — 매 실행마다 이 셀이 실제로 선정한다.

# %%
FUND_SELECT_QUERY = """
PREFIX fp: <http://mafest.ai/product#>
SELECT ?f ?sn WHERE {
  ?f a fp:PublicFund ; fp:productShortName ?sn ;
     fp:hasRiskGrade ?g ; fp:hasInvestmentRegion ?r ; fp:hasAssetType ?a .
}
ORDER BY ?f
LIMIT 20
"""


def select_fund() -> str:
    rows = graph.sparql(FUND_SELECT_QUERY)
    print(f"[FUND 선정] SPARQL 후보 {len(rows)}건")
    for row in rows:
        name = row["sn"]
        resolved = resolve_entity(name, "PublicFund")
        print(f"  후보 {name!r} -> resolve_entity status={resolved['status']} "
              f"candidates={len(resolved.get('candidates') or [])}")
        if resolved["status"] == "resolved":
            print(f"[FUND 선정 완료] {name!r}")
            return name
    raise RuntimeError("PublicFund 조건을 만족하며 유일 해소되는 펀드를 찾지 못했습니다")


FUND_NAME = select_fund()

# %% [markdown]
# ## 13문항 배터리와 기대치
#
# 각 문항은 `expect_*(ctx)` 로 검증한다. `ctx` 에는 그 문항이 도달한 스테이지까지의
# 산출물(frame/seed/route/result/answer)만 들어있다 — 도달하지 못한 스테이지가
# 필요한 검증은 조용히 건너뛴다(빈 리스트 반환), FAIL 로 표시하지 않는다.

# %%
STAGE_ORDER = ["S1", "S2", "S3", "S4", "S5", "S6-S9", "S10"]
CUTOFF = date(2026, 8, 24)


def _has_row_or_tbox_evidence(evidence: list[dict]) -> bool:
    return any(("row" in e) or (e.get("kind") == "tbox_source") for e in evidence)


def _as_of_violations(evidence: list[dict]) -> list[tuple[str, str]]:
    bad = []
    for e in evidence:
        for k, v in e.items():
            if "as_of" in k and isinstance(v, str):
                try:
                    if date.fromisoformat(v[:10]) > CUTOFF:
                        bad.append((k, v))
                except ValueError:
                    pass
    return bad


def expect_b1(ctx):
    checks = []
    seed = ctx.get("seed")
    if seed:
        cls = (seed.get("entity") or {}).get("class_uri", "") if seed["status"] == "resolved" else ""
        family = cls.split("#")[-1] in {"Company", "Issuer", "Organization", "AssetManager"}
        checks.append(("seed_resolved_company_family", seed["status"] == "resolved" and family,
                       f"status={seed['status']} class={cls}"))
    result = ctx.get("result")
    if result:
        rows, evid = result.get("rows") or [], result.get("evidence") or []
        checks.append(("rows>0", len(rows) > 0, f"rows={len(rows)}"))
        checks.append(("evidence_exists", len(evid) > 0, f"evidence={len(evid)}"))
    return checks


def expect_b2(ctx):
    checks = []
    result = ctx.get("result")
    if result:
        rows, evid = result.get("rows") or [], result.get("evidence") or []
        checks.append(("rows>0", len(rows) > 0, f"rows={len(rows)}"))
        checks.append(("evidence_row_or_tbox", _has_row_or_tbox_evidence(evid),
                       f"evidence_sample={evid[:1]}"))
    return checks


def expect_b3(ctx):
    checks = []
    result = ctx.get("result")
    if result:
        rows = result.get("rows") or []
        ok = result["status"].startswith("abstain") or len(rows) == 0
        checks.append(("abstain_or_zero_rows", ok, f"status={result['status']} rows={len(rows)}"))
    return checks


def expect_e1(ctx):
    checks = []
    result = ctx.get("result")
    if result:
        rows, evid = result.get("rows") or [], result.get("evidence") or []
        checks.append(("rows>0", len(rows) > 0, f"rows={len(rows)}"))
        checks.append(("row_evidence_exists", len(evid) > 0, f"evidence={len(evid)}"))
        bad = _as_of_violations(evid)
        checks.append(("as_of<=cutoff", len(bad) == 0, f"violations={bad[:3]}"))
    return checks


def expect_e2(ctx):
    # 관찰 케이스 — 성공/실패 모두 기록만 하고 배터리 실패로 치지 않는다.
    checks = []
    result = ctx.get("result")
    if result:
        rows = result.get("rows") or []
        checks.append(("observation_only", True,
                       f"OBSERVED status={result['status']} rows={len(rows)}"))
    return checks


def expect_e3(ctx):
    checks = []
    seed = ctx.get("seed")
    if seed:
        cls = (seed.get("entity") or {}).get("class_uri", "") if seed["status"] == "resolved" else ""
        checks.append(("seed_theme", seed["status"] == "resolved" and cls.endswith("#Theme"),
                       f"status={seed['status']} class={cls}"))
    result = ctx.get("result")
    if result:
        rows, evid = result.get("rows") or [], result.get("evidence") or []
        checks.append(("rows>0", len(rows) > 0, f"rows={len(rows)}"))
        checks.append(("evidence_exists", len(evid) > 0, f"evidence={len(evid)}"))
    return checks


def expect_e4(ctx):
    checks = []
    result = ctx.get("result")
    if result:
        rows, evid = result.get("rows") or [], result.get("evidence") or []
        checks.append(("rows>0", len(rows) > 0, f"rows={len(rows)}"))
        checks.append(("tbox_source_evidence", any(e.get("kind") == "tbox_source" for e in evid),
                       f"evidence={evid[:1]}"))
    return checks


def expect_e5(ctx):
    checks = []
    result = ctx.get("result")
    if result:
        checks.append(("status_ambiguous", result["status"] == "abstain_entity_ambiguous",
                       f"status={result['status']}"))
        cands = result.get("candidates") or []
        checks.append(("candidates>=2", len(cands) >= 2, f"candidates={len(cands)}"))
    return checks


def expect_f1(ctx):
    checks = []
    result = ctx.get("result")
    if result:
        rows, evid = result.get("rows") or [], result.get("evidence") or []
        checks.append(("rows>0", len(rows) > 0, f"rows={len(rows)}"))
        checks.append(("tbox_source_evidence", any(e.get("kind") == "tbox_source" for e in evid),
                       f"evidence={evid[:1]}"))
    return checks


def expect_f2(ctx):
    checks = []
    result = ctx.get("result")
    if result:
        rows = result.get("rows") or []
        checks.append(("rows>0", len(rows) > 0, f"rows={len(rows)}"))
        if rows:
            suffixes = ("_as_of", "_source", "_document_title", "_document_publisher",
                       "_document_date", "_document_quote", "_document")
            non_id_keys = [k for k in rows[0] if not any(k.endswith(s) for s in suffixes)]
            checks.append(("outputs>=2", len(non_id_keys) >= 2, f"keys={non_id_keys}"))
    return checks


def expect_f3(ctx):
    checks = []
    result = ctx.get("result")
    if result:
        rows = result.get("rows") or []
        ok = len(rows) == 0 or result["status"].startswith("abstain")
        checks.append(("zero_rows_or_abstain", ok, f"status={result['status']} rows={len(rows)}"))
    ans = ctx.get("answer")
    if ans:
        checks.append(("no_false_negative_phrase", "없음이 확인" not in ans, f"answer={ans[:80]!r}"))
    return checks


def expect_x1(ctx):
    checks = []
    result = ctx.get("result")
    if result:
        rows, evid = result.get("rows") or [], result.get("evidence") or []
        checks.append(("rows==22", len(rows) == 22, f"rows={len(rows)}"))
        checks.append(("evidence==22", len(evid) == 22, f"evidence={len(evid)}"))
    ans = ctx.get("answer")
    if ans:
        checks.append(("answer_has_as_of_phrase", "관계 기준일" in ans, f"answer_sample={ans[:60]!r}"))
    return checks


def expect_x2(ctx):
    checks = []
    s2 = ctx.get("s2_abstain")
    checks.append(("s2_code", bool(s2) and s2.get("code") == "ABSTAIN_NOT_RELEASED_AS_OF_CUTOFF",
                   f"s2={s2}"))
    stages = ctx.get("stages") or {}
    subsequent = all(stages.get(s) == "SKIP" for s in STAGE_ORDER[2:])
    checks.append(("subsequent_stages_skip", subsequent, f"stages={stages}"))
    return checks


EXPECT = {
    "B1": expect_b1, "B2": expect_b2, "B3": expect_b3,
    "E1": expect_e1, "E2": expect_e2, "E3": expect_e3, "E4": expect_e4, "E5": expect_e5,
    "F1": expect_f1, "F2": expect_f2, "F3": expect_f3,
    "X1": expect_x1, "X2": expect_x2,
}

BATTERY = [
    {"id": "B1", "question": "미래에셋증권이 발행한 채권을 알려줘"},
    {"id": "B2", "question": "국민은행이 발행한 채권의 신용등급을 알려줘"},
    {"id": "B3", "question": "VOO가 발행한 회사채를 알려줘"},
    {"id": "E1", "question": "KODEX 200이 보유한 종목을 비중과 함께 알려줘"},
    {"id": "E2", "question": "삼성전자가 편입된 ETF를 알려줘"},
    {"id": "E3", "question": "우주항공 테마와 연결된 ETF를 알려줘"},
    {"id": "E4", "question": "TIGER 미국S&P500의 투자지역을 알려줘"},
    {"id": "E5", "question": "LVDS ETF가 보유한 종목을 알려줘"},
    {"id": "F1", "question": f"{FUND_NAME}의 위험등급을 알려줘"},
    {"id": "F2", "question": f"{FUND_NAME}의 투자지역과 자산유형을 알려줘"},
    {"id": "F3", "question": f"{FUND_NAME}가 보유한 종목을 알려줘"},
    {"id": "X1", "question": "에코프로와 연결된 자회사 관계를 알려줘. 관계 기준일과 출처도 함께 보여줘"},
    {"id": "X2", "question": "2026-09-01 기준 KODEX 200 보유 종목을 알려줘"},
]
for item in BATTERY:
    item["expect"] = EXPECT[item["id"]]

print("BATTERY ids:", [b["id"] for b in BATTERY])

# %% [markdown]
# ## 스테이지 실행기
#
# 각 스테이지는 독립 try/except 로 감싼다 — 한 스테이지가 실패해도 이후
# 스테이지는 SKIP 으로 표시하고 그 문항 처리를 끝낸 뒤 다음 문항으로 넘어간다.
# `expect_*` 의 개별 assert 성격 검사는 예외를 던지지 않고 (name, passed, detail)
# 튜플만 쌓으므로 문항 간 독립성이 보장된다.

# %%
def _rate_limited(result: dict) -> bool:
    """clova 오류 문자열로만 판별한다 — clova.py 는 건드리지 않는다."""
    blob = json.dumps(result.get("attempts") or [], ensure_ascii=False, default=str)
    return "HTTP 429" in blob or "rate exceeded" in blob.lower() or "42901" in blob


def _compute_plan(question: str, frame: dict) -> dict:
    """S3 route 가 참조하는 plan. relation task 는 nodes.ground_query 와 동일하게 얕은 dict."""
    if frame.get("task") == "relation":
        return {"engine": "graph", "domain": None, "unresolved": [],
                "concepts": [], "entities": frame.get("entities") or []}
    return schema_context.ground(question, frame)


def run_item(item: dict, frame_cache: dict, *, deterministic: bool) -> dict:
    id_, question = item["id"], item["question"]
    stages: dict[str, str] = {}
    ctx = {"id": id_, "question": question}

    # S1 frame
    if id_ in frame_cache:
        frame = frame_cache[id_]
        stages["S1"] = "PASS(cached)"
    else:
        try:
            frame = query_frame.extract(question, use_audit=False)
            frame_cache[id_] = frame
            stages["S1"] = "PASS(hcx)"
        except Exception as exc:
            stages["S1"] = f"FAIL:{type(exc).__name__}:{exc}"
            for s in STAGE_ORDER[1:]:
                stages[s] = "SKIP"
            ctx["stages"] = stages
            return ctx
    ctx["frame"] = frame

    # S2 validate
    try:
        abstain = validate_mod.validate_graph_request(question, frame)
        stages["S2"] = abstain["code"] if abstain else "PASS"
        ctx["s2_abstain"] = abstain
    except Exception as exc:
        stages["S2"] = f"FAIL:{type(exc).__name__}:{exc}"
        abstain = {"code": "HARNESS_ERROR"}
    if stages["S2"] != "PASS":
        for s in STAGE_ORDER[2:]:
            stages[s] = "SKIP"
        ctx["stages"] = stages
        return ctx

    # S3 route
    try:
        plan = _compute_plan(question, frame)
        route = route_mod.select_route(frame, plan)
        stages["S3"] = f"PASS({route['query_type']})"
        ctx["route"] = route
    except Exception as exc:
        stages["S3"] = f"FAIL:{type(exc).__name__}:{exc}"

    # S4 seed
    seed = None
    try:
        seed = resolve_frame_seed(question, frame)
        stages["S4"] = "PASS(resolved)" if seed["status"] == "resolved" else seed["status"]
        ctx["seed"] = seed
    except Exception as exc:
        stages["S4"] = f"FAIL:{type(exc).__name__}:{exc}"

    # S5 fragment
    try:
        if seed and seed.get("status") == "resolved":
            entity = seed["entity"]
            fragment = catalog().select_fragment(question, seed_classes=[entity["class_uri"]], hops=2)
            stages["S5"] = f"PASS(classes={len(fragment.classes)})"
        else:
            stages["S5"] = "SKIP"
    except Exception as exc:
        stages["S5"] = f"FAIL:{type(exc).__name__}:{exc}"

    if deterministic:
        stages["S6-S9"] = "SKIP(deterministic)"
        stages["S10"] = "SKIP(deterministic)"
        ctx["stages"] = stages
        return ctx

    # S6~S9 text2sparql.run (HCX plan 생성 포함, self-correction 최대 3회)
    try:
        result = text2sparql.run(question, frame=frame, execute_rdb=False)
        status = result["status"]
        stages["S6-S9"] = status if status.startswith("abstain") else f"PASS({status})"
        if _rate_limited(result):
            # 429 로 날아간 attempt 가 섞인 결과는 plan 품질 근거로 쓸 수 없다.
            stages["S6-S9"] += "+rate_limited"
            ctx["rate_limited"] = True
        ctx["result"] = result
    except Exception as exc:
        stages["S6-S9"] = f"FAIL:{type(exc).__name__}:{exc}"
        stages["S10"] = "SKIP"
        ctx["stages"] = stages
        return ctx

    # S10 render — nodes.render_answer 를 state dict 로 직접 호출
    try:
        render_route_type = "graph_then_rdb" if result.get("rdb_result") else "graph_only"
        rstatus = result.get("status", "")
        r_abstain = None
        if rstatus.startswith("abstain"):
            r_abstain = {"code": rstatus.upper(), "reason": (result.get("trace") or [rstatus])[-1]}
        state = {"abstain": r_abstain, "route": {"query_type": render_route_type},
                 "results": result, "evidence": result.get("evidence") or []}
        ctx["answer"] = nodes.render_answer(state)["answer"]
        stages["S10"] = "PASS"
    except Exception as exc:
        stages["S10"] = f"FAIL:{type(exc).__name__}:{exc}"

    ctx["stages"] = stages
    return ctx

# %% [markdown]
# ## 캐시 입출력 (frames_cache.json / battery_results.json)

# %%
def load_frame_cache() -> dict:
    if FRAME_CACHE_PATH.is_file():
        return json.loads(FRAME_CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def save_frame_cache(cache: dict) -> None:
    FRAME_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def serialize_ctx(ctx: dict) -> dict:
    result = ctx.get("result") or {}
    return {
        "id": ctx["id"], "question": ctx["question"], "stages": ctx.get("stages"),
        "checks": ctx.get("checks"), "answer": ctx.get("answer"),
        "rate_limited": bool(ctx.get("rate_limited")),
        "seed_status": (ctx.get("seed") or {}).get("status"),
        "route_query_type": (ctx.get("route") or {}).get("query_type"),
        "result_status": result.get("status"),
        "rows_count": len(result.get("rows") or []),
        "evidence_count": len(result.get("evidence") or []),
        "rows_sample": (result.get("rows") or [])[:3],
        "candidates_count": len(result.get("candidates") or []),
    }


def save_battery_results(results: dict) -> None:
    payload = {id_: serialize_ctx(ctx) for id_, ctx in results.items()}
    RESULTS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                            encoding="utf-8")


def load_battery_results() -> dict | None:
    if RESULTS_PATH.is_file():
        return json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    return None

# %% [markdown]
# ## 매트릭스·검증 요약 출력

# %%
def print_matrix(results: dict) -> None:
    widths = [4] + [22] * len(STAGE_ORDER)
    header = ["ID"] + STAGE_ORDER

    def fmt_row(cells):
        return " | ".join(str(c).ljust(w)[:w] for c, w in zip(cells, widths))

    print(fmt_row(header))
    print("-+-".join("-" * w for w in widths))
    for item in BATTERY:
        ctx = results.get(item["id"])
        if not ctx:
            continue
        stages = ctx.get("stages") or {}
        print(fmt_row([item["id"]] + [stages.get(s, "-") for s in STAGE_ORDER]))
    # 매트릭스 칸 폭에 잘리므로 429 오염 문항은 따로 한 줄로 남긴다.
    limited = [i["id"] for i in BATTERY
               if (results.get(i["id"]) or {}).get("rate_limited")]
    print(f"rate_limited(HTTP 429) 문항: {limited or '없음'}")


def print_check_summary(results: dict) -> None:
    print("\n=== 문항별 기대 검증 ===")
    for item in BATTERY:
        ctx = results.get(item["id"])
        if not ctx:
            continue
        checks = ctx.get("checks") or []
        if not checks:
            print(f"[{item['id']}] checks: (이 스테이지 깊이에서는 검증 대상 없음)")
            continue
        for name, passed, detail in checks:
            mark = "PASS" if passed else "FAIL"
            print(f"[{item['id']}] {mark:4} {name}: {detail}")


def merge_with_cached(results: dict, cached: dict) -> dict:
    """deterministic 실행 결과에 battery_results.json 의 S6-S9/S10 을 얹어 보여준다."""
    merged = {}
    for id_, ctx in results.items():
        row = dict(ctx)
        row["stages"] = dict(ctx.get("stages") or {})
        if id_ in cached:
            c = cached[id_]
            for stage_key in ("S6-S9", "S10"):
                if (c.get("stages") or {}).get(stage_key):
                    row["stages"][stage_key] = c["stages"][stage_key]
            row["answer"] = c.get("answer")
            row["checks"] = c.get("checks") or row.get("checks")
            row["rate_limited"] = bool(c.get("rate_limited"))
            row["_cached_from"] = "battery_results.json"
        merged[id_] = row
    return merged

# %% [markdown]
# ## CLI / 실행

# %%
def get_args():
    if "ipykernel" in sys.modules:
        return argparse.Namespace(stages="deterministic", ids=None)
    parser = argparse.ArgumentParser(description="Graph-only QA 13문항 스테이지 배터리")
    parser.add_argument("--stages", choices=["deterministic", "full"], default="full")
    parser.add_argument("--all", action="store_true", help="alias — 기본값(full)과 동일")
    parser.add_argument("--ids", default=None, help="쉼표구분 문항 id, 예: B1,E1")
    args = parser.parse_args()
    if args.all:
        args.stages = "full"
    return args


def run_all(args) -> tuple[dict, bool]:
    ids_filter = {x.strip() for x in args.ids.split(",")} if args.ids else None
    frame_cache = load_frame_cache()
    deterministic = args.stages == "deterministic"
    battery = [b for b in BATTERY if not ids_filter or b["id"] in ids_filter]
    results = {}
    for index, item in enumerate(battery):
        if index and not deterministic:
            time.sleep(SLEEP_BETWEEN_ITEMS)
        ctx = run_item(item, frame_cache, deterministic=deterministic)
        ctx["checks"] = item["expect"](ctx)
        results[item["id"]] = ctx
        print(f"[{item['id']}] stages={ctx['stages']}", flush=True)
    save_frame_cache(frame_cache)
    if not deterministic:
        save_battery_results(results)
    return results, deterministic


# %%
ARGS = get_args()
print(f"모드: stages={ARGS.stages} ids={ARGS.ids or 'ALL'}")
RESULTS, DETERMINISTIC = run_all(ARGS)

print("\n=== 문항×스테이지 매트릭스 ===")
print_matrix(RESULTS)
print_check_summary(RESULTS)

# %%
if DETERMINISTIC:
    CACHED = load_battery_results()
    if CACHED:
        MERGED = merge_with_cached(RESULTS, CACHED)
        print("\n=== S6-S10 포함 매트릭스 (battery_results.json 캐시 합산, HCX 재호출 없음) ===")
        print_matrix(MERGED)
        print_check_summary(MERGED)
        print("\n=== 문항별 답변/ABSTAIN 사유 ===")
        for item in BATTERY:
            row = MERGED.get(item["id"], {})
            print(f"\n[{item['id']}] {item['question']}")
            print(f"  result_status={row.get('result_status')} "
                 f"rows={row.get('rows_count')} evidence={row.get('evidence_count')}")
            print(f"  answer: {(row.get('answer') or '')[:300]}")
    else:
        print("\nbattery_results.json 없음 — `--all` 을 먼저 실행하면 S6-S10 을 캐시에서 합쳐 보여준다.")
