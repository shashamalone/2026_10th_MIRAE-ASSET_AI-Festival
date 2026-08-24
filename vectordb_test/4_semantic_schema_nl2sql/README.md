# Action 3 — Semantic Schema Context

Planner에 주는 metadata만 A(Physical Schema), B(+TBox), C(+Business Context)로
바꿔 NL2SQL과 multi-source routing을 비교한다. Gold와 입력 snapshot은 첫 HCX 호출
전에 SHA-256으로 동결한다.

```bash
python3 src/kb/build_rdb.py
python3 vectordb_test/action3_semantic_schema/build_physical_schema_catalog.py
python3 vectordb_test/action3_semantic_schema/build_semantic_context.py
python3 vectordb_test/action3_semantic_schema/evaluate_sql.py --self-test
python3 vectordb_test/action3_semantic_schema/evaluate_routing.py --self-test
python3 vectordb_test/action3_semantic_schema/run_nl2sql_eval.py
python3 vectordb_test/action3_semantic_schema/evaluate_sql.py
python3 vectordb_test/action3_semantic_schema/run_nl2sql_eval.py --repeat-selected
python3 vectordb_test/action3_semantic_schema/evaluate_sql.py
python3 vectordb_test/action3_semantic_schema/run_routing_eval.py
python3 vectordb_test/action3_semantic_schema/evaluate_routing.py
python3 vectordb_test/action3_semantic_schema/run_routing_eval.py --repeat-selected
python3 vectordb_test/action3_semantic_schema/evaluate_routing.py
```

실행기는 기존 raw 결과를 지우지 않고 같은 snapshot의 미완료 cell만 이어서 실행한다.
Graph routing은 TTL snapshot을 대상으로 한 계획 평가이며 SPARQL은 실행하지 않는다.
