#!/usr/bin/env bash
# 로컬 PostgreSQL 18 + pgvector 를 sudo·docker 없이 띄운다.
#
# 이 머신에는 postgresql *클라이언트*(psql 18.4)만 깔려 있고 서버·docker·sudo 가 없다.
# apt-get download 는 root 가 필요 없으므로, deb 를 받아 사용자 디렉터리에 풀고
# 거기서 initdb/postgres 를 직접 돌린다. 시스템에는 아무것도 설치하지 않는다.
#
#   bash setup_local_pg.sh          # 설치 + 기동 (멱등)
#   bash setup_local_pg.sh stop     # 정지
#   PGVT_PREFIX=/tmp/pgvt bash setup_local_pg.sh
set -euo pipefail

PREFIX="${PGVT_PREFIX:-/tmp/pgvt}"        # 짧게 유지할 것 — 유닉스 소켓 경로는 107바이트 제한
PORT="${PGPORT:-55432}"
DB="${PGDATABASE:-vectordb_test}"
PGV="18"

ROOTFS="$PREFIX/rootfs"
DATA="$PREFIX/data"
SOCK="$PREFIX/sock"
BIN="$ROOTFS/usr/lib/postgresql/$PGV/bin"
export LD_LIBRARY_PATH="$ROOTFS/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"

if [ "${1:-start}" = "stop" ]; then
  "$BIN/pg_ctl" -D "$DATA" stop -m fast || true
  exit 0
fi

# 1) deb 내려받아 풀기 --------------------------------------------------------
if [ ! -x "$BIN/postgres" ]; then
  echo "== deb 내려받는 중 (root 불필요) =="
  mkdir -p "$PREFIX/deb" "$ROOTFS"
  cd "$PREFIX/deb"
  # postgresql-18 은 -updates 판(18.4)이 미러에서 404 나므로 릴리스 판(18.3)으로 고정한다.
  # pgvector 0.8.1-2 도 18.3 에 맞춰 빌드돼 있어 ABI 가 맞는다.
  apt-get download \
      postgresql-18=18.3-1 \
      postgresql-18-pgvector \
      libicu78 libnuma1 liburing2
  for d in *.deb; do dpkg-deb -x "$d" "$ROOTFS"; done
fi
"$BIN/postgres" --version

# 2) initdb -------------------------------------------------------------------
if [ ! -f "$DATA/PG_VERSION" ]; then
  echo "== initdb =="
  mkdir -p "$DATA" "$SOCK"
  "$BIN/initdb" -D "$DATA" -U postgres --encoding=UTF8 --locale=C.UTF-8 >/dev/null
fi

# 3) 기동 ---------------------------------------------------------------------
mkdir -p "$SOCK"
if ! "$BIN/pg_ctl" -D "$DATA" status >/dev/null 2>&1; then
  echo "== 기동 =="
  "$BIN/pg_ctl" -D "$DATA" -l "$PREFIX/pg.log" \
      -o "-p $PORT -k $SOCK -h 127.0.0.1" -w start
fi

# 4) DB + 확장 ----------------------------------------------------------------
export PGHOST=127.0.0.1 PGPORT="$PORT" PGUSER=postgres
psql -X -q -d postgres -tAc "select 1 from pg_database where datname='$DB'" | grep -q 1 \
  || createdb "$DB"
psql -X -q -d "$DB" -c 'CREATE EXTENSION IF NOT EXISTS vector;' \
                    -c 'CREATE EXTENSION IF NOT EXISTS pg_trgm;'

echo
echo "준비 완료:"
psql -X -q -d "$DB" -tAc "select 'PostgreSQL '||current_setting('server_version')"
psql -X -q -d "$DB" -tAc "select 'pgvector '||extversion from pg_extension where extname='vector'"
echo
echo "  export PGHOST=127.0.0.1 PGPORT=$PORT PGUSER=postgres PGDATABASE=$DB"
