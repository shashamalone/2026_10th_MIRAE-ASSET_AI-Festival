# 데이터 레이어 계획 (원본 / 보강 / 관계)

> 현행 기준: 주최측 2026-08-24 배포본 · 외부 데이터 허용 상한 `as_of <= 2026-08-24`

## 1. 판단 기준

1. 주최측 원천은 `data/csv/`에 그대로 두며 값 수정·컬럼 추가를 하지 않는다.
2. 1:1 스칼라 보강은 `data/enriched/`, 1:N 관계는 `data/relations/`에 둔다.
3. 외부 원천은 `data/external/`에 원본과 `{원본파일명}.meta.json`을 함께 둔다.
4. 주최측 값과 외부 값이 충돌하면 주최측을 우선하고 충돌 사실을 기록한다.
5. 기준일을 추정하지 않는다. 정책 상한과 실제 `as_of`를 분리한다.

## 2. 디렉터리와 파일명

```text
data/csv/        주최측 Excel 변환본(동결)
data/enriched/   원천과 동일 그레인의 스칼라 보강
data/relations/  주어-목적어 1건/행 관계
data/external/   외부 원본 + sidecar metadata
ontology/        TBox와 생성 ABox
artifacts/       재생성 가능한 빌드 결과
```

| 종류 | 규칙 | 예시 |
|---|---|---|
| 주최측 변환본 | `{테이블코드}_{슬러그}_{종류}_{스냅샷}.csv` | `PRFD01N001_fund_pub_master_20260824.csv` |
| 파생·관계 | `{슬러그}_{종류}.csv` | `bond_kr_enriched.csv`, `etf_theme.csv` |
| 외부 원천 | 출처 식별자와 실제 기준일 포함 | `dart_corpcode_20260711.xml` |
| 외부 sidecar | 원본 전체 파일명 뒤 `.meta.json` | `dart_corpcode_20260711.xml.meta.json` |

## 3. 생성 규칙

- builder는 입력·출력 경로와 PK를 명시하고 결정적으로 실행되어야 한다.
- 원천 컬럼은 소문자 이름과 UTF-8 BOM을 그대로 처리한다.
- 파생 테이블은 원천 PK를 보존한다. 채권은 `(pd_no,pd_exg_mkt,info_seq)`, ETF는 `pd_itm_no`다.
- 펀드는 `itm_no`가 단독 유일키이고 `prfd_attr_cds`가 집약돼 있으므로 별도 dedup을 만들지 않는다.
- 관계 테이블은 `source`와 실제 `as_of`를 가진다. 기준일이 불명인 경우 빈 값으로 남긴다.
- 외부 데이터는 sidecar의 `as_of <= 2026-08-24`를 검증한 뒤 사용한다.

## 4. 산출물 현황

| 산출물 | 그레인·역할 | 원천 | builder |
|---|---|---|---|
| `data/enriched/bond_kr_enriched.csv` | 채권 복합 PK별 등급 rank·잔존만기·구매가능 | 주최측 채권 master | `build_bond_enrichment.py` |
| `data/enriched/etf_kr_enriched.csv` | ETF별 총보수·복제방식 보완 | 주최측 ETF + LSEG | `build_etf_enrichment.py` |
| `data/enriched/company_master.csv` | 기업 1건/행 | DART corpCode + KIND | `build_company_relations.py` |
| `data/enriched/holding_code_map.csv` | 편입코드 1건/행 | ETF holding + company master | `build_holding_code_map.py` |
| `data/relations/etf_theme.csv` | ETF-테마 1건/행 | LSEG | `build_etf_enrichment.py` |
| `data/relations/etf_holding.csv` | ETF-편입종목 1건/행 | 운용사 snapshot | `build_etf_holding.py` |
| `data/relations/company_subsidiary.csv` | 모회사-자회사 출자 1건/행 | DART 공시 | `build_company_relations.py` |

정확한 행수·컬럼수는 `DATA_INVENTORY.md`에서만 관리한다.

## 5. 도메인별 안전 규칙

### 채권

- 물리 조인은 복합키를 사용하고 종목 집계는 `DISTINCT pd_no`로 한다.
- `buyable_quantity`는 조회·필터·evidence에 쓰지 않는다.
- 구매가능은 원화이면서 `remaining_days > 0`인 종목으로 정의한다.

### ETF

- 국내 ETF 질의는 `pd_grp_no='ETF'`가 필수다.
- LSEG 보강은 주최측 값이 비었거나 명백한 0.0 dummy일 때만 사용한다.
- ETF holding은 실제 `as_of=2026-07-10` 외부 snapshot이다.

### 펀드

- 1행=1펀드이며 `itm_no`가 단독 PK다.
- 공모 질의는 `prvo_pbff_desc='공모'`로 사모를 제외한다.
- 판매중·당사판매 모집단은 `sale_yn`과 `thco_sale_yn`을 함께 적용한다.
- 보수 4종은 천분율을 %로 변환하고 `fd_prsv_r`은 합산하지 않는다.

## 6. 외부 provenance

허용 상한 2026-08-24는 실제 수집일을 뜻하지 않는다.

- ETF 편입관계: `as_of=2026-07-10`
- DART/KIND 기업 원천: 파일·sidecar의 `as_of=2026-07-11`
- 자회사 관계: 공시 접수번호에서 구한 행별 날짜
- ETF theme: 기준일 미확인, NULL 유지

과거 날짜가 파일명에 있다는 이유로 08-24로 이름을 바꾸거나 metadata를 덮어쓰지 않는다.

## 7. 변경 추적과 검증

```bash
python3 script/build_data_inventory.py
python3 src/kb/build_rdb.py --check
python3 src/kb/build_schema_catalog.py --check
python3 script/validate_external.py
python3 script/validate_ontology.py
python3 script/test_rdb_vertical_slice.py --db
```

`DATA_INVENTORY.md`와 `table_definition_v1_0.csv`는 생성기로만 갱신한다.

## 8. 다음 후보

- 해외 ETF와 공모펀드 편입종목 관계
- 펀드 투자전략·운용철학 content index
- Graph Store 적재와 SPARQL runtime
- cutoff 이하 최신 외부 snapshot 선택 로직
