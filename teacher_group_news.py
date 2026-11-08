#!/usr/bin/env python3
"""
교사단체 최근 소식 -> history/teacher_group_news.json (주 1회, teacher_group_news.yml)

static_data/teacher_groups.json 의 전국 협회·교육청 연구회·점수 상위 연구회 이름으로 최근 180일 뉴스를 찾는다.
  1) 네이버 검색 API(news) - NAVER_CLIENT_ID/SECRET (앱에 '검색' API 가 켜져 있어야 함)
  2) 안 되면 구글 뉴스 RSS(키 불필요)
기사 제목·언론사·날짜·링크만 저장한다(본문·기사 속 개인 연락처는 저장하지 않음).
"""
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

SRC = Path("static_data/teacher_groups.json")
OUT = Path("history/teacher_group_news.json")
DAYS = 180
PER = 3
UA = {"User-Agent": "Mozilla/5.0 (dashboard news collector)"}
TAG = re.compile(r"<[^>]+>")


def short(name):
    n = re.sub(r"\(사\)|\([^)]*\)", " ", name)
    return re.sub(r"\s+", " ", n).strip() or name


def get(url, headers=None):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def naver(q):
    cid, sec = os.environ.get("NAVER_CLIENT_ID"), os.environ.get("NAVER_CLIENT_SECRET")
    if not (cid and sec):
        return None
    url = "https://openapi.naver.com/v1/search/news.json?" + urllib.parse.urlencode({"query": f'"{q}"', "display": 20, "sort": "date"})
    try:
        d = json.loads(get(url, {"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": sec}))
    except Exception as e:
        print(f"  [네이버] {str(e)[:80]}", file=sys.stderr)
        return None
    out = []
    for it in d.get("items", []):
        try:
            dt = parsedate_to_datetime(it["pubDate"]).date()
        except Exception:
            continue
        host = urllib.parse.urlparse(it.get("originallink") or it.get("link") or "").netloc.replace("www.", "")
        out.append({"t": html.unescape(TAG.sub("", it.get("title", ""))), "d": dt.isoformat(), "src": host,
                    "u": it.get("originallink") or it.get("link")})
    return out


def google(q):
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": f'"{q}" when:180d', "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
    try:
        root = ET.fromstring(get(url))
    except Exception as e:
        print(f"  [구글] {str(e)[:80]}", file=sys.stderr)
        return []
    out = []
    for it in root.iter("item"):
        try:
            dt = parsedate_to_datetime(it.findtext("pubDate")).date()
        except Exception:
            continue
        t = it.findtext("title") or ""
        src = it.findtext("source") or ""
        if src and t.endswith(" - " + src):
            t = t[: -len(src) - 3]
        out.append({"t": t, "d": dt.isoformat(), "src": src, "u": it.findtext("link")})
    return out


def main():
    g = json.loads(SRC.read_text(encoding="utf-8"))
    names = [o["name"] for o in g.get("national", [])] + [o["name"] for o in g.get("regional", [])] + \
            [o["name"] for o in g.get("groups", [])[:30]]
    since = (date.today() - timedelta(DAYS)).isoformat()
    res, via = {}, {"naver": 0, "google": 0}
    use_naver = True
    for nm in dict.fromkeys(names):
        q = short(nm)
        if len(q) < 3 or q.startswith("확인"):
            continue
        items = naver(q) if use_naver else None
        if items is None:
            use_naver = False  # 키 없음·검색 API 미허용이면 이후는 구글 RSS 로만
            items = google(q)
            via["google"] += 1
        else:
            via["naver"] += 1
        key = q.replace(" ", "")
        items = [i for i in items if i["d"] >= since and key[:4] in i["t"].replace(" ", "")]  # 제목에 단체명이 있는 기사만
        seen, keep = set(), []
        for i in sorted(items, key=lambda i: i["d"], reverse=True):
            k = re.sub(r"\W", "", i["t"])[:24]
            if k in seen:
                continue
            seen.add(k)
            keep.append(i)
        if keep:
            res[nm] = {"n": len(keep), "items": keep[:PER]}
        time.sleep(0.3)
    if not res:
        print("수집된 소식 없음 - 기존 파일 유지")
        return 0
    out = {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "since": since, "via": via, "orgs": res}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"저장: {OUT} · 소식 있는 단체 {len(res)}곳 / 조회 {len(dict.fromkeys(names))}곳 · {via}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
