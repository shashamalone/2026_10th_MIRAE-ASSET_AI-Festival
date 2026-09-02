# -*- coding: utf-8 -*-
"""35문항 routing 지표 4종과 E8~E11을 평가한다."""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "results/routing_raw.json"
GOLD = HERE / "gold/gold_routing.json"
OUT = HERE / "results/routing_metrics.json"
ERRORS = HERE / "results/error_cases.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(data, path: Path) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def shape(plan: list[dict]) -> tuple[set[str], set[tuple[str, str]], set[tuple[str, str]]]:
    ids = {x["id"]: x["engine"] for x in plan}
    engines = {x["engine"] for x in plan}
    # 같은 engine 안에서 몇 단계로 쪼갤지는 Planner 자유다. cross-engine 의존만 평가한다.
    edges = {(ids[d], x["engine"]) for x in plan for d in x.get("depends_on", [])
             if d in ids and ids[d] != x["engine"]}
    nodes = list(ids)
    reach = set((d, x["id"]) for x in plan for d in x.get("depends_on", []) if d in ids)
    changed = True
    while changed:
        changed = False
        for a, b in list(reach):
            for c, d in list(reach):
                if b == c and (a, d) not in reach:
                    reach.add((a, d)); changed = True
    parallel = set()
    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            if (a, b) not in reach and (b, a) not in reach:
                parallel.add(tuple(sorted((ids[a], ids[b]))))
    return engines, edges, parallel


def score(actual: dict | None, gold: dict, planner_error: str | None = None) -> dict:
    result = {"engine_selection_accuracy": 0.0, "dependency_accuracy": 0.0,
              "parallelization_accuracy": 0.0, "unnecessary_engine_call_rate": 0.0,
              "query_type_accuracy": 0.0, "errors": []}
    if planner_error or not isinstance(actual, dict) or not isinstance(actual.get("execution_plan"), list):
        result["errors"] = ["E10 Missing Engine"]
        result["planner_error"] = planner_error or "Planner JSON 오류"
        return result
    try:
        ae, ad, ap = shape(actual["execution_plan"])
        ge, gd, gp = shape(gold["execution_plan"])
    except Exception as e:
        result["errors"] = ["E10 Missing Engine"]
        result["planner_error"] = f"Planner plan 구조 오류: {e}"
        return result
    result["engine_selection_accuracy"] = float(ae == ge)
    result["dependency_accuracy"] = float(ad == gd)
    result["parallelization_accuracy"] = float(ap == gp)
    steps = actual["execution_plan"]
    extra = sum(x.get("engine") not in ge for x in steps)
    result["unnecessary_engine_call_rate"] = extra / len(steps) if steps else 0.0
    result["query_type_accuracy"] = float(actual.get("query_type") == gold["query_type"])
    missing = len(ge - ae)
    if missing:
        result["errors"].append("E10 Missing Engine")
    if extra:
        result["errors"].append("E11 Unnecessary Engine")
    if ae != ge and not missing and not extra:
        result["errors"].append("E8 Wrong Engine")
    if ad != gd or ap != gp:
        result["errors"].append("E9 Wrong Dependency")
    return result


def evaluate() -> dict:
    raw, gold_doc = load(RAW), load(GOLD)
    gold = {x["question_id"]: x for x in gold_doc["questions"]}
    rows = []
    for run in raw["runs"]:
        item = {k: run[k] for k in ("question_id", "condition", "run", "latency_seconds")}
        item.update(score(run.get("plan"), gold[run["question_id"]], run.get("error")))
        rows.append(item)
    metrics = ("engine_selection_accuracy", "dependency_accuracy", "parallelization_accuracy",
               "unnecessary_engine_call_rate", "query_type_accuracy")
    aggregate = {}
    for condition in ("A", "B", "C"):
        rs = [x for x in rows if x["condition"] == condition]
        aggregate[condition] = {m: (sum(x[m] for x in rs) / len(rs) if rs else 0) for m in metrics}
        aggregate[condition]["n"] = len(rs)
    run1 = defaultdict(dict)
    for x in rows:
        if x["run"] == 1:
            run1[x["question_id"]][x["condition"]] = x
    repeats = []
    primary = metrics[:4]
    for qid, by_c in run1.items():
        vals = [by_c.get(c) for c in ("A", "B", "C")]
        signatures = {tuple(x[m] for m in primary) for x in vals if x}
        if len([x for x in vals if x]) < 3 or any(x["errors"] for x in vals if x) or len(signatures) > 1:
            repeats.append(qid)
    taxonomy = Counter(e for x in rows for e in x["errors"])
    result = {"meta": raw["meta"], "aggregate": aggregate,
              "error_taxonomy": dict(taxonomy), "repeat_ids": sorted(repeats), "runs": rows}
    dump(result, OUT)
    errors = load(ERRORS) if ERRORS.exists() else {}
    errors["routing_repeat_ids"] = sorted(repeats)
    errors["routing"] = [x for x in rows if x["errors"]]
    dump(errors, ERRORS)
    print(json.dumps(aggregate, ensure_ascii=False, indent=2))
    print(f"repeat {len(repeats)}: {', '.join(repeats)}")
    return result


def self_test() -> None:
    gold = {"execution_plan": [
        {"id": "A", "engine": "graph", "depends_on": []},
        {"id": "B", "engine": "rdb", "depends_on": ["A"]},
        {"id": "C", "engine": "vector", "depends_on": ["A"]}],
        "query_type": "x"}
    assert score({**gold}, gold)["engine_selection_accuracy"] == 1
    graph_gold = {"execution_plan": [gold["execution_plan"][0]], "query_type": "x"}
    bad = {"execution_plan": graph_gold["execution_plan"] + [
        {"id": "D", "engine": "rdb", "depends_on": []}], "query_type": "x"}
    assert score(bad, graph_gold)["unnecessary_engine_call_rate"] > 0
    print("PASS evaluate_routing self-test")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    self_test() if args.self_test else evaluate()


if __name__ == "__main__":
    main()
