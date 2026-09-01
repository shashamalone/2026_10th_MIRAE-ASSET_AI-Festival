# 실험 7 결과 — Route Guard와 pyoxigraph GraphDB

## 결론

Architecture decision의 첫 구현 단위는 부분 성공이다.

- **Route Guard: PASS** — 저장 Query Frame에서 기존 RDB 14문항은 모두
`rdb_only`, 관계·다중 도메인 대표 3문항은 모두 `unsupported`로 분리됐다.
- **pyoxigraph 구축·SPARQL 실행: PASS** — TTL 10개를 persistent Store로 만들고
실제 관계 질의에서 46행을 반환했다.
- **GRAPH_ONLY evidence gate: PASS** — Holding 47,016건과 cutoff 이내
SubsidiaryRelation 29,524건 모두 실제 원천에서 생성한 `fp:Document`에 연결됐다.
Q24 결과도 46행·45 ETF로 그대로 유지됐다.

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

`graph_only` vertical slice는 evidence까지 통과했다. 자유형 route를 열지는 않으며,
검증된 Q24 template부터 constrained route에 등록할 수 있는 상태다.

## Route 결과


| 지표                   | 결과    | 판정   |
| -------------------- | -----: | ---- |
| 기존 RDB 질문 route      | 14/14 | PASS |
| unsupported 대표 route | 3/3   | PASS |
| cutoff safety 단위검사   | 4/4   | PASS |
| query type enum      | 고정 6종 | PASS |
| plan step 상한         | 3     | PASS |


q010은 Query Frame의 `relations`에 대표종목번호·판매상태 같은 속성 경로가 들어 있어
최초 규칙에서 잘못 차단됐다. `relations` 배열 존재만으로 판정하지 않고 task·단일
도메인·허용 computation·verified plan을 함께 보도록 수정한 뒤 14/14가 됐다.

## GraphDB 구축 결과


| 지표                               | 결과                   | 의미                                       |
| -------------------------------- | --------------------: | ---------------------------------------- |
| 입력 TTL                           | TBox 5 + ABox 5      | 현재 ontology 전체 입력                        |
| persistent triples               | 1,624,933            | evidence 및 cutoff projection 이후 Store 크기 |
| 제외한 미래 relation node             | 573                  | `fp:asOf > 2026-07-11`                   |
| Store 내 미래 `fp:asOf`             | 0                    | cutoff gate PASS                         |
| 에코프로 관계 SPARQL 결과                | 46행                  | 실제 pyoxigraph 실행 PASS                    |
| 고유 ETF                           | 45종                  | 에코프로의 cutoff 내 확인된 자회사 전체 경로             |
| ETN 결과                           | 0건                   | `a fp:ETF` template 강제                   |
| relation source/as_of coverage   | 100%                 | `sourceId`, 두 관계 기준일 존재                  |
| UPDATE 차단                        | PASS                 | read-only runtime                        |
| SERVICE 차단                       | PASS                 | 외부 federation 금지                         |
| Holding `supportedBy`            | 47,016/47,016 (100%) | 전체 편입관계 원천 매칭 PASS                       |
| SubsidiaryRelation `supportedBy` | 29,524/29,524 (100%) | cutoff 이내 전체 출자관계 PASS                   |
| cutoff 이후 evidence               | 0건                   | 미래 문서 연결 없음                              |
| Document 필수속성 오류                 | 0건                   | title·publisher·date·quote 100%          |


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

## 다음 Action Item

1. 통과한 Q24 고정 SPARQL만 `graph_only` constrained route에 등록한다.
2. 다음 GRAPH_ONLY Gold마다 같은 supportedBy 100% 계약을 적용한다.
3. 그 다음 `graph_then_rdb`, 마지막으로 entity-scoped Vector 검색을 추가한다.

## Evidence 구현 결과

- ETF 편입: 공식 운용사 raw와 sidecar를 `isin + as_of + code/name/weight`로 exact match했다.
- 기업 출자: DART raw의 접수번호·자회사명·지분율·출자목적을 exact match했다.
- 문서 URI는 원천 상대경로와 canonical claim의 SHA-256으로 결정적으로 생성했다.
- quote는 HCX가 생성한 문장이 아니라 원천 필드·값의 JSON 발췌다.
- ETF sidecar 상품명 충돌 1종은 주최측 명칭을 사용하고 두 표기를 evidence에 기록했다.
- raw exact-match 실패, sidecar 누락, cutoff 위반은 ABox build를 즉시 실패시킨다.

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