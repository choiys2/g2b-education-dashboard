#!/usr/bin/env python3
"""
발주 예측 캘린더(앞으로 DAYS 일) - combine_dashboard.py 가 build() 를 부른다(추가 수집·API 호출 없음).

  1) 1년 주기 반복: 작년 같은 시기(오늘-365+[−7, DAYS])에 공고한 연수 입찰을 기관·사업명 단위로 보고,
     올해(최근 120일) 같은 기관이 비슷한 이름으로 이미 다시 공고했으면 '재공고 확인', 아니면 '예상'으로 둔다.
     예상 공고 시기 = 작년 공고일 + 1년(±2주).
  2) 발주계획: history/order_plans.jsonl 중 연수·교육 용역(이번 달·다음 달 계획).
누적 기간이 1년 남짓이라 '작년에 했으니 올해도'라는 단순 반복 가정이다. 화면에 그렇게 밝힌다.
"""
import json
import re
from datetime import date, timedelta
from pathlib import Path

import training_topics
from mall_trends import TOPIC_NAME

DAYS = 60
NOT_TEACHER = re.compile(r"학생|국외|해외|체험연수|선수|탐방|자매학교|도제|현장연수|수학여행|캠프|학부모")
TEACHER = re.compile(r"교원|교사|교직원|교감|교장|관리자|직무연수|장학|공무원|전문직|연수원")
NON_TRAINING = re.compile(r"세탁|침구|공사|전산|사무기기|재해복구|고도화|건설|급식|청소|경비|소모품|시설|구매|임차|렌탈")
EDU_ORG = re.compile(r"교육청|교육부|교육지원청|학교|교육원|교육연수원|교원")
NON_EDU_ORG = re.compile(r"경찰|법무|소방|사법|대법원|해양|국방|병무")
STOP = set("년 및 의 등 위한 대상 용역 운영 위탁 사업 연수 교육 2025 2026 2027 긴급 재공고 차 기".split())


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


def _tok(t):
    t = re.sub(r"\[[^\]]*\]|\([^)]*\)|\d{4}\.?|\d+기|\d+차|[0-9]+", " ", t or "")
    return {w for w in re.findall(r"[가-힣A-Za-z]{2,}", t) if w not in STOP}


def _sim(a, b):
    return len(a & b) / max(1, len(a | b))


def build(today=None):
    today = today or date.today()
    rows, seen = [], set()
    for b in _jsonl("history/training_bids.jsonl"):
        no = (b.get("k") or "").rsplit("-", 1)[0]
        if no in seen or not b.get("d"):
            continue
        seen.add(no)
        rows.append(b)
    lo, hi = today - timedelta(365) - timedelta(7), today - timedelta(365) + timedelta(DAYS)
    recent = [b for b in rows if b["d"] >= (today - timedelta(120)).isoformat()]
    rec_tok = [(b, _tok(b.get("t"))) for b in recent]
    items, keyset = [], set()
    for b in rows:
        d = date.fromisoformat(b["d"])
        if not (lo <= d <= hi):
            continue
        t0 = b.get("t") or ""
        if NOT_TEACHER.search(t0) and not TEACHER.search(t0):
            continue  # 학생 국외연수·체험 등 교원 연수가 아닌 공고
        o0 = b.get("o") or ""
        if NON_TRAINING.search(t0) or not EDU_ORG.search(o0) or NON_EDU_ORG.search(o0):
            continue  # 시설·물품 용역, 교육기관이 아닌 발주처
        tk = _tok(b.get("t"))
        key = (b.get("o"), frozenset(tk))
        if key in keyset:
            continue
        keyset.add(key)
        hit = next((r for r, rt in rec_tok if r.get("o") == b.get("o") and _sim(tk, rt) >= 0.4), None)
        exp = d + timedelta(365)
        items.append({"kind": "반복", "org": b.get("o") or "", "r": b.get("r") or "", "t": b.get("t") or "", "last": b["d"],
                      "exp": exp.isoformat(), "from": (exp - timedelta(14)).isoformat(), "to": (exp + timedelta(14)).isoformat(),
                      "amt": b.get("a") or 0, "topics": [TOPIC_NAME.get(x, x) for x in training_topics.classify_topics(b.get("t") or "")],
                      "status": "재공고 확인" if hit else "예상", "hit_date": hit.get("d") if hit else None, "u": b.get("u")})
    # 발주계획(연수·교육 용역만)
    m_now, m_next = today.month, (today.month % 12) + 1
    pseen = set()
    for p in _jsonl("history/order_plans.jsonl"):
        t = p.get("t") or ""
        if not re.search(r"연수|직무|역량\s?강화|교원\s?교육|교육\s?운영", t) or re.search(r"공사|설계|감리|폐기물|급식|청소|경비", t):
            continue
        try:
            m = int(str(p.get("m") or "0")[:2])
        except ValueError:
            continue
        if m not in (m_now, m_next) or p.get("k") in pseen:
            continue
        pseen.add(p.get("k"))
        y = today.year + (1 if m < m_now else 0)
        items.append({"kind": "발주계획", "org": p.get("o") or "", "r": p.get("r") or "", "t": t, "last": p.get("d"),
                      "exp": f"{y}-{m:02d}-15", "from": f"{y}-{m:02d}-01", "to": f"{y}-{m:02d}-28", "amt": p.get("a") or 0,
                      "topics": [TOPIC_NAME.get(x, x) for x in training_topics.classify_topics(t)], "status": "계획 등록",
                      "how": p.get("how"), "hit_date": None, "u": None})
    items.sort(key=lambda x: (x["status"] == "재공고 확인", x["exp"]))
    pending = [x for x in items if x["status"] != "재공고 확인"]
    by_week, by_r = {}, {}
    for x in pending:
        e = date.fromisoformat(x["exp"])
        wk = (e - timedelta(e.weekday())).isoformat()
        by_week[wk] = by_week.get(wk, 0) + 1
        by_r[x["r"]] = by_r.get(x["r"], 0) + 1
    return {"generated": today.isoformat(), "days": DAYS, "items": items[:200], "n_pending": len(pending),
            "n_hit": sum(1 for x in items if x["status"] == "재공고 확인"),
            "amt_pending": sum(x["amt"] for x in pending), "by_week": sorted(by_week.items()),
            "by_region": sorted(by_r.items(), key=lambda kv: -kv[1]),
            "basis": f"연수 입찰 누적 {len(rows)}건({min((b['d'] for b in rows), default='-')}~) · 발주계획 연수 {len(pseen)}건"}


if __name__ == "__main__":
    r = build()
    print(r["basis"], "· 예상", r["n_pending"], "· 재공고 확인", r["n_hit"], "· 금액", r["amt_pending"])
    for x in r["items"][:12]:
        print(x["status"], x["exp"], x["r"], x["org"][:20], "|", x["t"][:50])
    print(r["by_region"][:8])
