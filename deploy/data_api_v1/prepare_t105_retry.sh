#!/usr/bin/env bash
set -Eeuo pipefail

base=/home/user1106/financial-agent-v2
release_sha=57c4edc96bd5cebe7703bb717480b0ebd935b39d
release_dir=${base}/releases/${release_sha}
current_dir=/home/user1106/financial-agent
backup_root=${base}/shared/backups
env_file=${release_dir}/.env
lock_file=${backup_root}/data-api-cutover.lock
project=financial-agent-prep
expected_snapshot=ddb3d994a4a5115a75bed7efa9c4cd0f6655f95b0a49f3b0e3c01b2bf8301a38
expected_release=financial-products-2026-08-24@${expected_snapshot}
current_graph=financial-agent-prep_oxigraph-data
next_graph=financial-agent-prep_oxigraph-next-2026-08-24-57c4edc
next_container=financial-product-graph-next
v2_api_base_image=financial-agent-v2-api:57c4edc-dbapi-c007-base
v2_api_image=financial-agent-v2-api:57c4edc-dbapi-c007-g10cov
placeholder_comment='empty rollback placeholder for a schema absent before V2 cutover'

exec 9>"${lock_file}"
flock -n 9 || { echo 'another data API cutover or rollback is active' >&2; exit 2; }

test -d "${release_dir}" && test -f "${env_file}"
test "$(stat -c '%a' "${env_file}")" = 600
test "$(stat -c '%a' "${current_dir}/.env")" = 600
test ! -e "${release_dir}/compose.override.yaml"
cd "${release_dir}"

mapfile -t settings < <(python3 - "${env_file}" <<'PY'
import shlex
import sys
from pathlib import Path

values = {}
for raw in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    key, value = key.strip(), value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        parsed = shlex.split(value, posix=True)
        value = parsed[0] if parsed else ""
    values[key] = value
for key in ("COMPOSE_PROJECT_NAME", "POSTGRES_USER", "POSTGRES_DB", "OXIGRAPH_VOLUME", "OXIGRAPH_NEXT_VOLUME", "BACKUP_ROOT", "API_PORT"):
    value = values.get(key) or ("8000" if key == "API_PORT" else "")
    if not value:
        raise SystemExit(f"RETRY_ENV_FAIL missing {key}")
    print(value)
PY
)
test "${settings[0]}" = "${project}"
postgres_user=${settings[1]}
postgres_db=${settings[2]}
test "${settings[3]}" = "${current_graph}"
test "${settings[4]}" = "${next_graph}"
test "${settings[5]}" = "${backup_root}"
api_port=${settings[6]}
export COMPOSE_PROJECT_NAME="${project}" POSTGRES_USER="${postgres_user}" POSTGRES_DB="${postgres_db}"
export OXIGRAPH_VOLUME="${current_graph}" OXIGRAPH_NEXT_VOLUME="${next_graph}" BACKUP_ROOT="${backup_root}"

psql_at=(docker compose exec -T db psql -v ON_ERROR_STOP=1 -U "${postgres_user}" -d "${postgres_db}" -At -c)
schema_count() {
    "${psql_at[@]}" "SELECT count(*) FROM pg_namespace WHERE nspname IN ($1)" | tr -d '\r\n'
}
canonical_count=$(schema_count "'meta','raw','enriched','relations','vec','core'")
next_count=$(schema_count "'meta_next','raw_next','enriched_next','relations_next','vec_next','core_next'")
prev_count=$(schema_count "'meta_prev','raw_prev','enriched_prev','relations_prev','vec_prev','core_prev'")
failed_count=$(schema_count "'meta_failed','raw_failed','enriched_failed','relations_failed','vec_failed','core_failed'")
if [[ "${canonical_count}|${next_count}|${prev_count}|${failed_count}" == '3|6|0|0' ]]; then
    ready_backup=$(find "${backup_root}" -mindepth 1 -maxdepth 1 -type d -name 'data-platform-v2-*' -printf '%T@ %p\n' | sort -nr | head -n 1 | cut -d' ' -f2-)
    test -n "${ready_backup}" && test -d "${ready_backup}"
    for required in old-api-image.tar old-api-image-id.txt old-api-health.json old-api-stats.json old-api-probe.json next-graph-volume.tgz next-graph-restore-drill.txt next-graph-optimize.txt scratch-schema-roundtrip.txt live-rdb-validation.json next-graph-validation.json; do
        test -s "${ready_backup}/${required}"
    done
    (cd "${ready_backup}" && sha256sum -c SHA256SUMS >/dev/null)
    test "$(docker inspect -f '{{.State.Running}}' "${next_container}")" = true
    test "$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}' "${next_container}")" = "${next_graph}"
    test -z "$(docker port "${next_container}" 7878/tcp 2>/dev/null)"
    ready_graph_id=$(docker compose ps -q graph)
    test -n "${ready_graph_id}"
    ready_graph_ports=$(docker port "${ready_graph_id}" 7878/tcp)
    test -n "${ready_graph_ports}"
    if grep -Ev '^(127[.]0[.]0[.]1|\[::1\]):[0-9]+$' <<<"${ready_graph_ports}" | grep -q .; then
        echo "RETRY_GRAPH_EXPOSURE_FAIL_ALREADY_READY: ${ready_graph_ports}" >&2
        exit 2
    fi
    curl --fail --silent --show-error "http://127.0.0.1:${api_port}/health" >/dev/null
    curl --fail --silent --show-error "http://127.0.0.1:${api_port}/db/stats" >/dev/null
    printf 'T105 RETRY READY PASS: backup=%s schemas=3|6|0|0 state=already_ready next_graph=%s old_api=unchanged graph_host=loopback\n' \
        "${ready_backup}" "${next_graph}"
    exit 0
fi
test "${canonical_count}|${next_count}|${prev_count}|${failed_count}" = '6|0|0|6'

old_absent_schemas=$("${psql_at[@]}" "SELECT string_agg(nspname,',' ORDER BY nspname) FROM pg_namespace WHERE nspname IN ('meta','raw','enriched','relations','vec','core') AND obj_description(oid,'pg_namespace')='${placeholder_comment}' AND pg_get_userbyid(nspowner)=current_user")
old_absent_schemas=$(tr -d '\r\n' <<<"${old_absent_schemas}")
[[ "${old_absent_schemas}" =~ ^(core|enriched|meta|raw|relations|vec)(,(core|enriched|meta|raw|relations|vec)){2}$ ]]
placeholder_count=$("${psql_at[@]}" "SELECT count(*) FROM pg_namespace WHERE nspname IN ('meta','raw','enriched','relations','vec','core') AND obj_description(oid,'pg_namespace')='${placeholder_comment}' AND pg_get_userbyid(nspowner)=current_user")
test "$(tr -d '\r\n' <<<"${placeholder_count}")" = 3

ready=$("${psql_at[@]}" "SELECT count(*) FROM meta_failed.load_run WHERE status='passed' AND phase='cutover_ready' AND validation_result->>'cutover_ready'='true'")
total_runs=$("${psql_at[@]}" "SELECT count(*) FROM meta_failed.load_run")
snapshot=$("${psql_at[@]}" "SELECT source_hash FROM meta_failed.dataset_snapshot")
official=$("${psql_at[@]}" "SELECT (SELECT count(*) FROM raw_failed.bond_kr_master)+(SELECT count(*) FROM raw_failed.etf_kr_master)+(SELECT count(*) FROM raw_failed.etf_gl_master)+(SELECT count(*) FROM raw_failed.fund_pub_master)")
holdings=$("${psql_at[@]}" "SELECT count(*) FROM relations_failed.product_holding")
subsidiaries=$("${psql_at[@]}" "SELECT count(*) FROM relations_failed.company_subsidiary")
test "$(tr -d '\r\n' <<<"${ready}")" = 1
test "$(tr -d '\r\n' <<<"${total_runs}")" = 1
test "$(tr -d '\r\n' <<<"${snapshot}")" = "${expected_snapshot}"
test "${official}" -eq 53375 && test "${holdings}" -eq 46951 && test "${subsidiaries}" -eq 8866

db_id=$(docker compose ps -q db)
graph_id=$(docker compose ps -q graph)
api_id=$(docker compose ps -q api)
test -n "${db_id}" && test -n "${graph_id}" && test -n "${api_id}"
test "$(docker inspect -f '{{.State.Running}}' "${db_id}")" = true
test "$(docker inspect -f '{{.State.Running}}' "${graph_id}")" = true
test "$(docker inspect -f '{{.State.Running}}' "${api_id}")" = true
test "$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Name}}{{end}}{{end}}' "${db_id}")" = financial-agent-prep_postgres-data-pg17
test "$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}' "${graph_id}")" = "${current_graph}"

curl --fail --silent --show-error "http://127.0.0.1:${api_port}/health" >/dev/null
curl --fail --silent --show-error "http://127.0.0.1:${api_port}/db/stats" >/dev/null

# Normalize the current Graph host exposure before taking the new baseline.
GRAPH_BIND=127.0.0.1 docker compose up -d --force-recreate graph
graph_id=$(docker compose ps -q graph)
test -n "${graph_id}" && test "$(docker inspect -f '{{.State.Running}}' "${graph_id}")" = true
graph_ports=$(docker port "${graph_id}" 7878/tcp)
test -n "${graph_ports}"
if grep -Ev '^(127[.]0[.]0[.]1|\[::1\]):[0-9]+$' <<<"${graph_ports}" | grep -q .; then
    echo "RETRY_GRAPH_EXPOSURE_FAIL: ${graph_ports}" >&2
    exit 2
fi

# The standard backup performs a real PostgreSQL restore drill and a Graph archive restore drill.
backup_dir=$(GRAPH_BIND=127.0.0.1 bash deploy/backup_v2.sh)
case "${backup_dir}" in
    ${backup_root}/data-platform-v2-*) ;;
    *) echo "RETRY_BACKUP_PATH_FAIL: ${backup_dir}" >&2; exit 2 ;;
esac
chmod 700 "${backup_dir}"
for _ in $(seq 1 30); do
    if curl --fail --silent --show-error "http://127.0.0.1:${api_port}/health" >/dev/null 2>&1 \
      && curl --fail --silent --show-error "http://127.0.0.1:${api_port}/db/stats" >/dev/null 2>&1; then break; fi
    sleep 2
done
curl --fail --silent --show-error "http://127.0.0.1:${api_port}/health" >/dev/null
curl --fail --silent --show-error "http://127.0.0.1:${api_port}/db/stats" >/dev/null

scratch_db="retry_drill_$(date -u +%Y%m%dT%H%M%SZ)_$$"
scratch_volume="oxigraph-next-retry-drill-$(date -u +%Y%m%dt%H%M%Sz)-$$"
probe_container="${project}-v2-retry-probe-$$"
scratch_compose_env=$(mktemp "${backup_dir}/.scratch-compose.XXXXXX")
probe_env=$(mktemp "${backup_dir}/.scratch-api.XXXXXX")
scratch_created=0
scratch_volume_created=0
probe_created=0
cleanup() {
    if [[ "${probe_created}" == 1 ]]; then docker rm -f "${probe_container}" >/dev/null 2>&1 || true; fi
    if [[ "${scratch_created}" == 1 ]]; then docker compose exec -T db dropdb -U "${postgres_user}" --if-exists "${scratch_db}" >/dev/null 2>&1 || true; fi
    if [[ "${scratch_volume_created}" == 1 ]]; then docker volume rm "${scratch_volume}" >/dev/null 2>&1 || true; fi
    rm -f -- "${scratch_compose_env}" "${probe_env}"
}
trap cleanup EXIT

api_id=$(docker compose ps -q api)
old_api_image_id=$(docker inspect -f '{{.Image}}' "${api_id}")
old_api_image_ref=$(docker inspect -f '{{.Config.Image}}' "${api_id}")
test -n "${old_api_image_id}" && test -n "${old_api_image_ref}"
docker image inspect "${old_api_image_id}" >/dev/null
printf '%s\n' "${old_api_image_id}" >"${backup_dir}/old-api-image-id.txt"
printf '%s\n' "${old_api_image_ref}" >"${backup_dir}/old-api-image-ref.txt"
docker save "${old_api_image_id}" -o "${backup_dir}/old-api-image.tar"
docker load -i "${backup_dir}/old-api-image.tar" >/dev/null
test "$(docker image inspect -f '{{.Id}}' "${old_api_image_id}")" = "${old_api_image_id}"

curl --fail --silent --show-error "http://127.0.0.1:${api_port}/health" >"${backup_dir}/old-api-health.json"
curl --fail --silent --show-error "http://127.0.0.1:${api_port}/db/stats" >"${backup_dir}/old-api-stats.json"
curl --fail --silent --show-error -H 'Content-Type: application/json' --data '{"sql":"SELECT 1 AS probe"}' \
    "http://127.0.0.1:${api_port}/db" >"${backup_dir}/old-api-probe.json"
graph_port=$(docker port "$(docker compose ps -q graph)" 7878/tcp | awk -F: '/^127[.]0[.]0[.]1:/{print "127.0.0.1:" $NF; exit}')
test -n "${graph_port}"
curl --fail --silent --show-error --get -H 'Accept: application/sparql-results+json' \
    --data-urlencode 'query=SELECT (COUNT(*) AS ?triples) WHERE { { ?s ?p ?o } UNION { GRAPH ?g { ?s ?p ?o } } }' \
    "http://${graph_port}/query" >"${backup_dir}/old-graph-count.json"
printf '%s\n' "${old_absent_schemas}" >"${backup_dir}/old-absent-schemas.txt"
printf 'ready=%s total_runs=%s snapshot=%s official=%s holdings=%s subsidiaries=%s\n' \
    "${ready}" "${total_runs}" "${snapshot}" "${official}" "${holdings}" "${subsidiaries}" \
    >"${backup_dir}/v2-failed-contracts.txt"

# The versioned next Graph is cold during archival; the active old Graph is untouched.
if docker container inspect "${next_container}" >/dev/null 2>&1; then
    test "$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}' "${next_container}")" = "${next_graph}"
    docker rm -f "${next_container}" >/dev/null
fi
docker volume inspect "${next_graph}" >/dev/null
docker run --rm -v "${next_graph}:/source:ro" -v "${backup_dir}:/backup" \
    busybox:1.36 tar -C /source -czf /backup/next-graph-volume.tgz .
printf '%s\n' "${next_graph}" >"${backup_dir}/next-graph-volume-name.txt"
tar -tzf "${backup_dir}/next-graph-volume.tgz" >"${backup_dir}/next-graph-tar-list.txt"
docker volume create "${scratch_volume}" >/dev/null
scratch_volume_created=1
docker run --rm -v "${scratch_volume}:/restore" -v "${backup_dir}:/backup:ro" \
    busybox:1.36 tar -C /restore -xzf /backup/next-graph-volume.tgz
docker run --rm -v "${scratch_volume}:/restore:ro" busybox:1.36 \
    sh -c 'find /restore -type f -print -quit | grep -q .'
printf 'restore=passed\n' >"${backup_dir}/next-graph-restore-drill.txt"
docker volume rm "${scratch_volume}" >/dev/null
scratch_volume_created=0

# Oxigraph explicitly recommends optimizing bulk-loaded stores before read-heavy use.
# The archive above is the recovery point if optimization fails.
printf 'NEXT GRAPH OPTIMIZE START: volume=%s\n' "${next_graph}"
docker run --rm -v "${next_graph}:/data" ghcr.io/oxigraph/oxigraph:latest \
    optimize -l /data >"${backup_dir}/next-graph-optimize.txt" 2>&1
printf 'NEXT GRAPH OPTIMIZE PASS\n'

docker network inspect "${project}_default" >/dev/null
docker run -d --name "${next_container}" --restart unless-stopped \
    --network "${project}_default" -v "${next_graph}:/data" \
    ghcr.io/oxigraph/oxigraph:latest serve-read-only --location /data --bind 0.0.0.0:7878 >/dev/null
test -z "$(docker port "${next_container}" 7878/tcp 2>/dev/null)"
next_ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "${next_container}")
test -n "${next_ip}"
for _ in $(seq 1 30); do
    if curl --fail --silent --show-error --get --data-urlencode 'query=ASK { ?s ?p ?o }' "http://${next_ip}:7878/query" >/dev/null 2>&1; then break; fi
    sleep 2
done
curl --fail --silent --show-error --get --data-urlencode 'query=ASK { ?s ?p ?o }' "http://${next_ip}:7878/query" >/dev/null

# Warm the two queries used by API /health, then enforce the API's immutable
# two-second Graph timeout before starting the scratch API container.
health_count_query="SELECT (COUNT(*) AS ?triples) WHERE { GRAPH ?g { ?s ?p ?o } FILTER(STRSTARTS(STR(?g), 'http://mafest.ai/graph/abox/')) }"
health_graphs_query="SELECT DISTINCT ?g WHERE { GRAPH ?g { ?s ?p ?o } FILTER(STRSTARTS(STR(?g), 'http://mafest.ai/graph/abox/')) }"
curl --fail --silent --show-error --get -H 'Accept: application/sparql-results+json' \
    --data-urlencode "query=${health_count_query}" "http://${next_ip}:7878/query" >/dev/null
curl --fail --silent --show-error --get -H 'Accept: application/sparql-results+json' \
    --data-urlencode "query=${health_graphs_query}" "http://${next_ip}:7878/query" >/dev/null
curl --fail --silent --show-error --max-time 2 --get -H 'Accept: application/sparql-results+json' \
    --data-urlencode "query=${health_count_query}" "http://${next_ip}:7878/query" >/dev/null
curl --fail --silent --show-error --max-time 2 --get -H 'Accept: application/sparql-results+json' \
    --data-urlencode "query=${health_graphs_query}" "http://${next_ip}:7878/query" >/dev/null
printf 'optimize=passed health_queries_under_2s=passed\n' >>"${backup_dir}/next-graph-optimize.txt"

if ! docker image inspect "${v2_api_base_image}" >/dev/null 2>&1; then
    docker build --label "mafest.runtime-base=${release_sha}" \
        --label "mafest.validator-fix=c007cf77457a2f443b67cca15743ea18ab49a6e4" \
        -t "${v2_api_base_image}" .
fi
if ! docker image inspect "${v2_api_image}" >/dev/null 2>&1; then
    docker build --build-arg "BASE_IMAGE=${v2_api_base_image}" -t "${v2_api_image}" - <<'DOCKERFILE'
ARG BASE_IMAGE=financial-agent-v2-api:57c4edc-dbapi-c007-base
FROM ${BASE_IMAGE}
RUN python -c 'from pathlib import Path; p=Path("/app/src/api.py"); s=p.read_text(encoding="utf-8"); old1="async with httpx.AsyncClient(timeout=STATEMENT_TIMEOUT_MS / 1000) as client:"; new1="async with httpx.AsyncClient(timeout=10.0) as client:"; old2="\"ORDER BY p.product_type,p.name\","; new2="\"ORDER BY p.product_id LIMIT 101\","; assert s.count(old1)==s.count(old2)==1; p.write_text(s.replace(old1,new1).replace(old2,new2),encoding="utf-8")'
DOCKERFILE
fi

docker compose exec -T db createdb -U "${postgres_user}" "${scratch_db}"
scratch_created=1
docker compose exec -T db pg_restore -U "${postgres_user}" -d "${scratch_db}" \
    --no-owner --no-privileges <"${backup_dir}/postgres.dump"

rearm_database() {
    local target_db=$1
    docker compose exec -T db psql -v ON_ERROR_STOP=1 -v old_absent_schemas="${old_absent_schemas}" \
        -U "${postgres_user}" -d "${target_db}" <<'SQL'
BEGIN;
SET LOCAL lock_timeout='10s';
SELECT set_config('mafest.old_absent_schemas', :'old_absent_schemas', true);
DO $do$
DECLARE
  base_name text;
  schema_oid oid;
  bases text[] := ARRAY['meta','raw','enriched','relations','vec','core'];
BEGIN
  FOREACH base_name IN ARRAY string_to_array(current_setting('mafest.old_absent_schemas'), ',') LOOP
    SELECT oid INTO schema_oid FROM pg_namespace WHERE nspname=base_name;
    IF schema_oid IS NULL
       OR obj_description(schema_oid,'pg_namespace') IS DISTINCT FROM 'empty rollback placeholder for a schema absent before V2 cutover'
       OR pg_get_userbyid((SELECT nspowner FROM pg_namespace WHERE oid=schema_oid)) IS DISTINCT FROM current_user THEN
      RAISE EXCEPTION 'unsafe retry placeholder: %', base_name;
    END IF;
    EXECUTE format('DROP SCHEMA %I RESTRICT', base_name);
  END LOOP;
  FOREACH base_name IN ARRAY bases LOOP
    IF to_regnamespace(base_name || '_failed') IS NULL OR to_regnamespace(base_name || '_next') IS NOT NULL THEN
      RAISE EXCEPTION 'unsafe retry source state: %', base_name;
    END IF;
    EXECUTE format('ALTER SCHEMA %I RENAME TO %I', base_name || '_failed', base_name || '_next');
  END LOOP;
END
$do$;
COMMIT;
SQL
}

cutover_database() {
    local target_db=$1
    {
        printf "SET lock_timeout='10s';\n"
        sed '/^COMMIT;[[:space:]]*$/d' sql/v2/090_cutover.sql
        cat <<'SQL'
SELECT set_config('mafest.old_absent_schemas', :'old_absent_schemas', true);
DO $do$
DECLARE
  base_name text;
BEGIN
  FOREACH base_name IN ARRAY string_to_array(current_setting('mafest.old_absent_schemas'), ',') LOOP
    IF to_regnamespace(base_name || '_prev') IS NOT NULL THEN
      RAISE EXCEPTION 'rollback placeholder already exists: %_prev', base_name;
    END IF;
    EXECUTE format('CREATE SCHEMA %I', base_name || '_prev');
    EXECUTE format('COMMENT ON SCHEMA %I IS %L', base_name || '_prev', 'empty rollback placeholder for a schema absent before V2 cutover');
  END LOOP;
END
$do$;
COMMIT;
SQL
    } | docker compose exec -T db psql -v ON_ERROR_STOP=1 -v old_absent_schemas="${old_absent_schemas}" \
        -U "${postgres_user}" -d "${target_db}"
}

rollback_database() {
    local target_db=$1
    {
        sed '/^COMMIT;[[:space:]]*$/d' sql/v2/095_rollback.sql
        cat <<'SQL'
SELECT set_config('mafest.old_absent_schemas', :'old_absent_schemas', true);
DO $do$
DECLARE
  base_name text;
  schema_oid oid;
BEGIN
  FOREACH base_name IN ARRAY string_to_array(current_setting('mafest.old_absent_schemas'), ',') LOOP
    SELECT oid INTO schema_oid FROM pg_namespace WHERE nspname=base_name;
    IF schema_oid IS NULL
       OR obj_description(schema_oid,'pg_namespace') IS DISTINCT FROM 'empty rollback placeholder for a schema absent before V2 cutover'
       OR pg_get_userbyid((SELECT nspowner FROM pg_namespace WHERE oid=schema_oid)) IS DISTINCT FROM current_user THEN
      RAISE EXCEPTION 'unsafe rollback placeholder: %', base_name;
    END IF;
    EXECUTE format('DROP SCHEMA %I RESTRICT', base_name);
  END LOOP;
END
$do$;
COMMIT;
SQL
    } | docker compose exec -T db psql -v ON_ERROR_STOP=1 -v old_absent_schemas="${old_absent_schemas}" \
        -U "${postgres_user}" -d "${target_db}"
}

state_counts() {
    local target_db=$1
    docker compose exec -T db psql -v ON_ERROR_STOP=1 -U "${postgres_user}" -d "${target_db}" -At -c \
        "SELECT (SELECT count(*) FROM pg_namespace WHERE nspname IN ('meta','raw','enriched','relations','vec','core'))||'|'||(SELECT count(*) FROM pg_namespace WHERE nspname IN ('meta_next','raw_next','enriched_next','relations_next','vec_next','core_next'))||'|'||(SELECT count(*) FROM pg_namespace WHERE nspname IN ('meta_prev','raw_prev','enriched_prev','relations_prev','vec_prev','core_prev'))||'|'||(SELECT count(*) FROM pg_namespace WHERE nspname IN ('meta_failed','raw_failed','enriched_failed','relations_failed','vec_failed','core_failed'))" | tr -d '\r\n'
}

rearm_database "${scratch_db}"
test "$(state_counts "${scratch_db}")" = '3|6|0|0'

python3 - "${env_file}" "${scratch_db}" "${scratch_compose_env}" "${probe_env}" <<'PY'
import shlex
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

source, database, compose_target, api_target = map(Path, sys.argv[1:])
raw_lines = source.read_text(encoding="utf-8").splitlines()
values = {}
for raw in raw_lines:
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        parsed_value = shlex.split(value, posix=True)
        value = parsed_value[0] if parsed_value else ""
    values[key.strip()] = value
admin = values.get("ADMIN_DATABASE_URL", "")
parts = urlsplit(admin)
if parts.scheme not in {"postgres", "postgresql"} or not parts.netloc:
    raise SystemExit("RETRY_ENV_FAIL ADMIN_DATABASE_URL must be a PostgreSQL URL")
scratch = urlunsplit((parts.scheme, parts.netloc, "/" + str(database), parts.query, parts.fragment))
replaced = set()
output = []
for raw in raw_lines:
    key = raw.split("=", 1)[0].strip() if "=" in raw else ""
    if key in {"ADMIN_DATABASE_URL", "DATABASE_URL"}:
        output.append(f"{key}={scratch}")
        replaced.add(key)
    else:
        output.append(raw)
for key in ("ADMIN_DATABASE_URL", "DATABASE_URL"):
    if key not in replaced:
        output.append(f"{key}={scratch}")
compose_target.write_text("\n".join(output) + "\n", encoding="utf-8")
api_target.write_text(
    f"DATABASE_URL={scratch}\nOXIGRAPH_URL=http://financial-product-graph-next:7878\n",
    encoding="utf-8",
)
PY
chmod 600 "${scratch_compose_env}" "${probe_env}"

docker compose --env-file "${scratch_compose_env}" --profile ops run --rm --no-deps \
    -e OXIGRAPH_NEXT_QUERY_URL=http://financial-product-graph-next:7878/query \
    builder python -c 'import json,psycopg; from kb.build_data_platform_v2 import dsn,validate_stage; from kb.v2_manifest import validate_source_dir; inspections=validate_source_dir(); conn=psycopg.connect(dsn()); conn.execute("SET TRANSACTION READ ONLY"); result=validate_stage(conn,inspections); conn.close(); print(json.dumps(result,ensure_ascii=False,default=str))' \
    >"${backup_dir}/scratch-rdb-validation.json"

cutover_database "${scratch_db}"
test "$(state_counts "${scratch_db}")" = '6|0|6|0'
docker run -d --name "${probe_container}" --network "${project}_default" --env-file "${probe_env}" \
    "${v2_api_image}" >/dev/null
probe_created=1
probe_ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "${probe_container}")
test -n "${probe_ip}"
for _ in $(seq 1 30); do
    if curl --fail --silent --show-error "http://${probe_ip}:8000/health" >"${backup_dir}/scratch-api-health.json" 2>/dev/null; then break; fi
    sleep 2
done
python3 - "${backup_dir}/scratch-api-health.json" "${expected_release}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    value = json.load(stream)
assert value.get("status") == "ok" and value.get("readiness") is True, value
assert value.get("rdb", {}).get("release_id") == sys.argv[2], value
assert value.get("graph", {}).get("release_id") == sys.argv[2], value
PY
for path in version stats tables catalog coverage; do
    response="${backup_dir}/scratch-api-${path}.json"
    status=$(curl --silent --show-error --output "${response}" --write-out '%{http_code}' "http://${probe_ip}:8000/db/${path}")
    printf 'SCRATCH_VERIFY_HTTP: path=/db/%s status=%s\n' "${path}" "${status}"
    if [[ "${status}" != 200 ]]; then
        cat "${response}" >&2
        exit 1
    fi
done
docker rm -f "${probe_container}" >/dev/null
probe_created=0

rollback_database "${scratch_db}"
test "$(state_counts "${scratch_db}")" = '3|0|0|6'
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U "${postgres_user}" -d "${scratch_db}" -At -c \
    "SELECT table_schema||'.'||table_name||'='||(xpath('/row/c/text()',query_to_xml(format('SELECT count(*) c FROM %I.%I',table_schema,table_name),false,true,'')))[1]::text FROM information_schema.tables WHERE table_schema IN ('meta','raw','enriched','relations','vec','core') ORDER BY 1" \
    >"${backup_dir}/scratch-restored-counts.txt"
cmp "${backup_dir}/scratch-restored-counts.txt" "${backup_dir}/postgres-counts.txt"
printf 'schema_roundtrip=passed before=6|0|0|6 rearmed=3|6|0|0 cutover=6|0|6|0 rollback=3|0|0|6\n' \
    >"${backup_dir}/scratch-schema-roundtrip.txt"
docker compose exec -T db dropdb -U "${postgres_user}" "${scratch_db}"
scratch_created=0

# The only live DB mutation happens after the backup, restore drills, and API probe pass.
rearm_database "${postgres_db}"
test "$(state_counts "${postgres_db}")" = '3|6|0|0'

docker compose --profile ops run --rm --no-deps \
    -e OXIGRAPH_NEXT_QUERY_URL=http://financial-product-graph-next:7878/query \
    builder python -c 'import json,psycopg; from kb.build_data_platform_v2 import dsn,validate_stage; from kb.v2_manifest import validate_source_dir; inspections=validate_source_dir(); conn=psycopg.connect(dsn()); conn.execute("SET TRANSACTION READ ONLY"); result=validate_stage(conn,inspections); conn.close(); print(json.dumps(result,ensure_ascii=False,default=str))' \
    >"${backup_dir}/live-rdb-validation.json"
OXIGRAPH_NEXT_QUERY_URL=http://financial-product-graph-next:7878/query \
    docker compose --profile ops run --rm --no-deps \
    -e OXIGRAPH_NEXT_QUERY_URL=http://financial-product-graph-next:7878/query \
    builder python -c 'import json; from kb.validate_data_platform_v2 import validate_graph_endpoint; result=validate_graph_endpoint(); assert result["triples"]==655388 and len(result["named_graphs"])==5; print(json.dumps(result,ensure_ascii=False))' \
    >"${backup_dir}/next-graph-validation.json"

test "$(docker inspect -f '{{.Image}}' "$(docker compose ps -q api)")" = "${old_api_image_id}"
curl --fail --silent --show-error "http://127.0.0.1:${api_port}/health" >"${backup_dir}/old-api-health.after.json"
curl --fail --silent --show-error "http://127.0.0.1:${api_port}/db/stats" >"${backup_dir}/old-api-stats.after.json"
curl --fail --silent --show-error -H 'Content-Type: application/json' --data '{"sql":"SELECT 1 AS probe"}' \
    "http://127.0.0.1:${api_port}/db" >"${backup_dir}/old-api-probe.after.json"
python3 - "${backup_dir}" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
def scrub(value):
    if isinstance(value, dict):
        return {key: scrub(item) for key, item in value.items() if key != "elapsed_ms"}
    if isinstance(value, list):
        return [scrub(item) for item in value]
    return value
for stem in ("old-api-health", "old-api-stats", "old-api-probe"):
    with (root / f"{stem}.json").open(encoding="utf-8") as stream:
        before = scrub(json.load(stream))
    with (root / f"{stem}.after.json").open(encoding="utf-8") as stream:
        after = scrub(json.load(stream))
    assert before == after, (stem, before, after)
PY

graph_id=$(docker compose ps -q graph)
graph_ports=$(docker port "${graph_id}" 7878/tcp)
if grep -Ev '^(127[.]0[.]0[.]1|\[::1\]):[0-9]+$' <<<"${graph_ports}" | grep -q .; then
    echo "RETRY_GRAPH_EXPOSURE_FAIL_AFTER: ${graph_ports}" >&2
    exit 2
fi
graph_port=$(awk -F: '/^127[.]0[.]0[.]1:/{print "127.0.0.1:" $NF; exit}' <<<"${graph_ports}")
test -n "${graph_port}"
curl --fail --silent --show-error --get -H 'Accept: application/sparql-results+json' \
    --data-urlencode 'query=SELECT (COUNT(*) AS ?triples) WHERE { { ?s ?p ?o } UNION { GRAPH ?g { ?s ?p ?o } } }' \
    "http://${graph_port}/query" >"${backup_dir}/old-graph-count.after.json"
cmp "${backup_dir}/old-graph-count.json" "${backup_dir}/old-graph-count.after.json"

test "$(schema_count "'meta','raw','enriched','relations','vec','core'")" = 3
test "$(schema_count "'meta_next','raw_next','enriched_next','relations_next','vec_next','core_next'")" = 6
test "$(schema_count "'meta_prev','raw_prev','enriched_prev','relations_prev','vec_prev','core_prev'")" = 0
test "$(schema_count "'meta_failed','raw_failed','enriched_failed','relations_failed','vec_failed','core_failed'")" = 0
test "$("${psql_at[@]}" "SELECT count(*) FROM meta_next.load_run WHERE status='passed' AND phase='cutover_ready' AND validation_result->>'cutover_ready'='true'" | tr -d '\r\n')" = 1

rm -f -- "${scratch_compose_env}" "${probe_env}"
files=(
    postgres.dump oxigraph-volume.tgz postgres-counts.txt oxigraph-volume-name.txt
    pg-restore-list.txt graph-tar-list.txt postgres-restore-drill.txt
    old-api-image.tar old-api-image-id.txt old-api-image-ref.txt
    old-api-health.json old-api-stats.json old-api-probe.json old-graph-count.json
    old-absent-schemas.txt v2-failed-contracts.txt
    next-graph-volume.tgz next-graph-volume-name.txt next-graph-tar-list.txt next-graph-restore-drill.txt next-graph-optimize.txt
    scratch-rdb-validation.json scratch-api-health.json scratch-api-version.json scratch-api-stats.json
    scratch-api-tables.json scratch-api-catalog.json scratch-api-coverage.json
    scratch-restored-counts.txt scratch-schema-roundtrip.txt
    live-rdb-validation.json next-graph-validation.json
    old-api-health.after.json old-api-stats.after.json old-api-probe.after.json old-graph-count.after.json
)
(
    cd "${backup_dir}"
    sha256sum "${files[@]}" >SHA256SUMS
    sha256sum -c SHA256SUMS >/dev/null
)
chmod 600 "${backup_dir}"/*

trap - EXIT
printf 'T105 RETRY READY PASS: backup=%s schemas=3|6|0|0 official=%s holdings=%s subsidiaries=%s next_graph=%s old_api=unchanged graph_host=loopback\n' \
    "${backup_dir}" "${official}" "${holdings}" "${subsidiaries}" "${next_graph}"
