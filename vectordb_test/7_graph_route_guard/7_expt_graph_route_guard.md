# 실험 7 — Deterministic Route Guard + pyoxigraph Graph Vertical Slice

## 목적

자유형 multi-engine Planner를 사용하지 않고 검증된 RDB 질의만 RDB로 보내며, 현재
TTL 10개를 pyoxigraph persistent Store로 구축해 실제 SPARQL 관계 경로를 검증한다.

검증된 binding을 유지하되 LLM의 자유도를 결정적으로 제한하는 구조를 테스트한다

```text
Query Understanding → 기존 HCX Query Frame 유지
  → TBox grounding → schema_context의 concept URI grounding 유지
  → 질문별 최소 verified binding 조회 → schema_bindings.json에서 domain/usage별 선택
  → 허용 table·column·join·engine whitelist  → 기존 deterministic RDB compiler 유지
  → SQL/route template 또는 constrained compiler → 신규 Route Guard 구현 중
  → schema·domain·cutoff validator → 2026-07-11 gate 추가 완료
  → 실행 → RDB + pyoxigraph 실제 SPARQL 검증
```

1. 질문별 full schema 대신 최소 verified binding만 제공
2. 허용 table·column·JOIN path를 whitelist로 제한
3. Routing을 자유 생성이 아닌 규칙 또는 constrained plan template으로 변환
4. 실행 전 schema·domain·cutoff validator 적용
5. JSON schema에 query type enum과 plan step 상한 추가
6. 같은 Gold와 snapshot으로 재실험



## 입력과 cutoff

- cutoff: `2026-07-11`
- TBox: `common.ttl`, `bond_kr.ttl`, `etf_kr.ttl`, `etf_gl.ttl`, `fund_pub.ttl`
- ABox: 도메인 4종과 company `instances_*.ttl` 5개
- 원본 TTL과 `data/csv`는 수정하지 않는다.
- build 단계에서 `fp:asOf > 2026-07-11`인 관계 노드와 그 인입 링크를 Store
산출물에서 제외하고 제외 건수를 manifest에 기록한다.

## 검증 질문

1. **기존 RDB 14문항**만 `rdb` route로 허용되는가?
2. 관계·다중 도메인 대표 질문은 SQL 실행 전에 차단되는가?
3. 현재 TTL을 pyoxigraph에 적재하고 실제 SPARQL을 실행할 수 있는가?
4. `에코프로 → 자회사 → 편입증권 → ETF` 경로가 cutoff 내 근거와 함께 반환되는가?
5. Graph 결과를 최종 답변에 사용할 문서 evidence가 충분한가?

## 실행

```bash
python3 -m pip install -r requirements.txt
python3 src/kb/build_graph.py
python3 src/kb/build_graph.py --check
python3 script/test_route_guard.py
python3 script/test_graph_vertical_slice.py
python3 vectordb_test/7_graph_route_guard/evaluate.py
```

## 판정 기준

- RDB route `14/14`, unsupported 대표 `3/3`
- Store의 cutoff 이후 `fp:asOf` `0건`
- 실제 SPARQL 결과 `1건 이상`
- relation source/as_of coverage `100%`
- UPDATE/SERVICE 거부
- `supportedBy` 문서 evidence coverage `100%`가 되기 전에는 GRAPH_ONLY 운영 승격 금지

