# 금융상품 데이터 플랫폼 v2 구현·운영 계약

## 적용 범위

`financial-products-2026-08-24`는 정상 XLSX 8개만 정본으로 사용한다. 원천 파일,
외부 원문, 생성 TTL, 임베딩 및 비밀값은 Git 산출물이 아니다. Git에는 결정적 빌더,
SQL, 카탈로그, 검증기, 배포·롤백 코드와 원천 체크섬만 둔다.

| 단계 | 구현 | Git 산출물 | 운영 산출물 |
|---|---|---|---|
| 원천 검사 | `kb.v2_manifest` | 파일명·shape·PK·SHA 계약 | 없음 |
| raw/enriched/relations | `kb.build_data_platform_v2` | 공식 DDL·변환 SQL | PostgreSQL `*_next` |
| Graph | `kb.build_graph_v2` | TBox 5개·결정적 빌더 | ABox 5개·Oxigraph named graph |
| Vector | `kb.build_vectors_v2` | 청크/임베딩 빌더 | pgvector 1024차원·HNSW |
| 검증 | `kb.validate_data_platform_v2` | 정적·stage 계약 | 검증 결과 JSON |
| 배포 | `deploy/*.sh` | 백업·전환·복구 절차 | 정식 스키마·Graph 볼륨 |

## 결정 규칙

- `BUYABLE_QUANTITY`는 값 제시를 위해 저장할 수 있지만 구매·판매가능 판정,
  필터, 정렬 또는 실행계획에는 사용하지 않는다.
- 채권 구매가능 여부는 최신 정본 존재와 명시적 만기·리스팅 종료만으로 보수적으로
  가정하고, `purchasable_rule`을 항상 함께 반환한다.
- 측정값 0/NULL은 `is_available=false`로 저장해 랭킹에서 제외한다. 코드/플래그
  0은 공식 설명을 따른다.
- `product_coverage`의 `unavailable`은 관계 미확보이며 비보유를 뜻하지 않는다.
- 같은 지표는 주최측 축이 있으면 주최측 값을 사용한다. 해당 축 자체가 없을 때만
  발행일·기준일이 2026-08-24 이하인 외부값을 허용한다.
- 해외ETF 1년 수익률은 LSEG Platform OAuth로 조회한 adjusted price 또는
  total-return 계열 필드만 사용한다. 권한상 필드가 없으면 종가로 대체하지 않는다.

LSEG 수집 구현은 공식 [Historical Pricing 튜토리얼](https://developers.lseg.com/en/api-catalog/lseg-data-platform/lseg-data-library-for-python/tutorials/content-tutorials/historical-pricing)의
날짜 범위 호출과 [Platform 인증 가이드](https://developers.lseg.com/en/api-catalog/lseg-data-platform/lseg-data-library-for-python/quick-start)의
자격증명 방식을 따른다.

## 실행 순서

읽기 전용 검사는 파일이나 DB를 변경하지 않는다.

```bash
python script/build_catalog_v2.py --check
python script/build_data_platform_v2.py --check
python script/build_vectors_v2.py --check
python script/validate_data_platform_v2.py
python script/regression_v2.py --check
```

운영 스테이징과 전환은 [`deploy/README_V2.md`](../../deploy/README_V2.md)를 따른다.
`stage_v2.sh`가 원천→RDB→외부 관계→Graph→Vector→통합 검증 순서를 고정한다.
정적 검증 성공은 운영 DB·외부 API·35문항 실질 응답 검증 성공을 대신하지 않는다.

## 공개 인터페이스

`/db/sql`, `/db/sparql`, `/db/tables`, `/db/columns`는 호환 유지하며
`/db/catalog`, `/db/coverage`, `/db/version`을 추가한다. SQL/SPARQL은 읽기 전용
문장만 허용하고 PostgreSQL 트랜잭션도 읽기 전용으로 설정한다. `/health`는 데이터
버전, raw 행 수, Graph 트리플 수, Vector 행 수와 CLOVA 설정 여부를 반환한다.

## 완료 판정

운영 완료는 백업 생성, `*_next` 통합 검증, 트랜잭션 스키마 전환, Graph 재적재,
API 헬스 체크, 35문항 live 회귀를 모두 통과한 때만 선언한다. 실패 시 PostgreSQL
스키마와 Graph 볼륨을 함께 복구하며 팀 검수 전 `_prev`와 백업을 삭제하지 않는다.
