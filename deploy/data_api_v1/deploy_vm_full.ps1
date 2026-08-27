[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [switch]$AcceptExistingPublicReadOnlyDbRisk,
    [string]$SshTarget = 'user1106@40.82.145.44',
    [string]$ConsumerBaseUrl = 'http://40.82.145.44:8000',
    [DateTimeOffset]$PublicTestExpiresAt = [DateTimeOffset]::Now.AddDays(2),
    [string]$T105ArtifactDir = '',
    [switch]$PrepareCompatibilityPatchOnly
)

$ErrorActionPreference = 'Stop'
if (-not $AcceptExistingPublicReadOnlyDbRisk) {
    throw 'Explicit -AcceptExistingPublicReadOnlyDbRisk is required for this temporary test VM'
}
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = (Resolve-Path (Join-Path $scriptDir '..\..')).Path
if (-not $T105ArtifactDir) {
    $T105ArtifactDir = Join-Path $repo '..\T-105-data-api-cutover\artifacts\runs\T-105-data-api-cutover\codex-v2-cutover-0826'
}
$sourceT105ArtifactDir = (Resolve-Path $T105ArtifactDir).Path
$patchedT105ArtifactDir = Join-Path $repo 'artifacts\runs\T-106-agent-data-api\codex-agent-data-api-0827\t105-default-graph-fix'
New-Item -ItemType Directory -Path $patchedT105ArtifactDir -Force | Out-Null
Copy-Item -Path (Join-Path $sourceT105ArtifactDir '*') -Destination $patchedT105ArtifactDir -Recurse -Force

$oldGraphQuery = 'query=SELECT (COUNT(*) AS ?triples) WHERE { GRAPH ?g { ?s ?p ?o } }'
$allGraphQuery = 'query=SELECT (COUNT(*) AS ?triples) WHERE { { ?s ?p ?o } UNION { GRAPH ?g { ?s ?p ?o } } }'
foreach ($name in ('data_api_cutover.sh', 'data_api_rollback.sh')) {
    $path = Join-Path $patchedT105ArtifactDir $name
    $content = [IO.File]::ReadAllText($path)
    $matches = ([regex]::Matches($content, [regex]::Escape($oldGraphQuery))).Count
    if ($matches -ne 1) {
        throw "Expected exactly one legacy named-graph count in ${name}; actual=$matches"
    }
    $content = $content.Replace($oldGraphQuery, $allGraphQuery)
    [IO.File]::WriteAllText($path, $content, [Text.UTF8Encoding]::new($false))
}
$cutoverPath = Join-Path $patchedT105ArtifactDir 'data_api_cutover.sh'
$cutoverContent = [IO.File]::ReadAllText($cutoverPath)
$backupContractAnchor = 'for required in postgres.dump oxigraph-volume.tgz oxigraph-volume-name.txt pg-restore-list.txt graph-tar-list.txt postgres-restore-drill.txt postgres-counts.txt; do test -s "${backup_dir}/${required}"; done'
$backupContractReplacement = @'
for required in postgres.dump oxigraph-volume.tgz oxigraph-volume-name.txt pg-restore-list.txt graph-tar-list.txt postgres-restore-drill.txt postgres-counts.txt old-api-image.tar old-api-image-id.txt old-api-image-ref.txt old-api-health.json old-api-stats.json old-api-probe.json old-graph-count.json next-graph-volume.tgz next-graph-tar-list.txt; do test -s "${backup_dir}/${required}"; done
'@.TrimEnd()
if (([regex]::Matches($cutoverContent, [regex]::Escape($backupContractAnchor))).Count -ne 1) {
    throw 'Retry backup contract patch anchor mismatch'
}
$cutoverContent = $cutoverContent.Replace($backupContractAnchor, $backupContractReplacement)
$oldImagePreserve = 'docker tag "${old_api_image}" "${old_api_tag}"'
$safeImagePreserve = @'
recorded_old_api_image=$(tr -d '\r\n' <"${backup_dir}/old-api-image-id.txt")
test "${recorded_old_api_image}" = "${old_api_image}"
if ! docker image inspect "${old_api_image}" >/dev/null 2>&1; then
    echo "OLD_API_IMAGE_RELOAD: restoring exact image from verified backup"
    docker load -i "${backup_dir}/old-api-image.tar" >/dev/null
fi
test "$(docker image inspect -f '{{.Id}}' "${old_api_image}")" = "${recorded_old_api_image}"
docker tag "${old_api_image}" "${old_api_tag}"
'@.TrimEnd()
$imageMatches = ([regex]::Matches($cutoverContent, [regex]::Escape($oldImagePreserve))).Count
if ($imageMatches -ne 1) {
    throw "Expected exactly one legacy old-image tag command; actual=$imageMatches"
}
$cutoverContent = $cutoverContent.Replace($oldImagePreserve, $safeImagePreserve)
$v2ImageNameAnchor = 'v2_api_image=financial-agent-v2-api:${release_sha:0:7}-dbapi-c007'
$v2ImageNameReplacement = 'v2_api_image=financial-agent-v2-api:${release_sha:0:7}-dbapi-c007-g10cov'
if (([regex]::Matches($cutoverContent, [regex]::Escape($v2ImageNameAnchor))).Count -ne 1) {
    throw 'V2 Graph-timeout image-name patch anchor mismatch'
}
$cutoverContent = $cutoverContent.Replace($v2ImageNameAnchor, $v2ImageNameReplacement)
$v2ImageBuildAnchor = 'docker build --label "mafest.runtime-base=${release_sha}" --label "mafest.validator-fix=${validator_commit}" -t "${v2_api_image}" .'
$v2ImageBuildReplacement = @'
v2_api_base_image=financial-agent-v2-api:${release_sha:0:7}-dbapi-c007-base
if ! docker image inspect "${v2_api_base_image}" >/dev/null 2>&1; then
    docker build --label "mafest.runtime-base=${release_sha}" --label "mafest.validator-fix=${validator_commit}" -t "${v2_api_base_image}" .
fi
docker build --build-arg "BASE_IMAGE=${v2_api_base_image}" -t "${v2_api_image}" - <<'DOCKERFILE'
ARG BASE_IMAGE=financial-agent-v2-api:57c4edc-dbapi-c007-base
FROM ${BASE_IMAGE}
RUN python -c 'from pathlib import Path; p=Path("/app/src/api.py"); s=p.read_text(encoding="utf-8"); old1="async with httpx.AsyncClient(timeout=STATEMENT_TIMEOUT_MS / 1000) as client:"; new1="async with httpx.AsyncClient(timeout=10.0) as client:"; old2="\"ORDER BY p.product_type,p.name\","; new2="\"ORDER BY p.product_id LIMIT 101\","; assert s.count(old1)==s.count(old2)==1; p.write_text(s.replace(old1,new1).replace(old2,new2),encoding="utf-8")'
DOCKERFILE
'@.TrimEnd()
if (([regex]::Matches($cutoverContent, [regex]::Escape($v2ImageBuildAnchor))).Count -ne 1) {
    throw 'V2 Graph-timeout image-build patch anchor mismatch'
}
$cutoverContent = $cutoverContent.Replace($v2ImageBuildAnchor, $v2ImageBuildReplacement)
$journalCreationAnchor = 'old_api_image=$(docker inspect -f ''{{.Image}}'' "${api_id}")'
$journalCreationReplacement = @'
old_absent_schemas=$("${psql_at[@]}" "WITH bases(name) AS (VALUES ('meta'),('raw'),('enriched'),('relations'),('vec'),('core')) SELECT string_agg(name,',' ORDER BY name) FROM bases WHERE to_regnamespace(name) IS NULL")
test -n "${old_absent_schemas}"
[[ "${old_absent_schemas}" =~ ^(core|enriched|meta|raw|relations|vec)(,(core|enriched|meta|raw|relations|vec))*$ ]]
old_api_image=$(docker inspect -f '{{.Image}}' "${api_id}")
'@.TrimEnd()
if (([regex]::Matches($cutoverContent, [regex]::Escape($journalCreationAnchor))).Count -ne 1) {
    throw 'Old absent-schema discovery patch anchor mismatch'
}
$cutoverContent = $cutoverContent.Replace($journalCreationAnchor, $journalCreationReplacement)
$journalAnchor = 'OLD_GRAPH_QUADS=${old_graph_quads}'
$journalReplacement = @'
OLD_GRAPH_QUADS=${old_graph_quads}
OLD_ABSENT_SCHEMAS=${old_absent_schemas}
'@.TrimEnd()
if (([regex]::Matches($cutoverContent, [regex]::Escape($journalAnchor))).Count -ne 1) {
    throw 'Old absent-schema journal patch anchor mismatch'
}
$cutoverContent = $cutoverContent.Replace($journalAnchor, $journalReplacement)
$databaseSwitchAnchor = @'
{ printf "SET lock_timeout='10s';\n"; sed -n '1,$p' sql/v2/090_cutover.sql; } | \
  docker compose exec -T db psql -U "${postgres_user}" -d "${postgres_db}"
'@.TrimEnd()
$atomicDatabaseSwitch = @'
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
} | docker compose exec -T db psql -v ON_ERROR_STOP=1 -v old_absent_schemas="${old_absent_schemas}" -U "${postgres_user}" -d "${postgres_db}"
'@.TrimEnd()
if (([regex]::Matches($cutoverContent, [regex]::Escape($databaseSwitchAnchor))).Count -ne 1) {
    throw 'Atomic database-switch patch anchor mismatch'
}
$cutoverContent = $cutoverContent.Replace($databaseSwitchAnchor, $atomicDatabaseSwitch)
$oldPortProbe = 'current_graph_port=$(docker port "${graph_id}" 7878/tcp | awk ''/^127[.]0[.]0[.]1:/{print; exit}'')'
$safePortProbe = 'current_graph_port=$(docker port "${graph_id}" 7878/tcp | awk -F: ''/^(127[.]0[.]0[.]1|0[.]0[.]0[.]0):/{print "127.0.0.1:" $NF; exit}'')'
if (([regex]::Matches($cutoverContent, [regex]::Escape($oldPortProbe))).Count -ne 1) {
    throw 'Cutover Graph-port patch anchor mismatch'
}
$cutoverContent = $cutoverContent.Replace($oldPortProbe, $safePortProbe)
$cutoverGraphStartAnchor = 'OXIGRAPH_ACTIVE_VOLUME="${next_graph}" docker compose -f compose.yaml -f deploy/compose.graph-pointer.yaml up -d graph'
$cutoverGraphStartReplacement = 'GRAPH_BIND=127.0.0.1 OXIGRAPH_ACTIVE_VOLUME="${next_graph}" docker compose -f compose.yaml -f deploy/compose.graph-pointer.yaml up -d graph'
if (([regex]::Matches($cutoverContent, [regex]::Escape($cutoverGraphStartAnchor))).Count -ne 1) {
    throw 'Cutover Graph loopback patch anchor mismatch'
}
$cutoverContent = $cutoverContent.Replace($cutoverGraphStartAnchor, $cutoverGraphStartReplacement)
$cutoverApiStartAnchor = 'DATA_API_IMAGE="${v2_api_image}" OXIGRAPH_ACTIVE_VOLUME="${next_graph}" \'
$cutoverApiStartReplacement = 'GRAPH_BIND=127.0.0.1 DATA_API_IMAGE="${v2_api_image}" OXIGRAPH_ACTIVE_VOLUME="${next_graph}" \'
if (([regex]::Matches($cutoverContent, [regex]::Escape($cutoverApiStartAnchor))).Count -ne 1) {
    throw 'Cutover API Graph-loopback patch anchor mismatch'
}
$cutoverContent = $cutoverContent.Replace($cutoverApiStartAnchor, $cutoverApiStartReplacement)
$runtimeDirAnchor = 'mkdir -p artifacts/runtime'
$cutoverRuntimeDirReplacement = @'
runtime_uid=$(id -u)
runtime_gid=$(id -g)
docker run --rm -e "TARGET_UID=${runtime_uid}" -e "TARGET_GID=${runtime_gid}" \
    -v "${release_dir}/artifacts:/artifacts" busybox:1.36 \
    sh -c 'mkdir -p /artifacts/runtime && chown -R "$TARGET_UID:$TARGET_GID" /artifacts/runtime && chmod 700 /artifacts/runtime'
'@.TrimEnd()
if (([regex]::Matches($cutoverContent, [regex]::Escape($runtimeDirAnchor))).Count -ne 1) {
    throw 'Cutover runtime-directory patch anchor mismatch'
}
$cutoverContent = $cutoverContent.Replace($runtimeDirAnchor, $cutoverRuntimeDirReplacement)
[IO.File]::WriteAllText($cutoverPath, $cutoverContent, [Text.UTF8Encoding]::new($false))

$rollbackPath = Join-Path $patchedT105ArtifactDir 'data_api_rollback.sh'
$rollbackContent = [IO.File]::ReadAllText($rollbackPath)
$rollbackRequiredAnchor = 'OLD_API_IMAGE OLD_API_TAG V2_API_IMAGE LOCK_FILE OLD_GRAPH_QUADS ROLE_EXISTED'
if (([regex]::Matches($rollbackContent, [regex]::Escape($rollbackRequiredAnchor))).Count -ne 1) {
    throw 'Rollback journal contract patch anchor mismatch'
}
$rollbackContent = $rollbackContent.Replace($rollbackRequiredAnchor, 'OLD_API_IMAGE OLD_API_TAG V2_API_IMAGE LOCK_FILE OLD_GRAPH_QUADS OLD_ABSENT_SCHEMAS ROLE_EXISTED')
$rollbackSwitchAnchor = 'docker compose exec -T db psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" < sql/v2/095_rollback.sql'
$atomicRollbackSwitch = @'
[[ "${OLD_ABSENT_SCHEMAS}" =~ ^(core|enriched|meta|raw|relations|vec)(,(core|enriched|meta|raw|relations|vec))*$ ]]
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
       OR obj_description(schema_oid, 'pg_namespace') IS DISTINCT FROM 'empty rollback placeholder for a schema absent before V2 cutover'
       OR pg_get_userbyid((SELECT nspowner FROM pg_namespace WHERE oid=schema_oid)) IS DISTINCT FROM current_user THEN
      RAISE EXCEPTION 'unsafe rollback placeholder: %', base_name;
    END IF;
    EXECUTE format('DROP SCHEMA %I RESTRICT', base_name);
  END LOOP;
END
$do$;
COMMIT;
SQL
} | docker compose exec -T db psql -v ON_ERROR_STOP=1 -v old_absent_schemas="${OLD_ABSENT_SCHEMAS}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"
'@.TrimEnd()
if (([regex]::Matches($rollbackContent, [regex]::Escape($rollbackSwitchAnchor))).Count -ne 1) {
    throw 'Atomic rollback-switch patch anchor mismatch'
}
$rollbackContent = $rollbackContent.Replace($rollbackSwitchAnchor, $atomicRollbackSwitch)
$oldRollbackPortProbe = 'graph_port=$(docker port "${graph_id}" 7878/tcp | awk ''/^127[.]0[.]0[.]1:/{print; exit}'')'
$safeRollbackPortProbe = 'graph_port=$(docker port "${graph_id}" 7878/tcp | awk -F: ''/^(127[.]0[.]0[.]1|0[.]0[.]0[.]0):/{print "127.0.0.1:" $NF; exit}'')'
if (([regex]::Matches($rollbackContent, [regex]::Escape($oldRollbackPortProbe))).Count -ne 1) {
    throw 'Rollback Graph-port patch anchor mismatch'
}
$rollbackContent = $rollbackContent.Replace($oldRollbackPortProbe, $safeRollbackPortProbe)
$rollbackGraphStartAnchor = 'COMPOSE_PROJECT_NAME="${PROJECT}" docker compose up -d graph'
$rollbackGraphStartReplacement = 'GRAPH_BIND=127.0.0.1 COMPOSE_PROJECT_NAME="${PROJECT}" docker compose up -d graph'
if (([regex]::Matches($rollbackContent, [regex]::Escape($rollbackGraphStartAnchor))).Count -ne 1) {
    throw 'Rollback Graph loopback patch anchor mismatch'
}
$rollbackContent = $rollbackContent.Replace($rollbackGraphStartAnchor, $rollbackGraphStartReplacement)
$rollbackApiStartAnchor = 'DATA_API_IMAGE="${OLD_API_TAG}" COMPOSE_PROJECT_NAME="${PROJECT}" \'
$rollbackApiStartReplacement = 'GRAPH_BIND=127.0.0.1 DATA_API_IMAGE="${OLD_API_TAG}" COMPOSE_PROJECT_NAME="${PROJECT}" \'
if (([regex]::Matches($rollbackContent, [regex]::Escape($rollbackApiStartAnchor))).Count -ne 1) {
    throw 'Rollback API Graph-loopback patch anchor mismatch'
}
$rollbackContent = $rollbackContent.Replace($rollbackApiStartAnchor, $rollbackApiStartReplacement)
$rollbackRuntimeDirReplacement = @'
runtime_uid=$(id -u)
runtime_gid=$(id -g)
docker run --rm -e "TARGET_UID=${runtime_uid}" -e "TARGET_GID=${runtime_gid}" \
    -v "${RELEASE_DIR}/artifacts:/artifacts" busybox:1.36 \
    sh -c 'mkdir -p /artifacts/runtime && chown -R "$TARGET_UID:$TARGET_GID" /artifacts/runtime && chmod 700 /artifacts/runtime'
'@.TrimEnd()
if (([regex]::Matches($rollbackContent, [regex]::Escape($runtimeDirAnchor))).Count -ne 1) {
    throw 'Rollback runtime-directory patch anchor mismatch'
}
$rollbackContent = $rollbackContent.Replace($runtimeDirAnchor, $rollbackRuntimeDirReplacement)
[IO.File]::WriteAllText($rollbackPath, $rollbackContent, [Text.UTF8Encoding]::new($false))

$verifyPath = Join-Path $patchedT105ArtifactDir 'data_api_verify.sh'
$verifyContent = [IO.File]::ReadAllText($verifyPath)
$oldEndpointLoop = @'
for path in /db/version /db/stats /db/tables /db/catalog /db/coverage; do
    curl --fail --silent --show-error "${api_url}${path}" >/dev/null
done
'@.TrimEnd()
$diagnosticEndpointLoop = @'
for path in /db/version /db/stats /db/tables /db/catalog /db/coverage; do
    response_file=$(mktemp)
    status=$(curl --silent --show-error --output "${response_file}" --write-out '%{http_code}' "${api_url}${path}")
    printf 'VERIFY_HTTP: path=%s status=%s\n' "${path}" "${status}"
    if [[ "${status}" != 200 ]]; then
        cat "${response_file}" >&2
        rm -f -- "${response_file}"
        exit 1
    fi
    rm -f -- "${response_file}"
done
'@.TrimEnd()
if (([regex]::Matches($verifyContent, [regex]::Escape($oldEndpointLoop))).Count -ne 1) {
    throw 'V2 endpoint diagnostic patch anchor mismatch'
}
$verifyContent = $verifyContent.Replace($oldEndpointLoop, $diagnosticEndpointLoop)
[IO.File]::WriteAllText($verifyPath, $verifyContent, [Text.UTF8Encoding]::new($false))
Write-Host 'T-105 compatibility patch prepared: atomic schema restore, verified image archive, full Graph/port support, endpoint diagnostics.'

$t105 = Join-Path $patchedT105ArtifactDir 'data_api_cutover.ps1'
$t106 = Join-Path $scriptDir 'deploy_vm.ps1'
foreach ($file in ($t105, $t106)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing deployment script: $file" }
}
if ($PrepareCompatibilityPatchOnly) {
    Write-Output "T-105 PATCH PREP PASS: $patchedT105ArtifactDir"
    return
}

$expected = 'financial-products-2026-08-24@ddb3d994a4a5115a75bed7efa9c4cd0f6655f95b0a49f3b0e3c01b2bf8301a38'
$v2Active = $false
try {
    $health = Invoke-RestMethod -Uri "$ConsumerBaseUrl/health" -TimeoutSec 20
    $v2Active = (
        $health.status -eq 'ok' -and
        $health.readiness -eq $true -and
        $health.rdb.release_id -eq $expected -and
        $health.graph.release_id -eq $expected
    )
}
catch {
    $v2Active = $false
}

if (-not $v2Active) {
    $probe = Invoke-RestMethod -Method Post -Uri "$ConsumerBaseUrl/db" -ContentType 'application/json' -Body '{"sql":"SELECT 1 AS probe"}' -TimeoutSec 20
    if ($probe.rows[0].probe -ne '1' -and $probe.rows[0].probe -ne 1) {
        throw 'Existing public read-only DB probe did not return 1; refusing risk-mode cutover'
    }
    Write-Warning 'The current VM already exposes guarded read-only /db publicly. T-105 will retain that state only until T-106 replaces it and blocks /db*.'
    $retryPreparation = Join-Path $scriptDir 'prepare_t105_retry.ps1'
    & $retryPreparation -SshTarget $SshTarget -ConsumerBaseUrl $ConsumerBaseUrl
    if ($LASTEXITCODE -ne 0) { throw 'T-105 retry preparation failed' }
    & $t105 -Preflight -SshTarget $SshTarget -ConsumerBaseUrl $ConsumerBaseUrl
    if ($LASTEXITCODE -ne 0) { throw 'T-105 preflight failed' }
    # T-105 predates the explicit existing-public-risk mode. Its legacy switch is
    # used only after the external probe and caller acknowledgement above.
    & $t105 -ApproveReplaceExistingService -ConfirmTeamRestrictedAccess -SshTarget $SshTarget -ConsumerBaseUrl $ConsumerBaseUrl
    if ($LASTEXITCODE -ne 0) { throw 'T-105 cutover failed or rolled back' }
}
else {
    Write-Host 'T-105 V2 DB/Graph release is already active; skipping cutover.'
}

& $t106 -SshTarget $SshTarget -ConsumerBaseUrl $ConsumerBaseUrl -PublicTestExpiresAt $PublicTestExpiresAt
if ($LASTEXITCODE -ne 0) { throw 'T-106 curated API deployment failed' }
Write-Output "FULL VM DEPLOY PASS: release=$expected public=$ConsumerBaseUrl expires=$($PublicTestExpiresAt.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')) raw_db=blocked"
