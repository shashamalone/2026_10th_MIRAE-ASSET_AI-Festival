# CURRENT DATA BUILD STRUCTURE

자동 생성 파일입니다. 직접 편집하지 말고 `python src/kb/build_catalog_v2.py`를 실행합니다.

## 데이터 계약

- 버전: `financial-products-2026-07-11`
- 배포일/외부 근거 상한: `2026-07-11`
- 전체 manifest SHA-256: `0f27e46933a327bd313458a6ef69c456e956c21921497e216675ebb4b1e0aec0`
- 원천: `_conversion_manifest.json`이 승인한 2026-07-11 데이터 CSV 4개와 스키마 CSV 4개만 사용합니다.
- 런타임: PostgreSQL 17 + pgvector + Oxigraph + 읽기전용 FastAPI
- 제출 경로에서 제외: DuckDB, FAISS, pyoxigraph, Gemini

## 원천 정본

| 코드 | 데이터 파일 | 행 | 열 | 실질 기준일 | 공식 Nullable 충돌(NULL 건수) | SHA-256 |
|---|---|---:|---:|---|---|---|
| PRBD01N001 | `PRBD01N001_bond_kr_master_20260711.csv` | 42,394 | 40 | 2026-02-24 | - | `e62894688f48c7a56735024d64881e34c1d7bfead3c1b8800c8f2b4d5f47cc3e` |
| PREF01N001 | `PREF01N001_etf_kr_master_20260711.csv` | 1,734 | 73 | 2026-06-15 | - | `0f8a1d0ac3f755f450a5a3ea7ff11c2e1fbe8f2210282d5e7d20c46eca92481f` |
| PREF02N001 | `PREF02N001_etf_gl_master_20260711.csv` | 5,646 | 49 | 2026-06-16 | - | `ada15bc0da0327db226e9ffc2e223e60f71c7f9977e34868af20295aabc166a1` |
| PRFD01N001 | `PRFD01N001_fund_pub_master_20260711.csv` | 95,619 | 45 | 2026-07-11 | - | `073a5f13c775422dd343bdf870a3184d2743cdde95923e297045dba6b9bb4ed1` |

## 빌드 순서

1. 승인 manifest·SHA-256·행/열·공식 헤더·PK 유일성·cutoff 검사
2. `raw_next`에 공식 타입·컬럼 그대로 적재(공백만 NULL, 0 보존)
3. `enriched_next`·`relations_next`·`meta_next` 생성
4. 결정적 ABox TTL 5개 생성 및 TBox/ABox RDF 검증
5. CLOVA Studio `bge-m3` 1024차원 schema/content embedding 적재
6. PK/FK·cutoff·Graph·Vector·교차질의·금지 SQL 검증
7. 검증 완료 후에만 `*_next → 정식`, 기존 정식 → `*_prev` 전환

모든 빌더의 `--check`는 파일과 DB를 변경하지 않습니다. 데이터·외부 원문·임베딩은
Git에 넣지 않고 이 카탈로그, 코드, SQL, 문서와 체크섬만 공유합니다.

## 물리 스키마

| 스키마 | 물리 테이블 수 |
|---|---:|
| `enriched` | 11 |
| `meta` | 4 |
| `raw` | 4 |
| `relations` | 5 |
| `vec` | 3 |

호환 뷰와 materialized view는 `TABLE_DEFINITION_V2_0.md`의 뷰 절을 따릅니다.

## 핵심 의미 규칙

- `buyable_quantity`는 raw/offer 저장 전용이며 구매가능 판정·필터·정렬에 사용하지 않습니다.
- 채권은 최신 정본에 있고 명시적으로 만기 또는 리스팅 종료가 아닌 경우에만
  `is_assumed_purchasable=true`이며 `purchasable_rule`을 함께 반환합니다.
- 측정값의 0/NULL은 `product_metric.is_available=false`로 비교·랭킹에서 제외합니다.
- 코드/플래그 0은 공식 설명을 따르며 이름 컬럼이 없으면 의미를 추측하지 않습니다.
- 동일 지표는 주최측 값이 우선이고 주최측에 축이 없을 때만 cutoff 검증 외부값을 씁니다.
- 미확보 관계는 `meta.product_coverage`에 이유를 저장하며 비보유로 해석하지 않습니다.
- 공식 `Nullable=NO`와 정본 공백이 충돌하면 해당 컬럼만 NULL을 허용하고 충돌 건수를
  manifest·카탈로그에 기록합니다. PK는 예외 없이 NOT NULL입니다.
