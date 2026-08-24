# -*- coding: utf-8 -*-
"""CLOVA Studio 클라이언트 — 채팅과 임베딩.

콘솔 샘플 코드와 다른 점 셋 (실측으로 확인):
  1. Accept를 application/json 으로. text/event-stream 이면 SSE라 반환값으로 못 쓴다.
  2. 추론 모델(HCX-007)은 maxTokens 를 거부한다. maxCompletionTokens 를 쓴다
     — 값 범위 문제가 아니라 파라미터명이 다르다(maxTokens=4096도 40001).
  3. HCX-007에서 structured outputs 를 쓰려면 thinking 을 명시적으로 꺼야 한다.
     기본 ON 이라 responseFormat 과 충돌한다. "off"는 무효값이고 "none"만 받는다.
"""
import json
import sys

import requests

from config import CLOVA_HOST, EMBEDDING_MODEL, ROOT

REASONING_MODELS = {"HCX-007"}


def load_key() -> str:
    """.env의 clova 키. 값은 절대 로그에 남기지 않는다."""
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


_KEY = None


def key() -> str:
    global _KEY
    if _KEY is None:
        _KEY = load_key()
    return _KEY


def chat(model, system, user, max_tokens=1024, response_format=None, temperature=0.1):
    body = {
        "messages": [
            {"role": "system", "content": [{"type": "text", "text": system}]},
            {"role": "user", "content": [{"type": "text", "text": user}]},
        ],
        "topP": 0.8, "temperature": temperature, "repetitionPenalty": 1.1,
        "stop": [], "seed": 0,
    }
    if model in REASONING_MODELS:
        body["maxCompletionTokens"] = max_tokens
        if response_format:
            body["thinking"] = {"effort": "none"}
    else:
        body["maxTokens"] = max_tokens
        body["topK"] = 0
        body["includeAiFilters"] = True
    if response_format:
        body["responseFormat"] = response_format

    r = requests.post(f"{CLOVA_HOST}/v3/chat-completions/{model}",
                      headers={"Authorization": key(),
                               "Content-Type": "application/json; charset=utf-8",
                               "Accept": "application/json"},
                      json=body, timeout=120)
    if r.status_code != 200:
        # 본문을 삼키면 원인을 못 찾는다. 40001 메시지에 어느 파라미터인지 들어 있다.
        raise RuntimeError(f"HTTP {r.status_code} — {r.text[:220]}")
    data = r.json()
    code = (data.get("status") or {}).get("code")
    if code not in (None, "20000"):
        raise RuntimeError(f"status {code} — {(data.get('status') or {}).get('message')}")
    content = (data.get("result") or {}).get("message", {}).get("content")
    if isinstance(content, list):   # v3는 입력이 배열이라 출력도 배열로 오는 경우가 있다
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    if not isinstance(content, str):
        raise RuntimeError(f"content 형태 불명: {type(content)}")
    return content


def parse_json_loose(text: str) -> dict:
    """모델이 코드펜스나 설명을 붙여도 JSON 객체만 뽑는다."""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("```")[1] if "```" in s[3:] else s[3:]
        s = s.removeprefix("json").strip()
    a, b = s.find("{"), s.rfind("}")
    if a == -1 or b == -1:
        raise json.JSONDecodeError("객체를 못 찾음", s, 0)
    return json.loads(s[a:b + 1])


_EMB = None


def _embedder():
    global _EMB
    if _EMB is None:
        from langchain_naver import ClovaXEmbeddings
        _EMB = ClovaXEmbeddings(model=EMBEDDING_MODEL,
                                api_key=key().removeprefix("Bearer ").strip())
    return _EMB


def embed(text: str) -> list[float]:
    return _embedder().embed_query(text)


def embed_many(texts: list[str], pause: float = 1.2, progress: bool = True) -> list[list[float]]:
    """여러 건 임베딩. 분당 쿼터가 있어 간격을 두고, 결과는 디스크에 캐시한다.

    - langchain의 embed_documents는 지연 없이 연속 호출해 429(rate exceeded)를 맞는다.
      실측상 약 60건 연속이면 차단되므로 기본 간격을 1.2s(≈50건/분)로 둔다.
    - 캐시가 없으면 중간에 실패할 때 앞서 성공한 호출이 통째로 버려진다.
      TTL 주석은 앞으로 계속 손볼 예정이라 재빌드가 반복된다.
    """
    import hashlib
    import time as _t

    from config import ARTIFACTS
    ARTIFACTS.mkdir(exist_ok=True)
    cache_path = ARTIFACTS / "embed_cache.json"
    cache = {}
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            cache = {}      # 깨진 캐시는 조용히 버린다. 다시 만들면 그만이다.

    def kk(t):
        return hashlib.sha1(f"{EMBEDDING_MODEL}\x00{t}".encode()).hexdigest()

    out, new_hits, api_calls = [], 0, 0
    for i, t in enumerate(texts):
        h = kk(t)
        if h in cache:
            out.append(cache[h])
            continue
        for attempt in range(7):
            try:
                v = embed(t)
                break
            except Exception as e:
                if "429" not in str(e) and "42901" not in str(e):
                    raise
                wait = min(2 ** attempt, 65)      # 분 단위 쿼터라 최대 65s까지 기다린다
                if progress:
                    print(f"  429 — {wait}s 대기 ({i+1}/{len(texts)})", flush=True)
                _t.sleep(wait)
        else:
            cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            raise RuntimeError(f"429 재시도 7회 실패: {i}번째 (여기까지는 캐시에 저장됨)")
        out.append(v)
        cache[h] = v
        new_hits += 1
        api_calls += 1
        if new_hits % 20 == 0:      # 중간 저장 — 크래시해도 진행분이 남는다
            cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        if progress and (i + 1) % 25 == 0:
            print(f"  {i+1}/{len(texts)}  (API 호출 {api_calls})", flush=True)
        _t.sleep(pause)

    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    if progress:
        print(f"  임베딩 완료 — API 호출 {api_calls}건 / 캐시 재사용 {len(texts)-api_calls}건")
    return out
