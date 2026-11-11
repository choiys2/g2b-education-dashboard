#!/usr/bin/env python3
"""
교과서·교사용 콘텐츠 여론 레이더 -> history/opinion_radar.json (네이버 블로그·카페 공개 검색 결과)

  - 출판사별 교과서·교사용 콘텐츠 언급량(최근 30일·주별)과 비상 관련 최근 글 제목·링크만 저장
  - 글쓴이 이름·아이디·본문은 저장하지 않는다. 링크는 https 만.
  - 주 1회(opinion_radar.yml). 키: NAVER_CLIENT_ID / NAVER_CLIENT_SECRET
  python opinion_radar.py
"""
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "history" / "opinion_radar.json"
BRANDS = {
    "비상": ["비상 교과서", "비상교육 교과서", "비상 지도서", "비바샘 수업자료"],
    "천재": ["천재 교과서", "천재교육 교과서", "티셀파 수업자료"],
    "미래엔": ["미래엔 교과서", "엠티처 수업자료"],
    "동아": ["동아출판 교과서", "두클래스 수업자료"],
    "지학사": ["지학사 교과서"],
}
POS = re.compile(r"좋|추천|편해|편리|유용|최고|만족|도움|알차|깔끔")
NEG = re.compile(r"불편|아쉽|별로|어렵|오류|불만|부족|비싸")
TAGS = [("선정·채택", r"선정|채택|심의|협의회"), ("수업자료", r"자료|PPT|활동지|수업"), ("평가", r"평가|문제|시험"), ("디지털", r"디지털|AI|온라인|플랫폼|AIDT")]


def strip(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def search(kind, q, cid, sec):
    url = f"https://openapi.naver.com/v1/search/{kind}.json?" + urllib.parse.urlencode({"query": q, "display": 100, "sort": "date"})
    req = urllib.request.Request(url, headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": sec})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8")).get("items", [])


def main():
    cid, sec = os.environ.get("NAVER_CLIENT_ID", ""), os.environ.get("NAVER_CLIENT_SECRET", "")
    if not cid or not sec:
        print("NAVER 키 없음 - 건너뜀")
        return 0
    today = date.today()
    since = today - timedelta(days=30)
    prev = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    weekly = defaultdict(dict, {k: dict(v) for k, v in (prev.get("weekly") or {}).items()})
    counts, recent, tags, tone, diag = Counter(), [], Counter(), Counter(), []
    seen = set()
    for brand, qs in BRANDS.items():
        for q in qs:
            for kind in ("blog", "cafearticle"):
                try:
                    items = search(kind, q, cid, sec)
                except Exception as e:  # noqa: BLE001
                    diag.append(f"{kind} {q}: {type(e).__name__}")
                    continue
                for it in items:
                    link = it.get("link") or ""
                    if link in seen:
                        continue
                    pd = it.get("postdate") or ""
                    d = datetime.strptime(pd, "%Y%m%d").date() if re.fullmatch(r"\d{8}", pd) else None
                    if kind == "blog" and (not d or d < since):
                        continue
                    seen.add(link)
                    counts[brand] += 1
                    t = strip(it.get("title"))
                    if d:
                        wk = (d - timedelta(days=d.weekday())).isoformat()
                        weekly[brand][wk] = weekly[brand].get(wk, 0) + 1
                    if brand == "비상":
                        body = t + " " + strip(it.get("description"))
                        for name, rx in TAGS:
                            if re.search(rx, body):
                                tags[name] += 1
                        tone["긍정"] += bool(POS.search(body))
                        tone["부정"] += bool(NEG.search(body))
                        if link.startswith("https://") and len(recent) < 40:
                            recent.append({"d": d.isoformat() if d else "", "t": t[:120], "u": link, "src": "블로그" if kind == "blog" else "카페"})
                time.sleep(0.15)
    total = sum(counts.values()) or 1
    keep = (today - timedelta(weeks=26)).isoformat()
    weekly = {b: {w: n for w, n in sorted(v.items()) if w >= keep} for b, v in weekly.items()}
    OUT.write_text(json.dumps({"generated": today.isoformat(), "window_days": 30,
                               "share": [{"brand": b, "n": counts[b], "pct": round(counts[b] / total * 100, 1)} for b in BRANDS],
                               "weekly": weekly, "tags": tags.most_common(), "tone": dict(tone),
                               "recent": sorted(recent, key=lambda x: x["d"], reverse=True)[:30], "diag": diag[:20],
                               "note": "네이버 블로그(최근 30일)·카페 검색 결과 기준, 검색어 묶음이 같은 기준으로 비교한 상대 언급량"},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print("여론 레이더:", dict(counts), "· 진단", len(diag))
    return 0


if __name__ == "__main__":
    sys.exit(main())
