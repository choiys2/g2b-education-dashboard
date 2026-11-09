#!/usr/bin/env python3
"""
레이더 수집본의 구글 뉴스 중계 링크 -> 원문 URL·원문 발행일 (radar.yml 에서 radar_collect.py 다음에 실행)

07:00 브리핑 세션은 최신 기사를 웹 검색으로 찾지 못하는 때가 많아(색인 지연) 원문 확인을 러너가 대신 한다.
브라우저로 중계 링크를 열어 리디렉션된 최종 URL과 article:published_time 을 읽는다
(2026-11-09 실측: 순차 140건 139건 성공·769초 -> 동시 6탭으로 단축). 시간 예산 BUDGET 초를 넘기면 처리한 만큼만 저장.
  items[i].orig      원문 URL
  items[i].orig_date 원문 메타 발행 시각(있을 때만)
  resolve: {tried, ok, dated, sec}
"""
import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.async_api import async_playwright

P = Path("history/edutech_radar.json")
KST = timezone(timedelta(hours=9))
HOURS, CAP, BUDGET, TABS, WAIT_MS = 96, 160, 420, 6, 12000
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
META_JS = """() => { const q = s => (document.querySelector(s) || {}).content || '';
  return q('meta[property="article:published_time"]') || q('meta[name="pubdate"]') || q('meta[itemprop="datePublished"]')
      || q('meta[name="article:published_time"]') || ''; }"""


async def one(ctx, x, stats):
    page = await ctx.new_page()
    try:
        await page.goto(x["url"], wait_until="commit", timeout=WAIT_MS)
        try:
            await page.wait_for_url(lambda u: "news.google.com" not in u and "consent.google" not in u, timeout=WAIT_MS)
        except Exception:
            pass
        u = page.url
        if u.startswith("http") and "google.com" not in u:
            x["orig"] = u
            stats["ok"] += 1
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=5000)
                m = await page.evaluate(META_JS)
                if m:
                    x["orig_date"] = m[:25]
                    stats["dated"] += 1
            except Exception:
                pass
    except Exception:
        pass
    finally:
        await page.close()


async def run(todo, stats):
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(user_agent=UA, locale="ko-KR")
        await ctx.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,mp4,css}", lambda r: r.abort())
        sem = asyncio.Semaphore(TABS)

        async def guarded(x):
            async with sem:
                await one(ctx, x, stats)
        try:
            await asyncio.wait_for(asyncio.gather(*(guarded(x) for x in todo)), timeout=BUDGET)
        except asyncio.TimeoutError:
            print("시간 예산 초과 - 처리한 만큼만 저장", flush=True)
        await b.close()


def main():
    d = json.loads(P.read_text(encoding="utf-8"))
    items = d.get("items") or []
    cut = (datetime.now(KST) - timedelta(hours=HOURS)).strftime("%Y-%m-%d %H:%M")
    todo = [x for x in items if "news.google.com" in (x.get("url") or "") and (x.get("date") or "") >= cut and not x.get("orig")][:CAP]
    t0, stats = time.time(), {"ok": 0, "dated": 0}
    if todo:
        try:
            asyncio.run(run(todo, stats))
        except Exception as e:
            print(f"원문 확인 중단: {type(e).__name__}: {str(e)[:120]}", flush=True)
    d["resolve"] = {"tried": len(todo), **stats, "sec": round(time.time() - t0), "hours": HOURS}
    P.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"원문 확인: {stats['ok']}/{len(todo)}건 · 발행일 {stats['dated']}건 · {d['resolve']['sec']}초", flush=True)


if __name__ == "__main__":
    main()
