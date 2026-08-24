# 5_query_frame_v1 — 1단계 Query Understanding 검증

파이프라인 1단계(Semantic Query Frame Extraction)의 출력 스키마를 35문항으로 검증하고 v1 을 확정한다.
여기서 수치로 확인된 것만 `src/agent/` 로 올린다.

```
query_frame.py         스키마 + 프롬프트 + extract() + audit() + guard() + to_conditions()
build_tbox_index.py    TTL 5개 → 평가 전용 pgvector 인덱스(schema_terms_all). 운영 인덱스는 안 건드린다
eval_query_frame.py    검증 영역 1~5
gold/gold_frames.jsonl        35문항 정답 프레임 (수기)
gold/ambiguous_queries.jsonl  모호 질의 12문항 (수기)
results/               원시 출력·스코어카드
```

## 왜 채움률로 검증하지 않는가

`entities 22/35` 는 실패가 아니라 엔티티가 없는 질문이 13개라는 뜻일 수 있다. 그래서 gold 에
슬롯별 필요 여부를 먼저 적고, **필요한 질문에서 채워졌는가(Recall) + 필요 없는 질문에서
안 만들었는가(Precision)** 를 잰다. 채움률은 보조 통계로만 찍는다.

`applicable` 같은 별도 필드는 두지 않았다 — **REQUIRED = gold 값이 비어있지 않음**으로 파생된다.
gold 가 `[]` 인 슬롯에 예측이 생기면 그게 곧 false positive 다.

## 확정 사항

| # | 결정 | 근거 |
|---|---|---|
| D1 | `domain_candidates` 는 배열, 값은 `bond_kr/etf_kr/etf_gl/fund_pub` | `product_category` 복합값 7문항. `BOND/ETF/FUND` 로는 q022·q028 이 요구하는 국내·해외 구분이 소실된다 |
| D2 | ABSTAIN 코드 정본은 긴 형식(`ABSTAIN_INVALID_TAXONOMY` 등) | 평가 대상 문자열이자 ttl 주석 표기 |
| D3 | 1단계는 ABSTAIN 을 판정하지 않는다. `validation_targets` 로 "무엇을 검증할지"만 낸다 | 판정은 `check_tbox`·`verify` 노드의 일 |
| D4 | 1단계는 TBox 를 보지 않는다. `fp:` URI·물리 컬럼명 생성 금지 | 검증 항목으로 0건 강제 |
| D5 | `operator` 극성은 사용자가 말한 축 기준 | "AA- 이상" → `신용등급 >= AA-`. `gold_nl2sql.json` 의 `crd_grd_rank <= 4` 는 물리층이라 **부호가 반대**다. 베끼면 gold 가 통째로 오염된다 |
| D6 | 팀 인터페이스는 `to_conditions()` 렌더러 1함수 | `wanggyu/agent/state.py:52` 가 `decomposed_conditions: list[str]` 로 계약을 못 박았고 `node.py:65` 가 불릿 텍스트로만 소비한다. 팀원 코드 수정 0 |

## 평가셋 오염 통제

프롬프트에 평가 문항의 답이 들어가면 점수가 부풀려진다. 다음을 제거했다.

- few-shot 예시가 q013 원문 그대로였다 → 평가셋에 없는 가상 질의로 교체
- 극성 예시의 `AA- 이상`·`순자산 1조 원 이상`·`총보수 0.05% 이하`·`잔존기간 3년 이하` 가
  각각 q011/q013·q015·q017·q013 의 조건과 일치했다 → `A+`·`2조 원`·`0.20%`·`듀레이션 4년`으로 교체
- `taxonomy_value` 설명의 예시가 `신용등급 "AAAA"`(= q031 의 답) 였다 → `위험등급 9등급`으로 교체

남은 겹침은 `신용등급`·`총보수`·`편입증권` 같은 도메인 어휘뿐이다. 이건 프롬프트가 반드시
가르쳐야 하는 필드 이름이지 답이 아니다.

**단, 감사 프롬프트(`AUDIT_SYSTEM`)에는 "신용등급은 AAA 가 최상단"과 "발행은 기업·기관이 하는 일"이
명시돼 있다.** 이 두 사실이 q031·q035 를 쉽게 만든다. 수치를 읽을 때 감안해야 한다.

## 알아둘 것

- q014·q023·q025·q030 은 데이터가 없어 최종 답변이 불가하다(`QUERY_COVERAGE_35.md`: 가능 15 / 부분 16 / 불가 4).
  1단계는 무관하다 — 프레임은 정상적으로 뽑혀야 하고 데이터 부재는 실행 단계에서 드러난다.
  이 "데이터 부재 답변불가"는 ABSTAIN 5종과 다른 축이라 `validation_targets` 에 넣지 않는다.
- "AA- 이상 → ratingRank ≤ 4" 변환은 1단계가 아니다. `agent-spec-0822.md:737` 이 이를 2.5단계
  business rule 로 배치했다. 1단계에서 하면 D4 위반이자 premature grounding 이다.
- 도메인별 기준일이 다르다(etf_kr 20260615 / etf_gl 20260616 / bond_kr 20260224 / holding 2026-07-10).
  `temporal.kind="latest_snapshot"` 은 도메인이 정해진 뒤에나 해소되므로 1단계는 `raw` 만 보존한다.

## 실행

```bash
python3 eval_query_frame.py --check-gold           # 네트워크 없이 gold 무결성만
python3 eval_query_frame.py --model HCX-007 --audit # 영역 1~3, 4a
python3 eval_query_frame.py --ambiguous            # 영역 4b
python3 build_tbox_index.py                        # 영역 5 전제 (pgvector)
python3 eval_query_frame.py --downstream           # 영역 5
```

---

# 측정 결과 (2026-08-23, HCX-007 + 별도 감사 호출)

## 모델 선택 — 실측으로 정했다

대표 4문항(조회·조건·관계·검증)으로 셋을 비교했다.

| 모델 | 스키마 준수(보정 전) | guard 보정 | 비고 |
|---|---|---|---|
| **HCX-007** | **4/4** | **1건** | 채택 |
| HCX-005 | 2/4 | 6건 | 가장 느림(최대 12.6s) |
| HCX-DASH-002 | 1/4 | 10건 | domain 을 통째로 비우거나 관계 질의를 조건검색으로 오분류 |

`HCX-DASH-002` 는 예전 측정(0.29s)의 속도 이점이 이 프롬프트에서는 사라졌다. 프롬프트가 길어
출력 토큰이 지연을 지배한다. 품질 차이가 커서 속도로 상쇄되지 않는다.

## 영역 1 — 구조 유효성

```
JSON parse 성공        35/35   PASS
스키마 준수(보정 전)    35/35   PASS   ← 중첩 스키마를 HCX-007 이 그대로 받는다
TBox 누출              1건     FAIL   q027 relations.path 에 included_in·parent_company
```

## 영역 2·3 — 슬롯 정확도와 의미 보존

| 슬롯 | Recall | Precision | 기준 | 판정 |
|---|---|---|---|---|
| domain_candidates | 89.1% | 95.3% | ≥95 | FAIL(R) |
| targets | 94.9% | 90.2% | ≥95 | FAIL |
| entities | 87.1% | 96.4% | ≥95 | FAIL(R) |
| constraints | 75.8% | 78.1% | ≥95 | FAIL |
| relations(존재) | 90.9% | 90.9% | ≥95 | FAIL |
| ordering | 85.7% | 100% | ≥95 | FAIL(R) |
| computation | 50.0% | 83.3% | ≥95 | FAIL |
| ambiguity | 100% | 50.0% | ≥95 | FAIL(P) |
| validation_targets(유형) | 60.0% | 60.0% | ≥95 | FAIL |

| 의미 보존 | 값 | 기준 | 판정 |
|---|---|---|---|
| **operator Exact** | **100%** | 100% | **PASS** |
| unit Exact | 100% | ≥95 | PASS |
| temporal Exact | 100% | ≥95 | PASS |
| task Exact | 97.1% | ≥95 | PASS |
| limit Exact | 97.1% | 100% | FAIL |
| value Exact | 95.0% | ≥95 | PASS |
| entity role Exact | 85.2% | ≥95 | FAIL |
| sort direction Exact | 83.3% | ≥95 | FAIL |
| relation 양끝 Exact | 50.0% | ≥95 | FAIL |

지연: p50 **5.7s**, 중앙값 기준 정상. p95 124.6s 는 API 스톨 1건 때문이며 재현되지 않는다.
감사 호출만 따로 재면 p50 0.76s / p95 1.14s 로 싸다.

## 영역 4 — 검증과 모호

```
Validation Recall(존재)   4/5     FAIL   q033 만 미검출
Validation Recall(유형)   3/5     FAIL   q032 를 future_value 로 오분류
Validation False Positive 1/30    FAIL   q026 만 오탐
Ambiguity Recall          11/12   FAIL   a06 "요즘 잘 나가는" 만 미검출
Premature Resolution      0/12    PASS   ← 가장 중요한 안전 속성
```

## 영역 5 — Downstream (TBox 검색 A/B, schema_terms_all 188용어)

|  | R@1 | R@3 | R@5 | R@10 | R@20 |
|---|---|---|---|---|---|
| A 질문원문 | 3.3% | 9.0% | 13.1% | 23.2% | 35.5% |
| B 슬롯연결 | 1.1% | 6.3% | 11.7% | 22.1% | 40.7% |
| B′ 슬롯개별병합 | 4.1% | 8.2% | 12.0% | 17.8% | 33.3% |
| **A+B′ 혼합** | **4.4%** | **10.1%** | **15.8%** | 22.7% | 37.4% |

**부정 결과 — 프레임은 질문 원문을 대체하지 못한다.** 슬롯을 한 문자열로 이어 붙이면(B)
여러 개념이 한 벡터로 평균돼 뭉개진다. TBox 인덱스가 `uri | label | altLabel | comment` 로
만들어져 있어 자연어 문장인 원문이 오히려 잘 맞는다.

**다만 원문에 슬롯 질의를 얹으면(A+B′) 운영 지점 K=5 에서 13.1% → 15.8% (상대 +21%) 로 오른다.**
따라서 2단계 TBox Grounding 의 권고안은 "원문을 프레임으로 갈아끼우기"가 아니라
"원문 검색 결과에 슬롯별 검색 결과를 병합하기"다.

---

# v1 판정

**전 항목 통과 기준으로는 미달이다.** 다만 실패의 성격이 두 갈래로 갈린다.

## 계약 등급 — downstream 이 값을 신뢰해도 되는 슬롯

`operator`(100%) · `unit`(100%) · `temporal`(100%) · `task`(97.1%) · `limit`(97.1%) ·
`value`(95.0%) · `targets`(R 94.9) · `entities` 텍스트(P 96.4) · `domain_candidates`(P 95.3)

여기에 **Premature Resolution 0%** 가 붙는다. 모호한 표현을 근거 없이 확정하지 않는다는
안전 속성은 12문항 전부에서 지켜졌다. 1단계의 존재 이유 중 절반이 이것이다.

## 참고 등급 — downstream 이 의존하면 안 되는 슬롯

`constraints`(75.8/78.1) · `computation`(50/83.3) · `validation_targets` 유형(60/60) ·
`entity role`(85.2) · `relation` 경로 양끝(50) · `ordering` Recall(85.7)

Planner 는 이 값들을 **힌트로만** 쓰고, 실제 필터·조인은 2.5단계 metadata_context 와
대조해 다시 확인해야 한다.

## 확인된 설계 결론 4가지

1. **감사는 분리해야 한다.** 분해와 감사를 한 프롬프트에 같이 시키면 서로 밀어낸다.
   트리거를 늘릴수록 다른 항목이 퇴행했다. 떼어내자 Validation Recall 이 1/5 → 5/5 로 올랐다.
   또 `validation_targets` 배열만 내게 하면 배열을 채워야 한다는 압력에 눌려 35문항 전부에
   무언가를 만들었다(정밀도 8.6%). **`normal` 을 enum 의 첫 값으로 둔 단일 verdict** 로 바꾸자
   오탐이 30/30 → 1/30 으로 떨어졌다.

2. **guard 는 장식이 아니다.** 결정적 규칙 두 개가 프롬프트로 못 잡던 것을 잡았다.
   `단일값 in → ==` 로 operator 88% → **100%**, `날짜 없는 as_of → latest_snapshot` 으로
   temporal 94.1% → **100%**. 둘 다 의미상 항진명제라 과적합이 아니다.

3. **`entity_existence` 는 1단계에서 원리적으로 판별할 수 없다.** 실재하는 낯선 이름
   (`에스케이하이닉스224-2`, `삼성 베스트 MMF 법인 제1호`)과 그럴듯한 가짜 이름
   (`KODEX AI로봇`)은 모델이 구분하지 못한다. 자기의심 트리거를 넣으면 q001·q002·q005·q006·q008
   에 오탐이 붙었다. **실제 메커니즘은 `entities[].match_mode="exact"` 와 해소기 0건 판정**이다.
   1단계가 못 잡는 게 결함이 아니라, 그 일이 여기 있지 않다.

4. **프레임은 TBox 검색을 위한 것이 아니다.** 영역 5 참조.

## 남은 결함 (수정하려면 일반 규칙으로만)

| 문항 | 증상 | 성격 |
|---|---|---|
| q015 | 범주 조건에 `in` 남용, domain 을 etf_gl 로 오판, 정렬 방향 asc | operator 는 guard 가 해결. 나머지 잔존 |
| q017·q018·q022 | `미국 주식형 ETF` 를 targets 한 덩어리로 묶어 투자지역·투자자산 constraint 누락 | targets/constraints 경계 |
| q017 | `1천억 달러` 를 1e12 로 환산(정답 1e11) | 자릿수 오류 |
| q016·q020·q028·q029 | "비교해줘" 가 있는데 `computation:compare` 미생성 | 트리거 미준수 |
| q027 | `included_in`·`parent_company` 영문 식별자 생성 | D4 누출 |
| q022·q028·q030·q035 | entity role 혼동(company↔ticker↔index) | role 분류 |

**주의: 이 목록을 문항별로 고치면 평가셋 과적합이다.** 35문항은 일반화를 재는 자이지
맞춰야 할 답이 아니다. 프롬프트 수정은 문항이 아니라 규칙 층위에서만 한다.
