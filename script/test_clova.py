# -*- coding: utf-8 -*-
"""CLOVA Studio 연결 진단.

1단계(Intent) · 2단계(Ontology Grounding) 구현 전에 확인해야 하는 것만 본다.
  A. 채팅 비스트리밍 호출 — 응답을 값으로 받아야 LangGraph 노드가 성립한다
  B. 프롬프트만으로 JSON 강제 — HCX-005/DASH-002 경로
  C. Structured Outputs — HCX-007 전용. 스키마 위반이 원천 차단되는지
  D. 임베딩 차원 — 2단계 스키마 인덱스의 전제

실행:  python3 script/test_clova.py
"""

import json
import pathlib
import sys
import time

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOST = "https://clovastudio.stream.ntruss.com"

# 추론 모델(HCX-007)은 maxTokens를 거부하고 maxCompletionTokens를 쓴다.
# 값 범위 문제가 아니라 파라미터명이 다르다 — maxTokens=4096도 40001로 떨어진다.
REASONING_MODELS = {"HCX-007"}
MODELS = ["HCX-005", "HCX-DASH-002", "HCX-007"]


def load_key() -> str:
    """.env에서 clova 키를 읽는다. 값은 절대 출력하지 않는다."""
    env = ROOT / ".env"
    if not env.exists():
        sys.exit(f"FAIL  .env 없음: {env}")
    for line in env.read_text(encoding="utf-8").splitlines():
        k, _, v = line.partition("=")
        if k.strip() == "clova":
            key = v.strip().strip('"').strip("'")
            if not key:
                sys.exit("FAIL  .env의 clova 값이 비어 있음")
            return key if key.startswith("Bearer ") else f"Bearer {key}"
    sys.exit("FAIL  .env에 clova 항목 없음")


def chat(key, model, system, user, max_tokens=512, response_format=None):
    """비스트리밍 호출.

    사용자 제공 콘솔 샘플과 다른 점 두 가지:
      - Accept를 application/json으로 (text/event-stream이면 SSE라 반환값으로 못 쓴다)
      - 모델별 토큰 파라미터명 분기
    """
    headers = {
        "Authorization": key,
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
    }
    body = {
        "messages": [
            {"role": "system", "content": [{"type": "text", "text": system}]},
            {"role": "user", "content": [{"type": "text", "text": user}]},
        ],
        "topP": 0.8,
        "temperature": 0.1,          # 분류는 결정적이어야 한다
        "repetitionPenalty": 1.1,
        "stop": [],
        "seed": 0,
    }
    if model in REASONING_MODELS:
        body["maxCompletionTokens"] = max_tokens
        if response_format:
            # thinking과 responseFormat은 상호배타. HCX-007은 thinking이 기본 ON이라
            # 명시적으로 꺼야 structured outputs가 통과한다. "off"는 무효값, "none"만 받는다.
            body["thinking"] = {"effort": "none"}
    else:
        body["maxTokens"] = max_tokens
        body["topK"] = 0
        body["includeAiFilters"] = True
    if response_format:
        body["responseFormat"] = response_format

    r = requests.post(f"{HOST}/v3/chat-completions/{model}", headers=headers, json=body, timeout=120)
    if r.status_code != 200:
        # 본문을 삼키면 진단이 무의미해진다. 40001 같은 건 메시지에 원인이 들어 있다.
        raise RuntimeError(f"HTTP {r.status_code} — {r.text[:220]}")
    data = r.json()

    code = (data.get("status") or {}).get("code")
    if code not in (None, "20000"):
        raise RuntimeError(f"status {code} — {(data.get('status') or {}).get('message')}")

    content = (data.get("result") or {}).get("message", {}).get("content")
    # v3는 입력이 배열이라 출력도 배열로 오는 경우가 있다. 둘 다 처리한다.
    if isinstance(content, list):
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    if not isinstance(content, str):
        raise RuntimeError(f"content 형태 불명: {type(content)} / {str(content)[:200]}")
    return content


def parse_json_loose(text: str) -> dict:
    """모델이 코드펜스나 설명을 붙여도 JSON만 뽑아낸다."""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("```")[1] if "```" in s[3:] else s[3:]
        s = s.removeprefix("json").strip()
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end == -1:
        raise json.JSONDecodeError("객체를 못 찾음", s, 0)
    return json.loads(s[start:end + 1])


DOMAINS = ["bond_kr", "etf_kr", "etf_gl", "fund_pub"]
QUERY_TYPES = ["simple_lookup", "conditional_search", "relation_search", "unanswerable_check"]

INTENT_SYSTEM = """
너는 금융상품 질의의 의도만 분류한다. JSON 객체 하나만 출력한다. 설명·코드펜스 금지.

domain: {DOMAINS} 중 해당하는 것 전부. 확실하지 않으면 복수로 넣는다.
  bond_kr=국내채권, etf_kr=국내ETF, etf_gl=해외ETF(미국·해외 상장), fund_pub=공모펀드

query_type: 아래 넷 중 하나. 위에서부터 먼저 맞는 것을 고른다.
  unanswerable_check  질의에 존재할 수 없는 값·미래 시점·미등재 상품이 섞여 있다.
                      예: 등급 체계에 없는 값(AAAA), 데이터 기준일 이후 출시, 이름이 없는 상품, 아직 실현되지 않은 수익률
  relation_search     상품과 다른 개체(기업·자회사·편입종목·테마·지수) 사이의 연결을 따라가야 한다.
                      "A를 편입한", "A의 자회사", "A 테마", "겹치는", "중복" 같은 표현이 신호다.
  conditional_search  단일 상품군 안에서 조건으로 거르고 정렬·비교·집계한다.
  simple_lookup       특정 상품 하나를 지목해 속성값만 조회한다.

keywords: 데이터 컬럼에 직접 매핑되지 않는 모호한 표현의 원문. 예: "안전한", "저보수", "규모가 큰"
entities: 질의에 등장한 상품명·기업명·티커 원문 그대로
numeric_filters: 명시적 수치 조건 원문. 예: "순자산 5000억 이상"

출력 형식:
{{"domain":[],"query_type":"","keywords":[],"entities":[],"numeric_filters":[]}}
"""


INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "domain": {"type": "array", "items": {"type": "string", "enum": DOMAINS}},
        "query_type": {"type": "string", "enum": QUERY_TYPES},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "entities": {"type": "array", "items": {"type": "string"}},
        "numeric_filters": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["domain", "query_type", "keywords", "entities", "numeric_filters"],
}

# 예상 35문항에서 뽑은 대표 케이스. (질의, 기대 query_type, 기대 domain)
CASES = [
    ("최신 상품정보 갱신일 기준으로 에스케이하이닉스224-2의 발행사, 신용등급, 표면금리, 만기일을 알려줘",
     "simple_lookup", "bond_kr"),
    ("안전한 ETF 추천해줘", "conditional_search", "etf_kr"),
    ("미국 증시에 상장된 주식형 ETF 중 총보수가 낮고 운용 규모가 큰 상품 3개만 비교해 주세요",
     "conditional_search", "etf_gl"),
    ("에코프로의 자회사를 편입한 ETF 중 순자산이 큰 상품의 위험요인 알려줘",
     "relation_search", "etf_kr"),
    ("캠브리콘이 편입된 중국 반도체 ETF를 알려줘", "relation_search", "etf_gl"),
    ("신용등급 AAAA인 채권 찾아줘", "unanswerable_check", "bond_kr"),
    ("KODEX AI로봇 ETF 정보 알려줘", "unanswerable_check", "etf_kr"),
]


def run_cases(key, model, response_format=None, label=""):
    hit = 0
    for q, want_type, want_dom in CASES:
        try:
            t0 = time.time()
            text = chat(key, model, INTENT_SYSTEM, q, max_tokens=1024, response_format=response_format)
            obj = parse_json_loose(text)
            got_type = obj.get("query_type")
            got_dom = obj.get("domain") or []
            ok_t = got_type == want_type
            ok_d = want_dom in got_dom
            hit += ok_t
            mark = "OK  " if ok_t and ok_d else ("~   " if ok_t or ok_d else "MISS")
            note = ""
            if not ok_t:
                note += f" type={got_type}(기대 {want_type})"
            if not ok_d:
                note += f" domain={got_dom}(기대 {want_dom} 포함)"
            print(f"  {mark} {time.time()-t0:5.2f}s  {q[:26]:<28}{note}")
        except Exception as e:
            print(f"  FAIL       {q[:26]:<28} {type(e).__name__}: {str(e)[:120]}")
    print(f"  → query_type 정확도 {hit}/{len(CASES)}  {label}")
    return hit


def main():
    key = load_key()
    print(f"키 로드 OK (길이 {len(key)-7}, 값 미출력)")

    print("\n[A] 채팅 비스트리밍 호출")
    alive = []
    for m in MODELS:
        try:
            t0 = time.time()
            out = chat(key, m, "한 단어로만 답한다.", "대한민국의 수도는?",
                       max_tokens=2048 if m in REASONING_MODELS else 64)
            print(f"  PASS  {m:<14} {time.time()-t0:5.2f}s  → {out.strip()[:40]!r}")
            alive.append(m)
        except Exception as e:
            print(f"  FAIL  {m:<14} {str(e)[:170]}")

    if "HCX-005" in alive:
        print("\n[B] 프롬프트 기반 JSON 강제 — HCX-005")
        run_cases(key, "HCX-005", label="(HCX-005 / 프롬프트만)")

    if "HCX-DASH-002" in alive:
        print("\n[B'] 프롬프트 기반 JSON 강제 — HCX-DASH-002 (경량·고속)")
        run_cases(key, "HCX-DASH-002", label="(DASH-002 / 프롬프트만)")

    if "HCX-007" in alive:
        print("\n[C] Structured Outputs — HCX-007 (스키마 강제)")
        run_cases(key, "HCX-007", response_format={"type": "json", "schema": INTENT_SCHEMA},
                  label="(HCX-007 / responseFormat)")

    print("\n[D] 임베딩 — 2단계 스키마 인덱스 전제")
    raw = key.removeprefix("Bearer ").strip()
    try:
        from langchain_naver import ClovaXEmbeddings
        for m in ("bge-m3", "clir-emb-dolphin"):
            try:
                t0 = time.time()
                v = ClovaXEmbeddings(model=m, api_key=raw).embed_query(
                    "1=최고위험 … 6=최저위험. 숫자가 클수록 안전하다.")
                print(f"  PASS  {m:<18} {time.time()-t0:5.2f}s  dim={len(v)}")
            except Exception as e:
                print(f"  FAIL  {m:<18} {type(e).__name__}: {str(e)[:170]}")
    except Exception as e:
        print(f"  FAIL  import: {e}")
    print()


if __name__ == "__main__":
    main()
