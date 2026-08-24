#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Query Frame v1 검증 하네스.

채움률은 검증이 아니다. "entities 22/35" 는 실패가 아니라 엔티티가 없는 질문이
13개라는 뜻일 수 있다. 그래서 gold 에 슬롯별 필요 여부를 먼저 적어두고
**필요한 질문에서 채워졌는가(Recall) + 필요 없는 질문에서 안 만들었는가(Precision)**
를 잰다. 채움률은 보조 통계로만 찍는다.

    python3 eval_query_frame.py --check-gold          # 네트워크 없이 gold 무결성만
    python3 eval_query_frame.py --model HCX-007       # 영역 1~3
    python3 eval_query_frame.py --ambiguous           # 영역 4 (모호 세트)
    python3 eval_query_frame.py --downstream          # 영역 5 (TBox A/B, pgvector 필요)
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))
import clova  # noqa: E402
import query_frame as qf  # noqa: E402

GOLD = HERE / "gold"
RESULTS = HERE / "results"
A3 = ROOT / "vectordb_test" / "action3_semantic_schema" / "gold"

# ── 텍스트 매칭 ────────────────────────────────────────────────────────────
# 한국어 자연어를 exact match 로 채점하면 표현 차이로 전부 틀린다. gold 는 별칭
# 배열을 허용하고, 매칭은 정규화 후 완전일치 → 부분일치 두 단계로 본다.
_PUNCT = re.compile(r"""[\s()\[\]{}·・,'"’“”]""")


def norm(s) -> str:
    return _PUNCT.sub("", str(s if s is not None else "")).lower()


def aliases(v) -> list:
    return list(v) if isinstance(v, list) else [v]


def hit(pred, gold, loose: bool) -> bool:
    p, gs = norm(pred), [norm(g) for g in aliases(gold) if g is not None]
    if not p:
        return False
    if p in gs:
        return True
    return loose and len(p) >= 2 and any(g and (g in p or p in g) for g in gs)


def pair(preds: list, golds: list, pkey, gkey) -> list[tuple[int, int]]:
    """gold ↔ pred 1:1 대응. 완전일치를 먼저 소진한 뒤 부분일치를 붙인다."""
    taken, out = set(), []
    for loose in (False, True):
        for gi, g in enumerate(golds):
            if any(gi == a for a, _ in out):
                continue
            for pi, p in enumerate(preds):
                if pi in taken:
                    continue
                if hit(pkey(p), gkey(g), loose):
                    out.append((gi, pi))
                    taken.add(pi)
                    break
    return out


class Tally:
    """슬롯 하나의 누적 집계. gold 가 0인 질문에서 생긴 예측은 전부 false positive 다."""

    def __init__(self, name):
        self.name, self.tp, self.gold, self.pred, self.skipped = name, 0, 0, 0, 0
        self.misses, self.fps = [], []

    def add(self, qid, tp, gold_n, pred_n, missing=(), fp=()):
        self.tp += tp
        self.gold += gold_n
        self.pred += pred_n
        self.misses += [(qid, m) for m in missing]
        self.fps += [(qid, f) for f in fp]

    @property
    def recall(self):
        return self.tp / self.gold if self.gold else None

    @property
    def precision(self):
        return self.tp / self.pred if self.pred else None

    def row(self):
        r, p = self.recall, self.precision
        f = lambda x: "  —  " if x is None else f"{x*100:5.1f}%"  # noqa: E731
        return (f"  {self.name:<20} gold {self.gold:>3}  pred {self.pred:>3}  "
                f"맞음 {self.tp:>3}  누락 {self.gold-self.tp:>2}  오생성 {self.pred-self.tp:>2}   "
                f"R {f(r)}  P {f(p)}" + (f"   (채점제외 {self.skipped})" if self.skipped else ""))


class Exact:
    """단일값 슬롯(task·limit·temporal). 정확도 하나만 본다."""

    def __init__(self, name):
        self.name, self.ok, self.n, self.skipped, self.bad = name, 0, 0, 0, []

    def add(self, qid, got, want):
        if want == "__skip__":
            self.skipped += 1
            return
        self.n += 1
        if (got in aliases(want)) if isinstance(want, list) else (got == want):
            self.ok += 1
        else:
            self.bad.append((qid, got, want))

    @property
    def acc(self):
        return self.ok / self.n if self.n else None

    def row(self):
        a = self.acc
        return (f"  {self.name:<20} {self.ok:>3}/{self.n:<3} "
                f"{'  —  ' if a is None else f'{a*100:5.1f}%'}"
                + (f"   (채점제외 {self.skipped})" if self.skipped else ""))


def load_gold():
    rows = [json.loads(l) for l in (GOLD / "gold_frames.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    return {r["question_id"]: r for r in rows}


def load_questions():
    qs = json.loads((A3 / "expected_queries_35.json").read_text(encoding="utf-8"))["questions"]
    return {f"q{int(q['id']):03d}": q for q in qs}


def load_ambiguous():
    return [json.loads(l) for l in (GOLD / "ambiguous_queries.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


# ── 영역 0: gold 무결성 (LLM 호출 없음) ─────────────────────────────────────
def check_gold() -> int:
    gold, qs, bad = load_gold(), load_questions(), []
    ids = sorted(gold)
    if ids != [f"q{i:03d}" for i in range(1, 36)]:
        bad.append(f"question_id 가 q001~q035 연속이 아니다: {ids}")

    enum_of = {"task": qf.TASKS, "temporal_kind": qf.TEMPORAL_KINDS}
    for qid, g in gold.items():
        for k, allowed in enum_of.items():
            for v in aliases(g.get(k)):
                if v not in allowed:
                    bad.append(f"{qid}.{k} enum 밖: {v!r}")
        for d in g.get("domain_candidates") or []:
            if d not in qf.DOMAINS:
                bad.append(f"{qid}.domain_candidates enum 밖: {d!r}")
        for c in g.get("computation") or []:
            if c not in qf.COMPUTATION_KINDS:
                bad.append(f"{qid}.computation enum 밖: {c!r}")
        for v in g.get("validation_targets") or []:
            if v["type"] not in qf.VALIDATION_TYPES:
                bad.append(f"{qid}.validation_targets enum 밖: {v['type']!r}")
        for a in g.get("ambiguity") or []:
            for t in aliases(a.get("type")):
                if t not in qf.AMBIGUITY_TYPES:
                    bad.append(f"{qid}.ambiguity enum 밖: {t!r}")
        for c in g.get("constraints") or []:
            for op in aliases(c.get("operator")):
                if op not in qf.OPERATORS:
                    bad.append(f"{qid}.constraints operator enum 밖: {op!r}")
        for o in g.get("ordering") or []:
            if o["direction"] not in qf.DIRECTIONS:
                bad.append(f"{qid}.ordering direction enum 밖: {o['direction']!r}")
        for slot in g.get("_optional") or []:
            if slot not in qf.SCORED_SLOTS:
                bad.append(f"{qid}._optional 이 채점 슬롯이 아니다: {slot!r}")
        # gold 의 원문 조각이 실제 질문에 있는지 — 오타로 매칭이 통째로 죽는 걸 막는다
        qtext = norm(qs[qid]["question"])
        for c in g.get("constraints") or []:
            if c.get("value_text") and not any(norm(v) in qtext for v in aliases(c["value_text"])):
                bad.append(f"{qid} constraint value_text 가 질문에 없다: {c['value_text']!r}")

    # 독립 gold(gold_nl2sql.json)와 limit 대조 — 두 손으로 적은 값이 어긋나면 한쪽이 틀렸다
    ref = json.loads((A3 / "gold_nl2sql.json").read_text(encoding="utf-8"))
    ref = ref["questions"] if isinstance(ref, dict) else ref
    for q in ref:
        want, got = q.get("required_limit"), gold[q["question_id"]]["limit"]
        if want != got:
            bad.append(f"{q['question_id']} limit 불일치: gold_frames={got} vs gold_nl2sql={want}")

    amb = load_ambiguous()
    for a in amb:
        for sp in a["spans"]:
            if not any(norm(s) in norm(a["question"]) for s in aliases(sp)):
                bad.append(f"{a['question_id']} span 이 질문에 없다: {sp!r}")

    print(f"gold_frames.jsonl        {len(gold)}행")
    print(f"ambiguous_queries.jsonl  {len(amb)}행")
    req = {s: sum(1 for g in gold.values() if g.get(s) not in (None, [], {})) for s in
           ["targets", "entities", "constraints", "relations", "ordering",
            "computation", "ambiguity", "validation_targets"]}
    print("  슬롯별 gold required 문항 수:", ", ".join(f"{k} {v}" for k, v in req.items()))
    print(f"  limit 지정 문항: {sum(1 for g in gold.values() if g['limit'])}")
    if bad:
        print(f"\nFAIL  {len(bad)}건")
        for b in bad:
            print("   -", b)
        return 1
    print("\ncheck-gold PASS")
    return 0


# ── 영역 1: 구조 유효성 — 보정 전 원본으로 잰다 ─────────────────────────────
_ENUM_AT = {"task": qf.TASKS, "domain_candidates": qf.DOMAINS}
_ITEM_ENUM = {"entities": {"role": qf.ENTITY_ROLES, "match_mode": qf.MATCH_MODES},
              "constraints": {"operator": qf.OPERATORS, "kind": qf.CONSTRAINT_KINDS,
                              "grounding_status": qf.GROUNDING},
              "ordering": {"direction": qf.DIRECTIONS},
              "computation": {"kind": qf.COMPUTATION_KINDS},
              "ambiguity": {"type": qf.AMBIGUITY_TYPES},
              "validation_targets": {"type": qf.VALIDATION_TYPES}}


def structure_errors(raw: dict) -> list[str]:
    if not isinstance(raw, dict):
        return ["최상위가 객체가 아님"]
    errs = [f"필수 필드 누락: {f}" for f in qf.FIELDS if f not in raw]
    for k, allowed in _ENUM_AT.items():
        for v in ([raw[k]] if k == "task" else raw.get(k) or []) if k in raw else []:
            if v not in allowed:
                errs.append(f"{k} enum 밖: {v!r}")
    for slot, spec in _ITEM_ENUM.items():
        for it in raw.get(slot) or []:
            if not isinstance(it, dict):
                errs.append(f"{slot} 항목이 객체가 아님: {it!r}")
                continue
            for key, allowed in spec.items():
                if key in it and it[key] not in allowed:
                    errs.append(f"{slot}.{key} enum 밖: {it[key]!r}")
    t = raw.get("temporal")
    if not isinstance(t, dict):
        errs.append("temporal 이 객체가 아님")
    elif t.get("kind") not in qf.TEMPORAL_KINDS:
        errs.append(f"temporal.kind enum 밖: {t.get('kind')!r}")
    lim = raw.get("limit")
    if lim is not None and not isinstance(lim, int):
        errs.append(f"limit 이 정수/null 이 아님: {lim!r}")
    for c in raw.get("constraints") or []:
        if isinstance(c, dict) and c.get("value_num") is not None \
                and not isinstance(c["value_num"], (int, float)):
            errs.append(f"constraints.value_num 이 수치가 아님: {c['value_num']!r}")
    return errs


# ── 영역 2·3: 슬롯 정확도 + 의미 보존 ───────────────────────────────────────
def _ignored(text, ignore) -> bool:
    # 완전일치만. 부분일치로 두면 _ignore 한 낱말이 그 말을 품은 정상 예측까지 삼킨다.
    return any(hit(text, [tok], False) for tok in ignore)


def score_one(qid, g, f, T, E):
    """gold g 와 예측 f 를 대조해 집계기 T(Tally)·E(Exact)에 넣는다."""
    opt = set(g.get("_optional") or [])
    ign = g.get("_ignore") or []

    # domain_candidates — 집합 R/P
    if "domain_candidates" in opt:
        T["domain_candidates"].skipped += 1
    else:
        gd, pd_ = set(g["domain_candidates"]), set(f["domain_candidates"])
        T["domain_candidates"].add(qid, len(gd & pd_), len(gd), len(pd_),
                                   sorted(gd - pd_), sorted(pd_ - gd))

    E["task"].add(qid, f["task"], "__skip__" if "task" in opt else g["task"])
    E["limit"].add(qid, f["limit"], "__skip__" if "limit" in opt else g["limit"])
    E["temporal"].add(qid, f["temporal"]["kind"],
                      "__skip__" if "temporal" in opt else g["temporal_kind"])

    # targets / entities — 텍스트 슬롯
    for slot, gkey in (("targets", lambda x: x), ("entities", lambda x: x["text"])):
        if slot in opt:
            T[slot].skipped += 1
            continue
        golds = g[slot]
        preds = [p for p in f[slot] if not _ignored(p["text"], ign)]
        m = pair(preds, golds, lambda p: p["text"], gkey)
        T[slot].add(qid, len(m), len(golds), len(preds),
                    [gkey(golds[i]) for i in range(len(golds)) if i not in {a for a, _ in m}],
                    [preds[i]["text"] for i in range(len(preds)) if i not in {b for _, b in m}])
        if slot == "entities":
            for gi, pi in m:
                want = golds[gi].get("role")
                if want is not None:
                    E["entity role"].add(qid, preds[pi]["role"], want)

    # constraints — field_text 로 짝짓고 operator/value/unit 은 의미 보존으로 따로 잰다
    if "constraints" in opt:
        T["constraints"].skipped += 1
    else:
        golds = [c for c in g["constraints"] if not c.get("_optional")]
        soft = [c for c in g["constraints"] if c.get("_optional")]
        preds = [p for p in f["constraints"] if not _ignored(p["field_text"], ign)]
        m = pair(preds, golds, lambda p: p["field_text"], lambda c: c["field_text"])
        used = {b for _, b in m}
        # 선택 constraint 에 맞은 예측은 오생성으로 치지 않는다
        leftover = [i for i in range(len(preds)) if i not in used]
        for c in soft:
            for i in list(leftover):
                if hit(preds[i]["field_text"], c["field_text"], True):
                    leftover.remove(i)
                    break
        T["constraints"].add(qid, len(m), len(golds), len(preds) - (len(preds) - len(used) - len(leftover)),
                             [golds[i]["field_text"] for i in range(len(golds)) if i not in {a for a, _ in m}],
                             [preds[i]["field_text"] for i in leftover])
        for gi, pi in m:
            gc, pc = golds[gi], preds[pi]
            E["operator"].add(qid, pc["operator"], gc["operator"])
            if gc.get("value_text") is not None:
                E["value"].add(qid, norm(pc["value_text"]), [norm(v) for v in aliases(gc["value_text"])])
            elif gc.get("value_num") is not None:
                E["value"].add(qid, pc["value_num"], aliases(gc["value_num"]))
            if "unit" in gc:
                E["unit"].add(qid, pc["unit"], gc["unit"])

    # relations — 경로 표현이 흔들리므로 (a) 존재 여부 (b) 양 끝 개체 두 단계로 본다
    if "relations" in opt:
        T["relations"].skipped += 1
    else:
        gh, ph = bool(g["relations"]), bool(f["relations"])
        T["relations"].add(qid, int(gh and ph), int(gh), int(ph),
                           ["관계 필요한데 없음"] if gh and not ph else [],
                           [" → ".join(r["path"]) for r in f["relations"]] if ph and not gh else [])
        if gh and ph:
            ok = any(hit(p["path"][0], gr["path_first"], True) and hit(p["path"][-1], gr["path_last"], True)
                     for gr in g["relations"] for p in f["relations"] if p["path"])
            E["relation 양끝"].add(qid, ok, True)

    # ordering — field_text 짝짓고 방향은 따로
    if "ordering" in opt:
        T["ordering"].skipped += 1
    else:
        golds, preds = g["ordering"], f["ordering"]
        m = pair(preds, golds, lambda p: p["field_text"], lambda o: o["field_text"])
        T["ordering"].add(qid, len(m), len(golds), len(preds),
                          [golds[i]["field_text"] for i in range(len(golds)) if i not in {a for a, _ in m}],
                          [preds[i]["field_text"] for i in range(len(preds)) if i not in {b for _, b in m}])
        for gi, pi in m:
            E["sort direction"].add(qid, preds[pi]["direction"], golds[gi]["direction"])

    # 집합 슬롯 — 종류만 본다
    for slot, gset, pset in (
            ("computation", set(g["computation"]), {c["kind"] for c in f["computation"]}),
            ("ambiguity", {a for x in g["ambiguity"] for a in aliases(x["type"])[:1]},
             {a["type"] for a in f["ambiguity"]}),
            ("validation_targets", {v["type"] for v in g["validation_targets"]},
             {v["type"] for v in f["validation_targets"]})):
        if slot in opt:
            T[slot].skipped += 1
            continue
        if slot == "ambiguity" and g["ambiguity"]:
            allowed = {a for x in g["ambiguity"] for a in aliases(x["type"])}
            tp = len(pset & allowed)
            T[slot].add(qid, min(tp, len(gset)), len(gset), len(pset),
                        [] if tp else sorted(gset), sorted(pset - allowed))
            continue
        T[slot].add(qid, len(gset & pset), len(gset), len(pset),
                    sorted(gset - pset), sorted(pset - gset))


# ── 실행 ───────────────────────────────────────────────────────────────────
def call(question: str, model: str, tries: int = 8, use_audit: bool = False) -> tuple[dict, float]:
    """429 는 분 단위 쿼터라 지수 백오프로 기다린다. 그 외 오류는 그대로 올린다."""
    for a in range(tries):
        t0 = time.time()
        try:
            return qf.extract(question, model=model, use_audit=use_audit), time.time() - t0
        except Exception as e:
            if "429" not in str(e) and "42901" not in str(e):
                raise
            wait = min(2 ** a, 65)
            print(f"    429 — {wait}s 대기", flush=True)
            time.sleep(wait)
    raise RuntimeError("429 재시도 실패")


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round((len(xs) - 1) * p)))] if xs else float("nan")


def run_35(model: str, only=None, use_audit: bool = False) -> dict:
    gold, qs = load_gold(), load_questions()
    ids = [i for i in sorted(qs) if not only or i in only]
    frames, lat, errors = {}, [], {}
    for n, qid in enumerate(ids, 1):
        try:
            f, dt = call(qs[qid]["question"], model, use_audit=use_audit)
        except Exception as e:
            errors[qid] = f"{type(e).__name__}: {e}"
            print(f"  [{n}/{len(ids)}] {qid}  FAIL  {errors[qid][:90]}", flush=True)
            continue
        frames[qid], _ = f, lat.append(dt)
        g = f.get("_guard") or []
        print(f"  [{n}/{len(ids)}] {qid}  {dt:5.2f}s  "
              f"dom={','.join(f['domain_candidates']) or '-':<22} task={f['task']:<14} "
              f"c={len(f['constraints'])} r={len(f['relations'])} v={len(f['validation_targets'])}"
              + (f"  guard {len(g)}" if g else ""), flush=True)

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"frames_{model}{'_audit' if use_audit else ''}.jsonl"
    out.write_text("".join(json.dumps({"question_id": k, **v}, ensure_ascii=False) + "\n"
                           for k, v in frames.items()), encoding="utf-8")
    print(f"\n원시 출력 → {out.relative_to(ROOT)}  ({len(frames)}건)")
    return report(model, gold, qs, frames, lat, errors, n_expected=len(ids))


def report(model, gold, qs, frames, lat, errors, n_expected=None) -> dict:
    n_total = n_expected or len(gold)
    print(f"\n{'='*94}\nQuery Frame v1 스코어카드 — {model} (schema {qf.SCHEMA_VERSION})\n{'='*94}")

    # 영역 1 ────────────────────────────────────────────────────────────────
    parsed = len(frames)
    struct_bad, leak_bad = {}, {}
    for qid, f in frames.items():
        e = structure_errors(f.get("_raw") or {})
        if e:
            struct_bad[qid] = e
        lk = qf.leaks(f)
        if lk:
            leak_bad[qid] = lk
    ok_struct = parsed - len(struct_bad)
    print(f"\n[영역 1] 구조 유효성 — 통과기준 {n_total}/{n_total}")
    print(f"  JSON parse 성공        {parsed}/{n_total}" + ("  ← FAIL" if parsed < n_total else ""))
    print(f"  스키마 준수(보정 전)    {ok_struct}/{n_total}" + ("  ← FAIL" if ok_struct < n_total else ""))
    print(f"  TBox 누출(fp:·물리컬럼) {len(leak_bad)}건" + ("  ← FAIL" if leak_bad else ""))
    for qid, e in list(struct_bad.items())[:8]:
        print(f"     {qid}: {'; '.join(e[:3])}")
    for qid, lk in leak_bad.items():
        print(f"     {qid} 누출: {lk}")
    for qid, e in errors.items():
        print(f"     {qid} 호출실패: {e[:100]}")

    # 영역 2·3 ──────────────────────────────────────────────────────────────
    T = {s: Tally(s) for s in ["domain_candidates", "targets", "entities", "constraints",
                               "relations", "ordering", "computation", "ambiguity",
                               "validation_targets"]}
    E = {s: Exact(s) for s in ["task", "limit", "temporal", "entity role", "operator",
                               "value", "unit", "sort direction", "relation 양끝"]}
    for qid, f in frames.items():
        score_one(qid, gold[qid], f, T, E)

    print(f"\n[영역 2] Applicability-aware Slot Accuracy — 통과기준 R·P ≥ 95%")
    for s in T:
        print(T[s].row())
    print(f"\n[영역 3] Semantic Preservation — operator 는 100%, 나머지 ≥95%")
    for s in ["task", "operator", "value", "unit", "sort direction", "limit",
              "temporal", "entity role", "relation 양끝"]:
        print(E[s].row())

    # 영역 4(35문항 쪽) ──────────────────────────────────────────────────────
    abstain = [q for q in frames if gold[q]["validation_targets"]]
    answerable = [q for q in frames if not gold[q]["validation_targets"]]
    v_rec = sum(1 for q in abstain if frames[q]["validation_targets"])
    v_fp = [q for q in answerable if frames[q]["validation_targets"]]
    print(f"\n[영역 4a] Validation — 통과기준 Recall {len(abstain)}/{len(abstain)}, FP 0/{len(answerable)}")
    print(f"  Validation Recall        {v_rec}/{len(abstain)}"
          + ("" if v_rec == len(abstain) else "  ← FAIL"))
    print(f"  Validation False Positive {len(v_fp)}/{len(answerable)}"
          + ("" if not v_fp else f"  ← FAIL {v_fp}"))
    for q in abstain:
        if True:
            got = [v["type"] for v in frames[q]["validation_targets"]]
            want = [v["type"] for v in gold[q]["validation_targets"]]
            print(f"     {q}  want {want}  got {got or '없음'}"
                  + ("" if set(want) & set(got) else "   ← 유형 불일치"))

    # 보조 통계 ─────────────────────────────────────────────────────────────
    print("\n[보조] 채움률 — 검증이 아니라 참고용이다")
    fill = {s: sum(1 for f in frames.values() if f.get(s) not in (None, [], {})) for s in qf.FIELDS}
    print("  " + "  ".join(f"{k} {v}/{parsed}" for k, v in fill.items() if k != "temporal"))
    nguard = sum(len(f.get("_guard") or []) for f in frames.values())
    print(f"  guard 보정 {nguard}건 / {parsed}문항")
    if lat:
        print(f"  지연 p50 {pct(lat,.5):.2f}s  p95 {pct(lat,.95):.2f}s  max {max(lat):.2f}s"
              + ("" if pct(lat, .95) <= 2.0 else "   ← 목표 p95 ≤ 2s 초과"))

    card = {"model": model, "schema_version": qf.SCHEMA_VERSION, "n": parsed,
            "structure": {"parsed": parsed, "schema_ok": ok_struct, "leaks": len(leak_bad)},
            "slots": {s: {"gold": T[s].gold, "pred": T[s].pred, "tp": T[s].tp,
                          "recall": T[s].recall, "precision": T[s].precision} for s in T},
            "exact": {s: {"ok": E[s].ok, "n": E[s].n, "acc": E[s].acc} for s in E},
            "validation": {"recall": f"{v_rec}/{len(abstain)}", "fp": f"{len(v_fp)}/{len(answerable)}"},
            "latency_p50": pct(lat, .5) if lat else None,
            "latency_p95": pct(lat, .95) if lat else None}
    (RESULTS / f"scorecard_{model}.json").write_text(
        json.dumps(card, ensure_ascii=False, indent=1), encoding="utf-8")
    return card


# ── 영역 4b: 모호 세트 ──────────────────────────────────────────────────────
def run_ambiguous(model: str) -> dict:
    rows = load_ambiguous()
    print(f"\n[영역 4b] Ambiguity — 통과기준 Recall 100%, Premature 0%  ({len(rows)}문항)")
    caught, premature, frames = 0, [], {}
    for r in rows:
        f, dt = call(r["question"], model)
        frames[r["question_id"]] = f
        spans = [a["span"] for a in f["ambiguity"]]
        got = all(any(hit(s, sp, True) for s in spans) for sp in r["spans"])
        caught += got
        # premature = 모호 span 을 resolved 조건으로 확정했거나, 질문에 없는 값을 만들어냄
        why = []
        for c in f["constraints"]:
            for sp in r["spans"]:
                if (hit(c["field_text"], sp, True) or hit(c["raw"], sp, True)) \
                        and c["grounding_status"] == "resolved":
                    why.append(f"{c['field_text']}={c.get('value_text') or c.get('value_num')} (resolved)")
            v = c.get("value_text")
            if c["grounding_status"] == "resolved" and v and norm(v) not in norm(r["question"]):
                why.append(f"질문에 없는 값 생성: {c['field_text']}={v!r}")
        if why:
            premature.append((r["question_id"], why))
        print(f"  {r['question_id']}  {dt:5.2f}s  task={f['task']:<14} "
              f"ambiguity={spans or '없음'}" + ("" if got else "   ← 모호 표현 누락")
              + ("   ← PREMATURE" if why else ""))
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"ambiguous_{model}.jsonl").write_text(
        "".join(json.dumps({"question_id": k, **v}, ensure_ascii=False) + "\n"
                for k, v in frames.items()), encoding="utf-8")
    print(f"\n  Ambiguity Recall      {caught}/{len(rows)}"
          + ("" if caught == len(rows) else "  ← FAIL"))
    print(f"  Premature Resolution  {len(premature)}/{len(rows)}"
          + ("" if not premature else "  ← FAIL"))
    for qid, why in premature:
        print(f"     {qid}: {'; '.join(why)}")
    return {"recall": f"{caught}/{len(rows)}", "premature": f"{len(premature)}/{len(rows)}"}


# ── 영역 5: Downstream Utility (TBox 검색 A/B) ──────────────────────────────
EVAL_TABLE = "schema_terms_all"     # 5개 TTL 전부. 운영 bond_schema_terms 는 건드리지 않는다


def _search(text: str, k: int, conn) -> list[str]:
    return [u for u, _ in _search_scored(text, k, conn)]


def _search_scored(text: str, k: int, conn) -> list[tuple[str, float]]:
    q = str(list(map(float, clova.embed(text))))
    return [(r[0], float(r[1])) for r in conn.execute(
        f"SELECT term_uri, 1 - (embedding <=> %(q)s::vector) FROM {EVAL_TABLE}"
        f" ORDER BY embedding <=> %(q)s::vector LIMIT %(k)s", {"q": q, "k": k}).fetchall()]


def frame_slot_queries(f: dict) -> list[str]:
    """B′: 슬롯을 이어 붙이지 않고 각각 따로 질의한다.

    한 문자열로 합치면 여러 개념이 한 벡터로 평균돼 뭉개진다. 실측에서 B(연결)는
    R@5 에서 원문보다 1.4p 나빴다 — 원문은 적어도 문장 하나로 응집돼 있다.
    """
    parts = ([t["text"] for t in f["targets"]]
             + [c["field_text"] for c in f["constraints"]]
             + [h for r in f["relations"] for h in r["path"]]
             + [x["text"] for x in f["requested_fields"]])
    seen, out = set(), []
    for x in parts:
        if x and norm(x) not in seen and len(norm(x)) >= 2:
            seen.add(norm(x))
            out.append(x)
    return out


def frame_query(f: dict) -> str:
    """B 안: 프레임의 의미 슬롯만 이어 붙인다. 질문의 잡음(근거 요구 문장 등)이 빠진다."""
    parts = ([t["text"] for t in f["targets"]]
             + [c["field_text"] for c in f["constraints"]]
             + [h for r in f["relations"] for h in r["path"]]
             + [x["text"] for x in f["requested_fields"]])
    seen, out = set(), []
    for p in parts:
        if p and norm(p) not in seen:
            seen.add(norm(p))
            out.append(p)
    return " ".join(out)


def run_downstream(model: str, ks=(1, 3, 5, 10, 20)) -> dict:
    import psycopg
    from config import BOND_DSN

    src = RESULTS / f"frames_{model}_audit.jsonl"
    if not src.exists():
        src = RESULTS / f"frames_{model}.jsonl"
    if not src.exists():
        sys.exit(f"먼저 --model {model} 로 프레임을 뽑아라 (없음: {src})")
    frames = {json.loads(l)["question_id"]: json.loads(l) for l in
              src.read_text(encoding="utf-8").splitlines() if l.strip()}
    routing = {q["question_id"]: set(q["grounded_concepts"])
               for q in json.loads((A3 / "gold_routing.json").read_text(encoding="utf-8"))["questions"]}
    qs = load_questions()

    conn = psycopg.connect(BOND_DSN, autocommit=True)
    n = conn.execute(f"SELECT count(*) FROM {EVAL_TABLE}").fetchone()[0]
    print(f"\n[영역 5] Downstream — {EVAL_TABLE} {n}개 용어. 통과기준 B ≥ A")
    idx = {r[0] for r in conn.execute(f"SELECT term_uri FROM {EVAL_TABLE}").fetchall()}

    acc = {arm: {k: {"hit": 0, "gold": 0} for k in ks} for arm in ("A", "B", "B'", "A+B'")}
    unreachable = set()
    for qid, f in sorted(frames.items()):
        g = routing.get(qid, set())
        unreachable |= (g - idx)
        g = g & idx              # 인덱스에 없는 개념은 어느 쪽도 못 찾는다 — 분모에서 뺀다
        if not g:
            continue
        tops = {"A": _search(qs[qid]["question"], max(ks), conn),
                "B": _search(frame_query(f), max(ks), conn) if frame_query(f).strip() else []}
        # B′ — 슬롯마다 따로 검색해 용어별 최고점으로 병합한 뒤 상위 k 를 자른다
        best: dict[str, float] = {}
        for sq in frame_slot_queries(f):
            for uri, sc in _search_scored(sq, max(ks), conn):
                if sc > best.get(uri, -1):
                    best[uri] = sc
        tops["B'"] = [u for u, _ in sorted(best.items(), key=lambda x: -x[1])]
        # 실무 조합 — 원문 질의를 버리지 않고 슬롯 질의를 얹는다
        for uri, sc in _search_scored(qs[qid]["question"], max(ks), conn):
            if sc > best.get(uri, -1):
                best[uri] = sc
        tops["A+B'"] = [u for u, _ in sorted(best.items(), key=lambda x: -x[1])]
        for arm, top in tops.items():
            for k in ks:
                acc[arm][k]["hit"] += len(set(top[:k]) & g)
                acc[arm][k]["gold"] += len(g)

    print(f"  {'':>6} " + "".join(f"  R@{k:<5}" for k in ks))
    rows = {}
    for arm, label in (("A", "A 질문원문"), ("B", "B 슬롯연결"), ("B'", "B′ 슬롯개별병합"), ("A+B'", "A+B′ 혼합")):
        rs = [acc[arm][k]["hit"] / acc[arm][k]["gold"] if acc[arm][k]["gold"] else 0.0 for k in ks]
        rows[arm] = rs
        print(f"  {label:<12} " + "".join(f" {r*100:5.1f}%" for r in rs))
    for arm in ("B", "B'", "A+B'"):
        d = [x - a for a, x in zip(rows["A"], rows[arm])]
        print(f"  {arm + '-A':<12} " + "".join(f" {x*100:+5.1f}p" for x in d))
    best_arm = max(("B", "B'", "A+B'"), key=lambda x: rows[x][ks.index(5)] if 5 in ks else rows[x][-1])
    verdict = all(x >= a - 1e-9 for a, x in zip(rows["A"], rows[best_arm]))
    print(f"\n  판정(전 구간): {'PASS' if verdict else 'FAIL'} — 최선 arm {best_arm}"
          + (" 이 모든 k 에서 A 이상" if verdict else " 도 일부 k 에서 A 에 못 미친다"))
    # 실제 운영 지점은 K=5 다(config.BOND_TOP_K). 전 구간 판정과 따로 찍는다 —
    # 기준을 사후에 바꾸지 않기 위해 둘 다 남긴다.
    if 5 in ks:
        i5 = ks.index(5)
        for arm in ("B", "B'", "A+B'"):
            d = rows[arm][i5] - rows["A"][i5]
            print(f"  운영지점 K=5  {arm:<5} {rows[arm][i5]*100:5.1f}%  (A 대비 {d*100:+.1f}p"
                  f", 상대 {d/rows['A'][i5]*100:+.0f}%)")
    if unreachable:
        print(f"  주의: 인덱스에 없어 분모에서 제외한 gold concept — {sorted(unreachable)}")
    return {"ks": list(ks), **{a: rows[a] for a in rows}, "pass": verdict}


def rescore(model: str, use_audit: bool = True) -> dict:
    """저장된 원시 출력(_raw)에 지금의 guard 를 다시 적용해 채점한다. API 호출 없음.

    guard 규칙을 고쳤을 때 그 효과만 분리해서 보려면 이게 유일하게 정확한 방법이다.
    LLM 을 다시 부르면 온도 0이어도 출력이 흔들려 무엇이 개선인지 알 수 없다.
    """
    src = RESULTS / f"frames_{model}{'_audit' if use_audit else ''}.jsonl"
    if not src.exists():
        sys.exit(f"저장된 프레임이 없다: {src}")
    gold, qs, frames = load_gold(), load_questions(), {}
    for line in src.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        old = json.loads(line)
        f = qf.guard(old.get("_raw") or {})
        f["_raw"] = old.get("_raw")
        f["validation_targets"] = old["validation_targets"]   # 감사는 별도 호출이라 _raw 에 없다
        frames[old["question_id"]] = f
    print(f"저장본 재채점 — {src.name} ({len(frames)}건, LLM 호출 없음)")
    return report(model, gold, qs, frames, [], {}, n_expected=len(frames))


def main():
    ap = argparse.ArgumentParser(description="Query Frame v1 검증")
    ap.add_argument("--check-gold", action="store_true", help="네트워크 없이 gold 무결성만")
    ap.add_argument("--model", default=qf.MODEL, help="추출 모델 (기본 HCX-007)")
    ap.add_argument("--ambiguous", action="store_true", help="영역 4b 모호 세트")
    ap.add_argument("--downstream", action="store_true", help="영역 5 TBox A/B (pgvector 필요)")
    ap.add_argument("--only", nargs="*", help="특정 question_id 만 (예: q013 q031)")
    ap.add_argument("--audit", action="store_true", help="validation_targets 를 별도 감사 호출로 뽑는다")
    ap.add_argument("--rescore", action="store_true", help="저장된 원시 출력에 지금의 guard 로 재채점 (API 호출 없음)")
    a = ap.parse_args()

    if a.check_gold:
        sys.exit(check_gold())
    if a.downstream:
        run_downstream(a.model)
        return
    if a.ambiguous:
        run_ambiguous(a.model)
        return
    if a.rescore:
        rescore(a.model, use_audit=True)
        return
    run_35(a.model, only=set(a.only) if a.only else None, use_audit=a.audit)


if __name__ == "__main__":
    main()
