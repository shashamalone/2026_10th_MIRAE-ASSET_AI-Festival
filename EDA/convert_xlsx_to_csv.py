"""xlsx(마스터/스키마) -> csv 변환. data/*.xlsx -> data/csv/*.csv"""
import glob, hashlib, json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "data" / "csv"
SNAPSHOT = "2026-07-11"
DOMAINS = {"PRBD01N001": "bond_kr", "PREF01N001": "etf_kr", "PREF02N001": "etf_gl", "PRFD01N001": "fund_pub"}
EXPECT_ROWS = {"bond_kr": 42394, "etf_kr": 1734, "etf_gl": 5646, "fund_pub": 95619}
EXPECT_COLS = {"bond_kr": 40, "etf_kr": 73, "etf_gl": 49, "fund_pub": 45}
PK_COLS = {"bond_kr": ["PD_NO"], "etf_kr": ["pd_itm_no"], "etf_gl": ["pd_itm_no"], "fund_pub": ["itm_no", "prfd_attr_cd"]}
SCHEMA_COLS = ["column", "pk_fk", "dtype", "name_ko", "example"]


def strip_df(df: pd.DataFrame) -> pd.DataFrame:
    """전 컬럼 str.strip() 후 빈 문자열 -> NA. sentinel 값은 건드리지 않는다."""
    df = df.apply(lambda c: c.str.strip())
    return df.where(df.ne(""), pd.NA)


def save(df: pd.DataFrame, name: str, source_file: str, sheet: str, manifest: list, strip_applied=True):
    path = OUT / f"{name}.csv"
    df.to_csv(path, encoding="utf-8-sig", lineterminator="\n", index=False)
    manifest.append({
        "file": path.name, "rows": len(df), "cols": len(df.columns),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_file": source_file, "sheet": sheet, "snapshot": SNAPSHOT,
        "strip_applied": strip_applied,
    })


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []

    for code, slug in DOMAINS.items():
        # master
        master_path = glob.glob(str(DATA / f"{code}*datarows.xlsx"))[0]
        master = pd.read_excel(master_path, sheet_name="datarows", dtype=str)
        master = strip_df(master)
        assert len(master) == EXPECT_ROWS[slug], f"{slug} rows {len(master)} != {EXPECT_ROWS[slug]}"
        assert len(master.columns) == EXPECT_COLS[slug], f"{slug} cols {len(master.columns)} != {EXPECT_COLS[slug]}"
        save(master, f"{code}_{slug}_master_{SNAPSHOT.replace('-', '')}", Path(master_path).name, "datarows", manifest)

        # round-trip check
        reloaded = pd.read_csv(OUT / f"{code}_{slug}_master_{SNAPSHOT.replace('-', '')}.csv", dtype=str, keep_default_na=False)
        reloaded = reloaded.where(reloaded.ne(""), pd.NA)
        assert reloaded.fillna("").equals(master.fillna("")), f"{slug} round-trip mismatch"

        # PK uniqueness -> record violation count in manifest, don't abort
        pk = PK_COLS[slug]
        dup_count = int(master.duplicated(subset=pk, keep=False).sum())
        manifest.append({"file": f"{code}_{slug}_master pk_check", "pk": pk, "duplicate_rows": dup_count})

        # schema
        schema_path = glob.glob(str(DATA / f"{code}*schema.xlsx"))[0]
        schema = pd.read_excel(schema_path, sheet_name="Sheet1_Schema", header=1, dtype=str)
        schema = strip_df(schema)
        schema.columns = SCHEMA_COLS[: len(schema.columns)]
        save(schema, f"{code}_{slug}_schema_{SNAPSHOT.replace('-', '')}", Path(schema_path).name, "Sheet1_Schema", manifest)

        # axis sample (title row + blank row precede header -> header=2)
        sample = pd.read_excel(schema_path, sheet_name="Sheet2_Sample", header=2, dtype=str)
        sample = strip_df(sample)
        save(sample, f"{code}_{slug}_axis_sample_{SNAPSHOT.replace('-', '')}", Path(schema_path).name, "Sheet2_Sample", manifest)

    (OUT / "_conversion_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"done. {len(manifest)} manifest entries.")


if __name__ == "__main__":
    main()
