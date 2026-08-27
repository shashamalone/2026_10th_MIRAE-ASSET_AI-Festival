## 재현 방법과 현재 주의사항

원래 실행 순서는 다음과 같다.

```bash
python3 eval_query_frame.py --check-gold
python3 eval_query_frame.py --model HCX-007 --audit
python3 eval_query_frame.py --ambiguous
python3 build_tbox_index.py
python3 eval_query_frame.py --downstream
```

- `--check-gold`: LLM·네트워크 없이 35문항 ID, enum, 원문 span, limit 교차 일관성을 검사한다.
- `--audit`: 기본 프레임 추출 뒤 별도 감사 호출로 `validation_targets`를 대체한다.
- `--ambiguous`: 별도 12문항에서 모호 span과 premature resolution을 검사한다.
- `build_tbox_index.py`: 운영 인덱스를 건드리지 않고 평가 전용 188용어 테이블을 만든다.
- `--downstream`: 저장된 프레임으로 A/B/B′/A+B′ 검색을 비교한다.

현재 `eval_query_frame.py`의 gold 참조 상수는 과거 경로인 `vectordb_test/action3_semantic_schema/gold`를 가리키지만 실제 파일은 `vectordb_test/4_semantic_schema_nl2sql/gold`에 있다. 따라서 현 작업트리에서 위 명령을 그대로 재실행하면 `FileNotFoundError`가 발생한다. **기존 결과 파일을 재현하기 전에 이 경로를 현재 디렉터리 구조에 맞게 수정해야 하며**, 이 README 재작성에서는 평가 코드와 기존 결과 파일을 변경하지 않았다.

또한 35회 LLM 호출은 API 상태에 따라 지연과 출력이 달라질 수 있다. guard 변경 효과만 비교할 때는 새 LLM 호출 대신 저장된 `_raw`에 `--rescore`를 적용해야 모델 출력 변동과 후처리 효과를 분리할 수 있다.