# Semantic Schema Context

Planner에 주는 metadata만 A(Physical Schema), B(+TBox), C(+Business Context)로
바꿔 NL2SQL과 multi-source routing을 비교한다. 

Gold와 입력 snapshot은 첫 HCX 호출
전에 SHA-256으로 동결한다.

질문 정본은 `expected_qa/2026_expected_qa.csv`이며 `expected_queries_35.json`을 포함한
Gold 3종은 `build_semantic_context.py`가 생성한다.

```bash
python3 src/kb/build_rdb.py
python3 vectordb_test/5_semantic_schema_nl2sql/build_physical_schema_catalog.py
python3 vectordb_test/5_semantic_schema_nl2sql/build_semantic_context.py
python3 vectordb_test/5_semantic_schema_nl2sql/evaluate_sql.py --self-test
python3 vectordb_test/5_semantic_schema_nl2sql/evaluate_routing.py --self-test
python3 vectordb_test/5_semantic_schema_nl2sql/run_nl2sql_eval.py
python3 vectordb_test/5_semantic_schema_nl2sql/evaluate_sql.py
python3 vectordb_test/5_semantic_schema_nl2sql/run_nl2sql_eval.py --repeat-selected
python3 vectordb_test/5_semantic_schema_nl2sql/evaluate_sql.py
python3 vectordb_test/5_semantic_schema_nl2sql/run_routing_eval.py
python3 vectordb_test/5_semantic_schema_nl2sql/evaluate_routing.py
python3 vectordb_test/5_semantic_schema_nl2sql/run_routing_eval.py --repeat-selected
python3 vectordb_test/5_semantic_schema_nl2sql/evaluate_routing.py
```

