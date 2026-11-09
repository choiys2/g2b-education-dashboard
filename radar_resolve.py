#!/usr/bin/env python3
"""
레이더 수집본의 구글 뉴스 중계 링크 -> 원문 URL·원문 발행일 (radar.yml 에서 radar_collect.py 다음에 실행)

07:00 브리핑 세션은 최신 기사를 웹 검색으로 찾지 못하는 때가 많아(색인 지연) 원문 확인을 러너가 대신 한다.
최근 HOURS 시간 기사 중 최대 CAP 건을 브라우저로 열어 리디렉션된 최종 URL과 article:published_time 을 남긴다.
  items[i].orig      원문 URL(실패하면 키 없음)
  items[i].orig_date 원문 메타의 발행 시각(있을 때만)
  resolve: {tried, ok, sec}
"""
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

P = Path("history/edutech_radar.json")
KST = timezone(timedelta(hours=9))
HOURS, CAP, WAIT_MS = 96, 140, 9000
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
META_JS = """() => { const q = s => (document.querySelector(s) || {}).content || '';
  return q('meta[property="article:published_time"]') || q('meta[name="pubdate"]') || q('meta[itemprop="datePublished"]')
      || q('meta[name="article:published_time"]') || ''; }"""


def main():
    d = json.loads(P.read_text(encoding="utf-8"))
    items = d.get("items") or []
    cut = (datetime.now(KST) - timedelta(hours=HOURS)).strftime("%Y-%m-%d %H:%M")
    todo = [x for x in items if "news.google.com" in (x.get("url") or "") and (x.get("date") or "") >= cut and not x.get("orig")][:CAP]
    t0, ok = time.time(), 0
    if todo:
        with sync_playwright() as p:
            b = p.chromium.launch()
            ctx = b.new_context(user_agent=UA, locale="ko-KR")
            ctx.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,mp4}", lambda r: r.abort())
            page = ctx.new_page()
            for x in todo:
                try:
                    page.goto(x["url"], wait_until="commit", timeout=WAIT_MS)
                    try:
                        page.wait_for_url(lambda u: "news.google.com" not in u and "consent.google" not in u, timeout=WAIT_MS)
                    except Exception:
                        pass
                    u = page.url
                    if u.startswith("http") and "google.com" not in u:
                        x["orig"] = u
                        ok += 1
                        try:
                            page.wait_for_load_state("domcontentloaded", timeout=4000)
                            m = page.evaluate(META_JS)
                            if m:
                                x["orig_date"] = m[:25]
                        except Exception:
                            pass
                except Exception:
                    pass
            b.close()
    d["resolve"] = {"tried": len(todo), "ok": ok, "sec": round(time.time() - t0), "hours": HOURS}
    P.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"원문 확인: {ok}/{len(todo)}건 · {d['resolve']['sec']}초")


if __name__ == "__main__":
    main()
