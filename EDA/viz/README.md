# 온톨로지 시각화

`ontology/*.ttl` 5종(병합 2,511 트리플)을 인터랙티브 그래프 3종으로 만든 것. 리터럴·ObjectProperty는 노드로 만들지 않고 툴팁/엣지 라벨로만 쓴다.

| 파일 | 보여주는 것 | 노드/엣지 |
|---|---|---|
| `ontology_schema.html` | 클래스 49개만. 실선=`rdfs:subClassOf`, 점선 파랑=ObjectProperty `domain→range`(라벨이 속성명), 점선 빨강=`owl:disjointWith`. 색은 역할(상품/조직/분류축/n-ary/기타) | 49 / 79 |
| `ontology_domains.html` | 같은 클래스 그래프를 **선언 파일별 색**으로. 별 모양이 파일 허브, 회색 점선이 "이 파일이 선언" | 54 / 128 |
| `ontology_codelists.html` | 코드리스트 개체 297종을 소속 클래스별 블록으로 배치(테마 176 포함). physics 끄고 좌표 고정 | 323 / 297 |

여는 법: 파일을 브라우저로 열면 된다(더블클릭 또는 `explorer.exe ontology_schema.html`). vis-network JS가 인라인이라 오프라인에서도 동작한다(bootstrap CSS 2줄만 CDN이며 그래프 렌더에는 무관).

재생성: `python3 EDA/build_ontology_viz.py` — 끝에 자체 점검(클래스 49, `owl:unionOf` domain 전개, 파일 크기)이 붙어 있어 깨지면 assert로 죽는다.

의존성: `python3 -m pip install --user --break-system-packages rdflib pyvis` (networkx는 안 쓴다 — rdflib → pyvis 직결)
