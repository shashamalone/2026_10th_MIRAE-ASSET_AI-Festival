# -*- coding: utf-8 -*-
"""Full Text Search 실측 — 이번 검증의 핵심.

PostgreSQL 기본 배포에는 한국어 형태소 분석기(korean 설정)가 없다.
'simple' 은 공백·구두점으로만 자르고, 'english' 는 거기에 라틴 문자용 스테머와
불용어를 얹을 뿐이라 한국어에는 아무 효과가 없다. 그 결과를 어절/조사/부분어별로
못박아 둔다. 나중에 누가 '한국어 FTS 되더라' 라고 하면 이 테스트가 반증한다.
"""
import search
from checks import check, finish

print("test_keyword_search  (simple vs english vs pg_trgm)")
conn = search.connect()


def keys(rows):
    return [r["doc_key"] for r in rows]


def probe(q):
    return (keys(search.keyword_search(conn, q, cfg="simple")),
            keys(search.keyword_search(conn, q, cfg="english")))


print("\n  [매트릭스]  질의 -> simple / english / trigram")
for q in ["barking dog", "barking dogs", "듀레이션", "위험등급", "금리 민감도",
          "듀레이션이 뭐야?", "듀레이션이", "등급", "채권 이자율"]:
    s, e = probe(q)
    t = keys(search.trigram_search(conn, q, threshold=0.3))
    print(f"    {q:16} | simple={s or '없음'} | english={e or '없음'} | trgm={t or '없음'}")

print("\n  [1] 정확 어절 한국어 질의 — FTS 가 잡아야 정상")
for q, exp in [("듀레이션", "fp:duration"),
               ("위험등급", "fp:riskGradeLevel"),
               ("금리 민감도", "fp:duration")]:
    s, e = probe(q)
    check(f"'{q}' simple 적중", exp in s, str(s))
    check(f"'{q}' english 적중", exp in e, str(e))

print("\n  [2] 조사 결합 질의 — 한국어 FTS 의 최대 약점")
for q in ["듀레이션이", "듀레이션이 뭐야?"]:
    s, e = probe(q)
    check(f"'{q}' simple 무적중(한계 확인)", s == [], str(s))
    check(f"'{q}' english 무적중(한계 확인)", e == [], str(e))

print("\n  [3] 부분어(복합명사 내부) — '등급' ⊂ '위험등급'")
s, e = probe("등급")
check("'등급' simple 무적중(한계 확인)", s == [], str(s))
check("'등급' english 무적중(한계 확인)", e == [], str(e))

print("\n  [4] 어휘 불일치(동의어) — '이자율' vs 원문 '표면금리'")
s, e = probe("채권 이자율")
check("'채권 이자율' simple 무적중", s == [], str(s))
check("'채권 이자율' english 무적중", e == [], str(e))

print("\n  [5] english 설정은 한국어에 아무 이득이 없다")
same = all(probe(q)[0] == probe(q)[1] for q in
           ["듀레이션", "위험등급", "금리 민감도", "듀레이션이", "등급", "채권 이자율"])
check("모든 한국어 질의에서 simple == english", same)
s_en, e_en = probe("barking dogs")
check("영문에서는 english 스테머가 실제로 이득 ('dogs'->'dog')",
      s_en == [] and "en:dog" in e_en, f"simple={s_en} english={e_en}")

print("\n  [6] pg_trgm 폴백 — 재현율은 살리지만 정밀도는 못 준다")
check("'등급' trgm 회수", "fp:riskGradeLevel" in keys(search.trigram_search(conn, "등급", threshold=0.3)))
check("'듀레이션이' trgm 회수", "fp:duration" in keys(search.trigram_search(conn, "듀레이션이", threshold=0.3)))
t = keys(search.trigram_search(conn, "채권 이자율", threshold=0.3))
check("'채권 이자율' trgm 은 오답을 1위로 (정밀도 한계 확인)",
      t and t[0] != "fp:couponRate", f"trgm 1위={t[0] if t else '없음'} / 정답=fp:couponRate")

finish("test_keyword_search")
