# -*- coding: utf-8 -*-
"""NL2SQL 7개 지표와 E1~E7/E12/E13을 결정적으로 평가한다."""
from __future__ import annotations

import argparse
import datetime as dt
import decimal
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))           # 런타임 모듈은 src/ 아래에 있다
from config import BOND_DSN  # noqa: E402

HERE = Path(__file__).resolve().parent
RAW = HERE / "results/nl2sql_raw.json"
OUT = HERE / "results/nl2sql_metrics.json"
ERRORS = HERE / "results/error_cases.json"
GOLD = HERE / "gold/gold_nl2sql.json"
CATALOG = HERE / "contexts/schema_only.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(data, path: Path) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def mask_sql(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"--[^\n]*", " ", text)
    text = re.sub(r"'(?:''|[^'])*'", "''", text)
    text = re.sub(r'"(?:""|[^"])*"', '""', text)
    return text


def safe_sql(text: str) -> bool:
    masked = mask_sql(text).strip()
    if not re.match(r"(?is)^(select\b|with\b)", masked):
        return False
    return ";" not in masked.rstrip(";")


def sql_from_run(run: dict) -> tuple[str | None, str | None]:
    if run.get("error"):
        return None, run["error"]
    try:
        steps = run["plan"]["execution_plan"]
        rdb = [x for x in steps if x["engine"] == "rdb"]
        if len(rdb) != 1 or not isinstance(rdb[0]["query"], str):
            return None, "rdb step이 정확히 1개가 아님"
        if not safe_sql(rdb[0]["query"]):
            return None, "단일 SELECT/WITH가 아님"
        return rdb[0]["query"], None
    except Exception as e:
        return None, f"Planner JSON 오류: {e}"


def catalog_sets(catalog: dict) -> tuple[set[str], set[str]]:
    tables = {t["table"] for t in catalog["tables"]}
    columns = {c["name"] for t in catalog["tables"] for c in t["columns"]}
    return tables, columns


def used_identifiers(query: str, tables: set[str], columns: set[str]) -> tuple[set[str], set[str]]:
    masked = mask_sql(query).lower()
    used_tables = {t for t in tables if re.search(
        rf"(?<![\w.]){re.escape(t.lower())}(?!\w)", masked)}
    used_columns = {c for c in columns if re.search(
        rf"(?<!\w){re.escape(c.lower())}(?!\w)", masked)}
    return used_tables, used_columns


def scalar(v):
    if isinstance(v, decimal.Decimal):
        return str(v.normalize()) if v else "0"
    if isinstance(v, float):
        return format(v, ".12g")
    if isinstance(v, (dt.date, dt.datetime, dt.time)):
        return v.isoformat()
    if isinstance(v, bytes):
        return v.hex()
    return v


def execute(conn, query: str) -> tuple[list[str], list[list], int]:
    with conn.transaction():
        conn.execute("SET TRANSACTION READ ONLY")
        conn.execute("SET LOCAL statement_timeout='5s'")
        cur = conn.execute(query)
        cols = [x.name.lower() for x in (cur.description or [])]
        rows = cur.fetchmany(10001)
        if len(rows) > 10000:
            raise RuntimeError("결과 10,000행 초과")
        normalized = [[scalar(x) for x in row] for row in rows]
        return cols, normalized, len(rows)


def comparable(cols: list[str], rows: list[list], order: bool):
    if len(cols) != len(set(cols)):
        return None
    records = [{c: v for c, v in zip(cols, row)} for row in rows]
    encoded = [json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
               for x in records]
    return encoded if order else Counter(encoded)


def filter_accuracy(query: str, filters: list[dict]) -> float:
    if not filters:
        return 1.0
    compact = re.sub(r"\s+", " ", query).lower()
    hits = 0
    for f in filters:
        col, op, value = f["column"].lower(), re.escape(str(f["operator"])), str(f["value"]).lower()
        val = rf"['\"]?{re.escape(value)}['\"]?"
        hits += bool(re.search(rf"\b{re.escape(col)}\b\s*{op}\s*{val}", compact))
    return hits / len(filters)


def classify(row: dict) -> list[str]:
    errors = []
    if row["hallucinated_schema"]:
        errors.append("E7 Hallucinated Schema")
    if not row["sql_executability"]:
        errors.append("E12 SQL Syntax Error")
        return errors
    if not row["table_accuracy"]:
        errors.append("E1 Wrong Table")
    if row["column_recall"] < 1:
        errors.append("E3 Missing Column")
    if row["filter_semantic_accuracy"] < 1:
        errors.append("E4 Wrong Filter Operator")
    if not row["join_accuracy"]:
        errors.append("E6 Wrong Join")
    structurally_correct = (row["table_accuracy"] and row["column_recall"] == 1 and
                            row["filter_semantic_accuracy"] == 1 and row["join_accuracy"])
    if row["sql_executability"] and not row["execution_accuracy"] and structurally_correct:
        errors.append("E13 Correct SQL / Wrong Result due to data")
    return errors


def evaluate() -> dict:
    raw, gold_doc, catalog = load(RAW), load(GOLD), load(CATALOG)
    gold = {x["question_id"]: x for x in gold_doc["questions"]}
    tables, columns = catalog_sets(catalog)
    rows, gold_results = [], {}
    with psycopg.connect(BOND_DSN, autocommit=True) as conn:
        for qid, q in gold.items():
            gold_results[qid] = execute(conn, q["gold_sql"])
        for run in raw["runs"]:
            q = gold[run["question_id"]]
            query, planner_error = sql_from_run(run)
            item = {k: run[k] for k in ("question_id", "condition", "run", "latency_seconds")}
            item["query"] = query
            item["planner_error"] = planner_error
            item.update({"table_accuracy": 0.0, "column_recall": 0.0,
                         "filter_semantic_accuracy": 0.0, "join_accuracy": 0.0,
                         "sql_executability": 0.0, "execution_accuracy": 0.0,
                         "hallucinated_schema": 0.0, "row_count": None})
            if query:
                actual_tables, actual_cols = used_identifiers(query, tables, columns)
                required_tables = set(q["required_tables"])
                required_cols = set(q["required_columns"]["all"])
                item["table_accuracy"] = float(actual_tables == required_tables)
                item["column_recall"] = (len(actual_cols & required_cols) / len(required_cols)
                                         if required_cols else 1.0)
                item["filter_semantic_accuracy"] = filter_accuracy(query, q["required_filters"])
                gold_joins = max(0, len(required_tables) - 1)
                actual_joins = len(re.findall(r"(?i)\bjoin\b", mask_sql(query)))
                item["join_accuracy"] = float(actual_joins >= gold_joins)
                try:
                    acols, arows, n = execute(conn, query)
                    item["sql_executability"], item["row_count"] = 1.0, n
                    gcols, grows, _ = gold_results[run["question_id"]]
                    if set(acols) == set(gcols):
                        order = q["order_sensitive"]
                        item["execution_accuracy"] = float(
                            comparable(acols, arows, order) == comparable(gcols, grows, order))
                except psycopg.Error as e:
                    item["execution_error"] = f"{e.sqlstate}: {str(e)[:300]}"
                    item["hallucinated_schema"] = float(e.sqlstate in {"42P01", "42703"})
                except Exception as e:
                    item["execution_error"] = f"{type(e).__name__}: {str(e)[:300]}"
            item["errors"] = classify(item)
            rows.append(item)
    metrics = ("table_accuracy", "column_recall", "filter_semantic_accuracy", "join_accuracy",
               "sql_executability", "execution_accuracy", "hallucinated_schema")
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
    for qid, by_c in run1.items():
        vals = [by_c.get(c) for c in ("A", "B", "C")]
        if len([x for x in vals if x]) < 3 or any(x["errors"] for x in vals if x) or \
                len({x["execution_accuracy"] for x in vals if x}) > 1:
            repeats.append(qid)
    taxonomy = Counter(e for x in rows for e in x["errors"])
    result = {"meta": raw["meta"], "aggregate": aggregate,
              "error_taxonomy": dict(taxonomy), "repeat_ids": sorted(repeats), "runs": rows}
    dump(result, OUT)
    errors = load(ERRORS) if ERRORS.exists() else {}
    errors["nl2sql_repeat_ids"] = sorted(repeats)
    errors["nl2sql"] = [x for x in rows if x["errors"]]
    dump(errors, ERRORS)
    print(json.dumps(aggregate, ensure_ascii=False, indent=2))
    print(f"repeat {len(repeats)}: {', '.join(repeats)}")
    return result


def self_test() -> None:
    assert safe_sql("SELECT ';' AS x;")
    assert safe_sql("WITH x AS (SELECT 1) SELECT * FROM x")
    assert not safe_sql("DELETE FROM x")
    assert not safe_sql("SELECT 1; DROP TABLE x")
    tables, cols = {"raw.t"}, {"a", "b"}
    assert used_identifiers("SELECT t.a FROM raw.t t WHERE b > 0", tables, cols) == ({"raw.t"}, {"a", "b"})
    assert filter_accuracy("WHERE x.crd_grd_rank <= 4", [
        {"column": "crd_grd_rank", "operator": "<=", "value": 4}]) == 1
    print("PASS evaluate_sql self-test")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    self_test() if args.self_test else evaluate()


if __name__ == "__main__":
    main()
