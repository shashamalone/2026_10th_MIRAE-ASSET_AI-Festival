# data/ 하위 CSV를 스캔해 DATA_INVENTORY.md 생성.
# 출력은 결정적(생성 시각·랜덤 요소 없음)이어야 한다 — git diff가 곧 데이터 구조 변경 이력이기 때문.
import glob
import os

import pandas as pd

OUT = "docs/DATA_INVENTORY.md"
LAYERS = [("data/csv", "원본"), ("data/enriched", "파생"), ("data/relations", "관계"), ("data/external", "외부")]
BUILDER = {  # 파일 → 생성 스크립트. 자동 추론이 불가능해 하드코딩한다.
    "fund_pub_dedup.csv": "build_fund_dedup.py",
    "etf_kr_enriched.csv": "build_etf_enrichment.py",
    "bond_kr_enriched.csv": "build_bond_enrichment.py",
    "etf_theme.csv": "build_etf_enrichment.py",
    "etf_holding.csv": "build_etf_holding.py",
    "company_master.csv": "build_company_relations.py",
    "company_subsidiary.csv": "build_company_relations.py",
}

files = [(p, layer) for d, layer in LAYERS for p in sorted(glob.glob(f"{d}/*.csv"))]
frames = {p: pd.read_csv(p, dtype=str, keep_default_na=False) for p, _ in files}

lines = [
    "# 데이터 인벤토리",
    "",
    "이 파일은 `EDA/build_data_inventory.py`가 생성한다. **직접 편집하지 말 것.**",
    "데이터 구조 변경 시 재실행 후 커밋하면 `git diff`가 그대로 변경 이력이 된다.",
    "(생성 시각을 넣지 않는 이유: 매번 바뀌면 diff가 노이즈로 덮여 변경 추적이 불가능해진다.)",
    "",
    "## 계층별 요약",
    "",
    "| 파일 | 계층 | 행수 | 컬럼수 | 생성 스크립트 |",
    "|---|---|---|---|---|",
]
for p, layer in files:
    df = frames[p]
    lines.append(f"| `{p}` | {layer} | {len(df):,} | {len(df.columns)} | "
                 f"{'`EDA/' + BUILDER[os.path.basename(p)] + '`' if os.path.basename(p) in BUILDER else '—'} |")

lines += ["", "## 파일별 컬럼", "", "결측률은 빈 문자열 기준. 값 예시는 문서 비대화를 막기 위해 싣지 않는다."]
for p, _ in files:
    df = frames[p]
    lines += ["", f"### `{p}`", "", "| 컬럼 | 결측률 | 고유값수 |", "|---|---|---|"]
    for c in df.columns:
        lines.append(f"| `{c}` | {df[c].eq('').mean() * 100:.1f}% | {df[c].nunique():,} |")

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(lines) + "\n")
print(f"{OUT}: {len(files)}개 파일, {len(lines)}줄")
