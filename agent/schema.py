"""
with_structured_output에 넘기는 JSON 스키마 모음.

이 파일도 데이터만 담는다. 로직은 없다. Pydantic 클래스 대신 순수 dict로
스키마를 적었다. with_structured_output은 Pydantic 클래스, TypedDict,
JSON 스키마 dict를 모두 받을 수 있는데, dict로 주면 새 클래스를 정의할
필요가 없고 결과도 dict로 돌아온다 (예: result["steps"]).
"""

# plan_routing 노드가 with_structured_output에 넘기는 스키마.
# LLM은 이 형태에 맞는 JSON만 돌려준다.
PLAN_JSON_SCHEMA = {
    "title": "execution_plan",
    "description": "금융상품 질의를 처리하기 위한 실행 계획",
    "type": "object",
    "properties": {
        "abstain": {
            "type": "boolean",
            "description": (
                "질의가 [검색된 속성 메타데이터]나 [실제 DB 테이블/컬럼 목록]에 "
                "없는 개념을 묻고 있어서 답할 수 없으면 true. 그 외에는 false."
            ),
        },
        "abstain_reason": {
            "type": "string",
            "description": "abstain이 true일 때만 채운다. 왜 답할 수 없는지 한 문장.",
        },
        "steps": {
            "type": "array",
            "description": "실행할 단계 목록. abstain이 true면 빈 배열([])로 둔다.",
            "items": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "이 단계의 고유 id. 예: A, B, C",
                    },
                    "engine": {
                        "type": "string",
                        "enum": ["graph", "rdb", "vector"],
                        "description": "이 단계를 실행할 엔진",
                    },
                    "query": {
                        "type": "string",
                        "description": "실제 SPARQL 또는 SQL 또는 검색어 문자열",
                    },
                    "depends_on": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "먼저 끝나야 하는 단계 id 목록. 없으면 빈 리스트.",
                    },
                },
                "required": ["id", "engine", "query", "depends_on"],
            },
        },
    },
    "required": ["abstain", "abstain_reason", "steps"],
}

# generate_answer 노드가 with_structured_output에 넘기는 스키마.
ANSWER_JSON_SCHEMA = {
    "title": "final_answer",
    "description": "금융상품 질의에 대한 최종 답변",
    "type": "object",
    "properties": {
        "answer": {
            "type": "string",
            "description": "최종 답변 텍스트",
        },
        "evidence": {
            "type": "array",
            "items": {"type": "string"},
            "description": "답변 근거로 사용한 retrieved_context 항목 요약",
        },
    },
    "required": ["answer", "evidence"],
}