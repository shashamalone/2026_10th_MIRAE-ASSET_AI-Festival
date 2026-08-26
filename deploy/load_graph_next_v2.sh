#!/usr/bin/env bash
set -euo pipefail

: "${OXIGRAPH_NEXT_VOLUME:?use a new versioned Oxigraph volume name}"
: "${OXIGRAPH_VOLUME:?set the exact current production Oxigraph volume name}"

if [[ "${OXIGRAPH_NEXT_VOLUME}" == "${OXIGRAPH_VOLUME}" ]]; then
  echo "next Graph volume must differ from the production volume" >&2
  exit 2
fi
if docker volume inspect "${OXIGRAPH_NEXT_VOLUME}" >/dev/null 2>&1; then
  echo "refusing to overwrite existing next Graph volume: ${OXIGRAPH_NEXT_VOLUME}" >&2
  exit 2
fi

image="${OXIGRAPH_IMAGE:-ghcr.io/oxigraph/oxigraph:latest}"
next_container="${OXIGRAPH_NEXT_CONTAINER:-financial-product-graph-next}"
compose_network="${COMPOSE_PROJECT_NAME:-financial-product-platform-v2}_default"
if docker container inspect "${next_container}" >/dev/null 2>&1; then
  echo "next Graph validation container already exists: ${next_container}" >&2
  exit 2
fi

docker volume create "${OXIGRAPH_NEXT_VOLUME}" >/dev/null
for name in common bond_kr etf_kr etf_gl fund_pub; do
  docker run --rm \
    -v "${OXIGRAPH_NEXT_VOLUME}:/data" \
    -v "${PWD}/ontology:/tbox:ro" \
    "${image}" load --location /data \
    --file "/tbox/${name}.ttl" --graph "http://mafest.ai/graph/tbox/${name}"
done
for name in bond_kr etf_kr etf_gl fund_pub company; do
  docker run --rm \
    -v "${OXIGRAPH_NEXT_VOLUME}:/data" \
    -v "${PWD}/artifacts/graph_v2:/abox:ro" \
    "${image}" load --location /data \
    --file "/abox/instances_${name}.ttl" --graph "http://mafest.ai/graph/abox/${name}"
done
docker run --rm -v "${OXIGRAPH_NEXT_VOLUME}:/data" \
  "${image}" optimize --location /data

docker run -d --name "${next_container}" --network "${compose_network}" \
  -v "${OXIGRAPH_NEXT_VOLUME}:/data" \
  "${image}" serve-read-only --location /data --bind 0.0.0.0:7878 >/dev/null

printf '%s\n' "OXIGRAPH_NEXT_QUERY_URL=http://${next_container}:7878/query"
