"""
utils.build_resolved_schema 결과(테이블·JOIN·컬럼·연산자·값 확정)를 SQL로 결정론 컴파일한다.
흐름: 조건마다 카탈로그 value_type 규칙으로 WHERE 조각을 만들고, 하나라도 표현 불가면 None을 돌려
      호출부(nodes._execute_target_step)가 기존 LLM 초안→SQL 경로로 폴백한다. 부분 컴파일은 하지 않는다.
입력: resolved_schema, apply_limit, union_mode. 출력: {"sql","assumptions","source":"deterministic"} 또는 None.
제약: LLM 폴백으로 매핑된 컬럼(value_type unknown)·단위 불일치·해석 불가 값은 컴파일하지 않는다.
구현 상태: filter/sort/select 계열만 다룬다. 집계·자기조인·CTE가 필요한 질의는 LLM 경로에 남긴다.
"""
from __future__ import annotations

import re

from tools import rdb_schema
from tools.rdb_schema import AttributeSpec

# 주최측이 무효라고 공지한 컬럼. 조건·정렬·필드 어디에 있어도 SQL에 넣지 않고 사유를 남긴다.
# (Q1·Q11·Q13 STALE_DEFINITION 원인. DOMAIN_SALE_POLICY 주석 참고)
FORBIDDEN_COLUMNS: dict[str, str] = {
    "buyable_quantity": "buyable_quantity(매수가능수량)는 주최측이 무효로 공지한 컬럼이라 조건·정렬·출력에 쓰지 않는다",
}

# 플래그(numeric_flag, Y/N categorical) 값을 참/거짓으로 읽는 어휘. 거짓 어휘를 먼저 검사한다 -
# "거래정지 아님"처럼 참 어휘(정지)와 거짓 어휘(아님)가 함께 나오면 부정이 우선이다.
_FALSY = ("아님", "아니오", "아니요", "불가", "없음", "안함", "안 함", "판매완료", "종료", "false", "no")
_TRUTHY = ("가능", "예", "판매중", "판매 중", "있음", "해당", "정지", "true", "yes", "y", "1", "o", "중")

_UNITS_BIG = {"조": 1e12, "억": 1e8, "만": 1e4}
_UNITS_SMALL = {"천": 1e3, "백": 1e2, "십": 1e1}
_CURRENCY_USD = ("달러", "usd", "$", "불")
_CURRENCY_KRW = ("원", "krw")


def parse_korean_number(text: str) -> float | None:
    """'1천억 달러'→1e11, '1000억 원'→1e11, '0.05%'→0.05, '1조 5천억'→1.5e12, '3년'→3.
    통화·%·개수 단위는 값에 영향을 주지 않는다(단위 판단은 호출부). 숫자가 없으면 None."""
    s = str(text or "").replace(",", "").strip()
    tokens = re.findall(r"\d+(?:\.\d+)?|[조억만천백십]", s)
    if not any(t[0].isdigit() for t in tokens):
        return None
    total = 0.0
    section = 0.0  # 만/억/조 단위 아래에서 쌓이는 값
    cur: float | None = None
    for tok in tokens:
        if tok[0].isdigit():
            if cur is not None:      # 숫자가 연달아 오면(예: '3 5') 해석 불가
                return None
            cur = float(tok)
        elif tok in _UNITS_SMALL:
            section += (cur if cur is not None else 1.0) * _UNITS_SMALL[tok]
            cur = None
        else:  # 조/억/만
            section += cur if cur is not None else 0.0
            total += (section if section else 1.0) * _UNITS_BIG[tok]
            section = 0.0
            cur = None
    total += section + (cur if cur is not None else 0.0)
    return total


def _duration_days(text: str) -> float | None:
    """'3년'→1095, '6개월'→180, '90일'→90. 기간 단위가 없으면 None."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*(년|개월|달|일)", str(text or ""))
    if not m:
        return None
    n = float(m.group(1))
    return {"년": n * 365, "개월": n * 30, "달": n * 30, "일": n}[m.group(2)]


def _q(value: str) -> str:
    """SQL 문자열 리터럴. 홑따옴표만 이스케이프한다(값은 카탈로그·의도 분석이 준 짧은 문자열)."""
    return "'" + str(value).replace("'", "''") + "'"


def _norm(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def _flag_truth(value: str) -> bool | None:
    v = _norm(value)
    if any(f in v for f in _FALSY):
        return False
    if any(t in v for t in _TRUTHY):
        return True
    return None


def _currency_mismatch(value: str, spec: AttributeSpec) -> bool:
    """값에 통화가 명시됐는데 컬럼 설명의 통화와 다르면 True. 둘 중 하나가 불명확하면 False."""
    v = str(value).lower()
    note = (spec.note or "").lower()
    val_usd = any(k in v for k in _CURRENCY_USD)
    val_krw = any(k in v for k in _CURRENCY_KRW) and not val_usd
    note_usd = "usd" in note or "달러" in note
    note_krw = "원)" in note or "(원" in note or "원화" in note
    if val_usd and note_krw and not note_usd:
        return True
    if val_krw and note_usd and not note_krw:
        return True
    return False


_OPS = {"eq": "=", "gte": ">=", "lte": "<=", ">": ">", "<": "<", "gt": ">", "lt": "<"}
_NUMERIC_PG_TYPES = {"numeric", "double precision", "integer", "bigint", "real", "smallint", "decimal"}


def _num_col(col: str, bare: str, column_types: dict[str, str] | None, *, force: bool = False) -> str:
    """숫자 비교에 쓸 컬럼 식. 원격 타입이 text면 CAST(... AS NUMERIC)을 붙인다.
    타입을 모르면(force=True인 날짜류만) 캐스팅한다 - 값이 '20270223'·'1' 같은
    숫자 문자열이라 numeric 컬럼이든 text 컬럼이든 CAST가 안전하다."""
    if column_types is None:
        return f"CAST({col} AS NUMERIC)" if force else col
    if column_types.get(bare, "") in _NUMERIC_PG_TYPES:
        return col
    return f"CAST({col} AS NUMERIC)"


def _compile_numeric(column: str, op: str, value: str, value_2: str, spec: AttributeSpec) -> str | None:
    if _currency_mismatch(value, spec):
        return None
    is_days = "day" in (spec.note or "").lower() or "일 단위" in (spec.note or "") or "일(day)" in (spec.note or "")
    def num(v: str) -> float | None:
        d = _duration_days(v) if is_days else None
        return d if d is not None else parse_korean_number(v)
    a = num(value)
    if a is None:
        return None
    if op == "between":
        b = num(value_2)
        if b is None:
            return None
        lo, hi = sorted([a, b])
        return f"{column} BETWEEN {lo:g} AND {hi:g}"
    if op in _OPS:
        return f"{column} {_OPS[op]} {a:g}"
    return None


def _compile_date(column: str, op: str, value: str, value_2: str) -> str | None:
    def ymd(v: str) -> tuple[int, int] | None:
        s = str(v or "")
        m = re.search(r"(\d{4})[.\-/년\s]*(\d{1,2})[.\-/월\s]*(\d{1,2})", s)
        if m:
            d = int(f"{m.group(1)}{int(m.group(2)):02d}{int(m.group(3)):02d}")
            return d, d
        m = re.search(r"(\d{4})[.\-/년\s]*(\d{1,2})\s*월?", s)
        if m and not re.search(r"\d{8}", s):
            y, mo = int(m.group(1)), int(m.group(2))
            return int(f"{y}{mo:02d}01"), int(f"{y}{mo:02d}31")
        m = re.search(r"(\d{4})\s*년?", s)
        if m and not re.search(r"\d{5,}", s):
            y = int(m.group(1))
            return int(f"{y}0101"), int(f"{y}1231")
        m = re.fullmatch(r"\s*(\d{8})(?:\.0)?\s*", s)
        if m:
            return int(m.group(1)), int(m.group(1))
        return None
    a = ymd(value)
    if a is None:
        return None
    if op == "eq":
        return f"{column} BETWEEN {a[0]} AND {a[1]}" if a[0] != a[1] else f"{column} = {a[0]}"
    if op == "gte":
        return f"{column} >= {a[0]}"
    if op == "lte":
        return f"{column} <= {a[1]}"
    if op == "between":
        b = ymd(value_2)
        if b is None:
            return None
        return f"{column} BETWEEN {min(a[0], b[0])} AND {max(a[1], b[1])}"
    return None


def compile_condition(c: dict, qualify, column_types: dict[str, str] | None = None) -> tuple[str | None, str | None]:
    """조건 레코드 하나 → (WHERE 조각, 메모). 조각이 None이면 컴파일 불가.
    조각이 빈 문자열이면 '조건을 의도적으로 뺐다'(금지 컬럼)이며 메모에 사유가 있다.
    column_types는 원격 컬럼 타입(utils.remote_column_types). 숫자 비교인데 text 컬럼이면 CAST한다."""
    spec: AttributeSpec | None = c.get("spec")
    column = c.get("column")
    op = c.get("operator", "eq")
    value = str(c.get("value") or "")
    value_2 = str(c.get("value_2") or "")
    if not column:
        return None, None
    bare = column.split(".")[-1]
    if bare in FORBIDDEN_COLUMNS:
        return "", FORBIDDEN_COLUMNS[bare]
    col = qualify(column)

    # 이미 파이썬이 값 목록을 확정한 경우(ordinal '이상/이하')
    if c.get("matched_values") is not None:
        vals = ", ".join(_q(v) for v in c["matched_values"])
        return f"{col} IN ({vals})", None
    # 조직명 표기 변형(검증된 약칭표) - 기존 LLM 지시문과 같은 형태
    if c.get("org_name_variants"):
        ors = " OR ".join(f"TRIM({col}) LIKE {_q('%' + v + '%')}" for v in c["org_name_variants"])
        return f"({ors})", None
    # Graph 핸드오프·상품코드 해소가 만든 IN 목록
    if op == "in":
        items = [v.strip() for v in value.split(",") if v.strip()]
        if not items:
            return None, None
        return f"{col} IN ({', '.join(_q(v) for v in items)})", None

    if spec is None:
        # subtype 조건(utils.resolve_subtype_conditions): 카탈로그 SUBTYPE_CONDITION_MAP이
        # (column, operator, value)를 이미 확정해 spec 없이 온다. 값은 실제 DB 값이라 그대로 쓴다.
        if op == "eq":
            return f"{col} = {_q(value)}", None
        if op == "contains":
            return f"{col} LIKE {_q('%' + value + '%')}", None
        if op in _OPS:
            n = parse_korean_number(value)
            return (f"{_num_col(col, bare, column_types)} {_OPS[op]} {n:g}", None) if n is not None else (None, None)
        return None, None
    vt = spec.value_type
    if vt == "unknown":           # LLM 폴백 매핑: 값 인코딩을 알 수 없다
        return None, None

    if vt == "numeric_flag" and spec.true_condition:
        truth = _flag_truth(value)
        if truth is None:
            return None, None
        base = f"{col} {spec.true_condition}"
        return (base if truth else f"NOT ({base})"), None

    if vt == "categorical":
        known = list(spec.known_values or [])
        if set(known) == {"Y", "N"}:       # Y/N 플래그형 범주
            truth = _flag_truth(value)
            if truth is None and value.upper() in ("Y", "N"):
                truth = value.upper() == "Y"
            if truth is None:
                return None, None
            return f"{col} = {_q('Y' if truth else 'N')}", None
        if op == "contains":
            return f"{col} LIKE {_q('%' + value + '%')}", None
        if op != "eq":
            return None, None
        if known:
            hit = next((k for k in known if _norm(k) == _norm(value)), None)
            if hit is None:
                return None, None
            return f"{col} = {_q(hit)}", None
        # 허용값 목록이 없는 범주(bd_knd·운용사 등): 공백 패딩 대비 TRIM 비교
        return f"TRIM({col}) = {_q(value.strip())}", None

    if vt == "text":
        if op == "contains":
            return f"{col} LIKE {_q('%' + value + '%')}", None
        if op == "eq":
            return f"TRIM({col}) = {_q(value.strip())}", None
        return None, None

    if vt == "numeric":
        return _compile_numeric(_num_col(col, bare, column_types), op, value, value_2, spec), None

    if vt == "date_yyyymmdd_numeric":
        # 원격에서 YYYYMMDD 날짜 컬럼은 전부 text다(2026-09-05 실측). 타입을 모르면 항상 CAST.
        return _compile_date(_num_col(col, bare, column_types, force=True), op, value, value_2), None

    return None, None   # ordinal without matched_values 등


def compile_sql(resolved_schema: dict, *, apply_limit: bool = True, union_mode: bool = False,
                column_types: dict[str, str] | None = None) -> dict | None:
    """resolved_schema → 완결 SQL(또는 union_mode 서브쿼리). 표현 불가면 None.
    column_types: 기본 테이블의 원격 컬럼 타입(utils.remote_column_types). 없으면 날짜류만 CAST한다."""
    joins = resolved_schema.get("joins") or []
    has_joins = bool(joins)
    table = resolved_schema["table"]
    domain = resolved_schema.get("domain", "")

    def qualify(column: str) -> str:
        if not has_joins or "." in column:
            return column
        return f"base.{column}"

    assumptions: list[str] = []
    where: list[str] = []
    forbidden_hit = False
    for c in resolved_schema.get("conditions") or []:
        frag, note = compile_condition(c, qualify, column_types)
        if frag is None:
            return None
        if note:
            assumptions.append(note)
        if frag == "":
            forbidden_hit = True
            continue
        where.append(frag)

    # 도메인 규칙: 국내ETF 테이블에는 ETN 545건이 섞여 있다(AGENTS.md). ETN을 조건으로 묻지 않았으면 ETF만 본다.
    if domain == "국내ETF":
        cols_used = {str(c.get("column") or "").split(".")[-1] for c in resolved_schema.get("conditions") or []}
        if "pd_grp_no" not in cols_used:
            where.append(f"{qualify('pd_grp_no')} = 'ETF'")
            assumptions.append("국내ETF 테이블의 ETN 혼입을 제외하기 위해 pd_grp_no = 'ETF' 조건을 추가했습니다")

    # 정렬
    sort = resolved_schema.get("sort")
    order_sql = ""
    sort_col = None
    if sort and sort.get("column"):
        bare = sort["column"].split(".")[-1]
        if bare in FORBIDDEN_COLUMNS:
            assumptions.append(FORBIDDEN_COLUMNS[bare] + " (정렬 기준에서 제외)")
            sort = None
        else:
            sort_col = qualify(sort["column"])
            spec = sort.get("spec")
            direction = "ASC" if (sort.get("order") or "asc").lower() == "asc" else "DESC"
            where.append(f"{sort_col} IS NOT NULL")
            if spec is not None and spec.value_type == "ordinal" and spec.value_order:
                cases = " ".join(f"WHEN {sort_col} = {_q(v)} THEN {i}" for i, v in enumerate(spec.value_order))
                order_expr = f"CASE {cases} ELSE {len(spec.value_order)} END"
            elif spec is not None and spec.value_type in ("numeric", "date_yyyymmdd_numeric"):
                # text로 저장된 숫자/날짜를 문자열 순으로 정렬하면 '9' > '10'이 된다.
                order_expr = _num_col(sort_col, bare, column_types, force=spec.value_type == "date_yyyymmdd_numeric")
            else:
                order_expr = sort_col
            order_sql = f"\nORDER BY {order_expr} {direction} NULLS LAST"
            if apply_limit and not union_mode and str(sort.get("limit") or "").isdigit():
                order_sql += f"\nLIMIT {int(sort['limit'])}"

    from_sql = f"FROM {table} AS base\n  " + "\n  ".join(joins) if has_joins else f"FROM {table}"
    where_sql = ("\nWHERE " + "\n  AND ".join(where)) if where else ""

    if union_mode:
        fields = {f["attribute"]: f for f in resolved_schema.get("fields") or [] if f.get("column")}
        code = fields.get("상품코드"); name = fields.get("상품명")
        if not (code and name and sort_col):
            return None
        select = (f"{qualify(code['column'])} AS code, {qualify(name['column'])} AS name, "
                  f"{_q(domain)} AS domain, {sort_col} AS sort_value")
        sql = f"SELECT {select}\n{from_sql}{where_sql}"
        return {"sql": sql, "assumptions": assumptions, "source": "deterministic"}

    select_cols: list[str] = []
    for f in resolved_schema.get("fields") or []:
        column = f.get("column")
        if not column:
            continue
        if column.split(".")[-1] in FORBIDDEN_COLUMNS:
            if not forbidden_hit:
                assumptions.append(FORBIDDEN_COLUMNS[column.split(".")[-1]])
            forbidden_hit = True
            continue
        q = qualify(column)
        if q not in select_cols:
            select_cols.append(q)
    if not select_cols:
        return None
    sql = f"SELECT {', '.join(select_cols)}\n{from_sql}{where_sql}{order_sql}"
    return {"sql": sql, "assumptions": assumptions, "source": "deterministic"}
