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
4. `OXIGRAPH_VOLUME`은 `docker volume ls`로 확인한 정확한 볼륨명으로 지정한다.
5. API의 `DATABASE_URL`은 `agent_reader`를, 빌더의 `ADMIN_DATABASE_URL`은 운영자
   역할을 사용한다. 비밀번호를 명령행이나 Git 파일에 넣지 않는다.
6. `AGENT_QUERY_URL`은 JSON `{"question":"..."}`을 받아 답변과 근거 또는
   `ABSTAIN_*` 코드를 반환하는 배포 Agent endpoint로 지정한다. 인증이 필요하면
   `AGENT_API_TOKEN`을 secret store로 주입한다.

## 실행

```bash
backup_dir="$(./deploy/backup_v2.sh)"
./deploy/stage_v2.sh
./deploy/cutover_v2.sh "${backup_dir}"
```

`stage_v2.sh`는 `*_next`만 재생성하며 정식·`*_prev`에는 손대지 않는다. 원천 검사,
RDB, legacy 근거 감사·관계 bundle, Graph TTL, CLOVA bge-m3 1024차원 embedding,
종합 검증 순서다. 감사에서 거부되거나 미해결인 관계는 coverage가 미확보로 남으며
비보유로 바뀌지 않는다.

cutover는 `_prev`가 이미 있으면 중단한다. 팀 검수 전 `_prev`, `_failed`, 백업을
삭제하지 않는다. Graph 적재나 `expected_question/2026_expected_queries.csv`의
35문항 live 회귀가 실패하면 rollback 스크립트가 PostgreSQL 스키마와 Oxigraph
볼륨 아카이브를 복원한다.

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
