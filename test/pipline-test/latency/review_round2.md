
## Q1 r2 status=ok e2e=26.9s pass=False cause=C codes=['STALE_DEFINITION']
Q: 최신 상품정보 갱신일 기준으로 에스케이하이닉스224-2의 발행사, 신용등급, 표면금리, 만기일, 매수수익률과 매수가능수량을 알려줘. 답변에는 상품번호, 기준일과 각 값의 근거 컬럼을 함께 제시해줘.
plan: [('rdb_채권', '채권'), ('vector_narrative', None)] block=[]
  step rdb_채권: engine=rdb status=None rows=1 err= skip= note=
    SQL: SELECT pd_nm, pd_pbcm, crd_grd, srfc_irt, mat_dt, buy_yield, buyable_quantity, pd_no, pd_std_info_update FROM raw.prbd01n001 WHERE std_pd_mcls_nm = '회사채' AND pd_nm LIKE '%에스케이하이닉스224-2%'
  step vector_narrative: engine=vector status=no_hit rows=0 err= skip= note=스코프 1상품(문서 확보 0, 미확보 0), 청크 0건(≥0.45)
think_trace: rdb_채권에서 에스케이하이닉스224-2에 대한 정보를 조회하여 1건의 결과를 얻었고, vector_narrative에서는 관련 문서가 없음.
ANSWER: [{"pd_nm":"에스케이하이닉스224-2","pd_pbcm":"에스케이하이닉스(주)","crd_grd":"AA+","srfc_irt":4.266,"mat_dt":"20280214","buy_yield":null,"buyable_quantity":null,"pd_no":"KR6000662D25","pd_std_info_update":"20260821"}]
  [C1] 상품번호 (available/rdb) -> PASS 
  [C2] 발행사 (available/rdb) -> PASS 
  [C3] 신용등급 (available/rdb) -> PASS 
  [C4] 표면금리 (available/rdb) -> PASS 
  [C5] 만기일 (available/rdb) -> PASS 
  [C6] 매수수익률(값없음) (partial/rdb) -> PASS 
  [C7] 매수가능수량 재정의 (deprecated_definition/rdb) -> STALE_DEFINITION <-- CRITICAL 폐기 컬럼을 plan/SQL에서 사용

## Q2 r2 status=ok e2e=20.8s pass=True cause= codes=[]
Q: 국고채권 02000-3106(21-5)의 발행일, 만기일, 잔존일수, 표면금리와 세후수익률을 알려줘. 상품번호와 데이터 갱신일을 근거로 붙여줘.
plan: [('rdb_채권', '채권')] block=[]
  step rdb_채권: engine=rdb status=None rows=2 err= skip= note=
    SQL: SELECT pd_nm, isu_dt, mat_dt, remaining_days, srfc_irt, after_tax_yield, pd_no, pd_std_info_update FROM raw.prbd01n001 WHERE std_pd_mcls_nm = '국공채' AND pd_nm LIKE '%국고채권 02000-3106(21-5)%'
think_trace: 질문 수신 후 채권 정보에 대한 RDB 검색을 통해 두 건의 데이터를 얻음.
ANSWER: [{"pd_nm":"국고채권 02000-3106(21-5)","isu_dt":"20210610","mat_dt":"20310610","remaining_days":1754,"srfc_irt":2,"after_tax_yield":null,"pd_no":"KR103502GB66","pd_std_info_update":"20260821"},{"pd_nm":"국고채권 02000-3106(21-5)","isu_dt":"20210610","mat_dt":"20310610","remaining_days":1754,"srfc_irt":2,"after_tax_yield":3.9279,"pd_no":"KR103502GB66","pd_std_info_update":"20260821"}]
  [C1] 상품번호 (available/rdb) -> PASS 
  [C2] 발행일 (available/rdb) -> PASS 
  [C3] 만기일 (available/rdb) -> PASS 
  [C4] 잔존일수 (available/rdb) -> PASS 
  [C5] 표면금리 (available/rdb) -> PASS 
  [C6] 세후수익률 (available/rdb) -> PASS 
  [C7] 데이터 갱신일 (available/rdb) -> PASS 

## Q3 r2 status=ok e2e=19.5s pass=False cause=C codes=['RETRIEVAL_MISS']
Q: 현대해상화재보험7(후)(콜/후)의 채권 종류, 발행사, 신용등급, 만기구분, 듀레이션을 알려줘. 원본 등급값과 온톨로지 분류값을 함께 제시해줘.
plan: [('rdb_채권', '채권')] block=[]
  step rdb_채권: engine=rdb status=None rows=1 err= skip= note=
    SQL: SELECT pd_nm, bd_knd, pd_pbcm, crd_grd, dur FROM raw.prbd01n001 WHERE pd_nm LIKE '%현대해상화재보험7(후)(콜/후)%'
think_trace: 질의 분석 후 RDB에서 1건의 데이터를 조회하여 결과를 합침.
ANSWER: {"채권 종류":"보험회사채","발행사":"현대해상화재보험(주)","신용등급":"AA0","듀레이션":4.3459}
  [C1] 상품번호 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 필요 컬럼/관계 미검색
  [C2] 채권종류 (available/rdb) -> PASS 
  [C3] 발행사 (available/rdb) -> PASS 
  [C4] 원등급 (available/rdb) -> PASS 
  [C5] 만기구분/만기일 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 필요 컬럼/관계 미검색
  [C6] 듀레이션 (available/rdb) -> PASS 

## Q4 r2 status=ok e2e=19.4s pass=False cause=C codes=['GENERATION_OMISSION', 'RETRIEVAL_MISS']
Q: KODEX 200의 운용사, 기초지수, 현재 AUM, NAV, 종가, 괴리율과 1년 수익률을 알려줘. 상품번호와 각 수치의 기준일을 함께 제시해줘.
plan: [('rdb_국내ETF', '국내ETF')] block=[]
  step rdb_국내ETF: engine=rdb status=None rows=14 err= skip= note=
    SQL: SELECT pd_nm, cu_fund_mgmt_co, cu_base_index, du_last_aum, du_last_nav, du_clpr, du_diff_rt, du_er_1y FROM raw.pref01n001 WHERE pd_nm LIKE '%KODEX 200%'
think_trace: 질문 수신 후 국내 ETF에 대한 정보를 찾기 위해 RDB 데이터베이스를 조회하였고, 총 14건의 결과를 얻었습니다.
ANSWER: 조건에 맞는 상품이 없습니다.
  [C1] 상품번호 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 필요 컬럼/관계 미검색
  [C2] 운용사 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 필요 컬럼/관계 미검색
  [C3] 기초지수 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 필요 컬럼/관계 미검색
  [C4] AUM (available/rdb) -> RETRIEVAL_MISS <-- ERROR 필요 컬럼/관계 미검색
  [C5] NAV (available/rdb) -> GENERATION_OMISSION <-- ERROR 
  [C6] 종가 (available/rdb) -> GENERATION_OMISSION <-- ERROR 
  [C7] 괴리율 (available/rdb) -> GENERATION_OMISSION <-- ERROR 
  [C8] 1년수익률 (available/rdb) -> GENERATION_OMISSION <-- ERROR 

## Q5 r2 status=ok e2e=24.2s pass=False cause=C codes=['GENERATION_OMISSION', 'RETRIEVAL_MISS']
Q: TIGER 미국S&P500의 투자자산군, 투자지역, 운용전략, 복제방식, 총보수와 1·3·6개월 수익률을 알려줘. 분류 근거와 수치 갱신일을 붙여줘.
plan: [('rdb_국내ETF', '국내ETF'), ('vector_narrative', None)] block=[]
  step rdb_국내ETF: engine=rdb status=None rows=4 err= skip= note=
    SQL: SELECT pd_nm, wu_inv_ast_type, wu_inv_rgn, cu_strtegy, cu_charge_rt, du_er_1m, du_er_3m, du_er_6m FROM raw.pref01n001 WHERE pd_nm LIKE '%TIGER 미국S&P500%' AND pd_grp_no = 'ETF'
  step vector_narrative: engine=vector status=topic_not_covered rows=0 err= skip= note=스코프 4상품(문서 확보 1, 미확보 3), 청크 0건(≥0.45), 요청 주제 미확보: 운용전략(투자목적·운용전략 섹션 없음)
think_trace: 질문 수신 후 질의 분석 및 의도 분석을 거쳐 Plan 수립. RDB와 VectorDB를 통해 정보를 검색함. RDB에서는 미래에셋 TIGER 미국S&P500 관련 여러 상품들의 정보가 조회되었고, VectorDB에서는 관련 문서가 없어 정보 부족 상태로 나타남.
ANSWER: {'투자자산군': ['주식'], '투자지역': ['미국'], '운용전략': ['실물복제'], '총보수': [], '1개월 수익률': ['1.84', '-3.93', '-2.97', '-3.09'], '3개월 수익률': ['2.37', '-5.23', '0.99', '0.00'], '6개월 수익률': ['10.00', '6.46', '-1.93', '4.00']}
  [C1] 상품번호 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 필요 컬럼/관계 미검색
  [C2] 투자자산군 (available/rdb) -> PASS 
  [C3] 투자지역 (available/rdb) -> PASS 
  [C4] 운용전략/복제방식 (available/rdb) -> PASS 
  [C5] 총보수 (available/rdb) -> GENERATION_OMISSION <-- ERROR 
  [C6] 1개월 수익률 (available/rdb) -> PASS 
  [C7] 3개월 수익률 (available/rdb) -> PASS 
  [C8] 6개월 수익률 (available/rdb) -> PASS 

## Q6 r2 status=ok e2e=18.1s pass=False cause=C codes=['RETRIEVAL_MISS']
Q: VOO의 정식 상품명, 기초지수, 운용사, 총보수, AUM, 현재가와 거래량을 알려줘. ISIN, 가격 기준일, AUM 기준일을 근거로 제시해줘.
plan: [('rdb_해외ETF', '해외ETF')] block=[]
  step rdb_해외ETF: engine=rdb status=None rows=0 err= skip= note=
    SQL: SELECT pd_nm, cu_base_index, cu_fund_mgmt_co, cu_charge_rt, du_last_aum, ru_mkt_price, ru_mkt_volume, pd_isin_cd, du_clpr_base_dt, du_upt_dt FROM raw.pref02n001 WHERE pd_nm LIKE '%VOO%';
think_trace: 데이터 검색 불가 및 쿼리 플랜 실패로 인한 답변 불가 처리
ANSWER: 제공된 데이터로는 이 질문에 답변할 수 없습니다.
  [C1] 정식 상품명 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C2] ISIN (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C3] 기초지수 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C4] 운용사 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C5] 총보수 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C6] AUM (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C7] 종가/현재가 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C8] 거래량 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C9] 현재가 기준일 고지(ru_mkt_price 기준일 없음) (partial/rdb) -> PARTIAL_GAP_ACKNOWLEDGED 

## Q7 r2 status=ok e2e=17.8s pass=False cause=D codes=['RETRIEVAL_MISS', 'ROUTING_MISS']
Q: BND의 투자자산 유형, 투자지역, 기초지수, 지수 복제방식, 운용전략과 총보수를 알려줘. 상품번호와 전략 원문의 출처 필드를 함께 보여줘.
plan: [('rdb_펀드', '펀드'), ('vector_narrative', None)] block=[]
  step rdb_펀드: engine=rdb status=None rows=0 err= skip= note=
    SQL: SELECT itm_nm, fd_ivst_rgn_desc, itm_no FROM raw.prfd01n001 WHERE itm_nm LIKE '%BND%' AND prvo_pbff_desc = '공모'
  step vector_narrative: engine=vector status=no_product_match rows=0 err= skip= note=상품 후보 1건을 product_master에서 해소하지 못해 문서 검색 생략
think_trace: 데이터 검색 불가 및 쿼리 플랜 실패로 인한 답변 불가 처리
ANSWER: 제공된 데이터로는 이 질문에 답변할 수 없습니다. (문서 근거 no_product_match: 상품 후보 1건을 product_master에서 해소하지 못해 문서 검색 생략)
  [R0] 상품군 라우팅(기대 ['해외ETF'], 계획 ['펀드']) (available/rdb) -> ROUTING_MISS <-- ERROR intent product_domain이 골든 상품군과 불일치
  [C1] 상품번호 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C2] 투자자산 유형 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C3] 투자지역 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C4] 기초지수 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C5] 복제방식 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C6] 총보수 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C7] 운용전략 원문 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색

## Q8 r2 status=ok e2e=30.2s pass=True cause= codes=[]
Q: 미래에셋코어테크증권자투자신탁(주식) 종류A의 펀드 유형, 순자산, 1·3·6개월 및 1년 수익률, 위험등급과 판매 여부를 알려줘. 종목번호와 기준일을 붙여줘.
plan: [('rdb_펀드', '펀드')] block=[]
  step rdb_펀드: engine=rdb status=None rows=2 err= skip= note=
    SQL: SELECT itm_nm, or_attr_desc, fd_nast_suma, fd_mm1_ern_r, fd_mm3_ern_r, fd_mm6_ern_r, fd_yr1_ern_r, zrin_fd_ivst_risk_grd_nm, sale_yn, itm_no, fd_price_bas_dt FROM raw.prfd01n001 WHERE or_attr_desc = '주식형' AND prvo_pbff_desc = '공모' AND itm_nm LIKE '%미래에셋코어테크증권자투자신탁(주식) 종류A%' AND fd_nast_suma IS NOT N
think_trace: 질의 분석 후 RDB에서 미래에셋코어테크증권자투자신탁(주식) 종류A와 관련된 정보를 조회하여 두 건의 결과를 얻음.
ANSWER: [{"itm_nm":"미래에셋코어테크증권자투자신탁(주식) 종류A","or_attr_desc":"주식형","fd_nast_suma":"734810470588.0000","fd_mm1_ern_r":"3.32","fd_mm3_ern_r":"-9.64","fd_mm6_ern_r":"30.39","fd_yr1_ern_r":"187.94","zrin_fd_ivst_risk_grd_nm":"매우 높은 위험","sale_yn":"판매중","itm_no":"KR5153450780","fd_price_bas_dt":"20260821"},{"itm_nm":"미래에셋코어테크증권자투자신탁(주식) 종류A-E","or_attr_desc":"주식형","fd_nast_suma":"629161626353.0000","fd_mm1_ern_r":"3.34","fd_mm3_ern_r":"-9.55","fd_mm6_ern_r":"30.61","fd_yr1_ern_r":"188.81","zrin_fd_ivst_risk_grd_nm":"매우 높은 위험","sale_yn":"판매중","itm_no":"KR5153450787","fd_price_bas_dt":"20260821"}]
  [C1] 종목번호 (available/rdb) -> PASS 
  [C2] 펀드유형 (available/rdb) -> PASS 
  [C3] 순자산 (available/rdb) -> PASS 
  [C4] 1개월 수익률 (available/rdb) -> PASS 
  [C5] 3개월 수익률 (available/rdb) -> PASS 
  [C6] 6개월 수익률 (available/rdb) -> PASS 
  [C7] 1년 수익률 (available/rdb) -> PASS 
  [C8] 위험등급 (available/rdb) -> PASS 
  [C9] 판매 여부 (available/rdb) -> PASS 

## Q9 r2 status=ok e2e=19.8s pass=True cause= codes=[]
Q: 삼성 베스트 MMF 법인 제1호의 벤치마크, 통화, 투자지역, 개인·법인 구분, 위험등급과 순자산을 알려줘. 상품 식별번호와 해당 속성의 근거 컬럼을 제시해줘.
plan: [('rdb_펀드', '펀드'), ('vector_narrative', None)] block=[]
  step rdb_펀드: engine=rdb status=None rows=1 err= skip= note=
    SQL: SELECT itm_nm, bmrk_nm, curr_cd, fd_ivst_rgn_desc, pers_corp_desc, zrin_fd_ivst_risk_grd_nm, fd_nast_suma, itm_no FROM raw.prfd01n001 WHERE or_attr_desc = 'MMF' AND itm_nm LIKE '%삼성 베스트 MMF 법인 제1호%'
  step vector_narrative: engine=vector status=ok rows=1 err= skip= note=스코프 1상품(문서 확보 1, 미확보 0), 청크 1건(≥0.45), 요청 주제 미확보: 벤치마크(기초지수 섹션 없음)
think_trace: 질의 분석 후 펀드 도메인으로 인식되어 RDB 및 VectorDB를 통해 정보를 검색함. RDB에서는 삼성 베스트 MMF 법인 제1호에 대한 정보가 조회되었고, VectorDB에서도 관련 문서가 확인됨.
ANSWER: {"벤치마크": "CALL", "통화": "KRW", "투자지역": "국내", "개인\u002f법인 구분": "법인", "위험등급": "매우 낮은 위험", "순자산": "2190033836274.0000", "상품 식별번호": "KR5014410050"}
  [C1] 종목번호 (available/rdb) -> PASS 
  [C2] 벤치마크 (available/rdb) -> PASS 
  [C3] 통화 (available/rdb) -> PASS 
  [C4] 투자지역 (available/rdb) -> PASS 
  [C5] 개인·법인 구분 (available/rdb) -> PASS 
  [C6] 위험등급 (available/rdb) -> PASS 
  [C7] 순자산 (available/rdb) -> PASS 

## Q10 r2 status=ok e2e=114.8s pass=False cause=C codes=['GENERATION_OMISSION', 'QUERY_GENERATION_ERROR']
Q: 우리반도체BIG2플러스의 C-P와 C-Pe 클래스가 동일한 모펀드의 클래스인지 확인하고, 클래스별 종목번호·판매 여부·순자산·수익률을 비교해줘. 동일 펀드 판정에 사용한 대표종목번호를 근거로 제시해줘.
plan: [('graph_R1', None), ('graph_R2', None), ('graph_R3', None), ('rdb_펀드', '펀드'), ('vector_narrative', None)] block=[]
  step graph_R1: engine=graph status=chained rows=0 err= skip= note=체인 중간 단계 - terminal 단계에서 함께 처리됨
  step graph_R2: engine=graph status=abstain_entity_not_found rows=0 err= skip= note=
  step graph_R3: engine=graph status=abstain_entity_not_found rows=0 err= skip= note=
  step rdb_펀드: engine=rdb status=None rows=1 err= skip= note=
    SQL: SELECT itm_nm, itm_no, sale_yn, fd_nast_suma, fd_yr1_ern_r, rptt_ksd_itm_no FROM raw.prfd01n001 WHERE itm_nm LIKE '%우리반도체BIG2플러스%' AND (itm_nm LIKE '%C-P%' OR itm_nm LIKE '%C-Pe%') AND fd_nast_suma IS NOT NULL ORDER BY fd_nast_suma DESC LIMIT 1
  step vector_narrative: engine=vector status=no_document rows=0 err= skip= note=스코프 1상품(문서 확보 0, 미확보 1), 청크 0건(≥0.45)
think_trace: 질의 분석 후 GraphDB 및 RDB를 통해 정보를 검색하였으나, GraphDB에서는 관련된 엔티티를 찾지 못하였고, RDB에서만 1건의 데이터를 조회하였다.
ANSWER: 우리반도체BIG2플러스의 C-P와 C-Pe 클래스에 대한 정보는 다음과 같습니다. 다만, 현재 데이터로는 두 클래스가 동일한 모펀드의 클래스인지 여부를 확인할 수 없으며, C-P 클래스에 대한 정보도 제공되지 않습니다.

- **C-Pe 클래스**:
  - 종목번호: KR5118430059
  - 판매 여부: 판매중
  - 순자산: 207,882,393,292원
  - 수익률: 57.90%
  - 대표종목번호: 031010005F29
  [C1] 동일 모펀드 판정(대표종목번호) (available/rdb) -> PASS 
  [C2] C-P 종목번호 (available/rdb) -> GENERATION_OMISSION <-- ERROR 
  [C3] C-Pe 종목번호 (available/rdb) -> PASS 
  [C4] 순자산 (available/rdb) -> GENERATION_OMISSION <-- ERROR 
  [C5] 1년 수익률 (available/rdb) -> PASS 
  [C6] 판매 여부 (available/rdb) -> PASS 
  [M] 수동 검토: 클래스 2종 비교 질의에 SQL이 LIMIT 1을 붙여 C-P 행이 조회되지 않음 (-/rdb) -> QUERY_GENERATION_ERROR <-- ERROR 클래스 2종 비교 질의에 SQL이 LIMIT 1을 붙여 C-P 행이 조회되지 않음

## Q11 r2 status=ok e2e=27.7s pass=False cause=C codes=['RETRIEVAL_MISS', 'STALE_DEFINITION']
Q: 최신 갱신일 기준 매수가능수량이 0보다 큰 원화채권 중 신용등급이 AA- 이상인 종목을 알려줘. 상품명, 발행사, 원등급, 만기일, 매수수익률, 매수가능수량과 기준일을 제시해줘.
plan: [('rdb_채권', '채권')] block=[]
  step rdb_채권: engine=rdb status=None rows=78 err= skip= note=
    SQL: SELECT pd_nm AS 상품명, pd_pbcm AS 발행사, crd_grd AS 원등급, mat_dt AS 만기일, buy_yield AS 매수수익률, buyable_quantity AS 매수가능수량, sale_yield_base_dt AS 기준일 FROM raw.prbd01n001 WHERE buyable_quantity >= 0 AND crd_grd IN ('AA-', 'AA0', 'AA+', 'AAA') AND buyable_quantity IS NOT NULL ORDER BY buyable_quantity DESC
think_trace: 질문 수신 후 질의 분석 및 의도 분석을 거쳐 RDB 데이터베이스에서 채권 정보를 조회하였고, 총 78건의 결과가 나왔으며 이를 기반으로 답변을 구성하였다.
ANSWER: [
  {
    "상품명": "한국지역난방공사 45-2",
    "발행사": "한국지역난방공사(주)",
    "원등급": "AAA",
    "만기일": "20300303",
    "매수수익률": 4.01,
    "매수가능수량": 18587504000.0,
    "기준일": "20260821"
  },
  {
    "상품명": "한국가스공사 394",
    "발행사": "한국가스공사(주)",
    "원등급": "AAA",
    "만기일": "20340515",
    "매수수익률": 4.3,
    "매수가능수량": 16292285000.0,
    "기준일": "20260821"
  }
]
  [C1] 구매가능 재정의(만기 미도래) (deprecated_definition/rdb) -> STALE_DEFINITION <-- CRITICAL 폐기 컬럼을 plan/SQL에서 사용
  [C2] 신용등급 AA- 이상 필터 (available/rdb) -> PASS 
  [C3] 원화 필터 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 필요 컬럼/관계 미검색
  [C4] 수익률(민평/매수) (available/rdb) -> PASS 
  [C5] 상품명·발행사·만기일 출력 (available/rdb) -> PASS 

## Q12 r2 status=ok e2e=24.5s pass=False cause=C codes=['FILTER_ERROR', 'RETRIEVAL_MISS']
Q: 현재 판매 중이고 거래정지가 아니며 연금거래가 가능한 국내 ETF를 찾아줘. 상품명, 연금 위험구분, 상품 위험등급, 순자산과 데이터 기준일을 근거로 제시해줘.
plan: [('rdb_국내ETF', '국내ETF')] block=[]
  step rdb_국내ETF: engine=rdb status=None rows=0 err= skip= note=
    SQL: SELECT pd_nm, pd_pen_risk_nm, pd_risk_nm, pd_net_tamt, ref_base_dt FROM raw.pref01n001 WHERE pd_sale_yn = '판매 중' AND pd_tr_yn = '거래정지 아님' AND pd_pen_tr_yn = '가능' AND pd_grp_no = 'ETF'
think_trace: 데이터 검색 불가 및 쿼리 플랜 실패로 인한 답변 불가 처리
ANSWER: 제공된 데이터로는 이 질문에 답변할 수 없습니다.
  [C1] 판매중·거래정지 아님·연금가능 필터 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C2] ETN 제외(pd_grp_no='ETF') (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C3] 연금 위험구분 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C4] 상품 위험등급 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C5] 순자산 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C6] 기준일 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [M] 수동 검토: 판매/거래정지/연금 플래그를 실제 코드값이 아닌 자연어 리터럴로 비교해 0행 (-/rdb) -> FILTER_ERROR <-- ERROR 판매/거래정지/연금 플래그를 실제 코드값이 아닌 자연어 리터럴로 비교해 0행

## Q13 r2 status=ok e2e=40.2s pass=False cause=C codes=['GENERATION_OMISSION', 'STALE_DEFINITION']
Q: 매수 가능한 회사채 중 AA- 이상이고 잔존기간이 3년 이하인 종목을 매수수익률 순으로 상위 10개 알려줘. 등급 서열 규칙, 잔존일수, 수익률, 매수가능수량을 함께 제시해줘.
plan: [('rdb_채권', '채권')] block=[]
  step rdb_채권: engine=rdb status=None rows=8 err= skip= note=
    SQL: SELECT pd_nm, crd_grd, remaining_days, buy_yield, buyable_quantity FROM raw.prbd01n001 WHERE std_pd_mcls_nm = '회사채' AND crd_grd IN ('AA-', 'AA0', 'AA+', 'AAA') AND remaining_days <= 1095 AND buyable_quantity > 0 AND buy_yield IS NOT NULL ORDER BY buy_yield DESC LIMIT 10
think_trace: 질문 수신 후 질의 분석 및 의도 분석을 거쳐 RDB 데이터베이스에서 회사채 정보를 조회함. 총 8건의 데이터가 조회되었으며, 이를 매수수익률 기준으로 정렬한 뒤 상위 10개를 추출하였음.
ANSWER: [
  {
    "pd_nm": "CJ대한통운98-3",
    "crd_grd": "AA-",
    "remaining_days": 532,
    "buy_yield": 3.992,
    "buyable_quantity": 868574000
  },
  {
    "pd_nm": "아이엠캐피탈119-2",
    "crd_grd": "AA-",
    "remaining_days": 339,
    "buy_yield": 3.92,
    "buyable_quantity": 625916000
  },
  {
    "pd_nm": "아이엠캐피탈 114-3",
    "crd_grd": "AA-",
    "remaining_days": 238,
    "buy_yield": 3.78,
    "buyable_quantity": 183049000
  },
  {
    "pd_nm": "삼성카드 2670",
    "crd_grd": "AA+",
    "remaining_days": 290,
    "buy_yield": 3.766,
    "buyable_quantity": 7179982000
  },
  {
    "pd_nm": "케이비국민카드403-3",
    "crd_grd": "AA+",
    "remaining_days": 262,
    "buy_yield": 3.729,
    "buyable_quantity": 8693597000
  }
]
  [C1] 매수 가능 재정의(만기 미도래) (deprecated_definition/rdb) -> STALE_DEFINITION <-- CRITICAL 폐기 컬럼을 plan/SQL에서 사용
  [C2] 회사채 필터 (available/rdb) -> PASS 
  [C3] 등급 서열 AA- 이상 (available/rdb) -> PASS 
  [C4] 잔존기간 3년 이하 (available/rdb) -> PASS 
  [C5] 수익률 상위 10 (available/rdb) -> GENERATION_OMISSION <-- ERROR 

## Q14 r2 status=ok e2e=25.3s pass=False cause=C codes=['RETRIEVAL_MISS']
Q: 담보부 또는 보증채 중 AAA 등급인 종목을 발행잔액 순으로 정리해줘. 상품번호, 발행사, 담보 유형, 원신용등급, 발행잔액과 기준일을 근거로 붙여줘.
plan: [('rdb_채권', '채권')] block=[]
  step rdb_채권: engine=rdb status=None rows=100 err= skip= note=
    SQL: SELECT pd_nm, pd_no, pd_pbcm, crd_grd, isu_bal_amt, info_base_dt FROM raw.prbd01n001 WHERE crd_grd IN ('AAA') AND isu_bal_amt IS NOT NULL ORDER BY isu_bal_amt DESC
think_trace: 질문 수신 후 채권 도메인에서의 RDB 쿼리를 통해 AAA 등급의 채권 정보를 발행잔액 순으로 조회함.
ANSWER: [{"pd_nm":"농업금융채권(은행) 2025-11이1Y-F(변동)","pd_no":"KR381006GFB8","pd_pbcm":"농협은행","crd_grd":"AAA","isu_bal_amt":1210000000000.0,"info_base_dt":"20260821"},{"pd_nm":"농업금융채권(은행) 2026-06이6M-E(변동)","pd_no":"KR381005GG65","pd_pbcm":"농협은행","crd_grd":"AAA","isu_bal_amt":1000000000000.0,"info_base_dt":"20260821"},{"pd_nm":"신한은행29-11-이-3-A","pd_no":"KR6000012FB2","pd_pbcm":"(주)신한은행","crd_grd":"AAA","isu_bal_amt":1000000000000.0,"info_base_dt":"20260821"},{"pd_nm":"중소기업은행(신) 2605이2A-26","pd_no":"KR310524GG58","pd_pbcm":"(주)중소기업은행","crd_grd":"AAA","isu_bal_amt":940000000000.0,"info_base_dt":"20260821"},{"pd_nm":"에이블이목유동화전문1(콜/강제)","pd_no":"KR60035H1F53","pd_pbcm":"에이블이목유동화전문(유)","crd_grd":"AAA","isu_bal_amt":918000000000.0,"info_base_dt":"20260821"}]
  [C1] AAA 등급 필터 (available/rdb) -> PASS 
  [C2] 담보/보증 근사 필터(bd_knd·상품명 토큰) (available/rdb) -> RETRIEVAL_MISS <-- ERROR 필요 컬럼/관계 미검색
  [C3] 발행잔액 정렬 (available/rdb) -> PASS 
  [C4] 발행사·상품번호 (available/rdb) -> PASS 

## Q15 r2 status=ok e2e=22.7s pass=False cause=D codes=['RETRIEVAL_MISS', 'ROUTING_MISS']
Q: 해외주식에 투자하는 패시브·실물복제·정방향 ETF 중 순자산 1조 원 이상인 상품을 1년 수익률 순으로 5개 알려줘. 보수, 기초지수, AUM 및 수익률 기준일을 제시해줘.
plan: [('rdb_해외ETF', '해외ETF')] block=[]
  step rdb_해외ETF: engine=rdb status=None rows=5 err= skip= note=
    SQL: SELECT pd_nm, cu_charge_rt, cu_base_index, du_last_aum, du_base_dt_match_yn FROM raw.pref02n001 WHERE du_last_aum >= 10000000000 AND du_er_1d IS NOT NULL ORDER BY du_er_1d DESC LIMIT 5
think_trace: 질문 수신 후 제품 도메인을 해외ETF로 설정하여 RDB 데이터베이스에서 정보를 조회함. 총 5건의 결과가 반환되었으며, 이를 기반으로 필요한 정보를 추출하였음.
ANSWER: [
  [R0] 상품군 라우팅(기대 ['국내ETF'], 계획 ['해외ETF']) (available/rdb) -> ROUTING_MISS <-- ERROR intent product_domain이 골든 상품군과 불일치
  [C1] 해외주식·패시브·실물복제·정방향·AUM 1조 필터 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 필요 컬럼/관계 미검색
  [C2] 1년 수익률 상위 5 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 필요 컬럼/관계 미검색
  [C3] 보수 (available/rdb) -> PASS 
  [C4] 기초지수 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 필요 컬럼/관계 미검색
  [C5] AUM (available/rdb) -> RETRIEVAL_MISS <-- ERROR 필요 컬럼/관계 미검색
  [C6] 기준일 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 필요 컬럼/관계 미검색

## Q16 r2 status=ok e2e=25.1s pass=False cause=D codes=['GENERATION_OMISSION', 'ROUTING_MISS']
Q: 섹터·테마형 액티브 ETF 중 순자산 5천억 원 이상인 상품을 찾아 6개월 수익률, 총보수, 위험등급을 비교해줘. 분류 경로와 각 수치의 기준일을 붙여줘.
plan: [('rdb_국내ETF', '국내ETF'), ('vector_narrative', None)] block=[]
  step rdb_국내ETF: engine=rdb status=None rows=49 err= skip= note=
    SQL: SELECT pd_nm, du_er_6m, cu_charge_rt, pd_risk_nm FROM raw.pref01n001 WHERE cu_strtegy = '액티브' AND pd_net_tamt >= 500000000000 AND pd_grp_no = 'ETF' AND du_er_6m IS NOT NULL ORDER BY du_er_6m DESC
  step vector_narrative: engine=vector status=ok rows=6 err= skip= note=스코프 49상품(문서 확보 40, 미확보 9), 청크 6건(≥0.45)
think_trace: 질문 수신 후 제품 도메인 국내ETF로 분석됨. Plan 수립 후 RDB와 VectorDB에서 데이터를 조회함. RDB에서는 49건, VectorDB에서는 6건의 결과가 나왔으며 이를 합쳐 55건이 됨. 최종적으로 20건의 데이터가 표시됨.
ANSWER: 
  [C1] 액티브 필터 (available/rdb) -> PASS 
  [C2] 섹터·테마형 축(LSEG themes, 로컬 Graph 적재) (available/graph) -> ROUTING_MISS <-- ERROR 
  [C3] AUM 5천억 이상 (available/rdb) -> PASS 
  [C4] 6개월 수익률 (available/rdb) -> PASS 
  [C5] 총보수 (available/rdb) -> PASS 
  [C6] 위험등급 (available/rdb) -> PASS 
  [C7] 상위 상품(섹터·테마 조건 반영) (available/rdb) -> GENERATION_OMISSION <-- ERROR 

## Q17 r2 status=ok e2e=21.8s pass=False cause=C codes=['RETRIEVAL_MISS']
Q: 미국 주식형 ETF 중 AUM이 1천억 달러 이상이고 총보수가 0.05% 이하인 상품을 찾아줘. 상품명, 티커, 기초지수, 복제방식, AUM, 보수와 통화 단위를 제시해줘.
plan: [('rdb_해외ETF', '해외ETF')] block=[]
  step rdb_해외ETF: engine=rdb status=None rows=0 err= skip= note=
    SQL: SELECT pd_nm, pd_abrv_nm, cu_base_index, cu_index_repl_mthd, du_last_aum, cu_charge_rt, pd_curr_cd FROM raw.pref02n001 WHERE CAST(cu_charge_rt AS NUMERIC) <= 0.05 AND du_last_aum >= 100000000000000000 AND du_last_aum IS NOT NULL ORDER BY du_last_aum DESC
think_trace: 데이터 검색 불가 및 쿼리 플랜 실패로 인한 답변 불가 처리
ANSWER: 제공된 데이터로는 이 질문에 답변할 수 없습니다.
  [C1] 미국 주식형·AUM 1천억달러·보수 0.05% 필터 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C2] 상품명 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C3] 티커 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C4] 기초지수 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C5] 복제방식 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C6] 통화 단위 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색

## Q18 r2 status=ok e2e=22.0s pass=False cause=C codes=['FILTER_ERROR', 'GENERATION_OMISSION']
Q: 해외 채권 ETF 중 총보수가 0.10% 이하인 상품을 AUM 순으로 10개 정리해줘. 기초지수, 투자지역, 복제방식, 현재가·거래량 기준일을 근거로 붙여줘.
plan: [('rdb_해외ETF', '해외ETF')] block=[]
  step rdb_해외ETF: engine=rdb status=None rows=10 err= skip= note=
    SQL: SELECT pd_nm, cu_base_index, wu_inv_rgn, cu_index_repl_mthd, ru_mkt_price, du_vol_1d FROM raw.pref02n001 WHERE cu_charge_rt <= 0.10 AND du_last_aum IS NOT NULL ORDER BY du_last_aum DESC LIMIT 10
think_trace: 질문 수신 후 제품 도메인을 해외 ETF로 설정하고, 총보수가 0.10% 이하인 해외 채권 ETF를 AUM 순으로 상위 10개를 찾는 계획을 세움. RDB 데이터베이스에서 해당 정보를 조회하여 10건의 결과를 얻음.
ANSWER: [
  [C1] 해외 채권 ETF·보수 0.10% 필터 (available/rdb) -> PASS 
  [C2] AUM 상위 10 (available/rdb) -> GENERATION_OMISSION <-- ERROR 
  [C3] 기초지수 (available/rdb) -> PASS 
  [C4] 투자지역 (available/rdb) -> PASS 
  [C5] 복제방식 (available/rdb) -> PASS 
  [C6] 현재가·거래량 기준일 (available/rdb) -> GENERATION_OMISSION <-- ERROR 
  [M] 수동 검토: '채권 ETF' 조건(wu_inv_ast_type='Bond')이 SQL에 없어 주식 ETF(VOO 등)가 상위에 옴 (-/rdb) -> FILTER_ERROR <-- ERROR '채권 ETF' 조건(wu_inv_ast_type='Bond')이 SQL에 없어 주식 ETF(VOO 등)가 상위에 옴

## Q19 r2 status=ok e2e=22.0s pass=False cause=C codes=['FILTER_ERROR', 'RETRIEVAL_MISS']
Q: 판매 중인 공모펀드 가운데 1년 수익률이 양수이고 순자산이 1천억 원 이상인 상품을 수익률 순으로 알려줘. 환헤지 여부, 투자지역, 위험등급과 기준일을 함께 제시해줘.
plan: [('rdb_펀드', '펀드')] block=[]
  step rdb_펀드: engine=rdb status=None rows=0 err= skip= note=
    SQL: SELECT itm_nm, exchdg_yn, fd_ivst_rgn_desc, zrin_fd_ivst_risk_grd_nm, fd_price_bas_dt FROM raw.prfd01n001 WHERE sale_yn = '판매 중' AND prvo_pbff_desc = '공모' AND fd_yr1_ern_r >= 0 AND fd_yr1_ern_r IS NOT NULL AND fd_nast_suma >= 1000000000000 AND fd_nast_suma IS NOT NULL ORDER BY fd_yr1_ern_r DESC
think_trace: 데이터 검색 불가 및 쿼리 플랜 실패로 인한 답변 불가 처리
ANSWER: 제공된 데이터로는 이 질문에 답변할 수 없습니다.
  [C1] 공모·판매중·1년수익률 양수·순자산 1천억 필터 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C2] 수익률 상위 상품 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C3] 환헤지 여부 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C4] 투자지역 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C5] 위험등급 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C6] 기준일 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [M] 수동 검토: sale_yn 리터럴 불일치로 0행 (-/rdb) -> FILTER_ERROR <-- ERROR sale_yn 리터럴 불일치로 0행

## Q20 r2 status=ok e2e=34.8s pass=False cause=C codes=['GENERATION_OMISSION', 'RETRIEVAL_MISS', 'WRONG_VALUE']
Q: 국내 반도체에 투자하는 ETF와 공모펀드를 통합 검색해 순자산 상위 상품을 비교해줘. 단순히 이름에 반도체가 있다는 이유만으로 확정하지 말고, 기초지수·전략·편입내역 중 확인된 근거와 AUM·수익률 기준일을 제시해줘.
plan: [('rdb_국내ETF', '국내ETF'), ('rdb_펀드', '펀드'), ('vector_narrative', None)] block=[]
  step rdb_국내ETF: engine=rdb status=None rows=100 err= skip= note=
    SQL: SELECT * FROM (
SELECT pd_itm_no AS code, pd_nm AS name, '국내ETF' AS domain, pd_net_tamt AS sort_value FROM raw.pref01n001 WHERE pd_grp_no = 'ETF' AND pd_nm LIKE '%반도체%'
  UNION ALL
SELECT itm_no AS code, itm_nm AS name, '펀드' AS domain, fd_nast_suma AS sort_value FROM raw.prfd01n001 WHERE prvo_pbff_d
  step rdb_펀드: engine=rdb status=None rows=0 err= skip= note=
  step vector_narrative: engine=vector status=ok rows=5 err= skip= note=스코프 50상품(문서 확보 11, 미확보 39), 청크 5건(≥0.45), 요청 주제 미확보: 전략(투자목적·운용전략 섹션 없음)
think_trace: 질문 수신 후 제품 도메인을 국내 ETF와 펀드로 설정하고, RDB와 VectorDB를 통해 정보를 수집함. RDB에서는 국내 ETF와 펀드의 순자산 정보를 조회하였고, VectorDB에서는 기초지수, 전략 등에 대한 문서 근거를 확보하였음.
ANSWER: 순자산 상위 상품으로는 미래에셋 TIGER 반도체TOP10증권상장지수투자신탁(주식)이 있으며, 해당 상품의 정보는 다음과 같음:

- **기초지수**: FnGuide AI 반도체 TOP2+ 지수
- **전략**: 유동시가총액 가중방식으로 종목별 최대비중 상위 2개 종목에 각각 25% 비중을 둠
- **편입내역**: 종목선정일 기준 시총 10,000억원 미만인 종목 제외
- **AUM**: 9,758억 원
- **수익률 기준일**: 2026-05-13
  [C1] 국내 반도체 ETF 순자산 상위 (available/rdb) -> PASS 
  [C2] 반도체 공모펀드 순자산 상위 (available/rdb) -> PASS 
  [C3] 기초지수 근거 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 필요 컬럼/관계 미검색
  [C4] 편입내역 근거 (external_required/graph|vector) -> EXTERNAL_EVIDENCE_PRESENT_OR_SCHEMA_CHECK_NEEDED 외부 관계/문서가 실제 적재됨 - 수동 확인
  [C5] AUM·수익률 기준일 (available/rdb) -> GENERATION_OMISSION <-- ERROR 
  [M] 수동 검토: TIGER 반도체TOP10의 기초지수로 다른 상품(AI반도체TOP2+) 문서 청크 값을 제시 (-/rdb) -> WRONG_VALUE <-- ERROR TIGER 반도체TOP10의 기초지수로 다른 상품(AI반도체TOP2+) 문서 청크 값을 제시

## Q21 r2 status=ok e2e=31.9s pass=False cause=C codes=['RETRIEVAL_MISS']
Q: KODEX200이 국내 ETF 데이터와 공모펀드 데이터에 모두 나타나는 이유를 설명해줘. 동일 운용상품, 상장 클래스, 별도 상품 중 무엇인지 상품번호·대표종목번호·상장 여부 관계를 근거로 판정해줘.
plan: [('rdb_국내ETF', '국내ETF'), ('rdb_펀드', '펀드'), ('vector_narrative', None)] block=[]
  step rdb_국내ETF: engine=rdb status=None rows=0 err= skip= note=
    SQL: SELECT pd_nm, pd_itm_no, pd_itm_no_ma, pd_sale_yn FROM raw.pref01n001 WHERE pd_nm = 'KODEX200'
  step rdb_펀드: engine=rdb status=None rows=0 err= skip= note=
    SQL: SELECT itm_nm AS 상품명, itm_no AS 상품번호, rptt_ksd_itm_no AS 대표종목번호, ofsfd_yn AS 상장_여부 FROM raw.prfd01n001 WHERE prvo_pbff_desc = '공모' AND itm_nm = 'KODEX200'
  step vector_narrative: engine=vector status=ok rows=9 err= skip= note=스코프 없음(전체 문서 검색), 청크 9건(≥0.45)
think_trace: 질문 수신 후 제품 도메인을 '국내ETF'와 '펀드'로 설정하였고, 이를 기반으로 RDB와 VectorDB에서 정보를 검색하였으나, RDB에서는 0건이 조회되었고 VectorDB에서만 9건의 정보가 검색되었다.
ANSWER: 현재 제공된 데이터로는 KODEX200이 국내 ETF 데이터와 공모펀드 데이터에 모두 나타나는 이유에 대해 구조화된 정보(상품번호, 대표종목번호, 상장 여부)를 제공할 수 없으며, 동일 운용상품 여부, 상장 클래스 차이, 별도 상품 여부에 대한 구체적인 설명 또한 포함되지 않았다.
  [C1] 동일 운용상품 판정(ksd_itm_no=pd_itm_no) (available/rdb|graph) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C2] ETF 상품번호 (available/rdb|graph) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C3] 펀드 종목번호/대표종목번호 (available/rdb|graph) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C4] 상장 여부 관계 (available/rdb|graph) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색

## Q22 r2 status=ok e2e=121.3s pass=True cause= codes=[]
Q: 캠브리콘이 실제 편입된 중국 반도체 ETF를 찾아줘. ETF→편입증권→기업 경로를 사용하고, ETF명·티커·편입비중·편입기준일·편입내역 문서명과 근거 문장을 제시해줘.
plan: [('graph_R1', None), ('graph_R2', None), ('graph_R3', None), ('graph_R4', None), ('graph_R5', None), ('rdb_해외ETF', '해외ETF')] block=[]
  step graph_R1: engine=graph status=chained rows=0 err= skip= note=체인 중간 단계 - terminal 단계에서 함께 처리됨
  step graph_R2: engine=graph status=abstain_entity_not_found rows=0 err= skip= note=
  step graph_R3: engine=graph status=abstain_entity_not_found rows=0 err= skip= note=
  step graph_R4: engine=graph status=abstain_entity_not_found rows=0 err= skip= note=
  step graph_R5: engine=graph status=abstain_entity_not_found rows=0 err= skip= note=
  step rdb_해외ETF: engine=rdb status=None rows=100 err= skip= note=
    SQL: SELECT pd_nm AS 상품명, pd_abrv_nm AS ETF명, pd_abrv_nm AS 티커 FROM raw.pref02n001
think_trace: 질문 수신 후 그래프 및 RDB 쿼리를 통해 해외 반도체 ETF 목록을 조회하였으나, 캠브리콘이 포함된 특정 ETF 정보는 찾을 수 없었음.
ANSWER: 조건에 맞는 ETF 정보가 부족하여 답변을 제공할 수 없습니다.
  [C1] 캠브리콘 편입 관계(ETF→편입증권→기업) (external_required/graph) -> EXTERNAL_DATA_REQUIRED 
  [C2] 편입비중·편입기준일 (external_required/graph) -> EXTERNAL_DATA_REQUIRED 
  [C3] 편입내역 문서명·근거 문장 (external_required/vector) -> EXTERNAL_DATA_REQUIRED 

## Q23 r2 status=ok e2e=146.0s pass=False cause=E codes=['UNSUPPORTED_INFERENCE']
Q: 최근 6개월 동안 우주항공 테마와 연결된 이력이 있는 ETF를 정리해줘. 현재 편입 관계와 단순 뉴스 언급을 구분하고, ETF→편입기업→산업/테마→근거문서 경로, 사건일, 문서명과 인용 근거를 제시해줘.
plan: [('graph_R1', None), ('graph_R2', None), ('graph_R3', None), ('graph_R4', None), ('rdb_국내ETF', '국내ETF'), ('rdb_해외ETF', '해외ETF')] block=[]
  step graph_R1: engine=graph status=ok rows=15 err= skip= note=
  step graph_R2: engine=graph status=abstain_entity_not_found rows=0 err= skip= note=
  step graph_R3: engine=graph status=abstain_entity_not_found rows=0 err= skip= note=
  step graph_R4: engine=graph status=abstain_entity_not_found rows=0 err= skip= note=
  step rdb_국내ETF: engine=rdb status=None rows=0 err= skip= note=
    SQL: SELECT pd_nm, pd_ticker, pd_nm AS 편입_기업, wu_inv_ast_type, cu_upt_dt, ref_base_index, ref_fund_mgmt_co FROM raw.pref01n001 WHERE cu_upt_dt >= '2023-01-01' AND pd_itm_no IN ('KR70102X0002', 'KR7494840002', 'KR70093D0007', 'KR70082F0008', 'KR7449450006', 'KR7463250001', 'KR7440910008', 'KR70080G0009', 
  step rdb_해외ETF: engine=rdb status=None rows=0 err= skip=미해결 개념: ['사건 발생 시점'] note=
think_trace: 질의 분석 후 그래프 및 RDB 쿼리를 통해 최근 6개월 동안 우주항공 테마와 관련된 이력을 가진 국내 및 해외 ETF 목록을 추출했습니다.
ANSWER: [{"etf_code":"KR70102X0002","etf_name":"ACE 유럽방산TOP10"},{"etf_code":"KR7494840002","etf_name":"TIGER 미국방산TOP10"},{"etf_code":"KR70093D0007","etf_name":"KoAct 팔란티어밸류체인액티브"},{"etf_code":"KR70082F0008","etf_name":"HANARO 유럽방산"},{"etf_code":"KR7449450006","etf_name":"PLUS K방산"},{"etf_code":"KR7463250001","etf_name":"TIGER K방산&우주"},{"etf_code":"KR7440910008","etf_name":"WON 미국우주항공방산"},{"etf_code":"KR70080G0009","etf_name":"KODEX 방산TOP10"},{"etf_code":"KR70100K0009","etf_name":"KODEX 방산TOP10레버리지"},{"etf_code":"KR7496770009","etf_name":"PLUS 글로벌방산"},{"etf_code":"KR7490480001","etf_name":"SOL K방산"},{"etf_code":"KR70151P0002","etf_name":"RISE 코리아전략산업액티브"},{"etf_code":"KR70104G0001","etf_name":"PLUS K방산레버리지"},{"etf_code":"KR7478150006","etf_name":"TIME 글로벌우주테크&방산액티브"},{"etf_code":"KR70090B0002","etf_name":"PLUS K방산소부장"}]
  [C1] 현재 우주항공/방산 테마 ETF (available/rdb|graph) -> PASS 
  [C2] 최근 6개월 테마 연결 이력(시점 축) (external_required/graph) -> EXTERNAL_DATA_REQUIRED 
  [C3] 현재 편입 관계와 뉴스 언급 구분 (external_required/vector) -> UNSUPPORTED_INFERENCE <-- CRITICAL 외부 필요 항목의 부재를 고지하지 않음

## Q24 r2 status=ok e2e=38.4s pass=True cause= codes=[]
Q: 에코프로의 자회사를 편입한 ETF를 찾고 그중 최신 AUM이 가장 큰 상품의 위험요인을 알려줘. 에코프로→자회사→편입종목→ETF 관계 근거, 편입비중·기준일, AUM 기준일과 위험요인 문서의 인용문을 제시해줘.
plan: [('graph_R1', None), ('graph_R2', None), ('graph_R3', None), ('rdb_국내ETF', '국내ETF'), ('vector_narrative', None)] block=[]
  step graph_R1: engine=graph status=chained rows=0 err= skip= note=체인 중간 단계 - terminal 단계에서 함께 처리됨
  step graph_R2: engine=graph status=chained rows=0 err= skip= note=체인 중간 단계 - terminal 단계에서 함께 처리됨
  step graph_R3: engine=graph status=abstain_evidence_missing rows=0 err= skip= note=
  step rdb_국내ETF: engine=rdb status=None rows=0 err= skip= note=
    SQL: SELECT pd_nm FROM raw.pref01n001 WHERE pd_grp_no = 'ETF' AND pd_nm LIKE '%에코프로%' AND du_last_aum IS NOT NULL ORDER BY du_last_aum DESC LIMIT 1
  step vector_narrative: engine=vector status=ok rows=5 err= skip= note=스코프 없음(전체 문서 검색), 청크 5건(≥0.45)
think_trace: 질의 분석 후 GraphDB와 RDB, VectorDB를 통해 정보를 검색하였으나, 에코프로의 자회사를 편입한 ETF와 관련된 구체적인 정보는 발견되지 않았습니다. 다만, 여러 ETF의 투자위험 관련 정보가 벡터 데이터베이스에서 수집되었습니다.
ANSWER: 위험요인 문서 인용문:

[집합투자기구 위험등급 분류기준 및 상세설명]
위험등급 | 분류기준 | 상세설명(주)
1등급 | 매우높은위험 | ①레버리지 등 수익구조가 특수하여 투자시 주의가 필요한 집합투자기구②국내ㆍ외 부동산, 자원 등 실물관련자산(중위험자산 제외)에 50%를 초과하여 투자하는 집합투자기구③최대손실률이 20%를 초과하는 파생결합증권에 주로 투자하는 집합투자기구④기타 이와 유사한 위험수준을 갖는 집합투자기구
2등급 | 높은위험 | ①고위험자산에 80% 이상 투자하는 집합투자기구②기타 이와 유사한 위험수준을 
(출처: 투자설명서, 기준일 2026-02-13)
  [C1] 에코프로 자회사 관계 (external_required/graph) -> EXTERNAL_DATA_REQUIRED 
  [C2] 자회사 ETF 편입 관계 (external_required/graph) -> EXTERNAL_DATA_REQUIRED 
  [C3] 편입비중·기준일 (external_required/graph) -> EXTERNAL_DATA_REQUIRED 
  [C4] ETF AUM·기준일(대상 ETF 특정 시) (partial/rdb) -> PARTIAL_GAP_ACKNOWLEDGED 
  [C5] 위험요인 문서 인용 (external_required/vector) -> EXTERNAL_EVIDENCE_PRESENT_OR_SCHEMA_CHECK_NEEDED 외부 관계/문서가 실제 적재됨 - 수동 확인

## Q25 r2 status=ok e2e=19.5s pass=False cause=C codes=['FILTER_ERROR', 'RETRIEVAL_MISS']
Q: 국민성장펀드의 구조, 운용주체, 자금조달 방식과 최근 투자전략 동향을 정리해줘. 공식 정책자료·운용자료만 사용하고 문서명, 발표기관, 발행일과 각 주장에 대응하는 근거 문장을 붙여줘.
plan: [('rdb_펀드', '펀드'), ('vector_narrative', None)] block=[]
  step rdb_펀드: engine=rdb status=None rows=0 err= skip= note=
    SQL: SELECT itm_nm FROM raw.prfd01n001 WHERE itm_nm LIKE '%국민성장펀드%' AND prvo_pbff_desc = '공모'
  step vector_narrative: engine=vector status=no_product_match rows=0 err= skip= note=상품 후보 1건을 product_master에서 해소하지 못해 문서 검색 생략
think_trace: 데이터 검색 불가 및 쿼리 플랜 실패로 인한 답변 불가 처리
ANSWER: 제공된 데이터로는 이 질문에 답변할 수 없습니다. (문서 근거 no_product_match: 상품 후보 1건을 product_master에서 해소하지 못해 문서 검색 생략)
  [C1] 국민성장 명칭 매칭 펀드 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C2] 구조/펀드유형 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C3] 벤치마크 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C4] 순자산 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C5] 운용주체·자금조달·투자전략 동향(공식 문서) (external_required/vector) -> EXTERNAL_DATA_REQUIRED 
  [M] 수동 검토: 국민성장 4건은 prvo_pbff_desc='사모'로 적재돼 공모 필터에 걸러짐(골든 비고의 함정) (-/rdb) -> FILTER_ERROR <-- ERROR 국민성장 4건은 prvo_pbff_desc='사모'로 적재돼 공모 필터에 걸러짐(골든 비고의 함정)

## Q26 r2 status=ok e2e=176.7s pass=False cause=C codes=['GENERATION_OMISSION', 'RETRIEVAL_MISS']
Q: SK하이닉스가 발행한 매수 가능 채권과 SK하이닉스를 편입한 ETF·공모펀드를 연결해 알려줘. 발행사→채권과 기업→편입증권→상품 경로를 구분하고 등급·수익률·편입비중·AUM의 기준일과 근거를 제시해줘.
plan: [('graph_R1', None), ('graph_R2', None), ('graph_R3', None), ('graph_R4', None), ('graph_R5', None), ('rdb_채권', '채권'), ('rdb_국내ETF', '국내ETF'), ('rdb_펀드', '펀드'), ('vector_narrative', None)] block=[]
  step graph_R1: engine=graph status=abstain_evidence_missing rows=0 err= skip= note=
  step graph_R2: engine=graph status=abstain_entity_not_found rows=0 err= skip= note=
  step graph_R3: engine=graph status=abstain_evidence_missing rows=0 err= skip= note=
  step graph_R4: engine=graph status=abstain_entity_not_found rows=0 err= skip= note=
  step graph_R5: engine=graph status=abstain_entity_not_found rows=0 err= skip= note=
  step rdb_채권: engine=rdb status=None rows=100 err= skip= note=
    SQL: SELECT pd_nm, crd_grd, applied_yield FROM raw.prbd01n001 WHERE std_pd_mcls_nm = '회사채'
  step rdb_국내ETF: engine=rdb status=None rows=15 err= skip= note=
    SQL: SELECT pd_nm AS 상품명, pd_risk_nm AS 등급, du_er_1d AS 수익률, du_last_aum AS AUM FROM raw.pref01n001 WHERE pd_grp_no = 'ETF' AND pd_nm LIKE '%SK하이닉스%'
  step rdb_펀드: engine=rdb status=None rows=0 err= skip= note=
    SQL: WITH sk_hynix_bond AS (
    SELECT *
    FROM raw.prfd01n001
    WHERE mtco_itm_no LIKE '%SK하이닉스%'
),
sk_hynix_funds AS (
    SELECT *
    FROM raw.prfd01n001
    WHERE (or_co_xtn_itt_cd LIKE '%SK하이닉스%' OR itm_nm LIKE '%SK하이닉스%') AND prvo_pbff_desc = '공모'
)

SELECT 
    COALESCE(sk_hynix_bond.itm_nm
  step vector_narrative: engine=vector status=no_hit rows=0 err= skip= note=스코프 50상품(문서 확보 0, 미확보 0), 청크 0건(≥0.45)
think_trace: 그래프 DB 및 벡터 DB에서 정보를 찾을 수 없었으며, RDB에서만 일부 데이터를 조회하였음. 채권과 관련된 정보는 여러 건의 데이터가 있었고, ETF와 관련된 정보도 일부 조회되었으나 펀드에 대한 정보는 없었음.
ANSWER: 
  [C1] 에스케이하이닉스(주) 발행 채권 목록(pd_pbcm 필터) (available/rdb) -> RETRIEVAL_MISS <-- ERROR 필요 컬럼/관계 미검색
  [C2] 채권 신용등급 (available/rdb) -> GENERATION_OMISSION <-- ERROR 
  [C3] 채권 만기 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 필요 컬럼/관계 미검색
  [C4] 채권 수익률 (available/rdb) -> PASS 
  [C5] SK하이닉스 편입 ETF·공모펀드 경로 (external_required/graph) -> GENERATION_OMISSION <-- ERROR 답변불가만 말하고 필요한 외부 데이터 종류를 명시하지 않음(§11.3)
  [C6] 편입비중·AUM 기준일 (external_required/graph|rdb) -> EXTERNAL_EVIDENCE_PRESENT_OR_SCHEMA_CHECK_NEEDED 외부 관계/문서가 실제 적재됨 - 수동 확인

## Q27 r2 status=ok e2e=96.8s pass=False cause=C codes=['GENERATION_OMISSION', 'RETRIEVAL_MISS']
Q: LG에너지솔루션 및 확인된 자회사가 발행한 채권과 이 기업들을 편입한 ETF를 찾아줘. 모자회사 관계의 공식 근거, 채권 신용등급·만기, ETF 편입비중을 제시하고 배터리산업 위험요인은 근거 문서별로 구분해줘.
plan: [('graph_R1', None), ('graph_R2', None), ('graph_R3', None), ('graph_R4', None), ('rdb_채권', '채권'), ('rdb_국내ETF', '국내ETF'), ('vector_narrative', None)] block=[]
  step graph_R1: engine=graph status=chained rows=0 err= skip= note=체인 중간 단계 - terminal 단계에서 함께 처리됨
  step graph_R2: engine=graph status=abstain_invalid_graph_plan rows=0 err= skip= note=
  step graph_R3: engine=graph status=abstain_entity_not_found rows=0 err= skip= note=
  step graph_R4: engine=graph status=abstain_evidence_missing rows=0 err= skip= note=
  step rdb_채권: engine=rdb status=None rows=100 err= skip= note=
    SQL: SELECT DISTINCT pd_no, pd_nm, crd_grd FROM raw.prbd01n001 WHERE std_pd_mcls_nm = '회사채'
  step rdb_국내ETF: engine=rdb status=None rows=3 err= skip= note=
    SQL: SELECT pd_nm
FROM raw.pref01n001
WHERE pd_grp_no = 'ETF'
AND (pd_nm LIKE '%배터리%' OR pd_nm LIKE '%LG에너지솔루션%')
  step vector_narrative: engine=vector status=topic_not_covered rows=0 err= skip= note=스코프 50상품(문서 확보 0, 미확보 0), 청크 0건(≥0.45), 요청 주제 미확보: 배터리산업 위험요인(투자위험 섹션 없음)
think_trace: 질의 분석 후 그래프 DB와 벡터 DB에서 정보를 찾으려 했으나 해당 정보는 발견되지 않았고, RDB에서만 일부 데이터를 찾았다.
ANSWER: 검색된 데이터에는 LG에너지솔루션 및 그 자회사가 발행한 채권과 관련된 정보가 부족하여 구체적인 답변을 제공할 수 없습니다.
  [C1] (주)엘지에너지솔루션 발행 채권 (available/rdb) -> PASS 
  [C2] 채권 신용등급 (available/rdb) -> GENERATION_OMISSION <-- ERROR 
  [C3] 채권 만기 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 필요 컬럼/관계 미검색
  [C4] 모자회사 관계 공식 근거 (external_required/graph) -> EXTERNAL_DATA_REQUIRED 
  [C5] ETF 편입비중 (external_required/graph) -> EXTERNAL_DATA_REQUIRED 
  [C6] 배터리산업 위험요인 문서 (external_required/vector) -> EXTERNAL_DATA_REQUIRED 

## Q28 r2 status=ok e2e=36.7s pass=False cause=C codes=['FILTER_ERROR', 'UNGROUNDED_CLAIM']
Q: 엔비디아를 편입한 국내 ETF와 해외 ETF 중 순자산이 큰 상품을 비교하고, 일반 지수형과 커버드콜형의 위험 차이를 설명해줘. 편입내역 기준일, 비중, AUM, 전략 원문 및 위험 설명의 문서 근거를 제시해줘.
plan: [('graph_R1', None), ('graph_R2', None), ('rdb_국내ETF', '국내ETF'), ('rdb_해외ETF', '해외ETF'), ('vector_narrative', None)] block=[]
  step graph_R1: engine=graph status=ok rows=3 err= skip= note=
  step graph_R2: engine=graph status=ok rows=3 err= skip= note=
  step rdb_국내ETF: engine=rdb status=None rows=1 err= skip= note=
    SQL: SELECT * FROM (
SELECT pd_itm_no AS code, pd_nm AS name, '국내ETF' AS domain, pd_net_tamt AS sort_value FROM raw.pref01n001 WHERE pd_grp_no = 'ETF' AND pd_nm LIKE '%엔비디아%'
  UNION ALL
SELECT pd_itm_no AS code, pd_nm AS name, '해외ETF' AS domain, du_last_aum AS sort_value FROM raw.pref02n001
) merged
ORD
  step rdb_해외ETF: engine=rdb status=None rows=0 err= skip= note=
  step vector_narrative: engine=vector status=topic_not_covered rows=0 err= skip= note=스코프 1상품(문서 확보 0, 미확보 0), 청크 0건(≥0.45), 요청 주제 미확보: 일반 지수형과 커버드콜형의 위험 차이/위험 설명(투자위험 섹션 없음); 전략 원문(투자목적
think_trace: 질문 수신 후 그래프 DB와 RDB를 통해 엔비디아를 편입한 국내 ETF와 해외 ETF 중 순자산이 큰 상품을 조회함. VectorDB에서는 필요한 정보를 찾을 수 없었음.
ANSWER: 검색된 데이터에는 다음과 같은 정보가 포함되어 있습니다:

1. TIGER 엔비디아미국채커버드콜밸런스(합성)
   - 코드: KR70000D0009
   
2. ACE 엔비디아채권혼합
   - 코드: KR7448540005
   
3. KIWOOM 엔비디아미국30년국채혼합액티브(H)
   - 코드: KR70015E0001
   
4. Vanguard 500 Index Fund;ETF
   - 코드: VOO, 순자산: 997,351,790,000.00
  [C1] 엔비디아 편입 관계(이름 포함≠편입) (external_required/graph) -> EXTERNAL_EVIDENCE_PRESENT_OR_SCHEMA_CHECK_NEEDED 외부 관계/문서가 실제 적재됨 - 수동 확인
  [C2] 편입비중·편입기준일 (external_required/graph) -> EXTERNAL_DATA_REQUIRED 
  [C3] AUM(상품명 후보 기준) (partial/rdb) -> PASS 
  [C4] 전략 원문·커버드콜 식별 (partial/rdb) -> PASS 
  [C5] 위험 설명 문서 근거 (external_required/vector) -> EXTERNAL_DATA_REQUIRED 
  [M] 수동 검토: 해외ETF 서브쿼리에 엔비디아 조건이 없어 AUM 상위(VOO·IVV)를 편입 ETF로 제시, 커버드콜 위험 설명은 인용 없는 일반 지식 (-/rdb) -> FILTER_ERROR <-- ERROR 해외ETF 서브쿼리에 엔비디아 조건이 없어 AUM 상위(VOO·IVV)를 편입 ETF로 제시, 커버드콜 위험 설명은 인용 없는 일반 지식
  [M] 수동 검토: 해외ETF 서브쿼리에 엔비디아 조건이 없어 AUM 상위(VOO·IVV)를 편입 ETF로 제시, 커버드콜 위험 설명은 인용 없는 일반 지식 (-/rdb) -> UNGROUNDED_CLAIM <-- CRITICAL 해외ETF 서브쿼리에 엔비디아 조건이 없어 AUM 상위(VOO·IVV)를 편입 ETF로 제시, 커버드콜 위험 설명은 인용 없는 일반 지식

## Q29 r2 status=ok e2e=37.0s pass=False cause=D codes=['GENERATION_OMISSION', 'RETRIEVAL_MISS', 'ROUTING_MISS']
Q: VOO, IVV, SPY가 같은 S&P 500 계열 지수를 추종하는지 확인하고 편입종목 중복률과 상위 기업 집중위험을 비교해줘. 기초지수, 편입기준일, 종목별 비중, 보수, AUM과 운용문서 근거를 제시해줘.
plan: [('graph_R1', None), ('rdb_국내ETF', '국내ETF'), ('vector_narrative', None)] block=[]
  step graph_R1: engine=graph status=abstain_entity_not_found rows=0 err= skip= note=
  step rdb_국내ETF: engine=rdb status=None rows=0 err= skip= note=
    SQL: SELECT pd_nm, ref_base_index, cu_base_index, cu_charge_rt, du_last_aum FROM raw.pref01n001 WHERE pd_nm LIKE '%VOO%' OR pd_nm LIKE '%IVV%' OR pd_nm LIKE '%SPY%';
  step vector_narrative: engine=vector status=no_product_match rows=0 err= skip= note=상품 후보 3건을 product_master에서 해소하지 못해 문서 검색 생략
think_trace: 데이터 검색 불가 및 쿼리 플랜 실패로 인한 답변 불가 처리
ANSWER: 제공된 데이터로는 이 질문에 답변할 수 없습니다. (문서 근거 no_product_match: 상품 후보 3건을 product_master에서 해소하지 못해 문서 검색 생략)
  [R0] 상품군 라우팅(기대 ['해외ETF'], 계획 ['국내ETF']) (available/rdb) -> ROUTING_MISS <-- ERROR intent product_domain이 골든 상품군과 불일치
  [C1] 기초지수 동일(S&P 500 TR) (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C2] 보수 (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C3] AUM (available/rdb) -> RETRIEVAL_MISS <-- ERROR 0행/필드 미검색
  [C4] 편입종목 중복률 (external_required/graph) -> GENERATION_OMISSION <-- ERROR 답변불가만 말하고 필요한 외부 데이터 종류를 명시하지 않음(§11.3)
  [C5] 상위 기업 집중위험(종목별 비중) (external_required/graph) -> GENERATION_OMISSION <-- ERROR 답변불가만 말하고 필요한 외부 데이터 종류를 명시하지 않음(§11.3)
  [C6] 운용문서 근거 (external_required/vector) -> EXTERNAL_DATA_REQUIRED 

## Q30 r2 status=ok e2e=32.6s pass=False cause=C codes=['FILTER_ERROR', 'GENERATION_OMISSION']
Q: 우리반도체BIG2플러스 펀드와 국내 반도체 ETF의 실제 편입종목 중복도를 계산하고 중복 노출이 큰 기업의 자회사·산업 위험을 알려줘. 클래스 중복은 제거하고 편입기준일, 중복도 계산식, 기업관계 및 위험문서 근거를 제시해줘.
plan: [('rdb_펀드', '펀드'), ('rdb_국내ETF', '국내ETF'), ('vector_narrative', None)] block=[]
  step rdb_펀드: engine=rdb status=None rows=100 err= skip= note=
    SQL: SELECT itm_nm, fd_price_bas_dt FROM raw.prfd01n001 WHERE or_attr_desc = '주식형' AND prvo_pbff_desc = '공모'
  step rdb_국내ETF: engine=rdb status=None rows=61 err= skip= note=
    SQL: SELECT pd_nm, pd_lstg_dt FROM raw.pref01n001 WHERE pd_grp_no = 'ETF' AND pd_nm LIKE '%반도체%';
  step vector_narrative: engine=vector status=ok rows=1 err= skip= note=스코프 50상품(문서 확보 1, 미확보 49), 청크 1건(≥0.45)
think_trace: 질문 수신 후 제품 도메인을 펀드와 국내 ETF로 설정하고, RDB와 VectorDB를 통해 데이터를 검색함. RDB에서는 각각 100건과 61건의 결과가 나왔으며, VectorDB에서는 1건의 결과가 나옴. 이후 결과를 합쳐 총 162건의 데이터를 얻음.
ANSWER: 죄송하지만, 제공된 데이터로는 요청하신 정보를 제공할 수 없습니다. 중복도 계산식, 기업관계, 위험문서 근거 등의 정보가 포함되어 있지 않으며, 중복 노출이 큰 기업의 자회사 및 산업 위험에 대한 정보도 확인할 수 없습니다.
  [C1] 우리반도체BIG2플러스 클래스 중복 제거 (available/rdb) -> GENERATION_OMISSION <-- ERROR 
  [C2] 편입종목 중복도(계산식) (external_required/graph) -> EXTERNAL_DATA_REQUIRED 
  [C3] 중복 노출 기업의 자회사·산업 위험 (external_required/graph) -> EXTERNAL_DATA_REQUIRED 
  [C4] 위험문서 근거 (external_required/vector) -> EXTERNAL_EVIDENCE_PRESENT_OR_SCHEMA_CHECK_NEEDED 외부 관계/문서가 실제 적재됨 - 수동 확인
  [M] 수동 검토: 펀드 SQL이 우리반도체BIG2플러스를 특정하지 않고 주식형 전체(100행)를 조회 (-/rdb) -> FILTER_ERROR <-- ERROR 펀드 SQL이 우리반도체BIG2플러스를 특정하지 않고 주식형 전체(100행)를 조회

## Q31 r2 status=ok e2e=10.4s pass=False cause=E codes=['MISSING_EVIDENCE']
Q: 신용등급이 AAAA인 매수 가능 채권을 찾아 상품번호와 신용평가 근거를 제시해줘.
plan: [('rdb_채권', '채권')] block=[]
  step rdb_채권: engine=rdb status=None rows=0 err= skip=유효하지 않은 조건: 신용등급='AAAA' ('AAAA'는 crd_grd의 유효 값 범위에 없습니다 (유효 값: ['C', 'C0', 'CC0', 'CCC', 'B-', 'B0', 'B+', 'BB-', 'BB0', note=
think_trace: 데이터 검색 불가 및 쿼리 플랜 실패로 인한 답변 불가 처리
ANSWER: 제공된 데이터로는 이 질문에 답변할 수 없습니다.
  [C1] 신용등급 AAAA는 허용값 아님 (invalid_taxonomy/ontology) -> MISSING_EVIDENCE <-- ERROR abstain은 했으나 subtype 근거 없음(기대 ABSTAIN_INVALID_TAXONOMY)

## Q32 r2 status=ok e2e=26.4s pass=False cause=D codes=['MISSING_EVIDENCE']
Q: 2026-08-24 기준으로 Kimi 관련 투자 상품을 찾아 해당 모델과 상품의 연결 근거 문서, 발표일과 편입비중을 알려줘.
plan: [('graph_R1', None), ('rdb_펀드', '펀드')] block=[]
  step graph_R1: engine=graph status=abstain_entity_not_found rows=0 err= skip= note=
  step rdb_펀드: engine=rdb status=None rows=0 err= skip= note=
    SQL: SELECT itm_nm FROM raw.prfd01n001 WHERE (fd_price_bas_dt >= '20260824') AND (itm_nm LIKE '%Kimi%') AND (prvo_pbff_desc = '공모')
think_trace: 데이터 검색 불가 및 쿼리 플랜 실패로 인한 답변 불가 처리
ANSWER: 제공된 데이터로는 이 질문에 답변할 수 없습니다.
  [C1] Kimi 관련 상품이 기준일 시점에 없음 (not_released_as_of_cutoff/ontology) -> MISSING_EVIDENCE <-- ERROR abstain은 했으나 subtype 근거 없음(기대 ABSTAIN_NOT_RELEASED_AS_OF_CUTOFF)

## Q33 r2 status=ok e2e=14.8s pass=False cause=D codes=['MISSING_EVIDENCE']
Q: KODEX AI로봇 ETF의 수익률과 편입종목을 공식 문서 근거로 알려줘.
plan: [('rdb_국내ETF', '국내ETF'), ('vector_narrative', None)] block=[]
  step rdb_국내ETF: engine=rdb status=None rows=0 err= skip= note=
    SQL: SELECT pd_nm, du_er_1d FROM raw.pref01n001 WHERE pd_nm LIKE '%KODEX AI로봇 ETF%' AND pd_grp_no = 'ETF'
  step vector_narrative: engine=vector status=no_product_match rows=0 err= skip= note=상품 후보 1건을 product_master에서 해소하지 못해 문서 검색 생략
think_trace: 데이터 검색 불가 및 쿼리 플랜 실패로 인한 답변 불가 처리
ANSWER: 제공된 데이터로는 이 질문에 답변할 수 없습니다. (문서 근거 no_product_match: 상품 후보 1건을 product_master에서 해소하지 못해 문서 검색 생략)
  [C1] KODEX AI로봇 상품 부재 (entity_not_found/ontology) -> MISSING_EVIDENCE <-- ERROR abstain은 했으나 subtype 근거 없음(기대 ABSTAIN_ENTITY_NOT_FOUND)

## Q34 r2 status=ok e2e=15.5s pass=False cause=D codes=['MISSING_EVIDENCE']
Q: TIGER 미국S&P500의 2027년 확정 연간수익률을 데이터 근거와 함께 알려줘.
plan: [('rdb_해외ETF', '해외ETF'), ('vector_narrative', None)] block=[]
  step rdb_해외ETF: engine=rdb status=None rows=0 err= skip= note=
    SQL: SELECT pd_nm FROM raw.pref02n001 WHERE pd_nm LIKE '%TIGER 미국S&P500%'
  step vector_narrative: engine=vector status=no_product_match rows=0 err= skip= note=상품 후보 1건을 product_master에서 해소하지 못해 문서 검색 생략
think_trace: 데이터 검색 불가 및 쿼리 플랜 실패로 인한 답변 불가 처리
ANSWER: 제공된 데이터로는 이 질문에 답변할 수 없습니다. (문서 근거 no_product_match: 상품 후보 1건을 product_master에서 해소하지 못해 문서 검색 생략)
  [C1] 2027년 확정 수익률은 미래값 (future_unavailable/ontology) -> MISSING_EVIDENCE <-- ERROR abstain은 했으나 subtype 근거 없음(기대 ABSTAIN_FUTURE_DATA)

## Q35 r2 status=ok e2e=23.1s pass=False cause=D codes=['MISSING_EVIDENCE']
Q: VOO가 직접 발행한 회사채의 신용등급과 만기일을 알려줘.
plan: [('graph_R1', None), ('rdb_채권', '채권')] block=[]
  step rdb_채권: engine=rdb status=None rows=100 err= skip= note=
    SQL: SELECT DISTINCT pd_nm, crd_grd, mat_dt FROM raw.prbd01n001 WHERE std_pd_mcls_nm = '회사채'
  step graph_R1: engine=graph status=abstain_entity_not_found rows=0 err= skip= note=
think_trace: 질의 분석 후 그래프 및 RDB 쿼리를 통해 VOO가 직접 발행한 회사채 정보를 조회하였으나, 해당 정보는 발견되지 않았습니다.
ANSWER: 조건에 맞는 회사채 정보가 없습니다.
  [C1] VOO는 ETF, issuedBy domain은 Bond (domain_mismatch/ontology) -> MISSING_EVIDENCE <-- ERROR abstain은 했으나 subtype 근거 없음(기대 ABSTAIN_DOMAIN_MISMATCH)
