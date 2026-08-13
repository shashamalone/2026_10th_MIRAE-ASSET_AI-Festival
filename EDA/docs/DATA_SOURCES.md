# 데이터 소스 목록

이 과제에서 사용·검토한 모든 데이터 출처를 한곳에 모은다. 어디서 왔고, 왜 쓰며, 무엇이 들어 있고, 그 출처에서 무엇까지 얻을 수 있는지를 기록한다.

**공통 제약** — 주최측 2026-07-11 스냅샷이 절대 기준이며, 외부 데이터는 `as_of ≤ 2026-07-11`만 허용한다. 상시 크롤링 파이프라인은 금지이고 1회 정적 취득만 한다. 상충 시 주최측 데이터가 우선한다. 상세는 `EXTERNAL_DATA_PLAN.md` 2절.

## 1. 한눈에 보기

| # | 소스 | 구분 | 상태 | 인증 |
|---|---|---|---|---|
| 1 | 주최측 금융상품 마스터 4종 | 원본 | 확보 | — |
| 2 | LSEG 정적 메타데이터 | 외부(기제공) | 확보 | — |
| 3 | 삼성자산운용 KODEX | 외부 수집 | **부분**(21/240) | 불필요 |
| 4 | 미래에셋 TIGER | 외부 수집 | 확보(229/235) | 불필요 |
| 5 | KB RISE | 외부 수집 | 확보(140/147) | 불필요 |
| 6 | 한국투자 ACE | 외부 수집 | 확보(105/114) | 불필요 |
| 7 | KRX KIND 상장법인목록 | 외부 수집 | 확보(2,795) | 불필요 |
| 8 | OpenDART | 외부 | **키 대기** | 필요 |
| 9 | 공정위 기업집단(공공데이터포털) | 외부 | 미착수 | 필요 |
| 10 | SEC EDGAR N-PORT | 외부 | 미착수 | 불필요 |
| 11 | KRX 정보데이터시스템 | 외부 | **차단** | 로그인 |
| 12 | KRX 오픈API | 외부 | **부적합** | 키 보유 |

---

## 2. 주최측 제공 원본

평가의 기준 데이터. `data/csv/`에 CSV로 변환해 보관하며 **동결**한다(값 수정·컬럼 추가 금지).

| 테이블 | 도메인 | 규모 | 이 과제에서의 용도 |
|---|---|---|---|
| `PRBD01N001` | 국내채권 | 42,394행 × 40컬럼 | 채권 속성·조건 검색의 유일한 근거. 신용등급·만기·표면금리·발행사 |
| `PREF01N001` | 국내ETF/ETN | 1,734행 × 73컬럼 | ETF 속성·순자산·위험등급·연금거래. ETN 532종 혼입 주의 |
| `PREF02N001` | 해외ETF/ETN | 5,646행 × 49컬럼 | 해외 ETF 보수·AUM·복제방식. 외부 조인키(ISIN·CIK·Lipper ID) 공급 |
| `PRFD01N001` | 공모펀드 | 95,619행 × 45컬럼 | 펀드 속성·수익률·위험등급. **11,139펀드의 롱포맷**이라 dedup 필수 |

**구성**: 각 도메인마다 `_master_`(데이터), `_schema_`(컬럼 정의), `_axis_sample_`(주최측이 분류 라벨 `axis_*`를 붙인 100행 샘플) 3종. axis 샘플은 온톨로지 분류축 설계의 기준으로 썼다.

**얻을 수 없는 것**: 편입종목, 기업 지배구조, 서술형 위험요인, 뉴스·사건 이력. 이것이 외부 데이터가 필요한 이유 전부다.

---

## 3. 확보한 외부 데이터

### 3.1 LSEG 정적 메타데이터

- **원본**: `lseg_static_metadata.json` (프로젝트에 기제공, 1,099건)
- **용도**: 국내 ETF의 **총보수 결측 보완**과 **테마 축** 공급
- **구성**: 6자리 단축코드를 키로 `themes`(176종), `ter`(총보수), `replication`, `base_market`, `base_asset`, `hedge_type`
- **활용 결과**: `pd_itm_no_ma` 선두 1글자를 뗀 값과 키가 일치. ETF 1,202종 중 1,099종(91.4%) 매칭. 총보수 결측이 81.9% → 8.4%로 감소. 테마는 `data/relations/etf_theme.csv`로 관계 테이블화
- **한계**: 기초지수명이 없어 `cu_base_index` 95.2% 결측은 보완 불가. 수집 시점(`as_of`) 미확인이라 관계 테이블의 `as_of`를 공란으로 뒀다
- **주의**: 주최측 `cu_charge_rt`에 값이 있어도 다수가 `0.0` 더미다. 실값(>0)만 우선하고 나머지는 `ter`로 채운다

### 3.2 ETF 편입종목 — 운용사 4사

전부 **인증 불필요, robots.txt 허용, 과거 일자 조회 가능**. `as_of = 2026-07-10`(07-11은 토요일이라 전 사이트 데이터 없음).

**공통 용도**: 상 난이도 7문항이 요구하는 `ETF → 편입종목 → 기업` 경로의 출발점. 온톨로지 `fp:Holding` 인스턴스의 원천이다.

| 운용사 | 엔드포인트 | 응답 | 편입종목 식별자 |
|---|---|---|---|
| 삼성 KODEX | `www.samsungfund.com/api/v1/kodex/product-pdf/{fId}.do?gijunYMD=YYYY.MM.DD` | JSON | 6자리 티커 (엑셀엔 ISIN 병기) |
| 미래에셋 TIGER | `investments.miraeasset.com/tigeretf/ko/product/search/detail/pdfListAjax.ajax?ksdFund={ISIN}&fixDate=YYYY.MM.DD` | HTML `<tr>` | 6자리 티커 / 해외는 블룸버그 |
| KB RISE | `www.riseetf.co.kr/prod/document/pdf/listExcel?searchTargetId={ID}&searchDate=YYYY-MM-DD` | HTML 테이블(.xls) | **ISIN 12자리** |
| 한국투자 ACE | `papi.aceetf.co.kr/api/funds/{fundCd}/pdf?page=1&size=1000&std_dt=YYYYMMDD` | JSON | 6자리 / 블룸버그 / ISIN 혼재 |

**상품목록(내부 ID 매핑)**

| 운용사 | 목록 URL |
|---|---|
| KODEX | `www.samsungfund.com/api/v1/kodex/product.do?pageNo={n}&pageRows=20&srchTerm=w` |
| TIGER | 불필요 — `ksdFund`에 ISIN 직결 |
| RISE | `www.riseetf.co.kr/prod/document/pdf?searchDate=YYYY-MM-DD&page={n}` |
| ACE | `papi.aceetf.co.kr/api/funds?page=1&size=500` (`stockCd`=ISIN, `fundCd` 동시 수록) |

**얻을 수 있는 것**: 종목코드·종목명·수량·평가금액·비중. 과거 일자 소급(TIGER 2009~, KODEX·RISE 2020~, ACE 2022~).

**쓰면 안 되는 것**: KODEX `curp`·`risep`, TIGER 등락률은 **조회 일자와 무관하게 오늘 값**이 박힌다(대조 검증으로 확인). 미래정보 유출이라 관계 테이블에 넣지 않는다.

**현재 커버리지**: 495종 / 31,549행. 국내 ETF 1,202종 대비 41.2%, 순자산 기준 50.2%. KODEX는 Cloudflare 도메인 차단으로 219종 미수집(보류). 상세는 `HOLDINGS_COLLECTION_DESIGN.md`.

### 3.3 KRX KIND 상장법인목록

- **URL**: `https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13`
- **용도**: **기업 식별자 마스터.** 운용사마다 다른 편입종목 식별자를 기업 노드로 묶는 enabler
- **구성**: 회사명·시장구분·**종목코드**·업종·주요제품·상장일·결산월·대표자명·홈페이지·지역. 2,802행 → 상장일 ≤ 2026-07-11 필터로 **2,795행**
- **조인 실측**: 편입종목 티커 87.6%, 편입종목 ISIN 96.4%, **채권 발행사 13.0%**
- **한계**: 상장사만. 채권 발행사 8,018곳의 대부분이 비상장(한국주택금융공사·한국산업은행 등 공기업·여전사·SPC)이라 발행사 매칭이 낮다 → DART `corpCode` 필요

---

## 4. 인증 대기 중

### 4.1 OpenDART

- **URL**: `https://opendart.fss.or.kr/api/` · 키 발급 `https://opendart.fss.or.kr/uss/umt/EgovMberInsertView.do`
- **용도**: **기업 지배구조(자회사·지분율)** 와 **비상장 포함 기업 식별자**
- **필요한 API 2종**
  - `otrCprInvstmntSttus` (타법인 출자현황) — 법인명·기말 지분율·출자목적·최초취득일을 **정형 JSON**으로 제공. 사업보고서 본문 파싱이 불필요하다
  - `corpCode.xml` — 고유번호↔기업명↔종목코드, **비상장 포함 약 11만 건**
- **인증**: 이메일 가입 후 즉시 발급, 무료, 일 20,000건. `.env`에 `dart=` 추가 필요
- **시점**: `bsns_year=2025 & reprt_code=11011`(사업보고서)로 조회. 에코프로 FY2025 접수일 2026-03-18로 컷오프보다 4개월 빠르다. 2026 반기보고서(접수 ~8월)만 피하면 된다
- **막힌 경로**: DART 공시 원문 직접 크롤링은 robots.txt Disallow(`/dsaf001/main.do`, `/report/viewer.do` 등). 공식 API가 합법 대체로다

### 4.2 공정거래위원회 기업집단 (공공데이터포털)

- **URL**: `https://www.data.go.kr/data/15091891/openapi.do` (소속회사 조회) 외 2종
- **용도**: 대기업집단 **그룹 경계 확정**. "에코프로의 자회사" 같은 질의에서 DART 지분율과 교차 검증
- **구성**: 기업집단명·소속회사명·법인등록번호·대표자·설립일·계열편입일
- **인증**: data.go.kr 서비스키, 자동승인
- **시점**: 2026-05-01 지정 기준(102개 집단) — 컷오프 이내
- **막힌 경로**: 공정위 기업집단포털(`egroup.go.kr`) 직접 스크래핑은 robots.txt가 `/egps/ps/` 전체를 Disallow

---

## 5. 미착수

### 5.1 SEC EDGAR N-PORT — 해외 ETF 보유종목

- **URL**: `https://www.sec.gov/edgar/`
- **용도**: 해외 ETF 편입종목(3문항). "캠브리콘이 편입된 중국 반도체 ETF" 등
- **조인키**: `pd_us_cik`(유효 5,633행 / 고유 375종), `pd_isin_cd`
- **난관**: CIK 하나가 여러 ETF를 묶는 신탁 단위라 **시리즈 ID 매핑이 추가로 필요**하다. 분기 공시라 과거 시점 확보에는 오히려 유리
- **대안**: iShares·Vanguard·Invesco 등 운용사 holdings 아카이브. 상위 4~5개 운용사가 AUM 대부분을 차지

### 5.2 근거 문서 (투자설명서·운용보고서)

- **URL**: DART 펀드공시, 운용사 공시자료실, 금투협 전자공시(`dis.kofia.or.kr`)
- **용도**: **blocking 8문항으로 최다.** 관계 질의가 "문서명·발행기관·발행일·근거 문장"을 명시적으로 요구한다. 편입종목만 확보해도 이 8문항은 '부분'에 머문다
- **성격**: 정형 데이터가 아니라 Vector DB 검색 대상

---

## 6. 조사 후 배제

| 소스 | URL | 배제 사유 |
|---|---|---|
| KRX 정보데이터시스템 ETF PDF | `data.krx.co.kr` | 2026년부터 **무로그인 API 접근 차단**. 정상 브라우저 헤더·세션 쿠키를 갖춰도 `HTTP 400 "LOGOUT"` 반환. pykrx도 `KRX_ID`/`KRX_PW` 요구 |
| KRX 오픈API | `openapi.krx.co.kr` / `data-dbg.krx.co.kr/svc/apis/` | **구성종목 엔드포인트가 존재하지 않는다.** 증권상품 카테고리는 ETF/ETN/ELW 일별매매정보 3종뿐(후보 경로 18개 전부 404, 실존 서비스는 401로 구분됨). 보유한 키는 유효하나 서비스별 활용신청·승인이 별도로 필요하며, 승인받아도 시세 정보만 얻는다 |

두 경로 모두 **우회를 시도하지 않았다.** 로그인 우회나 robots.txt 위반은 대회 규칙과 서비스 약관 양쪽에 어긋난다.

---

## 7. 보관 규칙

```
data/csv/       주최측 원본 변환본 (동결)
data/external/  외부 수집 원천 + 사이드카 {원본파일명}.meta.json
data/enriched/  스칼라 보강·재그레인 파생 테이블
data/relations/ 롱포맷 관계 테이블 (주어ID, 목적어, source, as_of)
```

모든 외부 원천에 `{source, as_of, retrieved_at, url}` 사이드카를 붙이고, `python3 EDA/validate_external.py`가 기준일 초과·필수 키 누락·인증키 노출을 검사한다(실패 시 exit 1). 계층·파일명 규칙은 `DATA_LAYER_PLAN.md`가 단일 기준이다.

`data/`는 gitignore 대상이므로 **저장소에는 스크립트만 남는다.** 클론 후 스크립트를 실행해 재생성하는 구조다.
