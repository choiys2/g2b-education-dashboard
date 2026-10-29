#!/usr/bin/env python3
"""
교사 트렌드(유튜브 교사 크리에이터) -> 경쟁사 탭 패널 데이터. combine_dashboard.py 에서 호출(API 호출 없음).

주제 열기: 교사 채널 최근 영상 조회수를 연수 주제(training_topics + 교사몰 상품 어휘)로 나눠
자사 과정 수와 나란히 놓는다 - 관심은 큰데 자사 과정이 적은 주제가 개발·마케팅 우선순위.
"""
import json
import math
import re
from datetime import date, timedelta
from pathlib import Path

from mall_trends import TOPIC_NAME, topics_of

SRC = Path(__file__).parent / "history" / "teacher_creator_trends.json"
INTEREST = Path(__file__).parent / "history" / "teacher_interest_trends.json"


def _trend(series):
    """[[주, 지수]] -> 최근 4주 평균, 그 앞 12주 대비 변화율(%), 최근 26주 스파크라인"""
    v = [x[1] for x in series or []]
    if len(v) < 8:
        return None
    last, prev = sum(v[-4:]) / 4, v[-16:-4]
    base = sum(prev) / len(prev) if prev else 0
    return {"idx": round(last, 1), "mom": round((last / base - 1) * 100) if base else None, "spark": [round(x, 1) for x in v[-26:]]}


def interest(own):
    """네이버 데이터랩·쇼핑인사이트·블로그/카페 글 수 -> 주제별 관심 지표"""
    try:
        src = json.loads(INTEREST.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"available": False}
    dl = (src.get("datalab") or {}).get("topics", {})
    hist = src.get("buzz_hist", {})
    days = sorted(hist)
    cur, prev = (hist[days[-1]] if days else {}), (hist[days[-2]] if len(days) > 1 else None)
    gap_days = (date.fromisoformat(days[-1]) - date.fromisoformat(days[-2])).days if prev else 0
    rows = []
    for t in set(dl) | set(cur):
        tr = _trend(dl.get(t))
        c = cur.get(t, {})
        total = sum(v for v in c.values() if v)
        weekly = None
        if prev and gap_days:
            p = prev.get(t, {})
            weekly = round(sum((c.get(k) or 0) - (p.get(k) or 0) for k in c if c.get(k) and p.get(k)) / gap_days * 7)
        rows.append({"id": t, "topic": TOPIC_NAME.get(t, t), "idx": tr and tr["idx"], "mom": tr and tr["mom"],
                     "spark": tr["spark"] if tr else [], "posts": total, "weekly": weekly, "own": own.get(t, 0),
                     "titles": (src.get("buzz_titles") or {}).get(t, [])[:3]})
    idxs = sorted(r["idx"] for r in rows if r["idx"] is not None)
    med = idxs[len(idxs) // 2] if idxs else 0
    for r in rows:
        sig = []
        if r["mom"] is not None and r["mom"] >= 15:
            sig.append("상승")
        if r["own"] <= 2 and (r["idx"] or 0) >= med:
            sig.append("공백")
        r["signal"] = sig
    rows.sort(key=lambda r: -(r["idx"] or 0))
    shop = [{"k": k, **(_trend(v) or {"idx": None, "mom": None, "spark": []})}
            for k, v in ((src.get("shopping") or {}).get("keywords") or {}).items()]
    return {"available": bool(rows), "dl_date": (src.get("datalab") or {}).get("captured_date"), "ages": (src.get("datalab") or {}).get("ages", ""),
            "buzz_date": src.get("buzz_date"), "has_weekly": bool(prev), "rows": rows, "shop": shop}


def _growth(hist, cid, weeks=4):
    h = sorted((hist or {}).get(cid, {}).items())
    if len(h) < 2:
        return None
    base = next((v for d, v in reversed(h[:-1]) if d <= (date.fromisoformat(h[-1][0]) - timedelta(weeks=weeks)).isoformat()), h[0][1])
    return h[-1][1] - base


def build(own_courses):
    try:
        src = json.loads(SRC.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        src = {}
    yt = src.get("youtube", {})
    out = {"available": bool(yt.get("channels")), "yt_date": yt.get("captured_date")}

    heat, chans, vids = {}, [], []
    recent_cut = (date.today() - timedelta(days=60)).isoformat()
    for c in yt.get("channels", []):
        rec = c.get("recent", [])
        tv = {}
        for v in rec:
            ts = topics_of(v["t"], product=True)
            for t in ts or ["etc"]:
                tv[t] = tv.get(t, 0) + v["v"]
            if v.get("d", "") >= recent_cut:
                vids.append({"id": v["id"], "t": v["t"], "d": v["d"], "v": v["v"], "ch": c["title"],
                             "topics": [TOPIC_NAME.get(t, t) for t in ts]})
        # 채널 1개 = 영향력 log10(구독자) 만큼의 표를 최근 영상 조회 비중대로 주제에 나눠 준다(바이럴 영상 1개가 전체를 덮지 않게)
        tot_c = sum(tv.values()) or 1
        for t, v in tv.items():
            if t != "etc":
                heat[t] = heat.get(t, 0) + math.log10(c["subs"] + 10) * v / tot_c
        main = max((k for k in tv if k != "etc"), key=lambda k: tv[k], default="")
        chans.append({"t": c["title"], "h": c.get("handle", ""), "id": c["id"], "subs": c["subs"],
                      "g4": _growth(yt.get("subs_hist"), c["id"]),
                      "avg": round(sum(v["v"] for v in rec) / len(rec)) if rec else 0,
                      "topic": TOPIC_NAME.get(main, ""), "insta": "" if re.search(r"instagram|^www", c.get("insta", ""), re.I) else c.get("insta", ""),
                      "top": max(rec, key=lambda v: v["v"]) if rec else None})
    chans.sort(key=lambda c: -c["subs"])
    out["channels"] = chans[:20]
    out["n_channels"] = len(chans)
    out["videos"] = sorted(vids, key=lambda v: -v["v"])[:10]

    own = {}
    for c in own_courses or []:
        for t in topics_of(c.get("title", "")):
            own[t] = own.get(t, 0) + 1
    out["interest"] = interest(own)
    tot = sum(heat.values()) or 1
    out["heat"] = sorted(({"topic": TOPIC_NAME.get(t, t), "heat": round(v / tot * 100, 1), "own": own.get(t, 0)}
                          for t, v in heat.items()), key=lambda r: -r["heat"])
    return out
