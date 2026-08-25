# Query Frame HCX latency 단일변수 후속 실험

기존 live 실패의 주원인인 **HCX timeout/5초 초과**를 prompt → token → schema → connection → queue → timeout 순서로 한 변수씩 비교한 뒤, 선택 구성을 RDB 14문항으로
qualification한다. 운영 src/**는 이 실험에서 변경하지 않는다.

```
python3 vectordb_test/6_rdb_vertical_slice/evaluate_query_frame_latency.py --dry-run


python3 vectordb_test/6_rdb_vertical_slice/evaluate_query_frame_latency.py --stage prompt --write-results


python3 vectordb_test/6_rdb_vertical_slice/evaluate_query_frame_latency.py --stage token --write-results


python3 vectordb_test/6_rdb_vertical_slice/evaluate_query_frame_latency.py --stage schema --write-results


python3 vectordb_test/6_rdb_vertical_slice/evaluate_query_frame_latency.py --stage connection --write-results


python3 vectordb_test/6_rdb_vertical_slice/evaluate_query_frame_latency.py --stage queue --write-results


python3 vectordb_test/6_rdb_vertical_slice/evaluate_query_frame_latency.py --stage timeout --write-results


python3 vectordb_test/6_rdb_vertical_slice/evaluate_query_frame_latency.py --stage qualification --write-results
```



각 stage는 중복 실행을 거부하며 자동 재시도하지 않는다. 초기 arm당 3회에서 판정이
불충분하면 arm당 5회로 확장한다. queue 단계는 동일 endpoint의 순차/동시 요청 진단일
뿐 운영 설정으로 선택하지 않는다. 상세 명세와 누적 결과는
6_2_result_query_frame_latency.md, 호출 단위 원자료와
집계는 results/query_frame_latency_raw.jsonl,
results/query_frame_latency_metrics.json에 기록한다.