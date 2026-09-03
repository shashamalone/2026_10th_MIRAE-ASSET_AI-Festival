### 표 1. 질의별 결과 (warm 2~4회차, ms는 중앙값)

| ID | 질문 | 루브릭 유형 | 라우트 | 정답 | E2E p50 | E2E p95 | frame ms | plan ms | graph ms | rdb ms | vector ms | generate ms | LLM 호출 | 실패신호 | 오답 원인코드 |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| Q1 | 최신 상품정보 갱신일 기준으로 에스케이하이닉스224-2의 발행사, 신 | 부분산출 | rdb_only+vector | X(0/3) | 24,712 | 26,933 | 9,159 | 0 | 0 | 12,875 | 1,222 | 2,734 | 6 | vector_narrative:0행×3 | C×3 STALE_DEFINITION×3 |
| Q2 | 국고채권 02000-3106(21-5)의 발행일, 만기일, 잔존일수, | 산출가능 | rdb_only | O(3/3) | 20,960 | 23,707 | 6,782 | 0 | 0 | 10,723 | 0 | 3,442 | 6 | - | - - |
| Q3 | 현대해상화재보험7(후)(콜/후)의 채권 종류, 발행사, 신용등급, 만 | 산출가능 | rdb_only+vector | X(0/3) | 14,774 | 19,506 | 12,132 | 0 | 0 | 1,011 | 1,035 | 0 | 3 | rdb_채권:skipped×2, vector_narrative:0행×2 | C×3 QUERY_GENERATION_ERROR×2, RETRIEVAL_MISS×1 |
| Q4 | KODEX 200의 운용사, 기초지수, 현재 AUM, NAV, 종가, | 산출가능 | rdb_only | X(0/3) | 19,382 | 20,976 | 8,340 | 0 | 0 | 9,926 | 0 | 1,622 | 6 | - | C×3 GENERATION_OMISSION×3, RETRIEVAL_MISS×3 |
| Q5 | TIGER 미국S&P500의 투자자산군, 투자지역, 운용전략, 복제방 | 산출가능 | rdb_only+vector | X(0/3) | 23,992 | 24,186 | 7,265 | 0 | 0 | 10,155 | 1,618 | 3,551 | 6 | vector_narrative:0행×3 | C×3 GENERATION_OMISSION×3, RETRIEVAL_MISS×3 |
| Q6 | VOO의 정식 상품명, 기초지수, 운용사, 총보수, AUM, 현재가와 | 부분산출 | rdb_only | X(0/3) | 20,361 | 24,998 | 6,958 | 0 | 0 | 11,531 | 0 | 0 | 5 | rdb_해외ETF:0행×2, rdb_해외ETF:error×1, vector_narrative:0행×1 | C×3 GENERATION_OMISSION×2, RETRIEVAL_MISS×2, QUERY_EXECUTION_ERROR×1 |
| Q7 | BND의 투자자산 유형, 투자지역, 기초지수, 지수 복제방식, 운용전 | 산출가능 | rdb_only+vector | X(0/3) | 25,134 | 25,278 | 6,700 | 0 | 0 | 18,041 | 284 | 0 | 7 | vector_narrative:0행×3, rdb_펀드:error×2, rdb_펀드:0행×1 | D×3 ROUTING_MISS×3, QUERY_EXECUTION_ERROR×2, RETRIEVAL_MISS×1 |
| Q8 | 미래에셋코어테크증권자투자신탁(주식) 종류A의 펀드 유형, 순자산, 1 | 산출가능 | rdb_only | O(3/3) | 26,698 | 30,236 | 11,103 | 0 | 0 | 11,748 | 0 | 3,837 | 6 | - | - - |
| Q9 | 삼성 베스트 MMF 법인 제1호의 벤치마크, 통화, 투자지역, 개인· | 산출가능 | rdb_only+vector | O(3/3) | 19,821 | 20,469 | 6,538 | 0 | 0 | 10,051 | 1,023 | 2,706 | 6 | - | - - |
| Q10 | 우리반도체BIG2플러스의 C-P와 C-Pe 클래스가 동일한 모펀드의  | 산출가능 | graph_then_rdb+vector | X(0/3) | 140,842 | 152,805 | 13,655 | 0 | 107,584 | 14,729 | 1,146 | 3,550 | 6 | graph_R2:abstain_entity_not_found×3, graph_R3:abstain_entity_not_found×3, vector_narrative:0행×3 | C×3 GENERATION_OMISSION×3, QUERY_GENERATION_ERROR×3 |
| Q11 | 최신 갱신일 기준 매수가능수량이 0보다 큰 원화채권 중 신용등급이 A | 정의변경 | rdb_only | X(0/3) | 29,816 | 31,889 | 12,474 | 0 | 0 | 9,993 | 0 | 7,313 | 6 | exception×1 | C×2/F×1 RETRIEVAL_MISS×3, STALE_DEFINITION×3, GENERATION_OMISSION×1 |
| Q12 | 현재 판매 중이고 거래정지가 아니며 연금거래가 가능한 국내 ETF를  | 산출가능 | rdb_only | X(0/3) | 24,537 | 24,893 | 13,555 | 0 | 0 | 10,743 | 0 | 0 | 5 | rdb_국내ETF:0행×3 | C×3 FILTER_ERROR×3, GENERATION_OMISSION×3, RETRIEVAL_MISS×3 |
| Q13 | 매수 가능한 회사채 중 AA- 이상이고 잔존기간이 3년 이하인 종목을 | 정의변경 | rdb_only | X(0/3) | 36,138 | 40,206 | 12,372 | 0 | 0 | 14,972 | 0 | 8,776 | 7 | exception×1 | C×2/F×1 GENERATION_OMISSION×3, STALE_DEFINITION×3, INFRA_EXCEPTION×1 |
| Q14 | 담보부 또는 보증채 중 AAA 등급인 종목을 발행잔액 순으로 정리해줘 | 부분산출 | rdb_only | X(0/3) | 24,622 | 25,298 | 7,491 | 0 | 0 | 10,088 | 0 | 7,031 | 6 | exception×1 | C×2/F×1 RETRIEVAL_MISS×3, GENERATION_OMISSION×2, INFRA_EXCEPTION×1 |
| Q15 | 해외주식에 투자하는 패시브·실물복제·정방향 ETF 중 순자산 1조 원 | 산출가능 | rdb_only | X(0/3) | 22,652 | 23,023 | 11,207 | 0 | 0 | 10,033 | 0 | 0 | 5 | rdb_해외ETF:0행×2 | D×3 GENERATION_OMISSION×3, RETRIEVAL_MISS×3, ROUTING_MISS×3 |
| Q16 | 섹터·테마형 액티브 ETF 중 순자산 5천억 원 이상인 상품을 찾아  | 부분산출 | rdb_only+vector | X(0/3) | 30,282 | 38,432 | 7,897 | 0 | 0 | 13,568 | 1,735 | 7,047 | 7 | - | D×3 ROUTING_MISS×3, GENERATION_OMISSION×2 |
| Q17 | 미국 주식형 ETF 중 AUM이 1천억 달러 이상이고 총보수가 0.0 | 산출가능 | rdb_only | X(0/3) | 22,332 | 23,454 | 8,895 | 0 | 0 | 13,021 | 0 | 0 | 6 | rdb_해외ETF:0행×2 | C×2/E×1 GENERATION_OMISSION×3, FILTER_ERROR×2, RETRIEVAL_MISS×2 |
| Q18 | 해외 채권 ETF 중 총보수가 0.10% 이하인 상품을 AUM 순으로 | 산출가능 | rdb_only | X(0/3) | 29,876 | 30,128 | 8,656 | 0 | 0 | 12,311 | 0 | 9,148 | 7 | - | C×3 FILTER_ERROR×3, GENERATION_OMISSION×3 |
| Q19 | 판매 중인 공모펀드 가운데 1년 수익률이 양수이고 순자산이 1천억 원 | 산출가능 | rdb_only | X(0/3) | 23,560 | 24,939 | 11,644 | 0 | 0 | 11,860 | 0 | 0 | 5 | rdb_펀드:0행×3 | C×3 FILTER_ERROR×3, GENERATION_OMISSION×3, RETRIEVAL_MISS×3 |
| Q20 | 국내 반도체에 투자하는 ETF와 공모펀드를 통합 검색해 순자산 상위  | 부분산출 | rdb_only+vector | X(0/3) | 34,818 | 35,742 | 8,681 | 0 | 0 | 18,455 | 2,299 | 4,564 | 7 | rdb_펀드:0행×3 | C×3 GENERATION_OMISSION×3, RETRIEVAL_MISS×3, WRONG_VALUE×3 |
| Q21 | KODEX200이 국내 ETF 데이터와 공모펀드 데이터에 모두 나타나 | 산출가능 | rdb_only+vector | X(0/2) | 34,020 | 36,129 | 7,811 | 0 | 0 | 21,182 | 1,848 | 3,168 | 9 | rdb_펀드:0행×2, vector_narrative:0행×2, rdb_국내ETF:0행×1, rate_limited×1 | C×1/E×1 RETRIEVAL_MISS×1, GENERATION_OMISSION×1 |
| Q22 | 캠브리콘이 실제 편입된 중국 반도체 ETF를 찾아줘. ETF→편입증권 | 외부데이터필요 | graph_then_rdb | △(1/3) | 40,310 | 121,272 | 9,514 | 0 | 14,171 | 10,763 | 0 | 1,623 | 6 | graph_R1:abstain_entity_not_found×2, graph_R2:abstain_entity_not_found×1, graph_R3:abstain_entity_not_found×1, graph_R4:abstain_entity_not_found×1 | E×2 GENERATION_OMISSION×2 |
| Q23 | 최근 6개월 동안 우주항공 테마와 연결된 이력이 있는 ETF를 정리해 | 부분산출 | graph_then_rdb | X(0/3) | 145,989 | 166,062 | 20,780 | 0 | 91,743 | 27,265 | 0 | 7,644 | 9 | graph_R2:abstain_entity_not_found×3, graph_R3:abstain_entity_not_found×3, graph_R4:abstain_entity_not_found×3, rdb_해외ETF:skipped×3 | E×3 UNSUPPORTED_INFERENCE×3 |
| Q24 | 에코프로의 자회사를 편입한 ETF를 찾고 그중 최신 AUM이 가장 큰 | 외부데이터필요 | graph_then_rdb+vector | △(2/3) | 30,841 | 38,439 | 13,988 | 0 | 99 | 11,355 | 683 | 4,798 | 6 | graph_R3:abstain_evidence_missing×3, rdb_국내ETF:0행×2, vector_narrative:0행×1 | E×1 GENERATION_OMISSION×1 |
| Q25 | 국민성장펀드의 구조, 운용주체, 자금조달 방식과 최근 투자전략 동향을 | 부분산출 | rdb_only+vector | X(0/3) | 19,520 | 21,333 | 8,941 | 0 | 0 | 10,124 | 258 | 0 | 5 | rdb_펀드:0행×3, vector_narrative:0행×3 | C×3 FILTER_ERROR×3, RETRIEVAL_MISS×3 |
| Q26 | SK하이닉스가 발행한 매수 가능 채권과 SK하이닉스를 편입한 ETF· | 부분산출 | graph_then_rdb+vector | X(0/3) | 176,711 | 188,884 | 20,398 | 0 | 108,237 | 46,336 | 1,601 | 1,882 | 15 | vector_narrative:0행×3, graph_R1:abstain_evidence_missing×2, graph_R2:abstain_entity_not_found×2, graph_R3:abstain_evidence_missing×2 | C×3 GENERATION_OMISSION×3, RETRIEVAL_MISS×2, UNSUPPORTED_INFERENCE×2 |
| Q27 | LG에너지솔루션 및 확인된 자회사가 발행한 채권과 이 기업들을 편입한 | 부분산출 | graph_then_rdb+vector | X(0/3) | 96,790 | 113,719 | 16,561 | 0 | 54,412 | 23,106 | 1,595 | 4,976 | 11 | graph_R3:abstain_entity_not_found×3, graph_R4:abstain_evidence_missing×3, vector_narrative:0행×3, graph_R2:abstain_invalid_graph_plan×2 | C×3 GENERATION_OMISSION×3, RETRIEVAL_MISS×3 |
| Q28 | 엔비디아를 편입한 국내 ETF와 해외 ETF 중 순자산이 큰 상품을  | 외부데이터필요 | graph_then_rdb+vector | △(1/3) | 41,996 | 46,948 | 13,625 | 0 | 610 | 21,363 | 1,188 | 3,569 | 7 | rdb_해외ETF:0행×3, vector_narrative:0행×1, rdb_국내ETF:error×1 | C×1/E×1 FILTER_ERROR×1, UNGROUNDED_CLAIM×1, UNSUPPORTED_INFERENCE×1 |
| Q29 | VOO, IVV, SPY가 같은 S&P 500 계열 지수를 추종하는지 | 부분산출 | graph_then_rdb+vector | X(0/3) | 37,014 | 38,356 | 12,561 | 0 | 13,998 | 10,671 | 279 | 0 | 5 | graph_R1:abstain_entity_not_found×3, rdb_국내ETF:0행×3, vector_narrative:0행×3 | D×3 GENERATION_OMISSION×3, RETRIEVAL_MISS×3, ROUTING_MISS×3 |
| Q30 | 우리반도체BIG2플러스 펀드와 국내 반도체 ETF의 실제 편입종목 중 | 외부데이터필요 | rdb_only+vector | X(0/3) | 39,369 | 47,348 | 8,785 | 0 | 0 | 25,887 | 1,212 | 2,698 | 9 | rdb_국내ETF:error×1 | C×3 FILTER_ERROR×3, GENERATION_OMISSION×3 |
| Q31 | 신용등급이 AAAA인 매수 가능 채권을 찾아 상품번호와 신용평가 근거 | ABSTAIN | rdb_only | X(0/3) | 11,065 | 11,134 | 9,223 | 0 | 0 | 1,686 | 0 | 0 | 3 | rdb_채권:skipped×3 | E×3 MISSING_EVIDENCE×3 |
| Q32 | 2026-08-24 기준으로 Kimi 관련 투자 상품을 찾아 해당 모 | ABSTAIN | rdb_only | △(1/3) | 26,418 | 28,308 | 6,585 | 0 | 0 | 15,905 | 0 | 0 | 7 | rdb_펀드:0행×2, graph_R1:abstain_entity_not_found×1 | D×2 MISSING_EVIDENCE×2 |
| Q33 | KODEX AI로봇 ETF의 수익률과 편입종목을 공식 문서 근거로 알 | ABSTAIN | rdb_only+vector | X(0/3) | 14,886 | 15,713 | 6,710 | 0 | 0 | 8,151 | 254 | 0 | 5 | rdb_국내ETF:0행×3, vector_narrative:0행×3 | D×3 MISSING_EVIDENCE×3 |
| Q34 | TIGER 미국S&P500의 2027년 확정 연간수익률을 데이터 근거 | ABSTAIN | rdb_only+vector | △(1/3) | 16,011 | 18,275 | 6,607 | 0 | 0 | 8,538 | 342 | 0 | 5 | vector_narrative:0행×3, rdb_해외ETF:0행×2 | D×2 MISSING_EVIDENCE×2 |
| Q35 | VOO가 직접 발행한 회사채의 신용등급과 만기일을 알려줘. | ABSTAIN | graph+rdb(parallel) | X(0/3) | 23,976 | 46,803 | 6,711 | 0 | 16,202 | 6,429 | 0 | 1,786 | 5 | graph_R1:abstain_entity_not_found×3 | D×3 MISSING_EVIDENCE×3 |

### 표 2. 루브릭 유형별

| 유형 | 문항수 | 채점 회차 | 정답 회차 | 오답률 % | 평균 E2E ms | 최다 오답 원인 | 최다 실패코드 |
|---|---:|---:|---:|---:|---:|---|---|
| 산출가능 | 14 | 41 | 9 | 78.0 | 31,339 | C | GENERATION_OMISSION |
| 부분산출 | 10 | 30 | 0 | 100.0 | 61,277 | C | RETRIEVAL_MISS |
| 외부데이터필요 | 4 | 12 | 4 | 66.7 | 45,056 | E | GENERATION_OMISSION |
| 정의변경 | 2 | 6 | 0 | 100.0 | 32,977 | C | STALE_DEFINITION |
| ABSTAIN | 5 | 15 | 2 | 86.7 | 19,924 | D | MISSING_EVIDENCE |

### 표 3. 계층별 병목 (warm ok 회차)

| 계층 | 평균 기여 ms | p95 기여 ms | E2E 기여율 % | 타는 질의 비율 | 원인 오답 수 | 시간축 점수 | 품질축 점수 | 시간 순위 | 품질 순위 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GraphDB | 43,560 | 117,593 | 30.2 | 0.29 | 0 | 33,598 | 0.00 | 1 | 2 |
| RDB | 14,131 | 27,333 | 35.4 | 1.00 | 52 | 27,333 | 0.58 | 2 | 1 |
| VectorDB | 1,114 | 2,280 | 1.4 | 0.54 | 0 | 1,237 | 0.00 | 3 | 3 |
| query_frame(LLM) | 10,432 | 19,598 | 26.1 | 1.00 | 0 | 19,598 | 0.00 | - | - |
| generate(LLM) | 4,451 | 9,680 | 7.3 | 0.77 | 12 | 7,468 | 0.13 | - | - |
| plan/route_guard | 1 | 1 | 0.0 | 0.03 | 22 | 0 | 0.25 | - | - |

### 질의별 단계 누적 시간 (warm 중앙값, 1칸=1초)

| ID | frame | rdb | graph | vector | generate | E2E p50 s | 막대 (F=frame R=rdb G=graph V=vector A=generate) |
|---|---:|---:|---:|---:|---:|---:|---|
| Q1 | 9,159 | 12,875 | 0 | 1,222 | 2,734 | 24.7 | `FFFFFFFFFRRRRRRRRRRRRRVAAA` |
| Q2 | 6,782 | 10,723 | 0 | 0 | 3,442 | 21.0 | `FFFFFFFRRRRRRRRRRRAAA` |
| Q3 | 12,132 | 1,011 | 0 | 1,035 | 0 | 14.8 | `FFFFFFFFFFFFRV` |
| Q4 | 8,340 | 9,926 | 0 | 0 | 1,622 | 19.4 | `FFFFFFFFRRRRRRRRRRAA` |
| Q5 | 7,265 | 10,155 | 0 | 1,618 | 3,551 | 24.0 | `FFFFFFFRRRRRRRRRRVVAAAA` |
| Q6 | 6,958 | 11,531 | 0 | 0 | 0 | 20.4 | `FFFFFFFRRRRRRRRRRRR` |
| Q7 | 6,700 | 18,041 | 0 | 284 | 0 | 25.1 | `FFFFFFFRRRRRRRRRRRRRRRRRR` |
| Q8 | 11,103 | 11,748 | 0 | 0 | 3,837 | 26.7 | `FFFFFFFFFFFRRRRRRRRRRRRAAAA` |
| Q9 | 6,538 | 10,051 | 0 | 1,023 | 2,706 | 19.8 | `FFFFFFFRRRRRRRRRRVAAA` |
| Q10 | 13,655 | 14,729 | 107,584 | 1,146 | 3,550 | 140.8 | `FFFFFFFFFFFFFFRRRRRRRRRRRRRRRGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGVAAAA` |
| Q11 | 12,474 | 9,993 | 0 | 0 | 7,313 | 29.8 | `FFFFFFFFFFFFRRRRRRRRRRAAAAAAA` |
| Q12 | 13,555 | 10,743 | 0 | 0 | 0 | 24.5 | `FFFFFFFFFFFFFFRRRRRRRRRRR` |
| Q13 | 12,372 | 14,972 | 0 | 0 | 8,776 | 36.1 | `FFFFFFFFFFFFRRRRRRRRRRRRRRRAAAAAAAAA` |
| Q14 | 7,491 | 10,088 | 0 | 0 | 7,031 | 24.6 | `FFFFFFFRRRRRRRRRRAAAAAAA` |
| Q15 | 11,207 | 10,033 | 0 | 0 | 0 | 22.7 | `FFFFFFFFFFFRRRRRRRRRR` |
| Q16 | 7,897 | 13,568 | 0 | 1,735 | 7,047 | 30.3 | `FFFFFFFFRRRRRRRRRRRRRRVVAAAAAAA` |
| Q17 | 8,895 | 13,021 | 0 | 0 | 0 | 22.3 | `FFFFFFFFFRRRRRRRRRRRRR` |
| Q18 | 8,656 | 12,311 | 0 | 0 | 9,148 | 29.9 | `FFFFFFFFFRRRRRRRRRRRRAAAAAAAAA` |
| Q19 | 11,644 | 11,860 | 0 | 0 | 0 | 23.6 | `FFFFFFFFFFFFRRRRRRRRRRRR` |
| Q20 | 8,681 | 18,455 | 0 | 2,299 | 4,564 | 34.8 | `FFFFFFFFFRRRRRRRRRRRRRRRRRRVVAAAAA` |
| Q21 | 7,811 | 21,182 | 0 | 1,848 | 3,168 | 34.0 | `FFFFFFFFRRRRRRRRRRRRRRRRRRRRRVVAAA` |
| Q22 | 9,514 | 10,763 | 14,171 | 0 | 1,623 | 40.3 | `FFFFFFFFFFRRRRRRRRRRRGGGGGGGGGGGGGGAA` |
| Q23 | 20,780 | 27,265 | 91,743 | 0 | 7,644 | 146.0 | `FFFFFFFFFFFFFFFFFFFFFRRRRRRRRRRRRRRRRRRRRRRRRRRRGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGAAAAAAAA` |
| Q24 | 13,988 | 11,355 | 99 | 683 | 4,798 | 30.8 | `FFFFFFFFFFFFFFRRRRRRRRRRRVAAAAA` |
| Q25 | 8,941 | 10,124 | 0 | 258 | 0 | 19.5 | `FFFFFFFFFRRRRRRRRRR` |
| Q26 | 20,398 | 46,336 | 108,237 | 1,601 | 1,882 | 176.7 | `FFFFFFFFFFFFFFFFFFFFRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGVVAA` |
| Q27 | 16,561 | 23,106 | 54,412 | 1,595 | 4,976 | 96.8 | `FFFFFFFFFFFFFFFFFRRRRRRRRRRRRRRRRRRRRRRRGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGVVAAAAA` |
| Q28 | 13,625 | 21,363 | 610 | 1,188 | 3,569 | 42.0 | `FFFFFFFFFFFFFFRRRRRRRRRRRRRRRRRRRRRGVAAAA` |
| Q29 | 12,561 | 10,671 | 13,998 | 279 | 0 | 37.0 | `FFFFFFFFFFFFFRRRRRRRRRRRGGGGGGGGGGGGGG` |
| Q30 | 8,785 | 25,887 | 0 | 1,212 | 2,698 | 39.4 | `FFFFFFFFFRRRRRRRRRRRRRRRRRRRRRRRRRRVAAA` |
| Q31 | 9,223 | 1,686 | 0 | 0 | 0 | 11.1 | `FFFFFFFFFRR` |
| Q32 | 6,585 | 15,905 | 0 | 0 | 0 | 26.4 | `FFFFFFFRRRRRRRRRRRRRRRR` |
| Q33 | 6,710 | 8,151 | 0 | 254 | 0 | 14.9 | `FFFFFFFRRRRRRRR` |
| Q34 | 6,607 | 8,538 | 0 | 342 | 0 | 16.0 | `FFFFFFFRRRRRRRRR` |
| Q35 | 6,711 | 6,429 | 16,202 | 0 | 1,786 | 24.0 | `FFFFFFFRRRRRRGGGGGGGGGGGGGGGGAA` |

### 루브릭 유형별 오답률 (1칸=5%)

| 유형 | 오답률 % | 막대 |
|---|---:|---|
| 산출가능 | 78.0 | `████████████████` |
| 부분산출 | 100.0 | `████████████████████` |
| 외부데이터필요 | 66.7 | `█████████████` |
| 정의변경 | 100.0 | `████████████████████` |
| ABSTAIN | 86.7 | `█████████████████` |