# 실험 노트북 (계획 v4 — 2026-08-28)

`src/` 를 `%%module` 셀로 복사한 독립 실험 공간. **실험 중 `src/`·`metadata/`·`requirements.txt`·`data/csv/` 는 수정하지 않는다.**
`sync_to_py(dry_run=False)` 는 최종 채택 시에만 실행한다 (계획 v4 §10).

## 노트북

| 노트북 | 실험 ID | 내용 |
|---|---|---|
| `agent_main_0828.ipynb` | EXP-20260828-main-01 | RDB Agent 기준선 보관 (Q01·Q06·Q08, 코드 수정 없음) |
| `agent_graph_0828.ipynb` | EXP-20260828-graph-01 | Graph 검색 G01~G12 + 체크리스트 10항 (로컬 pyoxigraph) |
| `agent_vector_0828.ipynb` | EXP-20260828-vector-01 | PDF 적재 + Vector 검색 V01~V08 (로컬 pgvector) |
| `agent_integrated_0828.ipynb` | EXP-20260828-integrated-01 | Q02 병렬 / Q03 경로결정 / Q05 순차 통합 |

결과 JSON 은 `results/` 에 저장된다.

## 재생성·실행

```bash
# 재생성 (src 최신본 기준 — 노트북 수정 중이면 백업 먼저)
python3 test/notebook/experiments/build_experiments.py [main|graph|vector|integrated ...]

# 헤드리스 실행
jupyter nbconvert --to notebook --execute --inplace \
  --ExecutePreprocessor.timeout=900 test/notebook/experiments/<노트북>.ipynb
```

## 전제 조건

- 로컬 PostgreSQL `mafest` (127.0.0.1:5432) + pgvector — RDB·Vector 실험 공용
- `artifacts/oxigraph` 가 **cutoff 2026-08-24** 로 빌드돼 있어야 한다.
  구 빌드(07-11 cutoff, 08-24 릴리스 관계 573노드 누락)는 `artifacts/oxigraph.pre_0828_cutoff0711` 로 백업됨.
  재빌드: `kb.build_graph` 의 `CUTOFF` 를 `"2026-08-24"` 로 바꿔 `build()` (src 는 실험 중 미수정 — 그래프 노트북의 전제 셀 참고)
- `pyoxigraph` 설치: `python3 -m pip install --user --break-system-packages pyoxigraph`
- `.env` 의 CLOVA 키 (main·vector·integrated 노트북)
- `data/pdf_demo/` PDF 2개 (vector 실험 입력):
  - `국민참여형 국민성장펀드.pdf` → fund_pub `KR5153480100`
  - `미래에셋TIGERMSCIKOREATotalReturn증권상장지수투자신탁(주식).pdf` → etf_kr `KR7310970009`

## 계획 대비 변경점 (사유)

- **Azure Data API 미사용** (사용자 결정, 엔드포인트 2026-08-29 만료): Graph·RDB·Vector 전부 로컬.
  계획 §6 의 `tools.data_api.FinancialDataClient` 는 저장소에 구현이 없어, 같은 호출 형태를
  로컬 pgvector 로 구현해 `tools.data_api` 모듈로 등록했다 (vector 노트북 참고).
- Q05 의 RDB 후보 랭킹(IN-list)은 LogicalPlan compiler 미지원 — 실험에서는 read-only 직접 SQL,
  승격 시 binding `etf_kr.net_assets` 경로로 전환.
