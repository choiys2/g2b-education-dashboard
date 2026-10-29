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
    tot = sum(heat.values()) or 1
    out["heat"] = sorted(({"topic": TOPIC_NAME.get(t, t), "heat": round(v / tot * 100, 1), "own": own.get(t, 0)}
                          for t, v in heat.items()), key=lambda r: -r["heat"])
    return out
