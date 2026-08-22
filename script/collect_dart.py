"""OpenDART 수집 — ① 기업 고유번호 마스터(corpCode.xml) ② 상장사 타법인 출자현황.

    python3 EDA/collect_dart.py            # 전량
    python3 EDA/collect_dart.py 20         # 20종만 시범
    python3 EDA/collect_dart.py corpcode   # 마스터만

인증키는 .env의 `dart=`. 로그·사이드카 URL에는 `***`로 마스킹해 기록한다(EDA/validate_external.py가 검사).
재실행 시 이미 받은 파일은 건너뛴다. 일 20,000건 한도 안에서 sleep 0.3초(DART_SLEEP)로 정중하게 돈다.
"""
import io
import json
import os
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
MASTER_DIR = ROOT / "data/external/company_master"
GOV_DIR = ROOT / "data/external/company_governance"
KIND = MASTER_DIR / "kind_listed_corp_20260711.csv"
HOLDING = ROOT / "data/relations/etf_holding.csv"
CORPCODE = MASTER_DIR / "dart_corpcode_20260711.xml"
AS_OF = "2026-07-11"  # 스냅샷 기준일. 개별 공시 접수일은 build_company_relations.py가 rcept_no에서 뽑는다
YMD = AS_OF.replace("-", "")
BSNS_YEAR, REPRT_CODE = "2025", "11011"  # FY2025 사업보고서 — 접수일 2026-03 전후라 컷오프보다 안전
SLEEP = float(os.environ.get("DART_SLEEP", 0.3))
BACKOFF = float(os.environ.get("DART_BACKOFF", 60))  # 429/403/020(요청제한)을 만나면 대기 후 재시도
MAX_RETRY = int(os.environ.get("DART_MAX_RETRY", 5))
OK_STATUS = {"000", "013"}  # 013 = 조회된 데이터 없음(출자한 타법인이 없는 회사). 실패가 아니다

KEY = next(l.split("=", 1)[1].strip() for l in (ROOT / ".env").read_text().splitlines()
           if l.startswith("dart="))
assert len(KEY) == 40, "dart 인증키 형식 이상"


def mask(url):
    return url.replace(KEY, "***")


def get(url):
    """403/429는 레이트리밋이므로 대기 후 재시도. 그 외 HTTP 오류는 올린다."""
    for attempt in range(MAX_RETRY + 1):
        r = requests.get(url, timeout=60)
        if r.status_code in (403, 429) and BACKOFF and attempt < MAX_RETRY:
            print(f"  .. HTTP {r.status_code} — {BACKOFF:.0f}초 대기 후 재시도 ({attempt + 1}/{MAX_RETRY})", flush=True)
            time.sleep(BACKOFF)
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()


def sidecar(path, url, **extra):
    meta = {"source": "DART OpenAPI (opendart.fss.or.kr)", "as_of": AS_OF,
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "url": mask(url), **extra}
    path.with_name(path.name + ".meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def collect_corpcode():
    """고유번호 전체(비상장 포함) zip → XML."""
    if CORPCODE.exists():
        print(f"[corpCode] 스킵(기수집): {CORPCODE.name}")
        return
    url = f"https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={KEY}"
    body = get(url).content
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".xml"))
        xml = z.read(name)
    assert b"<list>" in xml, f"XML 아님(인증 실패 응답?): {xml[:200]}"
    CORPCODE.parent.mkdir(parents=True, exist_ok=True)
    CORPCODE.write_bytes(xml)
    sidecar(CORPCODE, url, api="corpCode", zip_member=name, bytes=len(xml))
    print(f"[corpCode] 저장 {CORPCODE.name} ({len(xml):,} bytes)")


def stock_to_corp():
    """corpCode.xml → {6자리 종목코드: 고유번호}. 상장사만 stock_code가 채워져 있다."""
    df = pd.read_xml(CORPCODE, dtype=str, encoding="utf-8")
    df["stock_code"] = df["stock_code"].fillna("").str.strip()
    df = df[df.stock_code.str.len() == 6]
    return dict(zip(df.stock_code, df.corp_code.str.zfill(8)))


def targets():
    """ETF 편입종목 ticker6 ∪ KIND 상장사 종목코드 → corpCode로 매핑된 상장사."""
    h = pd.read_csv(HOLDING, dtype=str, keep_default_na=False)
    codes = set(h.loc[h.holding_code_type == "ticker6", "holding_code_raw"])
    codes |= set(pd.read_csv(KIND, dtype=str, keep_default_na=False)["종목코드"])
    m = stock_to_corp()
    hit = sorted((m[c], c) for c in codes if c in m)
    print(f"[출자현황] 후보 종목코드 {len(codes):,} → corp_code 매핑 {len(hit):,}종 (미매핑 {len(codes) - len(hit):,})")
    return hit


def collect_invst(limit=None):
    GOV_DIR.mkdir(parents=True, exist_ok=True)
    rows = targets()[:limit]
    if shard := os.environ.get("DART_SHARD"):  # "0/4" — 4개 프로세스로 나눠 받을 때만. 동시 4요청까지가 예의선
        i, n = (int(x) for x in shard.split("/"))
        rows = rows[i::n]
        print(f"[출자현황] shard {shard} → {len(rows):,}종")
    ok = empty = skip = 0
    fails = []
    for n, (corp, stock) in enumerate(rows, 1):
        path = GOV_DIR / f"dart_invst_{corp}_{YMD}.json"
        if path.exists():
            skip += 1
            continue
        url = ("https://opendart.fss.or.kr/api/otrCprInvstmntSttus.json"
               f"?crtfc_key={KEY}&corp_code={corp}&bsns_year={BSNS_YEAR}&reprt_code={REPRT_CODE}")
        try:
            for attempt in range(MAX_RETRY + 1):
                body = get(url).content
                j = json.loads(body)
                if j.get("status") != "020" or not BACKOFF or attempt >= MAX_RETRY:
                    break
                print(f"  .. status 020(요청제한) — {BACKOFF:.0f}초 대기 후 재시도 ({attempt + 1}/{MAX_RETRY})", flush=True)
                time.sleep(BACKOFF)
            if j.get("status") not in OK_STATUS:
                raise ValueError(f"status {j.get('status')} {j.get('message')}")
            path.write_bytes(body)
            sidecar(path, url, api="otrCprInvstmntSttus", corp_code=corp, stock_code=stock,
                    bsns_year=BSNS_YEAR, reprt_code=REPRT_CODE,
                    status=j["status"], rows=len(j.get("list") or []))
            ok += 1
            empty += not (j.get("list") or [])
        except Exception as e:
            fails.append((corp, stock, f"{type(e).__name__}: {e}"))
        time.sleep(SLEEP)
        if n % 200 == 0:
            print(f"  {n}/{len(rows)} (수집 {ok}, 그중 빈결과 {empty}, 스킵 {skip}, 실패 {len(fails)})", flush=True)
    print(f"[출자현황] 완료: 수집 {ok} (빈결과 {empty}), 스킵 {skip}, 실패 {len(fails)}")
    for f in fails[:30]:
        print("  FAIL", *f, sep="\t")


if __name__ == "__main__":
    args = sys.argv[1:]  # [건수제한] [corpcode]
    collect_corpcode()
    if "corpcode" not in args:
        collect_invst(int(args[0]) if args and args[0].isdigit() else None)
