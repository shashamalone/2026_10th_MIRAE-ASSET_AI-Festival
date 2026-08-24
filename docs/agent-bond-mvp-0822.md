# 채권 스키마 Vector DB + LangGraph MVP — 초도 브리핑

> 2026-08-21 · 구현 완료본. 이 문서 이전 버전은 구현 전 지시서였다.
> 지시서 원문은 저장소에 남아 있지 않다(`docs/`는 `.gitignore` 대상이 아니지만 아직 커밋 전이었고, 별도 사본이 없었다). 지시서의 조항이 필요한 경우 이 문서 §2와 §3이 그 내용을 인용해 담고 있다.

> **2026-08-22 갱신 — 벡터 저장소를 FAISS에서 PostgreSQL + pgvector로 이전했다.**
> 검색 결과는 이전 전후가 **완전히 동등**하다(동결 질의 72건 Top-5 순서 72/72 일치, score 최대 오차 0.00e+00).
> 아래 본문의 FAISS 관련 서술은 §8에 정리한 대체 관계를 함께 읽어야 한다.
> 인덱스에 넣는 용어는 **주석 보유 130건 그대로**다 — 코드리스트 91건을 넣어 본 실측은 §8-4에 있다.

---

## 0. 30초 요약

**무엇을 만들었나.** 채권 온톨로지(`.ttl` 파일)에 사람이 적어둔 **용어 설명**을 검색 가능한 형태로 바꿔 넣어두고, 사용자가 한국어로 질문하면 **관련 용어를 찾아 그 설명만 근거로 답변**하는 최소 파이프라인이다.

```text
"듀레이션은 뭐야?"
   ↓ ① 질문 분류      — 채권 질문인가? 용어를 묻는가?
   ↓ ② 용어 검색      — 130개 스키마 용어 중 관련된 것을 찾는다 (LLM 미사용)
   ↓ ③ 답변 생성      — 찾은 설명만 근거로 한국어 답변
"듀레이션은 채권의 금리 민감도를 나타내는 지표입니다…"
```


|            | 현황                                                                          |
| ---------- | --------------------------------------------------------------------------- |
| **되는 것**   | 4개 테스트 질문 전부 end-to-end 통과. 질문당 **3~6초**. "듀레이션"·"위험등급" 모두 **1순위 적중**       |
| **애매한 것**  | 답변이 **찾은 설명 밖으로 나가는 경우가 4문항 중 2문항**. 금융 상식으로는 맞는 말이지만 대회 규칙상 근거 없는 단정은 감점이다 |
| **안 하는 것** | 실제 채권 상품을 찾아주지 못한다. 이번 범위는 **용어 설명**까지다. 상품 검색은 다음 단계                       |
| **안 만든 것** | 외부에 노출할 API(`api.py`). 주최측 응답 규격이 4단계 작업이라 지금 만들면 두 번 짜게 된다 — §3-1          |


**한 줄로.** 파이프라인은 뚫렸고 검색 품질은 쓸 만하다. 남은 진짜 문제는 **답변이 근거를 벗어나는 것**이고, 그건 §6에 정리했다.

---

## 1. 무엇이 동작하는가

### 1-1. 실행 예시 (실측, 그대로 옮김)

```text
$ python3 script/test_bond_agent.py

==============================================================================
QUESTION  채권의 위험등급은 어떻게 정의돼?   [5.93s]
INTENT    BOND / SCHEMA_SEARCH  keywords=['채권', '위험등급']
TOP HITS
  1. 0.625  fp:riskGradeLevel            위험등급 수준
  2. 0.603  fp:RiskGrade                 투자위험등급
  3. 0.588  fp:hasRiskGrade              투자위험등급
  4. 0.549  fp:ratingStatus              신용등급 상태
  5. 0.545  fp:GovernmentBond            국공채
ANSWER
채권의 위험등급은 1부터 6까지의 숫자로 표현되며, 1은 최고위험, 6은 최저위험입니다.
이러한 위험등급은 채권뿐만 아니라 국내 ETF와 공모펀드에도 동일하게 적용됩니다.
또한, 명칭 체계는 다르지만 모든 도메인에서 코드 서열은 '1=최고위험'으로 일치합니다.

근거:
- term_uri: fp:riskGradeLevel (위험등급 수준)
- term_uri: fp:RiskGrade (투자위험등급)
```

이 답변은 검색된 두 용어의 주석 안에만 머물러 있다. **이것이 의도한 동작이다.** 4문항 중 2문항은 이 선을 넘는다(§6-1).

### 1-2. 실측 수치


| 항목                           | 값                                                                          | 확인 방법                                        |
| ---------------------------- | -------------------------------------------------------------------------- | -------------------------------------------- |
| end-to-end                   | **4문항 4/4 통과**                                                             | `python3 script/test_bond_agent.py`          |
| 질문당 소요                       | **3.29 ~ 5.93초** (재현 실행) / 최초 실측 3.9~8.9초                                  | 위 스크립트가 질문마다 출력                              |
| 스키마 인덱스                      | **130 resource × 1024차원**                                                  | `bond_kr.ttl` 39개 + `common.ttl` 91개         |
| 검색 방식                        | cosine 유사도 — **pgvector `<=>`** (08-22 이전 전: L2 정규화 후 FAISS `IndexFlatIP`) | `src/kb/build_bond_index.py`                 |
| 점수 하한                        | `0.45` 미만은 버림 → 노이즈 **4건 → 0건**                                            | §3-2 (1)                                     |
| `~~artifacts/bond.faiss~~`   | **삭제됨** → PostgreSQL `mafest.bond_schema_terms` 130행                       | §8                                           |
| `artifacts/bond_terms.json`  | 75 KB                                                                      | 측정 하네스용 교환 파일로 계속 생성. `vector_id`는 §8-2에서 제거 |
| `artifacts/embed_cache.json` | 1.54 MB (130건)                                                             |                                              |
| 모델 — intent                  | `HCX-DASH-002`                                                             | 분류 전용. 실측 0.29초로 가장 빠름                       |
| 모델 — answer                  | `HCX-005`                                                                  |                                              |
| 모델 — embedding               | `bge-m3` (1024차원)                                                          | CLOVA Studio                                 |


---

## 2. 완료조건 점검

지시서 §15의 10개 항목이다.


| #   | 완료조건                                                                 | 판정       | 근거                                                              |
| --- | -------------------------------------------------------------------- | :--------: | --------------------------------------------------------------- |
| 1   | 채권 TTL에서 `rdfs:label`·`rdfs:comment`를 읽을 수 있다                        | **PASS** | `src/kb/build_bond_index.py:collect()`. 한국어 리터럴 우선(`pick()`)    |
| 2   | resource별 검색용 text가 생성된다                                             | **PASS** | `URI | label | comment` 형식, resource 1개 = vector 1개             |
| 3   | CLOVA `bge-m3` embedding이 생성된다                                       | **PASS** | 130건 × 1024차원                                                   |
| 4   | `~~artifacts/bond.faiss`가 생성된다~~ → `**bond_schema_terms` 테이블에 적재된다** | **PASS** | 130행 × 1024차원, NULL 0 (08-22 이전)                                |
| 5   | `artifacts/bond_terms.json`이 생성된다                                    | **PASS** | 75 KB. `vector_id` 제거 — `term_uri`가 PK다                         |
| 6   | `bond_schema_search()`가 Top-K를 반환한다                                  | **PASS** | `src/tools/bond_schema.py`. 단 하한 미달은 K를 억지로 채우지 않는다             |
| 7   | `classify_intent`가 `BOND / SCHEMA_SEARCH`를 반환할 수 있다                  | **PASS** | "반환할 수 있다"는 충족(4건 중 2건). **다만 항상 그렇지는 않다** → §6-2               |
| 8   | LangGraph가 `classify_intent → search_bond_schema → answer` 순서로 실행된다  | **PASS** | `src/agent/agent_core.py`. 분기 없는 직선                             |
| 9   | 최종 답변이 검색된 comment를 **근거로** 생성된다                                     | **부분**   | 4문항 중 **2문항이 comment 밖 문장을 생성**한다. 프롬프트로 금지했는데도 지켜지지 않는다 → §6-1 |
| 10  | `script/test_bond_agent.py`로 end-to-end 실행 가능하다                      | **PASS** | 위 §1-1                                                          |


**9 PASS / 1 부분.** 유일한 미달인 9번이 이 MVP에서 가장 중요한 항목이라는 점을 숨기지 않는다. 파이프라인이 도는 것과 답변이 신뢰 가능한 것은 다른 문제이고, 후자가 아직 안 끝났다.

---

## 3. 지시서와 달라진 것

### 3-1. 지시서대로 하지 못한 것 (3건)

#### (1) Action 1 "기존 구현을 최대한 재사용한다" — 재사용할 것이 없었다

지시서 Action 1은 `agent/`·`tools/`·`kb/`·`clova.py`·`config.py`·`api.py`의 **현재 구현 상태를 읽고 재사용하라**고 지시한다. 확인 결과 **이 중 하나도 존재하지 않았다.** git 이력에도 없다(`git log --all -- agent/ tools/ kb/ clova.py config.py api.py` → 결과 없음).

**결과:** 전부 신규 생성. 재사용한 것은 딱 하나, `script/test_clova.py`에서 검증된 CLOVA 호출 코드다(§3-2 (4)).

**왜 중요한가:** 지시서가 가정한 "기존 코드에 얹기"가 아니라 "바닥부터"였다는 뜻이고, 따라서 이 코드에는 아직 다른 도메인(ETF·펀드·주식)과 공유하기 위한 추상화가 **일부러** 없다. 두 번째 도메인이 붙을 때 공통부를 뽑는 것이 맞다.

#### (2) `ontology/bond.ttl` → `bond_kr.ttl` + `common.ttl` 두 개

지시서는 채권 TTL이 `ontology/bond.ttl` **하나**라고 가정한다. 이 저장소의 실제 스키마는 `**common.ttl` + 도메인 4개**(`bond_kr`·`etf_kr`·`etf_gl`·`fund_pub`)로 갈려 있고 `bond.ttl`이라는 파일은 없다.

`bond_kr.ttl` 하나만 넣으면 안 되는 구체적 이유:


| 테스트 질문               | 필요한 용어                              | 어디에 있나             |
| -------------------- | ----------------------------------- | ------------------ |
| "채권의 위험등급은 어떻게 정의돼?" | `fp:RiskGrade`, `fp:riskGradeLevel` | `**common.ttl`에만** |


`bond_kr.ttl`은 12행 주석에서 *"공통 클래스·관계(fp:Product, fp:issuedBy, fp:CreditRating, fp:RiskGrade 등)는 common.ttl에 있다"* 라고 명시적으로 넘긴다. 즉 `bond_kr.ttl`만 인덱싱하면 **테스트 4문항 중 1문항을 구조적으로 못 답한다.**

**결과:** `config.BOND_TTL_PATHS`를 리스트로 두고 둘 다 파싱한다. 주석 있는 fp: resource는 `bond_kr.ttl` 39개 + `common.ttl` 91개 = **130개**.

#### (3) `api.py`는 만들지 않았다

지시서 §11과 §2 파일 구조에 `api.py`가 등장하지만, **§15 완료조건 10개에는 없다.** 그리고 주최측 응답 규격은 이미 확정돼 있다 — `question_id`·`question`·`retrieved_context`·`think_trace`·`answer` **5필드 고정**(`docs/spec_0818.md:277`, 과제설명 PDF p11 인용).

지시서 §11이 제시한 예시 응답은 이 규격과 다르다(`intent` 필드가 있고 `question_id`·`think_trace`가 없다). 지금 지시서 예시대로 만들면 **4단계 Answer Generator에서 규격을 두 번 짜게 된다.** `docs/WBS_BOND.md`도 이 매핑(BOND-P5)을 4단계 소관으로 배정하고 있다.

**결과:** 미생성. `requirements.txt`에 `fastapi`·`uvicorn`은 이미 들어 있으므로, 규격이 확정된 시점에 얇은 래퍼 하나만 얹으면 된다. 현재 진입점은 `agent.agent_core.ask(question) -> dict`이고 이 dict가 5필드의 원재료를 전부 담고 있다.

### 3-2. 지시서에 없지만 추가한 것 (4건)

#### (1) 점수 하한 `BOND_SCORE_FLOOR = 0.45`

지시서 §5는 무조건 Top-K를 반환하라고 한다. 그렇게 두면 관련 없는 용어가 답변 컨텍스트에 섞여 들어간다. **실측:**

```text
Q: "듀레이션은 뭐야?"
 하한 없음(floor=0.0):          하한 적용(floor=0.45):
   0.501  fp:duration              0.501  fp:duration
   0.383  fp:subsidiaryOf        ← 자회사 관계. 채권과 무관
   0.368  fp:SubsidiaryRelation  ← 출자관계. 채권과 무관
   0.364  fp:RatingBand
   0.361  fp:hasCreditRating
```

**왜 버려야 하나:** 단순히 지저분해서가 아니다. **빈약하거나 엉뚱한 근거를 받으면 모델이 그 빈틈을 자기 일반 지식으로 메운다.** 근거를 적게 주는 쪽이 근거 아닌 것을 주는 쪽보다 낫다 — 적으면 "부족하다"고 말할 수 있지만, 엉뚱한 것이 섞이면 모델이 그걸 근거 삼아 이야기를 만든다.

**결과:** 노이즈 4건 → 0건. `bond_schema_search()`는 하한 미달일 때 **K를 억지로 채우지 않고** 짧은 리스트를 반환한다. 전부 미달이면 빈 리스트이고, `answer` 노드가 *"관련 항목을 찾지 못했습니다"* 로 정직하게 끝낸다.

> `0.45`는 130건 규모에서 실측으로 고른 값이다. 인덱스가 커지거나 임베딩 모델이 바뀌면 다시 재봐야 한다. `src/config.py` 한 줄이라 조정은 쉽다.

#### (2) 임베딩 캐시 + 429 백오프 (`src/clova.py:embed_many`)

CLOVA 임베딩에는 **분당 쿼터**가 있다. 실측상 **약 60건 연속 호출이면 차단**된다. langchain의 `embed_documents`는 지연 없이 연속 호출하기 때문에 130건 빌드에서 **두 번 연속 실패**했고, 더 나쁜 것은 실패할 때마다 **앞서 성공한 호출이 통째로 버려졌다**는 점이다. 130건을 다시 부르면 다시 차단된다.

**결과 — 세 겹:**


| 장치      | 값                            | 효과                          |
| ------- | ---------------------------- | --------------------------- |
| 호출 간격   | `1.2s` (≈50건/분)              | 쿼터에 안 닿는다                   |
| 429 백오프 | 지수, 최대 65초, 7회               | 분 단위 쿼터라 한 번은 분을 넘겨 기다려야 한다 |
| 디스크 캐시  | `artifacts/embed_cache.json` | 실패해도 진행분이 남는다. 20건마다 중간 저장  |


캐시 키는 `sha1(모델명 + 텍스트)`라 **주석을 고친 resource만 다시 호출**된다. TTL 주석은 앞으로 계속 손볼 예정이라 재빌드가 반복되는데, 캐시 덕에 두 번째 빌드부터는 사실상 즉시 끝난다.

#### (3) `skos:altLabel`을 검색 텍스트에 포함 — ⚠ **현재 인덱스에서는 효과 없음**

`src/kb/build_bond_index.py:53-55`가 `skos:altLabel`을 검색 텍스트에 붙인다. 의도는 사용자가 쓰는 말과 스키마 라벨이 다른 경우를 잡는 것이다.

**그런데 실측 결과 현재 인덱스에서는 한 건도 동작하지 않는다:**


| 집합                                         | 개수    |
| ------------------------------------------ | ----- |
| `rdfs:comment`를 가진 fp: resource (= 인덱싱 대상) | 130   |
| `skos:altLabel`을 가진 fp: resource           | 37    |
| **교집합**                                    | **0** |


`bond_terms.json`의 130건 전부 `alt_labels: []`이다. 이유는 구조적이다 — `altLabel`은 코드리스트 **개체**(`fp:RiskGrade_1`, `fp:AssetType_Bond`, `fp:RatingBand_NotRated` …)에 붙어 있는데 이들에겐 `rdfs:comment`가 없고, `comment`를 가진 클래스·프로퍼티에는 `altLabel`이 없다.

`fp:RatingBand_NotRated`는 실제로 `rdfs:label "무등급"@ko, "NotRated"@en`을 갖는다 — 한국어 라벨이 **이미 "무등급"이고**, `altLabel`이 아니라 `label`이며, `comment`가 없어 애초에 인덱싱되지 않는다.

**판단:** 코드는 남겨둔다(3줄이고, 앞으로 개체에 `comment`를 달거나 클래스에 `altLabel`을 달면 즉시 동작한다). 다만 **"동의어 검색이 된다"고 믿으면 안 된다.** 코드리스트 개체까지 검색하려면 인덱싱 조건(`comment` 필수)을 바꾸는 별도 결정이 필요하고, 그건 이번 범위가 아니다.

#### (4) `clova.py`를 `script/test_clova.py`에서 승격

CLOVA 호출 규격은 콘솔 샘플과 세 군데가 다르고(§5), 그 세 가지를 이미 `script/test_clova.py`가 실측으로 알아내 담고 있었다. 여기서 복제하면 **같은 규격 지식이 두 곳에 생기고, 한쪽만 고쳤을 때 조용히 어긋난다** — 그 어긋남은 런타임 `40001`로만 드러나서 찾기 어렵다.

**결과:** 최상위 `clova.py`로 승격하고 `agent/`·`tools/`·`kb/` 전부가 이것 하나를 쓴다(08-22 `src/` 이전 후 현재 위치는 `src/clova.py`). `script/test_clova.py`는 규격 탐색 기록으로 그대로 둔다.

---

## 4. 파일별 역할

src/       = 실행·빌드 로직

data/      = 실제 데이터

ontology/  = 의미 모델

metadata/  = 의미 ↔ 물리 스키마 연결정보

artifacts/ = 빌드 결과

script/    = 실행/검증

docs/      = 명세/실험 기록

```text
<저장소 루트>
├── src/                               런타임 코드. 08-22 src/ 이전 (docs/spec_0818.md:374)
│   ├── src/agent/
│   │   ├── agent_core.py              LangGraph 조립 + 진입점 ask()
│   │   ├── nodes.py                   노드 3종 + 프롬프트 2종
│   │   └── state.py                   노드 간에 오가는 데이터 형태
│   ├── src/tools/
│   │   └── bond_schema.py             벡터 검색 (LLM 미사용)
│   ├── src/kb/
│   │   └── build_bond_index.py        TTL → pgvector 적재 (오프라인, 1회)
│   ├── clova.py                       CLOVA Studio 클라이언트 (chat + embedding)
│   ├── config.py                      경로·모델·임계값 상수
│   └── api.py                         ← 미생성 (§3-1 (3))
├── artifacts/                         ← .gitignore 대상. 전부 재생성 가능
│   ├── (bond.faiss 삭제)              벡터는 PostgreSQL mafest.bond_schema_terms
│   ├── bond_terms.json                벡터 ↔ 용어 대응표
│   └── embed_cache.json               임베딩 캐시 (지시서 트리에 없던 것)
├── ontology/
│   ├── bond_kr.ttl                    채권 전용 스키마 (39)  ← 지시서의 bond.ttl에서 변경
│   └── common.ttl                     4개 도메인 공통 스키마 (91)  ← 추가
└── script/
    └── test_bond_agent.py             end-to-end 실행 확인
```

> `**artifacts/`가 `.gitignore`에 있는 이유:** 세 파일 모두 `ontology/*.ttl`에서 **재생성 가능한 산출물**이기 때문이다. 커밋하면 TTL을 고칠 때마다 1.5 MB짜리 바이너리 diff가 따라붙는다. 새로 받은 사람은 `python3 src/kb/build_bond_index.py` 한 번을 돌리면 된다(§7).

---

### `src/config.py` — 25행

- **한 줄 역할:** 경로·모델명·임계값이 코드 곳곳에 흩어지지 않도록 한곳에 모은 상수 파일. **값을 바꾸고 싶으면 여기부터 본다.**
- **입력 → 출력:** 없음(상수만). `ROOT`는 자기 파일 위치 기준이라 어느 디렉터리에서 실행해도 경로가 맞는다.
- **핵심 상수:** `BOND_TTL_PATHS`(리스트 — §3-1 (2)) · `BOND_DSN`·`BOND_TABLE`(08-22 이전, 구 `BOND_INDEX_PATH`·`BOND_TERMS_PATH` 대체) · `BOND_TOP_K=5` · `BOND_SCORE_FLOOR=0.45` · `EMBEDDING_MODEL="bge-m3"` · `INTENT_MODEL="HCX-DASH-002"` · `ANSWER_MODEL="HCX-005"` · `CLOVA_HOST`
- **주의점:** `BOND_TTL_PATHS`나 `EMBEDDING_MODEL`을 바꾸면 **인덱스를 반드시 재빌드**해야 한다. pgvector 이전 후에는 테이블이 단일 원본이라 파일 두 개가 어긋날 여지 자체가 없어졌다(구 `_load()`의 개수 불일치 검사도 함께 사라졌다). 대신 **재빌드를 안 하면 옛 임베딩이 그대로 남는다** — `DROP TABLE` 후 재생성이므로 빌더를 돌리기만 하면 된다.
- **접속 정보는 환경변수로 덮을 수 있다**(`PGHOST`·`PGPORT`·`PGUSER`·`PGPASSWORD`·`PGDATABASE`). 기본값은 `127.0.0.1:5432 / postgres / mafest`다. 유닉스 소켓은 peer 인증에 걸리므로 host를 반드시 명시한다.

### `src/clova.py` — 171행

- **한 줄 역할:** CLOVA Studio(HyperCLOVA X)에 말을 거는 유일한 창구. **채팅**(질문→답변)과 **임베딩**(텍스트→숫자 벡터) 둘 다 여기 있다.
- **입력 → 출력:**
  - `chat(model, system, user, …)` → 모델 응답 **문자열**
  - `embed(text)` → **1024개 실수 리스트**
  - `embed_many(texts)` → 리스트의 리스트 (+ `artifacts/embed_cache.json` 갱신)
- **핵심 함수:**
  - `load_key()` / `key()` — `.env`의 `clova` 키를 1회만 읽어 캐시. **키 값은 절대 로그에 남기지 않는다**
  - `chat()` — 모델이 추론형(`HCX-007`)인지에 따라 요청 바디를 다르게 만든다(§5)
  - `parse_json_loose()` — 모델이 코드펜스나 설명을 붙여도 JSON 객체만 추출
  - `embed_many()` — 간격 1.2초 + 429 지수 백오프 + 디스크 캐시(§3-2 (2))
- **주의점:**
  - `.env`가 없거나 `clova` 항목이 비면 **즉시 `sys.exit`** 한다. 키 없이 돌다가 401로 죽는 것보다 시작할 때 죽는 편이 낫다.
  - HTTP 오류 시 응답 본문 앞 220자를 예외 메시지에 **그대로 싣는다.** CLOVA의 `40001`은 어느 파라미터가 문제인지 본문에만 적혀 있어서, 삼키면 원인을 못 찾는다.
  - `REASONING_MODELS = {"HCX-007"}`는 **하드코딩된 목록**이다. 추론 모델이 추가되면 여기에 넣어야 한다.

### `src/kb/build_bond_index.py` — 85행

- **한 줄 역할:** 온톨로지 TTL을 읽어 **검색용 벡터 인덱스를 만드는 오프라인 빌더.** 평소엔 안 돌고, TTL을 고쳤을 때만 돌린다.
- **입력 → 출력:** `ontology/bond_kr.ttl` + `ontology/common.ttl` → PostgreSQL `bond_schema_terms` 테이블 + `artifacts/bond_terms.json`(측정 하네스용 교환 파일)
- **핵심 함수:**
  - `pick(g, s, prop)` — 같은 프로퍼티에 `@ko`/`@en`이 둘 다 있으면 **한국어 우선**. 질문이 한국어라 한국어 라벨이 붙어야 검색이 맞는다
  - `collect()` — `**rdfs:comment`가 있는** `fp:` resource를 **URI 정렬 순서로** 모은다(130건)
  - `main()` — `embed_many` → `DROP TABLE` → `CREATE` → `INSERT ... ::vector` → 적재 검증(행수·차원·NULL)
- **주의점:**
  - `**rdfs:comment`가 없는 resource는 넣지 않는다.** 답변 단계(`src/agent/nodes.py`)가 *"comment 안에 적힌 문장만 근거로 삼는다"* 고 규정하므로, 주석 없는 용어는 검색에 걸려도 근거로 못 쓰고 Top-K 슬롯만 차지한다. 코드리스트 개체 91건을 넣어 본 실측 결과는 **§8-4**에 있다(Top-1 −9, 근거 커버리지 100%→68.6%).
  - `**vector_id`는 제거했다.** 위치가 곧 식별자였던 FAISS와 달리 pgvector는 `term_uri`가 PK다. 재빌드로 정렬 순서가 바뀌어도 검색 결과가 흔들리지 않는다.
  - 검색 단위는 **resource 1개 = vector 1개**. TTL을 일반 문서처럼 chunking하지 않는다.
  - 130건 규모에서는 플래너가 **Seq Scan**을 고르고 그게 정상이다. HNSW 인덱스는 지금 만들어도 의미가 없다 — 수만 건이 되면 그때 `m`·`ef_construction`과 `maintenance_work_mem`을 함께 봐야 한다.

### `src/tools/bond_schema.py` — 50행

- **한 줄 역할:** 질문 문장을 받아 **관련된 스키마 용어 Top-K를 돌려주는 검색 함수.** LangGraph와 무관하게 단독으로도 쓸 수 있다.
- **입력 → 출력:** 질문 문자열 → `[{term_uri, label, comment, score}, …]` (`score`는 cosine, 1에 가까울수록 유사)
- **핵심 함수:**
  - `_conn()` — `@lru_cache(maxsize=1)`. DB 접속을 **프로세스당 한 번만** 연다. 비어 있으면 `SystemExit`로 빌드를 안내한다
  - `bond_schema_search(text, k, floor)` — 임베딩 → `ORDER BY embedding <=> %s::vector LIMIT k` → 하한 필터. **시그니처·반환 형식은 FAISS 때와 동일하다**
- **주의점:**
  - **캐싱이 성능상 필수다.** 매 검색마다 다시 읽으면 질의 하나에 수백 ms가 붙어 응답 예산(60초 권장, 15초 목표)을 갉아먹는다.
  - **자르는 순서가 결과를 바꾼다.** `k`를 먼저 뽑고 그 다음 `floor`로 거른다. `floor`를 SQL `WHERE`로 내리면 하한을 넘는 것 중 상위 k개가 나와 결과가 더 많아진다. 이전 동등성을 위해 FAISS 때의 순서를 그대로 옮겼다 — **다만 이 순서 자체는 알려진 결함이다**(근거 없는 용어가 슬롯을 먼저 차지할 수 있다, §8-4).
  - `%s::vector` **캐스팅이 필수다.** `register_vector`는 numpy 배열만 변환하는데 `clova.embed()`는 순수 list를 준다. 빠뜨리면 `float8[]`로 나가 연산자를 못 찾는다.
  - **하한 미달이면 K를 채우지 않는다.** 반환 개수가 0~K 사이로 변하니 호출부는 빈 리스트를 반드시 처리해야 한다(`src/agent/nodes.py:answer`가 처리한다).
  - **매 호출마다 CLOVA 임베딩 API를 1회 부른다.** 질문 임베딩은 캐시되지 않는다(같은 질문이 반복될 일이 없어서). 응답 시간 3~6초의 한 조각이 여기다.

### `src/agent/state.py` — 10행

- **한 줄 역할:** 노드들이 주고받는 **데이터 상자의 모양** 정의. LangGraph가 이 형태로 상태를 넘긴다.
- **입력 → 출력:** 없음(타입 선언만).
- **핵심 클래스:** `State(TypedDict)` — `question: str` / `intent: dict` / `schema_hits: list` / `answer: str`
- **주의점:** 지시서 §7이 정한 최소 4필드 그대로다. `think_trace` 같은 주최측 규격 필드는 **일부러 넣지 않았다** — 규격 확정이 4단계 작업이라(§3-1 (3)) 지금 넣으면 두 번 고친다.

### `src/agent/nodes.py` — 65행

- **한 줄 역할:** 파이프라인 **3단계 각각의 실제 동작**. 그리고 LLM에게 주는 **지시문(프롬프트) 2개**가 여기 있다. 답변 품질을 손보려면 대개 이 파일이다.
- **입력 → 출력:** 각 함수가 `State`를 받아 **바뀐 필드만 담은 dict**를 반환한다(LangGraph가 병합).
  - `classify_intent` : `question` → `{"intent": {...}}`
  - `search_bond_schema` : `question` → `{"schema_hits": [...]}`
  - `answer` : `question` + `schema_hits` → `{"answer": "..."}`
- **핵심 함수·상수:**
  - `INTENT_SYSTEM` — 분류 지시문. `domain`(BOND/ETF/FUND/OTHER) × `intent`(SCHEMA_SEARCH/DATA_SEARCH) + `keywords`
  - `ANSWER_SYSTEM` — 답변 지시문. **"comment 안에 적힌 문장만 근거로 삼는다"**, "일반 지식은 쓰지 마라", "부족하면 부족하다고 말한다", "투자 추천 금지", "근거 term_uri 나열", "3~5문장"
  - `_context(hits)` — 검색 결과를 `[1] term_uri / label / comment` 블록으로 직렬화
- **주의점:**
  - `**classify_intent`는 실패해도 파이프라인을 세우지 않는다.** 예외를 잡아 기본값(`BOND`/`SCHEMA_SEARCH`)으로 넘기고 `intent["error"]`에 사유를 남긴다. 분류가 없어도 검색은 질문 원문으로 되기 때문이다. **테스트 출력에 `⚠`가 보이면 분류가 죽은 것**이니 그냥 넘기지 말 것.
  - `_context()`는 `**score`를 LLM에 넘기지 않는다.** 숫자를 주면 모델이 "유사도 0.5니까 확실하다" 식으로 근거 삼을 여지가 생긴다.
  - `**ANSWER_SYSTEM`의 금지 조항이 실제로는 지켜지지 않는다(4건 중 2건).** 프롬프트를 더 세게 쓰는 것으로는 해결되지 않았다 — §6-1.
  - `intent` 결과는 **현재 어떤 분기에도 쓰이지 않는다.** 그래프가 직선이라 기록용이다(지시서 §10이 분기 금지).

### `src/agent/agent_core.py` — 25행

- **한 줄 역할:** 세 노드를 **순서대로 잇고**, 바깥에서 부를 함수 하나(`ask`)를 제공한다. 이 시스템의 정문이다.
- **입력 → 출력:** `ask("듀레이션은 뭐야?")` → `{"question","intent","schema_hits","answer"}` dict
- **핵심 함수:** `build()` — `StateGraph(State)`에 노드 3개와 `START → classify_intent → search_bond_schema → answer → END` 간선을 걸고 `compile()`. `APP` — 모듈 로드 시 1회 컴파일. `ask(question)` — `APP.invoke()` 래퍼
- **주의점:**
  - `**APP`이 import 시점에 만들어진다.** 그래프 컴파일은 가볍지만, `import agent.agent_core` 자체가 `tools.bond_schema` → `psycopg`·`clova`를 끌어온다. DB 접속은 첫 검색까지 지연된다(`_conn()`이 `lru_cache`라).
  - **분기가 없다.** ETF 질문을 넣어도 채권 인덱스를 검색한다. 도메인 라우팅은 다음 단계 작업이다.
  - `api.py`가 붙을 자리가 여기다 — `ask()`의 반환 dict가 주최측 5필드의 원재료를 전부 담고 있다.

### `script/test_bond_agent.py` — 30행

- **한 줄 역할:** 지시서 §8이 정한 **테스트 질문 4개를 순서대로 돌려** 분류·검색·답변을 눈으로 확인하는 스크립트.
- **입력 → 출력:** 없음(질문이 파일에 하드코딩) → 표준출력에 질문별 `QUESTION`(+소요초) / `INTENT` / `TOP HITS` / `ANSWER`
- **핵심 상수:** `QUESTIONS` — 위험등급 정의 / 듀레이션 정의 / 듀레이션 해석 / 금리위험. **네 번째는 스키마에 직접 대응 용어가 없는 질문이라 "근거 부족"을 말하는지 보는 용도다.**
- **주의점:**
  - **pass/fail 판정을 하지 않는다.** 통과 여부는 사람이 출력을 읽고 정한다. 답변 품질이 자연어라 자동 판정이 어려워서인데, 뒤집으면 **CI에 걸 수 없다.** §6-1의 답변 검증 노드가 생기면 그때 자동화 대상이 된다.
  - **매 실행이 CLOVA API를 8회 부른다**(질문 4 × 분류·임베딩·답변). 무료가 아니고 쿼터도 쓴다.

### `src/api.py` — **미생성**

- **왜 없나:** 지시서 §15 완료조건에 없고, 주최측 응답 규격(`question_id`·`question`·`retrieved_context`·`think_trace`·`answer` 5필드 고정)은 **4단계 Answer Generator 소관**이다. 지시서 §11의 예시 응답은 이 규격과 달라서, 그대로 만들면 규격을 두 번 짜게 된다. 상세는 §3-1 (3).
- **붙일 때:** `requirements.txt`에 `fastapi`·`uvicorn`이 이미 있다. `agent.agent_core.ask()`를 감싸 5필드로 직렬화하는 얇은 래퍼면 된다.

---

## 5. CLOVA API 주의사항

**CLOVA 콘솔이 주는 샘플 코드를 그대로 쓰면 동작하지 않는다.** 세 군데가 다르고, 셋 다 실측으로 알아낸 것이다. 이어받는 사람이 같은 곳에서 시간을 쓰지 않도록 적는다. 구현은 전부 `src/clova.py:chat()`에 있다.


| #   | 콘솔 샘플                       | 실제로 필요한 것                                                                     | 안 고치면                                                                                                                               |
| --- | --------------------------- | ----------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `Accept: text/event-stream` | `**Accept: application/json**`                                                | 응답이 SSE 스트림으로 와서 **값으로 받을 수 없다.** LangGraph 노드는 `return`으로 값을 넘겨야 하므로 노드 자체가 성립하지 않는다. 비스트리밍 응답은 `result.message.content`에 들어온다     |
| 2   | `maxTokens`                 | 추론 모델(`HCX-007`)은 `**maxCompletionTokens**`                                   | `**40001 Invalid parameter`.** 값 범위 문제로 착각하기 쉬운데 **파라미터 이름이 다른 것**이다 — `maxTokens=4096`으로 낮춰도 똑같이 거부된다. 비추론 모델은 반대로 `maxTokens`를 쓴다 |
| 3   | (`thinking` 미언급)            | `HCX-007` + structured outputs면 `**thinking: {"effort": "none"}`으로 명시적으로 끈다** | `HCX-007`은 thinking이 **기본 ON**이라 `responseFormat`과 충돌한다. `**"off"`는 무효값이고 `"none"`만 받는다.** 부수 효과로 응답이 **4.69초 → 1.3초**로 줄었다         |


### 추가로 알아둘 것

- **v3는 응답 `content`가 문자열일 수도 배열일 수도 있다.** 입력이 `[{"type":"text","text":…}]` 배열 형식이라 출력도 배열로 오는 경우가 있다. `chat()`이 양쪽을 처리한다.
- **HTTP 200이어도 실패일 수 있다.** 본문의 `status.code`가 `"20000"`이 아니면 오류다. `chat()`이 이것도 검사한다.
- **임베딩에는 분당 쿼터가 있다.** 약 60건 연속이면 차단. 대량 임베딩은 반드시 `embed_many()`를 쓸 것 — 직접 `embed()`를 루프로 돌리면 막힌다(§3-2 (2)).
- `**.env`의 키 형식은 유연하다.** `Bearer`  접두가 있든 없든 `load_key()`가 맞춰준다. 따옴표도 벗긴다.

---

## 6. 남은 문제

두 건이고, 둘 다 **프롬프트만으로는 해결되지 않는다는 것이 실측으로 확인됐다.** 둘 다 같은 성질의 문제다 — LLM에게 말로 부탁한 제약은 지켜지지 않는다.

### 6-1. 환각 — 4문항 중 2문항 (**우선순위 최상**)

**무엇이 문제인가.** 답변이 검색된 주석 밖으로 나간다. 지시서 §15의 *"최종 답변이 검색된 comment를 근거로 생성된다"* 가 부분 미달인 이유다.

**실측 사례 — "듀레이션이 길면 어떤 의미야?"**


|                       | 내용                                                                                                                                              |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `fp:duration` 주석 (전부) | "금리 민감도. **0이 8,268건이며 만기경과와 미계산이 섞여 있으므로 듀레이션 질의 시 0 제외가 필수**다. 익일 계열(NDY_DUR)과 컨벡시티는 중복·고급축이라 온톨로지에 싣지 않았다."                                  |
| 실제 답변                 | "…**제공된 스키마에서는 듀레이션이 금리와 반비례 관계임을 명시하고 있으며**, 듀레이션이 길수록 금리 변화에 더 민감하게 반응한다고 설명합니다. 따라서, 듀레이션이 긴 채권은 금리 상승 시 가격 하락 폭이 크고, 금리 하락 시 가격 상승 폭도 큽니다." |


주석에 있는 것은 **"금리 민감도"** 다섯 글자뿐이다. 나머지는 전부 모델의 일반 지식이다. 금융 상식으로는 맞는 말이지만 **대회 규칙상 "근거 없는 단정"은 감점 직결**이다(과제설명 p7, `docs/WBS_BOND.md` BOND-P1).

> **주목할 점:** 모델은 단순히 지식을 덧붙인 게 아니라 **"제공된 스키마에서는 … 명시하고 있으며"라고 근거를 허위 귀속했다.** 없는 내용을 스키마가 말했다고 주장하는 것이라 단순 확장보다 나쁘다. 네 번째 질문("채권 금리위험이 뭐야?")은 *"제공된 스키마에는 직접적인 설명은 없지만"* 이라고 인정한 뒤에도 일반 지식을 이어 붙였다.

**이미 해본 것:** `ANSWER_SYSTEM`에 *"네가 알고 있는 금융 일반 지식은 쓰지 마라. comment에 없으면 없는 것이다"* 를 넣고, 심지어 **이 듀레이션 사례를 예시로 명시**했다(`src/agent/nodes.py:26`). `HCX-005`가 지키지 않는다.

**해결 후보 3가지:**


| 방안                                 | 방법                                                                                    | 비용                                            | 비고                                   |
| ---------------------------------- | ------------------------------------------------------------------------------------- | --------------------------------------------- | ------------------------------------ |
| **답변 검증 노드**                       | `answer` 뒤에 노드를 하나 더 두고, 답변 각 문장이 `schema_hits`의 comment로 뒷받침되는지 검사. 미달 문장은 삭제하거나 재생성 | LLM 호출 1회 추가 (+2~3초)                          | 가장 확실. 응답 예산(15초 목표) 안에 들어간다         |
| `**HCX-007` + structured outputs** | 답변을 `{문장, 근거 term_uri}` 배열로 강제해 **문장마다 근거를 달게** 한다. 근거를 못 대는 문장은 애초에 만들 수 없다          | 모델 변경. `thinking:{"effort":"none"}` 필수(§5 #3) | 구조로 막는 방식이라 프롬프트보다 견고                |
| **few-shot**                       | "주석에 없으면 이렇게 답한다"는 예시를 프롬프트에 2~3개 넣는다                                                 | 가장 쌈                                          | 지시문 단독이 실패했으므로 **먼저 이것부터 시도**해 볼 만하다 |


### 6-2. intent enum 미준수 — 4건 중 2건

**무엇이 문제인가.** `INTENT_SYSTEM`은 `intent` 값으로 `SCHEMA_SEARCH` 또는 `DATA_SEARCH`만 쓰라고 지정한다. 실제로는 절반이 자유 문자열로 나온다.


| 질문                 | 반환된 `intent`    | 규격 준수 |
| ------------------ | --------------- | :-----: |
| 채권의 위험등급은 어떻게 정의돼? | `SCHEMA_SEARCH` | ○     |
| 듀레이션은 뭐야?          | `SCHEMA_SEARCH` | ○     |
| 듀레이션이 길면 어떤 의미야?   | `"용어정의"`        | ✗     |
| 채권 금리위험이 뭐야?       | `"용어 검색"`       | ✗     |


`domain`은 4건 모두 `BOND`로 정확했다. 어긋나는 것은 `intent`뿐이다.

**왜 지금은 안 터지나:** 그래프가 직선이라 `intent`가 **어떤 분기에도 쓰이지 않는다**(기록용). 하지만 **도메인·의도 라우팅이 붙는 순간 조용히 오라우팅된다** — 자유 문자열은 어느 분기 조건에도 안 맞아 기본 경로로 흘러가고, 로그를 봐도 정상처럼 보인다.

**해결 후보 2가지:**

1. **후처리 가드** — 값이 enum에 없으면 `SCHEMA_SEARCH`로 강제하고 원본을 `intent["raw"]`에 남긴다. 몇 줄이고 LLM 호출이 늘지 않는다. **분기가 붙기 전까지는 이것으로 충분하다.**
2. **structured outputs** — `responseFormat`으로 enum을 스키마에 박는다. 확실하지만 `HCX-DASH-002`의 지원 여부 확인이 필요하고, 지원하더라도 분류 속도(0.29초)를 잃을 수 있다.

---

## 7. 실행 방법

### 사전 준비

```bash
python3 -m pip install -r requirements.txt
```

`.env`에 CLOVA Studio 키가 있어야 한다. 없으면 시작 시점에 바로 죽는다.

```text
clova=<API 키>
```

> 키는 `Bearer`  접두가 있어도 없어도 되고, 따옴표도 자동으로 벗겨진다.

**PostgreSQL + pgvector가 떠 있어야 한다**(08-22 이전 이후). 실측 환경은 PostgreSQL 18.6 / pgvector 0.8.1이다.

```bash
sudo apt install -y postgresql-18 postgresql-18-pgvector
sudo service postgresql start
createdb -h 127.0.0.1 -U postgres mafest        # 최초 1회
```

접속 기본값은 `127.0.0.1:5432 / postgres / mafest`이고 `PGHOST`·`PGPORT`·`PGUSER`·`PGPASSWORD`·`PGDATABASE`로 덮을 수 있다.
**유닉스 소켓으로 붙으면 `Peer authentication failed`가 난다** — host를 명시해 TCP로 붙어야 한다.

### 1단계 — 인덱스 빌드 (최초 1회, TTL을 고쳤을 때 재실행)

```bash
python3 src/kb/build_bond_index.py
```

기대 출력:

```text
resource 130개 수집 (bond_kr.ttl, common.ttl)
  임베딩 완료 — API 호출 130건 / 캐시 재사용 0건
  bond_schema_terms    130행 × 1024차원  (NULL 0)
  bond_terms.json      75KB
소요 ...s
```

- **최초 빌드는 3분쯤 걸린다.** 분당 쿼터 때문에 호출 간격이 1.2초다(§3-2 (2)). 중간에 `429 — Ns 대기` 가 찍혀도 정상이니 기다린다.
- **두 번째 빌드부터는 거의 즉시** 끝난다. `artifacts/embed_cache.json`이 살아 있으면 **바뀐 주석만** 다시 부른다.
- `artifacts/`가 통째로 없어도 이 명령 하나로 전부 복구된다. `.gitignore` 대상인 이유다.

### 2단계 — end-to-end 확인

```bash
python3 script/test_bond_agent.py
```

질문 4개에 대해 `INTENT` / `TOP HITS` / `ANSWER`가 찍힌다. 예시는 §1-1.

**출력을 읽을 때 볼 것:**


| 신호                         | 의미                                       |
| -------------------------- | ---------------------------------------- |
| `INTENT` 줄에 `⚠`            | 분류 LLM 호출이 실패해 기본값으로 넘어갔다. 그냥 넘기지 말 것    |
| `TOP HITS`가 비었거나 1건        | 정상일 수 있다. 하한 `0.45` 미달을 버린 결과다(§3-2 (1)) |
| `ANSWER`에 "제공된 스키마에는 …까지만" | **의도한 동작이다.** 근거 부족을 인정한 것               |
| `ANSWER`가 주석에 없는 인과를 단정    | §6-1의 환각. 현재 4건 중 2건에서 나온다               |


### 개별 검색만 확인하기 (LLM 답변 없이, 빠름)

```bash
python3 -c "
import sys; sys.path.insert(0,'.')
from tools.bond_schema import bond_schema_search
for h in bond_schema_search('듀레이션은 뭐야?', k=5, floor=0.0):
    print(f\"{h['score']:.3f}  {h['term_uri']:<26} {h['label']}\")
"
```

`floor=0.0`을 주면 하한에 걸려 버려진 것까지 보인다. 하한 값을 다시 조정할 때 쓴다.

---

## 8. FAISS → pgvector 이전 (2026-08-22)

### 8-1. 왜 옮겼나

FAISS는 벡터 검색 하나만 한다. pgvector는 같은 테이블에서 **벡터 검색과 키워드 검색(Full Text Search)을 한 자리에서** 할 수 있어, 나중에 하이브리드 검색을 붙일 때 인덱스를 새로 만들 필요가 없다.

옮기기 전에 1차 PoC로 **점수 체계가 달라지지 않는지**부터 확인했다. 현행 `faiss.normalize_L2` + `IndexFlatIP`와 pgvector `1 - (a <=> b)`가 **최대 오차 5.03e-07**로 일치했다(`vectordb_test/results/1_pgvector_test_report.md`). 그래서 `BOND_SCORE_FLOOR = 0.45`를 **재조정 없이 그대로** 들고 왔다.

### 8-2. 무엇이 바뀌었나 (파일 단위)


| 파일                                                                  | 변경                                                                                                                                           |
| ------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/config.py`                                                     | `BOND_INDEX_PATH`·`BOND_TERMS_PATH` 삭제 → `BOND_DB`·`BOND_DSN`·`BOND_TABLE`·`EMBED_DIM` 추가. `**BOND_TOP_K=5`·`BOND_SCORE_FLOOR=0.45`는 변경 없음** |
| `src/kb/build_bond_index.py`                                        | FAISS 쓰기 → `DROP TABLE`·`CREATE`·`INSERT ::vector` + 적재 검증. **L2 정규화 호출 삭제**(`<=>`가 내부 처리). `vector_id` 제거                                   |
| `src/tools/bond_schema.py`                                          | `_load()`(FAISS 인덱스+JSON 로드, 개수 정합 검사) 삭제 → `_conn()`(커넥션 1개). **시그니처·반환 형식 불변**                                                             |
| `src/agent/nodes.py`·`src/agent/state.py`·`src/agent/agent_core.py` | **변경 없음**                                                                                                                                    |
| `requirements.txt`                                                  | `faiss-cpu` → `psycopg[binary]`, `pgvector`                                                                                                  |
| `artifacts/bond.faiss`                                              | **삭제**. 백업은 `vectordb_test/results/bond_130.faiss.snapshot`                                                                                  |
| `src/clova.py`                                                      | `embed()`가 디스크 캐시를 공유하도록 `embed_many`에 위임 → §8-5의 버그를 유발                                                                                     |
| `script/test_pgvector_migration.py`                                 | **신규.** 같은 스크립트로 두 엔진을 재고 비교한다                                                                                                               |


### 8-3. 동등성 검증 결과

동결 질의 72건(`vectordb_test/results/2_baseline_130.json`의 `resolved_queryset`, sha `98b2c6d3019c1031`)을 **런타임 contract 그대로**(`k=5`, `floor=0.45`) 양쪽 엔진에 통과시켰다.

```text
$ python3 script/test_pgvector_migration.py faiss       # 이전 전에 포착
$ python3 script/test_pgvector_migration.py pgvector    # 이전 후
$ python3 script/test_pgvector_migration.py compare

  지표                     faiss    pgvector
  strict_top1            39/52       39/52
  lenient_top1           50/60       50/60
  recall_at_3            57/60       57/60

  Top-5 순서 동일: 72/72  불일치 0
  같은 용어의 score 최대 오차: 0.00e+00  (비교 297쌍)

PASS — FAISS 와 pgvector 결과 동등
```

> 여기 수치가 `vectordb_test`의 baseline(strict 39/52 · lenient 51/60 · R@3 58/60)과 조금 다른 이유는 **k가 다르기 때문**이다. 측정 하네스는 `k=30`으로 계측기 포화를 피하고, 런타임은 `k=5`로 돈다. 이 표는 **런타임 contract 기준**이다.

### 8-4. 코드리스트 91건은 넣지 않기로 했다

`rdfs:comment`가 없는 코드리스트 개체 91건(신용등급 AAA/AA+, 투자지역, 자산군 …)을 넣어 130 → 221로 만들고 같은 질의셋으로 실측했다. 결과는 `vectordb_test/3_baseline_130_v2/baseline_130_v2_report.md`에 있다.


| 지표                | 130      | 221       | 델타       |
| ----------------- | -------- | --------- | -------- |
| lenient Top-1     | 51/60    | 42/60     | **−9**   |
| Recall@3          | 58/60    | 54/60     | −4       |
| 무관 질의 오탐          | 2/8      | 4/8       | +2       |
| **근거 커버리지 Top-5** | **100%** | **68.6%** | **−113** |


**기존 용어끼리의 역전은 0건**이었다 — 손실 19건 전부가 신규 91건이 1위 자리를 가져간 것이다. 즉 검색이 망가진 게 아니라 **상위 슬롯을 점유**했다. 그런데 그 91건은 `comment`가 빈 문자열이라 답변 단계에서 인용할 문장이 없다. 실제로 답변 가능 질의 2건(`등급`·`보수`)이 **근거 0건 상태로** 답변 단계에 들어갔다.

→ **Top-1 정확도만 보면 이 피해가 안 보인다.** 넣을지 말지는 91건의 *이득*을 재는 별도 질의셋이 나온 뒤에 정한다(Action 3).

### 8-5. 이전 중에 만들고 잡은 버그

`clova.embed()`를 캐시 경유로 바꾸면서 **무한 재귀**를 넣었다.

```text
embed()      → embed_many([text])     ← 새로 넣은 위임
embed_many() → embed(t)               ← 원래 있던 호출
→ RecursionError
```

**동등성 테스트 72건이 이 버그를 못 잡았다.** 질의가 전부 캐시에 있어 `embed_many`가 즉시 반환했기 때문이다. 재귀는 **캐시 미스에서만** 터지고, 그건 `script/test_bond_agent.py`의 새 질문에서 드러났다.

고친 방식은 원시 호출 `_embed_raw()`를 따로 두고 `embed_many`가 그것만 부르게 한 것이다. 재발을 막기 위해 `src/clova.py`에 자기검사를 넣었다 — **반드시 캐시에 없는 문장**(`uuid4`)으로 검사한다.

```bash
python3 src/clova.py
#   clova 자기검사 PASS — 캐시미스 경로 dim=1024, 재호출 일치
```

**교훈:** 캐시가 있는 경로는 캐시 적중만 테스트하면 통과한다. 미스 경로를 따로 밟아야 한다.

### 8-6. 이전 후 상태 검증

```text
① 런타임 130 복원      bond_terms.json 130건 / comment 없는 것 0건
② pgvector 적재        130행 / NULL 0 / comment 빈것 0
③ contract 불변        bond_schema_search(text: str, k: int = 5, floor: float = 0.45) -> list[dict]
                       agent/nodes.py 호출부 변경 없음
④ 회귀                 PASS — Top-5 순서 72/72, score 오차 0.00e+00
⑤ FAISS 제거           import faiss 0건 / requirements 0건 / bond.faiss 삭제됨
   end-to-end          script/test_bond_agent.py EXIT=0
```

### 8-7. 이전이 고치지 못한 것

**§6-1의 환각은 그대로다.** 이전 후 실행에서도 `"채권 금리위험이 뭐야?"`에 대해 *"채권은 일반적으로 금리와 반비례 관계를 가지므로"* 라는, 검색된 어느 `comment`에도 없는 문장이 나왔다. 저장소 엔진을 바꾼 것이지 답변 규율을 바꾼 것이 아니다 — **§6-1은 여전히 우선순위 최상이다.**