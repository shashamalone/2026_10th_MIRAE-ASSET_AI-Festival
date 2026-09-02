# 130_v2 → 221 코드리스트 확장 영향 검증 보고서

## 0. Executive Summary

이번 실험은 기존 TBox 중심 검색사전 130건에 `rdfs:label`만 있고 `rdfs:comment`가 없는 코드리스트 91건을 추가해,  
**검색 범위를 넓히는 것이 실제 Ontology Grounding 품질에 어떤 영향을 주는지** 확인한 실험이다.

결론은 다음과 같다.

> **코드리스트 91건은 기존 TBox 용어의 의미 검색 자체를 망가뜨린 것이 아니라, 같은 Vector Search의 상위 슬롯을 점유하면서 설명 근거가 있는 TBox 용어를 밀어냈다.**

핵심 결과:

| 지표 | TBox 130_v2 | 221 혼합 | 변화 |
|---|---:|---:|---:|
| Strict Top-1 | 75.0% | 65.4% | -9.6%p |
| Lenient Top-1 | 85.0% | 70.0% | -15.0%p |
| Recall@3 | 96.7% | 90.0% | -6.7%p |
| Noise FP @0.45 | 25.0% | 50.0% | +25.0%p |
| Top-3 comment 근거 커버리지 | 100% | 76.4% | -23.6%p |
| Top-5 comment 근거 커버리지 | 100% | 68.6% | -31.4%p |

하지만 중요한 점은 **기존 130개 용어끼리의 Top-1 역전은 0건**이었다는 것이다.

즉 문제는:

```text
TBox 검색 품질 붕괴
```

가 아니라,

```text
TBox 개념
+
코드리스트 값
↓
동일 Vector Index에서 경쟁
↓
코드값이 상위 슬롯 점유
↓
comment 기반 근거 손실
```

이었다.

### 이번 실험이 확정한 아키텍처 의미

따라서 현재 Agent의 1~2단계는 다음 방향을 유지한다.

```text
① Query Understanding
        ↓
② TBox Ontology Grounding
   - comment가 풍부한 개념/속성 중심 Vector Search
   - 자연어 → fp: ontology concept
```

`AAA`, `AA-`, `장기`, `담보부`처럼 실제 조건값에 가까운 코드리스트는  
**TBox Vector Grounding의 검색사전에 그대로 섞지 않는다.**

다음 문제는 “코드리스트를 Vector DB에 더 넣을 것인가”가 아니라:

> **TBox에서 grounding된 논리 개념을 실제 RDB table.column, Graph predicate, Vector source와 어떻게 연결해 Planner에게 넘길 것인가**

이다.

따라서 다음 Action 3는 코드리스트 추가 실험이 아니라  
**Semantic Schema Context 기반 NL2SQL / Plan & Routing 실험**으로 전환한다.

---

# 1. 테스트 목적

기존 `src/kb/build_bond_index.py`는 `rdfs:comment`가 있는 subject만 검색사전에 포함했다.

그 결과:

```text
comment 보유 TBox 중심 용어     130건
label만 있는 코드리스트 값      91건
전체                            221건
```

구조였다.

이번 실험에서는 코드리스트 91건을 추가해 다음 질문 하나를 측정했다.

> **“91건이 같은 Vector Index에 들어왔을 때 기존 Ontology Grounding이 얼마나 흔들리는가?”**

여기서 사람 손으로 `rdfs:comment`를 추가하지 않았다.

이유는:

```text
코드리스트 추가 효과
```

와

```text
사람이 작성한 설명문 효과
```

를 분리하기 위해서다.

따라서 변경은 수집 조건 하나뿐이다.

```text
기존
comment 존재 → 인덱싱

변경
comment 존재 OR label 존재 → 인덱싱
```

---

# 2. 실험 설계

## 2.1 비교 구조

실험은 두 단계로 나눴다.

| 단계 | 비교 | 목적 |
|---|---|---|
| 1 | `130 → 130_v2` | 코퍼스는 그대로 두고 측정기의 결정성만 확보 |
| 2 | `130_v2 → 221` | 측정 조건을 고정한 뒤 코드리스트 91건의 순수 영향 측정 |

### 왜 130_v2가 필요한가

기존 keyword 검색은 동일 점수일 때 2차 정렬 키가 없었다.

따라서 테이블을 다시 만들기만 해도 동일 점수 항목의 순서가 달라질 수 있었다.

이를 제거하기 위해:

```sql
ORDER BY r DESC, term_uri
```

로 tie-breaker를 고정했다.

또한 noise / absent 후보 분포를 충분히 보기 위해 vector search의 측정용 `k`를 10 → 30으로 확대했다.

그 결과:

```text
벡터 계열 잡음 폭 = 0
RRF 잡음 폭       = ±1
```

로 확인됐다.

즉 이후 `130_v2 → 221`의 Vector 지표 변화는 측정기 흔들림이 아니라 실제 corpus 변화로 해석할 수 있다.

---

# 3. 검색 코퍼스 변화

## 3.1 130 vs 221

| 항목 | 130 | 221 |
|---|---:|---:|
| 전체 용어 | 130 | 221 |
| comment 보유 | 130 (100%) | 130 (58.8%) |
| comment 없음 | 0 | 91 |
| 기존 text 길이 중앙값 | 117.5자 | - |
| 신규 91건 text 길이 중앙값 | - | 27.0자 |
| 동일 label 그룹 | 16 | 23 |
| 동일 label pair | 16 | 25 |

신규 91건 중:

```text
altLabel 보유     37
altLabel 없음     54
```

이다.

대표적인 embedding text는 다음과 같다.

```text
fp:AssetType_Commodity | 원자재
fp:Rating_A            | A
fp:Rating_BB           | BB
fp:Maturity_LongTerm   | 장기 | 장기채권, 장기물
```

기존 TBox term은 comment가 포함된 긴 설명문인 반면, 신규 코드리스트 값은 대부분 짧다.

즉 동일 Vector Space 안에 서로 다른 두 text regime이 들어갔다.

```text
TBox term
= 개념 설명 중심

Code value
= 짧은 값 / label 중심
```

---

# 4. 테스트 질의

기존 130 baseline의 **72개 질의를 그대로 동결해서 사용**했다.

| 분류 | n | 목적 |
|---|---:|---|
| Exact | 12 | ontology label 그대로 입력 |
| Natural | 12 | 자연어·의문문 |
| Synonym | 10 | ontology label과 다른 표현 |
| Partial | 8 | 부분어 |
| Confuse | 18 | 유사·경쟁 용어 |
| Noise | 8 | 비금융 무관 질의 |
| Absent | 4 | 금융 개념이지만 현재 ontology에 없는 질의 |

질의셋 자체가 바뀌면 전후 비교가 무효가 되므로 다음 SHA를 동일하게 유지했다.

```text
resolved_queryset_sha = 98b2c6d3019c1031
```

---

# 5. 평가 지표

기존 지표:

- Strict Top-1
- Lenient Top-1
- Recall@3
- FTS Hit
- Hybrid(RRF) Top-1
- Noise False Positive @0.45

이번 실험에서는 두 가지를 추가했다.

## 5.1 Evidence Coverage

Top-3 / Top-5 결과 중:

```text
comment != ""
```

인 term의 수를 측정한다.

이 지표가 중요한 이유는 현재 답변 노드의 계약이:

```text
"RETRIEVED SCHEMA의 comment 안에 적힌 문장만 근거로 삼는다."
```

이기 때문이다.

즉 Top-1 URI가 맞아도 comment가 없는 term이 상위 슬롯을 채우면  
실제 답변 단계에 넘길 evidence는 줄어들 수 있다.

---

## 5.2 Measurement Noise

`130 → 130_v2` 차이를 측정기 자체의 noise baseline으로 사용한다.

```text
Vector metric noise = 0
RRF noise           = ±1
```

---

# 6. 결과

## 6.1 측정기 안정화: 130 → 130_v2

| 지표 | 130 | 130_v2 | 변화 |
|---|---:|---:|---:|
| Strict Top-1 | 39/52 | 39/52 | 0 |
| Lenient Top-1 | 51/60 | 51/60 | 0 |
| Recall@3 | 58/60 | 58/60 | 0 |
| Noise FP | 2/8 | 2/8 | 0 |
| FTS Hit | 35/60 | 35/60 | 0 |
| RRF Top-1 | 50/60 | 49/60 | -1 |

Vector Top-1은 72문항 모두 동일했다.

따라서 이후 Vector 지표 변화는 실제 corpus 변화로 본다.

---

## 6.2 본 실험: 130_v2 → 221

| 지표 | 130_v2 | 221 | 변화 |
|---|---:|---:|---:|
| Strict Top-1 | 39/52 (75.0%) | 34/52 (65.4%) | -5 |
| Lenient Top-1 | 51/60 (85.0%) | 42/60 (70.0%) | -9 |
| Recall@3 | 58/60 (96.7%) | 54/60 (90.0%) | -4 |
| Noise FP | 2/8 (25%) | 4/8 (50%) | +2 |
| Noise 0.45 초과 term 수 | 15 | 53 | +38 |
| RRF Top-1 | 49/60 | 45/60 | -4 |
| FTS Hit | 35/60 | 35/60 | 0 |
| Top-3 Evidence Coverage | 216/216 (100%) | 165/216 (76.4%) | -51 |
| Top-5 Evidence Coverage | 360/360 (100%) | 247/360 (68.6%) | -113 |

Vector 계열 변화는 측정 noise 0을 크게 넘었다.

따라서 이는 실제 변화다.

---

# 7. 핵심 발견

## 7.1 기존 TBox term 검색 자체가 망가진 것은 아니다

Top-1이 변경된 19건을 추적한 결과:

```text
기존 term → 기존 term     0건
기존 term → 신규 term    19건
```

이었다.

즉 코드리스트 91건이 기존 term 간 의미 순서를 흐트러뜨린 것이 아니다.

정확한 현상은:

> **신규 코드값이 기존 TBox term보다 높은 similarity를 얻어 상위 슬롯을 차지했다.**

이다.

이 차이는 중요하다.

```text
기존 term 간 순위 붕괴
→ embedding / retrieval 자체 문제

신규 term의 슬롯 점유
→ 서로 다른 역할의 resource를 같은 index에서 경쟁시킨 구조 문제
```

이번 결과는 후자에 가깝다.

---

## 7.2 “개념”과 “값”이 같은 Vector Space에서 경쟁했다

대표 사례:

| 질의 | 기존 1위 | 신규 1위 |
|---|---|---|
| 담보가 잡혀 있나요? | 담보 유형 | 담보부 |
| 쿠폰금리 | 표면금리 | 변동금리 |
| 신용평가 등급 | 신용등급 | 등급 보유 |
| 만기 | 만기일 | 만기경과 |
| 투자위험등급 | 투자위험등급 | 보통 위험(4등급) |

여기에는 서로 다른 문제가 섞여 있다.

### Case A — 값이 더 직접적인 경우

```text
"담보"
→ 담보 유형
vs
→ 담보부
```

사용자 의도에 따라 실제 값이 더 직접적인 후보가 될 수도 있다.

### Case B — 명백한 의미 오류

```text
"쿠폰금리"
→ 표면금리
vs
→ 변동금리
```

`쿠폰금리`는 표면금리의 표현에 가깝지, 변동금리라는 코드값과 동일하지 않다.

### Case C — 사실상 동점

```text
"만기"
만기일     0.6124
만기경과   0.6127
```

점수차가 너무 작아 Vector ranking 자체로 개념과 값을 구분하기 어렵다.

---

## 7.3 실제 피해는 Top-1보다 Evidence Loss에서 더 크게 나타났다

Top-5 comment 근거 수가 줄어든 질의:

```text
47 / 72
```

답변 가능 60건 중 Top-5에 comment가 하나도 없는 질의:

```text
2건
- 등급
- 보수
```

또한:

```text
Exact Top-1
12/12 → 12/12
```

로 그대로였지만:

```text
Exact Top-5 evidence
60/60 → 48/60
```

으로 20% 감소했다.

즉:

> **검색 지표만 보면 정상처럼 보여도 실제 Answer 단계에 전달되는 근거는 악화될 수 있다.**

따라서 향후에도 단순 URI hit뿐 아니라 evidence coverage를 함께 측정해야 한다.

---

## 7.4 `등급` 계열이 가장 강한 충돌 구간이다

Recall@3에서 새로 빠진 질의:

```text
등급
보수
채권 신용등급
평가사 등급이 몇 개인가요
```

중 3건이 등급 계열이다.

221 corpus에서는:

```text
CreditRating
RatingBand
RiskGrade
Rated
ratingRank
...
```

가 동시에 경쟁한다.

따라서 `신용등급`, `위험등급`, `등급 대역`, `등급 서열`, `실제 등급값`은  
하나의 검색 문제로 취급하면 안 된다.

이는 이후 Plan & Routing에서 **논리 개념과 실제 조건값을 분리해야 할 필요성**으로 이어진다.

---

## 7.5 기존 `0.45` floor는 코드값 문서에 그대로 적용할 수 없다

Noise FP:

```text
25% → 50%
```

대표 결과:

```text
"파이썬 리스트 정렬"   → A     0.5220
"어제 축구 경기 결과" → A     0.4962
"비트코인 시세 알려줘" → 통화  0.5139
```

기존 TBox term:

```text
text length median = 117.5
```

신규 코드리스트:

```text
text length median = 27.0
```

따라서 두 corpus는 similarity score distribution 자체가 다르다.

즉:

```text
BOND_SCORE_FLOOR = 0.45
```

는 TBox comment 중심 검색에서 얻은 noise floor이지  
짧은 코드값까지 포함한 전체 ontology의 보편적 relevance threshold가 아니다.

---

# 8. 이번 테스트의 판정

## 8.1 Index Build

| 조건 | 결과 |
|---|---:|
| 221건 적재 | PASS |
| 기존 130 embedding 재사용 | PASS |
| 신규 91건만 embedding 생성 | PASS |
| 중복 URI | 0 |
| embedding NULL | 0 |

인프라적으로는 정상이다.

---

## 8.2 Search Architecture

### 판정: 현재 형태의 221 Mixed Index는 사용하지 않는다

이유는 단순 Top-1 하락이 아니다.

핵심은:

```text
Top-5 evidence coverage
100% → 68.6%
```

이며, 답변 가능한 질의 2건이 **comment 근거 0건** 상태로 Answer 단계에 진입한다.

따라서:

> **TBox 개념 검색과 코드값 검색을 동일한 Vector Retrieval 슬롯에서 경쟁시키는 구조는 현재 Agent의 Grounding 목적과 맞지 않는다.**

---

# 9. 이번 실험이 전체 Agent 설계에 주는 의미

이번 실험 전에는 다음 두 방향을 모두 고려할 수 있었다.

```text
Option A
TBox concept만 Vectorize
→ 실제 값은 후속 단계에서 조회

Option B
TBox concept + code value 모두 Vectorize
→ 한 번에 grounding
```

221 실험 결과 Option B에서는:

- 코드값이 TBox 개념을 밀어냄
- comment evidence 감소
- 동일 threshold 사용 불가
- 등급 계열 ambiguity 증가

가 확인됐다.

따라서 현재 1~2단계의 책임은 다음처럼 유지하는 것이 타당하다.

```text
① Query Understanding
   사용자 언어를 조건으로 분해
        ↓
② TBox Ontology Grounding
   comment 기반 semantic retrieval
   "이 질문이 어떤 금융 개념을 요구하는가?"
```

여기까지가 **논리 의미 해석**이다.

다음 문제는:

```text
fp:ratingRank
fp:remainingDays
fp:expenseRatio
```

같이 grounding된 논리 개념을 실제:

```text
raw.bond_master.rating_rank
raw.bond_master.remaining_days
raw.etf_master.total_expense_ratio
```

와 연결하는 것이다.

이 문제는 Vector Search의 범위를 넓혀 해결할 문제가 아니라  
**Logical Schema ↔ Physical Schema Linking 문제**다.

---

# 10. 다음 단계로 이어지는 질문

현재 2단계는 다음과 같은 결과를 만든다고 가정한다.

```json
{
  "grounded_concepts": [
    {
      "concept_uri": "fp:ratingRank",
      "label": "신용등급 서열"
    },
    {
      "concept_uri": "fp:remainingDays",
      "label": "잔존일수"
    }
  ]
}
```

하지만 3단계 Planner가 실제 SQL을 만들려면 다음 정보가 추가로 필요하다.

```text
fp:ratingRank
→ 어느 DB?
→ 어느 table?
→ 어느 column?
→ 문자열 비교인가 숫자 비교인가?
→ AA- 이상은 어떤 방향인가?

fp:remainingDays
→ 어느 table.column?
→ 단위는 day인가 year인가?
```

즉 2단계 이후에는 **Ontology Meaning과 Physical Schema를 연결한 metadata context**가 필요할 가능성이 높다.

다음 Action 3는 바로 이 문제를 검증한다.

---

# 11. Action 3 — Semantic Schema Context 기반 NL2SQL / Plan & Routing 실험

기존의:

```text
코드리스트 91건의 검색 이득 측정
```

을 Action 3의 핵심으로 두지 않는다.

대신 다음 세 조건을 비교한다.

## A. Physical Schema Only

Planner 입력:

```text
raw.table.column
datatype
PK/FK
```

만 제공.

---

## B. Physical Schema + TBox Meaning

Planner 입력:

```text
RDB schema
+
fp: ontology concept
+
rdfs:comment
```

제공.

---

## C. Physical Schema + TBox Meaning + Business Context

Planner 입력:

```text
RDB schema
+
ontology meaning
+
concept ↔ physical source
+
filter rule
+
join rule
+
unit / value rule
```

제공.

예:

```json
{
  "concept_uri": "fp:ratingRank",
  "business_meaning": "신용등급 간 우열 비교용 서열",
  "sources": [
    {
      "engine": "rdb",
      "path": "raw.bond_master.rating_rank",
      "datatype": "INTEGER",
      "usage": ["FILTER", "SORT"],
      "business_rule": "신용등급 범위 비교는 원등급 문자열이 아니라 rating_rank를 사용한다."
    }
  ]
}
```

---

# 12. Action 3에서 검증할 핵심 지표

35개 예상질의를 활용해 다음을 비교한다.

### NL2SQL

- Table Accuracy
- Required Column Recall
- Filter Semantic Accuracy
- Join Accuracy
- SQL Executability
- Execution Accuracy
- Hallucinated Schema Rate

### Plan & Routing

- RDB / Graph / Vector 선택 정확도
- Engine 누락률
- 불필요한 Engine 호출률
- `depends_on` 정확도
- Graph → RDB → Vector 순서 정확도
- 실제 실행 가능한 Plan 비율

핵심 질문은 다음이다.

> **Planner가 RDB schema만 보고 논리 의미를 스스로 연결하게 해도 되는가?**

또는:

> **Ontology Grounding 이후 Business Context가 결합된 Semantic Schema Context를 제공해야 하는가?**

---

# 13. 현재까지 확정된 정책

이번 실험으로 다음은 유지한다.

### TBox Vector Grounding

```text
comment가 풍부한 schema concept 중심
```

### Retrieval

```text
Vector Search 기본
Top-3 후보 전달
RRF 기본 경로 제외
```

### Threshold

```text
0.45
= noise floor
≠ 답변 가능성 판정
```

### Code Value

```text
TBox Vector Index에 무조건 혼합하지 않음
```

실제 값의 resolution 위치는 후속 Plan / ABox / RDB 구조에서 결정한다.

---

# 14. 이번 실험이 검증하지 않은 것

이번 테스트는 다음을 직접 검증하지 않았다.

### 14.1 실제 3단계 SQL 정확도

이번 실험은 Ontology Retrieval 단계까지만 측정했다.

따라서:

```text
TBox Grounding
→ RDB Schema Linking
→ SQL
```

이 실제로 정확한지는 Action 3에서 검증해야 한다.

### 14.2 코드리스트 91건의 최종 Agent 가치

221 mixed index가 실패했다고 해서:

```text
AAA
AA-
장기
담보부
```

같은 값이 Agent에 필요 없다는 뜻은 아니다.

이 값들은 이후 ABox / RDB filtering에서 필요할 수 있다.

이번 실험이 부정한 것은:

```text
"그 값을 TBox concept와 같은 Vector Retrieval 슬롯에서 경쟁시키는 방식"
```

이다.

### 14.3 LLM 최종 Answer Accuracy

Evidence coverage는 최종 답변 품질의 proxy다.

실제 답변 품질은 Plan / Execution / Answer까지 연결한 E2E에서 별도로 측정한다.

---

# 15. 최종 결론

이번 221 실험은 단순히 “용어가 많아지면 검색이 나빠진다”는 결과가 아니다.

더 정확한 결론은 다음이다.

> **TBox의 개념·속성과 실제 코드값은 Agent 내부에서 서로 다른 역할을 가진다. 이를 동일 Vector Index에서 경쟁시키면 코드값이 상위 슬롯을 점유하면서 TBox comment 기반 근거를 밀어낸다. 따라서 1~2단계는 TBox 의미 Grounding에 집중하고, 그 이후 단계에서 논리 개념을 RDB / Graph / Vector의 실제 Physical Schema와 연결하는 구조를 검증해야 한다.**

따라서 다음 Action은:

```text
Action 3
Semantic Schema Context 기반
NL2SQL + Plan & Routing A/B/C 실험
```

으로 이어진다.

```text
A. Physical Schema Only

B. Physical Schema
   + TBox Meaning

C. Physical Schema
   + TBox Meaning
   + Business Context / Binding Rule
```

세 조건을 동일 예상질의로 비교해  
**Planner가 Physical Schema 연결을 어디까지 스스로 판단하게 할 것인지 결정한다.**

---

# 부록 A. 재현

```bash
cd vectordb_test/3_baseline_130_v2

# 130_v2
python3 eval130_load.py terms130
python3 eval130_run.py terms130 3_eval130_v2_raw.json
python3 eval130_freeze.py 3_baseline_130_v2 3_eval130_v2_raw.json terms130

# 221
python3 ../../kb/build_bond_index.py
python3 eval130_load.py terms221
python3 eval130_run.py terms221 3_eval221_raw.json
python3 eval130_freeze.py 3_baseline_221 3_eval221_raw.json terms221

# 비교
python3 eval_compare.py \
  ../results/3_baseline_130_v2.json \
  ../results/3_baseline_221.json
```

---

# 부록 B. 주요 산출물

| 파일 | 역할 |
|---|---|
| `eval130_load.py` | pgvector 적재 |
| `eval130_run.py` | 동결 질의셋 평가 |
| `eval130_freeze.py` | baseline 동결 |
| `eval_compare.py` | 130_v2 / 221 비교 |
| `3_baseline_130_v2.json` | 결정적 130 baseline |
| `3_baseline_221.json` | 221 mixed baseline |
