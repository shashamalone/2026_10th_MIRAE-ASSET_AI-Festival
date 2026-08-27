[CmdletBinding()]
param(
    [string]$SshTarget = 'user1106@40.82.145.44'
)

$ErrorActionPreference = 'Stop'
$remoteCommand = @'
set -Eeuo pipefail
base=/home/user1106/financial-agent-v2
backup_root=${base}/shared/backups
pointer=${backup_root}/latest-data-api-cutover.txt
release=/home/user1106/financial-agent-v2/releases/57c4edc96bd5cebe7703bb717480b0ebd935b39d

echo '=== POINTER ==='
if [[ ! -s ${pointer} ]]; then
  echo 'NO_LATEST_CUTOVER_POINTER'
  echo 'failure_scope=before_journal_and_before_runtime_mutation'
  echo '=== REPLAY READ-ONLY PREFLIGHT ==='
  set +e
  bash "${base}/incoming/data_api_cutover.sh" --preflight
  preflight_exit=$?
  set -e
  echo "preflight_exit=${preflight_exit}"

  echo '=== PRE-JOURNAL STATE ==='
  cd "${release}"
  printf 'release_env_mode=%s current_env_mode=%s override=%s\n' \
    "$(stat -c '%a' .env)" \
    "$(stat -c '%a' /home/user1106/financial-agent/.env)" \
    "$(test -e compose.override.yaml && echo present || echo absent)"
  docker compose --project-name financial-agent-prep ps --all

  echo '=== SCHEMA SETS ==='
  docker compose --project-name financial-agent-prep exec -T db \
    psql -U agent -d financial_agent -At -v ON_ERROR_STOP=1 -c \
    "SELECT CASE WHEN nspname IN ('meta','raw','enriched','relations','vec','core') THEN 'canonical' WHEN nspname LIKE '%_next' THEN 'next' WHEN nspname LIKE '%_prev' THEN 'prev' WHEN nspname LIKE '%_failed' THEN 'failed' END AS schema_set,count(*) FROM pg_namespace WHERE nspname IN ('meta','raw','enriched','relations','vec','core','meta_next','raw_next','enriched_next','relations_next','vec_next','core_next','meta_prev','raw_prev','enriched_prev','relations_prev','vec_prev','core_prev','meta_failed','raw_failed','enriched_failed','relations_failed','vec_failed','core_failed') GROUP BY 1 ORDER BY 1"

  echo '=== GRAPH ENDPOINTS ==='
  for container in financial-agent-prep-graph-1 financial-product-graph-next; do
    if ! docker container inspect "${container}" >/dev/null 2>&1; then
      echo "container=${container} absent"
      continue
    fi
    docker inspect -f 'container='"${container}"' image={{.Config.Image}} running={{.State.Running}} status={{.State.Status}} mounts={{range .Mounts}}{{.Destination}}={{.Name}};{{end}}' "${container}"
    port=$(docker port "${container}" 7878/tcp 2>/dev/null | awk '/^127[.]0[.]0[.]1:/{print; exit}' || true)
    echo "container=${container} port=${port:-none}"
    if [[ -n ${port} ]]; then
      curl --fail --silent --show-error --get \
        -H 'Accept: application/sparql-results+json' \
        --data-urlencode 'query=SELECT (COUNT(*) AS ?triples) WHERE { GRAPH ?g { ?s ?p ?o } }' \
        "http://${port}/query" || true
      echo
    fi
  done

  echo '=== CUTOVER DIRECTORIES ==='
  find "${backup_root}" -mindepth 2 -maxdepth 2 -type d -name 'data-api-cutover-*' -printf '%p\n' | sort || true
  echo "T105 PREJOURNAL DIAG PASS: preflight_exit=${preflight_exit}"
  exit 0
fi
journal=$(tr -d '\r\n' <"${pointer}")
journal=$(readlink -f -- "${journal}")
case "${journal}" in
  ${backup_root}/data-platform-v2-*/data-api-cutover-*/journal.env) ;;
  *) echo "REFUSE_JOURNAL_PATH: ${journal}"; exit 3 ;;
esac
echo "journal=${journal}"

echo '=== SAFE JOURNAL STATE ==='
grep -E '^(PROJECT|CURRENT_GRAPH|NEXT_GRAPH|STATUS|PHASE|READER_ROTATED|EFFECTIVE_READER_ROTATED|FINISHED_AT|WATCHDOG|WATCHDOG_RESULT|WATCHDOG_AT)=' "${journal}" || true

echo '=== JOURNAL FILES ==='
find "$(dirname "${journal}")" -mindepth 1 -maxdepth 1 -type f -printf '%f %s bytes\n' | sort
if [[ -f $(dirname "${journal}")/watchdog.log ]]; then
  echo '=== WATCHDOG LOG ==='
  tail -n 80 "$(dirname "${journal}")/watchdog.log"
fi

echo '=== COMPOSE STATE ==='
cd "${release}"
docker compose --project-name financial-agent-prep ps --all

echo '=== SERVICE IDENTITIES ==='
for service in db graph api; do
  id=$(docker compose --project-name financial-agent-prep ps -q "${service}" || true)
  if [[ -z ${id} ]]; then
    echo "service=${service} id=absent"
    continue
  fi
  docker inspect -f 'service='"${service}"' id={{.Id}} image={{.Config.Image}} running={{.State.Running}} status={{.State.Status}} exit={{.State.ExitCode}} mounts={{range .Mounts}}{{.Destination}}={{.Name}};{{end}}' "${id}"
done

echo '=== SCHEMA SETS ==='
docker compose --project-name financial-agent-prep exec -T db \
  psql -U agent -d financial_agent -At -v ON_ERROR_STOP=1 -c \
  "SELECT CASE WHEN nspname IN ('meta','raw','enriched','relations','vec','core') THEN 'canonical' WHEN nspname LIKE '%_next' THEN 'next' WHEN nspname LIKE '%_prev' THEN 'prev' WHEN nspname LIKE '%_failed' THEN 'failed' END AS schema_set,count(*) FROM pg_namespace WHERE nspname IN ('meta','raw','enriched','relations','vec','core','meta_next','raw_next','enriched_next','relations_next','vec_next','core_next','meta_prev','raw_prev','enriched_prev','relations_prev','vec_prev','core_prev','meta_failed','raw_failed','enriched_failed','relations_failed','vec_failed','core_failed') GROUP BY 1 ORDER BY 1"

echo '=== GRAPH VOLUMES ==='
docker volume ls --format '{{.Name}}' | grep -E '^financial-agent-prep_oxigraph-(data|next-2026-08-24-57c4edc)$' | sort || true

echo 'T105 DIAG PASS'
'@

$encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($remoteCommand))
$launcher = "printf '%s' '$encoded' | base64 -d | bash"
& ssh $SshTarget $launcher
if ($LASTEXITCODE -ne 0) {
    throw 'T-105 remote diagnosis failed'
}
