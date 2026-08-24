# -*- coding: utf-8 -*-
"""Verified LogicalPlan → constrained PostgreSQL SELECT → evidence rows."""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import psycopg
from psycopg import sql

from config import BOND_DSN
from tools.schema_context import metadata, norm
from tools.validate import validate_entity_count, validate_rows

_OPERATORS = {"==": "=", "!=": "<>", ">": ">", ">=": ">=", "<": "<", "<=": "<="}


@dataclass
class CompiledQuery:
    query: sql.Composed
    params: list
    columns: list[str]
    evidence: list[dict]


@lru_cache(maxsize=1)
def _conn():
    return psycopg.connect(BOND_DSN, autocommit=True)


def _qtable(name: str):
    schema, table = name.split(".")
    return sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(table))


def _aliases(plan: dict, used_tables: set[str]) -> dict[str, str]:
    schema, _, bindings = metadata()
    base = schema["domains"][plan["domain"]]
    out = {base["base_table"]: base["alias"]}
    for table in sorted(used_tables - set(out)):
        stem = table.rsplit(".", 1)[-1]
        candidate = "e" if stem.endswith("enriched") else stem[0]
        while candidate in out.values():
            candidate += "x"
        out[table] = candidate
    return out


def _binding_expr(binding: dict, aliases: dict[str, str]):
    return sql.SQL("{}.{}").format(sql.Identifier(aliases[binding["table"]]),
                                    sql.Identifier(binding["column"]))


def resolve_entities(conn, plan: dict) -> tuple[dict, dict | None]:
    """모호한 class 조합을 실제 canonical 상품명으로 바꾼다. 유사명 대체는 하지 않는다."""
    if not plan.get("entities"):
        return plan, None
    schema, rules, bindings = metadata()
    entity = plan["entities"][0]
    if entity["mode"] == "exact":
        b = bindings[entity["binding"]]
        query = sql.SQL("SELECT count(*) FROM {} WHERE {} = %s").format(
            _qtable(b["table"]), sql.Identifier(b["column"]))
        count = conn.execute(query, [entity["value"]]).fetchone()[0]
        return plan, validate_entity_count(count, entity)
    if entity["mode"] != "fund_classes":
        return plan, {"code": "ABSTAIN_UNRESOLVED_QUERY", "reason": "지원하지 않는 entity mode"}
    table = schema["domains"]["fund_pub"]["base_table"]
    # stem/class는 후보 탐색에만 쓰고, 실제 실행은 아래에서 확정한 정식명 완전일치 IN으로 한다.
    rows = conn.execute(sql.SQL("SELECT itm_nm FROM {} WHERE itm_nm ILIKE %s").format(_qtable(table)),
                        [f"%{entity['stem']}%" ]).fetchall()
    names = []
    for class_name in entity["classes"]:
        nc = norm(class_name)
        matches = [r[0] for r in rows if norm(r[0]).endswith(nc)]
        if len(matches) != 1:
            return plan, validate_entity_count(0, {"value": f"{entity['stem']} {class_name}"})
        names.append(matches[0])
    updated = dict(plan)
    updated["entities"] = [{"mode": "in", "binding": "fund.product_name", "values": names}]
    return updated, None


def compile_plan(plan: dict) -> CompiledQuery:
    if not plan.get("domain") or plan.get("unresolved"):
        raise ValueError("미해소 LogicalPlan은 컴파일할 수 없습니다")
    schema, rules, bindings = metadata()
    domain = schema["domains"][plan["domain"]]
    referenced = list(plan["select"])
    referenced += [x["binding"] for x in plan.get("filters") or []]
    referenced += [x["binding"] for x in plan.get("order") or []]
    referenced += [x["binding"] for x in plan.get("entities") or [] if x.get("binding")]
    unknown = set(referenced) - set(bindings)
    if unknown:
        raise ValueError(f"등록되지 않은 binding: {sorted(unknown)}")
    for binding_id in plan["select"]:
        if "select" not in bindings[binding_id]["usage"]:
            raise ValueError(f"SELECT 금지 binding: {binding_id}")
    used_tables = {bindings[x]["table"] for x in referenced}
    aliases = _aliases(plan, used_tables)
    base = domain["base_table"]

    joins = []
    for table in sorted(used_tables - {base}):
        rule = next((j for j in schema["joins"]
                     if {j["left"], j["right"]} == {base, table}), None)
        if not rule:
            raise ValueError(f"허용되지 않은 JOIN: {base} ↔ {table}")
        left, right = rule["left"], rule["right"]
        joins.append(sql.SQL(" JOIN {} {} ON {}.{} = {}.{}").format(
            _qtable(right), sql.Identifier(aliases[right]),
            sql.Identifier(aliases[left]), sql.Identifier(rule["left_key"]),
            sql.Identifier(aliases[right]), sql.Identifier(rule["right_key"])))
    if len(joins) > rules["max_joins"]:
        raise ValueError("JOIN 상한 초과")

    select_exprs = [_binding_expr(bindings[x], aliases) for x in plan["select"]]
    query = sql.SQL("SELECT {} FROM {} {}").format(
        sql.SQL(",").join(select_exprs), _qtable(base), sql.Identifier(aliases[base]))
    query += sql.Composed(joins)
    params, where = [], []
    for item in plan.get("entities") or []:
        b = bindings[item["binding"]]
        expr = _binding_expr(b, aliases)
        if item["mode"] == "exact":
            where.append(sql.SQL("{} = %s").format(expr))
            params.append(item["value"])
        elif item["mode"] == "in":
            where.append(sql.SQL("{} = ANY(%s)").format(expr))
            params.append(item["values"])
        else:
            raise ValueError(f"해소되지 않은 entity mode: {item['mode']}")
    for item in plan.get("filters") or []:
        b = bindings[item["binding"]]
        if "filter" not in b["usage"]:
            raise ValueError(f"FILTER 금지 binding: {b['id']}")
        if item["operator"] not in _OPERATORS:
            raise ValueError(f"지원하지 않는 operator: {item['operator']}")
        where.append(sql.SQL("{} {} %s").format(
            _binding_expr(b, aliases), sql.SQL(_OPERATORS[item["operator"]])))
        params.append(item["value"])
    if where:
        query += sql.SQL(" WHERE ") + sql.SQL(" AND ").join(where)
    order = []
    for item in plan.get("order") or []:
        b = bindings[item["binding"]]
        if "sort" not in b["usage"]:
            raise ValueError(f"SORT 금지 binding: {b['id']}")
        direction = item.get("direction", "desc").upper()
        if direction not in {"ASC", "DESC"}:
            raise ValueError(f"정렬 방향 오류: {direction}")
        expr = sql.SQL("{} {}").format(_binding_expr(b, aliases), sql.SQL(direction))
        if item.get("nulls") in {"first", "last"}:
            expr += sql.SQL(f" NULLS {item['nulls'].upper()}")
        order.append(expr)
    if order:
        query += sql.SQL(" ORDER BY ") + sql.SQL(",").join(order)
    if plan.get("limit"):
        query += sql.SQL(" LIMIT %s")
        params.append(min(int(plan["limit"]), rules["max_rows"]))

    evidence = [{"binding": x, "label": bindings[x]["label"],
                 "source_table": bindings[x]["table"], "source_column": bindings[x]["column"],
                 "as_of": plan["as_of"]["value"], "as_of_basis": plan["as_of"]["basis"],
                 "source_kind": "organizer" if bindings[x]["table"].startswith("raw.")
                 else "derived_from_organizer"}
                for x in plan["select"]]
    return CompiledQuery(query=query, params=params,
                         columns=[bindings[x]["column"] for x in plan["select"]], evidence=evidence)


def execute(plan: dict, conn=None) -> dict:
    conn = conn or _conn()
    conn.execute(f"SET statement_timeout = {metadata()[1]['statement_timeout_ms']}")
    resolved, abstain = resolve_entities(conn, plan)
    if abstain:
        return {"rows": [], "columns": [], "evidence": [], "abstain": abstain}
    compiled = compile_plan(resolved)
    with conn.transaction():
        conn.execute("SET TRANSACTION READ ONLY")
        cur = conn.execute(compiled.query, compiled.params)
        raw = cur.fetchall()
        columns = [d.name for d in cur.description]
    rows = [dict(zip(columns, row)) for row in raw]
    abstain = validate_rows(rows, metadata()[1]["max_rows"])
    return {"rows": rows if not abstain else [], "columns": columns,
            "evidence": compiled.evidence, "abstain": abstain}
