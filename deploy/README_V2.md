# 금융상품 데이터 플랫폼 v2 제자리 배포

이 절차는 PostgreSQL 17 + pgvector, Oxigraph, 읽기전용 FastAPI를 유지한다. 운영
PostgreSQL과 Oxigraph 쓰기 권한은 서버 운영자만 사용한다. `.env`, 원천 XLSX, 외부
원문, 임베딩/TTL 산출물과 백업은 Git에 커밋하지 않는다.

## 준비

1. `.env.example`을 서버의 secret store 또는 `.env`로 옮기고 실제 값을 주입한다.
2. `DATASET_DIR`는 `ai-festival2026_금융상품Agent_DtataSet260824`의 정상 XLSX
   8개가 바로 들어 있는 디렉터리로 지정한다. `__MACOSX/._*`는 사용하지 않는다.
3. `LEGACY_DATA_DIR`는 팀원이 제공한 `data/data`를 지정한다. 이 디렉터리는
   20260711 legacy 참고자료이며, 공식 sidecar·cutoff·새 상품 ID를 통과한 ETF
   편입과 DART 자회사 관계만 bundle로 재생성된다.
4. `OXIGRAPH_VOLUME`은 현재 정식 Graph의 정확한 볼륨명, `OXIGRAPH_NEXT_VOLUME`은
   아직 존재하지 않는 release별 새 볼륨명으로 지정한다. 두 값이 같으면 중단한다.
5. API의 `DATABASE_URL`은 `agent_reader`를, 빌더의 `ADMIN_DATABASE_URL`은 운영자
   역할을 사용한다. 비밀번호를 명령행이나 Git 파일에 넣지 않는다.
6. `AGENT_QUERY_URL`은 JSON `{"question":"..."}`을 받아 답변과 근거 또는
   `ABSTAIN_*` 코드를 반환하는 배포 Agent endpoint로 지정한다. 인증이 필요하면
   `AGENT_API_TOKEN`을 secret store로 주입한다.

## 실행

```bash
export OXIGRAPH_NEXT_VOLUME=oxigraph-next-financial-products-2026-08-24
backup_dir="$(./deploy/backup_v2.sh)"
./deploy/stage_v2.sh
./deploy/cutover_v2.sh "${backup_dir}"
```

`stage_v2.sh`는 `*_next`만 재생성하며 정식·`*_prev`에는 손대지 않는다. 원천 검사,
RDB, legacy 근거 감사·관계 bundle, Graph TTL, pgvector schema/동일 해시 재사용,
별도 next Graph 볼륨 적재·SPARQL, 종합 검증 순서다. 신규 CLOVA 호출은 하지 않으며
재사용 불가 시 세 벡터 테이블은 빈 `pending` 상태다. 편입 46,951건과 자회사
8,866건을 강제하고, 감사에서 거부되거나 미해결인 관계는 coverage가 미확보로 남으며
비보유로 바뀌지 않는다.

backup은 dump/Graph tar SHA, `pg_restore --list`, `tar -tzf`, 일회성 restore drill을
통과해야 한다. cutover는 API를 drain한 뒤 PostgreSQL schema rename과 검증된 Graph
volume pointer를 함께 바꾸며 `_prev`가 이미 있으면 중단한다. 팀 검수 전 `_prev`,
`_failed`, 이전/next Graph 볼륨과 백업을 삭제하지 않는다. Graph 검증이나
`expected_question/2026_expected_queries.csv`의 35문항 live 회귀가 실패하면 두
저장소를 함께 원복한다. 롤백 검증이 실패하면 API를 닫은 채 종료한다.

수동 롤백은 다음과 같다.

```bash
./deploy/rollback_v2.sh "${backup_dir}"
```

## 읽기전용 역할

운영자가 `agent_reader` LOGIN 역할을 대화형/secret store로 만든 뒤 다음을 실행한다.

```bash
docker compose exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  < sql/v2/100_readonly_grants.sql
```

Oxigraph 서비스는 `serve-read-only`로만 기동한다. Graph 적재는 서비스를 중지한
점검 시간의 `cutover_v2.sh`만 수행한다.
