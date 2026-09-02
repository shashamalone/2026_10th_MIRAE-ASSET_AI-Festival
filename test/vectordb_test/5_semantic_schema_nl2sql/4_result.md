# 4. Semantic Schema Context 기반 NL2SQL·Routing 실험 결과

## 요약

- 실행 기간: **2026-08-23~2026-08-24**
- 데이터 cutoff: `2026-07-11`
- 모델: HyperCLOVA X `HCX-007`
- 통제값: temperature `0.1`, seed `0`, top_p `0.8`, 최대 출력 `4096` tokens
- **NL2SQL 평가: 28문항 × 3조건 × 3회 = 252셀**
- **Routing 평가: 35문항 × 3조건 × 3회 = 315셀**
- 최종 결론: **A/B/C 어느 조건도 운영 Planner 채택 기준을 만족하지 못했다.**

C는 A보다 Table Accuracy를 `21.4%p` 높이고 Hallucinated Schema Rate를 `16.7%p` 낮췄다. 즉 명시적인 semantic binding과 business rule은 모델이 관련 테이블을 찾는 데는 도움을 줬다. 그러나 SQL Executability는 C에서도 `22.6%`, Execution Accuracy는 세 조건 모두 `0%`였다. 테이블을 찾는 개선이 정확한 컬럼·필터·JOIN·최종 결과를 생성하는 개선으로 이어지지 않았다.

## 1. 실험 목적

이 실험은 Ontology Grounding 이후 Planner에게 어느 수준의 메타데이터를 제공해야 SQL과 multi-source 실행계획 오류가 줄어드는지를 검증한다.

비교 변수는 Planner에게 제공하는 metadata context뿐이다.


| 조건                   | 제공 정보                                                            | 의도                                             |
| -------------------- | ---------------------------------------------------------------- | ---------------------------------------------- |
| A — Physical Schema  | PostgreSQL table·column·datatype·PK/FK·nullable                  | 물리 스키마만으로 NL2SQL과 Routing이 가능한지 확인             |
| B — A + TBox         | A + 질문별 ontology concept의 label·description·domain·range         | 논리적 business meaning이 schema linking에 주는 효과 확인 |
| C — B + Binding/Rule | B + concept↔physical source binding·usage·filter/join/value rule | 명시적 실행 규칙을 제공했을 때의 추가 개선 확인                    |


B에는 concept와 physical column 사이의 명시적인 binding을 넣지 않았다. C에는 binding을 넣었지만 SQL template이나 허용 경로를 강제하지 않았으므로, 최종 table·column·JOIN 선택은 여전히 Planner가 수행했다.

## 2. 데이터와 실행 환경

### 2.1 PostgreSQL 적재 범위

원천·파생·관계 데이터 12개 테이블을 명시적 타입과 PK/FK로 PostgreSQL에 적재했다.


| 계층        | 테이블                  | 적재 행    |
| --------- | -------------------- | -------: |
| raw       | `bond_kr_master`     | 42,394  |
| raw       | `etf_kr_master`      | 1,733   |
| raw       | `etf_gl_master`      | 5,646   |
| raw       | `fund_pub_master`    | 95,618  |
| enriched  | `bond_kr_enriched`   | 42,394  |
| enriched  | `etf_kr_enriched`    | 1,733   |
| enriched  | `fund_pub_dedup`     | 11,138  |
| enriched  | `company_master`     | 118,709 |
| enriched  | `holding_code_map`   | 1,393   |
| relations | `etf_theme`          | 5,646   |
| relations | `etf_holding`        | 47,016  |
| relations | `company_subsidiary` | 29,524  |


다음 데이터 정합성 규칙을 적용했다.

- 깨진 국내 ETF 식별자 `pd_itm_no='KR'` 1행 제외
- 깨진 공모펀드 식별자 `itm_no='"'` 1행 제외
- 펀드 집계에는 `fund_pub_dedup` 사용
- 국내 ETF는 `pd_grp_no='ETF'`로 ETN 제외
- 관계 데이터에서 `as_of > 2026-07-11` 0행 확인
- `data/csv/`는 읽기 전용으로 유지
- PostgreSQL PK/FK 제약 20개 검증

### 2.2 질문과 반복 단위

NL2SQL은 Gold plan에 RDB step이 있는 28문항을 대상으로 했다. Routing은 예상 평가질의 35문항 전체를 대상으로 했다.


| 실험      | 문항  | 조건  | 반복  | 최종 셀 | 조건별 n |
| ------- | ---: | ---: | ---: | ----: | -----: |
| NL2SQL  | 28  | 3   | 3   | 252  | 84    |
| Routing | 35  | 3   | 3   | 315  | 105   |


1차 실행에서 오류가 있거나 A/B/C의 primary 결과가 다른 문항만 2·3차 반복 대상으로 삼았다. 실제로 NL2SQL 28문항과 Routing 35문항 모두 반복 조건에 해당해 전체가 3회 실행됐다.

NL2SQL Gold의 구조는 다음과 같다.


| Gold 특성                    | 문항/항목 수 |
| -------------------------- | -------: |
| 단일 테이블 문항                  | 13      |
| 2개 테이블 문항                  | 9       |
| 3개 테이블 문항                  | 4       |
| 4개 테이블 문항                  | 2       |
| 명시적 required filter가 있는 문항 | 7       |
| required filter 항목         | 12      |
| 결과 순서에 민감한 문항              | 19      |


### 2.3 통제 조건

A/B/C 간 다음 항목은 동일하게 유지했다.

- HyperCLOVA X 모델과 생성 파라미터
- system prompt와 user question
- Planner JSON schema
- PostgreSQL 데이터 snapshot
- TBox·ABox TTL snapshot
- Gold question과 평가 코드
- SQL 실행 timeout과 결과 행 제한

조건별 실행 순서는 문항·반복 번호에 따라 순환시켜 특정 조건이 항상 먼저 호출되는 순서 효과를 줄였다.

### 2.4 재시도와 실패 보존 원칙

- API quota로 실패한 NL2SQL 78셀은 같은 입력으로 재호출하고 모델 오류에서 제외했다.
- 일시적 DNS 장애로 실패한 Routing 11셀도 같은 입력으로 재호출하고 모델 오류에서 제외했다.
- Routing의 모델 JSON 파싱 실패 8셀은 실제 Planner 출력 실패이므로 결과에 보존했다.
- 최종 raw 결과에는 재시도 가능한 인프라 오류가 남아 있지 않다.

Gold, A/B/C context, CSV·TTL snapshot은 SHA-256으로 기록했다. Routing 실행 중 Gold 파일 해시는 `ab13…`에서 `d19b…`로 변경됐지만 다음을 검증했다.

- 35개 질문 문구 동일
- 원본 예상질의 SHA 동일
- A/B/C context SHA 동일
- 모델 prompt에는 Gold execution plan이 포함되지 않음

변경 이력은 `results/routing_raw.json`의 `meta.gold_hash_migration`에 기록했다.

## 3. 평가 단위와 공통 집계 방식

평가의 최소 단위인 `cell`은 다음 조합 하나다.

```text
question_id × condition(A/B/C) × run(1/2/3)
```

조건별 최종 지표는 각 cell 점수의 산술평균이다.

```text
조건별 지표 = 조건에 속한 모든 cell 점수의 합 / 조건별 cell 수
```

NL2SQL에서 Table Accuracy·Join Accuracy·SQL Executability·Execution Accuracy·Hallucinated Schema는 cell별 `0 또는 1`이다. Required Column Recall과 Filter Semantic Accuracy는 cell 안에서도 부분점수 `0~1`을 가질 수 있다.

Routing에서 Engine Selection·Dependency·Parallelization Accuracy는 cell별 `0 또는 1`이다. Unnecessary Engine Call Rate는 cell별 불필요 step 비율을 계산한 뒤 조건별 평균을 낸다.

## 4. NL2SQL 평가 기준

### 4.1 평가 전 SQL 유효성 계약

Planner 출력에서 다음 조건을 모두 만족해야 평가 가능한 SQL로 인정한다.

1. `execution_plan` 안에 `engine='rdb'` step이 정확히 1개여야 한다.
2. 해당 step의 `query`가 문자열이어야 한다.
3. SQL은 `SELECT` 또는 `WITH ... SELECT`로 시작해야 한다.
4. 문자열·주석 밖에 복수 statement를 만드는 세미콜론이 없어야 한다.
5. PostgreSQL 읽기 전용 transaction에서 실행돼야 한다.
6. statement timeout `5초` 안에 끝나야 한다.
7. 결과가 `10,000행` 이하여야 한다.

이 계약을 만족하지 못한 cell은 SQL 구조 지표가 기본값 0으로 남고, E12 범주에 포함된다.

### 4.2 Table Accuracy

**측정 질문:** **Planner가 Gold SQL에 필요한 물리 테이블 집합을 정확히 선택했는가?**

**계산식:**

```text
Table Accuracy(cell) = 1, 사용 테이블 집합 == Gold required_tables
                       0, 그 외
```

**통과 기준:** 필요한 테이블을 모두 포함하면서 불필요한 테이블을 하나도 추가하지 않아야 한다.

**지표 의미:** 자연어 질문을 올바른 데이터 domain과 physical table로 연결하는 schema linking 능력을 측정한다.

**해석상 주의:**

- exact-set 지표이므로 필요한 테이블을 모두 사용해도 불필요한 테이블 하나를 추가하면 0이다.
- catalog에 존재하지 않는 hallucinated table은 식별자 집합 비교뿐 아니라 실제 PostgreSQL 실행 오류로도 검출한다.
- 올바른 테이블을 선택했다는 사실만으로 컬럼·필터·JOIN이 맞다는 뜻은 아니다.

### 4.3 Required Column Recall

**측정 질문:** **답변 생성과 필터·정렬·JOIN에 필요한 Gold 필수 컬럼을 얼마나 사용했는가?**

**계산식:**

```text
Required Column Recall(cell)
  = |생성 SQL에서 발견된 catalog 컬럼 ∩ Gold 필수 컬럼|
    / |Gold 필수 컬럼|
```

**통과 기준:** `1.0`이면 Gold 필수 컬럼을 모두 사용한 것이다.

**지표 의미:** 테이블을 선택한 뒤 질문의 projection·조건·정렬·관계 연결에 필요한 속성을 빠짐없이 가져오는 능력을 측정한다.

**해석상 주의:**

- Recall이므로 불필요한 추가 컬럼은 직접 감점하지 않는다.
- SELECT뿐 아니라 WHERE·JOIN·ORDER BY 등 SQL 전체에서 언급된 catalog 컬럼을 센다.
- SQL 주석과 문자열 literal은 식별자 탐지 전에 masking한다.
- 동일 이름 컬럼이 여러 테이블에 존재해도 현재 평가는 비한정 column name 집합 기준이므로 table-qualified column 정확도를 완전히 구분하지 못한다.

### 4.4 Filter Semantic Accuracy

**측정 질문:** **Gold에 정의된 필터의 컬럼·연산자·값을 같은 의미로 생성했는가?**

**계산식:**

```text
Filter Semantic Accuracy(cell)
  = SQL에서 발견된 required filter 수 / Gold required filter 수
```

각 required filter는 `column operator value` 패턴으로 검사한다. 예를 들어 `AA- 이상`은 다음처럼 정규화된 rule로 평가한다.

```sql
crd_grd_rank <= 4
```

**통과 기준:** 정의된 required filter 패턴을 모두 포함하면 `1.0`이다. Gold에 별도 required filter가 없는 문항은 평가 가능한 SQL이 있을 때 `1.0`을 부여한다.

**지표 의미:** 단순 컬럼 선택을 넘어 범위 방향, 임계값, 상태 조건 같은 business filter를 SQL로 옮기는 능력을 측정한다.

**해석상 주의:**

- 정규식 기반이므로 논리적으로 동등하지만 표현이 다른 SQL을 놓칠 수 있다.
- 반대로 패턴이 존재해도 전체 WHERE 논리가 정확하다는 보장은 없다.
- required filter가 명시된 문항은 28개 중 7개, filter 항목은 총 12개다. 따라서 전체 평균은 filter가 없는 21문항과 SQL 생성 실패의 영향도 함께 받는다.
- 따라서 이 지표만으로 business rule 적용 성공을 확정하지 않고 Execution Accuracy와 함께 본다.

### 4.5 Join Accuracy

**측정 질문:** **Gold required table 수에 필요한 최소 JOIN 개수를 생성했는가?**

**계산식:**

```text
Gold 최소 JOIN 수 = max(0, required table 수 - 1)

Join Accuracy(cell) = 1, 생성 SQL JOIN 수 >= Gold 최소 JOIN 수
                      0, 그 외
```

**지표 의미:** 복수 테이블 문항에서 관계 연결 구조를 만들었는지 확인하는 최소 구조 지표다.

**해석상 주의:**

- 현재 구현은 JOIN의 개수만 평가한다.
- JOIN key, 방향, cardinality, INNER/LEFT 선택은 직접 판정하지 않는다.
- 잘못된 key로 JOIN해도 개수 조건만 만족하면 1이 될 수 있다.
- 따라서 이름과 달리 완전한 join correctness가 아니며, Execution Accuracy로 보완해야 한다.

### 4.6 SQL Executability

**측정 질문:** **생성된 SQL이 실제 PostgreSQL에서 안전하게 오류 없이 실행되는가?**

**계산식:**

```text
SQL Executability(cell) = 1, 읽기 전용 PostgreSQL 실행 성공
                          0, Planner 계약 또는 DB 실행 실패
```

**성공 조건:**

- RDB step 1개
- 안전한 단일 SELECT/WITH
- PostgreSQL 문법·table·column·type 유효
- 5초 이내 완료
- 결과 10,000행 이하

**지표 의미:** 생성 문자열이 실제 실행 가능한 query인지 보는 end-to-end 전 단계 지표다.

**해석상 주의:** 실행 가능하다는 것은 정답이라는 뜻이 아니다. 잘못된 필터나 JOIN도 문법과 schema가 유효하면 실행될 수 있다.

### 4.7 Execution Accuracy

**측정 질문:** **생성 SQL의 실제 결과가 Gold SQL의 결과와 동일한가?**

**판정 절차:**

1. 같은 PostgreSQL snapshot에서 Gold SQL과 생성 SQL을 각각 실행한다.
2. 결과 column name을 소문자로 정규화한다.
3. Decimal·float·date/time·bytes 값을 결정적으로 정규화한다.
4. 생성 결과와 Gold 결과의 column 집합이 같은지 확인한다.
5. 순서 민감 문항은 row sequence를 그대로 비교한다.
6. 순서 비민감 문항은 중복을 보존한 row multiset으로 비교한다.

**계산식:**

```text
Execution Accuracy(cell) = 1, 결과 column 집합과 전체 row 결과가 Gold와 동일
                           0, 그 외
```

**지표 의미:** table·column·filter·join·sort·limit이 결합된 최종 의미 정확도를 측정하는 핵심 지표다.

**해석상 주의:**

- 결과가 의미상 유사해도 추가 evidence column이나 누락 column이 있으면 0이다.
- order-sensitive 문항은 동일 row라도 순서가 다르면 0이다.
- exact-match 기준이 엄격하지만, 최종 답변에 필요한 데이터 계약을 충족하는지 가장 직접적으로 보여준다.

### 4.8 Hallucinated Schema Rate

**측정 질문:** 생성 SQL이 PostgreSQL catalog에 없는 table 또는 column을 사용했는가?

**계산식:**

```text
Hallucinated Schema(cell) = 1,
  PostgreSQL SQLSTATE가 undefined_table(42P01) 또는 undefined_column(42703)

Hallucinated Schema Rate
  = hallucinated cell 수 / 조건별 전체 cell 수
```

**지표 의미:** Planner가 제공된 physical schema를 벗어나 존재하지 않는 식별자를 만들어내는 비율이다. 이 지표만 낮을수록 좋다.

**해석상 주의:**

- SQL이 생성되지 않았거나 Planner JSON 구조가 잘못된 경우는 E12로 분류되며 hallucination에는 포함되지 않는다.
- PostgreSQL이 실제로 undefined table/column으로 판정한 실행만 센다.
- 따라서 raw 응답에 존재하는 모든 잠재적 허구 표현을 세는 지표는 아니다.

## 5. NL2SQL 결과

단위는 %, 각 조건 `n=84`다. Hallucinated Schema Rate는 낮을수록 좋고 나머지는 높을수록 좋다.


| 지표                       | A Physical Schema | B A+TBox | C B+Binding/Rule |
| ------------------------ | -----------------: | --------: | ----------------: |
| Table Accuracy           | 19.0              | 26.2     | **40.5**         |
| Required Column Recall   | **36.8**          | 32.0     | 36.6             |
| Filter Semantic Accuracy | **75.0**          | 68.5     | 66.1             |
| Join Accuracy            | **60.7**          | 57.1     | 57.1             |
| SQL Executability        | 19.0              | **23.8** | 22.6             |
| Execution Accuracy       | 0.0               | 0.0      | 0.0              |
| Hallucinated Schema Rate | 59.5              | 48.8     | **42.9**         |


0/1 지표는 다음 cell 수로 환산할 수 있다.


| 지표                        | A         | B         | C         |
| ------------------------- | ---------: | ---------: | ---------: |
| **Table exact match**     | 16/84     | 22/84     | **34/84** |
| 최소 JOIN 수 충족              | **51/84** | 48/84     | 48/84     |
| PostgreSQL 실행 성공          | 16/84     | **20/84** | 19/84     |
| **Gold 결과 exact match**   | 0/84      | 0/84      | 0/84      |
| Undefined table/column 오류 | 50/84     | 41/84     | **36/84** |


### 5.1 Table Accuracy 해석

C는 A보다 `21.4%p` 높았다. 명시적 binding과 business context가 어떤 물리 테이블을 봐야 하는지 결정하는 데는 효과가 있었다.

그러나 C에서도 exact table set을 맞힌 것은 84셀 중 34셀뿐이다. Table Accuracy 개선만으로 운영 가능한 schema linking이라고 보기는 어렵다.

### 5.2 Required Column Recall 해석

A `36.8%`, C `36.6%`로 사실상 개선이 없었다. C의 binding이 테이블 후보는 좁혔지만 답변·필터·정렬·JOIN에 필요한 전체 컬럼 계약을 완성하지 못했다.

B가 `32.0%`로 가장 낮아, TBox description만 제공하고 명시적 binding을 주지 않는 방식은 column linking에 직접적인 도움을 주지 못했다.

### 5.3 Filter Semantic Accuracy 해석

A `75.0%`가 가장 높고 C는 `66.1%`였다. business rule을 추가했는데도 aggregate filter 점수가 개선되지 않았다.

다만 이 수치는 정규식 기반 required filter 탐지, filter가 없는 문항, SQL 생성 실패가 함께 반영된 평균이다. 따라서 “A가 business filter를 더 정확히 이해했다”라고 단독 해석하기보다는 C의 rule이 실행 SQL까지 안정적으로 전달되지 않았다는 신호로 해석한다.

### 5.4 Join Accuracy 해석

A `60.7%`, B/C `57.1%`로 C의 개선이 없었다. 현재 지표는 JOIN 개수만 보므로 실제 key 정확도보다 관대하다. 이 관대한 조건에서도 C가 개선되지 않았다는 점은 binding만으로 관계 경로 생성이 안정화되지 않았음을 의미한다.

### 5.5 SQL Executability 해석

B가 `23.8%`로 가장 높았지만 A보다 `4.8%p` 높은 수준에 그쳤다. C는 `22.6%`로 B보다 `1.2%p` 낮다. 명시적 binding과 rule이 실제 PostgreSQL 문법·schema·type을 만족하는 SQL 생성으로 연결되지 않았다.

### 5.6 Execution Accuracy 해석

세 조건 모두 `0%`다. PostgreSQL에서 실행에 성공한 A 16셀, B 20셀, C 19셀도 결과 column과 row가 Gold와 일치하지 않았다.

이는 이번 실험의 결정적인 실패 지표다. 실행 가능한 SQL 일부가 생성됐다는 사실과 관계없이 최종 질문에 필요한 정확한 결과를 반환한 SQL은 없었다.

### 5.7 Hallucinated Schema Rate 해석

A `59.5%`에서 B `48.8%`, C `42.9%`로 단계적으로 감소했다. C는 A보다 `16.7%p` 낮아 semantic context가 schema hallucination 억제에는 효과가 있었다.

하지만 목표는 `0%`이며, C에서도 84셀 중 36셀이 존재하지 않는 table 또는 column 때문에 실패했다. 상대적 개선은 확인됐지만 절대 수준은 운영 적용이 불가능하다.

### 5.8 응답 지연시간


| 조건  | NL2SQL latency p50 |
| --- | ------------------: |
| A   | 4.70초              |
| B   | **4.54초**          |
| C   | 4.90초              |


C context가 더 크지만 p50 차이는 0.4초 이내였다. 이번 실패의 주원인은 latency가 아니라 SQL 정확도다.

## 6. NL2SQL 오류 분포

한 cell에 여러 구조 오류가 함께 존재할 수 있으므로 오류 건수의 합은 전체 cell 수보다 클 수 있다. 단, SQL 실행 불가 cell은 E12를 기록하고 이후의 구조 오류 분류를 중단한다.


| 오류                             | 판정 기준                                      | A   | B   | C   |
| ------------------------------ | ------------------------------------------ | ---: | ---: | ---: |
| E1 Wrong Table                 | 실행 가능한 SQL의 table 집합이 Gold와 다름             | 7   | 6   | 7   |
| E3 Missing Column              | 실행 가능한 SQL의 Required Column Recall이 1 미만   | 16  | 20  | 19  |
| E4 Wrong Filter Operator       | 실행 가능한 SQL의 Filter Semantic Accuracy가 1 미만 | 3   | 2   | 2   |
| E6 Wrong Join                  | 실행 가능한 SQL의 최소 JOIN 개수가 부족                 | 4   | 2   | 0   |
| E7 Hallucinated Schema         | DB가 undefined table/column SQLSTATE 반환     | 50  | 41  | 36  |
| E12 SQL Syntax/Execution Error | Planner 계약 위반 또는 PostgreSQL 실행 실패          | 68  | 64  | 65  |


오류 분류의 제한은 다음과 같다.

- E2 Wrong Column은 “필수 컬럼 누락”과 “불필요하지만 유효한 컬럼 추가”를 결정적으로 분리하지 않아 독립 집계하지 않았다.
- E5 Wrong Business Rule은 E4 및 Execution Accuracy와 중복 없이 자동 판정할 기준이 없어 독립 집계하지 않았다.
- E12 이름은 SQL Syntax Error지만 실제 구현상 RDB step 수 위반, unsafe SQL, timeout, 10,000행 초과 및 기타 실행 오류를 포함한다.
- E13은 table·column·filter·join 구조 지표가 모두 맞고 실행 결과만 다른 경우로 제한했으며 해당 cell은 0건이다.
- E6가 C에서 0건인 것은 실행 가능한 cell 가운데 최소 JOIN 수 부족이 없었다는 뜻이다. 전체 Join Accuracy가 높다는 뜻은 아니다.

## 7. Multi-source Routing 평가 기준

Routing Gold와 Planner plan은 `graph`, `rdb`, `vector` step 및 `depends_on`으로 구성된다.

예시는 다음과 같다.

```text
Graph ──→ RDB
  └────→ Vector
```

같은 engine 안에서 몇 step으로 분해할지는 Planner의 자유로 두고, 서로 다른 engine 사이의 선택과 의존성을 중심으로 평가했다.

### 7.1 Engine Selection Accuracy

**측정 질문:** 필요한 engine 집합을 빠짐없이, 불필요한 engine 없이 선택했는가?

**계산식:**

```text
Engine Selection Accuracy(cell) = 1, 실제 engine 집합 == Gold engine 집합
                                  0, 그 외
```

**지표 의미:** 질문을 관계 탐색(Graph), 수치·집계(RDB), 근거 문서 검색(Vector) 중 어느 source로 보내야 하는지 판단하는 능력을 측정한다.

**해석상 주의:** engine 호출 순서와 dependency는 보지 않고 집합만 비교한다. 필요한 engine 하나를 누락하거나 하나를 추가하면 0이다.

### 7.2 Dependency Accuracy

**측정 질문:** 서로 다른 engine 사이의 선후행 관계를 Gold와 동일하게 구성했는가?

**계산식:**

```text
Dependency Accuracy(cell) = 1, cross-engine dependency edge 집합 == Gold edge 집합
                            0, 그 외
```

예를 들어 Graph에서 식별자를 찾은 뒤 RDB가 그 결과를 사용해야 하면 `(graph, rdb)` edge가 필요하다.

**지표 의미:** 선행 결과가 필요한 step만 순차 실행하도록 계획하는 능력을 측정한다.

**해석상 주의:** 같은 engine 안의 내부 step 분해와 dependency는 평가에서 제외한다. step ID 자체가 아니라 engine 간 edge로 축약해 비교한다.

### 7.3 Parallelization Accuracy

**측정 질문:** 서로 의존하지 않는 engine step을 Gold와 동일하게 병렬 실행 가능 상태로 두었는가?

**계산 방식:**

1. `depends_on`의 transitive reachability를 계산한다.
2. 양방향으로 도달 관계가 없는 step pair를 병렬 가능 pair로 본다.
3. Planner와 Gold의 병렬 가능 engine-pair 집합을 exact match로 비교한다.

```text
Parallelization Accuracy(cell) = 1, 병렬 가능 pair 집합 == Gold pair 집합
                                 0, 그 외
```

**지표 의미:** 독립 작업을 불필요하게 직렬화하거나, 순서가 필요한 작업을 잘못 병렬화하는지를 측정한다.

**해석상 주의:** engine pair 집합으로 축약하므로 동일 engine의 여러 step을 세밀하게 평가하지 않는다.

### 7.4 Unnecessary Engine Call Rate

**측정 질문:** Gold에 필요하지 않은 engine step을 얼마나 추가했는가?

**계산식:**

```text
Unnecessary Engine Call Rate(cell)
  = Gold engine 집합 밖의 실제 step 수 / 실제 전체 step 수
```

조건별 값은 cell별 rate의 평균이다.

**지표 의미:** 불필요한 source 호출로 인한 latency·비용·오류 전파 가능성을 측정한다. 낮을수록 좋다.

**해석상 주의:** Gold에 포함된 engine을 중복 호출하는 경우는 현재 구현에서 unnecessary로 세지 않는다. 오직 Gold engine 집합 밖의 engine step만 센다.

### 7.5 Query Type Accuracy — 보조 지표

Planner가 반환한 `query_type` 문자열이 Gold의 유형명과 exact match인지 평가한다.

```text
Query Type Accuracy(cell) = 1, actual query_type == Gold query_type
                            0, 그 외
```

A/B/C 모두 `0%`였다. 이 값은 primary Routing 4개 지표에는 포함하지 않았지만, Planner가 합의된 유형 label contract도 지키지 못했음을 보여준다.

## 8. Multi-source Routing 결과

단위는 %, 각 조건 `n=105`다. Unnecessary Engine Call Rate만 낮을수록 좋다.


| 지표                           | A        | B        | C        |
| ---------------------------- | --------: | --------: | --------: |
| Engine Selection Accuracy    | 13.3     | 12.4     | **24.8** |
| Dependency Accuracy          | **23.8** | 19.0     | 21.0     |
| Parallelization Accuracy     | 41.9     | **43.8** | 37.1     |
| Unnecessary Engine Call Rate | 38.7     | 39.1     | **34.7** |


exact-match 지표는 다음 cell 수에 해당한다.


| 지표                          | A          | B          | C          |
| --------------------------- | ----------: | ----------: | ----------: |
| Engine 집합 exact match       | 14/105     | 13/105     | **26/105** |
| Dependency edge exact match | **25/105** | 20/105     | 22/105     |
| Parallel pair exact match   | 44/105     | **46/105** | 39/105     |
| Query type exact match      | 0/105      | 0/105      | 0/105      |


### 8.1 Engine Selection 해석

C는 A보다 `11.4%p`, B보다 `12.4%p` 높았다. 명시적 source binding이 필요한 engine 후보를 찾는 데는 일부 도움이 됐다.

그러나 C에서도 Gold engine 집합을 맞힌 것은 105셀 중 26셀뿐이다. 운영 목표 `95%`와 큰 차이가 있다.

### 8.2 Dependency 해석

A `23.8%`가 가장 높고 C는 `21.0%`였다. C가 어떤 engine을 사용할지 찾는 데는 도움을 줬지만, 그 engine을 어떤 순서로 연결할지는 개선하지 못했다.

### 8.3 Parallelization 해석

B `43.8%`가 가장 높았지만 세 조건 모두 절반 미만이다. C는 `37.1%`로 가장 낮아, binding과 rule이 추가되면서 plan step이 늘거나 불필요한 dependency가 생겼을 가능성을 보여준다.

### 8.4 Unnecessary Engine Call 해석

C `34.7%`가 가장 낮지만 실제 cell 기준 E11 Unnecessary Engine은 57건이다. 상대적으로 가장 낫더라도 생성된 step 가운데 Gold에 없는 engine이 차지하는 cell별 비율의 평균이 약 3분의 1이라는 뜻이다.

### 8.5 Routing 응답 지연시간


| 조건  | Routing latency p50 |
| --- | -------------------: |
| A   | **4.72초**           |
| B   | 4.86초               |
| C   | 6.02초               |


C는 A보다 p50이 약 `1.30초` 길었다. 더 큰 metadata context와 복잡한 plan 출력이 latency 증가에 영향을 준 것으로 해석할 수 있으나, 본 실험은 context 크기 자체를 별도 분해 측정하지 않았으므로 인과로 확정하지 않는다.

## 9. Routing 오류 분포

한 cell에 여러 오류가 함께 집계될 수 있다.


| 오류                     | 판정 기준                                   | A   | B   | C   |
| ---------------------- | --------------------------------------- | ---: | ---: | ---: |
| E8 Wrong Engine        | 누락·추가로 설명되지 않는 engine 집합 불일치            | 0   | 0   | 0   |
| E9 Wrong Dependency    | dependency 또는 parallel pair가 Gold와 다름   | 92  | 99  | 97  |
| E10 Missing Engine     | Gold 필수 engine 누락 또는 Planner 구조/JSON 실패 | 36  | 35  | 29  |
| E11 Unnecessary Engine | Gold에 없는 engine step 추가                 | 66  | 67  | 57  |
| Planner JSON 파싱 실패     | JSON schema로 해석할 수 없는 모델 출력             | 5   | 1   | 2   |


E9는 dependency와 parallelization 중 하나라도 다르면 부여하므로 두 문제를 합친 상위 오류 범주다. JSON 파싱 실패 cell은 정상 execution plan이 없으므로 E10으로도 집계된다.

## 10. 성공 기준 판정


| 권장 기준                     | 목표   | C 실측  | 목표 대비 차이 | 판정  |
| ------------------------- | ----: | -----: | --------: | --- |
| SQL Executability         | ≥95% | 22.6% | -72.4%p  | 실패  |
| Execution Accuracy        | ≥90% | 0.0%  | -90.0%p  | 실패  |
| Required Column Recall    | ≥95% | 36.6% | -58.4%p  | 실패  |
| Hallucinated Schema       | 0%   | 42.9% | +42.9%p  | 실패  |
| Engine Selection Accuracy | ≥95% | 24.8% | -70.2%p  | 실패  |
| Dependency Accuracy       | ≥95% | 21.0% | -74.0%p  | 실패  |


C가 상대적으로 개선한 지표가 있더라도 모든 절대 기준에서 큰 폭으로 미달했다. 따라서 C를 곧바로 최종 architecture로 채택할 수 없다.

## 11. 실험 결과가 답하는 질문

### 11.1 RDB physical schema만 제공해도 충분한가?

아니다. A의 Table Accuracy는 `19.0%`, SQL Executability는 `19.0%`, Execution Accuracy는 `0%`, Hallucinated Schema Rate는 `59.5%`다.

### 11.2 TBox business meaning을 추가하면 어떤 오류가 줄어드는가?

A→B에서 Hallucinated Schema Rate는 `10.7%p` 감소했고 E6 Wrong Join은 4건에서 2건으로 줄었다. 하지만 Required Column Recall·Filter Semantic Accuracy·Join Accuracy는 하락했고 Execution Accuracy는 개선되지 않았다. TBox description만으로는 안정적인 physical binding을 만들 수 없다.

### 11.3 명시적 semantic binding과 business rule이 필요한가?

- 안전장치로 필요하지만 충분하지 않다. C는 Table Accuracy와 Hallucinated Schema Rate, Engine Selection Accuracy를 개선했다.

- 그러나 SQL Executability `22.6%`, Execution Accuracy `0%`이므로 binding을 hint로 제공하는 것만으로는 부족하다.

### 11.4 Planner가 physical schema 연결을 스스로 판단해도 되는가?

- 현재 방식으로는 안 된다.

- C에서도 undefined table/column 오류가 36/84셀 발생했고 필요한 engine 집합은 26/105셀만 맞혔다. verified binding과 deterministic schema validator가 필요하다.

### 11.5 RDB·Graph·Vector 계획을 정확한 순서로 만들 수 있는가?

- 현재 prompt/context 구조로는 어렵다.

- C의 Engine Selection Accuracy는 `24.8%`, Dependency Accuracy는 `21.0%`, Parallelization Accuracy는 `37.1%`다.

## 12. 주요 실패 요인

### 12.1 전체 physical schema가 계속 넓은 탐색 공간을 제공

- C도 질문에 허용된 table·column만 강제한 것이 아니라 full physical schema와 binding hint를 함께 제공했다.

- 모델은 여전히 관련 있어 보이는 다른 식별자를 선택할 수 있었다.

### 12.2 Binding이 실행 계약이 아니라 힌트

- Concept에 여러 physical source가 연결될 수 있지만 최종 경로 하나, JOIN key, 허용 filter expression을 강제하지 않았다.
- 그 결과 table 선택은 개선됐지만 column recall과 execution result는 개선되지 않았다.

### 12.3 Graph·RDB·Vector 역할 경계가 결정적이지 않음

- 일부 관계는 Graph predicate와 PostgreSQL relation table 양쪽에서 표현할 수 있다. 단순 자연어 routing 원칙만으로는 Gold engine과 dependency를 안정적으로 재현하기 어렵다.

### 12.4 생성 후 schema·plan 교정 단계 부재

Planner가 생성한 table·column·engine을 catalog whitelist와 대조해 수정하거나 재계획하는 단계가 없다. 한 번의 생성 결과가 곧바로 실행·평가되므로 hallucination과 누락이 그대로 최종 실패가 된다.

### 12.5 엄격한 결과 계약

Execution Accuracy는 결과 column과 전체 row의 exact match를 요구한다. 이는 엄격한 기준이지만 SQL Executability 자체가 C에서도 `22.6%`이므로 strict result comparison만으로 0%를 설명할 수는 없다.

## 13. 측정하지 않은 범위

이번 실험에서 다음은 측정하지 않았다.

- Graph store의 실제 구축과 SPARQL 실행 정확도
- Vector content 검색의 retrieval quality와 실행 정확도
- 최종 Answer 생성 품질과 evidence 문장 품질
- Planner reasoning trace
- JOIN key·direction·cardinality의 독립 정적 정확도
- 논리적으로 동등한 다양한 SQL 표현을 포괄하는 semantic parser 기반 평가
- E2 Wrong Column과 E5 Wrong Business Rule의 독립 자동 분류
- context token 수가 latency와 정확도에 미치는 인과 효과

따라서 Routing 지표는 **TTL snapshot을 기준으로 한 plan-only 평가이며 Graph·Vector 실행 성공률로 해석**하면 안 된다.

## 14. Architecture decision

Option A, B, C를 현재 형태 그대로 운영 Planner에 적용하지 않는다. 다음 단계에서는 C의 검증된 binding을 유지하되 LLM의 자유도를 결정적으로 제한해야 한다.

```text
Query Understanding
  → TBox grounding
  → 질문별 최소 verified binding 조회
  → 허용 table·column·join·engine whitelist
  → SQL/route template 또는 constrained compiler
  → schema·domain·cutoff validator
  → 실행
```

우선순위는 다음과 같다.

1. 질문별 full schema 대신 최소 verified binding만 제공
2. 허용 table·column·JOIN path를 whitelist로 제한
3. Routing을 자유 생성이 아닌 규칙 또는 constrained plan template으로 변환
4. 실행 전 schema·domain·cutoff validator 적용
5. JSON schema에 query type enum과 plan step 상한 추가
6. 같은 Gold와 snapshot으로 재실험

## 15. 재현 및 산출물

### 15.1 주요 실행 명령

```bash
python3 src/kb/build_rdb.py --check
python3 vectordb_test/4_semantic_schema_nl2sql/evaluate_sql.py --self-test
python3 vectordb_test/4_semantic_schema_nl2sql/evaluate_routing.py --self-test
python3 vectordb_test/4_semantic_schema_nl2sql/evaluate_sql.py
python3 vectordb_test/4_semantic_schema_nl2sql/evaluate_routing.py
```

### 15.2 결과 파일

- 원시 실행: [`results/nl2sql_raw.json`](results/nl2sql_raw.json), [`results/routing_raw.json`](results/routing_raw.json)
- 상세 지표: [`results/nl2sql_metrics.json`](results/nl2sql_metrics.json), [`results/routing_metrics.json`](results/routing_metrics.json)
- 오류 사례: [`results/error_cases.json`](results/error_cases.json)
- Gold: [`gold/gold_nl2sql.json`](gold/gold_nl2sql.json), [`gold/gold_routing.json`](gold/gold_routing.json)
- Context: [`contexts/schema_only.json`](contexts/schema_only.json), [`contexts/schema_tbox.json`](contexts/schema_tbox.json), [`contexts/schema_tbox_business.json`](contexts/schema_tbox_business.json)
- 평가 코드: [`evaluate_sql.py`](evaluate_sql.py), [`evaluate_routing.py`](evaluate_routing.py)

## 최종 결론

Semantic Schema Context C는 schema linking의 초기 단계에는 효과가 있었다. Table Accuracy가 A `19.0%`에서 C `40.5%`로 상승했고 Hallucinated Schema Rate는 `59.5%`에서 `42.9%`로 감소했다.

하지만 최종 목표는 “관련 테이블을 더 자주 찾는 것”이 아니라 “정확한 실행 결과를 만드는 것”이다. Required Column Recall과 filter·join 지표는 개선되지 않았고, SQL Executability는 `22.6%`, Execution Accuracy는 `0%`였다. Routing도 Engine Selection `24.8%`, Dependency `21.0%`로 운영 기준에 크게 미달했다.

따라서 다음 단계의 핵심은 더 많은 설명을 prompt에 추가하는 것이 아니라, 질문별 최소 binding·허용 경로·결정적 validator로 Planner의 선택 공간을 줄이는 것이다.
