# 외부 수집 원천의 as_of 기준일 검증 — 대회 규칙상 2026-08-24 이후 데이터는 미래정보 유출이다.
# 사이드카 규칙: 원본 파일명 전체에 .meta.json을 덧붙인다 (a.xls → a.xls.meta.json)
import glob
import json
import os
import sys

EXTERNAL = "data/external"
CUTOFF = "2026-08-24"
REQUIRED = {"source", "as_of", "retrieved_at", "url"}


def norm(d):
    """20260710 / 2026.07.10 / 2026-07-10 → 2026-07-10"""
    d = d.strip().replace(".", "-").replace("/", "-")
    if len(d) == 8 and d.isdigit():
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return d


problems = []
metas = glob.glob(f"{EXTERNAL}/**/*.meta.json", recursive=True)

# 사이드카 없는 원본 파일 적발 (메타 파일 자신은 제외)
for path in glob.glob(f"{EXTERNAL}/**/*", recursive=True):
    if os.path.isfile(path) and not path.endswith(".meta.json") and f"{path}.meta.json" not in metas:
        problems.append(f"사이드카 없음: {path}")

for m in metas:
    src = m[: -len(".meta.json")]
    try:
        meta = json.load(open(m, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        problems.append(f"사이드카 파싱 실패: {m} ({e})")
        continue
    if missing := REQUIRED - meta.keys():
        problems.append(f"필수 키 누락 {sorted(missing)}: {m}")
    if not os.path.exists(src):
        problems.append(f"원본 없음: {src}")
    if (as_of := norm(str(meta.get("as_of", "")))) > CUTOFF:
        problems.append(f"as_of 기준일 초과 ({as_of} > {CUTOFF}): {src}")
    if "key" in meta.get("url", "").lower() and "***" not in meta.get("url", ""):
        problems.append(f"url에 인증키가 마스킹 없이 노출된 것으로 보임: {m}")

print(f"검사: 원천 {len(metas)}건 (기준일 {CUTOFF} 이하)")
for p in problems:
    print("  FAIL", p)
if problems:
    sys.exit(1)
print("OK — 전 항목 통과")
