#!/usr/bin/env python3
"""
통합 기회점수(시도 × 연수 주제) -> '이번 주 공략 Top 10' (B2G영업 탭 맨 위). combine_dashboard.py 가 build() 를 부른다.

점수(100점, 규칙 기반 - 수주 결과 학습은 하지 않음):
  발주 수요 30   최근 12개월 나라장터 연수 입찰(공고번호 단위) 시도×주제 건수(로그 정규화)
  발주 모멘텀 10  최근 90일 건수가 12개월 월평균×3 보다 많으면 가점
  트렌드 20      교사 트렌드 2027 주제 점수(0~100) × 0.2
  시장 규모 10    시도 학교 수(나이스) 정규화
  강사 공급 15    강사풀 시도 핵심·활동 강사 수(로그) 10 + 그 시도·주제 교사 연구회 5
  자사 기반 5     최근 12개월 그 시도 자사 수주(계약) 이력
  AI 확대 5       AI 주제만: 2027 AI 중점학교 신규 지정 추정(시도 비중)
  경쟁 강도 -15   최근 12개월 그 시도 경쟁사 계약 건수(정규화)
각 칸의 근거 수치를 함께 남겨 화면에서 펼쳐 볼 수 있게 한다.
"""
import json
import math
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import training_topics
from mall_trends import TOPIC_NAME

SIDO = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
OWN = "비바샘"


def _jsonl(p):
    p = Path(p)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def _load(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return default


def _norm_log(v, mx):
    return math.log1p(v) / math.log1p(mx) if mx > 0 else 0.0


def build(trend2027=None, data_rows=None, today=None, pipeline=None):
    today = today or date.today()
    y1, d90 = (today - timedelta(365)).isoformat(), (today - timedelta(90)).isoformat()

    # 1) 연수 입찰 수요(공고번호 단위 중복 제거)
    bids, seen = defaultdict(lambda: {"n": 0, "n90": 0, "amt": 0, "titles": []}), set()
    for b in _jsonl("history/training_bids.jsonl"):
        no, d, r = (b.get("k") or "").rsplit("-", 1)[0], b.get("d") or "", b.get("r")
        if d < y1 or no in seen or r not in SIDO:
            continue
        seen.add(no)
        for tid in training_topics.classify_topics(b.get("t") or ""):
            c = bids[(r, tid)]
            c["n"] += 1
            c["amt"] += b.get("a") or 0
            if d >= d90:
                c["n90"] += 1
            if len(c["titles"]) < 3:
                c["titles"].append(b.get("t") or "")

    # 2) 계약(자사·경쟁사) - 수의계약 포함
    comp, own = Counter(), Counter()
    for c in _jsonl("history/competitor_contracts.jsonl"):
        if (c.get("date") or "") < y1 or c.get("region") not in SIDO:
            continue
        (own if OWN in (c.get("competitor") or "") else comp)[c["region"]] += 1

    # 3) 트렌드·학교 수·강사 공급·연구회·AI 확대
    T = {t["id"]: t for t in ((trend2027 or {}).get("topics") or [])}
    schools = {r["region"]: r.get("total", 0) for r in (data_rows or [])}
    G = _load("static_data/teacher_groups.json", {}) or {}
    core = dict((G.get("pool") or {}).get("core_by_sido") or [])
    grp = Counter()
    for g in G.get("groups") or []:
        for tid in g.get("topics") or []:
            grp[(g.get("sido"), tid)] += 1
    U = _load("static_data/ai_school_updates.json", {}) or {}
    st = (_load("static_data/ai_schools_2026.json", {}) or {}).get("status") or []
    tot = sum(r.get("ai_moe") or 0 for r in st) or 1
    p27 = next((x["n"] for x in (U.get("national") or {}).get("plan", []) if x.get("year") == 2027), 0)
    ai_new = {r["region"]: max(0, round(p27 * (r.get("ai_moe") or 0) / tot) - (r.get("ai_moe") or 0)) for r in st} if p27 else {}

    mx_bid = (max([c["n"] for c in bids.values()] or [1])) or 1
    mx_sch = (max(schools.values() or [1])) or 1
    mx_core = (max(core.values() or [1])) or 1
    mx_comp = (max(comp.values() or [1])) or 1
    mx_ai = (max(ai_new.values() or [1])) or 1
    cells = []
    for r in SIDO:
        for tid, nm in TOPIC_NAME.items():
            c = bids.get((r, tid), {"n": 0, "n90": 0, "amt": 0, "titles": []})
            t = T.get(tid, {})
            part = {
                "발주 수요": round(30 * _norm_log(c["n"], mx_bid), 1),
                "모멘텀": round(min(10, 10 * max(0, c["n90"] - c["n"] / 4) / max(1, c["n"] / 4)), 1) if c["n"] else 0,
                "트렌드": round(0.2 * (t.get("score") or 0), 1),
                "시장 규모": round(10 * (schools.get(r, 0) / mx_sch), 1),
                "강사 공급": round(10 * _norm_log(core.get(r, 0), mx_core) + min(5, 2.5 * grp.get((r, tid), 0)), 1),
                "자사 기반": round(min(5, 1.5 * own.get(r, 0)), 1),
                "AI 확대": round(5 * ai_new.get(r, 0) / mx_ai, 1) if tid == "ai" and ai_new else 0,
                "경쟁 강도": -round(15 * comp.get(r, 0) / mx_comp, 1),
            }
            score = round(sum(part.values()), 1)
            if c["n"] == 0 and (t.get("score") or 0) < 40:
                continue  # 수요 근거가 전혀 없는 칸은 목록에서 뺀다
            supply_low = core.get(r, 0) < 5 and grp.get((r, tid), 0) == 0
            supply_thin = core.get(r, 0) < 5 and not supply_low
            heavy = comp.get(r, 0) >= max(3, mx_comp * 0.6)
            act = ("강사 확보 먼저 — 그 시도 강사·연구회가 거의 없음" if supply_low else
                   "차별 주제로 제안 — 경쟁사 계약이 많은 시도" if heavy else
                   ("제안 착수 + 강사 확보 병행 — 연구회는 있으나 핵심 강사 5명 미만" if supply_thin else "제안 착수 — 수요·공급 모두 갖춤") if c["n"] >= 2
                   else "선제 제안 — 트렌드 대비 발주가 아직 적음")
            cells.append({"sido": r, "tid": tid, "topic": nm, "score": score, "parts": part,
                          "bids": c["n"], "bids90": c["n90"], "amt": c["amt"], "titles": c["titles"],
                          "trend": t.get("score"), "stage": t.get("stage"), "core": core.get(r, 0), "groups": grp.get((r, tid), 0),
                          "comp": comp.get(r, 0), "own": own.get(r, 0), "ai_new": ai_new.get(r) if tid == "ai" else None, "action": act})
    # 자사 진행 사업(영업 파이프라인, 시도별 건수·금액) - 표시만, 점수에는 넣지 않는다(수주 결과 학습 안 함)
    pipe = {k: v for k, v in ((pipeline or {}).get("byRegion") or {}).items()}
    for x in cells:
        p = pipe.get(x["sido"]) or {}
        x["pipe"] = {"n": p.get("count", 0), "amt": p.get("amount", 0)}
    cells.sort(key=lambda x: -x["score"])
    by_sido = defaultdict(float)
    for x in cells:
        by_sido[x["sido"]] = max(by_sido[x["sido"]], x["score"])
    return {"generated": today.isoformat(), "top": cells[:10], "cells": cells[:120],
            "heat": [{"sido": r, "best": round(by_sido.get(r, 0), 1)} for r in SIDO],
            "n_bids": len(seen), "comp_total": sum(comp.values()), "own_total": sum(own.values()),
            "weights": {"발주 수요": 30, "모멘텀": 10, "트렌드": 20, "시장 규모": 10, "강사 공급": 15, "자사 기반": 5, "AI 확대": 5, "경쟁 강도": -15}}


if __name__ == "__main__":
    r = build()
    for x in r["top"]:
        print(x["score"], x["sido"], x["topic"], x["bids"], x["action"])
