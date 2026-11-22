#!/usr/bin/env python3
"""
CP 키메시지(사용자 승인 2026-11-22) — 일반 화면 맨 위 '오늘의 키메시지 띠'·'이번 주 시장 스토리'·'알고 계셨나요'·'내 관점' 데이터.
숫자 위주 JSON(문장은 화면에서 조립)으로 내보내 combine_dashboard 의 데이터 무력화(_neutral)를 그대로 거친다.
CP 문구 원칙: 출처·수집 방식·도구명·자사 매출·점유는 넣지 않는다(시장 사실만).
"""
from collections import Counter, defaultdict
from datetime import date, timedelta

from cp_viz import SIDO

TODAY = date.today()


def _topic_of(t, T):
    return next((n for n, rx in T if rx.search(t)), "")


def build():
    from viz_more import _bids, _months
    from sales_analysis import _topics, _load, _forecast
    T = _topics()
    B = _bids(730)
    if not B:
        return None
    y1 = [b for b in B if b["d"] >= TODAY - timedelta(days=365)]
    tot = sum(b["a"] for b in y1) or 1
    # 시도별
    sd_amt, sd_n = Counter(), Counter()
    sd_mon = defaultdict(Counter)
    sd_tp = defaultdict(Counter)
    for b in y1:
        if b["sd"]:
            sd_amt[b["sd"]] += b["a"]
            sd_n[b["sd"]] += 1
            sd_mon[b["sd"]][b["d"].month] += 1
            tp = _topic_of(b["t"], T)
            if tp:
                sd_tp[b["sd"]][tp] += 1
    ms = _months(6)
    rec3, pre3 = set(ms[-3:]), set(ms[:3])
    sd_up = {}
    for s in SIDO:
        a = sum(1 for b in B if b["sd"] == s and b["d"].isoformat()[:7] in rec3)
        p = sum(1 for b in B if b["sd"] == s and b["d"].isoformat()[:7] in pre3)
        sd_up[s] = [a, p]
    # 주제
    tp_n = Counter()
    for b in y1:
        tp = _topic_of(b["t"], T)
        if tp:
            tp_n[tp] += 1
    tp_tot = sum(tp_n.values()) or 1
    # 떠오르는 주제: 최근 3개월 vs 그 이전 3개월(건수 3 이상, 증가율 순)
    r3, p3 = Counter(), Counter()
    for b in B:
        k = b["d"].isoformat()[:7]
        tp = _topic_of(b["t"], T)
        if tp and k in rec3:
            r3[tp] += 1
        elif tp and k in pre3:
            p3[tp] += 1
    rising = [n for n in sorted(r3, key=lambda n: -(r3[n] + 1) / (p3[n] + 1)) if r3[n] >= 3 and r3[n] > p3[n]][:2]
    # 시기(주별 최대 구간)
    mon = Counter(b["d"].month for b in y1)
    peak = [m for m, _ in mon.most_common(2)]
    # 예보
    try:
        months, F = _forecast(_load())
        fc = [[f"{y}-{m:02d}", len(F[(y, m)])] for (y, m) in months]
        fc_sd = defaultdict(int)
        for k in F:
            for z in F[k]:
                s = next((x for x in SIDO if str(z.get("r") or "").startswith(x)), "")
                if s:
                    fc_sd[s] += 1
    except Exception:  # noqa: BLE001
        fc, fc_sd = [], {}
    # 알고 계셨나요(데이터로 확인되는 사실만): 공고가 몰리는 요일 · 하반기 최대 달 · 공고 규모가 가장 큰 시도
    facts = []
    wd = Counter(b["d"].weekday() for b in y1)
    if wd:
        top2 = [d for d, _ in wd.most_common(2)]
        facts.append({"k": "wday", "d": top2, "pct": round(sum(wd[d] for d in top2) / sum(wd.values()) * 100)})
    h2 = {m: mon[m] for m in range(7, 13)}
    if any(h2.values()):
        mm = max(h2, key=h2.get)
        facts.append({"k": "h2", "m": mm, "n": h2[mm]})
    amts = [(b["a"], b["sd"]) for b in y1 if b["a"] > 0 and b["sd"]]
    if amts:
        med = defaultdict(list)
        for a, s in amts:
            med[s].append(a)
        rich = max((s for s in med if len(med[s]) >= 5), key=lambda s: sorted(med[s])[len(med[s]) // 2], default=None)
        if rich:
            v = sorted(med[rich]); facts.append({"k": "rich", "sd": rich, "med": round(v[len(v) // 2] / 1e8, 2)})
    return {
        "asof": TODAY.isoformat(),
        "tot": round(tot / 1e8, 1),
        "sd": {s: {"amt": round(sd_amt[s] / 1e8, 1), "sh": round(sd_amt[s] / tot * 100), "n": sd_n[s],
                   "peak": [m for m, _ in sd_mon[s].most_common(2)], "tp": [n for n, _ in sd_tp[s].most_common(2)],
                   "up": sd_up.get(s, [0, 0]), "fc": fc_sd.get(s, 0)} for s in SIDO if sd_n[s]},
        "top_sd": [s for s, _ in sd_amt.most_common(3)],
        "peak": peak,
        "tp": [[n, round(c / tp_tot * 100)] for n, c in tp_n.most_common(8)],
        "rising": rising,
        "up": [s for s in SIDO if sd_up[s][0] > sd_up[s][1]],
        "fc": fc,
        "facts": facts,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(build(), ensure_ascii=False)[:1500])
