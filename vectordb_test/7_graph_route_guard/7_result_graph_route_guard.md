# 실험 7 결과 — Route Guard와 pyoxigraph GraphDB

## 결론

Architecture decision의 첫 구현 단위는 부분 성공이다.

- **Route Guard: PASS** — 저장 Query Frame에서 기존 RDB 14문항은 모두
  `rdb_only`, 관계·다중 도메인 대표 3문항은 모두 `unsupported`로 분리됐다.
- **pyoxigraph 구축·SPARQL 실행: PASS** — TTL 10개를 persistent Store로 만들고
  실제 관계 질의에서 46행을 반환했다.
- **GRAPH_ONLY 운영 승격: BLOCKED** — 관계의 `sourceId`와 `asOf`는 존재하지만
  `fp:supportedBy` 문서 evidence 인스턴스가 없어 근거 문장 계약을 만족하지 못한다.
- **현재 RDB snapshot 승격: BLOCKED** — metadata의 네 도메인 `as_of=2026-08-21`이
  절대 cutoff `2026-07-11`을 넘는다. 과거 RDB 14/14 성공을 부정하는 결과가 아니라,
  현재 snapshot을 같은 실험으로 재사용할 수 없다는 판정이다.

## 구현된 실행 계약

```text
HCX Query Frame
  → verified metadata grounding
  → schema/domain/cutoff validator
  → constrained route JSON
       query_type enum
       execution_plan maxItems=3
  → rdb_only 또는 unsupported
```

현재 enum은 향후 route까지 명시하되, 실제 반환은 검증된 두 종류만 허용한다.

```text
rdb_only, tbox_validate_only, graph_only, graph_then_rdb,
graph_then_rdb_vector, unsupported
```

`graph_only`는 아래 독립 vertical slice가 evidence까지 통과한 뒤에만 route에서
활성화한다.

## Route 결과

| 지표 | 결과 | 판정 |
|---|---:|---|
| 기존 RDB 질문 route | 14/14 | PASS |
| unsupported 대표 route | 3/3 | PASS |
| cutoff safety 단위검사 | 4/4 | PASS |
| query type enum | 고정 6종 | PASS |
| plan step 상한 | 3 | PASS |

q010은 Query Frame의 `relations`에 대표종목번호·판매상태 같은 속성 경로가 들어 있어
최초 규칙에서 잘못 차단됐다. `relations` 배열 존재만으로 판정하지 않고 task·단일
도메인·허용 computation·verified plan을 함께 보도록 수정한 뒤 14/14가 됐다.

## GraphDB 구축 결과

| 지표 | 결과 | 의미 |
|---|---:|---|
| 입력 TTL | TBox 5 + ABox 5 | 현재 ontology 전체 입력 |
| persistent triples | 1,165,996 | cutoff projection 이후 Store 크기 |
| 제외한 미래 relation node | 573 | `fp:asOf > 2026-07-11` |
| Store 내 미래 `fp:asOf` | 0 | cutoff gate PASS |
| 에코프로 관계 SPARQL 결과 | 46행 | 실제 pyoxigraph 실행 PASS |
| 고유 ETF | 45종 | 에코프로의 cutoff 내 확인된 자회사 전체 경로 |
| ETN 결과 | 0건 | `a fp:ETF` template 강제 |
| relation source/as_of coverage | 100% | `sourceId`, 두 관계 기준일 존재 |
| UPDATE 차단 | PASS | read-only runtime |
| SERVICE 차단 | PASS | 외부 federation 금지 |
| `supportedBy` coverage | 0% | 문서 evidence 미구축 |

검증한 경로는 다음과 같다.

```text
에코프로
  → fp:hasSubsidiary / fp:subsidiaryCompany
  → 자회사
  → fp:issuedByCompany 역방향
  → 편입증권
  → fp:holdingSecurity 역방향
  → fp:hasHolding 역방향
  → ETF
```

기존 ontology 검증의 에코프로비엠 단일 경로는 고유 ETF 40종이며, 실험 7 template은
cutoff 내 확인된 다른 자회사도 포함해 고유 ETF 45종·관계행 46건을 반환했다.
예시 결과에는 에코프로비엠, `sec-247540`, ETF명, 편입비중,
편입기준일 `2026-07-10`, 관계기준일 `2026-03-18`, KODEX/RISE 등의 source와
DART source ID가 포함됐다.

## 현재 blocker

### 1. RDB snapshot cutoff 불일치

`build_schema_catalog.py --check`는 다음 네 도메인을 의도적으로 차단했다.

```text
bond_kr, etf_kr, etf_gl, fund_pub: as_of 2026-08-21 > cutoff 2026-07-11
```

따라서 08-21 값을 07-11이라고 relabel해서는 안 된다. 07-11 snapshot을 복구하거나
07-11 현재 유효한 행만 재구축한 뒤 동일 Gold 회귀를 다시 실행해야 한다.

### 2. Graph 문서 evidence 부재

현재 Holding과 SubsidiaryRelation에는 `fp:sourceId`가 있지만 실제 `fp:Document`
인스턴스와 `fp:supportedBy` 링크가 없다. 따라서 SPARQL 결과 자체는 맞더라도 사용자가
요구한 문서명·발행기관·발행일·근거 문장을 반환할 수 없다.

## 다음 Action Item

1. 07-11 RDB snapshot을 복구하고 기존 Gold DB exact 14/14를 재확인한다.
2. cutoff 이하 공식 편입내역·DART 문서를 `fp:Document`로 구축한다.
3. Holding/SubsidiaryRelation의 `fp:supportedBy`를 연결하고 coverage 100%를 만든다.
4. 같은 에코프로 SPARQL을 재실행해 결과 exact와 문서 evidence를 함께 검증한다.
5. 이 네 조건이 통과된 뒤에만 `graph_only` route를 활성화한다.
6. 그 다음 `graph_then_rdb`, 마지막으로 entity-scoped Vector 검색을 추가한다.

## 재현 명령

```bash
python3 -m pip install -r requirements.txt
python3 src/kb/build_graph.py --check
python3 script/test_route_guard.py
python3 script/test_graph_vertical_slice.py
python3 vectordb_test/7_graph_route_guard/evaluate.py
```

수치 정본은 `results/metrics.json`, Store build 정본은
`artifacts/oxigraph/manifest.json`이다.
