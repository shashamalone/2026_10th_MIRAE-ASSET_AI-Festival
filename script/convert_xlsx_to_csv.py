"""xlsx(마스터/스키마) -> csv 변환. data_raw/*.xlsx -> data/csv/*.csv

2026-08-24 배포본부터 원천 레이아웃이 바뀌었다.
  - 위치: data/*.xlsx -> data_raw/*.xlsx, 파일명 소문자 + `_data`/`_schema`
  - 시트: datarows/Sheet1_Schema/Sheet2_Sample -> data/schema (Sample 시트 폐지)
  - 스키마 컬럼: column/pk_fk/dtype/name_ko/example -> 순번/컬럼명/데이터타입/Nullable/컬럼코멘트
"""
import glob, hashlib, json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW, OUT = ROOT / "data_raw", ROOT / "data" / "csv"
SNAPSHOT = "2026-08-24"
DOMAINS = {"prbd01n001": "bond_kr", "pref01n001": "etf_kr", "pref02n001": "etf_gl", "prfd01n001": "fund_pub"}
PK_COLS = {"bond_kr": ["pd_no"], "etf_kr": ["pd_itm_no"], "etf_gl": ["pd_itm_no"], "fund_pub": ["itm_no"]}
SCHEMA_COLS = ["seq", "column", "dtype", "nullable", "comment_ko"]


def strip_df(df: pd.DataFrame) -> pd.DataFrame:
    """전 컬럼 str.strip() 후 빈 문자열 -> NA. sentinel 값은 건드리지 않는다."""
    df = df.apply(lambda c: c.str.strip())
    return df.where(df.ne(""), pd.NA)


def save(df: pd.DataFrame, name: str, source_file: str, sheet: str, manifest: list):
    path = OUT / f"{name}.csv"
    df.to_csv(path, encoding="utf-8-sig", lineterminator="\n", index=False)
    manifest.append({
        "file": path.name, "rows": len(df), "cols": len(df.columns),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_file": source_file, "sheet": sheet, "snapshot": SNAPSHOT, "strip_applied": True,
    })


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest, stamp = [], SNAPSHOT.replace("-", "")

    for code, slug in DOMAINS.items():
        master_path = glob.glob(str(RAW / f"{code}*_data.xlsx"))[0]
        master = strip_df(pd.read_excel(master_path, sheet_name="data", dtype=str))
        name = f"{code.upper()}_{slug}_master_{stamp}"
        save(master, name, Path(master_path).name, "data", manifest)

        reloaded = pd.read_csv(OUT / f"{name}.csv", dtype=str, keep_default_na=False)
        reloaded = reloaded.where(reloaded.ne(""), pd.NA)
        assert reloaded.fillna("").equals(master.fillna("")), f"{slug} round-trip mismatch"

        pk = PK_COLS[slug]
        manifest.append({"file": f"{name} pk_check", "pk": pk,
                         "duplicate_rows": int(master.duplicated(subset=pk, keep=False).sum())})

        schema_path = glob.glob(str(RAW / f"{code}*_schema.xlsx"))[0]
        schema = strip_df(pd.read_excel(schema_path, sheet_name="schema", dtype=str))
        schema.columns = SCHEMA_COLS[: len(schema.columns)]
        assert set(schema["column"]) == set(master.columns), f"{slug} schema/master column mismatch"
        save(schema, f"{code.upper()}_{slug}_schema_{stamp}", Path(schema_path).name, "schema", manifest)

    (OUT / "_conversion_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"done. {len(manifest)} manifest entries.")


if __name__ == "__main__":
    main()
