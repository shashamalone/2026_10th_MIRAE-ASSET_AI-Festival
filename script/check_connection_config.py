# -*- coding: utf-8 -*-
"""로컬 PostgreSQL 포워딩과 Data API 설정을 읽기 전용으로 점검한다.

실행:
    python script/check_connection_config.py

DB에는 SELECT만 실행하고, Data API에는 GET 요청만 보낸다.
"""
from __future__ import annotations

import os
import socket
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def value(name: str, default: str) -> tuple[str, str]:
    current = os.environ.get(name)
    return (current if current else default, "env" if current else "default")


def check_tcp(host: str, port: int) -> None:
    try:
        with socket.create_connection((host, port), timeout=3):
            print(f"[OK] TCP {host}:{port} is open")
    except OSError as exc:
        print(f"[FAIL] TCP {host}:{port} is not reachable: {exc}")


def check_api(base_url: str) -> None:
    for path in ("/health", "/v1/release"):
        url = base_url.rstrip("/") + path
        try:
            request = Request(url, method="GET")
            with urlopen(request, timeout=5) as response:
                body = response.read().decode("utf-8", errors="replace")
                print(f"[OK] GET {url} -> HTTP {response.status}")
                print(f"     {body[:500]}")
        except HTTPError as exc:
            print(f"[FAIL] GET {url} -> HTTP {exc.code}")
        except URLError as exc:
            print(f"[FAIL] GET {url} -> {exc.reason}")
        except OSError as exc:
            print(f"[FAIL] GET {url} -> {exc}")


def check_postgres(
    host: str, port: int, user: str, password: str, dbname: str
) -> None:
    try:
        import psycopg
    except ImportError:
        print("[SKIP] psycopg is not installed in this Python environment")
        return

    try:
        with psycopg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=dbname,
            connect_timeout=5,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT current_database(), inet_server_addr(), version()"
                )
                database, server_addr, version = cur.fetchone()
            print(f"[OK] PostgreSQL login: database={database}, server={server_addr}")
            print(f"     {version}")
    except Exception as exc:
        print(f"[FAIL] PostgreSQL login: {type(exc).__name__}: {exc}")


def main() -> None:
    host, host_source = value("PGHOST", "127.0.0.1")
    port_text, port_source = value("PGPORT", "5432")
    user, user_source = value("PGUSER", "postgres")
    password, password_source = value("PGPASSWORD", "postgres")
    dbname, dbname_source = value("PGDATABASE", "mafest")
    api_url = os.environ.get("FINANCIAL_DATA_API_URL", "")

    try:
        port = int(port_text)
    except ValueError:
        print(f"[FAIL] PGPORT is not an integer: {port_text}")
        return

    print("=== Effective PostgreSQL configuration ===")
    print(f"PGHOST    = {host} ({host_source})")
    print(f"PGPORT    = {port} ({port_source})")
    print(f"PGUSER    = {user} ({user_source})")
    print(f"PGPASSWORD = {'set' if password else 'empty'} ({password_source})")
    print(f"PGDATABASE = {dbname} ({dbname_source})")
    print()

    print("=== Local/forwarded PostgreSQL check ===")
    check_tcp(host, port)
    check_postgres(host, port, user, password, dbname)
    print()

    print("=== Data API configuration ===")
    if api_url:
        print(f"FINANCIAL_DATA_API_URL = {api_url}")
        check_api(api_url)
    else:
        print("FINANCIAL_DATA_API_URL is not set")
        print("Data API is not configured for this process.")

    print()
    print("=== Interpretation ===")
    print("The current src/config.py uses PG* variables, not FINANCIAL_DATA_API_URL.")
    print("Therefore a successful PostgreSQL check means direct DB access is active.")


if __name__ == "__main__":
    main()
