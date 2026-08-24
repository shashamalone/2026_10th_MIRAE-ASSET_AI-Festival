# 데이터 레이어 계획 (원본 / 보강 / 관계)

새로 만드는 모든 값을 어디에 둘지에 대한 단일 기준. 근거 표시(주최측 데이터 vs 외부 보강 구분)와 15초 응답(RDB 선필터)을 동시에 만족하기 위한 구조다.

## 판단 기준

| 값의 모양 | 저장 위치 | 예시 |
|---|---|---|
| 상품 1개당 값 1개 (스칼라) 또는 원본의 재그레인 | 파생 테이블 (`data/enriched/`) | ter(총보수), replication, hedge_type, is_sellable, 등급 ordinal, 펀드 dedup |
| 상품 1개당 값 N개 / 엔티티 간 연결 | 관계 테이블 (`data/relations/`) → ttl 트리플 | themes, 구성종목, 기업↔자회사, ETF↔지수 |

- 다중값을 CSV 컬럼에 `;`로 이어붙이면 SQL 필터·그래프 탐색 둘 다 망가진다 → 관계는 반드시 롱포맷 관계 테이블.
- 스칼라를 그래프에만 두면 정렬·비교 질의가 SPARQL로 밀려 15초 제한에 불리하다 → 스칼라는 RDB 컬럼.
- 관계 테이블은 온톨로지의 원천이다: 같은 CSV에서 RDB 적재와 `ontology/*.ttl` 트리플 생성을 둘 다 뽑는다(이중 작업 아님).

## 디렉터리 구조

```
data/csv/        원본 변환본만. 동결 — 파생물 저장 금지, 컬럼 추가·값 수정 금지
data/enriched/   원본 파생 테이블 (재그레인 + 스칼라 보강). 원본 PK + 출처 컬럼(*_source)
data/relations/  롱포맷 관계 테이블 (주어ID, 목적어, source, as_of)
data/external/   외부 수집 원천 (EXTERNAL_DATA_PLAN.md 규칙: as_of ≤ 2026-07-11, 사이드카 JSON)
ontology/*.ttl   relations + enriched 스키마에서 생성

script/*.py      실행 스크립트 (build_*.py 파생 생성, collect_*.py 수집, validate_*.py 검증)
EDA/src/*.py     jupytext 노트북 소스 전용 (01~05). 실행 스크립트를 여기 두지 않는다
docs/docs_data_layer/ · docs/docs_data_collection/  문서
```

### 파일명 규칙

| 대상 | 규칙 | 예 |
|---|---|---|
| 원본 변환본 | `{테이블코드}_{슬러그}_{종류}_{스냅샷}.csv` — 출처 추적이 필요하므로 테이블코드·날짜 유지 | `PRFD01N001_fund_pub_master_20260711.csv` |
| 파생/관계 테이블 | `{슬러그}_{종류}.csv` — 스냅샷이 하나뿐이라 날짜 중복 표기 안 함 | `fund_pub_dedup.csv`, `etf_theme.csv` |
| 외부 수집 원천 | `{식별자}_{as_of}.{확장자}` + 사이드카 `{원본파일명}.meta.json` | `kodex_200_20260710.xls` + `kodex_200_20260710.xls.meta.json` |

파일명은 **ASCII만** 사용한다. 원본 xlsx가 NFD 한글이라 경로 하드코딩이 깨졌던 전례가 있다.

## 외부 원천 → 관계 테이블 파이프라인

`data/external/`은 **원천 보관소**이고 질의에 직접 쓰이지 않는다. 반드시 `script/build_*.py`를 거쳐 정규화된 `data/relations/` 또는 `data/enriched/`로 떨어뜨린 뒤 사용한다.

```
data/external/{항목}/{파일} + 사이드카 JSON(source, as_of, retrieved_at, url)
        │  script/build_*.py — 식별자 정규화, 조인키 매핑, as_of·source 부여
        ▼
data/relations/*.csv (관계) 또는 data/enriched/*.csv (스칼라)
        │  ontology 빌드
        ▼
ontology/*.ttl
```

관계 테이블의 `as_of`는 사이드카 JSON의 `as_of`를 그대로 승계한다. 시점을 모르는 관계는 `as_of`를 빈 값으로 두되 **추정 날짜를 채워 넣지 않는다** — 근거 표시에서 거짓 기준일이 되기 때문이다.

## 생성 규칙

1. **원본 동결**: `data/csv/`에는 원본 변환본만 둔다. 값 수정·컬럼 추가는 물론 파생 테이블 저장도 금지. 깨진 행(펀드 itm_no=`"`) 배제도 파생 테이블에서만.
2. **출처 컬럼 필수**: 보강 스칼라에는 `{컬럼}_source`를, 관계 테이블에는 `source`·`as_of`를 붙인다 (`RDB` = 주최측 값, `LSEG` 등 = 외부). 답변 evidence가 이 컬럼을 그대로 인용한다.
3. **우선순위**: 주최측 값이 0이 아닌 실값이면 주최측 우선 → 결측·0.0 더미면 외부로 보완 → 둘 다 없으면 결측 유지("확인할 수 없음" 대상).
4. **재현 가능**: 모든 파생 테이블은 `script/build_*.py` 스크립트로 생성한다. 수작업 편집 금지.

## 산출물 현황

`원천데이터` 열은 이 파일이 어느 데이터에서 파생됐는지를 나타낸다. **주최측**은 2026-07-11 스냅샷 원본(`data/csv/`), **외부**는 대회 규칙상 `as_of ≤ 2026-07-11`을 지켜 별도 수집한 데이터(상세는 `EXTERNAL_DATA_SOURCES.md`), **내부 파생**은 이 표의 다른 행을 조합해 만든 2차 산출물이다.

| 파일 | 내용 | 원천데이터 | 스크립트 |
|---|---|---|---|
| `data/enriched/fund_pub_dedup.csv` | 펀드 1행화(11,138), 속성코드는 `prfd_attr_cds`로 집약 | 주최측 `PRFD01N001_fund_pub_master` | `build_fund_dedup.py` |
| `data/enriched/etf_kr_enriched.csv` | 국내ETF/ETN PK + LSEG 스칼라(ter·replication·base_market·base_asset·hedge_type) + `charge_rt_final`/`charge_rt_source` | 주최측 `PREF01N001_etf_kr_master` + 외부 LSEG(`lseg_static_metadata.json`) | `build_etf_enrichment.py` |
| `data/enriched/bond_kr_enriched.csv` | 국내채권 PK + 등급 ordinal(`crd_grd_rank`, 1=AAA) + 잔존만기(`remaining_days`/`maturity_bucket`, 2026-07-11 기준 재계산) + `is_sellable`(254건) | 주최측 `PRBD01N001_bond_kr_master` | `build_bond_enrichment.py` |
| `data/relations/etf_theme.csv` | 국내ETF↔테마 (LSEG themes, 176종) 롱포맷. `as_of`는 LSEG 수집 시점 미확인이라 공란 | 외부 LSEG(`lseg_static_metadata.json`) | `build_etf_enrichment.py` |
| `data/relations/etf_holding.csv` | 국내ETF↔편입종목 (KODEX/TIGER/RISE/ACE 4사, `as_of` 2026-07-10) 롱포맷. 식별자는 원본 보존(`holding_code_raw`/`holding_code_type`) | 외부 운용사 4사 API(KODEX/TIGER/RISE/ACE) | `collect_etf_holdings.py` → `build_etf_holding.py` |
| `data/enriched/company_master.csv` | DART 기업 고유번호 마스터(118,709, 상장 3,983/비상장 114,726) + 정규화명 `corp_name_norm` | 외부 DART `corpCode` + KIND 상장법인목록 | `build_company_relations.py` |
| `data/enriched/holding_code_map.csv` | 편입종목 ticker6 1,393종 식별자 해소: 정확매칭 1,211 / 모ETF 72(`etf_isin`) / 우선주→보통주 20(`common_ticker`) / 미해소 90(대부분 회사채 코드 — 오매칭 위험으로 공란 유지). `match_rule`로 판정 근거 기록 | 내부 파생 (`etf_holding.csv` + `company_master.csv` + 주최측 `PREF01N001`) | `build_holding_code_map.py` |
| `data/relations/company_subsidiary.csv` | 기업↔자회사 지분율 (29,524행, 모회사 2,266사) 롱포맷. 자회사는 법인명 문자열이라 `child_corp_code`로 마스터에 되붙임(**행 기준 30.33%** = 8,955/29,524, 판정 근거는 `child_match_rule`: unique_name 7,780 / clean_unique_name 868 / unique_listed 275 / clean_unique_listed 32). 고유 자회사명 기준으로는 **26.48%**(6,572/24,818)다 — **두 수치는 분모가 다를 뿐 둘 다 맞다. 인용할 때 기준을 함께 적는다**. 비상장 동명이인·사명변경은 미매칭 유지. `as_of`는 공시 접수일(`rcept_no`), 2026-07-11 초과분 제외 | 외부 DART `otrCprInvstmntSttus`(타법인출자현황) | `collect_dart.py` → `build_company_relations.py` |
| `ontology/instances_*.ttl` | 위 관계·마스터 테이블의 TTL 인스턴스 5파일(1,392,793트리플, 약 64MB). fp:Holding·fp:SubsidiaryRelation n-ary, 결정적 출력. **gitignore 대상**(재생성 가능·주최측 데이터 파생) | 내부 파생 (위 `data/relations/`·`data/enriched/` 전체) | `build_ontology_instances.py` (검증 `validate_ontology.py`) |
| `docs/docs_data_layer/DATA_INVENTORY.md` | 위 전체의 행수·컬럼·결측률 스냅샷 (문서, 자동 생성) | 내부 파생 (위 전체) | `build_data_inventory.py` |

채권 보강 테이블은 전 컬럼이 원본 파생이라 컬럼별 `*_source` 대신 테이블 전체에 `source` = `derived:PRBD01N001` 한 컬럼을 둔다.

## 변경 추적

데이터 구조 변경 이력은 수기 changelog 대신 `docs/docs_data_layer/DATA_INVENTORY.md`의 `git diff`로 관리한다.

1. 원본 교체·파생 테이블 추가·컬럼 변경이 생기면 `python3 script/build_data_inventory.py`를 재실행한다.
2. 갱신된 `DATA_INVENTORY.md`를 함께 커밋한다. `git diff`가 곧 "어느 파일의 어느 컬럼이 언제 바뀌었나"의 답이 된다.
3. 문서는 직접 편집하지 않는다. 출력은 결정적이어야 하므로 생성 시각 같은 매 실행마다 바뀌는 값을 넣지 않는다(diff 노이즈 방지).

## 다음 후보 (미생성)

- `data/relations/product_index.csv`: 상품↔기초지수/벤치마크 — 지수 별칭 매핑 후
