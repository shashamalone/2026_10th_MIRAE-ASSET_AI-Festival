#!/usr/bin/env bash
# feature 브랜치의 런타임 계층(AGENTS.md 디렉터리 구조)만 dev로 반영한다.
# 커밋은 하지 않는다 — status 확인 후 직접 커밋한다.
set -euo pipefail

SRC="${1:-feature/ontology-definition}"
PATHS=(agent tools kb ontology script
       docs docs_data_layer docs_data_collection
       config.py clova.py requirements.txt api.py)

[ -z "$(git status --porcelain -uno)" ] || {
  echo "작업트리가 더럽다. 먼저 커밋하거나 stash 하라."; exit 1; }

git switch dev
# 소스에서 삭제된 파일까지 반영하려면 인덱스를 먼저 비운다
git rm -r --cached -q --ignore-unmatch -- "${PATHS[@]}"
for p in "${PATHS[@]}"; do
  git checkout "$SRC" -- "$p" 2>/dev/null || echo "skip: $p (소스에 없음)"
done

git status --short
echo
echo "확인 후:  git commit -m 'sync: $SRC 런타임 계층 → dev' && git push origin dev"
