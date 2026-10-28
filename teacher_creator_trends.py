#!/usr/bin/env python3
"""
교사 트렌드 수집(주 1회, mall_catalog.yml) - 유튜브 교사 크리에이터 + 교사 대상 도서.

  - YouTube Data API v3 (YOUTUBE_API_KEY): 교사 관련 검색어로 채널을 찾고 구독자·최근 영상 조회수를 모은다.
    주당 할당량 사용 약 800 유닛(무료 일 10,000).
    채널 소개에 공개로 적힌 인스타그램 계정만 함께 표시한다(인스타그램 자체는 수집하지 않음).
  - 알라딘 Open API (ALADIN_TTB_KEY): 교사·수업 관련 검색어의 판매지수순 도서와 신간.
공개 채널명·도서명만 저장하고 개인 연락처(이메일·전화)는 저장하지 않는다.
키가 없으면 그 출처만 건너뛰고 기존 값을 유지한다.
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

OUT = Path("history/teacher_creator_trends.json")
YT = "https://www.googleapis.com/youtube/v3/"
YT_QUERIES = ["초등교사 브이로그", "중등교사 브이로그", "교사 브이로그", "선생님 유튜버 학급경영", "초등 수업 아이디어 교사",
              "교사 AI 활용 수업", "교사 일상", "임용 교사 공부"]
TEACHER_RE = re.compile(r"교사|선생님|쌤|teacher|교실|학급|임용", re.I)
INSTA_RE = re.compile(r"(?:instagram\.com/|인스타(?:그램)?\s*[:：]?\s*@?)([A-Za-z0-9._]{3,30})", re.I)
BOOK_QUERIES = ["교사", "학급경영", "수업 설계", "초등교사", "교사 AI", "생활지도", "문해력 수업", "평가 루브릭"]
BOOK_CAT_RE = re.compile(r"교육학|교사|교육|수업|학교")
MIN_SUBS = 3000


def get(url, params):
    with urllib.request.urlopen(url + "?" + urllib.parse.urlencode(params), timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def youtube(key, prev):
    ids = set()
    for q in YT_QUERIES:
        try:
            d = get(YT + "search", {"part": "snippet", "q": q, "type": "channel", "regionCode": "KR",
                                    "relevanceLanguage": "ko", "maxResults": 25, "key": key})
            ids.update(i["snippet"]["channelId"] for i in d.get("items", []))
        except Exception as e:
            print(f"  [유튜브 검색 실패] {q}: {e}", file=sys.stderr)
    ids.update(c["id"] for c in prev.get("channels", []))  # 지난주 채널은 계속 추적(증가 추이)
    chans, idl = [], list(ids)
    for i in range(0, len(idl), 50):
        d = get(YT + "channels", {"part": "snippet,statistics,contentDetails", "id": ",".join(idl[i:i + 50]), "key": key})
        for c in d.get("items", []):
            sn, st = c["snippet"], c.get("statistics", {})
            text = sn.get("title", "") + " " + sn.get("description", "")
            subs = int(st.get("subscriberCount", 0) or 0)
            if not TEACHER_RE.search(text) or subs < MIN_SUBS or st.get("hiddenSubscriberCount"):
                continue
            m = INSTA_RE.search(sn.get("description", ""))
            chans.append({"id": c["id"], "title": sn.get("title", ""), "handle": sn.get("customUrl", ""),
                          "subs": subs, "views": int(st.get("viewCount", 0) or 0), "videos": int(st.get("videoCount", 0) or 0),
                          "insta": m.group(1).rstrip(".") if m else "",
                          "uploads": c.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads", "")})
    chans.sort(key=lambda c: -c["subs"])
    chans = chans[:40]
    for c in chans:  # 최근 영상 5개 조회수·제목(주제 판정용)
        c["recent"] = []
        if not c["uploads"]:
            continue
        try:
            pl = get(YT + "playlistItems", {"part": "contentDetails", "playlistId": c["uploads"], "maxResults": 5, "key": key})
            vids = [i["contentDetails"]["videoId"] for i in pl.get("items", [])]
            if vids:
                vd = get(YT + "videos", {"part": "snippet,statistics", "id": ",".join(vids), "key": key})
                c["recent"] = [{"id": v["id"], "t": v["snippet"]["title"][:100], "d": v["snippet"]["publishedAt"][:10],
                                "v": int(v.get("statistics", {}).get("viewCount", 0) or 0)} for v in vd.get("items", [])]
        except Exception as e:
            print(f"  [영상 조회 실패] {c['title']}: {e}", file=sys.stderr)
        c.pop("uploads", None)
    return chans


def books(key):
    out = {}
    for q in BOOK_QUERIES:
        for sort, tag in (("SalesPoint", "best"), ("PublishTime", "new")):
            try:
                d = get("http://www.aladin.co.kr/ttb/api/ItemSearch.aspx",
                        {"ttbkey": key, "Query": q, "QueryType": "Keyword", "SearchTarget": "Book", "Sort": sort,
                         "MaxResults": 20, "output": "js", "Version": "20131101"})
            except Exception as e:
                print(f"  [알라딘 실패] {q}/{sort}: {e}", file=sys.stderr)
                continue
            for it in d.get("item", []):
                if not BOOK_CAT_RE.search(it.get("categoryName", "")):
                    continue
                b = out.setdefault(it["itemId"], {"id": it["itemId"], "t": it.get("title", "")[:120], "a": it.get("author", "")[:60],
                                                  "pub": it.get("publisher", ""), "d": it.get("pubDate", ""),
                                                  "sp": int(it.get("salesPoint", 0) or 0), "cat": it.get("categoryName", "").split(">")[-1],
                                                  "link": it.get("link", ""), "q": [], "kind": set()})
                b["q"].append(q)
                b["kind"].add(tag)
    rows = []
    for b in out.values():
        b["kind"] = sorted(b["kind"])
        rows.append(b)
    rows.sort(key=lambda b: -b["sp"])
    return rows[:80]


def main():
    prev = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    today = date.today().isoformat()
    out = dict(prev)
    yk, ak = os.environ.get("YOUTUBE_API_KEY"), os.environ.get("ALADIN_TTB_KEY")
    if yk:
        ch = youtube(yk, prev.get("youtube", {}))
        if ch:
            hist = prev.get("youtube", {}).get("subs_hist", {})  # {채널id: {날짜: 구독자}} 최근 12주
            for c in ch:
                h = hist.setdefault(c["id"], {})
                h[today] = c["subs"]
                for k in sorted(h)[:-12]:
                    h.pop(k)
            hist = {k: v for k, v in hist.items() if any(c["id"] == k for c in ch)}
            out["youtube"] = {"captured_date": today, "channels": ch, "subs_hist": hist}
        print(f"유튜브 교사 채널 {len(ch)}개")
    else:
        print("YOUTUBE_API_KEY 없음 - 유튜브 건너뜀")
    if ak:
        bk = books(ak)
        if bk:
            out["books"] = {"captured_date": today, "items": bk}
        print(f"교사 도서 {len(bk)}권")
    else:
        print("ALADIN_TTB_KEY 없음 - 도서 건너뜀")
    if out != prev:
        OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
