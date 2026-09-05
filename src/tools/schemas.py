"""
with_structured_output에 넘기는 JSON 스키마 모음. 기존 agent 패키지의
schema.py와 같은 관례(순수 dict, 로직 없음)를 따른다.

[product_domain을 고정 enum + 하위 유형(subtype)으로 재설계]
이 프로젝트가 실제로 다루는 상품군은 채권, 국내ETF, 해외ETF, 펀드
네 개로 닫혀 있다(각각 raw.prbd01n001, raw.pref01n001, raw.pref02n001,
raw.prfd01n001 네 테이블에 대응). 그래서 이전처럼 "기타" 이스케이프를
열어 두지 않고 이 네 값으로만 못박았다. 이 네 도메인 밖의 상품(정기예금,
보험 등)을 묻는 질문은 product_domain이 그냥 빈 배열이 되고, 그건 이
시스템이 애초에 다루지 않는 영역이라는 뜻이다.

domain 밑에 subtype(하위 상품 유형: 채권의 회사채/국공채, ETF의
레버리지/인버스, 펀드의 주식형/채권형 등)을 같이 묶었다. 처음엔
product_domain을 문자열 배열로 두고 subtype을 conditions 안의 조건
하나로 흘려보내는 방식도 고려했지만, 그러면 "상품유형" 같은 개념이
conditions와 product_domain 어느 쪽에 담겨야 하는지 모호해진다. domain과
subtype을 같은 객체에 묶어 두면 이 모호함이 스키마 레벨에서 사라진다.

[DB/엔진 선택은 여전히 이 스키마의 몫이 아니다]
이 스키마가 표준화하는 건 "질문이 개념적으로 무엇을 묻는가"까지다.
relations에 담긴 entity 간 연결, conditions의 applies_to로 표현되는
"이 조건이 최종 대상에 걸리는지 아니면 중간 relation에 걸리는지"가
이미 실행 순서를 그대로 encoding하고 있어서, "어느 DB를 언제 호출할지"는
이 구조만 보고 plan_query_node(nodes.py)가 결정론적으로 계산한다.
LLM에게 "이건 GraphDB에 물어봐"라고 직접 말하게 하지 않는 이유는
DB 이름을 몰라도 되게 하려는 게 아니라(어차피 이 프로젝트에서 RDB/Graph/
Vector를 쓴다는 건 이미 정해져 있다), 질의를 개념 단위로 정확히 쪼개는
언어적 판단과 그 결과를 어떤 엔진에 어떤 순서로 넘길지 정하는 시스템
설계 판단을 같은 LLM 호출에서 섞지 않기 위해서다. relations의
object_ref 체인 하나만 정확하면 실행 순서는 규칙만으로 100% 재현되고
(8개 예시 질문으로 이미 검증함), 반대로 LLM이 매번 "GraphDB 먼저,
그다음 RDB"를 직접 말로 재구성하게 하면 그 판단 자체가 매 호출마다
흔들릴 수 있는 새로운 실패 지점이 하나 더 생긴다.

narrative_topics(예: 위험요인)이 실제로 RDB의 텍스트 컬럼에서 가져올 수
있는지, 아니면 Vector 검색이 필요한지도 이 노드가 판단하지 않는다.
이건 catalog.py의 개념->컬럼 매핑과 완전히 같은 성격의 문제라서,
conditions/fields에 쓰는 카탈로그 대조 로직을 narrative_topics에도
그대로 확장해서 다음 단계에서 처리하는 쪽을 권장한다(아직 구현 전).

[relations의 relation 이름도 온톨로지 TBox를 몰라도 된다]
이전 버전은 "TBox에 있는 술어면 그 이름에 가깝게 써라"고 예시까지
들었는데, 그러려면 결국 이 노드가 TBox 내용을 알아야 한다는 뜻이라
DB 구조를 모른다고 가정한다는 원칙과 정면으로 어긋났다. 지금은
conditions.attribute와 완전히 같은 방식으로 처리한다. relation에는
holds, subsidiary_of처럼 뜻이 분명한 개념명만 쓰게 하고, 그 개념을
실제 OWL 술어로 매핑하는 일은 이 스키마가 아니라 나중에 만들 Graph
카탈로그(catalog.py의 BOND_ATTRIBUTE_MAP 같은 개념->실제 식별자
매핑 테이블을 Graph 쪽에도 두는 것)의 몫으로 미뤘다. TBox 내용은
그 카탈로그를 만들 때 필요하고, 이 프롬프트에는 주입하지 않는다.

[교차질의(cross-domain query) 대응: sort.limit, conditions.domain]
대회 측이 공지한 평가 방식에 "2개 이상의 상품을 비교/검색"하는 교차질의
유형이 명시되어 있다(예: "삼성전자를 보유한 국내/해외ETF와 공모펀드를
1년 수익률 기준 TOP10 알려줘"). 이 유형 자체의 라우팅(여러 도메인의
RDB 조회를 병렬로 실행하는 것)은 기존 스키마로 이미 표현되고
plan_query_node가 이미 정확히 처리한다(product_domain 배열에 도메인을
여러 개 담으면 도메인마다 RDB 단계가 생기고, 전부 같은 Graph 결과에만
의존하므로 서로 독립적으로 병렬 실행된다). 실제로 빠져 있던 건 두
가지뿐이었다.

  1. "TOP10"처럼 결과 개수를 제한하는 표현을 담을 곳이 없었다. sort에
     limit을 추가했다. 여러 도메인을 함께 조회하는 질문이면 limit은
     도메인별로 각각 적용되는 게 아니라, 여러 RDB 단계의 결과를 전부
     합친 뒤 정렬해서 적용된다(도메인당 10개씩 뽑는 게 아니라 합쳐서
     10개). 이 병합+정렬+절단은 plan_query_node가 아니라 그 다음의
     "결과 합치기" 노드가 할 일이다. plan_query_node는 여러 RDB 단계가
     같은 sort/limit을 공유한다는 사실만 각 단계에 그대로 실어 보낸다.

  2. "신용등급 A+ 이상 채권과 위험등급 2등급 이하 ETF를 비교해줘"처럼
     도메인마다 다른 조건이 걸리는 비교형 질문을 표현할 방법이 없었다.
     conditions에 domain을 추가해서, 특정 도메인에만 걸리는 조건을
     표시할 수 있게 했다. 비워두면(대부분의 질문이 이 경우다) 여러
     도메인이 있어도 그 조건이 전부에 똑같이 적용된다는 뜻이다.

enum이 HCX-007의 json_schema 구조화 출력에서 문제를 일으키면(파싱 에러,
enum 밖 값 반환 등), 1순위 대응은 enum을 없애고 프롬프트 지시로만
남기는 것이다.
"""

# 노드 2(analyze_intent_node)가 쓰는 스키마. DB 종류를 전혀 몰라도 되는
# 순수 질의 분해 결과.
INTENT_ANALYSIS_JSON_SCHEMA = {
    "title": "query_intent",
    "description": "사용자 질의를 DB 구조에 대한 지식 없이 개념 단위로 분해한 결과",
    "type": "object",
    "properties": {
        "raw_question": {"type": "string", "description": "원문 그대로"},
        "task": {
            "type": "string",
            "enum": ["lookup", "filter_rank", "relation", "comparison", "explanation", "recommendation"],
            "description": (
                "이 질문의 성격. lookup(특정 상품/개체 하나를 그대로 찾기), "
                "filter_rank(조건으로 걸러 정렬·상위 N), relation(다른 엔티티와의 "
                "관계를 묻는 질문), comparison(2개 이상 비교), explanation(설명·"
                "서술형 답변), recommendation(추천). relations가 비어 있어도 이 "
                "질문이 관계형인지 별도로 판단하는 안전망으로 쓰인다 - relations "
                "추출이 누락됐을 때 plan_query_node가 이 값을 보고 경고할 수 있다."
            ),
        },
        "product_domain": {
            "type": "array",
            "description": (
                "질문이 다루는 상품 도메인. 이 시스템이 다루는 상품군은 채권, "
                "국내ETF, 해외ETF, 펀드 네 가지뿐이다. 질문이 이 네 가지 중 "
                "무엇에도 해당하지 않으면(도메인을 특정할 수 없는 질문, 상품과 "
                "무관한 질문, 정기예금처럼 이 시스템이 다루지 않는 상품군) 빈 "
                "배열로 둔다. 하나의 질문이 여러 도메인에 걸치면(예: '채권과 "
                "ETF 중 어느 쪽이 더 안전해') 해당하는 항목을 모두 배열에 "
                "담는다."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "enum": ["채권", "국내ETF", "해외ETF", "펀드"],
                        "description": (
                            "국내ETF와 해외ETF는 어디에 '투자'하는지가 아니라 그 "
                            "ETF 자체가 어느 거래소에 '상장'되어 있는지로 "
                            "구분한다. '중국 반도체에 투자하는 ETF'라도 한국"
                            "거래소에 상장된 상품(TIGER, KODEX 등 국내 운용사가 "
                            "만든 해외투자형 ETF)이면 국내ETF다. 나스닥, 뉴욕"
                            "증권거래소, '미국에 상장된'처럼 해외 거래소가 질문에 "
                            "명시적으로 드러나야 해외ETF로 분류한다. 상장 위치가 "
                            "질문에 전혀 드러나지 않으면, 국내 투자자 대상 "
                            "서비스라는 맥락상 다른 단서가 없는 한 국내ETF로 "
                            "본다. 펀드는 이 데이터셋에서 공모펀드만 가리킨다. "
                            "사모펀드를 묻는 질문이라도 개념적으로 가장 가까운 "
                            "'펀드'로 분류한다(공모/사모 구분이 필요하면 "
                            "subtype에 담는다). 그 상품이 실제로 데이터에 "
                            "있는지는 이 노드가 판단하지 않는다."
                        ),
                    },
                    "subtype": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "이 도메인 안에서 질문이 더 좁혀 지정하는 하위 상품"
                            "유형. 채권이면 회사채, 국공채, 특수채, 개인투자용"
                            "국채 같은 구분. ETF면 레버리지, 인버스, 액티브, "
                            "테마형 같은 구분. 펀드면 주식형, 채권형, 혼합형, "
                            "공모, 사모 같은 구분. 질문에 이런 하위 구분이 "
                            "명시적으로 나오지 않으면 빈 배열로 둔다. 여기 담은 "
                            "정보는 conditions에 다시 조건으로 넣지 않는다(중복"
                            "표현 금지)."
                        ),
                    },
                },
                "required": ["domain", "subtype"],
            },
        },
        "target_entities": {
            "type": "array",
            "description": "질문이 특정 상품명이나 회사명을 직접 지목한 경우.",
            "items": {
                "type": "object",
                "properties": {
                    "surface_form": {"type": "string", "description": "질문에 등장한 표현 그대로"},
                    "entity_type": {
                        "type": "string",
                        "enum": ["product_name", "company", "theme", "unknown"],
                    },
                },
                "required": ["surface_form", "entity_type"],
            },
        },
        "conditions": {
            "type": "array",
            "description": (
                "단순 속성 필터. attribute는 실제 컬럼명이 아니라 개념명이다. "
                "특정 상품명 자체(예: 국민성장펀드)는 여기가 아니라 "
                "target_entities에 담고, 도메인 하위 유형(예: 회사채, "
                "레버리지)은 여기가 아니라 product_domain 항목의 subtype에 "
                "담는다. 그 외의 속성 필터(신용등급, 잔존기간, 순자산, "
                "매수수익률처럼 수치나 값으로 비교되는 것)만 여기에 담는다."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "attribute": {
                        "type": "string",
                        "description": "개념명. 예: 신용등급, 잔존기간, 통화. 실제 DB 컬럼명을 몰라도 된다.",
                    },
                    "operator": {
                        "type": "string",
                        "enum": ["eq", "ne", "gt", "gte", "lt", "lte", "between", "contains"],
                        "description": "'이상'=gte, '이하'=lte, '인'=eq, '사이'=between, '포함/관련'=contains. 문장의 어미로 결정한다.",
                    },
                    "value": {"type": "string"},
                    "value_2": {
                        "type": "string",
                        "description": "between일 때만 두 번째 값. 아니면 빈 문자열.",
                    },
                    "applies_to": {
                        "type": "string",
                        "description": "이 조건이 걸리는 대상. 최종 조회 대상이면 'target', relations 배열 안 특정 관계에 걸리면 그 relation의 id.",
                    },
                    "domain": {
                        "type": "string",
                        "description": (
                            "product_domain에 도메인이 여러 개 있고 이 조건이 그중 "
                            "특정 도메인에만 걸릴 때만 그 도메인 이름을 쓴다(예: '신용등급 "
                            "A+ 이상 채권과 위험등급 2등급 이하 ETF를 비교'에서 신용등급 "
                            "조건은 domain: '채권', 위험등급 조건은 domain: '국내ETF'). "
                            "도메인이 하나뿐이거나 여러 도메인에 똑같이 적용되는 조건이면 "
                            "빈 문자열로 둔다."
                        ),
                    },
                    "time_window_relative": {
                        "type": "string",
                        "description": "'최근 6개월'처럼 상대적 기간이면 예: '6_months'. 없으면 빈 문자열.",
                    },
                    "kind": {
                        "type": "string",
                        "enum": ["quantitative", "categorical", "boolean", "qualitative"],
                        "description": (
                            "이 조건의 성격. quantitative(수치 비교), categorical(범주형 "
                            "값), boolean(참/거짓), qualitative(\"안전한\", \"좋은\"처럼 "
                            "확정할 수 없는 주관적 형용사). qualitative는 실제 컬럼 조건으로 "
                            "확정하면 안 된다."
                        ),
                    },
                    "grounding_status": {
                        "type": "string",
                        "enum": ["resolved", "unresolved"],
                        "description": (
                            "resolved(이 조건이 실제 값으로 확정될 수 있음)/unresolved(아직 "
                            "확정할 수 없음). kind가 qualitative이면 항상 unresolved여야 "
                            "한다."
                        ),
                    },
                },
                "required": [
                    "attribute", "operator", "value", "value_2", "applies_to", "domain",
                    "time_window_relative", "kind", "grounding_status",
                ],
            },
        },
        "relations": {
            "type": "array",
            "description": (
                "엔티티 간 관계. 다른 엔티티와의 연결을 묻는 질문에서만 채운다. "
                "체인 길이에는 제한이 없다. '에코프로의 자회사를 편입한 ETF'처럼 "
                "2단계로 이어지든, '에코프로의 자회사의 계열사가 편입된 ETF'처럼 "
                "3단계 이상으로 이어지든, 단계마다 새 relation을 만들고 "
                "object_ref로 이전 relation의 id를 가리켜 체인을 만든다. 체인의 "
                "마지막 relation(다른 relation의 object_ref로 참조되지 않는 "
                "relation)의 subject_domain은 보통 product_domain에 쓴 도메인과 "
                "같다. 가능하면 그때 같은 표현(국내ETF, 해외ETF 등)을 쓰고, "
                "확실하지 않으면 상위 개념(ETF, Company 등)만 써도 된다."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "이 관계의 고유 id. 예: R1, R2."},
                    "subject_domain": {"type": "string", "description": "관계의 주체 도메인. 예: ETF, Company. 모르면 빈 문자열."},
                    "relation": {
                        "type": "string",
                        "description": (
                            "관계 이름. 실제 온톨로지 술어(OWL property, 예: "
                            "fp:isThemeProduct)의 정확한 이름은 몰라도 된다. 그건 "
                            "conditions의 attribute가 실제 컬럼명이 아니라 개념명인 "
                            "것과 똑같은 이유로 이 노드가 알 이유가 없는 DB 구조 "
                            "정보다(이 노드에 TBox 내용을 따로 주입하지 않는다). "
                            "holds, subsidiary_of, tagged_with처럼 관계의 뜻이 분명히 "
                            "드러나는 짧은 개념명만 쓴다. 같은 뜻의 관계는 항상 같은 "
                            "이름으로 써서 일관성을 유지한다. 이 개념명을 실제 OWL "
                            "술어로 매핑하는 일은 catalog.py의 개념->컬럼 매핑과 같은 "
                            "방식으로 Graph 쪽에 별도 카탈로그를 두고 다음 단계에서 "
                            "처리해야 한다(아직 구현 전)."
                        ),
                    },
                    "object_entity": {
                        "type": "string",
                        "description": "관계의 대상이 되는 구체적 이름. object_ref를 쓰면 빈 문자열로 둔다.",
                    },
                    "object_ref": {
                        "type": "string",
                        "description": "관계의 대상이 다른 relation의 결과일 때 그 relation의 id. object_entity를 쓰면 빈 문자열로 둔다.",
                    },
                    "time_window_relative": {"type": "string", "description": "예: '6_months'. 없으면 빈 문자열."},
                    "entity_role": {
                        "type": "string",
                        "enum": [
                            "product", "share_class", "company", "issuer", "index",
                            "theme", "manager", "ticker", "model", "",
                        ],
                        "description": (
                            "관계 대상(object_entity 또는 object_ref가 가리키는 결과)이 "
                            "실제로 어떤 역할의 엔티티인지. product(상품 자체), "
                            "share_class(클래스/유형), company(기업), issuer(발행사), "
                            "index(지수), theme(테마), manager(운용사), ticker(티커/"
                            "종목코드), model(모델/시리즈). 확실하지 않으면 빈 문자열. "
                            "GraphDB가 어느 TBox 클래스부터 엔티티를 찾아볼지 결정하는 "
                            "유일한 신호이므로 가능하면 채운다."
                        ),
                    },
                    "path": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "관계를 자연어로 나열한 경로 힌트. 예: [\"ETF\", \"편입증권\", "
                            "\"기업\"]. 실행 순서 계산에는 쓰이지 않는다(그건 id/object_ref가 "
                            "계속 담당한다) - Graph 쪽 스키마 탐색 정확도를 높이는 참고 "
                            "정보일 뿐이다. 모르면 빈 배열로 둔다."
                        ),
                    },
                },
                "required": [
                    "id", "subject_domain", "relation", "object_entity", "object_ref",
                    "time_window_relative", "entity_role", "path",
                ],
            },
        },
        "sort": {
            "type": "object",
            "description": "정렬 조건. 없으면 attribute를 빈 문자열로 둔다.",
            "properties": {
                "attribute": {"type": "string"},
                "order": {"type": "string", "enum": ["asc", "desc", ""]},
                "limit": {
                    "type": "string",
                    "description": (
                        "'상위 N개', 'TOP10'처럼 개수 제한이 있으면 그 숫자를 문자열로 "
                        "담는다(예: '10'). 여러 product_domain을 함께 조회하는 질문(예: "
                        "'국내/해외ETF와 펀드를 1년 수익률 기준 TOP10')이면 이 limit은 "
                        "도메인별로 각각 적용되는 게 아니라, 도메인 결과를 전부 합쳐서 "
                        "정렬한 뒤 적용된다. 제한이 없으면 빈 문자열."
                    ),
                },
                "domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "이 정렬(그리고 limit)을 공유하는 도메인 목록. product_domain에 "
                        "도메인이 여러 개 있고 이 정렬이 그중 일부에만 적용될 때만 "
                        "채운다(예: '국내ETF·해외ETF는 수익률 TOP5로 묶고 채권은 별개로 "
                        "보여줘'에서 국내ETF·해외ETF만). 비워두면(대부분의 질문) "
                        "product_domain 전체가 이 정렬을 공유한다는 뜻이다."
                    ),
                },
            },
            "required": ["attribute", "order", "limit", "domains"],
        },
        "output_requirements": {
            "type": "object",
            "properties": {
                "fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "결과에 구조화된 값으로 꼭 포함해야 하는 개념명. 예: 순자산.",
                },
                "narrative_topics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "서술형으로 설명해야 하는 주제. 예: 위험요인, 투자전략 동향. "
                        "이 주제가 실제로 RDB의 특정 컬럼에서 가져올 수 있는지, "
                        "아니면 Vector 검색이 필요한지는 이 노드가 판단하지 않는다. "
                        "그 판단은 카탈로그 대조 단계의 몫이다."
                    ),
                },
            },
            "required": ["fields", "narrative_topics"],
        },
        "answer_format": {
            "type": "string",
            "enum": ["list", "narrative", "list_with_narrative"],
            "description": (
                "narrative_topics로 딱 떨어지게 쪼갤 세부 주제가 없어도(예: "
                "'OO 상품 정보 알려줘'처럼 상품 전체에 대한 개괄 설명), 서술형 "
                "답이 필요하면 narrative 또는 list_with_narrative를 쓰고 "
                "narrative_topics는 빈 배열로 둘 수 있다."
            ),
        },
    },
    "required": [
        "raw_question", "task", "product_domain", "target_entities", "conditions",
        "relations", "sort", "output_requirements", "answer_format",
    ],
}

# 노드 3의 폴백: 카탈로그에 없는 개념을 실제 컬럼명에 매칭
COLUMN_RESOLUTION_JSON_SCHEMA = {
    "title": "column_resolution",
    "description": "카탈로그에 없는 개념명을 실제 테이블 컬럼명에 매칭",
    "type": "object",
    "properties": {
        "resolutions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "concept": {"type": "string", "description": "입력으로 받은 개념명 그대로"},
                    "column": {
                        "type": "string",
                        "description": "가장 적절한 실제 컬럼명. 대응하는 컬럼이 전혀 없다고 판단되면 빈 문자열.",
                    },
                    "confidence": {"type": "string", "enum": ["high", "low"]},
                },
                "required": ["concept", "column", "confidence"],
            },
        },
    },
    "required": ["resolutions"],
}

# 노드 4 두 번째 단계(자연어 초안 -> 실제 SQL)가 쓰는 스키마.
SQL_OUTPUT_JSON_SCHEMA = {
    "title": "sql_output",
    "description": "자연어 초안을 실제 SQL로 옮긴 결과",
    "type": "object",
    "properties": {
        "sql": {"type": "string", "description": "실행 가능한 SQL 한 문장."},
        "assumptions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "SQL을 쓰면서 암묵적으로 적용한 규칙. 예: 'BUY_YIELD가 NULL인 행은 제외했습니다.'",
        },
    },
    "required": ["sql", "assumptions"],
}

# 최종 response schema
FINAL_ANSWER_JSON_SCHEMA = {
    "title": "final_answer_output",
    "description": "대회 제출 형식에 맞춘 최종 답변 및 추론 과정",
    "type": "object",
    "properties": {
        "think_trace": {
            "type": "string",
            "description": "사고·추론·도구 사용 과정을 간략히 요약. 예: '조건 파싱 -> 필터(위험등급 2등급 이하) -> 정렬(순자산) -> 상위 3종 도출'"
        },
        "answer": {
            "type": "string",
            "description": "검색된 데이터를 바탕으로 한 최종 자연어 답변"
        }
    },
    "required": ["think_trace", "answer"],
    "additionalProperties": False
}
