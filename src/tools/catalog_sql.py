"""Read-only semantic metadata and closed-grammar SQL for resolved target steps.

Physical truth belongs exclusively to schema_snapshot. DB descriptions augment
the reviewed Python catalogue; they never override its mappings or become SQL.
No SQL-writing/repair LLM participates in compilation.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
import re
import time

from tools import rdb_schema, schema_snapshot
from tools.rdb_schema import AttributeSpec


class CompileError(ValueError):
    """The requested semantics cannot safely be represented by this compiler."""


MASTER_TABLES = {
    "raw.prbd01n001": "raw.bond_kr_master",
    "raw.pref01n001": "raw.etf_kr_master",
    "raw.pref02n001": "raw.etf_gl_master",
    "raw.prfd01n001": "raw.fund_pub_master",
}
_SEMANTIC_CACHE: dict[tuple, tuple[float, dict]] = {}
_IDENT = re.compile(r"[a-z_][a-z_0-9]*\Z")
_NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")


def normalize(text: str) -> str:
    return "".join(text.split()).casefold()


def domain_metadata(domain: str, snapshot: dict | None = None) -> dict[str, dict]:
    """Fetch <=98 catalog rows; fail closed on truncation/schema/release drift.

    This cache contains semantic rows only, keyed by physical snapshot identity.
    A missing/unavailable catalogue must not stop an already-reviewed mapping.
    Callers decide whether to fall back to the reviewed catalogue, visibly.
    """
    snap = snapshot if snapshot is not None else schema_snapshot.get_snapshot()
    table = rdb_schema.get_domain_entry(domain)["table"]
    physical_columns = set(schema_snapshot.get_columns(table, snap))
    master = MASTER_TABLES[table]
    # The alias contract must hold in this release, not just in old documentation.
    if physical_columns != set(schema_snapshot.get_columns(master, snap)):
        raise CompileError(f"{table} / {master} 컬럼 계약 불일치")
    key = (snap.get("source_url"), schema_snapshot.snapshot_release_id(snap),
           snap.get("fetched_at"), master)
    cached = _SEMANTIC_CACHE.get(key)
    if cached and time.monotonic() - cached[0] < 300:
        return cached[1]
    namespace, name = master.split(".")
    payload = schema_snapshot._request(
        "/db/catalog", params={"table_schema": namespace, "table_name": name},
        base_url=snap.get("source_url"), max_retries=1,
    )
    rows: dict[str, dict] = {}
    for row in payload["rows"]:
        column = row.get("column_name")
        if row.get("table_schema") != namespace or row.get("table_name") != name:
            raise CompileError("카탈로그 응답에 요청하지 않은 테이블이 포함됨")
        if column not in physical_columns or column in rows:
            raise CompileError("카탈로그 컬럼이 물리 스냅샷과 다르거나 중복됨")
        rows[column] = dict(row)
    if set(rows) != physical_columns:
        raise CompileError("카탈로그 응답의 컬럼이 누락됨")
    _SEMANTIC_CACHE[key] = (time.monotonic(), rows)
    return rows


def spec_for_column(domain: str, column: str, metadata: dict) -> AttributeSpec:
    """Reuse reviewed type/ranking/join rules when the same column is known."""
    for spec in rdb_schema.get_attribute_catalog(domain).values():
        if spec.column == column and not spec.join_table:
            return spec
    static = rdb_schema.RDB_SCHEMA[domain]["properties"].get(column, {})
    row = metadata.get(column, {})
    dtype = static.get("type") or row.get("data_type", "")
    numeric = any(token in dtype for token in ("numeric", "decimal", "double", "real", "integer", "bigint"))
    note = "; ".join(f"{key}={row[key]}" for key in
                     ("description", "unit", "zero_null_rule", "transform_expression") if row.get(key))
    return AttributeSpec(column=column, value_type="numeric" if numeric else "text", note=note)


def description_aliases(domain: str, metadata: dict) -> dict[str, AttributeSpec]:
    """Only unambiguous full descriptions; curated semantic keys always win."""
    reviewed = rdb_schema.get_attribute_catalog(domain)
    protected = {normalize(key) for key in reviewed}
    candidates: dict[str, list[str]] = defaultdict(list)
    for column, row in metadata.items():
        description = row.get("description")
        if isinstance(description, str) and description.strip():
            candidates[normalize(description)].append(column)
    return {name: spec_for_column(domain, columns[0], metadata)
            for name, columns in candidates.items() if len(columns) == 1 and name not in protected}


def literal(value) -> str:
    """PostgreSQL escape string, independent of standard_conforming_strings."""
    value = str(value)
    if "\x00" in value:
        raise CompileError("NUL은 SQL 값으로 사용할 수 없습니다")
    return "E'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def identifier(value: str) -> str:
    if not isinstance(value, str) or not _IDENT.fullmatch(value):
        raise CompileError(f"허용되지 않은 식별자: {value!r}")
    return value


def numeric_value(value, column: str, domain: str = "") -> str:
    text = "".join(str(value).split()).replace(",", "")
    multiplier = Decimal(1)
    # Units are converted only where the catalogue explicitly defines them.
    if column == "remaining_days" and text.endswith("년"):
        text, multiplier = text[:-1].strip(), Decimal(365)
    elif column == "remaining_days" and text.endswith("일"):
        text = text[:-1].strip()
    elif column in {"pd_net_tamt", "fd_nast_suma"} or (column == "du_last_aum" and domain == "국내ETF"):
        for unit, factor in (("조원", "1e12"), ("천억원", "1e11"), ("백억원", "1e10"), ("십억원", "1e9"), ("억원", "1e8"), ("만원", "1e4"), ("원", "1")):
            if text.endswith(unit):
                text, multiplier = text[:-len(unit)].strip(), Decimal(factor)
                if not text and unit in {"천억원", "백억원", "십억원"}:
                    text = "1"
                break
    elif column == "du_last_aum" and domain == "해외ETF":
        for currency in ("달러", "USD", "usd"):
            if not text.endswith(currency):
                continue
            text = text[:-len(currency)]
            for suffix, factor in (("조", "1e12"), ("천억", "1e11"), ("백억", "1e10"), ("십억", "1e9"), ("억", "1e8"), ("만", "1e4")):
                if text.endswith(suffix):
                    text, multiplier = text[:-len(suffix)] or "1", Decimal(factor)
                    break
            break
    elif text.endswith("%") and ("rt" in column or "_er_" in column or "yield" in column):
        text = text[:-1].strip()
    if not _NUMBER.fullmatch(text) or len(text) > 64:
        raise CompileError(f"숫자/단위를 확정할 수 없습니다: {value!r}")
    try:
        result = Decimal(text) * multiplier
    except InvalidOperation as exc:
        raise CompileError("유효하지 않은 숫자") from exc
    if not result.is_finite() or abs(result.adjusted()) > 100:
        raise CompileError("숫자가 지원 범위를 벗어났습니다")
    return format(result, "f")


def _numeric_expr(column: str) -> str:
    # All raw live columns are text. CASE protects casts on non-numeric values.
    clean = f"REPLACE(BTRIM({column}::text), ',', '')"
    return (f"CASE WHEN {clean} ~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$' "
            f"THEN {clean}::numeric END")


def _date_value(value) -> str:
    text = re.sub(r"[-./]", "", str(value).strip())
    if not re.fullmatch(r"\d{8}", text):
        raise CompileError(f"날짜는 YYYYMMDD 또는 YYYY-MM-DD여야 합니다: {value!r}")
    try:
        date(int(text[:4]), int(text[4:6]), int(text[6:]))
    except ValueError as exc:
        raise CompileError(f"유효하지 않은 날짜: {value!r}") from exc
    return text


def limit_value(value) -> int | None:
    if value in (None, ""):
        return None
    match = re.fullmatch(r"(?:top\s*)?([0-9]+)(?:\s*개)?", str(value).strip(), re.IGNORECASE)
    if not match or not 1 <= int(match[1]) <= 10000:
        raise CompileError("LIMIT은 1~10000 정수여야 합니다")
    return int(match[1])


def compile_select(resolved: dict, *, apply_limit: bool = True, union_mode: bool = False,
                   snapshot: dict | None = None, metadata: dict | None = None) -> dict:
    """Compile exactly the resolved fields/conditions, never a best-effort subset.

    Runtime requires a verified snapshot; explicit snapshots are for offline tests.
    Unsupported operators, ambiguous values and unresolved columns fail closed.
    """
    if resolved.get("unresolved_concepts") or resolved.get("invalid_conditions"):
        raise CompileError("미해결 개념 또는 무효 조건이 있어 SQL을 생성하지 않습니다")
    snap = snapshot if snapshot is not None else schema_snapshot.get_snapshot()
    domain, table = resolved["domain"], resolved["table"]
    if table != rdb_schema.get_domain_entry(domain)["table"]:
        raise CompileError("도메인과 기본 테이블이 다릅니다")
    schema_snapshot.assert_contract(table_refs=[table], snapshot=snap)
    metadata_notes = []
    if metadata is None:
        try:
            metadata = domain_metadata(domain, snap)
        except Exception as exc:
            metadata = {}
            metadata_notes.append(f"DB 의미 메타를 확인하지 못해 검토된 Python 카탈로그만 사용: {exc}")
    refs: set[tuple[str, str]] = set()
    join_sql: dict[str, str] = {}
    assumptions: list[str] = metadata_notes
    reviewed = rdb_schema.get_attribute_catalog(domain)

    def column(record: dict) -> str:
        name, spec = record.get("column"), record.get("spec")
        if not name:
            raise CompileError(f"컬럼 미확정: {record.get('attribute')}")
        if "." not in name:
            identifier(name)
            refs.add((table, name))
            return f"base.{name}"
        matches = [(key, item) for key, item in reviewed.items()
                   if item == spec and item.column == name and item.join_table]
        if not matches:
            raise CompileError("검토된 카탈로그에 없는 조인/표현식")
        key, trusted = matches[0]
        alias, bare = name.split(".")
        identifier(alias)
        identifier(bare)
        if alias != trusted.join_alias:
            raise CompileError("등록 조인의 별칭 불일치")
        declared = rdb_schema.DERIVED_JOIN_PHYSICAL_REFS.get(key)
        if not declared:
            raise CompileError("조인의 물리 참조 선언이 없습니다")
        refs.update(declared["columns"])
        schema_snapshot.assert_contract(table_refs=declared["tables"], snapshot=snap)
        join_sql[alias] = f"LEFT JOIN {trusted.join_table} AS {alias} ON {trusted.join_on}"
        return name

    def typed(record: dict, *, ranking=False) -> str:
        col, spec = column(record), record.get("spec")
        if spec and spec.value_type == "ordinal":
            if not spec.value_order:
                raise CompileError("순서형 척도 정의가 없습니다")
            return "CASE " + col + " " + " ".join(
                f"WHEN {literal(v)} THEN {i}" for i, v in enumerate(spec.value_order)) + " END"
        if spec and spec.value_type in {"numeric", "date_yyyymmdd_numeric"}:
            expr = _numeric_expr(col)
            rule = metadata.get(record["column"], {}).get("zero_null_rule", "")
            if "측정값 비교" in rule and "값 없음" in rule:
                expr = f"NULLIF(({expr}), 0)"
            return f"({expr})"
        if ranking:
            raise CompileError(f"수치/순서 정렬 규칙 미확정: {record.get('attribute')}")
        return f"{col}::text"

    def predicate(record: dict) -> str:
        if not record.get("valid", True):
            raise CompileError(record.get("invalid_reason") or "무효 조건")
        col, spec = column(record), record.get("spec")
        op, value = record.get("operator"), record.get("value")
        if value is None or not str(value).strip():
            raise CompileError("빈 필터 값")
        if record.get("category_values"):
            if op not in {"eq", "ne", "neq"}:
                raise CompileError("온톨로지 범주 조건의 연산자 미지원")
            negation = "NOT " if op in {"ne", "neq"} else ""
            return f"{col} {negation}IN ({', '.join(literal(v) for v in record['category_values'])})"
        flag = rdb_schema.BINARY_COLUMN_CONTRACTS.get((domain, record["column"]))
        if flag is None and spec and set(spec.known_values) == {"Y", "N"}:
            flag = {"true": "Y", "false": "N", "numeric": False}
        if flag:
            token = normalize(str(value))
            polarity = None
            if token in {"true", "1", "y", "yes", "가능", "참", *flag.get("true_aliases", ())}:
                polarity = "true"
            elif token in {"false", "0", "n", "no", "불가", "거짓", *flag.get("false_aliases", ())}:
                polarity = "false"
            if polarity is not None:
                if op not in {"eq", "ne", "neq"}:
                    raise CompileError("참/거짓 범위 비교는 지원하지 않습니다")
                if op in {"ne", "neq"}:
                    polarity = "false" if polarity == "true" else "true"
                # Equality to the known negative code does not label arbitrary
                # non-positive codes (or NULL) as a verified negative.
                lhs = f"({_numeric_expr(col)})" if flag["numeric"] else f"BTRIM({col}::text)"
                rhs = flag[polarity] if flag["numeric"] else literal(flag[polarity])
                return f"{lhs} = {rhs}"
        if spec and spec.value_type == "categorical" and spec.known_values and op in {"eq", "ne", "neq"}:
            # A reviewed categorical domain is a closed set for equality.  Do
            # not ask an LLM to choose the "nearest" member or weaken equality
            # to a substring: either operation can turn a harmless zero-row
            # result into a silently wrong classification.  Whitespace/case
            # normalization is lossless; anything else must remain blocked.
            matches = [candidate for candidate in spec.known_values
                       if normalize(candidate) == normalize(str(value))]
            if len(matches) != 1:
                raise CompileError(
                    f"등록되지 않은 범주값: {value!r} (컬럼 {record['column']})"
                )
            value = matches[0]
        if record.get("entity_identity"):
            if op != "contains" or record.get("column") != reviewed["상품명"].column:
                raise CompileError("상품식별 표시는 검토된 상품명 contains 조건에만 허용됩니다")
            columns = rdb_schema.PRODUCT_IDENTITY_COLUMNS[domain]
            for identity_column in columns:
                identifier(identity_column)
                refs.add((table, identity_column))
            needle = literal(str(value).replace(" ", "").lower())

            def exact(alias):
                return " OR ".join(f"LOWER(REPLACE({alias}.{name}::text, ' ', '')) = {needle}" for name in columns)

            # The existence check is over the same approved base table. It is
            # generated from reviewed identifiers, never from an LLM SQL string.
            fallback = f"POSITION({needle} IN LOWER(REPLACE({col}::text, ' ', ''))) > 0"
            return (f"(({exact('base')}) OR (NOT EXISTS (SELECT 1 FROM {table} AS identity_probe "
                    f"WHERE {exact('identity_probe')}) AND {fallback}))")
        if op == "in":
            values = value if isinstance(value, list) else [v.strip() for v in str(value).split(",")]
            if not values or any(not str(v).strip() for v in values):
                raise CompileError("빈 IN 조건")
            return f"{col}::text IN ({', '.join(literal(v) for v in values)})"
        if spec and spec.value_type == "ordinal":
            values = record.get("matched_values")
            if values is None:
                raise CompileError("순서형 조건의 값 집합이 확정되지 않았습니다")
            return f"{col} IN ({', '.join(literal(v) for v in values)})" if values else "FALSE"
        if op == "contains" or record.get("org_name_variants") or (spec and spec.is_organization_name):
            if (record.get("org_name_variants") or (spec and spec.is_organization_name)) and op not in {"eq", "contains"}:
                raise CompileError("운용사/발행사 별칭에 지원되지 않는 연산자")
            variants = record.get("org_name_variants") or [value]
            parts = []
            for variant in variants:
                # POSITION uses literal substring semantics: %, _ are not wildcards.
                lhs = f"LOWER(REPLACE({col}::text, ' ', ''))"
                name = str(variant).replace(" ", "").lower()
                if record.get("org_name_variants") or (spec and spec.is_organization_name):
                    # Legal designators are not part of the distinguishing
                    # organization name. Keep equality, not fuzzy substrings.
                    for marker in ("주식회사", "(주)", "㈜"):
                        lhs = f"REPLACE({lhs}, {literal(marker)}, '')"
                        name = name.replace(marker, "")
                rhs = literal(name)
                parts.append(f"POSITION({rhs} IN {lhs}) > 0" if op == "contains" else f"{lhs} = {rhs}")
            return "(" + " OR ".join(parts) + ")"
        operators = {"eq": "=", "ne": "<>", "neq": "<>", "gte": ">=", "lte": "<=", "gt": ">", "lt": "<", ">": ">", "<": "<"}
        if op not in operators and op != "between":
            raise CompileError(f"지원하지 않는 연산자: {op!r}")
        if spec and spec.true_condition:
            if op != "eq":
                raise CompileError("불리언 조건은 eq만 지원합니다")
            true_match = re.fullmatch(r"= '([^']*)'", spec.true_condition)
            if not true_match:
                raise CompileError("등록된 참 조건을 해석할 수 없습니다")
            token = normalize(str(value))
            if token in {"true", "1", "y", "yes", "가능", "판매가능", "판매중", "참"}:
                return f"{col}::text = {literal(true_match[1])}"
            if token in {"false", "0", "n", "no", "불가", "판매불가", "판매완료", "거짓"}:
                return f"{col}::text <> {literal(true_match[1])}"
            if str(value) not in spec.known_values:
                raise CompileError(f"참/거짓 값을 해석할 수 없습니다: {value!r}")
        # Subtype records have no AttributeSpec; their numeric operators are explicit.
        numeric = bool(spec and spec.value_type in {"numeric", "date_yyyymmdd_numeric"}) or op in {">", "<"}
        if numeric:
            lhs = typed(record) if spec else f"({_numeric_expr(col)})"
            convert = _date_value if spec and spec.value_type == "date_yyyymmdd_numeric" else lambda v: numeric_value(v, record["column"], domain)
        else:
            if op not in {"eq", "ne", "neq"}:
                raise CompileError("텍스트 컬럼의 수치/범위 비교는 허용하지 않습니다")
            lhs, convert = f"{col}::text", literal
            if record.get("any_group") == "product_names":
                lhs, convert = f"UPPER(BTRIM({col}::text))", lambda v: literal(str(v).strip().upper())
        if op == "between":
            return f"{lhs} BETWEEN {convert(value)} AND {convert(record.get('value_2', ''))}"
        return f"{lhs} {operators[op]} {convert(value)}"

    where, alternatives = [], defaultdict(list)
    for condition in resolved.get("conditions", []):
        term = predicate(condition)
        if condition.get("any_group"):
            alternatives[condition["any_group"]].append(term)
        else:
            where.append(term)
    where.extend("(" + " OR ".join(items) + ")" for items in alternatives.values())
    if resolved.get("class_suffixes"):
        if domain != "펀드" or not any(c.get("entity_identity") for c in resolved.get("conditions", [])):
            raise CompileError("클래스 접미사 검색에는 펀드명 범위가 필요합니다")
        suffixes = resolved["class_suffixes"]
        if any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9-]{0,30}", s) for s in suffixes):
            raise CompileError("유효하지 않은 클래스 코드")
        where.append("(" + " OR ".join("base.itm_nm ~* " + literal(r"(?:Class|종류)\s*" + re.escape(s) + "$" ) for s in suffixes) + ")")
        refs.add((table, "itm_nm"))
    usd_amount = domain == "해외ETF" and any(
        c.get("column") == "du_last_aum" and str(c.get("value", "")).strip().lower().endswith(("달러", "usd"))
        for c in resolved.get("conditions", []))
    if usd_amount:
        refs.add((table, "pd_trd_ccy"))
        where.append(f"base.pd_trd_ccy = {literal('USD')}")
        assumptions.append("해외ETF AUM의 달러 조건은 거래통화 USD 행에만 적용하며 환율 변환을 하지 않습니다.")
    # These are reviewed domain caveats, now enforced independently of SQL LLMs.
    used_condition_columns = {item.get("column") for item in resolved.get("conditions", [])}
    subtypes = resolved.get("subtype") or []
    if domain in {"국내ETF", "해외ETF"} and "pd_grp_no" not in used_condition_columns:
        group = "ETN" if any("ETN" in value.upper() for value in subtypes) else "ETF"
        refs.add((table, "pd_grp_no"))
        where.append(f"base.pd_grp_no = {literal(group)}")
        assumptions.append(f"{domain} 상품군 조건: {group}")
    sort = resolved.get("sort")
    sort_expr = typed(sort, ranking=True) if sort else None
    if sort_expr:
        where.append(f"{sort_expr} IS NOT NULL")
    fields = list(resolved.get("fields", []))
    if sort and not union_mode:
        fields.append({**sort, "attribute": f"정렬근거({sort['attribute']})"})
    # Return the actual tested values, so a ranking/filter claim is auditable.
    for record in resolved.get("conditions", []):
        if record.get("column") and not any(f.get("column") == record["column"] for f in fields):
            fields.append({**record, "attribute": f"조건근거({record['attribute']})"})
    if usd_amount:
        fields.append({"attribute": "AUM통화", "column": "pd_trd_ccy", "spec": None})
    if not union_mode:
        # Identity + source dates are provenance, not optional display concepts.
        # They remain available even when the intent LLM omits them from fields.
        code_spec = reviewed.get("상품코드")
        if code_spec and not any(f.get("column") == code_spec.column for f in fields):
            fields.append({"attribute": "상품코드", "column": code_spec.column, "spec": code_spec})
        as_of_columns = set()
        for record in fields + ([sort] if sort else []):
            row = metadata.get(record.get("column"), {})
            as_of_columns.update(col.strip() for col in row.get("as_of_column", "").split(",") if col.strip())
        for as_of in sorted(as_of_columns):
            if not schema_snapshot.column_exists(table, as_of, snap):
                assumptions.append(f"기준일 메타가 존재하지 않는 컬럼 {as_of!r}를 참조하여 제외했습니다.")
                continue
            if not any(f.get("column") == as_of for f in fields):
                fields.append({"attribute": f"출처기준일({as_of})", "column": as_of,
                               "spec": spec_for_column(domain, as_of, metadata)})
    output_fields = []

    def output_binding(record: dict, key: str) -> dict:
        name = record["column"]
        info = metadata.get(name, {})
        return {"attribute": record["attribute"], "key": key,
                "column": name if "." in name else f"{table}.{name}",
                "as_of_columns": [c.strip() for c in info.get("as_of_column", "").split(",") if c.strip()],
                "unit": info.get("unit", ""), "zero_null_rule": info.get("zero_null_rule", "")}

    if union_mode:
        mapped = {f["attribute"]: f for f in fields}
        if not sort_expr or not {"상품코드", "상품명"} <= mapped.keys():
            raise CompileError("UNION 투영/정렬 컬럼 미확정")
        projections = [f"{column(mapped['상품코드'])}::text AS code",
                       f"{column(mapped['상품명'])}::text AS name", f"{literal(domain)} AS domain",
                       f"{sort_expr} AS sort_value"]
        output_fields = [output_binding(mapped["상품코드"], "code"),
                         output_binding(mapped["상품명"], "name"),
                         output_binding(sort, "sort_value")]
        if sort.get("spec") and sort["spec"].value_type == "ordinal":
            # sort_value is an internal rank, not the original rating/category.
            output_fields[-1]["attribute"] = f"정렬순위({sort['attribute']})"
    else:
        # Physical output names preserve existing answer provenance and consumers.
        projections, seen = [], set()
        for record in fields + ([sort] if sort else []):
            col = column(record)
            alias = record["column"].split(".")[-1]
            output_fields.append(output_binding(record, alias))
            if alias not in seen:
                projections.append(f"{col} AS {identifier(alias)}")
                seen.add(alias)
        if not projections:
            raise CompileError("SELECT에 확정된 컬럼이 없습니다")
    schema_snapshot.assert_contract(column_refs=refs, snapshot=snap)
    sql = "SELECT " + ", ".join(projections) + f"\nFROM {table} AS base"
    if join_sql:
        sql += "\n" + "\n".join(join_sql.values())
    if where:
        sql += "\nWHERE " + "\n  AND ".join(f"({term})" for term in where)
    if sort and not union_mode:
        order = str(sort.get("order") or "asc").lower()
        if order not in {"asc", "desc"}:
            raise CompileError("정렬 방향은 asc/desc여야 합니다")
        sql += f"\nORDER BY {sort_expr} {order.upper()} NULLS LAST"
        if apply_limit:
            limit = limit_value(sort.get("limit"))
            if limit is not None:
                sql += f"\nLIMIT {limit}"
    return {"sql": sql, "assumptions": assumptions, "compiled": True,
            "compiler": "catalog-sql-v1", "column_refs": sorted(refs),
            "output_fields": output_fields}
