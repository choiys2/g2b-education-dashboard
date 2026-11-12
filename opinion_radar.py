#!/usr/bin/env python3
"""
교과서·교사용 콘텐츠 여론 레이더 -> history/opinion_radar.json (다음(카카오) 블로그·카페 공개 검색, 없으면 구글 뉴스)

  - 출판사별 교과서·교사용 콘텐츠 언급량(최근 30일·주별)과 비상 관련 최근 글 제목·링크만 저장
  - 글쓴이 이름·아이디·본문은 저장하지 않는다. 링크는 https 만.
  - 주 1회(opinion_radar.yml). 키: KAKAO_REST_KEY(네이버 검색 API 는 중단)
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
# 교사 플랫폼별 반응(교사 생태계 비교 탭) - 같은 방식, 제목·링크·날짜만
PLATFORMS = {
    "비바샘": ["비바샘"],
    "엠티처": ["엠티처"],
    "T셀파": ["티셀파", "T셀파"],
    "두클래스": ["두클래스"],
    "아이스크림S·쌤튜브": ["아이스크림S", "쌤튜브"],
    "티처빌·쌤동네": ["티처빌 연수", "쌤동네"],
}
POS = re.compile(r"좋|추천|편해|편리|유용|최고|만족|도움|알차|깔끔")
NEG = re.compile(r"불편|아쉽|별로|어렵|오류|불만|부족|비싸")
TAGS = [("선정·채택", r"선정|채택|심의|협의회"), ("수업자료", r"자료|PPT|활동지|수업"), ("평가", r"평가|문제|시험"), ("디지털", r"디지털|AI|온라인|플랫폼|AIDT")]


def strip(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def kakao(kind, q, key):
    """카카오(다음) 블로그·카페 검색 - 최신순 50건씩 2쪽. 블로그명·카페명·본문은 저장하지 않는다."""
    out = []
    for page in (1, 2):
        url = f"https://dapi.kakao.com/v2/search/{kind}?" + urllib.parse.urlencode({"query": q, "sort": "recency", "size": 50, "page": page})
        req = urllib.request.Request(url, headers={"Authorization": "KakaoAK " + key})
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8"))
        for it in d.get("documents", []):
            out.append({"title": it.get("title", ""), "link": it.get("url", ""), "postdate": (it.get("datetime") or "")[:10].replace("-", ""),
                        "description": it.get("contents", "")})
        if (d.get("meta") or {}).get("is_end"):
            break
        time.sleep(0.2)
    return out


def google(q):
    """네이버 검색 키가 없거나 권한이 없을 때: 구글 뉴스 RSS(언론 보도) 최근 30일."""
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": f'"{q}" when:30d', "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (dashboard-collector)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        root = ET.fromstring(r.read())
    out = []
    for it in root.iter("item"):
        try:
            d = parsedate_to_datetime(it.findtext("pubDate")).date()
        except Exception:  # noqa: BLE001
            continue
        out.append({"title": it.findtext("title") or "", "link": it.findtext("link") or "", "postdate": d.strftime("%Y%m%d"), "description": ""})
    return out


def main():
    # 우선순위: 카카오(다음) 블로그·카페 → 구글 뉴스(언론). 네이버 검색 API 는 중단돼 쓰지 않는다.
    kkey = os.environ.get("KAKAO_REST_KEY", "")
    mode = "kakao" if kkey else "google"
    if mode == "kakao":
        try:
            kakao("blog", "교과서", kkey)
        except Exception as e:  # noqa: BLE001
            print("카카오 검색 사용 불가:", getattr(e, "code", type(e).__name__), "- 구글 뉴스로 대체")
            mode = "google"
    today = date.today()
    since = today - timedelta(days=30)
    prev = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    weekly = defaultdict(dict, {k: dict(v) for k, v in (prev.get("weekly") or {}).items()})
    counts, recent, tags, tone, diag = Counter(), [], Counter(), Counter(), []
    seen = set()
    for brand, qs in BRANDS.items():
        for q in qs:
            for kind in (("blog", "cafe") if mode == "kakao" else ("news",)):
                try:
                    items = kakao(kind, q, kkey) if mode == "kakao" else google(q)
                except Exception as e:  # noqa: BLE001
                    diag.append(f"{kind} {q}: {getattr(e, 'code', type(e).__name__)}")
                    continue
                for it in items:
                    link = it.get("link") or ""
                    if link in seen:
                        continue
                    pd = it.get("postdate") or ""
                    d = datetime.strptime(pd, "%Y%m%d").date() if re.fullmatch(r"\d{8}", pd) else None
                    if not d or d < since:  # 블로그·카페·뉴스 모두 최근 30일만
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
                            recent.append({"d": d.isoformat() if d else "", "t": t[:120], "u": link, "src": {"blog": "블로그", "cafe": "카페", "news": "언론"}[kind]})
                time.sleep(0.15)
    plat = {}
    for pn, qs in PLATFORMS.items():
        ps, pc, ptone, pw, ptags = set(), 0, Counter(), Counter(), Counter()
        for q in qs:
            for kind in (("blog", "cafe") if mode == "kakao" else ("news",)):
                try:
                    items = kakao(kind, q, kkey) if mode == "kakao" else google(q)
                except Exception as e:  # noqa: BLE001
                    diag.append(f"{kind} {q}: {getattr(e, 'code', type(e).__name__)}")
                    continue
                for it in items:
                    link, pd = it.get("link") or "", it.get("postdate") or ""
                    d = datetime.strptime(pd, "%Y%m%d").date() if re.fullmatch(r"\d{8}", pd) else None
                    if link in ps or not d or d < since:
                        continue
                    ps.add(link)
                    pc += 1
                    body = strip(it.get("title")) + " " + strip(it.get("description"))
                    ptone["긍정"] += bool(POS.search(body))
                    ptone["부정"] += bool(NEG.search(body))
                    pw[(d - timedelta(days=d.weekday())).isoformat()] += 1
                    for name, rx in TAGS:
                        if re.search(rx, body):
                            ptags[name] += 1
                time.sleep(0.15)
        plat[pn] = {"n": pc, "pos": ptone["긍정"], "neg": ptone["부정"], "weekly": dict(sorted(pw.items())[-6:]), "tags": ptags.most_common(4)}
    total = sum(counts.values()) or 1
    keep = (today - timedelta(weeks=26)).isoformat()
    weekly = {b: {w: n for w, n in sorted(v.items()) if w >= keep} for b, v in weekly.items()}
    OUT.write_text(json.dumps({"generated": today.isoformat(), "window_days": 30,
                               "share": [{"brand": b, "n": counts[b], "pct": round(counts[b] / total * 100, 1)} for b in BRANDS],
                               "weekly": weekly, "tags": tags.most_common(), "tone": dict(tone), "platforms": plat,
                               "recent": sorted(recent, key=lambda x: x["d"], reverse=True)[:30], "diag": diag[:20],
                               "mode": mode,
                               "note": ("다음(카카오) 블로그·카페 최근 30일 글 기준" if mode == "kakao" else "구글 뉴스 최근 30일 언론 보도 기준(카카오 키 없음)") + ", 같은 검색어 묶음으로 비교한 상대 언급량"},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print("여론 레이더:", mode, dict(counts), "· 진단", len(diag))
    return 0


if __name__ == "__main__":
    sys.exit(main())
