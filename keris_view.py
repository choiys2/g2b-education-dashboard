#!/usr/bin/env python3
"""
KERIS 조달(history/keris_procurement.json) -> 'KERIS 조달' 탭 데이터(combine_dashboard.py 에서 호출, API 호출 없음).

  - 진행 중 공고(마감 전) D-day, 관련 분야 강조
  - 발주 추이(월별 건수·금액)·분야 구성·계약방식
  - 개찰·낙찰: 참가업체 수 분포, 낙찰률, 낙찰업체 순위(건수·금액)
  - 자사·경쟁사 참여·낙찰 이력(관련 분야 개찰 참가 목록 기준)
"""
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

from keris_export import classify

SRC = Path(__file__).parent / "history" / "keris_procurement.json"


def _rate(v):
    try:
        return round(float(str(v).replace("%", "")), 2)
    except (TypeError, ValueError):
        return None


def _corp(n):
    """'(주)○○', '주식회사 ○○' 표기 차이를 합친다."""
    return re.sub(r"\(주\)|㈜|주식회사|\(유\)|유한회사|\s+", "", n or "").strip()


def build():
    try:
        d = json.loads(SRC.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"available": False}
    bids, opens, awards, parts = d.get("bids", {}), d.get("opening", {}), d.get("awards", {}), d.get("participants", {})
    if not bids and not awards:
        return {"available": False, "status": d.get("status", {})}
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    today = date.today()

    # 진행 중 공고: 마감일시가 지금 이후(재공고 차수는 최신만)
    for b in bids.values():
        b["cat"] = classify(b.get("t", ""))  # 분류 규칙이 바뀌어도 재수집 없이 반영
    latest = {}
    for k, b in bids.items():
        no = b.get("no") or k.rsplit("-", 1)[0]
        if no not in latest or (b.get("ord") or "") > (latest[no].get("ord") or ""):
            latest[no] = {**b, "key": k}
    live = []
    for b in latest.values():
        close = (b.get("close") or "").replace("/", "-")
        if close and close >= now:
            try:
                dd = (datetime.strptime(close[:10], "%Y-%m-%d").date() - today).days
            except ValueError:
                dd = None
            live.append({**b, "dday": dd})
    live.sort(key=lambda b: (not b["rel"], b.get("dday") if b.get("dday") is not None else 999))

    # 월별 추이·분야·계약방식(최신 차수 기준)
    by_month = defaultdict(lambda: {"n": 0, "amt": 0, "rel": 0})
    cats, cat_amt, methods = Counter(), Counter(), Counter()
    for b in latest.values():
        m = (b.get("d") or "")[:7]
        if not m:
            continue
        amt = b.get("budget") or b.get("est") or 0
        by_month[m]["n"] += 1
        by_month[m]["amt"] += amt
        by_month[m]["rel"] += 1 if b.get("rel") else 0
        cats[b["cat"]] += 1
        cat_amt[b["cat"]] += amt
        methods[b.get("method") or "미상"] += 1
    months = sorted(by_month)[-36:]

    # 개찰·낙찰
    n_dist = Counter()
    for o in opens.values():
        n = o.get("n")
        if n:
            n_dist["1개사" if n == 1 else "2~3개사" if n <= 3 else "4~9개사" if n <= 9 else "10개사 이상"] += 1
    status = Counter(o.get("status") or "미상" for o in opens.values())
    wins = defaultdict(lambda: {"n": 0, "amt": 0, "rel": 0, "name": ""})
    rates = []
    for k, a in awards.items():
        c = _corp(a.get("winner"))
        if not c:
            continue
        w = wins[c]
        w["name"] = a.get("winner")
        w["n"] += 1
        w["amt"] += a.get("amt") or 0
        rel = bids.get(k, {}).get("rel") or False
        w["rel"] += 1 if rel else 0
        w["co"] = a.get("co", "")
        r = _rate(a.get("rate"))
        if r and 50 <= r <= 110 and (a.get("n") or 0) >= 2:  # 1개사 수의시담(100%)은 낙찰률 분포에서 제외
            rates.append({"r": r, "rel": rel, "n": a.get("n"), "t": a.get("t"), "amt": a.get("amt")})
    top = sorted(wins.values(), key=lambda w: -w["amt"])[:15]
    rel_rates = [x["r"] for x in rates if x["rel"]]

    # 자사·경쟁사 참여 이력(관련 분야 개찰 참가 목록)
    co = defaultdict(lambda: {"bid": 0, "win": 0, "items": []})
    for k, ps in parts.items():
        for p in ps:
            if not p.get("co"):
                continue
            c = co[p["co"]]
            c["bid"] += 1
            won = p.get("rank") == 1
            c["win"] += 1 if won else 0
            c["items"].append({"t": (bids.get(k) or opens.get(k) or {}).get("t", ""), "d": (opens.get(k) or {}).get("d", ""),
                               "rank": p.get("rank"), "n": len(ps), "rate": p.get("rate")})
    for c in co.values():
        c["items"] = sorted(c["items"], key=lambda x: x["d"], reverse=True)[:8]
    # 관련 분야 낙찰 목록(최근순)
    rel_awards = sorted(({**a, "key": k} for k, a in awards.items() if bids.get(k, {}).get("rel") or a.get("co")),
                        key=lambda a: a.get("d") or "", reverse=True)[:20]

    tot_amt = sum(b.get("budget") or b.get("est") or 0 for b in latest.values())
    return {"available": True, "updated": d.get("updated"), "inst": d.get("inst"),
            "kpi": {"bids": len(latest), "rel": sum(1 for b in latest.values() if b.get("rel")), "amt": tot_amt,
                    "live": len(live), "awards": len(awards), "avg_n": round(sum(o["n"] for o in opens.values() if o.get("n")) /
                                                                          max(1, sum(1 for o in opens.values() if o.get("n"))), 1),
                    "rate_med": sorted(x["r"] for x in rates)[len(rates) // 2] if rates else None,
                    "solo": sum(1 for a in awards.values() if (a.get("n") or 0) == 1), "comp_n": len(rates),
                    "rel_rate_med": sorted(rel_rates)[len(rel_rates) // 2] if rel_rates else None,
                    "since": min((b.get("d") or "9") for b in latest.values()) if latest else ""},
            "live": live[:40], "months": [{"m": m, **by_month[m]} for m in months],
            "cats": [{"cat": c, "n": n, "amt": cat_amt[c]} for c, n in cats.most_common()],
            "methods": methods.most_common(6), "n_dist": [[k, n_dist[k]] for k in ("1개사", "2~3개사", "4~9개사", "10개사 이상")],
            "open_status": status.most_common(5), "winners": top, "rates": rates[-200:],
            "companies": {k: v for k, v in sorted(co.items(), key=lambda x: -x[1]["bid"])},
            "rel_awards": rel_awards, "status": d.get("status", {}).get("diag", [])[:5]}


if __name__ == "__main__":
    o = build()
    print(json.dumps({k: o.get(k) for k in ("kpi", "cats", "methods", "n_dist", "open_status")}, ensure_ascii=False, indent=1))
