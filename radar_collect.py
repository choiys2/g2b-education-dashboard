#!/usr/bin/env python3
"""
에듀테크 레이더(https://edutech-radar.netlify.app/) 기사 목록 수집 - 매일 06:40 KST(radar.yml).

클라우드 분석 세션은 이 주소에 직접 접속할 수 없어, GitHub 러너가 대신 열어 history/edutech_radar.json 에 남긴다.
  - 페이지가 불러오는 JSON 응답(fetch/XHR)을 그대로 가로채 기사 배열을 찾는다(가장 정확).
  - JSON 이 없으면 화면의 기사 카드(링크·제목·날짜 텍스트)를 읽는다.
  - 실패하면 status 에 이유를 적고 기사 목록은 비운다(분석 쪽이 '사이트 미확인'으로 처리).
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://edutech-radar.netlify.app/"
OUT = Path("history/edutech_radar.json")
KST = timezone(timedelta(hours=9))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
DATE_RE = re.compile(r"(20\d{2})[.\-/년 ]\s?(\d{1,2})[.\-/월 ]\s?(\d{1,2})")


def _articles_in(obj, depth=0):
    """JSON 안에서 '제목+링크'를 가진 객체 배열을 찾는다."""
    if depth > 5:
        return []
    if isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj[:5]):
        keys = set().union(*(x.keys() for x in obj[:5]))
        if any(k in keys for k in ("title", "headline", "name")) and any(k in keys for k in ("url", "link", "href")):
            return obj
    if isinstance(obj, dict):
        best = []
        for v in obj.values():
            r = _articles_in(v, depth + 1)
            if len(r) > len(best):
                best = r
        return best
    return []


def _norm(a):
    g = lambda *ks: next((str(a[k]) for k in ks if a.get(k) not in (None, "")), "")
    d = g("date", "published", "publishedAt", "pubDate", "createdAt", "time", "datetime")
    m = DATE_RE.search(d)
    return {"title": g("title", "headline", "name")[:300], "url": g("url", "link", "href"),
            "date": "-".join([m.group(1), m.group(2).zfill(2), m.group(3).zfill(2)]) if m else d[:25],
            "source": g("source", "press", "publisher", "media", "outlet", "site")[:80],
            "summary": g("summary", "description", "desc", "snippet", "content", "abstract")[:600],
            "category": g("category", "tag", "tags", "section", "topic")[:80]}


JS_CARDS = """() => [...document.querySelectorAll('a[href^="http"]')]
  .filter(a => !a.href.includes(location.host) && (a.innerText || '').trim().length > 12)
  .map(a => { const card = a.closest('article, li, .card, [class*=card], [class*=item], div') || a;
              return {title: a.innerText.trim().split('\\n')[0].slice(0, 300), url: a.href, text: (card.innerText || '').slice(0, 800)}; })"""


def main():
    now = datetime.now(KST)
    out = {"collected_at": now.strftime("%Y-%m-%d %H:%M"), "url": URL, "status": "", "method": "", "items": []}
    jsons = []
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            page = b.new_page(user_agent=UA, locale="ko-KR")

            def on_resp(r):
                try:
                    if "json" in (r.headers.get("content-type") or "") or r.url.endswith(".json"):
                        jsons.append((r.url, r.json()))
                except Exception:
                    pass
            page.on("response", on_resp)
            resp = page.goto(URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(4000)
            out["http"] = resp.status if resp else None
            best_url, best = "", []
            for u, j in jsons:
                arr = _articles_in(j)
                if len(arr) > len(best):
                    best_url, best = u, arr
            if best:
                out["method"], out["source_json"] = "json", best_url
                out["items"] = [_norm(a) for a in best]
            else:
                cards = page.evaluate(JS_CARDS)
                seen, items = set(), []
                for c in cards:
                    if c["url"] in seen:
                        continue
                    seen.add(c["url"])
                    m = DATE_RE.search(c["text"])
                    items.append({"title": c["title"], "url": c["url"],
                                  "date": "-".join([m.group(1), m.group(2).zfill(2), m.group(3).zfill(2)]) if m else "",
                                  "source": "", "summary": re.sub(r"\s+", " ", c["text"])[:600], "category": ""})
                out["method"], out["items"] = "dom", items
            out["page_title"] = page.title()
            out["page_text_head"] = re.sub(r"\s+", " ", page.evaluate("() => document.body.innerText"))[:1500]
            b.close()
        out["status"] = "ok" if out["items"] else "empty"
    except Exception as e:
        out["status"] = f"error: {str(e).splitlines()[0][:200]}"
    out["json_urls"] = [u for u, _ in jsons][:20]
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"레이더 수집: {out['status']} · 방식 {out['method']} · 기사 {len(out['items'])}건 · JSON 응답 {len(jsons)}개")
    for it in out["items"][:8]:
        print("  ", it["date"], "|", it["source"], "|", it["title"][:80])
    return 0


if __name__ == "__main__":
    sys.exit(main())
