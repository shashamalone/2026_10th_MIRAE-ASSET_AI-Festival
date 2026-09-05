"""
rdb_schema.py

RDB(PostgreSQL) 4개 테이블(채권, 국내ETF, 해외ETF, 펀드)에 대한 정적
참조 정보를 모아 둔 파일이다. 실제로 동작하는 로직(파일 I/O, DB 연결,
API 호출)은 전혀 없다. "이 도메인은 이 테이블이고, 컬럼은 이렇고,
개념은 이 컬럼에 대응한다"는 매핑을 미리 적어 두고, 다른 노드가 상황에
따라 골라서 import해 쓰는 참조 데이터다.

[이 파일의 데이터 기준일: 2026-08-24 배포본]
이전 버전은 2026-07-11 스냅샷 기준이었고, 이번에 주최측이 재배포한
prbd01n001 / pref01n001 / pref02n001 / prfd01n001 의 data.xlsx와
schema.xlsx를 전부 다시 프로파일링해서 처음부터 다시 작성했다.
두 배포본은 컬럼 구성과 행 수가 모두 크게 달라서, 이전 파일 내용을
부분 수정하는 방식으로는 맞출 수 없었다.

  도메인      이전(07-11)          이번(08-24)         비고
  ---------  ------------------  ------------------  ------------------
  채권        42,394행 / 40컬럼    21,882행 / 58컬럼   컬럼명이 소문자로 바뀜
  국내ETF     1,734행 / 70컬럼     1,780행 / 98컬럼    ref_/du_vlty_/pd_dvid_ 계열 신설
  해외ETF     5,646행 / 49컬럼     6,037행 / 49컬럼    구성 거의 동일
  펀드        95,619행 / 45컬럼    23,676행 / 75컬럼   행이 1/4로 줄고 컬럼은 늘어남

[반드시 알아야 할 변경 5가지]

1. 채권 테이블의 컬럼명이 전부 소문자로 바뀌었다. 이전 파일은
   PD_NO, CRD_GRD처럼 대문자로 적혀 있었는데, 새 schema.xlsx는
   pd_no, crd_grd다. Postgres는 따옴표 없는 식별자를 소문자로 접기
   때문에 대문자로 적어도 대체로 동작하지만, 스키마 문서와 실제
   컬럼명이 다르면 LLM이 SQL을 쓸 때 혼동하므로 전부 소문자로 통일했다.

2. 채권의 "판매가능여부" 개념을 카탈로그에서 삭제했다. 주최측이
   buyable_quantity 컬럼은 값이 무효이니 신경 쓰지 말고, 상장폐지나
   리스팅 종료 종목을 제외한 나머지는 전부 구매가능하다고 가정하라고
   공지했다. 실제로 이 컬럼은 21,882행 중 634행(2.9%)에만 값이 있고
   그 634행조차 절반 이상이 0이다. 이 조건을 걸면 후보군이 1만 건에서
   18건으로 잘려 나가 사실상 오답이 된다. 채권 테이블에는 상장폐지
   여부를 나타내는 컬럼 자체가 없으므로, 판매가능 조건은 아예 걸지
   않는 것이 공지에 맞는 처리다. 대신 아래 DOMAIN_SALE_POLICY에
   도메인별 처리 방침을 명시해 두었다.

3. 채권에 pd_risk_nm(상품위험등급명)이 새로 생겼다. 국내ETF와 같은
   "매우높은위험(1등급)~매우낮은위험(6등급)" 체계이고 결측이 없다.
   이전 파일에서 위험등급으로 쓰던 pd_risk_gcd는 0~6 원문 코드인데,
   이제 pd_risk_nm이 있으므로 이름 컬럼을 ordinal로 쓰는 것이 맞다.

4. 채권은 한 종목(pd_no)이 여러 행으로 나올 수 있다. info_seq가
   "동일 종목/시장/기준일 내 판매 LOT 구분 순번"이고, 21,882행 중
   고유 pd_no는 20,497개다(307개 종목이 2행, 1개가 3행). 종목 개수를
   세거나 상위 N개를 뽑을 때 DISTINCT나 GROUP BY 없이 그냥 세면
   중복 계상된다. 이전 배포본에는 없던 새 이슈다.

5. 펀드의 사모 비중이 완전히 달라졌다. 이전에는 공모 95,451 대
   사모 102건이라 "사실상 공모펀드 위주"라고 적었는데, 이번 배포본은
   공모 14,716 대 사모 8,960으로 사모가 38%다. 과제명이 공모펀드인
   만큼 공모/사모 구분 조건이 실제로 필요해졌다.

[값이 0이거나 비어 있는 데이터에 대한 주최측 방침]
0이나 결측은 오류가 아니라 의도된 값이며, 그 값을 조회하는 질의에는
값을 빼고 보여주거나 "그 값은 없다"고 응답하면 된다고 공지되었다.
그래서 아래 note에 "값이 있는 행 전부 0.0" / "N% 결측" 같은 기록을
남길 때, 그것을 근거로 임의의 대체값을 채우지 말고 결측은 결측대로
답변에 드러내야 한다.

[섹터/테마를 RDB로 풀 수 없다는 점은 이번에도 동일]
국내ETF의 pd_sect_nm(섹터명) 컬럼은 이번 배포본에서 아예 사라졌고,
pd_sect_cd만 남았는데 값이 2/3/4/8/9라는 숫자뿐이고 이름 매핑 컬럼이
테이블 안에 없다. 반도체, 2차전지 같은 테마는 여전히 상품명(pd_nm)
텍스트 안에만 자연어로 들어 있다. 따라서 "반도체 ETF" 같은 조건은
등호 비교로 처리할 수 없고, pd_nm에 대한 contains(LIKE '%반도체%')
매칭이거나 Graph/Vector 쪽으로 넘겨야 한다. ATTRIBUTE_CATALOG에
"섹터"를 넣지 않은 이유가 이것이다. 다만 이번에는 국내ETF에
ref_geo_focus(refinitiv 투자지역)와 ref_ast_type(자산유형)이 새로
생겨서 지역/자산군 축은 두 벌(wu_ 계열, ref_ 계열)이 되었다.
wu_ 계열이 한글이고 결측이 없어 기본값으로 삼았다.

[해외ETF cu_strtegy는 이번에도 서술형 텍스트]
6,037건 중 99.8%에 값이 있는 영문 자유서술 문장이다. "이 ETF의 운용
전략을 설명해줘" 같은 narrative 질문은 Vector 검색 없이 이 컬럼 하나로
답이 될 수 있다.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field


@dataclass
class AttributeSpec:
    """개념 하나가 실제로 어느 컬럼에 대응하는지, 그 값을 어떻게 다뤄야
    하는지에 대한 규칙."""

    column: str
    value_type: str  # "numeric" | "categorical" | "ordinal" | "numeric_flag" | "date_yyyymmdd_numeric" | "text"
    note: str = ""
    value_order: list[str] = field(default_factory=list)
    # ordinal일 때만 쓴다. 반드시 오름차순(자연어로 "더 크다/좋다/높다"라고
    # 표현하는 방향으로 index가 커지는 순서)으로 채운다. gte(이상)는
    # value_order[idx:], lte(이하)는 value_order[:idx+1]이 되도록
    # utils.resolve_ordinal_matched_values가 이 값을 그대로 슬라이싱한다.
    # 이 방향을 반대로(내림차순) 넣으면 이상/이하 결과가 뒤집힌다.
    known_values: list[str] = field(default_factory=list)  # categorical일 때 참고용
    true_condition: str = ""  # numeric_flag일 때: "> 0" 같은 조건

    # ------------------------------------------------------------------
    # 이 컬럼이 raw.* 기본 테이블이 아니라 enriched.* 같은 보강 테이블에
    # 있을 때만 세 필드를 채운다. 셋 다 비어 있으면(기본값) 예전과 완전히
    # 같게 동작한다 - 기존 카탈로그 항목은 전부 이 필드들을 안 쓰므로
    # 하위호환이 깨지지 않는다.
    #
    #   join_table: 보강 테이블 전체 이름(스키마 포함). 예: "enriched.product_metric"
    #               2홉 조인이 필요하면 파생 테이블 "(SELECT ...)"을 그대로 넣어도
    #               된다 - utils가 "LEFT JOIN {join_table} AS {alias} ON {on}"으로
    #               펼치기 때문에 서브쿼리도 문법적으로 성립한다("총보수율" 참고).
    #   join_alias: 그 테이블에 붙일 별칭. 예: "pm"
    #   join_on:    JOIN 조건. 기본 테이블은 항상 "base"로 별칭이 고정된다.
    #               예: "pm.pd_itm_no = base.pd_itm_no"
    #
    # column 값 자체도 join_table을 쓸 때는 별칭을 붙여서 적는다(예:
    # "pm.expense_ratio"). 기본 테이블 컬럼은 지금처럼 별칭 없이 적으면
    # 되고(예: "pd_net_tamt"), utils.format_resolved_schema가 JOIN이 하나
    # 라도 있는 쿼리에서만 자동으로 "base." 접두어를 붙여 준다.
    join_table: str = ""
    join_alias: str = ""
    join_on: str = ""

    # 이 컬럼이 회사/기관 이름을 담는 컬럼이면 True. "SK하이닉스"(질문에서
    # 흔히 쓰는 영문+한글 혼용 약칭)와 "에스케이하이닉스(주)"(원천 데이터의
    # 순한글 정식 표기) 같은 표기 차이 때문에 exact match가 0건으로
    # 실패하는 사고가 실측으로 확인됐다(2026-09-02). True로 표시된 개념은
    # utils.build_resolved_schema가 graph_ids.expand_organization_aliases로
    # 검증된 약칭 표(에스케이<->SK 등)만 써서 표기 변형 후보를 만들고,
    # SQL 생성 LLM에는 이미 계산된 IN(...) 후보 목록으로 넘긴다 - 편집거리나
    # 유사도로 "비슷한 이름"을 지어내는 것이 아니라, 검증된 표 안의 치환만
    # 쓰므로 절대 규칙(엉뚱한 상품/회사 대체 금지)을 위반하지 않는다.
    is_organization_name: bool = False


# ---------------------------------------------------------------------------
# 데이터 기준일. 질의에 "현재", "최신"이 나와도 이 날짜가 사실상의 today다.
# ---------------------------------------------------------------------------
DATA_SNAPSHOT_DATE = "2026-08-24"
# 테이블 안에 박혀 있는 기준일 컬럼의 실제 값(참고용).
#   채권      info_base_dt = 20260821, pd_std_info_update = 20260821
#   국내ETF   wu_upt_dt = 20260821, ref_base_dt = 20260822, cu_upt_dt 최신 20260824
#   해외ETF   cu_upt_dt = 20260822, du_nav_base_dt = 20260822
#   펀드      fd_price_bas_dt 최신 = 20260821


# ---------------------------------------------------------------------------
# 도메인 <-> 실제 테이블 매핑
# ---------------------------------------------------------------------------
DOMAIN_TABLE_INFO: dict[str, dict[str, str]] = {
    "채권": {"table": "raw.prbd01n001"},
    "국내ETF": {"table": "raw.pref01n001"},
    "해외ETF": {"table": "raw.pref02n001"},
    "펀드": {"table": "raw.prfd01n001"},
}


# ---------------------------------------------------------------------------
# 보강(enriched) 테이블 참조 정보. AttributeSpec.join_table에 실제로 쓰이는
# 값들을 여기 한곳에 모아 문서화한다(코드가 이 딕셔너리를 직접 읽지는
# 않는다 - AttributeSpec 쪽에 이미 필요한 값이 다 박혀 있다. 이건 어떤
# 보강 테이블이 왜 존재하는지 사람이 한눈에 보기 위한 참조용이다).
#
# [T-115 / 2026-09-05 실측 정정]
# 이 아래 내용은 2026-08-31 기준으로 쓰였는데, 그때 참조한 두 테이블은
# 2026-09-05 현재 배포된 DB(information_schema)에 **존재하지 않는다**.
#
#   당시 기록                  현재 live
#   -------------------------  --------------------------------------------
#   enriched.etf_kr_enriched   없음. enriched.etf_kr (10컬럼) 이 그 자리다.
#   enriched.bond_kr_enriched  없음. enriched.bond_kr_offer / bond_kr_product
#
# 더 중요한 건 이름이 아니라 데이터다. etf_kr_enriched 가 제공하던 LSEG 보강
# (charge_rt_final)이 현재 배포본에는 없고, enriched.etf_kr 에도 보수 컬럼이
# 아예 없다. 총보수율은 이제 enriched.product_metric 의 EXPENSE_RATIO 로만
# 얻을 수 있는데 국내ETF 커버리지가 67/1,235 = 5.4% 다(아래 "총보수율" 참고).
# 즉 이름 드리프트가 아니라 커버리지 회귀이며, 보강 복원은 데이터 파이프라인
# 쪽 별도 과제다.
#
# 이 딕셔너리는 사람이 읽는 참조용이지만(코드는 AttributeSpec 을 직접 읽는다),
# 틀린 참조를 남겨 두면 다음 사람이 또 같은 함정에 빠진다. 그래서 live 기준
# 으로 고쳐 적고, 사라진 것은 사라졌다고 명시한다.
# ---------------------------------------------------------------------------
ENRICHED_TABLE_INFO: dict[str, dict[str, str]] = {
    "국내ETF": {
        "table": "enriched.etf_kr",
        "join_key": "product_id (pd_itm_no 로도 조인 가능)",
        "status": "존재. 단 보수 컬럼 없음 - 총보수율은 product_metric 경유",
        "note": (
            "10컬럼(product_id, pd_itm_no, name, ticker, isin, manager, "
            "base_index, currency, listing_date, delisting_date). "
            "과거 etf_kr_enriched 가 주던 charge_rt_final/replication/"
            "base_market/base_asset/hedge_type 보강은 현재 배포본에 없다."
        ),
    },
    "채권": {
        "table": "enriched.bond_kr_offer, enriched.bond_kr_product",
        "join_key": "product_id",
        "status": "존재(이름 변경). 아직 카탈로그 미연결",
        "note": (
            "과거 bond_kr_enriched 로 기록됐던 보강이 offer/product 두 테이블로 "
            "분리됐다. is_sellable/crd_grd_rank 가 현재 스키마에도 있는지는 "
            "확인하지 않았다 - 연결 전에 information_schema 로 먼저 검증할 것."
        ),
    },
}


# ---------------------------------------------------------------------------
# "판매 가능"을 도메인별로 어떻게 처리할지에 대한 방침.
#
# 주최측 공지: buyable_quantity 값은 무효이고, 상장폐지 혹은 리스팅 종료
# 종목을 제외한 나머지는 전부 "구매가능"하다고 가정한다.
#
# 질문에 "판매 가능한", "살 수 있는" 같은 표현이 나왔을 때 SQL에 조건을
# 걸어야 할지 말지를 여기서 정한다. plan/SQL 생성 단계가 이 값을 읽어
# 조건을 넣거나 뺀다.
# ---------------------------------------------------------------------------
DOMAIN_SALE_POLICY: dict[str, dict[str, str]] = {
    "채권": {
        "mode": "no_filter",
        "reason": (
            "buyable_quantity는 주최측이 무효라고 공지한 컬럼이고(21,882행 중 "
            "634행만 값이 있으며 그중 다수가 0), 이 테이블에는 상장폐지나 "
            "거래종료를 나타내는 컬럼 자체가 없다. 따라서 채권은 '판매 가능' "
            "조건을 SQL에 걸지 않고 전 종목을 구매가능으로 간주한다."
        ),
    },
    "국내ETF": {
        "mode": "column_filter",
        "column": "pd_sale_yn",
        "condition": "pd_sale_yn = '1'",
        "reason": (
            "pd_sale_yn=0인 246건 중 245건이 pd_lste_dt(거래종료일자)가 "
            "99991231이 아닌(= 이미 상장폐지/거래종료 예정이 잡힌) 종목이라, "
            "이 컬럼이 사실상 공지의 '상장폐지 혹은 리스팅 종료' 조건과 "
            "일치한다. 더 엄밀히 하려면 pd_lste_dt <> 99991231 조건을 "
            "직접 걸어도 결과가 거의 같다."
        ),
    },
    "해외ETF": {
        "mode": "no_filter",
        "reason": (
            "pd_sale_yn이 값 있는 행 전부 1.0이고 pd_tr_yn도 전부 0.0이라 "
            "변별력이 0이다. 조건을 걸어도 아무것도 걸러지지 않으므로 "
            "넣지 않는다."
        ),
    },
    "펀드": {
        "mode": "column_filter",
        "column": "sale_yn",
        "condition": "sale_yn = '판매중'",
        "reason": (
            "판매중 10,962건 / 판매완료 12,714건으로 변별력이 크고, 텍스트 "
            "상태값이라 의미가 분명하다. 다른 도메인과 달리 0/1 플래그가 아니다."
        ),
    },
}


# ---------------------------------------------------------------------------
# 원시 컬럼 스키마: schema.xlsx의 컬럼명/타입/코멘트 + data.xlsx 실측 기반 설명
# ---------------------------------------------------------------------------
RDB_SCHEMA: dict[str, dict] = {}

# --- 채권 (raw.prbd01n001, 21,882행 / 20,497 고유 종목) ---------------------
RDB_SCHEMA["채권"] = {
    "table": DOMAIN_TABLE_INFO["채권"]["table"],
    "type": "object",
    "properties": {
        # 식별/명칭
        "pd_no": {"type": "text", "description": "상품번호(채권 종목번호, 예: KR60143NEFC6). 결측 없음. 단 info_seq 때문에 한 종목이 여러 행일 수 있어 유일값이 아니다(21,882행 중 20,497개)."},
        "info_seq": {"type": "bigint", "description": "동일 종목/시장/기준일 내 판매 LOT 구분 순번(1/2/3). 1이 21,574행, 2가 307행, 3이 1행. 종목 단위로 세려면 DISTINCT pd_no 또는 info_seq=1 조건이 필요하다."},
        "info_base_dt": {"type": "text", "description": "판매/민평 공통 기준일. 전 행이 20260821 단일값."},
        "pd_nm": {"type": "text", "description": "상품명(채권명). 결측 없음. 발행사명과 회차가 붙은 형태(예: 경기주택도시공사24-10-83(지))."},
        "pd_abrv_nm": {"type": "text", "description": "상품약어명. 뒤쪽에 공백 패딩이 붙어 있어 TRIM 비교를 권장."},
        "pd_eng_nm": {"type": "text", "description": "상품영문명."},
        "pd_abrv_eng_nm": {"type": "text", "description": "상품영문약어명. 공백 패딩 있음."},
        "pd_pbcm": {"type": "text", "description": "발행기관/발행자명(1,837종). 공백 패딩이 붙어 있어 TRIM 비교를 권장. 0.7% 결측."},
        "pd_ctry_cd": {"type": "text", "description": "국가코드(종목번호 앞 2자리). 값은 KR/XS 두 가지."},

        # 분류
        "std_pd_mcls_nm": {"type": "text", "description": "상품중분류명. 값은 회사채(12,865)/특수채(6,177)/국공채(2,840) 세 가지뿐이다. 이전 배포본에 있던 개인투자용국채와 외화채권 분류는 이번 데이터에 없다."},
        "std_pd_scls_nm": {"type": "text", "description": "상품소분류명(13종: 일반사채 12,747, 공사채 4,208, 지역개발 1,679, 특수은행채 1,324, 은행채 703, 도시철도 452, 국고채 371, 국민주택 210, 공모지방채 108, 중앙은행채 33, 기타사채 27, 기타국채 14, 물가채 6)."},
        "bd_knd": {"type": "text", "description": "예탁원 기준 채권종류명(41종). 뒤쪽 공백 패딩이 있어 TRIM 비교를 권장. 0.7% 결측."},
        "bd_ofr_tcd": {"type": "text", "description": "모집구분. 값은 공모(19,875)/사모(2,007) 두 가지. 결측 없음."},
        "bd_inrt_tcd": {"type": "text", "description": "금리구분. 값은 고정금리(20,904)/변동금리(830)/고정+변동금리(148). 결측 없음."},
        "bd_intp_tcd": {"type": "text", "description": "이자지급구분. 값은 이표채(18,059)/복리채(2,867)/할인채(689)/단리채(267). 결측 없음."},
        "pd_exg_mkt": {"type": "text", "description": "거래구분. 값은 장내/장외 두 가지. 결측 없음."},
        "curr_cd": {"type": "text", "description": "통화코드. 21,881행이 KRW이고 '000'이라는 오류값이 1건 있다. 이번 배포본에는 USD/EUR/JPY 채권이 없다."},

        # 등급
        "crd_grd": {"type": "text", "description": "적용신용등급(15종: AAA 8,722 / AA- 3,530 / AA+ 2,543 / AA0 1,241 / A0 737 / A+ 678 / A- 124 / BBB+ 109 / C0 103 / BBB0 45 / BB0 13 / BBB- 7 / B- 5 / BB- 3 / B+ 2). 18.4%(4,020건) 결측. 이전 배포본(41.6% 결측)보다 채움률이 크게 좋아졌다."},
        "crd_grd_dt": {"type": "text", "description": "신용등급 적용일자(YYYYMMDD 숫자). 등급이 바뀌지 않으면 과거 일자로 유지될 수 있다. 18.3% 결측."},
        "pd_risk_gcd": {"type": "text", "description": "상품위험등급 원문 코드(11~16 및 0). 11이 1등급, 16이 6등급이고 0은 '해당없음'(19건). 결측 없음."},
        "pd_risk_nm": {"type": "text", "description": "상품위험등급명(7종: 낮은위험(5등급) 9,849 / 매우낮은위험(6등급) 8,929 / 매우높은위험(1등급) 1,441 / 보통위험(4등급) 1,424 / 다소높은위험(3등급) 146 / 높은위험(2등급) 74 / 해당없음 19). 결측 없음. 이전 배포본에는 없던 컬럼이다."},

        # 금액/일자
        "isu_bal_amt": {"type": "double precision", "description": "발행잔액(원). 결측 없음."},
        "bd_tisu_a": {"type": "numeric(26,8)", "description": "총발행금액(원). 결측 없음. isu_bal_amt(잔액)와 다른 개념이다."},
        "isu_dt": {"type": "text", "description": "발행일자. 문서 타입은 text지만 실제 값은 YYYYMMDD 숫자(예: 20251223.0). 결측 없음."},
        "mat_dt": {"type": "text", "description": "상환일자(영구채는 1차 콜행사개시일). 문서 타입은 text지만 실제 값은 YYYYMMDD 숫자. 결측 없음."},
        "remaining_days": {"type": "double precision", "description": "잔존일수(일 단위, 이미 계산되어 있음). 결측 없음(이전 배포본은 25.1% 결측이었다). mat_dt로 다시 계산할 필요 없다."},
        "pd_std_info_update": {"type": "text", "description": "민평정보 기준일/최근 업데이트 일자. 전 행이 20260821 단일값."},

        # 금리/수익률
        "srfc_irt": {"type": "double precision", "description": "표면이자율/쿠폰금리(%). 결측 없음."},
        "applied_yield": {"type": "double precision", "description": "민평수익률/민평금리(%). 결측 없음. 이 도메인에서 가장 신뢰할 만한 수익률 컬럼이다."},
        "ndy_applied_yield": {"type": "double precision", "description": "익일 민평수익률/민평금리(%). 0.1% 결측."},
        "exg_close_yield": {"type": "double precision", "description": "장내 종가수익률(%). 18.9% 결측이고 값이 있는 행 중에도 0.0이 다수다."},
        "exrt_grte_ern_r": {"type": "numeric(20,12)", "description": "만기보장수익률. 19종뿐이고 대부분 0.0이라 사실상 특수 목적 컬럼이다."},
        "exrt_grte_ern_r_tcd": {"type": "text", "description": "만기보장수익률구분코드(99가 21,338건으로 대부분, 나머지 1~5가 소수)."},
        "exrt_rpy_r": {"type": "numeric(20,12)", "description": "만기상환율(%). 대부분 100.0."},

        # 판매 관련(대부분 결측 - 아래 buyable_quantity 설명 참고)
        "buy_yield": {"type": "double precision", "description": "매수수익률/매수금리(%). 97.1% 결측(634행에만 값 존재). 정렬/필터에 쓰면 대부분의 종목이 탈락한다."},
        "buyable_quantity": {"type": "double precision", "description": "매수가능수량. 97.1% 결측. 주최측이 이 컬럼 값은 무효라고 공지했으므로 '판매 가능' 판단에 절대 쓰지 않는다(DOMAIN_SALE_POLICY 참고)."},
        "trade_price": {"type": "double precision", "description": "매매단가(표준투입단가). 97.1% 결측."},
        "sale_yield_base_dt": {"type": "text", "description": "판매수익률 기준일. 97.1% 결측이고 값이 있는 행은 전부 20260821."},
        "bdbns_abl_chnl_nm": {"type": "text", "description": "채권매매가능채널구분명. 97.1% 결측이고 값이 있는 행은 전부 '온오프 겸용' 단일값이라 변별력이 없다."},
        "bdbns_abl_chnl_tcd": {"type": "text", "description": "채권매매가능채널구분코드. 97.1% 결측, 값은 0.0 단일값."},
        "after_tax_yield": {"type": "double precision", "description": "개인 세후 운용수익률(%). 97.1% 결측."},
        "corp_pretax_yield": {"type": "double precision", "description": "법인 세전 투자수익률(%). 97.1% 결측."},
        "corp_after_tax_yield": {"type": "double precision", "description": "법인 세후 투자수익률(%). 97.1% 결측."},
        "pref_tax_yield": {"type": "double precision", "description": "세금우대 세후 운용수익률(%). 97.1% 결측."},
        "avg_annual_tax_yield": {"type": "double precision", "description": "세후 연평균수익률(%). 97.1% 결측이고 값이 있는 행 전부 0.0이라 사실상 미사용."},
        "depo_equiv_yield_154": {"type": "double precision", "description": "예금환산수익률(세율 15.4% 기준). 97.1% 결측."},
        "depo_equiv_yield_495": {"type": "double precision", "description": "은행환산수익률(세율 49.5% 기준). 97.1% 결측."},

        # 가격/리스크 지표
        "eval_price": {"type": "double precision", "description": "평가일단가(Clean Price 성격). 결측 없음."},
        "dirty": {"type": "double precision", "description": "이자부단가(Dirty Price). 0.1% 결측."},
        "dur": {"type": "double precision", "description": "듀레이션(년). 0.1% 결측(이전 배포본은 31.6% 결측이었다)."},
        "cov": {"type": "double precision", "description": "컨벡시티. 0.1% 결측."},
        "ndy_eval_price": {"type": "double precision", "description": "익일 평가일단가. 0.1% 결측."},
        "ndy_dirty": {"type": "double precision", "description": "익일 이자부단가. 0.1% 결측."},
        "ndy_dur": {"type": "double precision", "description": "익일 듀레이션. 0.1% 결측."},
        "ndy_cov": {"type": "double precision", "description": "익일 컨벡시티. 0.1% 결측."},
        "exg_close_price": {"type": "double precision", "description": "장내 채권종가. 18.9% 결측이고 값이 있는 행에도 0.0이 다수 섞여 있다."},
        "exg_close_price_base_dt": {"type": "text", "description": "장내 채권종가/종가수익률 기준일(YYYYMMDD 문자열). 19.0% 결측이고 공백 문자열이 섞여 있다."},

        # 기타
        "pd_pen_tr_yn": {"type": "text", "description": "퇴직연금 편입 가능 여부. 값은 N(19,951)/Y(1,931). 결측 없음."},
    },
}

# --- 국내ETF (raw.pref01n001, 1,780행) --------------------------------------
RDB_SCHEMA["국내ETF"] = {
    "table": DOMAIN_TABLE_INFO["국내ETF"]["table"],
    "type": "object",
    "properties": {
        # 식별/명칭
        "pd_itm_no": {"type": "text", "description": "상품번호(ISIN, 예: KR70000Z0003). 1,780건 전부 유일값. 결측 없음."},
        "pd_itm_no_ma": {"type": "text", "description": "상품번호(미래에셋 단축코드, 예: A0000Z0). 전부 유일값."},
        "pd_isin_cd": {"type": "text", "description": "Refinitiv ISIN. 32.1% 결측(ref_ 계열과 같은 결측 패턴)."},
        "pd_ric": {"type": "text", "description": "Refinitiv RIC(예: 0000Z0.KS). 32.1% 결측."},
        "pd_ticker": {"type": "text", "description": "Refinitiv 티커. 32.1% 결측."},
        "pd_nm": {"type": "text", "description": "상품명(정식). 결측 없음. 반도체/2차전지 같은 테마 키워드는 별도 섹터 컬럼이 아니라 이 텍스트 안에만 들어 있다."},
        "pd_abrv_nm": {"type": "text", "description": "상품약어명(예: RISE 바이오TOP10액티브)."},

        # 분류/속성
        "pd_grp_no": {"type": "text", "description": "상품군종류. 값은 ETF(1,235)/ETN(545) 두 가지. 이 테이블은 ETF만 있는 게 아니다."},
        "cu_fund_mgmt_co": {"type": "text", "description": "운용사(100종, 예: KB/삼성/iM에셋). 결측 없음."},
        "cu_base_index": {"type": "text", "description": "기초지수. 7.1% 결측이고 값이 있는 행에도 공백 문자열이 섞여 있다. nunique가 20뿐이라 대부분 공백 계열로 보인다."},
        "cu_strtegy": {"type": "text", "description": "운용전략. 실물복제(763)/액티브(358)/합성복제(82)가 정상 값이고, 'C'라는 코드성 오류값이 422건 섞여 있다. 8.7% 결측."},
        "cu_lev_fector": {"type": "double precision", "description": "레버리지 배수(1.0/1.5/2.0/-1.0/-2.0 등 7종). 음수가 인버스 상품이다. 10.2% 결측."},
        "cu_charge_rt": {"type": "double precision", "description": "총보수요율(%). 87.8% 결측이라 실사용률이 매우 낮다."},
        "cu_charge_etc_rt": {"type": "double precision", "description": "기타비용요율(%). 87.8% 결측이고 값이 있는 행 전부 0.0."},
        "wu_inv_ast_type": {"type": "text", "description": "투자자산군(9종: 주식 1,015 / 채권 221 / 원자재 211 / 대체투자 132 / 혼합자산 86 / 단기자금 45 / 기타 37 / 통화 29 / 부동산 4). 결측 없음. 산업 섹터가 아니라 자산군 분류다."},
        "wu_inv_rgn": {"type": "text", "description": "투자지역(11종: 국내 1,069 / 미국 466 / 글로벌 76 / 중국 63 / 아시아 33 / 일본 25 / 인도 19 / 남미북미 12 / 유럽 7 / 이머징브릭스 5 / 베트남 5). 결측 없음."},
        "pd_sect_cd": {"type": "text", "description": "ETF 섹터코드. 값이 2.0/3.0/4.0/8.0/9.0 숫자뿐이고 이름으로 매핑해 줄 컬럼이 이 테이블에 없다. 이전 배포본에 있던 pd_sect_nm(섹터명)은 이번에 삭제되었다. 10.2% 결측."},
        "ref_ast_type": {"type": "text", "description": "Refinitiv 자산유형(영문 7종: Equity/Bond/Alternatives/Mixed Assets/Money Market/Commodity/Other). 32.1% 결측. wu_inv_ast_type과 같은 축의 영문 버전이다."},
        "ref_geo_focus": {"type": "text", "description": "Refinitiv 투자지역(영문 23종, 예: Korea/United States of America/Global). 32.1% 결측. wu_inv_rgn의 영문 세분화 버전이다."},
        "ref_base_index": {"type": "text", "description": "Refinitiv 벤치마크명(905종). 32.1% 결측. cu_base_index보다 채움률과 다양성이 훨씬 낫다."},
        "ref_fund_mgmt_co": {"type": "text", "description": "Refinitiv 운용사(영문 29종). 32.1% 결측."},
        "ref_base_dt": {"type": "double precision", "description": "Refinitiv 기준일. 값이 있는 행 전부 20260822."},

        # 위험/판매
        "pd_risk_cd": {"type": "text", "description": "상품등급코드(PD_RISK_GCD_11~PD_RISK_GCD_16, 마지막 두 자리가 1~6등급). 결측 없음."},
        "pd_risk_nm": {"type": "text", "description": "상품등급명(6종: 매우높은위험(1등급) 775 / 높은위험(2등급) 691 / 낮은위험(5등급) 117 / 보통위험(4등급) 91 / 다소높은위험(3등급) 85 / 매우낮은위험(6등급) 21). 결측 없음."},
        "pd_sale_yn": {"type": "text", "description": "상품판매여부. 문서 타입은 text지만 실제 값은 정수 1(1,534건)/0(246건)이고 Y/N 문자열이 아니다. 0인 246건 중 245건이 pd_lste_dt가 99991231이 아닌(거래종료 예정) 종목이라, 주최측 공지의 '상장폐지/리스팅 종료' 기준과 사실상 일치한다."},
        "pd_lste_dt": {"type": "double precision", "description": "상품거래종료일자(YYYYMMDD 숫자). 1,535건이 99991231(종료 예정 없음)이고 242건만 실제 종료일이 잡혀 있다."},
        "pd_lstg_dt": {"type": "double precision", "description": "상품거래가능일자(상장일, YYYYMMDD 숫자). 0.2% 결측."},
        "pd_tr_yn": {"type": "double precision", "description": "상품거래정지여부. 0.0(정상 1,695건)/1.0(정지 82건)."},
        "pd_pen_tr_yn": {"type": "text", "description": "연금거래가능여부(Y/N). 결측 없음."},
        "pd_pen_risk_nm": {"type": "text", "description": "연금거래위험구분. 값은 위험자산/안전자산/N 세 가지. 결측 없음."},
        "wu_core_yn": {"type": "text", "description": "핵심ETF여부(Y/N). 결측 없음."},
        "pd_spac_yn": {"type": "text", "description": "SPAC 여부. 값이 있는 행 전부 'N'이라 변별력 없음. 10.2% 결측."},

        # 규모/가격
        "pd_net_tamt": {"type": "double precision", "description": "순자산총액(원). 10.2% 결측. 이 도메인의 '순자산' 기본 컬럼이다."},
        "du_last_aum": {"type": "double precision", "description": "최종 AUM(원). 10.2% 결측. pd_net_tamt와 유사 계열이나 값이 미세하게 다르다."},
        "pd_circ_net_tamt": {"type": "double precision", "description": "유통순자산총액(원). 10.2% 결측."},
        "pd_lst_stk_cnt": {"type": "bigint", "description": "상품상장주식수. 결측 없음."},
        "pd_stk_cnt": {"type": "double precision", "description": "상장주식수. 10.2% 결측."},
        "pd_circ_stk_cnt": {"type": "double precision", "description": "유통주식수. 10.2% 결측."},
        "du_last_nav": {"type": "double precision", "description": "최종 NAV(주당 순자산가치). 10.2% 결측."},
        "du_nav_yday": {"type": "double precision", "description": "전일 NAV. 10.2% 결측."},
        "du_nav_rnf_amt": {"type": "double precision", "description": "전일 대비 NAV 등락금액. 10.2% 결측."},
        "du_nav_base_dt": {"type": "double precision", "description": "NAV 기준일(YYYYMMDD). 10.2% 결측."},
        "du_bpr": {"type": "double precision", "description": "기준가. 0.2% 결측."},
        "du_clpr": {"type": "double precision", "description": "종가. 0.2% 결측."},
        "du_hpr": {"type": "double precision", "description": "고가. 0.2% 결측."},
        "du_lpr": {"type": "double precision", "description": "시가(스키마 코멘트는 '시가'지만 컬럼명은 low price 계열이라 저가일 가능성이 있다). 0.2% 결측."},
        "ru_mkt_price": {"type": "double precision", "description": "현재가. du_clpr와 값이 같다. 0.2% 결측."},
        "ru_mkt_volume": {"type": "double precision", "description": "거래량. du_vol_1d와 값이 같다. 0.2% 결측."},

        # 수익률/변동성
        "du_er_1d": {"type": "double precision", "description": "1일 수익률(%). 11.0% 결측."},
        "du_er_1m": {"type": "double precision", "description": "1개월 수익률(%). 11.0% 결측."},
        "du_er_3m": {"type": "double precision", "description": "3개월 수익률(%). 12.8% 결측."},
        "du_er_6m": {"type": "double precision", "description": "6개월 수익률(%). 16.5% 결측."},
        "du_er_1y": {"type": "double precision", "description": "1년 수익률(%). 20.4% 결측."},
        "du_er_ytd": {"type": "double precision", "description": "연초 대비 수익률(%). 17.0% 결측."},
        "du_vlty_1m": {"type": "double precision", "description": "최근 20거래일 연환산 변동성(%). 5.8% 결측. 이전 배포본에 없던 컬럼이다."},
        "du_vlty_3m": {"type": "double precision", "description": "최근 60거래일 연환산 변동성(%). 10.4% 결측."},
        "du_vlty_6m": {"type": "double precision", "description": "최근 120거래일 연환산 변동성(%). 16.5% 결측."},
        "du_vlty_1y": {"type": "double precision", "description": "최근 252거래일 연환산 변동성(%). 26.5% 결측."},
        "du_vlty_base_dt": {"type": "double precision", "description": "변동성 산출 기준일(YYYYMMDD). 4.8% 결측."},
        "du_chas_errt": {"type": "double precision", "description": "추적오차율(%). 10.2% 결측. 이전 배포본은 전부 0.0이었으나 이번에는 497종의 실제 값이 들어 있다."},
        "du_chas_errt_base_dt": {"type": "double precision", "description": "추적오차율 기준일. 10.2% 결측."},
        "du_diff_rt": {"type": "double precision", "description": "괴리율(%). 10.2% 결측. 이전 배포본은 전부 0.0이었으나 이번에는 303종의 실제 값이 들어 있다."},
        "du_diff_rt_base_dt": {"type": "double precision", "description": "괴리율 기준일. 10.2% 결측."},

        # 거래대금/거래량
        "du_val_1d": {"type": "double precision", "description": "일거래대금(원). 0.2% 결측."},
        "du_val_5d": {"type": "double precision", "description": "5일 평균 일거래대금(원). 0.3% 결측."},
        "du_val_1m": {"type": "double precision", "description": "1개월 평균 일거래대금(원). 0.9% 결측."},
        "du_vol_1d": {"type": "double precision", "description": "일거래량(주). 0.2% 결측."},
        "du_vol_avg_5d": {"type": "double precision", "description": "5일 평균 거래량(주). 0.3% 결측."},
        "du_vol_avg_1m": {"type": "double precision", "description": "1개월 평균 거래량(주). 0.8% 결측."},

        # 분배금(이번 배포본 신설)
        "pd_dvid_cycl": {"type": "text", "description": "분배주기(Q 698 / A 306 / M 196 / S 8, 공백 422). 8.4% 결측."},
        "pd_dvid_yield": {"type": "double precision", "description": "연환산 분배수익률(%). 32.1% 결측. 이전 배포본은 전부 0.0이었으나 이번에는 실제 값이 들어 있다."},
        "pd_divd_amt_pshr": {"type": "double precision", "description": "주당 분배금(원천 우선, 없으면 회당 추정). 32.1% 결측."},
        "pd_divd_amt_ann": {"type": "double precision", "description": "연간 추정 분배금. 53.4% 결측."},
        "pd_dvid_pay_cnt": {"type": "double precision", "description": "연간 지급횟수(1/2/4/12). 32.1% 결측."},
        "pd_dvid_pay_months": {"type": "text", "description": "분배 지급월(영문 월 이름을 쉼표로 나열, 예: January,April,July,October). 32.1% 결측."},
        "pd_dvid_nav": {"type": "double precision", "description": "분배금 계산 기준 NAV. 32.1% 결측."},
        "pd_dvid_prc_base_dt": {"type": "double precision", "description": "분배금 계산 NAV 기준일. 32.1% 결측."},
        "pd_dvid_base_dt": {"type": "double precision", "description": "분배정보 기준일. 값이 있는 행 전부 20260822."},
        "pd_dvid_tax_basis": {"type": "text", "description": "분배 과세기준. 값이 있는 행 전부 'Gross' 단일값."},
        "pd_dvid_inc_dist": {"type": "text", "description": "원천 성과배분/분배금. 1,780건 전부 NULL이라 사실상 미사용 컬럼."},

        # 펀더멘털(이번 배포본 신설, 채권형 ETF 위주로만 채워짐)
        "fn_average_coupon": {"type": "double precision", "description": "평균쿠폰이자율(%). 88.8% 결측(채권형 ETF에만 값이 있음)."},
        "fn_average_quality": {"type": "double precision", "description": "평균신용품질(숫자 스코어). 95.8% 결측."},
        "fn_effective_maturity": {"type": "double precision", "description": "실질만기(년). 87.9% 결측."},
        "fn_nominal_maturity": {"type": "double precision", "description": "명목만기(년). 87.9% 결측. fn_effective_maturity와 값이 같다."},
        "fn_average_maturity": {"type": "double precision", "description": "평균잔존만기. 1,780건 전부 NULL이라 사실상 미사용 컬럼."},
        "fn_effective_duration": {"type": "double precision", "description": "듀레이션. 1,780건 전부 NULL이라 사실상 미사용 컬럼."},
        "fn_modified_duration": {"type": "double precision", "description": "수정듀레이션. 1,780건 전부 NULL이라 사실상 미사용 컬럼."},
        "fn_base_dt": {"type": "double precision", "description": "펀더멘털 기준일. 값이 있는 행 전부 20260822."},
        "fn_portfolio_dt": {"type": "double precision", "description": "포트폴리오 기준일(17종). 37.2% 결측."},

        # 통화/시장/갱신일
        "pd_curr_cd": {"type": "text", "description": "상품통화코드. 값은 CURR_CD_KRW / CURR_CD_000 두 가지(원시 ISO 코드가 아니라 접두어가 붙은 형태)."},
        "pd_curr_nm": {"type": "text", "description": "상품통화명(한국원화/해당없음)."},
        "pd_exg_mkt_cd": {"type": "text", "description": "거래소코드. 전 행 EXG_MKT_NO_001 단일값."},
        "pd_exg_mkt_nm": {"type": "text", "description": "거래소명. 전 행 '유가증권' 단일값(공백 패딩 있음)."},
        "pd_mkt_id": {"type": "text", "description": "상품거래시장코드. 전 행 STK 단일값."},
        "pd_mkt_nm": {"type": "text", "description": "상품거래시장명. 사실상 '유가증권' 단일값(공백 패딩 있음)."},
        "cu_upt_dt": {"type": "double precision", "description": "변동갱신일자(YYYYMMDD). 최신값 20260824. 10.2% 결측."},
        "du_upt_dt": {"type": "double precision", "description": "일간갱신일자(YYYYMMDD). 최신값 20260821. 10.2% 결측."},
        "wu_upt_dt": {"type": "double precision", "description": "주간갱신일자. 값이 있는 행 전부 20260821."},
    },
}

# --- 해외ETF (raw.pref02n001, 6,037행) --------------------------------------
RDB_SCHEMA["해외ETF"] = {
    "table": DOMAIN_TABLE_INFO["해외ETF"]["table"],
    "type": "object",
    "properties": {
        # 식별/명칭
        "pd_itm_no": {"type": "text", "description": "해외 ETF RIC(예: AAUA.K). 6,037건 전부 유일값. 결측 없음."},
        "pd_itm_no_ma": {"type": "text", "description": "해외 ETF RIC(PDF 조인키). pd_itm_no와 값이 같다."},
        "pd_isin_cd": {"type": "text", "description": "ISIN 코드(예: US02072Q2755). 0.2% 결측."},
        "pd_abrv_nm": {"type": "text", "description": "상품약어명(티커, 예: AAUA). 결측 없음. 질문에서 VOO, QQQ처럼 티커로 부르면 이 컬럼으로 찾는다."},
        "pd_nm": {"type": "text", "description": "상품명(영문 정식명). 결측 없음."},
        "pd_lipper_id": {"type": "text", "description": "Lipper 펀드코드. 0.2% 결측."},
        "pd_us_cik": {"type": "text", "description": "미국 SEC CIK 번호(389종). 0.3% 결측."},

        # 분류/속성
        "pd_grp_no": {"type": "text", "description": "상품군종류. 값은 ETF(5,972)/ETN(65) 두 가지."},
        "cu_fund_mgmt_co": {"type": "text", "description": "운용사(영문 382종). 0.2% 결측."},
        "cu_base_index": {"type": "text", "description": "기초지수(영문 1,850종). 0.2% 결측. 지수를 제공하지 않는 액티브 상품은 'Index is not provided by Management Company'로 표기된다."},
        "cu_strtegy": {"type": "text", "description": "운용전략(영문 자유서술 문장, 5,943종). 0.2% 결측. narrative 질문(운용 목표 설명 등)에 Vector 없이 RDB 텍스트로 바로 답할 수 있는 후보 컬럼이다."},
        "cu_index_repl_mthd": {"type": "text", "description": "인덱스 복제방법(Full/Optimized/Swap 등 4종). 60.1% 결측."},
        "cu_index_tracking_yn": {"type": "text", "description": "인덱스 추적 여부. 값이 있는 행 전부 'Y'. 60.1% 결측."},
        "cu_inverse_short_yn": {"type": "text", "description": "인버스 또는 숏 여부. 값이 있는 행 전부 'Y'이고 97.0% 결측이라, 결측이 곧 '인버스 아님'을 뜻한다."},
        "cu_etn_yn": {"type": "text", "description": "ETN 여부. 값이 있는 행 전부 'Y'이고 98.9% 결측. pd_grp_no로 판단하는 편이 낫다."},
        "cu_lev_fector": {"type": "double precision", "description": "레버리지 배수(2.0/-2.0/3.0 등 11종). 85.1% 결측이라 결측이 곧 배수 1배를 뜻한다."},
        "cu_charge_rt": {"type": "double precision", "description": "연간보수율(%). 결측 없음. 국내ETF의 cu_charge_rt(87.8% 결측)와 달리 이 도메인은 전부 채워져 있다."},
        "wu_inv_ast_type": {"type": "text", "description": "투자자산군(영문 6종: Equity/Alternatives/Bond/Mixed Assets/Commodity/Money Market). 0.2% 결측."},
        "wu_inv_rgn": {"type": "text", "description": "투자지역(영문 59종, 예: United States of America/Global/Global Ex US). 국내ETF보다 훨씬 세분화되어 있어 '아시아' 같은 느슨한 지역명은 등호가 아니라 contains 매칭이 필요할 수 있다. 0.2% 결측."},
        "wu_core_yn": {"type": "text", "description": "핵심 ETF 여부. 값이 있는 행 전부 'N'이고 98.2% 결측이라 변별력이 없다."},

        # 규모/가격
        "du_last_aum": {"type": "double precision", "description": "일간 순자산총액(거래통화 기준, 대부분 USD). 3.4% 결측. 이 도메인의 '순자산' 컬럼이다."},
        "du_last_nav": {"type": "double precision", "description": "추정 주당 NAV. 87.4% 결측이라 실사용률이 낮다."},
        "pd_lst_stk_cnt": {"type": "double precision", "description": "상장주식수. 결측 없음."},
        "pd_lst_price": {"type": "double precision", "description": "액면가. 값이 0.0 아니면 0.01뿐이라 사실상 미사용."},
        "du_bpr": {"type": "double precision", "description": "기준가. 0.2% 결측."},
        "du_clpr": {"type": "double precision", "description": "종가. 0.2% 결측."},
        "du_opr": {"type": "double precision", "description": "시가. 0.2% 결측."},
        "du_hpr": {"type": "double precision", "description": "고가. 0.2% 결측."},
        "du_lpr": {"type": "double precision", "description": "저가. 0.2% 결측."},
        "ru_mkt_price": {"type": "double precision", "description": "실시간 현재가. du_clpr와 값이 같다."},
        "ru_mkt_volume": {"type": "double precision", "description": "실시간 거래량. du_vol_1d와 값이 같다."},
        "du_val_1d": {"type": "double precision", "description": "외화 거래대금. 0.2% 결측."},
        "du_vol_1d": {"type": "double precision", "description": "거래량. 0.2% 결측."},
        "du_er_1d": {"type": "double precision", "description": "1일 수익률(%). 0.2% 결측. 이 도메인에는 1개월/1년 같은 장기 수익률 컬럼이 없다."},
        "du_diff_rt": {"type": "double precision", "description": "종가 대비 추정 NAV 괴리율(%). 6,037건 중 3건에만 값이 있어 사실상 미사용 컬럼."},

        # 거래소/통화
        "pd_exg_mkt_cd": {"type": "text", "description": "거래소코드(AMX/NAS/NYS 위주, 정체 불명 코드 101/102가 소수). 이 값 자체가 '해외 상장'이라는 도메인 분류의 근거이기도 하다. 결측 없음."},
        "pd_mkt_id": {"type": "text", "description": "거래소국가코드. 전 행 US 단일값."},
        "pd_curr_cd": {"type": "text", "description": "펀드통화코드. USD가 대부분이고 INR이 소수. 0.2% 결측."},
        "pd_trd_ccy": {"type": "text", "description": "거래통화코드. 전 행 USD 단일값."},

        # 판매/일자
        "pd_sale_yn": {"type": "text", "description": "판매여부. 값이 있는 행 전부 1.0 단일값이라 변별력이 없다(DOMAIN_SALE_POLICY 참고)."},
        "pd_tr_yn": {"type": "text", "description": "거래정지여부. 값이 있는 행 전부 0.0 단일값이라 변별력이 없다."},
        "pd_lstg_dt": {"type": "text", "description": "설정일(YYYYMMDD 숫자, 예: 20070223). 결측 없음."},
        "du_clpr_base_dt": {"type": "double precision", "description": "선택된 종가의 원천 기준일(109종). 최신값 20260821이지만 과거 일자가 섞여 있어 종목마다 종가 기준일이 다르다."},
        "du_clpr_src": {"type": "text", "description": "선택된 종가 원천 컬럼 식별자. 전 행 'pd65n101.tday_clpr' 단일값."},
        "du_base_dt_match_yn": {"type": "text", "description": "NAV/종가 기준일 일치 여부. 값이 있는 행 전부 'N'이라, NAV 기준일과 종가 기준일이 다른 것이 정상 상태다."},
        "du_nav_base_dt": {"type": "text", "description": "NAV 원천 기준일. 전 행 20260822 단일값."},
        "du_upt_dt": {"type": "text", "description": "일간갱신일자(108종). 최신값 20260822."},
        "cu_upt_dt": {"type": "text", "description": "변동갱신일자. 전 행 20260822 단일값."},
        "wu_upt_dt": {"type": "text", "description": "주간갱신일자. 전 행 20260822 단일값."},
    },
}

# --- 펀드 (raw.prfd01n001, 23,676행) ----------------------------------------
RDB_SCHEMA["펀드"] = {
    "table": DOMAIN_TABLE_INFO["펀드"]["table"],
    "type": "object",
    "properties": {
        # 식별/명칭
        "itm_no": {"type": "text", "description": "종목번호(ISIN, 예: KR5010101611). 23,676건 전부 유일값. 결측 없음."},
        "itm_nm": {"type": "text", "description": "종목명(정식). 결측 없음."},
        "itm_abrv_nm": {"type": "text", "description": "종목약어명. 결측 없음."},
        "itm_eng_nm": {"type": "text", "description": "종목영문명. 결측 없음."},
        "itm_eabrv_nm": {"type": "text", "description": "종목영문약어명. 99.4% 결측이라 실사용률이 매우 낮다."},
        "std_itm_no": {"type": "text", "description": "표준종목번호(ISIN). 2.2% 결측이고 공백 문자열이 섞여 있다."},
        "fss_itm_no": {"type": "text", "description": "금융감독원 종목번호. 0.2% 결측."},
        "ksd_itm_no": {"type": "text", "description": "예탁원 종목번호. 2.5% 결측, 공백 문자열 섞임."},
        "rptt_ksd_itm_no": {"type": "text", "description": "대표 예탁원 종목번호. 같은 모펀드의 여러 클래스를 묶는 키로 쓸 수 있다. 0.5% 결측."},
        "mtco_itm_no": {"type": "text", "description": "운용사 종목번호. 0.5% 결측."},
        "kofia_fd_ccd": {"type": "text", "description": "금융투자협회 펀드분류코드(6,765종). 0.2% 결측."},

        # 분류
        "or_attr_desc": {"type": "text", "description": "운용속성구분(14종: 주식형 5,231 / 채권형 4,472 / 재간접 3,652 / 채권혼합 2,989 / 파생상품 2,302 / 혼합자산 1,272 / 해당없음 905 / 주식혼합 877 / 특별자산 785 / MMF 601 / 임대형 226 / 기타 170 / 대출형 106 / 개발형 88). 결측 없음. 이전 배포본에 있던 '06' 오류값은 사라졌고 파생상품/개발형/기타가 새로 생겼다."},
        "prvo_pbff_desc": {"type": "text", "description": "사모/공모 구분. 공모 14,716 / 사모 8,960. 결측 없음. 이전 배포본(사모 102건)과 달리 사모 비중이 38%라 공모펀드만 대상으로 하려면 이 조건을 반드시 걸어야 한다."},
        "prvo_fd_desc": {"type": "text", "description": "사모펀드 세부구분(해당없음/일반사모/일반사모(2015년전) 4종). 결측 없음."},
        "fd_ivst_rgn_desc": {"type": "text", "description": "펀드투자지역(9종: 국내 11,300 / 글로벌 5,925 / 해당없음 3,678 / 아시아 1,290 / 남미북미 815 / 유럽 329 / 이머징브릭스 283 / 기타 38 / 중동아프리카 18). 결측 없음."},
        "ovrs_fd_desc": {"type": "text", "description": "해외펀드구분(국내 14,912 / 해외 6,961 / 국내외혼합 1,687 / 해당없음 116). fd_ivst_rgn_desc와 다른 축으로, 펀드 자체가 어디에 설정된 상품인지를 나타낸다. 결측 없음."},
        "fd_estb_ctry_cd": {"type": "text", "description": "펀드설립국가코드(0/410/442 등 숫자 코드 7종). 이름 매핑 컬럼은 이 테이블에 없다."},
        "int_dvd_desc": {"type": "text", "description": "이자배당구분(배당 20,520 / 이자 2,809 / 해당없음 347). 결측 없음."},
        "pers_corp_desc": {"type": "text", "description": "개인법인구분(해당없음/개인/법인). 결측 없음."},
        "hdge_fd_yn": {"type": "text", "description": "헤지펀드 여부(0/1). 결측 없음."},
        "ofsfd_yn": {"type": "text", "description": "역외펀드 여부(0/1). 결측 없음."},
        "fd_set_pcd": {"type": "text", "description": "펀드설정유형코드(0/10/20). 결측 없음."},
        "pfiv_sale_cntl_tcd": {"type": "text", "description": "전문투자자 판매제어 구분코드(0/1/3 등 4종). 결측 없음."},
        "frc_bpr_itm_yn": {"type": "text", "description": "외화기준가종목 여부(0/1). 결측 없음."},

        # 클래스(이번 배포본 신설)
        "han_clas_nm": {"type": "text", "description": "클래스 한글 표기(195종, 예: 수수료미징구-온라인). 59.3% 결측. 클래스가 나뉜 펀드에만 값이 있다."},
        "han_clas_fee_type": {"type": "text", "description": "클래스 수수료 부과 유형(수수료미징구 7,834 / 수수료선취 1,786 / 수수료후취 5). 59.3% 결측."},
        "han_clas_sales_channel": {"type": "text", "description": "클래스 판매채널(오프라인 6,048 / 온라인 3,548 / 직판 7). 59.4% 결측."},
        "han_clas_policies": {"type": "text", "description": "클래스 부가 정책(33종, 예: 랩,펀드 / 보수체감 / 개인연금). 73.5% 결측."},

        # 판매/보수
        "sale_yn": {"type": "text", "description": "판매여부. 값은 판매중(10,962)/판매완료(12,714) 텍스트이고 0/1 플래그가 아니다. 결측 없음."},
        "thco_sale_yn": {"type": "text", "description": "당사판매여부. 값이 있는 행 전부 'Y'이고 55.2% 결측이라 변별력이 낮다."},
        "sale_co_rwrd_r": {"type": "double precision", "description": "판매회사보수(%). 결측 없음."},
        "or_co_rwrd_r": {"type": "double precision", "description": "집합투자업자보수(운용보수, %). 결측 없음."},
        "trusc_rwrd_r": {"type": "double precision", "description": "신탁업자보수(%). 결측 없음."},
        "ofwk_trus_rwrd_r": {"type": "double precision", "description": "일반사무관리보수(%). 결측 없음. 총보수를 구하려면 이 네 보수 컬럼을 더해야 하며, 합산 컬럼은 따로 없다."},
        "or_co_xtn_itt_cd": {"type": "text", "description": "운용회사 대외기관코드(275종). 운용사 이름 컬럼은 이 테이블에 없다. 결측 없음."},
        "trusc_xtn_itt_cd": {"type": "text", "description": "수탁회사 대외기관코드(50종). 0.2% 결측."},

        # 규모/수익률
        "fd_nast_suma": {"type": "double precision", "description": "펀드 순자산(원). 60.2% 결측. 이전 배포본(13.1% 결측)보다 결측이 크게 늘었으므로 정렬/필터 시 NULL 제외가 사실상 필수다."},
        "bns_bpr": {"type": "double precision", "description": "매매기준가. 60.2% 결측."},
        "fd_sbpr": {"type": "bigint", "description": "시가평가금액. 결측 없음이지만 0인 행이 많다."},
        "fd_prsv_r": {"type": "double precision", "description": "보전율(%). 결측 없음."},
        "fd_mm1_ern_r": {"type": "double precision", "description": "1개월 수익률(%). 68.8% 결측."},
        "fd_mm3_ern_r": {"type": "double precision", "description": "3개월 수익률(%). 69.1% 결측."},
        "fd_mm6_ern_r": {"type": "double precision", "description": "6개월 수익률(%). 69.5% 결측."},
        "fd_mm18_ern_r": {"type": "double precision", "description": "18개월 수익률(%). 70.9% 결측."},
        "fd_yr1_ern_r": {"type": "double precision", "description": "1년 수익률(%). 70.3% 결측."},
        "fd_yr2_ern_r": {"type": "double precision", "description": "2년 수익률(%). 71.5% 결측."},
        "fd_yr3_ern_r": {"type": "double precision", "description": "3년 수익률(%). 72.6% 결측."},
        "fd_yr5_ern_r": {"type": "double precision", "description": "5년 수익률(%). 74.7% 결측."},
        "fd_wk1_ern_r": {"type": "double precision", "description": "1주일 수익률(%). 23,676건 전부 NULL이라 사실상 미사용 컬럼이다(이전 배포본에는 값이 있었다)."},

        # 위험등급/구성비율(제로인)
        "zrin_fd_ivst_risk_gcd": {"type": "double precision", "description": "제로인 펀드투자위험등급코드(1~6, 1이 최고위험). 63.3% 결측."},
        "zrin_fd_ivst_risk_grd_nm": {"type": "text", "description": "제로인 펀드투자위험등급명(높은 위험 3,023 / 다소 높은 위험 1,765 / 보통 위험 1,428 / 낮은 위험 1,193 / 매우 높은 위험 897 / 매우 낮은 위험 355). '높은위험'(20건), '보통위험'(8건)처럼 공백이 빠진 중복 표기가 섞여 있어 TRIM 및 공백 제거 비교를 권장. 63.3% 결측."},
        "zrin_btyp_nm": {"type": "text", "description": "제로인 대유형명(18종, 예: MMF/기타/외화 MMF). 52.4% 결측."},
        "zrin_btyp_cd": {"type": "double precision", "description": "제로인 대유형코드(18종). 52.4% 결측."},
        "zrin_ptn_nm": {"type": "text", "description": "제로인 유형명(102종). 52.4% 결측."},
        "zrin_pcd": {"type": "double precision", "description": "제로인 유형코드(104종). 52.4% 결측."},
        "zrin_attr_nms": {"type": "text", "description": "제로인 속성명 목록(쉼표 구분, 예: 추가,국내,개방,국내위탁판매). 52.4% 결측."},
        "zrin_dmst_stk_cmst_rt": {"type": "double precision", "description": "국내주식 구성비율(%). 60.2% 결측."},
        "zrin_ovrs_stk_cmst_rt": {"type": "double precision", "description": "해외주식 구성비율(%). 60.2% 결측."},
        "zrin_dmst_bd_cmst_rt": {"type": "double precision", "description": "국내채권 구성비율(%). 60.2% 결측."},
        "zrin_ovrs_bd_cmst_rt": {"type": "double precision", "description": "해외채권 구성비율(%). 60.2% 결측."},
        "zrin_fd_cmst_rt": {"type": "double precision", "description": "펀드 구성비율(재간접 비중, %). 60.2% 결측."},
        "zrin_liqt_cmst_rt": {"type": "double precision", "description": "유동성 구성비율(%). 60.2% 결측."},
        "zrin_etc_ast_cmst_rt": {"type": "double precision", "description": "기타자산 구성비율(%). 60.2% 결측."},

        # 속성 코드(이번 배포본 신설)
        "prfd_attr_cds": {"type": "text", "description": "펀드별 속성코드 목록(쉼표 구분, 예: C101,V101,D102,C103). 52.4% 결측."},
        "prfd_attr_cnt": {"type": "bigint", "description": "펀드별 속성 개수(0~13). 결측 없음."},
        "prfd_attr_search_text": {"type": "text", "description": "상품검색용 속성 코드/명칭이 함께 들어간 텍스트(예: 'D102 국내위탁판매 V101 국내 C101 추가'). 52.4% 결측. LIKE 검색용으로 쓸 수 있다."},

        # 벤치마크/분배/통화/일자
        "bmrk_nm": {"type": "text", "description": "벤치마크명(국문, 389종). 52.4% 결측."},
        "bmrk_eng_nm": {"type": "text", "description": "벤치마크명(영문, 386종). 52.4% 결측."},
        "fd_last_dstb_r": {"type": "double precision", "description": "최근 분배율(%). 54.1% 결측."},
        "fd_last_dstb_actg_bss_dt": {"type": "double precision", "description": "최근 분배 회계기초일자(YYYYMMDD). 54.1% 결측."},
        "fd_last_dstb_actg_eot_dt": {"type": "double precision", "description": "최근 분배 회계기말일자(YYYYMMDD). 54.1% 결측."},
        "curr_cd": {"type": "text", "description": "통화코드(KRW 23,147 / USD 453 / EUR 56 / JPY 15 / AUD 2 / GBP 2 / SEK 1). 결측 없음."},
        "exchdg_yn": {"type": "text", "description": "환헤지 여부(Y/N). 70.5% 결측."},
        "fd_price_bas_dt": {"type": "double precision", "description": "펀드 기준가/수익률 기준일자(905종). 최신값 20260821이지만 과거 일자가 섞여 있어 종목마다 기준일이 다르다. 60.2% 결측."},
        "fd_daily_bas_dt": {"type": "double precision", "description": "펀드 데일리정보 기준일자. fd_price_bas_dt와 같은 값. 60.2% 결측."},
    },
}


# ---------------------------------------------------------------------------
# 큐레이션된 개념 카탈로그: "개념명 -> 실제 컬럼" + 실 데이터 검증 결과.
# ---------------------------------------------------------------------------

BOND_ATTRIBUTES: dict[str, AttributeSpec] = {
    "신용등급": AttributeSpec(
        column="crd_grd",
        value_type="ordinal",
        value_order=[
            "C", "C0", "CC0", "CCC",
            "B-", "B0", "B+", "BB-", "BB0", "BB+", "BBB-", "BBB0", "BBB+",
            "A-", "A0", "A+", "AA-", "AA0", "AA+", "AAA",
        ],
        note=(
            "18.4%(4,020건) 결측이다. 이번 배포본에서 실제로 관측된 값은 15종"
            "(AAA/AA+/AA0/AA-/A+/A0/A-/BBB+/BBB0/BBB-/BB0/BB-/B+/B-/C0)이지만, "
            "value_order에는 등급 체계 전체를 넣어 뒀다. 관측되지 않은 값이 "
            "IN 목록에 섞여도 결과는 달라지지 않고, 반대로 목록에서 빠지면 "
            "gte/lte 슬라이싱이 틀어지기 때문이다. 이전 배포본에 있던 "
            "PD_EVCO_CRD_GRD(평가사별 등급 병기 컬럼)는 이번 데이터에 없다. "
            "value_order는 오름차순(등급이 나쁜 값부터 좋은 값 순)이다. "
            "'gte(이상)'는 value_order에서 이 값의 인덱스부터 끝까지가 정답이고, "
            "'lte(이하)'는 처음부터 이 값의 인덱스까지가 정답이다"
            "(utils.resolve_ordinal_matched_values가 이 계산을 코드로 대신한다. "
            "LLM에게 CASE WHEN 방향을 맡기지 않는다)."
        ),
    ),
    "위험등급": AttributeSpec(
        column="pd_risk_nm",
        value_type="ordinal",
        value_order=[
            "매우높은위험(1등급)", "높은위험(2등급)", "다소높은위험(3등급)",
            "보통위험(4등급)", "낮은위험(5등급)", "매우낮은위험(6등급)",
        ],
        note=(
            "이번 배포본에서 새로 생긴 컬럼이며 결측이 없다. 국내ETF의 "
            "pd_risk_nm과 완전히 같은 표기 체계다(공백 없이 붙여 쓴다). "
            "1등급이 가장 위험하고 6등급이 가장 안전하다. value_order는 등급 "
            "번호 오름차순이라 'N등급 이상'은 value_order[idx:], 'N등급 이하'는 "
            "value_order[:idx+1]이 정답이다. 등급 외에 '해당없음' 값이 19건 "
            "있는데 순서가 없으므로 value_order에 넣지 않았다(비교 조건에서 "
            "자연히 제외된다). 원문 코드 pd_risk_gcd(11~16, 0)는 같은 정보의 "
            "코드 버전이므로 이름 컬럼만 쓴다. 이전 배포본에서 위험등급으로 "
            "쓰던 PD_RISK_GCD(0~6)와는 코드 체계가 다르니 주의한다."
        ),
    ),
    "잔존기간": AttributeSpec(
        column="remaining_days",
        value_type="numeric",
        note=(
            "이미 계산되어 있는 일(day) 단위 컬럼이고 이번 배포본에서는 결측이 "
            "없다(이전 배포본은 25.1% 결측이었다). mat_dt로 다시 계산할 필요 "
            "없다. 연 단위 조건이면 365를 곱해 일 단위로 변환한다."
        ),
    ),
    "만기일": AttributeSpec(
        column="mat_dt",
        value_type="date_yyyymmdd_numeric",
        note=(
            "상환일자(영구채는 1차 콜행사개시일). YYYYMMDD 형태의 숫자다. "
            "날짜 연산이 필요하면 TO_DATE(CAST(mat_dt AS text), 'YYYYMMDD')로 "
            "변환한다. 잔존기간 조건이면 이 컬럼 대신 remaining_days를 우선 쓴다."
        ),
    ),
    "발행일": AttributeSpec(column="isu_dt", value_type="date_yyyymmdd_numeric", note="결측 없음."),
    "표면금리": AttributeSpec(column="srfc_irt", value_type="numeric", note="표면이자율/쿠폰금리(%). 결측 없음."),
    "민평수익률": AttributeSpec(
        column="applied_yield",
        value_type="numeric",
        note=(
            "결측이 없어 이 도메인에서 수익률 기준 정렬에 쓸 수 있는 사실상 "
            "유일한 컬럼이다. buy_yield(매수수익률)는 97.1% 결측이라 정렬에 "
            "쓰면 대부분의 종목이 탈락한다."
        ),
    ),
    "매수수익률": AttributeSpec(
        column="buy_yield",
        value_type="numeric",
        note=(
            "97.1% 결측(21,882건 중 634건에만 값 존재). 질문이 명시적으로 "
            "매수수익률을 지목한 게 아니라면 applied_yield(민평수익률)를 쓴다. "
            "이 컬럼으로 정렬/필터하면 후보군이 3%로 줄어든다."
        ),
    ),
    "듀레이션": AttributeSpec(column="dur", value_type="numeric", note="0.1% 결측(이전 배포본은 31.6% 결측이었다)."),
    "컨벡시티": AttributeSpec(column="cov", value_type="numeric", note="0.1% 결측."),
    "평가가격": AttributeSpec(column="eval_price", value_type="numeric", note="평가일단가(Clean Price 성격). 결측 없음."),
    "발행잔액": AttributeSpec(column="isu_bal_amt", value_type="numeric", note="결측 없음."),
    "총발행금액": AttributeSpec(column="bd_tisu_a", value_type="numeric", note="발행잔액(isu_bal_amt)과 다른 개념이다. 결측 없음."),
    "통화": AttributeSpec(
        column="curr_cd",
        value_type="categorical",
        known_values=["KRW"],
        note=(
            "'원화채권'이면 KRW. 21,882건 중 21,881건이 KRW이고 '000'이라는 "
            "오류값이 1건 있다. 이번 배포본에는 USD/EUR/JPY 채권이 아예 없으므로 "
            "'외화채권' 조건은 결과가 0건이 된다."
        ),
    ),
    "상품유형": AttributeSpec(
        column="std_pd_mcls_nm",
        value_type="categorical",
        known_values=["회사채", "특수채", "국공채"],
        note=(
            "'회사채'처럼 질문에 그대로 나오는 중분류다. 등호 비교로 충분. "
            "이번 배포본에는 이 3종밖에 없다(이전에 있던 개인투자용국채, "
            "외화채권-회사채, 외화채권-금융채는 사라졌다). product_domain의 "
            "subtype으로 뽑힌 값이 여기로 매핑된다."
        ),
    ),
    "상품소분류": AttributeSpec(
        column="std_pd_scls_nm",
        value_type="categorical",
        known_values=[
            "일반사채", "공사채", "지역개발", "특수은행채", "은행채", "도시철도",
            "국고채", "국민주택", "공모지방채", "중앙은행채", "기타사채", "기타국채", "물가채",
        ],
        note="상품유형(중분류)보다 한 단계 아래 분류다. 결측 없음.",
    ),
    "채권종류": AttributeSpec(
        column="bd_knd",
        value_type="categorical",
        note="예탁원 기준 채권종류명 41종. 뒤쪽 공백 패딩이 있어 TRIM(bd_knd) 비교를 권장. 0.7% 결측.",
    ),
    "모집구분": AttributeSpec(
        column="bd_ofr_tcd",
        value_type="categorical",
        known_values=["공모", "사모"],
        note="공모 19,875 / 사모 2,007. 결측 없음. 이번 배포본에서 새로 쓸 수 있게 된 축이다.",
    ),
    "금리구분": AttributeSpec(
        column="bd_inrt_tcd",
        value_type="categorical",
        known_values=["고정금리", "변동금리", "고정+변동금리"],
        note="결측 없음.",
    ),
    "이자지급구분": AttributeSpec(
        column="bd_intp_tcd",
        value_type="categorical",
        known_values=["이표채", "복리채", "할인채", "단리채"],
        note="결측 없음.",
    ),
    "거래시장": AttributeSpec(
        column="pd_exg_mkt",
        value_type="categorical",
        known_values=["장내", "장외"],
        note="결측 없음.",
    ),
    "발행기관": AttributeSpec(
        column="pd_pbcm",
        value_type="text",
        is_organization_name=True,
        note="1,837종. 공백 패딩이 있어 TRIM(pd_pbcm) 비교나 LIKE 매칭을 권장. 0.7% 결측.",
    ),
    # "발행사"는 "발행기관"과 같은 개념의 다른 표현이다. 질문 분석 LLM이
    # 이 둘을 섞어 쓰는 게 실측됐다(2026-09-02, "SK하이닉스가 발행한 채권"
    # 질문에서 "발행사"로 나옴) - 카탈로그에 "발행기관"만 있으면 정규화
    # 비교로도 안 걸려서(공백 제거해도 "발행사"≠"발행기관") LLM 폴백으로
    # 새는데, 그 폴백 경로는 is_organization_name이 안 붙어 조직명 별칭
    # 확장이 적용되지 않는다. 같은 컬럼을 가리키는 별칭 항목을 하나 더
    # 등록해 어느 표현으로 오든 정확히 카탈로그에서 잡히게 한다.
    "발행사": AttributeSpec(
        column="pd_pbcm",
        value_type="text",
        is_organization_name=True,
        note="'발행기관'의 동의어. 1,837종. 공백 패딩이 있어 TRIM(pd_pbcm) 비교나 LIKE 매칭을 권장. 0.7% 결측.",
    ),
    "퇴직연금편입가능여부": AttributeSpec(
        column="pd_pen_tr_yn",
        value_type="categorical",
        true_condition="= 'Y'",
        known_values=["Y", "N"],
        note="Y 1,931 / N 19,951. 결측 없음.",
    ),
    "상품명": AttributeSpec(column="pd_nm", value_type="text", note="결측 없음."),
    # §8(Graph->RDB 핸드오프)용: GraphDB의 fp:productCode가 이 컬럼과 같은
    # ISIN 값이다(실측 확인, 예: KR60143NEFC6). Graph가 찾은 엔티티 코드를
    # "상품코드 in (...)" 조건으로 주입할 때 이 개념명을 쓴다.
    "상품코드": AttributeSpec(column="pd_no", value_type="text", note="ISIN. 결측 없음(단 info_seq로 한 종목이 여러 행일 수 있음)."),
    # "상품번호"는 "상품코드"의 동의어다. 2026-09-05 실측: Q4가 "상품번호와 각
    # 수치의 기준일을 함께 제시해줘"라고 물었는데 카탈로그에 "상품코드"만 있어
    # LLM 폴백으로 샜고, 폴백도 "대응하는 컬럼을 찾지 못해 결과에서 제외"하고
    # 끝났다(golden C1은 pd_itm_no를 요구). "발행사"/"발행기관" 때와 같은
    # 부류라 같은 방식으로 별칭 항목을 하나 더 등록한다.
    "상품번호": AttributeSpec(column="pd_no", value_type="text", note="'상품코드'의 동의어. ISIN. 결측 없음(단 info_seq로 한 종목이 여러 행일 수 있음)."),
    # 주의: '판매가능여부'는 의도적으로 넣지 않았다. 주최측이 buyable_quantity를
    # 무효로 공지했고 이 테이블에는 상장폐지 여부 컬럼이 없다. 자세한 이유는
    # DOMAIN_SALE_POLICY["채권"] 참고.
    "ESG채권구분": AttributeSpec(
        column="pd_nm",
        value_type="categorical",
        known_values=["녹색채권", "사회적채권", "지속가능채권"],
        note=(
            "채권 이름(pd_nm)에 포함된 기호로 ESG 여부를 판별한다. "
            "(녹)=녹색채권, (사)=사회적채권, (지)=지속가능채권. "
            "반드시 문자열 포함(LIKE) 연산으로 검색해야 한다. "
            "(예: WHERE pd_nm LIKE '%' || '(녹)' || '%')"
        ),
    ),
    "채권특수조건": AttributeSpec(
        column="pd_nm",
        value_type="categorical",
        known_values=["강제상환채권", "중순위채권", "신권", "콜옵션부채권"],
        note=(
            "종목명(pd_nm) 부기 기호로 특수 조건을 판별한다. "
            "(강제)=강제상환, (중)=중순위, (신)=신권, (콜)=콜옵션. "
            "반드시 문자열 포함(LIKE) 연산으로 검색해야 한다."
        ),
    )
}


# 국내ETF: 2026-08-24 배포본(1,780건)으로 다시 검증했다. 이전 배포본 대비
# pd_sect_nm(섹터명)이 삭제되고 ref_/du_vlty_/pd_dvid_/fn_ 계열이 신설되었다.
# "섹터"는 이번에도 카탈로그에 넣지 않았다. pd_sect_cd는 숫자 코드뿐이고
# 이름 매핑이 테이블에 없으며, 반도체/2차전지 같은 테마는 pd_nm 텍스트에만
# 들어 있어 등호 비교로 풀 수 없다(모듈 docstring 참고).
DOMESTIC_ETF_ATTRIBUTES: dict[str, AttributeSpec] = {
    "순자산": AttributeSpec(
        column="pd_net_tamt",
        value_type="numeric",
        note="순자산총액(원). 10.2% 결측. du_last_aum도 유사 계열이지만 이 컬럼을 기본으로 쓴다.",
    ),
    # "AUM"/"NAV"는 질문에 자주 그대로 나오는데 카탈로그에 없어서 매번 LLM
    # 폴백으로 샜다(2026-09-05 Q4 실측: concept_fallback concepts=['AUM','NAV',
    # '각 수치의 기준일']). 폴백은 이름이 비슷한 컬럼을 고르는 경향이 있어
    # AUM -> du_last_aum 을 집어 golden 이 요구한 pd_net_tamt 와 어긋났다.
    # 결정론적으로 잡히도록 별칭 항목을 등록한다.
    "AUM": AttributeSpec(
        column="pd_net_tamt",
        value_type="numeric",
        note="'순자산'의 동의어. du_last_aum 이 이름은 더 비슷해 보이지만 값이 다르다 - "
             "순자산총액은 pd_net_tamt 를 쓴다.",
    ),
    "NAV": AttributeSpec(
        column="du_last_nav",
        value_type="numeric",
        note="최종 NAV(주당 순자산가치). 10.2% 결측. '기준가'와 같은 개념이다.",
    ),
    "위험등급": AttributeSpec(
        column="pd_risk_nm",
        value_type="ordinal",
        value_order=[
            "매우높은위험(1등급)", "높은위험(2등급)", "다소높은위험(3등급)",
            "보통위험(4등급)", "낮은위험(5등급)", "매우낮은위험(6등급)",
        ],
        note=(
            "1등급이 가장 위험하고 6등급이 가장 안전하다. 결측 없고 6종 전부 "
            "실 데이터에서 확인된다. value_order는 등급 번호 오름차순(1등급이 "
            "먼저)이므로 'N등급 이상'은 value_order[idx:], 'N등급 이하'는 "
            "value_order[:idx+1]이 정답이다(utils.resolve_ordinal_matched_values가 계산). "
            "채권 도메인의 pd_risk_nm과 표기가 동일하다."
        ),
    ),
    "투자자산유형": AttributeSpec(
        column="wu_inv_ast_type",
        value_type="categorical",
        known_values=["주식", "채권", "원자재", "대체투자", "혼합자산", "단기자금", "기타", "통화", "부동산"],
        note=(
            "자산군 단위 분류(주식형/채권형 등)이지 반도체 같은 산업 섹터가 "
            "아니다. 결측 없음. 이번 배포본에서 '대체투자'가 새로 생겨 9종이 "
            "되었다. 영문 축이 필요하면 ref_ast_type(32.1% 결측)을 쓴다."
        ),
    ),
    "투자지역": AttributeSpec(
        column="wu_inv_rgn",
        value_type="categorical",
        known_values=["국내", "미국", "글로벌", "중국", "아시아", "일본", "인도", "남미/북미", "유럽", "이머징/브릭스", "베트남"],
        note="결측 없음. 영문 세분화 축이 필요하면 ref_geo_focus(23종, 32.1% 결측)를 쓴다.",
    ),
    "판매가능여부": AttributeSpec(
        column="pd_sale_yn",
        value_type="numeric_flag",
        true_condition="= '1'",
        note=(
            "정수 1(판매가능 1,534건)/0(판매불가 246건). Y/N 문자열이 아니다. "
            "0인 246건 중 245건이 pd_lste_dt(거래종료일자)가 잡혀 있는 종목이라 "
            "주최측 공지의 '상장폐지 혹은 리스팅 종료' 기준과 사실상 일치한다."
        ),
    ),
    "거래종료일": AttributeSpec(
        column="pd_lste_dt",
        value_type="date_yyyymmdd_numeric",
        note=(
            "상품거래종료일자. 1,535건이 99991231이며 이는 '종료 예정 없음'을 "
            "뜻하는 sentinel 값이다. 실제 종료일이 잡힌 종목은 242건뿐이다. "
            "'상장폐지 예정' 조건은 pd_lste_dt <> 99991231로 표현한다."
        ),
    ),
    "상장일": AttributeSpec(
        column="pd_lstg_dt",
        value_type="date_yyyymmdd_numeric",
        note="상품거래가능일자. YYYYMMDD 숫자(예: 20241224.0). 0.2% 결측.",
    ),
    "상품군": AttributeSpec(
        column="pd_grp_no",
        value_type="categorical",
        known_values=["ETF", "ETN"],
        note=(
            "이 테이블은 ETF(1,235건)뿐 아니라 ETN(545건)도 섞여 있다. "
            "'순수 ETF만'이라는 조건이 질문에 있으면 이 컬럼으로 걸러야 한다."
        ),
    ),
    "운용사": AttributeSpec(
        column="cu_fund_mgmt_co",
        value_type="categorical",
        is_organization_name=True,
        note="100종(KB/삼성/iM에셋 등 브랜드 약칭). 결측 없음. 영문이 필요하면 ref_fund_mgmt_co(29종)를 쓴다.",
    ),
    "운용전략": AttributeSpec(
        column="cu_strtegy",
        value_type="categorical",
        known_values=["실물복제", "액티브", "합성복제"],
        note=(
            "정상 값은 이 3종이고, 'C'라는 코드성 오류값이 422건 섞여 있다"
            "(정상 값이 아니므로 등호 비교 시 자연히 제외된다). 8.7% 결측."
        ),
    ),
    "레버리지배수": AttributeSpec(
        column="cu_lev_fector",
        value_type="numeric",
        note=(
            "1.0/1.5/2.0/-1.0/-2.0 등 7종. 음수가 인버스 상품이다. "
            "'레버리지 ETF'는 > 1, '인버스 ETF'는 < 0으로 표현한다. 10.2% 결측."
        ),
    ),
    "총보수율": AttributeSpec(
        # [T-115 / 2026-09-05] 이전 정의는 enriched.etf_kr_enriched 의
        # charge_rt_final 을 봤는데 그 테이블이 현재 배포본에 없다. 총보수는
        # 이제 enriched.product_metric 에 EXPENSE_RATIO 로 정규화돼 있다.
        #
        # product_metric 은 product_id 로 붙는데 base(raw.pref01n001)에는
        # product_id 가 없다. 그래서 enriched.etf_kr 를 거쳐 pd_itm_no 로
        # 되돌아오는 2홉을 파생 테이블 하나로 접어 넣는다(조인 기계가
        # LEFT JOIN <table> AS <alias> ON <cond> 한 홉만 지원하므로).
        #
        # is_available 이 False 인 행은 값이 신뢰 대상이 아니므로 CASE 로
        # NULL 처리한다 - "값이 있는데 못 믿는" 상태를 만들지 않는다.
        column="pm.expense_ratio",
        value_type="numeric",
        join_table=(
            "(SELECT e.pd_itm_no, "
            "CASE WHEN m.is_available THEN m.value END AS expense_ratio, "
            "m.is_available, m.unavailable_reason "
            "FROM enriched.etf_kr e "
            "JOIN enriched.product_metric m ON m.product_id = e.product_id "
            "WHERE m.metric_code = 'EXPENSE_RATIO')"
        ),
        join_alias="pm",
        join_on="pm.pd_itm_no = base.pd_itm_no",
        note=(
            "⚠ 커버리지 5.4%(1,235건 중 67건만 is_available). 정렬·비교의 "
            "기준으로 쓰면 대부분의 종목이 탈락하므로, 이 값으로 '가장 저렴한 "
            "ETF' 같은 순위를 내면 표본이 67건뿐이라는 사실을 답변에 반드시 "
            "밝혀야 한다. "
            "배경: 원본 cu_charge_rt 자체가 87.8% 결측이고, 그 구멍을 메우던 "
            "LSEG 보강(charge_rt_final, 결측 38.3%)이 현재 배포본에서 빠졌다. "
            "남아 있는 67건은 charge_rt_source='RDB'였던 주최측 원본 값이다. "
            "참고로 해외ETF는 같은 cu_charge_rt 로 93.8%(5,604/5,972)가 나오므로 "
            "이 결손은 국내ETF 원천 파일(PREF01N001)에 국한된 문제다. "
            "결측 사유는 파생 테이블의 unavailable_reason 으로 확인할 수 있다."
        ),
    ),
    "기초지수": AttributeSpec(
        column="ref_base_index",
        value_type="text",
        note=(
            "cu_base_index는 7.1% 결측인데도 nunique가 20뿐이라 대부분 공백 "
            "계열이다. 실제 지수명을 쓰려면 ref_base_index(905종, 32.1% 결측)를 "
            "쓰는 편이 낫다."
        ),
    ),
    "1개월수익률": AttributeSpec(column="du_er_1m", value_type="numeric", note="11.0% 결측."),
    "3개월수익률": AttributeSpec(column="du_er_3m", value_type="numeric", note="12.8% 결측."),
    "6개월수익률": AttributeSpec(column="du_er_6m", value_type="numeric", note="16.5% 결측."),
    "1년수익률": AttributeSpec(column="du_er_1y", value_type="numeric", note="20.4% 결측."),
    "연초대비수익률": AttributeSpec(column="du_er_ytd", value_type="numeric", note="17.0% 결측."),
    "변동성": AttributeSpec(
        column="du_vlty_1y",
        value_type="numeric",
        note=(
            "최근 252거래일 연환산 변동성(%). 26.5% 결측. 더 짧은 구간이 "
            "필요하면 du_vlty_1m(5.8% 결측), du_vlty_3m, du_vlty_6m을 쓴다. "
            "이번 배포본에서 새로 생긴 컬럼이다."
        ),
    ),
    "추적오차율": AttributeSpec(column="du_chas_errt", value_type="numeric", note="10.2% 결측. 이전 배포본은 전부 0.0이었으나 이번에는 실제 값이 들어 있다."),
    "괴리율": AttributeSpec(column="du_diff_rt", value_type="numeric", note="10.2% 결측. 이전 배포본은 전부 0.0이었으나 이번에는 실제 값이 들어 있다."),
    "분배수익률": AttributeSpec(column="pd_dvid_yield", value_type="numeric", note="연환산 분배수익률(%). 32.1% 결측. 이번 배포본에서 실제 값이 들어왔다."),
    "분배주기": AttributeSpec(
        column="pd_dvid_cycl",
        value_type="categorical",
        known_values=["M", "Q", "S", "A"],
        note="M=월, Q=분기, S=반기, A=연. 공백 문자열이 422건 섞여 있고 8.4% 결측이다. '월배당 ETF'는 pd_dvid_cycl = 'M'이다.",
    ),
    "거래대금": AttributeSpec(column="du_val_1d", value_type="numeric", note="일거래대금(원). 0.2% 결측."),
    "거래량": AttributeSpec(column="du_vol_1d", value_type="numeric", note="일거래량(주). 0.2% 결측."),
    "종가": AttributeSpec(column="du_clpr", value_type="numeric", note="0.2% 결측."),
    "연금거래가능여부": AttributeSpec(
        column="pd_pen_tr_yn",
        value_type="categorical",
        known_values=["Y", "N"],
        note="결측 없음.",
    ),
    "상품명": AttributeSpec(
        column="pd_nm",
        value_type="text",
        note="결측 없음. 반도체/2차전지 같은 테마 조건은 이 컬럼에 대한 LIKE 매칭으로만 처리할 수 있다.",
    ),
    # §8(Graph->RDB 핸드오프)용: GraphDB의 fp:productCode가 이 컬럼과 같은
    # ISIN 값이다(실측 확인, 예: KR7491510004).
    "상품코드": AttributeSpec(column="pd_itm_no", value_type="text", note="ISIN. 1,780건 전부 유일값. 결측 없음."),
    # "상품번호"는 "상품코드"의 동의어다. 2026-09-05 실측: Q4가 "상품번호와 각
    # 수치의 기준일을 함께 제시해줘"라고 물었는데 카탈로그에 "상품코드"만 있어
    # LLM 폴백으로 샜고, 폴백도 "대응하는 컬럼을 찾지 못해 결과에서 제외"하고
    # 끝났다(golden C1은 pd_itm_no를 요구). "발행사"/"발행기관" 때와 같은
    # 부류라 같은 방식으로 별칭 항목을 하나 더 등록한다.
    "상품번호": AttributeSpec(column="pd_itm_no", value_type="text", note="'상품코드'의 동의어. ISIN. 1,780건 전부 유일값. 결측 없음."),
}

# 해외ETF: 2026-08-24 배포본(6,037건)으로 다시 검증했다. 위험등급에 대응하는
# 컬럼이 이 테이블에는 아예 없다(국내ETF의 pd_risk_cd/pd_risk_nm 같은 짝이 없음).
# 수익률도 du_er_1d(1일)뿐이라 "1년 수익률 기준 정렬" 같은 질문은 이 도메인에서
# RDB만으로 답할 수 없다. 교차질의에서 국내ETF/펀드와 함께 정렬해야 할 때
# 이 점이 문제가 되므로, 그런 질의는 답변 불가로 처리하거나 다른 지표로
# 대체해야 한다.
OVERSEAS_ETF_ATTRIBUTES: dict[str, AttributeSpec] = {
    "순자산": AttributeSpec(
        column="du_last_aum",
        value_type="numeric",
        note="일간 순자산총액(거래통화 기준, 대부분 USD). 3.4% 결측. 원화 환산값이 아니므로 국내 상품과 직접 비교할 때 통화 차이를 언급해야 한다.",
    ),
    "투자자산유형": AttributeSpec(
        column="wu_inv_ast_type",
        value_type="categorical",
        known_values=["Equity", "Alternatives", "Bond", "Mixed Assets", "Commodity", "Money Market"],
        note="값이 영문이다. 0.2% 결측. 국내ETF는 한글이라 교차질의에서 같은 개념이라도 값 표기가 다르다.",
    ),
    "투자지역": AttributeSpec(
        column="wu_inv_rgn",
        value_type="categorical",
        note=(
            "59종, 영문(예: United States of America, Global, Global Ex US). "
            "국내ETF보다 훨씬 세분화되어 있어 known_values를 다 나열하지 않았다. "
            "'아시아'처럼 느슨한 지역명이 질문에 나오면 등호가 아니라 contains "
            "매칭이 필요할 수 있다. 0.2% 결측."
        ),
    ),
    "상장거래소": AttributeSpec(
        column="pd_exg_mkt_cd",
        value_type="categorical",
        known_values=["AMX", "NAS", "NYS"],
        note=(
            "AMX/NAS/NYS가 대다수이고 정체가 불분명한 코드('101','102')가 소수 "
            "있다. 이 컬럼의 값 자체가 '해외 상장'이라는 도메인 분류의 근거이기도 "
            "하다. 결측 없음."
        ),
    ),
    "총보수율": AttributeSpec(
        column="cu_charge_rt",
        value_type="numeric",
        note="연간보수율(%). 결측 없음. 국내ETF의 같은 이름 컬럼(87.8% 결측)과 달리 전부 채워져 있어 정렬에 쓸 수 있다.",
    ),
    "상품군": AttributeSpec(
        column="pd_grp_no",
        value_type="categorical",
        known_values=["ETF", "ETN"],
        note="ETF 5,972건, ETN 65건이 섞여 있다.",
    ),
    # 국내ETF의 "운용사"(901행)와 같은 이유로 is_organization_name을 붙인다 -
    # 이전엔 국내ETF만 표시돼 있었는데, "조직명 컬럼이면 별칭 확장을
    # 받는다"는 규칙이 도메인마다 다르게 적용될 이유가 없다(2026-09-02
    # 전체 카탈로그 점검에서 발견). 이 도메인은 값이 영문(382종)이라
    # graph_ids._ORGANIZATION_ALIASES(한글 발음 표기 전용)의 실질 효과는
    # 없지만, 규칙 자체는 일관되게 유지한다.
    "운용사": AttributeSpec(
        column="cu_fund_mgmt_co", value_type="text", note="영문 382종. 0.2% 결측.",
        is_organization_name=True,
    ),
    "기초지수": AttributeSpec(
        column="cu_base_index",
        value_type="text",
        note="영문 1,850종. 0.2% 결측. 지수를 제공하지 않는 액티브 상품은 'Index is not provided by Management Company'로 표기된다.",
    ),
    "운용전략": AttributeSpec(
        column="cu_strtegy",
        value_type="text",
        note=(
            "영문 자유서술 문장이고 99.8%에 값이 있다. 등호 비교용 범주값이 "
            "아니라 서술형 텍스트이므로, '운용 전략을 설명해줘' 같은 narrative "
            "질문에 이 컬럼 내용을 그대로 인용해 답할 수 있다."
        ),
    ),
    "복제방법": AttributeSpec(
        column="cu_index_repl_mthd",
        value_type="categorical",
        known_values=["Full", "Optimized", "Swap"],
        note="60.1% 결측.",
    ),
    "레버리지배수": AttributeSpec(
        column="cu_lev_fector",
        value_type="numeric",
        note="2.0/-2.0/3.0 등 11종. 85.1% 결측이라 결측이 곧 1배(일반 상품)를 뜻한다. 인버스는 cu_inverse_short_yn = 'Y'로도 판별할 수 있다.",
    ),
    "설정일": AttributeSpec(
        column="pd_lstg_dt",
        value_type="date_yyyymmdd_numeric",
        note="YYYYMMDD 숫자(예: 20070223). 결측 없음.",
    ),
    "1일수익률": AttributeSpec(
        column="du_er_1d",
        value_type="numeric",
        note=(
            "0.2% 결측. 이 도메인에는 1개월/1년 같은 장기 수익률 컬럼이 아예 "
            "없다. 질문이 '1년 수익률 기준'을 요구하면 해외ETF는 RDB만으로 "
            "답할 수 없으므로 그 사실을 명시해야 한다."
        ),
    ),
    "종가": AttributeSpec(column="du_clpr", value_type="numeric", note="0.2% 결측."),
    "거래량": AttributeSpec(column="du_vol_1d", value_type="numeric", note="0.2% 결측."),
    "거래대금": AttributeSpec(column="du_val_1d", value_type="numeric", note="외화 거래대금. 0.2% 결측."),
    "상장주식수": AttributeSpec(column="pd_lst_stk_cnt", value_type="numeric", note="결측 없음."),
    "티커": AttributeSpec(
        column="pd_abrv_nm",
        value_type="text",
        note="질문에서 VOO, QQQ처럼 티커로 상품을 부르면 이 컬럼으로 찾는다. 결측 없음.",
    ),
    "상품명": AttributeSpec(column="pd_nm", value_type="text", note="영문 정식명. 결측 없음."),
    # §8(Graph->RDB 핸드오프)용: GraphDB의 fp:productCode가 이 컬럼과 같은
    # RIC 값이다(실측 확인, 예: APRH.K, SMQ — 해외ETF는 ISIN이 아니라 RIC를
    # productCode로 쓴다. pd_isin_cd가 아니라 pd_itm_no로 매핑해야 한다).
    "상품코드": AttributeSpec(column="pd_itm_no", value_type="text", note="RIC. 6,037건 전부 유일값. 결측 없음."),
    # "상품번호"는 "상품코드"의 동의어다. 2026-09-05 실측: Q4가 "상품번호와 각
    # 수치의 기준일을 함께 제시해줘"라고 물었는데 카탈로그에 "상품코드"만 있어
    # LLM 폴백으로 샜고, 폴백도 "대응하는 컬럼을 찾지 못해 결과에서 제외"하고
    # 끝났다(golden C1은 pd_itm_no를 요구). "발행사"/"발행기관" 때와 같은
    # 부류라 같은 방식으로 별칭 항목을 하나 더 등록한다.
    "상품번호": AttributeSpec(column="pd_itm_no", value_type="text", note="'상품코드'의 동의어. RIC. 6,037건 전부 유일값. 결측 없음."),
    # 주의: '판매가능여부'는 넣지 않았다. pd_sale_yn이 전부 1.0, pd_tr_yn이
    # 전부 0.0이라 걸러지는 것이 없다. DOMAIN_SALE_POLICY["해외ETF"] 참고.
}

# 펀드: 2026-08-24 배포본(23,676건)으로 다시 검증했다. 이전 배포본(95,619건)
# 대비 행이 1/4로 줄고 컬럼은 45개에서 75개로 늘었다. 특히 두 가지가 크게
# 달라졌다.
#   - 사모 비중이 0.1%에서 38%로 늘어 공모/사모 조건이 실제로 필요해졌다.
#   - 순자산과 수익률 계열의 결측률이 13~33%에서 60~75%로 크게 나빠졌다.
#     정렬/필터에서 NULL 제외가 사실상 필수다.
FUND_ATTRIBUTES: dict[str, AttributeSpec] = {
    "순자산": AttributeSpec(
        column="fd_nast_suma",
        value_type="numeric",
        note="펀드 순자산(원). 60.2% 결측(이전 배포본은 13.1%였다). 정렬/필터 시 NULL 제외가 필수다.",
    ),
    "위험등급": AttributeSpec(
        column="zrin_fd_ivst_risk_grd_nm",
        value_type="ordinal",
        value_order=["매우 높은 위험", "높은 위험", "다소 높은 위험", "보통 위험", "낮은 위험", "매우 낮은 위험"],
        note=(
            "1등급(매우 높은 위험)이 가장 위험하고 6등급(매우 낮은 위험)이 가장 "
            "안전하다. 63.3% 결측이라 이 조건을 걸면 후보군이 3분의 1로 줄어든다. "
            "'높은위험'(20건), '보통위험'(8건)처럼 공백이 빠진 표기가 섞여 있어 "
            "REPLACE(zrin_fd_ivst_risk_grd_nm, ' ', '') 같은 정규화 비교를 "
            "권장한다. 값 표기가 국내ETF/채권의 pd_risk_nm('높은위험(2등급)')과 "
            "달라서 교차질의에서 등급을 그대로 비교하면 안 된다. value_order는 "
            "등급 번호 오름차순(1등급이 먼저)이라 gte/lte 계산 방식은 다른 "
            "도메인과 동일하다."
        ),
    ),
    "펀드유형": AttributeSpec(
        column="or_attr_desc",
        value_type="categorical",
        known_values=[
            "주식형", "채권형", "재간접", "채권혼합", "파생상품", "혼합자산",
            "주식혼합", "특별자산", "MMF", "임대형", "기타", "대출형", "개발형", "해당없음",
        ],
        note=(
            "14종이고 결측 없음. 이전 배포본에 있던 '06' 코드성 오류값은 "
            "사라졌고 파생상품(2,302건)/개발형/기타가 새로 생겼다."
        ),
    ),
    "판매가능여부": AttributeSpec(
        column="sale_yn",
        value_type="numeric_flag", # categorical에서 numeric_flag로 변경하여 참/거짓 매핑을 활성화합니다.
        true_condition="= '판매중'", # [핵심 추가] LLM에게 true일 때 이 조건을 쓰라고 명시합니다.
        known_values=["판매중", "판매완료"],
        note=(
            "'판매중'(10,962건)이면 판매 가능하고 '판매완료'(12,714건)면 불가다. "
            "다른 도메인처럼 0/1이나 Y/N 플래그가 아니라 텍스트 상태값이다. "
            "변별력이 커서 이 조건 유무에 따라 결과가 크게 달라진다."
        ),
    ),
    "공모사모구분": AttributeSpec(
        column="prvo_pbff_desc",
        value_type="categorical",
        known_values=["공모", "사모"],
        note=(
            "공모 14,716건 / 사모 8,960건. 이전 배포본(사모 102건)과 달리 사모가 "
            "38%를 차지하므로, 과제가 공모펀드 대상임을 감안하면 별도 지시가 "
            "없어도 공모 조건을 거는 것을 검토해야 한다."
        ),
    ),
    "투자지역": AttributeSpec(
        column="fd_ivst_rgn_desc",
        value_type="categorical",
        known_values=["국내", "글로벌", "해당없음", "아시아", "남미/북미", "유럽", "이머징/브릭스", "기타", "중동/아프리카"],
        note="결측 없음. '해당없음'이 3,678건 있어 지역 조건을 걸면 이들은 제외된다.",
    ),
    "해외국내구분": AttributeSpec(
        column="ovrs_fd_desc",
        value_type="categorical",
        known_values=["국내", "해외", "국내외혼합", "해당없음"],
        note="투자지역(fd_ivst_rgn_desc)과 다른 축이다. 이건 펀드 자체가 어디에 설정된 상품인지를 나타낸다. 결측 없음.",
    ),
    "통화": AttributeSpec(
        column="curr_cd",
        value_type="categorical",
        known_values=["KRW", "USD", "EUR", "JPY", "AUD", "GBP", "SEK"],
        note="KRW 23,147건이 대부분이고 나머지는 소수다. 결측 없음.",
    ),
    "환헤지여부": AttributeSpec(
        column="exchdg_yn",
        value_type="categorical",
        known_values=["Y", "N"],
        note="70.5% 결측이라 이 조건을 걸면 후보군이 30%로 줄어든다.",
    ),
    "이자배당구분": AttributeSpec(
        column="int_dvd_desc",
        value_type="categorical",
        known_values=["배당", "이자", "해당없음"],
        note="결측 없음.",
    ),
    "판매채널": AttributeSpec(
        column="han_clas_sales_channel",
        value_type="categorical",
        known_values=["온라인", "오프라인", "직판"],
        note="59.4% 결측(클래스가 나뉜 펀드에만 값이 있다). 이번 배포본에서 새로 생긴 컬럼이다.",
    ),
    "수수료유형": AttributeSpec(
        column="han_clas_fee_type",
        value_type="categorical",
        known_values=["수수료미징구", "수수료선취", "수수료후취"],
        note="59.3% 결측. 이번 배포본에서 새로 생긴 컬럼이다.",
    ),
    "클래스명": AttributeSpec(
        column="han_clas_nm",
        value_type="text",
        note="195종(예: 수수료미징구-온라인). 59.3% 결측. 같은 모펀드의 클래스를 묶으려면 rptt_ksd_itm_no를 쓴다.",
    ),
    "판매회사보수": AttributeSpec(column="sale_co_rwrd_r", value_type="numeric", note="결측 없음."),
    "운용보수": AttributeSpec(column="or_co_rwrd_r", value_type="numeric", note="집합투자업자보수(%). 결측 없음."),
    "신탁보수": AttributeSpec(column="trusc_rwrd_r", value_type="numeric", note="신탁업자보수(%). 결측 없음."),
    "사무관리보수": AttributeSpec(column="ofwk_trus_rwrd_r", value_type="numeric", note="일반사무관리보수(%). 결측 없음."),
    "1개월수익률": AttributeSpec(column="fd_mm1_ern_r", value_type="numeric", note="68.8% 결측."),
    "3개월수익률": AttributeSpec(column="fd_mm3_ern_r", value_type="numeric", note="69.1% 결측."),
    "6개월수익률": AttributeSpec(column="fd_mm6_ern_r", value_type="numeric", note="69.5% 결측."),
    "1년수익률": AttributeSpec(column="fd_yr1_ern_r", value_type="numeric", note="70.3% 결측. 정렬 시 NULL 제외 필수."),
    "2년수익률": AttributeSpec(column="fd_yr2_ern_r", value_type="numeric", note="71.5% 결측."),
    "3년수익률": AttributeSpec(column="fd_yr3_ern_r", value_type="numeric", note="72.6% 결측."),
    "5년수익률": AttributeSpec(column="fd_yr5_ern_r", value_type="numeric", note="74.7% 결측."),
    "국내주식구성비율": AttributeSpec(column="zrin_dmst_stk_cmst_rt", value_type="numeric", note="60.2% 결측."),
    "해외주식구성비율": AttributeSpec(column="zrin_ovrs_stk_cmst_rt", value_type="numeric", note="60.2% 결측."),
    "국내채권구성비율": AttributeSpec(column="zrin_dmst_bd_cmst_rt", value_type="numeric", note="60.2% 결측."),
    "해외채권구성비율": AttributeSpec(column="zrin_ovrs_bd_cmst_rt", value_type="numeric", note="60.2% 결측."),
    "벤치마크": AttributeSpec(column="bmrk_nm", value_type="text", note="국문 389종. 52.4% 결측."),
    "상품명": AttributeSpec(column="itm_nm", value_type="text", note="종목명(정식). 결측 없음."),
    # §8(Graph->RDB 핸드오프)용: GraphDB의 fp:productCode가 이 컬럼과 같은
    # ISIN 값이다(실측 확인, 예: KR5153490900).
    "상품코드": AttributeSpec(column="itm_no", value_type="text", note="ISIN(종목번호). 23,676건 전부 유일값. 결측 없음."),
    # "상품번호"는 "상품코드"의 동의어다. 2026-09-05 실측: Q4가 "상품번호와 각
    # 수치의 기준일을 함께 제시해줘"라고 물었는데 카탈로그에 "상품코드"만 있어
    # LLM 폴백으로 샜고, 폴백도 "대응하는 컬럼을 찾지 못해 결과에서 제외"하고
    # 끝났다(golden C1은 pd_itm_no를 요구). "발행사"/"발행기관" 때와 같은
    # 부류라 같은 방식으로 별칭 항목을 하나 더 등록한다.
    "상품번호": AttributeSpec(column="itm_no", value_type="text", note="'상품코드'의 동의어. ISIN(종목번호). 23,676건 전부 유일값. 결측 없음."),
    # 주의: 이 테이블에는 운용사 '이름' 컬럼이 없다. or_co_xtn_itt_cd(275종)는
    # 코드일 뿐이고 이름 매핑 테이블이 별도로 필요하다. "미래에셋에서 운용하는
    # 펀드" 같은 질문은 itm_nm(종목명)에 운용사명이 들어 있는 경우에만
    # LIKE 매칭으로 처리할 수 있다.
}

ATTRIBUTE_CATALOG: dict[str, dict[str, AttributeSpec]] = {
    "채권": BOND_ATTRIBUTES,
    "국내ETF": DOMESTIC_ETF_ATTRIBUTES,
    "해외ETF": OVERSEAS_ETF_ATTRIBUTES,
    "펀드": FUND_ATTRIBUTES,
}


# 도메인별 개념 카탈로그의 검증 수준. 넷 다 2026-08-24 배포본 data.xlsx로
# 직접 프로파일링해서 검증했으므로 전부 verified다.
ATTRIBUTE_CATALOG_STATUS: dict[str, str] = {
    "채권": "verified",
    "국내ETF": "verified",
    "해외ETF": "verified",
    "펀드": "verified",
}


# ---------------------------------------------------------------------------
# 도메인별로 SQL을 쓸 때 반드시 지켜야 하는 주의사항.
# SQL 생성 프롬프트에 그대로 끼워 넣을 수 있는 문장으로 적어 둔다.
# ---------------------------------------------------------------------------
DOMAIN_SQL_CAVEATS: dict[str, list[str]] = {
    "채권": [
        "한 종목(pd_no)이 info_seq 때문에 여러 행으로 나올 수 있다(21,882행 / 20,497 고유 종목). "
        "종목 개수를 세거나 상위 N개를 뽑을 때는 DISTINCT pd_no를 쓰거나 info_seq = 1 조건을 건다.",
        "'판매 가능한' 조건은 SQL에 넣지 않는다. buyable_quantity는 주최측이 무효로 공지한 컬럼이고, "
        "이 테이블에는 상장폐지 여부 컬럼이 없어 전 종목을 구매가능으로 간주한다.",
        "수익률 기준 정렬이면 applied_yield(민평수익률, 결측 없음)를 쓴다. "
        "buy_yield는 97.1% 결측이라 정렬에 쓰면 대부분의 종목이 사라진다.",
        "pd_nm을 제외한 이름 계열 컬럼(pd_abrv_nm, pd_pbcm, bd_knd)에는 공백 패딩이 있어 TRIM 비교가 필요하다.",
        "상품명으로 특정 종목을 찾을 때는 원문과 공백제거본을 OR 로 함께 건다: "
        "(pd_nm LIKE '%키워드%' OR REPLACE(pd_nm, ' ', '') LIKE '%키워드에서공백뺀것%'). "
        "REPLACE 를 컬럼에만 걸고 키워드에 공백을 남기면 0건이 된다(실측). 아래 ESG채권 "
        "기호 규칙은 그대로 지킨다(기호에는 공백이 없어 충돌하지 않는다).",
        "상품명(pd_nm)으로 ESG채권을 검색할 때, '사회적채권'은 반드시 '%(사)%', '녹색채권'은 '%(녹)%', '지속가능채권'은 '%(지)%' 라는 기호 형태로만 검색해야 한다. LIKE '%사회적채권%' 처럼 원본 단어를 그대로 쓰면 데이터가 0건이 되므로 절대 임의로 변형하지 말 것.",
    ],
    "국내ETF": [
        "이 테이블에는 ETN(545건)이 섞여 있다. 질문이 ETF만 요구하면 pd_grp_no = 'ETF' 조건을 건다.",
        "반도체, 2차전지 같은 테마 조건은 등호로 풀 수 없다. pd_nm LIKE '%키워드%' 매칭으로만 가능하다.",
        # ⚠ 이 문구에 물리 테이블 이름을 적지 않는다. 2026-09-03 실측 trace 에서
        # 확인된 사고다: 예전 문구가 "enriched.etf_kr_enriched 의 charge_rt_final
        # 을 쓴다"고 적혀 있었고, 이 caveat 은 utils.py 가 국내ETF 질의 **전부**에
        # 주입한다. 그래서 총보수와 아무 상관 없는 질문(Q23 편입기업/테마, Q30
        # 상품명 검색)에서도 LLM 이 그 테이블명을 배워 JOIN 을 지어냈고,
        # UndefinedTable 로 3회 재시도를 모두 태웠다(7문항 24회차).
        # 조인이 필요한 질의에는 [해석된 스키마]가 JOIN 절을 이미 넣어 준다.
        "총보수율은 [해석된 스키마]에 나온 컬럼으로만 조회한다. JOIN 절이 필요한 "
        "경우 이미 포함되어 있으므로 직접 JOIN 을 쓰거나 테이블 이름을 지어내지 "
        "말 것. 원본 cu_charge_rt 는 87.8% 결측이라 직접 쓰지 않는다. "
        "다만 총보수 값 자체가 1,235건 중 67건(5.4%)에만 있으므로, 총보수 기준 "
        "정렬·최저가 질의는 표본이 67건이라는 사실을 답변에 함께 밝힌다. "
        "조건을 만족하는 종목이 없으면 없다고 답하고 다른 컬럼으로 대체하지 않는다.",
        "순자산은 pd_net_tamt를 쓴다. du_last_aum도 있지만 값이 미세하게 다르다. "
        "질문이 'AUM'이라고 해도 마찬가지로 pd_net_tamt다(이름이 비슷하다고 du_last_aum을 "
        "고르면 golden과 값이 어긋난다 - 실측).",
        "기초지수는 ref_base_index를 쓴다. cu_base_index는 이름이 비슷하지만 nunique가 "
        "20뿐이고 대부분 공백이라 SELECT에 넣으면 빈 값이 나온다(2026-09-05 Q4 실측). "
        "[해석된 스키마]가 지정한 컬럼을 비슷해 보이는 다른 컬럼으로 바꾸지 말 것.",
        # 2026-09-05 실측 사고. Q4가 "KODEX 200"을 물었는데 LLM이 그대로
        # LIKE '%KODEX 200%'를 썼다. 정작 본체인 KR7069500007의 표기는
        # '삼성 KODEX200 증권상장지수투자신탁[주식]'(붙여쓰기)라 안 걸리고,
        # 띄어쓰기가 있는 파생상품 14건만 걸렸다. 그래서 답변이
        # "조건에 맞는 상품이 없습니다"로 나갔다 - 데이터는 있는데 못 찾은 것이다.
        "상품명으로 특정 종목을 찾을 때는 원문과 공백제거본을 **OR 로 함께** 건다. "
        "맞는 형태: (pd_nm LIKE '%KODEX 200%' OR REPLACE(pd_nm, ' ', '') LIKE '%KODEX200%') "
        "틀린 형태 1: TRIM(pd_nm) LIKE '%KODEX 200%' (TRIM은 양끝 공백만 지운다) "
        "틀린 형태 2: REPLACE(pd_nm, ' ', '') LIKE '%KODEX 200%' "
        "(컬럼만 공백을 지우고 키워드에 공백을 남기면 매칭이 0건이 된다 - 실측 실패). "
        "OR 형태를 쓰면 둘 중 한쪽만 맞아도 걸리므로 안전하다. "
        "이 규칙이 없으면 원본 표기가 붙여쓰기인 종목이 결과에서 통째로 빠진다 "
        "(KR7069500007 '삼성 KODEX200 증권상장지수투자신탁[주식]'이 그렇게 누락되고 "
        "띄어쓰기가 있는 파생상품 14건만 걸렸다). "
        "여러 건이 걸리고 질문이 특정 한 종목을 지목한 것이면, 이름이 가장 짧은 "
        "것이 기본 상품이고 나머지는 접미사가 붙은 파생상품이다. 이때 반드시 "
        "ORDER BY LENGTH(REPLACE(pd_nm, ' ', '')) ASC 를 붙여 기본 상품이 첫 행에 "
        "오게 한다. 이 정렬이 없으면 파생상품이 먼저 나와 답변이 엉뚱한 종목부터 "
        "설명하고, 목록이 길어져 정작 질문한 종목이 잘려 나간다(실측).",
    ],
    "해외ETF": [
        "이 도메인에는 위험등급 컬럼이 아예 없다. 위험등급 조건이 걸리면 답변 불가로 처리한다.",
        "수익률은 du_er_1d(1일)뿐이다. '1년 수익률' 같은 조건은 이 도메인에서 답할 수 없다.",
        "순자산(du_last_aum)은 USD 기준이라 원화 기준인 국내 상품과 직접 비교하면 안 된다.",
        "투자자산유형과 투자지역 값이 영문이라 국내ETF(한글)와 교차질의할 때 값 매핑이 필요하다.",
        "상품명으로 특정 종목을 찾을 때는 원문과 공백제거본을 OR 로 함께 건다: "
        "(pd_nm LIKE '%키워드%' OR REPLACE(pd_nm, ' ', '') LIKE '%키워드에서공백뺀것%'). "
        "REPLACE 를 컬럼에만 걸고 키워드에 공백을 남기면 0건이 된다(실측). OR 형태는 "
        "한쪽만 맞아도 걸리므로 안전하다.",
    ],
    "펀드": [
        "사모펀드가 8,960건(38%) 섞여 있다. 공모펀드만 대상이면 prvo_pbff_desc = '공모' 조건을 건다.",
        "순자산과 수익률 계열이 60~75% 결측이다. 정렬 시 반드시 IS NOT NULL 조건을 함께 건다.",
        "총보수 합산 컬럼이 없다. 필요하면 sale_co_rwrd_r + or_co_rwrd_r + trusc_rwrd_r + ofwk_trus_rwrd_r로 직접 더한다.",
        "운용사 이름 컬럼이 없다. or_co_xtn_itt_cd는 코드일 뿐이라 운용사명 조건은 itm_nm LIKE 매칭으로만 근사할 수 있다.",
        "위험등급 값 표기가 '높은 위험'처럼 공백이 들어간 형태라 국내ETF의 '높은위험(2등급)'과 다르다.",
        "상품명으로 특정 종목을 찾을 때는 원문과 공백제거본을 OR 로 함께 건다: "
        "(itm_nm LIKE '%키워드%' OR REPLACE(itm_nm, ' ', '') LIKE '%키워드에서공백뺀것%'). "
        "REPLACE 를 컬럼에만 걸고 키워드에 공백을 남기면 0건이 된다(실측).",
    ],
}


def get_attribute_catalog(domain: str) -> dict[str, AttributeSpec]:
    return ATTRIBUTE_CATALOG.get(domain, {})


def get_domain_entry(domain: str) -> dict | None:
    """select_table_and_columns_node가 쓰기 편하도록 {"table", "attributes"}
    형태로 묶어서 돌려준다. 4개 도메인 전부 등록되어 있으므로 None은 원래
    정의된 4개 밖의 이름을 넣었을 때만 나온다."""
    if domain not in DOMAIN_TABLE_INFO:
        return None
    return {"table": DOMAIN_TABLE_INFO[domain]["table"], "attributes": ATTRIBUTE_CATALOG.get(domain, {})}


def get_full_column_list(domain: str) -> list[str]:
    """노드 3의 LLM 폴백(카탈로그에 없는 개념을 실제 컬럼에 매칭)에 넘길
    "이 도메인의 실제 컬럼명 전체" 목록. 컬럼명과 설명을 함께 묶어서 준다."""
    if domain not in RDB_SCHEMA:
        raise KeyError(f"알 수 없는 domain: {domain!r}")

    properties = RDB_SCHEMA[domain]["properties"]
    return [
        f"{col_name} ({props.get('description', '설명 없음')})"
        for col_name, props in properties.items()
    ]


def get_sql_caveats(domain: str) -> list[str]:
    """SQL 생성 프롬프트에 끼워 넣을 도메인별 주의사항."""
    return DOMAIN_SQL_CAVEATS.get(domain, [])


def get_sale_policy(domain: str) -> dict[str, str]:
    """'판매 가능한' 조건을 이 도메인에서 어떻게 처리할지 돌려준다.
    mode가 "no_filter"면 조건을 아예 걸지 않고, "column_filter"면
    condition 문자열을 WHERE 절에 그대로 붙인다."""
    return DOMAIN_SALE_POLICY.get(domain, {"mode": "no_filter", "reason": "등록되지 않은 도메인"})


# ---------------------------------------------------------------------------
# subtype(하위 상품유형) -> 실제 조건 매핑.
#
# utils.collect_needed_concepts/build_condition_list는 원래 subtype[0]
# 하나를 "상품유형"이라는 개념 이름 하나로 뭉뚱그려 ATTRIBUTE_CATALOG에서
# 찾았다. 채권은 이게 맞다(회사채/특수채/국공채가 std_pd_mcls_nm 하나로
# 전부 표현된다). 하지만 ETF/펀드는 subtype 값마다 실제로 가리키는 컬럼이
# 다르다 - "레버리지"/"인버스"는 배수 컬럼의 부호나 크기 문제고, 펀드의
# "공모"/"사모"는 "채권형"/"주식형"과 다른 컬럼(prvo_pbff_desc)에
# 대응한다. 개념 이름 하나에 컬럼 하나를 고정하는 기존 구조로는 이걸
# 표현할 수 없다.
#
# 그래서 subtype은 이제 개념명 경유(ATTRIBUTE_CATALOG 조회)가 아니라
# 여기서 값 단위로 직접 (column, operator, value)를 반환한다. 매핑이
# 없는 값(예: 국내ETF "테마형" - pd_nm 텍스트에만 있고 컬럼이 없다)은
# None을 돌려주고, 호출부(utils.resolve_subtype_conditions)는 이 경우
# 조건을 걸지 않고 넘어간다. 값 하나가 매핑이 없다고 질문 전체를 막으면
# 안 된다 - 실제로 이걸 안 챙기면 "레버리지 ETF" 같은 흔한 질문이 통째로
# "미해결 개념"으로 답변불가 처리된다(2026-08-31 실측 확인).
# ---------------------------------------------------------------------------
SUBTYPE_CONDITION_MAP: dict[str, dict[str, dict]] = {
    "채권": {
        # 1. 상품중분류명 (std_pd_mcls_nm) - 3종
        "국공채": {"column": "std_pd_mcls_nm", "operator": "eq", "value": "국공채"},
        "특수채": {"column": "std_pd_mcls_nm", "operator": "eq", "value": "특수채"},
        "회사채": {"column": "std_pd_mcls_nm", "operator": "eq", "value": "회사채"},
        
        # 2. 상품소분류명 (std_pd_scls_nm) - 13종
        "공모지방채": {"column": "std_pd_scls_nm", "operator": "eq", "value": "공모지방채"},
        "공사채": {"column": "std_pd_scls_nm", "operator": "eq", "value": "공사채"},
        "국고채": {"column": "std_pd_scls_nm", "operator": "eq", "value": "국고채"},
        "국민주택": {"column": "std_pd_scls_nm", "operator": "eq", "value": "국민주택"},
        "기타국채": {"column": "std_pd_scls_nm", "operator": "eq", "value": "기타국채"},
        "기타사채": {"column": "std_pd_scls_nm", "operator": "eq", "value": "기타사채"},
        "도시철도": {"column": "std_pd_scls_nm", "operator": "eq", "value": "도시철도"},
        "물가채": {"column": "std_pd_scls_nm", "operator": "eq", "value": "물가채"},
        "은행채": {"column": "std_pd_scls_nm", "operator": "eq", "value": "은행채"},
        "일반사채": {"column": "std_pd_scls_nm", "operator": "eq", "value": "일반사채"},
        "중앙은행채": {"column": "std_pd_scls_nm", "operator": "eq", "value": "중앙은행채"},
        "지역개발": {"column": "std_pd_scls_nm", "operator": "eq", "value": "지역개발"},
        "특수은행채": {"column": "std_pd_scls_nm", "operator": "eq", "value": "특수은행채"},

        # 3. 채권종류명 (bd_knd) - 예탁원 기준 32종
        "Conduit회사채": {"column": "bd_knd", "operator": "eq", "value": "Conduit회사채"},
        "MBS": {"column": "bd_knd", "operator": "eq", "value": "MBS"},
        "국고채권": {"column": "bd_knd", "operator": "eq", "value": "국고채권"},
        "국민주택1종": {"column": "bd_knd", "operator": "eq", "value": "국민주택1종"},
        "국민주택2종": {"column": "bd_knd", "operator": "eq", "value": "국민주택2종"},
        "금융지주회사채": {"column": "bd_knd", "operator": "eq", "value": "금융지주회사채"},
        "기업인수목적회사채": {"column": "bd_knd", "operator": "eq", "value": "기업인수목적회사채"},
        "기타금융투자전업회사채": {"column": "bd_knd", "operator": "eq", "value": "기타금융투자전업회사채"},
        "기타금융회사채": {"column": "bd_knd", "operator": "eq", "value": "기타금융회사채"},
        "도시철도공채": {"column": "bd_knd", "operator": "eq", "value": "도시철도공채"},
        "모집지방채": {"column": "bd_knd", "operator": "eq", "value": "모집지방채"},
        "보험회사채": {"column": "bd_knd", "operator": "eq", "value": "보험회사채"},
        "부동산투자회사채": {"column": "bd_knd", "operator": "eq", "value": "부동산투자회사채"},
        "시설대여채": {"column": "bd_knd", "operator": "eq", "value": "시설대여채(리스)"},
        "리스채": {"column": "bd_knd", "operator": "eq", "value": "시설대여채(리스)"},
        "신용카드채": {"column": "bd_knd", "operator": "eq", "value": "신용카드채"},
        "외국환평형기금": {"column": "bd_knd", "operator": "eq", "value": "외국환평형기금"},
        "유동화수익증권": {"column": "bd_knd", "operator": "eq", "value": "유동화수익증권"},
        "유동화회사채": {"column": "bd_knd", "operator": "eq", "value": "유동화회사채"},
        "일반은행채": {"column": "bd_knd", "operator": "eq", "value": "일반은행채"},
        "일반지방공사채": {"column": "bd_knd", "operator": "eq", "value": "일반지방공사채"},
        "일반특수법인채": {"column": "bd_knd", "operator": "eq", "value": "일반특수법인채"},
        "일반회사채": {"column": "bd_knd", "operator": "eq", "value": "일반회사채"},
        "재정증권": {"column": "bd_knd", "operator": "eq", "value": "재정증권"},
        "증권금융채": {"column": "bd_knd", "operator": "eq", "value": "증권금융채(특수금융)"},
        "지방공사보상채권": {"column": "bd_knd", "operator": "eq", "value": "지방공사보상채권"},
        "지역개발채": {"column": "bd_knd", "operator": "eq", "value": "지역개발채"},
        "집합투자회사채": {"column": "bd_knd", "operator": "eq", "value": "집합투자회사채"},
        "통화안정채권": {"column": "bd_knd", "operator": "eq", "value": "통화안정채권"},
        "투자매매중개채": {"column": "bd_knd", "operator": "eq", "value": "투자매매.중개채"}, # 점(.) 제거하여 자연어 검색 용이하게 매핑
        "특수보상채권": {"column": "bd_knd", "operator": "eq", "value": "특수보상채권"},
        "특수은행채": {"column": "bd_knd", "operator": "eq", "value": "특수은행채"},
        "할부금융채": {"column": "bd_knd", "operator": "eq", "value": "할부금융채"},

        # 4. 금리구분 (bd_inrt_tcd)
        "고정금리": {"column": "bd_inrt_tcd", "operator": "eq", "value": "고정금리"},
        "변동금리": {"column": "bd_inrt_tcd", "operator": "eq", "value": "변동금리"},
        "고정변동금리": {"column": "bd_inrt_tcd", "operator": "eq", "value": "고정+변동금리"},
        "혼합형금리": {"column": "bd_inrt_tcd", "operator": "eq", "value": "고정+변동금리"},

        # 5. 이자지급구분 (bd_intp_tcd)
        "단리채": {"column": "bd_intp_tcd", "operator": "eq", "value": "단리채"},
        "복리채": {"column": "bd_intp_tcd", "operator": "eq", "value": "복리채"},
        "이표채": {"column": "bd_intp_tcd", "operator": "eq", "value": "이표채"},
        "할인채": {"column": "bd_intp_tcd", "operator": "eq", "value": "할인채"},

        # 6. 거래구분 (pd_exg_mkt) - 유사어 확장
        "장내": {"column": "pd_exg_mkt", "operator": "eq", "value": "장내"},
        "장내거래": {"column": "pd_exg_mkt", "operator": "eq", "value": "장내"},
        "장내채권": {"column": "pd_exg_mkt", "operator": "eq", "value": "장내"},
        "장외": {"column": "pd_exg_mkt", "operator": "eq", "value": "장외"},
        "장외거래": {"column": "pd_exg_mkt", "operator": "eq", "value": "장외"},
        "장외채권": {"column": "pd_exg_mkt", "operator": "eq", "value": "장외"},

        # 7. 모집구분 (bd_ofr_tcd) - 유사어 확장
        "공모": {"column": "bd_ofr_tcd", "operator": "eq", "value": "공모"},
        "공모발행": {"column": "bd_ofr_tcd", "operator": "eq", "value": "공모"},
        "공모채권": {"column": "bd_ofr_tcd", "operator": "eq", "value": "공모"},
        "사모": {"column": "bd_ofr_tcd", "operator": "eq", "value": "사모"},
        "사모발행": {"column": "bd_ofr_tcd", "operator": "eq", "value": "사모"},
        "사모채권": {"column": "bd_ofr_tcd", "operator": "eq", "value": "사모"},

        # 8. 비정형 부기 기호 매핑 (pd_nm LIKE) - 데이터 기반 완벽 확장
        "녹색채권": {"column": "pd_nm", "operator": "contains", "value": "(녹)"},
        "사회적채권": {"column": "pd_nm", "operator": "contains", "value": "(사)"},
        "지속가능채권": {"column": "pd_nm", "operator": "contains", "value": "(지)"},
        "ESG채권": {"column": "pd_nm", "operator": "contains", "value": "(녹)"},
        "강제상환채권": {"column": "pd_nm", "operator": "contains", "value": "(강제)"},
        "강제상환": {"column": "pd_nm", "operator": "contains", "value": "(강제)"},
        "중순위채권": {"column": "pd_nm", "operator": "contains", "value": "(중)"},
        "중순위": {"column": "pd_nm", "operator": "contains", "value": "(중)"},
        "신권": {"column": "pd_nm", "operator": "contains", "value": "(신)"},
        "콜옵션부채권": {"column": "pd_nm", "operator": "contains", "value": "(콜)"},
        "콜옵션": {"column": "pd_nm", "operator": "contains", "value": "(콜)"},
        "후순위채권": {"column": "pd_nm", "operator": "contains", "value": "(후)"},
        "후순위": {"column": "pd_nm", "operator": "contains", "value": "(후)"},
        "풋옵션부채권": {"column": "pd_nm", "operator": "contains", "value": "(풋)"},
        "풋옵션": {"column": "pd_nm", "operator": "contains", "value": "(풋)"},
        "전환사채": {"column": "pd_nm", "operator": "contains", "value": "(전환)"},
        "교환사채": {"column": "pd_nm", "operator": "contains", "value": "(교환)"},
        "조건부자본증권": {"column": "pd_nm", "operator": "contains", "value": "(조건상각)"},
        "상각형조건부자본증권": {"column": "pd_nm", "operator": "contains", "value": "(조건상각)"},
    },
    "국내ETF": {
        "실물복제": {"column": "cu_strtegy", "operator": "eq", "value": "실물복제"},
        "합성복제": {"column": "cu_strtegy", "operator": "eq", "value": "합성복제"},
        "액티브": {"column": "cu_strtegy", "operator": "eq", "value": "액티브"},
        "레버리지": {"column": "cu_lev_fector", "operator": ">", "value": "1"},
        "인버스": {"column": "cu_lev_fector", "operator": "<", "value": "0"},
        # "테마형"은 대응 컬럼이 없다(모듈 docstring의 섹터/테마 설명 참고).
        # 이 값은 매핑을 안 넣어서 조건 없이 넘어가게 한다.
    },
    "해외ETF": {
        "레버리지": {"column": "cu_lev_fector", "operator": ">", "value": "1"},
        "인버스": {"column": "cu_lev_fector", "operator": "<", "value": "0"},
    },
    "펀드": {
        "주식형": {"column": "or_attr_desc", "operator": "eq", "value": "주식형"},
        "채권형": {"column": "or_attr_desc", "operator": "eq", "value": "채권형"},
        "채권혼합": {"column": "or_attr_desc", "operator": "eq", "value": "채권혼합"},
        "주식혼합": {"column": "or_attr_desc", "operator": "eq", "value": "주식혼합"},
        "혼합자산": {"column": "or_attr_desc", "operator": "eq", "value": "혼합자산"},
        "혼합형": {"column": "or_attr_desc", "operator": "eq", "value": "혼합자산"},  # 질문에서 흔히 쓰는 표현
        "재간접": {"column": "or_attr_desc", "operator": "eq", "value": "재간접"},
        "특별자산": {"column": "or_attr_desc", "operator": "eq", "value": "특별자산"},
        "MMF": {"column": "or_attr_desc", "operator": "eq", "value": "MMF"},
        "파생상품": {"column": "or_attr_desc", "operator": "eq", "value": "파생상품"},
        "공모": {"column": "prvo_pbff_desc", "operator": "eq", "value": "공모"},
        "사모": {"column": "prvo_pbff_desc", "operator": "eq", "value": "사모"},
    },
}


def resolve_subtype_condition(domain: str, subtype_value: str) -> dict | None:
    """subtype 값 하나를 실제 (column, operator, value) 조건으로 매핑한다.
    매핑이 없으면 None이며, 호출부는 이 경우 조건을 걸지 않고 넘어가야
    한다(억지로 아무 컬럼에나 끼워 맞추면 조용히 틀린 0건 결과가 나온다)."""
    return SUBTYPE_CONDITION_MAP.get(domain, {}).get(subtype_value)


# ---------------------------------------------------------------------------
# 스키마 계약 검증 (T-115)
#
# 이 카탈로그는 "의미"의 정본이지 "물리적 존재"의 정본이 아니다. 어떤 테이블이
# 실제로 있는지는 tools.schema_snapshot 이 live information_schema 에서 읽는다.
# 둘이 어긋난 채로 돌면 SQL 이 실패하고, 실패한 SQL 을 고치는 nodes._fix_sql 이
# 다시 이 카탈로그를 근거로 삼기 때문에 같은 오답을 반복한다(수렴 불가).
# 그래서 어긋남은 쿼리 시점이 아니라 기동 시점에 잡는다.
# ---------------------------------------------------------------------------

# join_table 이 파생 테이블 "(SELECT ...)" 인 경우, 그 서브쿼리가 실제로 읽는
# 물리 테이블과 컬럼을 여기 적어 둔다. 문자열 파싱으로 추출하면 조용히
# 틀리므로 손으로 선언하고, 아래 iter_* 가 이걸 같이 검사한다.
DERIVED_JOIN_PHYSICAL_REFS: dict[str, dict[str, list]] = {
    "총보수율": {
        "tables": ["enriched.etf_kr", "enriched.product_metric"],
        "columns": [
            ("enriched.etf_kr", "pd_itm_no"),
            ("enriched.etf_kr", "product_id"),
            ("enriched.product_metric", "product_id"),
            ("enriched.product_metric", "metric_code"),
            ("enriched.product_metric", "value"),
            ("enriched.product_metric", "is_available"),
            ("enriched.product_metric", "unavailable_reason"),
        ],
    },
}


def iter_catalog_table_refs() -> set[str]:
    """카탈로그가 물리적 존재를 전제하는 테이블 전체를 모은다.

    상수를 손으로 나열하지 않고 카탈로그에서 도출한다 - 나열식으로 두면
    항목이 늘어날 때 검증만 조용히 뒤처진다.
    """
    refs: set[str] = set()

    for entry in DOMAIN_TABLE_INFO.values():
        refs.add(entry["table"])

    for domain_attrs in ATTRIBUTE_CATALOG.values():
        for concept, spec in domain_attrs.items():
            if not spec.join_table:
                continue
            if spec.join_table.lstrip().startswith("("):
                # 파생 테이블: 선언된 물리 의존만 검사한다.
                refs.update(DERIVED_JOIN_PHYSICAL_REFS.get(concept, {}).get("tables", []))
            else:
                refs.add(spec.join_table)

    return refs


def iter_catalog_column_refs() -> set[tuple[str, str]]:
    """카탈로그가 존재를 전제하는 (테이블, 컬럼) 쌍 전체를 모은다.

    [SCHEMA-001] 테이블만 검사하면 이번 사고의 절반만 잡는다. 실제로 처음
    터진 것도 컬럼이었다(enriched.etf_kr 에 charge_rt_final 이 없었다).
    테이블은 있는데 컬럼이 사라진 경우가 더 조용하고 더 흔하다.

    검사 대상은 세 갈래다.
      1. RDB_SCHEMA[domain]["properties"] - get_full_column_list 가 그대로
         LLM 에게 "실제 컬럼 목록"이라고 넘기는 것들.
      2. AttributeSpec.column 중 별칭이 없는 것 - 기본 테이블 컬럼.
      3. 파생 조인이 내부에서 읽는 컬럼 - 위 선언에서 가져온다.
    별칭이 붙은 컬럼(join_alias 소속)은 파생 조인이면 3번이 덮고, 일반
    조인 테이블이면 그 테이블 기준으로 검사한다.
    """
    refs: set[tuple[str, str]] = set()

    for domain, entry in DOMAIN_TABLE_INFO.items():
        table = entry["table"]
        for column in RDB_SCHEMA.get(domain, {}).get("properties", {}):
            refs.add((table, column))

    for domain, domain_attrs in ATTRIBUTE_CATALOG.items():
        base_table = DOMAIN_TABLE_INFO.get(domain, {}).get("table")
        for concept, spec in domain_attrs.items():
            column = spec.column
            if spec.join_table and spec.join_table.lstrip().startswith("("):
                declared = DERIVED_JOIN_PHYSICAL_REFS.get(concept, {}).get("columns", [])
                refs.update((t, c) for t, c in declared)
                continue
            if "." in column:
                alias, _, bare = column.partition(".")
                if spec.join_table and alias == spec.join_alias:
                    refs.add((spec.join_table, bare))
                continue
            if base_table:
                refs.add((base_table, column))

    return refs


_PHYSICAL_TABLE_PATTERN = re.compile(
    r"\b(?:raw|enriched|relations|vec|core|meta)\.[a-z_0-9]+"
)


def assert_caveat_hygiene() -> None:
    """SQL caveat 이 물리 테이블 이름을 언급하지 않는지 확인한다.

    utils 는 도메인 caveat 을 그 도메인의 **모든** 질의 프롬프트에 주입한다.
    그래서 caveat 에 테이블 이름이 들어 있으면, 그 테이블이 이번 질의의
    JOIN 에 없더라도 LLM 이 이름을 배워 조인을 지어낸다.

    가설이 아니라 실측이다. 2026-09-03 팀원 trace 에서 예전 caveat
    ("enriched.etf_kr_enriched 의 charge_rt_final 을 쓴다")이 총보수와 무관한
    질문까지 오염시켜 UndefinedTable 을 만들었다 - Q5·Q16·Q23·Q24·Q26·Q27·Q30
    7문항 24회차가 3회 재시도를 모두 태우고 실패했다. 그중 Q30 은 조인만
    빼면 61행이 정상 반환되는, 원래 답할 수 있던 질문이었다.

    필요한 조인은 [해석된 스키마]가 이미 넣어 주므로 caveat 이 테이블 이름을
    말할 이유가 없다.
    """
    offenders: list[str] = []
    for domain, caveats in DOMAIN_SQL_CAVEATS.items():
        for index, text in enumerate(caveats):
            found = sorted(set(_PHYSICAL_TABLE_PATTERN.findall(text)))
            if found:
                offenders.append(f"{domain}[{index}]: {', '.join(found)}")
    if offenders:
        raise ValueError(
            "SQL caveat 에 물리 테이블 이름이 들어 있다. 이 문구는 도메인의 모든 "
            "질의에 주입되므로 LLM 이 없는 조인을 지어내게 만든다(2026-09-03 "
            "trace 실측). 개념 이름으로 바꾸고 JOIN 은 해석된 스키마에 맡길 것:\n  - "
            + "\n  - ".join(offenders)
        )


def assert_schema_contract(snapshot: dict | None = None) -> None:
    """카탈로그가 참조하는 테이블·컬럼이 live 에 전부 있는지 확인한다.

    없으면 schema_snapshot.SchemaContractError 를 던진다. 삼키지 말 것 -
    이 예외는 "곧 실패할 것"이 아니라 "이미 틀린 전제로 돌고 있었다"는 뜻이다.

    ENRICHED_TABLE_INFO 는 사람이 읽는 참조용이라(코드가 직접 읽지 않는다)
    여기서 검사하지 않는다. 실제로 SQL 에 들어가는 것만 검사한다.
    """
    from tools import schema_snapshot

    # 프롬프트에 주입되는 문구가 없는 테이블을 가르치지 않는지 먼저 본다.
    # 네트워크가 필요 없는 검사라 앞에 둔다.
    assert_caveat_hygiene()

    schema_snapshot.assert_contract(
        table_refs=sorted(iter_catalog_table_refs()),
        column_refs=sorted(iter_catalog_column_refs()),
        snapshot=snapshot,
    )


# 기동 시점 검사는 기본적으로 켜지 않는다. 라이브러리 import 가 네트워크를
# 요구하면 오프라인 테스트·정적 분석이 전부 깨지기 때문이다. 에이전트
# 진입점(nodes 쪽, T-116)에서 RDB_SCHEMA_CONTRACT_CHECK=1 을 주거나
# assert_schema_contract() 를 직접 부른다.
if os.environ.get("RDB_SCHEMA_CONTRACT_CHECK") == "1":  # pragma: no cover
    assert_schema_contract()