from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "refresh_etf_holdings", ROOT / "script" / "refresh_etf_holdings.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_kodex_parser_requires_exact_response_date():
    body = json.dumps(
        {
            "pdf": {
                "gijunYMD": "20260821",
                "list": [{"itmNo": "005930", "secNm": "삼성전자", "ratio": "19.5"}],
            }
        }
    ).encode()
    rows, evidence = MODULE.parse_kodex(body, "2026-08-21")
    assert rows == [("005930", "삼성전자", "19.5")]
    assert evidence == {
        "kind": "response_field",
        "field": "pdf.gijunYMD",
        "value": "2026-08-21",
    }
    with pytest.raises(ValueError, match="response date"):
        MODULE.parse_kodex(body, "2026-08-20")


def test_ace_parser_requires_uniform_exact_response_date():
    body = json.dumps(
        {
            "pdfList": [
                {
                    "std_DT": "2026-08-21",
                    "jm_KSC_CD": "688256 C1 Equity",
                    "sec_NM": "Cambricon Technologies Corp Ltd",
                    "wg": "9.25",
                }
            ]
        }
    ).encode()
    rows, evidence = MODULE.parse_ace(body, "2026-08-21")
    assert rows[0][0] == "688256 C1 Equity"
    assert evidence["value"] == "2026-08-21"
    with pytest.raises(ValueError, match="response dates"):
        MODULE.parse_ace(body, "2026-08-20")


def test_tiger_parser_preserves_codes_and_uses_dated_endpoint_evidence():
    body = b"""
    <tr data-tot-cnt="1"><td>688256 C1 Equity</td><td>Cambricon</td>
      <td>100</td><td>5000</td><td>9.25</td><td>-</td></tr>
    """
    rows, evidence = MODULE.parse_tiger(body, "2026-08-21")
    assert rows == [("688256 C1 Equity", "Cambricon", "9.25")]
    assert evidence["parameter"] == "fixDate"
    assert evidence["response_row_count"] == 1


def test_rise_parser_anchors_on_isin_and_excludes_cash():
    body = b"""
    <tr><td></td><td>1</td><td>US14167L1035</td><td>Cambricon</td>
      <td>2</td><td>4.5</td><td>-</td></tr>
    <tr><td></td><td>2</td><td>CASH00000001</td><td>cash</td>
      <td>1</td><td>100</td><td>-</td></tr>
    """
    rows, evidence = MODULE.parse_rise(body, "2026-08-21")
    assert rows == [("US14167L1035", "Cambricon", "4.5")]
    assert evidence["parameter"] == "searchDate"


def test_master_targets_only_selected_branded_etfs(tmp_path: Path):
    master = tmp_path / "master.csv"
    pd.DataFrame(
        [
            {"pd_grp_no": "ETF", "pd_abrv_nm": "TIGER one", "pd_itm_no": "KR7000000001", "pd_itm_no_ma": "A123456"},
            {"pd_grp_no": "ETN", "pd_abrv_nm": "TIGER note", "pd_itm_no": "KR7000000002", "pd_itm_no_ma": "A123457"},
            {"pd_grp_no": "ETF", "pd_abrv_nm": "ACE two", "pd_itm_no": "KR7000000003", "pd_itm_no_ma": "A123458"},
        ]
    ).to_csv(master, index=False)
    targets = MODULE.load_targets(master, ["TIGER"])
    assert [(item.brand, item.ticker) for item in targets] == [("TIGER", "123456")]


def test_relation_is_sorted_and_date_locked():
    records = [
        (
            MODULE.Target("TIGER", "KR7000000001", "123456", "TIGER one"),
            [("Z US Equity", "Z", "2"), ("005930", "삼성전자", "1")],
            {},
        )
    ]
    relation = MODULE.build_relation(records, "2026-08-21")
    assert relation["holding_code_raw"].tolist() == ["005930", "Z US Equity"]
    assert relation["holding_code_type"].tolist() == ["ticker6", "bloomberg"]
    assert relation["as_of"].unique().tolist() == ["2026-08-21"]


def test_shared_data_outputs_are_rejected(tmp_path: Path):
    with pytest.raises(ValueError, match="refusing"):
        MODULE.safe_output_dir(tmp_path / "data" / "data" / "run")
    with pytest.raises(ValueError, match="refusing"):
        MODULE.safe_output_dir(tmp_path / "data" / "snapshots" / "run")


def test_kodex_mapping_paginates_when_publisher_caps_page_size(monkeypatch):
    class Response:
        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    pages = iter(
        [
            Response(
                [
                    {"stkTicker": "000001", "fId": "A", "totalCnt": "3"},
                    {"stkTicker": "000002", "fId": "B", "totalCnt": "3"},
                ]
            ),
            Response([{"stkTicker": "000003", "fId": "C", "totalCnt": "3"}]),
        ]
    )
    collector = MODULE.Collector(timeout=1, retries=0, backoff=0, pause=0)
    monkeypatch.setattr(collector, "get", lambda _url: next(pages))
    assert collector.kodex_map() == {"000001": "A", "000002": "B", "000003": "C"}


def test_products_ended_by_snapshot_are_not_collection_failures():
    active = MODULE.Target("ACE", "KR7000000001", "000001", "ACE active", "99991231")
    ended = MODULE.Target("ACE", "KR7000000002", "000002", "ACE ended", "20260820")
    unknown = MODULE.Target("ACE", "KR7000000003", "000003", "ACE unknown", "")
    included, excluded = MODULE.split_active_targets([active, ended, unknown], "2026-08-21")
    assert included == [active, unknown]
    assert excluded == [ended]
