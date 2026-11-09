#!/usr/bin/env python3
"""
레이더 수집본의 구글 뉴스 중계 링크 -> 원문 URL·원문 발행일 (radar.yml 에서 radar_collect.py 다음에 실행)

07:00 브리핑 세션은 최신 기사를 웹 검색으로 찾지 못하는 때가 많아(색인 지연) 원문 확인을 러너가 대신 한다.
브라우저를 쓰지 않고 구글 뉴스 기사 페이지의 서명값(data-n-a-sg/ts)으로 batchexecute 를 불러 원문 URL을 얻는다.
병렬 8개 · 전체 시간 예산 BUDGET 초 · 끊겨도 처리한 만큼 저장한다.
  items[i].orig      원문 URL
  items[i].orig_date 원문 메타 발행 시각(있을 때만)
  resolve: {tried, ok, dated, sec}
"""
import json
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

P = Path("history/edutech_radar.json")
KST = timezone(timedelta(hours=9))
HOURS, CAP, BUDGET, WORKERS = 96, 160, 480, 8
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept-Language": "ko-KR,ko;q=0.9"}
META = re.compile(r'<meta[^>]+(?:property|name|itemprop)=["\'](?:article:published_time|pubdate|datePublished|og:pubdate)["\'][^>]*content=["\']([^"\']+)', re.I)
META2 = re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name|itemprop)=["\'](?:article:published_time|pubdate|datePublished)["\']', re.I)


def _get(url, data=None, timeout=10, headers=None):
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(400_000).decode("utf-8", "replace"), r.geturl()


def decode(gurl):
    aid = urllib.parse.urlparse(gurl).path.rstrip("/").split("/")[-1]
    html, _ = _get(f"https://news.google.com/rss/articles/{aid}")
    sg, ts = re.search(r'data-n-a-sg="([^"]+)"', html), re.search(r'data-n-a-ts="([^"]+)"', html)
    if not (sg and ts):
        return None
    inner = ["garturlreq", [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None, None, None, None, 0, 1],
                            "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0], aid, int(ts.group(1)), sg.group(1)]
    body = urllib.parse.urlencode({"f.req": json.dumps([[["Fbv4je", json.dumps(inner), None, "generic"]]])}).encode()
    txt, _ = _get("https://news.google.com/_/DotsSplashUi/data/batchexecute", data=body,
                  headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"})
    part = txt.split("\n\n", 1)[1] if "\n\n" in txt else txt
    arr = json.loads(part)
    u = json.loads(arr[0][2])[1]
    return u if isinstance(u, str) and u.startswith("http") else None


def pubdate(url):
    try:
        html, _ = _get(url, timeout=6)
    except Exception:
        return None
    m = META.search(html) or META2.search(html)
    return m.group(1)[:25] if m else None


def work(x):
    try:
        u = decode(x["url"])
    except Exception:
        return x, None, None
    return x, u, (pubdate(u) if u else None)


def main():
    d = json.loads(P.read_text(encoding="utf-8"))
    items = d.get("items") or []
    cut = (datetime.now(KST) - timedelta(hours=HOURS)).strftime("%Y-%m-%d %H:%M")
    todo = [x for x in items if "news.google.com" in (x.get("url") or "") and (x.get("date") or "") >= cut and not x.get("orig")][:CAP]
    t0, ok, dated = time.time(), 0, 0
    ex = ThreadPoolExecutor(WORKERS)
    futs = [ex.submit(work, x) for x in todo]
    try:
        for f in as_completed(futs, timeout=BUDGET):
            x, u, pd = f.result()
            if u:
                x["orig"] = u
                ok += 1
                if pd:
                    x["orig_date"] = pd
                    dated += 1
    except Exception:
        pass  # 시간 예산 초과 - 처리한 만큼만 저장
    ex.shutdown(wait=False, cancel_futures=True)
    d["resolve"] = {"tried": len(todo), "ok": ok, "dated": dated, "sec": round(time.time() - t0), "hours": HOURS}
    P.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"원문 확인: {ok}/{len(todo)}건 · 발행일 {dated}건 · {d['resolve']['sec']}초")


if __name__ == "__main__":
    main()
    import os
    os._exit(0)  # 남은 스레드(타임아웃 대기)를 기다리지 않고 끝낸다
