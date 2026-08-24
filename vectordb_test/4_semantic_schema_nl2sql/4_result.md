# Action 3 — Semantic Schema Context 실험 결과

- 실행 기준일: 2026-08-23~2026-08-24
- 데이터 cutoff: `2026-07-11`
- 모델: HyperCLOVA X `HCX-007`
- 통제값: temperature `0.1`, seed `0`, top_p `0.8`, 최대 출력 `4096` tokens
- 조건: A=Physical Schema, B=A+TBox, C=B+명시적 binding/business rule
- 결론: **A/B/C 어느 조건도 운영 Planner 채택 기준을 만족하지 못했다.** C가 일부 지표에서 상대적으로 낫지만 SQL 실행 정답률은 세 조건 모두 `0%`다.

## 1. 실행 범위와 재현성

PostgreSQL에는 원천·파생·관계 데이터 12개 테이블을 명시적 타입과 PK/FK로 적재했다.

| 계층 | 테이블 | 적재 행 |
|---|---|---:|
| raw | `bond_kr_master` | 42,394 |
| raw | `etf_kr_master` | 1,733 |
| raw | `etf_gl_master` | 5,646 |
| raw | `fund_pub_master` | 95,618 |
| enriched | `bond_kr_enriched` | 42,394 |
| enriched | `etf_kr_enriched` | 1,733 |
| enriched | `fund_pub_dedup` | 11,138 |
| enriched | `company_master` | 118,709 |
| enriched | `holding_code_map` | 1,393 |
| relations | `etf_theme` | 5,646 |
| relations | `etf_holding` | 47,016 |
| relations | `company_subsidiary` | 29,524 |

깨진 국내 ETF 식별자 `pd_itm_no='KR'` 1행과 공모펀드 `itm_no='"'` 1행은 명시적으로 제외했다. `data/csv/`는 읽기만 했고, 관계 `as_of > 2026-07-11`은 0행이다.

NL2SQL은 RDB가 필요한 28문항, Routing은 전체 35문항을 평가했다. 1차에서 모든 문항에 오류 또는 A/B/C 차이가 있어 문항별 3회가 모두 실행됐다.

| 실험 | 문항 | 조건 | 반복 | 최종 셀 |
|---|---:|---:|---:|---:|
| NL2SQL | 28 | 3 | 3 | 252 |
| Routing | 35 | 3 | 3 | 315 |

API quota로 실패한 NL2SQL 78셀과 일시적 DNS 장애로 실패한 Routing 11셀은 모델 오류에서 제외하고 같은 입력으로 재호출했다. Routing의 모델 JSON 파싱 실패 8셀은 실제 Planner 실패로 보존했다.

Gold, A/B/C context, CSV·TTL snapshot은 SHA-256으로 기록했다. Routing 중 Gold 파일 해시는 `ab13…`에서 `d19b…`로 변경됐으나 35개 질문 문구, 원본 예상질의 SHA, A/B/C context가 동일함을 검증했다. 모델 prompt에는 Gold plan이 포함되지 않으며, 변경 이력과 사유는 `routing_raw.json.meta.gold_hash_migration`에 남겼다.

## 2. NL2SQL 결과

단위는 %, 각 조건 `n=84`다. Hallucinated Schema는 낮을수록 좋고 나머지는 높을수록 좋다.

| 지표 | A | B | C |
|---|---:|---:|---:|
| Table Accuracy | 19.0 | 26.2 | **40.5** |
| Required Column Recall | **36.8** | 32.0 | 36.6 |
| Filter Semantic Accuracy | **75.0** | 68.5 | 66.1 |
| Join Accuracy | **60.7** | 57.1 | 57.1 |
| SQL Executability | 19.0 | **23.8** | 22.6 |
| Execution Accuracy | 0.0 | 0.0 | 0.0 |
| Hallucinated Schema Rate | 59.5 | 48.8 | **42.9** |

C는 A보다 Table Accuracy를 21.4%p 높이고 hallucination을 16.7%p 낮췄다. 그러나 필터·조인·실행 가능성은 개선되지 않았고, 최종 결과 집합이 Gold와 일치한 실행은 한 건도 없었다.

### NL2SQL 오류 분포

한 셀에 여러 오류가 함께 집계될 수 있다.

| 오류 | A | B | C |
|---|---:|---:|---:|
| E1 Wrong Table | 7 | 6 | 7 |
| E3 Missing Column | 16 | 20 | 19 |
| E4 Wrong Filter Operator | 3 | 2 | 2 |
| E6 Wrong Join | 4 | 2 | 0 |
| E7 Hallucinated Schema | 50 | 41 | 36 |
| E12 SQL Syntax/Execution Error | 68 | 64 | 65 |

E2와 E5는 다른 오류와 중복 없이 결정적으로 분리할 기준이 없어 독립 집계하지 않았다. E13은 구조 지표가 모두 맞고 실행 결과만 다른 경우로 제한했으며 해당 셀은 0건이다.

## 3. Multi-source Routing 결과

단위는 %, 각 조건 `n=105`다. Unnecessary Engine Call Rate는 낮을수록 좋다.

| 지표 | A | B | C |
|---|---:|---:|---:|
| Engine Selection Accuracy | 13.3 | 12.4 | **24.8** |
| Dependency Accuracy | **23.8** | 19.0 | 21.0 |
| Parallelization Accuracy | 41.9 | **43.8** | 37.1 |
| Unnecessary Engine Call Rate | 38.7 | 39.1 | **34.7** |

C는 엔진 선택과 불필요 호출에서 상대적으로 가장 나았지만, 필요한 엔진 집합을 맞힌 비율은 24.8%에 불과하다. 의존성과 병렬화도 개선되지 않았다.

| 오류 | A | B | C |
|---|---:|---:|---:|
| E9 Wrong Dependency | 92 | 99 | 97 |
| E10 Missing Engine | 36 | 35 | 29 |
| E11 Unnecessary Engine | 66 | 67 | 57 |
| Planner JSON 파싱 실패 | 5 | 1 | 2 |

Graph는 동결 TTL snapshot을 기준으로 plan만 평가했다. Graph store 구축과 SPARQL 실행 정확도, Vector 검색 실행 정확도는 이번 Action 범위가 아니므로 측정하지 않았다.

## 4. 성공 기준 판정

| 권장 기준 | 목표 | C 실측 | 판정 |
|---|---:|---:|---|
| SQL Executability | ≥95% | 22.6% | 실패 |
| Execution Accuracy | ≥90% | 0.0% | 실패 |
| Required Column Recall | ≥95% | 36.6% | 실패 |
| Hallucinated Schema | 0% | 42.9% | 실패 |
| Engine Selection Accuracy | ≥95% | 24.8% | 실패 |
| Dependency Accuracy | ≥95% | 21.0% | 실패 |

## 5. 최종 판정 질문

1. **RDB schema만 제공해도 충분한가?** 아니다. A의 SQL 실행 정답률은 0%, schema hallucination은 59.5%다.
2. **TBox business meaning을 추가하면 어떤 오류가 줄어드는가?** A→B에서 hallucination은 10.7%p, E6 Wrong Join은 2건 줄었다. 반면 column recall·filter·join 정확도는 악화돼 일관된 개선은 아니다.
3. **명시적인 semantic binding/business rule까지 제공해야 하는가?** 안전장치로는 필요하지만 충분하지 않다. C는 table accuracy와 hallucination, engine selection을 개선했지만 execution accuracy는 여전히 0%다.
4. **Planner가 physical schema 연결을 스스로 판단해도 되는가?** 안 된다. C에서도 schema hallucination 42.9%, engine selection 24.8%로 deterministic schema validation과 검증된 binding이 필요하다.
5. **RDB/Graph/Vector 계획을 정확한 순서로 만들 수 있는가?** 현재 prompt/context 구조로는 어렵다. C의 dependency accuracy는 21.0%, parallelization accuracy는 37.1%다.

## 6. Architecture decision

Option A, B, C를 그대로 운영 Planner에 적용하지 않는다. 다음 단계의 최소 후보는 C의 검증된 binding만 활용하되, LLM이 임의 table/column/engine을 만들 수 없도록 아래를 결정적으로 제한하는 구조다.

```text
TBox grounding
  → 질문별 최소 verified binding 조회
  → 허용된 SQL/route template 또는 constrained compiler
  → schema·domain·cutoff validator
  → 실행
```

이번 Action에서는 Graph store, 신규 parser/embedding 의존성, 자동 binding 갱신을 추가하지 않았다. 먼저 실패가 집중된 schema 식별자와 engine dependency를 결정적으로 제한한 뒤 동일 Gold로 재측정해야 한다.

## 7. 산출물

- 원시 실행: [`nl2sql_raw.json`](nl2sql_raw.json), [`routing_raw.json`](routing_raw.json)
- 상세 지표: [`nl2sql_metrics.json`](nl2sql_metrics.json), [`routing_metrics.json`](routing_metrics.json)
- 오류 사례: [`error_cases.json`](error_cases.json)
- Gold: [`../gold/gold_nl2sql.json`](../gold/gold_nl2sql.json), [`../gold/gold_routing.json`](../gold/gold_routing.json)
- Context: [`../contexts/schema_only.json`](../contexts/schema_only.json), [`../contexts/schema_tbox.json`](../contexts/schema_tbox.json), [`../contexts/schema_tbox_business.json`](../contexts/schema_tbox_business.json)
