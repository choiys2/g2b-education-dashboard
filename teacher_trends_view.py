#!/usr/bin/env python3
"""
교사 트렌드(유튜브 교사 크리에이터·교사 도서) -> 경쟁사 탭 패널 데이터. combine_dashboard.py 에서 호출(API 호출 없음).

주제 열기: 최근 영상 조회수와 도서 판매지수를 연수 주제(training_topics + 교사몰 상품 어휘)로 나눠
자사 과정 수와 나란히 놓는다 - 관심은 큰데 자사 과정이 적은 주제가 개발·마케팅 우선순위.
"""
import json
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
    yt, bk = src.get("youtube", {}), src.get("books", {})
    out = {"available": bool(yt.get("channels") or bk.get("items")),
           "yt_date": yt.get("captured_date"), "book_date": bk.get("captured_date")}

    heat = {}
    chans = []
    for c in yt.get("channels", []):
        rec = c.get("recent", [])
        tv = {}
        for v in rec:
            for t in topics_of(v["t"], product=True) or ["etc"]:
                tv[t] = tv.get(t, 0) + v["v"]
                if t != "etc":
                    heat.setdefault(t, {"yt": 0, "book": 0})["yt"] += v["v"]
        main = max((k for k in tv if k != "etc"), key=lambda k: tv[k], default="")
        chans.append({"t": c["title"], "h": c.get("handle", ""), "id": c["id"], "subs": c["subs"],
                      "g4": _growth(yt.get("subs_hist"), c["id"]),
                      "avg": round(sum(v["v"] for v in rec) / len(rec)) if rec else 0,
                      "topic": TOPIC_NAME.get(main, ""), "insta": c.get("insta", ""),
                      "top": max(rec, key=lambda v: v["v"]) if rec else None})
    chans.sort(key=lambda c: -c["subs"])
    out["channels"] = chans[:20]
    out["n_channels"] = len(chans)

    items = bk.get("items", [])
    for b in items:
        b["topics"] = [TOPIC_NAME.get(t, t) for t in topics_of(b["t"], product=True)]
        for t in topics_of(b["t"], product=True):
            heat.setdefault(t, {"yt": 0, "book": 0})["book"] += b["sp"]
    out["books_best"] = [b for b in items if "best" in b.get("kind", [])][:12]
    six = (date.today() - timedelta(days=183)).isoformat()
    out["books_new"] = sorted([b for b in items if b.get("d", "") >= six], key=lambda b: b["d"], reverse=True)[:10]

    own = {}
    for c in own_courses or []:
        for t in topics_of(c.get("title", "")):
            own[t] = own.get(t, 0) + 1
    ty, tb = sum(v["yt"] for v in heat.values()), sum(v["book"] for v in heat.values())
    n_src = (ty > 0) + (tb > 0) or 1  # 한쪽 출처만 있으면 그 비중이 곧 열기
    rows = []
    for t, v in heat.items():
        y, b = v["yt"] / (ty or 1) * 100, v["book"] / (tb or 1) * 100
        rows.append({"topic": TOPIC_NAME.get(t, t), "yt": round(y, 1), "book": round(b, 1), "heat": round((y + b) / n_src, 1), "own": own.get(t, 0)})
    rows.sort(key=lambda r: -r["heat"])
    out["heat"] = rows
    return out
