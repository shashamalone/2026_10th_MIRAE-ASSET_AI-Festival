# T-101 공식 데이터 감사

- 감사일: 2026-08-26 (Asia/Seoul)
- 정본 release / 외부 근거 cutoff: 2026-08-24
- 정본 위치: `../data/ai-festival2026_금융상품Agent_DtataSet260824/`
- 감사 범위: 공식 XLSX 8개와 commit `7105519383833db80e6c6f163c240b4394414d19`에 보존된 2026-08-22 자산 8개
- 결론: **공식 파일 집합, SHA-256, 행·열, PK 계약은 PASS.** 보존 자산은 삭제하지 않되 현재 운영 정본으로 그대로 채택할 수 있는 것은 없으며, 7개는 `UPDATE`, 1개는 `REJECT`다.

## 1. 감사 방법과 불변성

공식 XLSX는 Python 3.13 표준 라이브러리의 `zipfile`, OOXML streaming parse, `hashlib.sha256`만으로 읽었다. 워크북을 저장하거나 공유 데이터에 산출물을 쓰지 않았다. 데이터 행 수는 헤더를 제외하고, 열 수는 공식 `data` 헤더를 기준으로 집계했다. 스키마 행 수 역시 헤더를 제외했다.

정본 디렉터리에는 아래 8개만 있었고 `__MACOSX/._*` 파일은 없었다. 모든 데이터 파일의 헤더는 대응 스키마의 컬럼 수와 맞았으며, 스키마 파일은 `schema` 1개 시트, 데이터 파일은 `data` 1개 시트 계약을 사용한다.

## 2. 파일 집합, SHA-256, shape 계약

| 파일 | 역할 | 계약 크기 | SHA-256 |
|---|---|---:|---|
| `prbd01n001_data.xlsx` | 국내채권 데이터 | 21,882 × 58 | `574ae5d6c1d98704712c256ed5352cbaed065ea9c3a6eb7b2a52adb305fa9001` |
| `prbd01n001_schema.xlsx` | 국내채권 스키마 | 58 × 5 | `9965126695066f9dc07951a78054e9e7639b6863d1ad2a9616f7e2d8fcadbc4f` |
| `pref01n001_data.xlsx` | 국내 ETF/ETN 데이터 | 1,780 × 98 | `18c4329d8fc8768d030316816f3e6e48226a3c217db3354245b766a2c6f6c592` |
| `pref01n001_schema.xlsx` | 국내 ETF/ETN 스키마 | 98 × 5 | `2135081fd8107760d127915147032987ee1d9e7c2ed039665ae4214b96faec5a` |
| `pref02n001_data.xlsx` | 해외 ETF/ETN 데이터 | 6,037 × 49 | `ca6a274aeaf3f884f2f7635d7802558bc6dabf408871ecb1f71e5a50d9d34067` |
| `pref02n001_schema.xlsx` | 해외 ETF/ETN 스키마 | 49 × 5 | `32ac732f0501f4ab518682175fecc50756ee1eafde9296801f139d62559b5e64` |
| `prfd01n001_data.xlsx` | 펀드 데이터 | 23,676 × 75 | `81b3ce3f1d5042b32fd52a76acff094fc5b8dd9fa36289af2fb54c195eb5d94c` |
| `prfd01n001_schema.xlsx` | 펀드 스키마 | 75 × 5 | `cfe7be44cbcd9ce349206776a4eb46996162643acbf3ca5a4f74c2886394862b` |

데이터 4종 합계는 **53,375행, 280열**이다. 기대 계약 `21,882×58`, `1,780×98`, `6,037×49`, `23,676×75`와 모두 일치한다.

## 3. grain, PK, 상품군 계약

| 소스 | 검증 PK | 유일 건수 / 행 수 | 판정 |
|---|---|---:|---|
| PRBD01N001 | `(pd_no, pd_exg_mkt, info_base_dt, info_seq)` | 21,882 / 21,882 | PASS |
| PREF01N001 | `pd_itm_no` | 1,780 / 1,780 | PASS |
| PREF02N001 | `pd_itm_no` | 6,037 / 6,037 | PASS |
| PRFD01N001 | `itm_no` | 23,676 / 23,676 | PASS |

펀드는 `itm_no`가 전체 23,676행에서 유일하다. 2026-07-11 legacy의 `(itm_no, prfd_attr_cd)` dedup을 적용하면 안 된다. 현재 정본에는 단수형 `prfd_attr_cd`가 없고 `prfd_attr_cds`가 있으며, 공모/사모 구분 정본 컬럼 `prvo_pbff_desc`는 **공모 14,716 / 사모 8,960**이다. 둘 다 raw에 보존하고 공개 상품 ABox를 만들 때만 공모를 선택한다.

ETF와 ETN은 파일명이나 상장지만으로 구분하지 않고 `pd_grp_no`를 사용해야 한다.

| 소스 | ETF | ETN | 합계 |
|---|---:|---:|---:|
| PREF01N001 국내 | 1,235 | 545 | 1,780 |
| PREF02N001 해외 | 5,972 | 65 | 6,037 |

## 4. 실제 기준일

release date를 개별 수치의 기준일로 대체하지 않는다.

| 소스 | 실측 기준일 축 | 해석 |
|---|---|---|
| PRBD01N001 | `info_base_dt`, `pd_std_info_update`, 유효 `sale_yield_base_dt` 모두 2026-08-21 | 채권 수치 evidence는 08-21 |
| PREF01N001 | `cu_upt_dt` 최대 08-24, `du_upt_dt`·`wu_upt_dt` 최대 08-21, `fn_base_dt`·`ref_base_dt` 08-22 | 분류/설명, 시장지표, 참조지표의 날짜축이 다름 |
| PREF02N001 | `cu_upt_dt`·`wu_upt_dt`·`du_nav_base_dt` 08-22, `du_upt_dt` 최대 08-22, `du_clpr_base_dt` 최대 08-21 | 해외 ETF/ETN은 대체로 08-22, 종가는 08-21 |
| PRFD01N001 | `fd_daily_bas_dt`·`fd_price_bas_dt` 최대 08-21 | 값별로 과거일/결측이 있으므로 행 단위 날짜를 반환 |

모든 관측 최대일은 cutoff 2026-08-24 이하다.

## 5. sentinel과 dummy/의미 함정

### 5.1 해외 ETF 기초지수 sentinel

PREF02N001 `cu_base_index`의 물리적 공백은 11행뿐이지만 다음 문장형 sentinel을 포함하면 실질 미제공은 **2,931 / 6,037 = 48.55%**다.

- `Index is not provided by Management Company`: 2,285행
- `Index is not available on Lipper Database`: 635행
- 공백: 11행

이 값들은 지수명이 아니므로 NULL/미제공 상태로 정규화하고 지수 개체를 만들지 않는다.

### 5.2 국내 ETF 총보수

PREF01N001의 ETF 1,235종 중 `cu_charge_rt`는 1,018종(82.43%)이 결측이다. 비결측 217종 중 150종(69.12%)은 `0`이다. `0`을 무료 상품의 확정값으로 간주하거나 보수 순위에 넣지 않는다. ETN 545종은 전부 결측이며 상품군 domain guard가 필요하다.

### 5.3 괴리율·추적오차의 release 차이

2026-07-11 문서의 “국내 전 종목 0.00” 가정은 **2026-08-24 정본에는 성립하지 않는다.** 현재 국내 데이터 실측은 다음과 같다.

| 컬럼 | ETF 비결측 / 0 | ETN 비결측 / 0 | 전체 0 |
|---|---:|---:|---:|
| `du_diff_rt` | 1,176 / 45 | 422 / 62 | 107 |
| `du_chas_errt` | 1,176 / 16 | 422 / 422 | 438 |

따라서 컬럼 전체를 폐기할 수는 없지만, `0`은 raw에 보존하되 측정값 비교·랭킹에서 값 없음으로 다뤄야 한다. 특히 ETN의 비결측 `du_chas_errt` 422건은 전부 0이므로 상품군별 가드가 필수다.

### 5.4 채권 등급과 의사결정용 파생값

- `std_pd_mcls_nm=국공채` 2,840행은 `crd_grd`가 100% 결측이다. 이는 `UnratedByDesign`이다.
- 특수채는 6,177행 중 254행(4.11%), 회사채는 12,865행 중 926행(7.20%)이 등급 결측이다. 이들은 `RatingUnknown`으로 구분한다.
- `remaining_days`는 비결측 21,877행 중 21,866행이 `mat_dt - info_base_dt`와 정확히 일치하지만 11행은 최대 54일 차이가 있다. 의사결정 시 재계산하고 raw는 근거로 보존한다.
- `buyable_quantity`는 NULL 21,248행, 0이 338행이다. 양수 존재만으로 판매 가능성을 판정하지 않는 저장 전용 컬럼이다.

## 6. 보존된 2026-08-22 자산 판정

여기서 `REJECT`는 파일 삭제가 아니라 **현재 운영/평가 정본으로 사용 금지**를 뜻한다. 8개 모두 보존 상태를 유지한다.

| 자산 | 판정 | 근거와 필요한 조치 |
|---|---|---|
| `docs_data_collection/EVIDENCE_DOCS_PLAN.md` | UPDATE | 문서 단독 해결 문항을 7→4로 바로잡은 점은 유효하다. 그러나 cutoff를 2026-07-11로 두고 국내 ETF 1,202종·외부 holdings 07-10을 전제로 하며 DART 키 부재라는 머신 상태도 문서에 고정했다. 08-24 cutoff와 1,235 ETF 기준으로 재검증한다. |
| `docs_data_layer/PROPERTY_STORAGE_MAP.csv` | UPDATE | 136개 property/고유성 및 storage 분포는 구조적으로 온전하다. 그러나 `documentPublishedDate`·`remainingDays`가 07-11을 기준으로 하고, `fundAttributeCode`는 현재 없는 단수형 `prfd_attr_cd`를 가리키며, legacy `data/csv` 파생 및 구 builder 상태가 섞여 있다. 현재 raw catalog와 v2 builder로 재생성한다. |
| `docs_data_layer/PROPERTY_STORAGE_MAP.md` | UPDATE | 136-property 설계 설명은 유용하지만 `build_ontology_instances.py`, 07-11 잔존일수 분석, 과거 배포 상태를 현재 사실처럼 서술한다. CSV 재생성 뒤 함께 갱신한다. |
| `docs_data_layer/ABSTAIN_RULES.csv` | UPDATE | rule 18개, ID 18개 고유, action은 ABSTAIN 8 / GUARD 9 / REWRITE 1이며 property 누락은 없다. 다만 stale storage map의 availability를 복사하므로 현재 runtime catalog와 T-102 ontology 결과에 다시 결합해야 한다. |
| `docs_data_layer/ABSTAIN_RULES.md` | UPDATE | ABSTAIN/도메인 가드 개념은 유지한다. 해외 ETF를 5,646종으로 적고 runtime 미배선 상태를 전제로 하므로 현재 5,972 ETF 및 v2 검증 계약에 맞춘다. |
| `docs_data_layer/QUERY_COVERAGE_OFFICIAL.md` | **REJECT** | 현재 운영 정본으로 사용 금지. 07-11 데이터와 국내 1,202/해외 5,646 ETF를 사용하고 응답시간을 60초로 적었으나 현재 회귀 계약은 15초 경계를 강제한다. “문서 축으로 7문항 해결” 주장도 후속 `EVIDENCE_DOCS_PLAN.md`가 4문항으로 정정했다. 필요 사실만 새 평가 문서로 이관한다. |
| `script/build_storage_map.py` | UPDATE | AST 문법은 PASS이고 5개 TBox를 읽는 골격은 재사용 가능하다. 그러나 실제 predicate 감지를 legacy `script/build_ontology_instances.py`에 의존하고 v2 graph/catalog 구현 및 현행 데이터 계약을 보지 않는다. 입력원을 v2 manifest/catalog로 교체한다. |
| `script/build_abstain_rules.py` | UPDATE | AST 문법과 결정론적 CSV 생성 골격은 유지한다. 입력이 stale property map이고 출력도 legacy `docs_data_layer` 계층이므로 T-102 ontology와 현행 runtime validation을 입력으로 받도록 갱신한다. |

구조 검사 결과 `PROPERTY_STORAGE_MAP.csv`는 136행/136개 고유 property이며 storage 분포는 RDB 83, graph 37, none 9, vector 7이다. `ABSTAIN_RULES.csv`는 18행/18개 고유 rule이고 참조 property 누락은 없다. 이는 보존 가치의 근거이지 현재 의미 계약의 정확성을 보장하지는 않는다.

## 7. 검증 결과와 환경 blocker

| 검증 | 결과 |
|---|---|
| 표준 라이브러리 OOXML read-only 검사: 파일 집합, SHA-256, shape, PK, 날짜축, 주요 sentinel | PASS |
| 보존 CSV 행/고유키/참조 무결성 | PASS (`136/136`, `18/18`, missing property 0) |
| `ast.parse` on `script/build_storage_map.py`, `script/build_abstain_rules.py` | PASS |
| `SourceContractTest` | 환경 blocker |

실행한 정확한 명령:

```powershell
py -3 -B -m unittest tests.test_v2_contracts.SourceContractTest
```

테스트 discovery 전에 `tests/test_v2_contracts.py:11`의 `import pandas as pd`에서 `ModuleNotFoundError: No module named 'pandas'`가 발생했다. 추가 probe에서 system Python에는 `openpyxl`도 없었다. 의존성을 설치하거나 lockfile을 변경하지 않았고, 동일 계약을 read-only OOXML 검사로 독립 확인했다.

## 8. 통합 권고

1. 위 8개 SHA-256을 2026-08-24 dataset manifest의 승인값으로 pin한다. manifest/current 포인터 변경은 integrator가 수행한다.
2. `QUERY_COVERAGE_OFFICIAL.md`는 historical 표식을 붙인 뒤 새 평가 정본에서 제외한다.
3. 나머지 7개는 T-102 ontology 및 v2 runtime catalog가 안정된 뒤 재생성/갱신한다. 이전 산출물을 덮어쓰거나 삭제하지 않는다.
4. 공식 XLSX 8개는 계속 읽기 전용으로 유지하고, 2026-07-11 legacy CSV를 운영 적재 입력으로 사용하지 않는다.
