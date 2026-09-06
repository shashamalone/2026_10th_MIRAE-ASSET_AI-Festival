# -*- coding: utf-8 -*-
"""공개 DB 인터페이스의 읽기전용 SQL/SPARQL 방어선."""
from __future__ import annotations

import re

SQL_START = re.compile(r"^\s*(?:select|with|explain)\b", re.IGNORECASE)
SQL_FORBIDDEN = re.compile(
    r"\b(?:insert|update|delete|merge|copy|create|alter|drop|truncate|grant|revoke|"
    r"comment|vacuum|analyze|refresh|reindex|cluster|call|do|execute|prepare|listen|notify|"
    r"set|reset|lock|discard|security|lo_import|lo_export|pg_read_file|pg_write_file)\b",
    re.IGNORECASE,
)
SPARQL_START = re.compile(
    r"^\s*(?:(?:prefix|base)\s+[^\n]+\s*)*(?:select|ask|construct|describe)\b",
    re.IGNORECASE,
)
SPARQL_FORBIDDEN = re.compile(
    r"\b(?:insert|delete|load|clear|create|drop|copy|move|add|with)\b",
    re.IGNORECASE,
)


def strip_literals_and_comments(query: str) -> str:
    without_block = re.sub(r"/\*.*?\*/", " ", query, flags=re.DOTALL)
    without_line = re.sub(r"--[^\n]*", " ", without_block)
    without_dollar = re.sub(r"\$[^$]*\$.*?\$[^$]*\$", " ", without_line, flags=re.DOTALL)
    return re.sub(r"'(?:''|[^'])*'", "''", without_dollar)


def ensure_read_only_sql(query: str) -> str:
    if not query or not query.strip():
        raise ValueError("빈 SQL")
    normalized = strip_literals_and_comments(query)
    if ";" in normalized.rstrip().rstrip(";"):
        raise ValueError("다중 SQL 문은 허용하지 않습니다")
    normalized = normalized.rstrip().removesuffix(";").strip()
    if not SQL_START.match(normalized):
        raise ValueError("SELECT/WITH/EXPLAIN만 허용합니다")
    if SQL_FORBIDDEN.search(normalized):
        raise ValueError("쓰기 또는 서버 파일/세션 접근 SQL은 허용하지 않습니다")
    return query.rstrip().removesuffix(";")


def ensure_read_only_sparql(query: str) -> str:
    if not query or not query.strip():
        raise ValueError("빈 SPARQL")
    normalized = re.sub(r"#[^\n]*", " ", query)
    normalized = re.sub(r'"(?:\\.|[^"\\])*"', '""', normalized)
    if not SPARQL_START.match(normalized):
        raise ValueError("SELECT/ASK/CONSTRUCT/DESCRIBE만 허용합니다")
    if SPARQL_FORBIDDEN.search(normalized):
        raise ValueError("SPARQL Update는 허용하지 않습니다")
    return query
