#!/usr/bin/env python3
"""
(일회성 점검) 티처몰·아이스크림몰 공개 화면 구조 확인 — 수집기(competitor_mall_scrape.py) 작성 전 사전 조사.
robots.txt 와 공개 페이지의 메뉴(베스트·신상품·카테고리·세트) 링크, 상품 카드 후보만 로그로 출력한다. 저장하지 않음.
"""
import re
import sys
import urllib.request
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright

STARTS = ["https://www.teacherville.co.kr/", "https://shop.teacherville.co.kr/", "https://www.teachermall.co.kr/",
          "https://teacher.i-scream.co.kr/", "https://www.i-screammall.co.kr/", "https://mall.i-scream.co.kr/"]
MENU = re.compile(r"베스트|BEST|Best|인기|랭킹|신상|NEW|New|신규|카테고리|전체|세트|SET|패키지|기획전|몰|MALL|Mall|쇼핑")
PROD = re.compile(r"goods|product|prd|item|detail|view", re.I)


def robots(u):
    p = urlparse(u)
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{p.scheme}://{p.netloc}/robots.txt", headers={"User-Agent": "Mozilla/5.0"}), timeout=10) as r:
            t = r.read().decode("utf-8", "ignore")
        print(f"[robots] {p.netloc}:\n" + "\n".join("    " + l for l in t.splitlines()[:25]))
    except Exception as e:
        print(f"[robots] {p.netloc}: 조회 실패 {type(e).__name__}")


def inspect(page, url, depth=0):
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2500)
    except Exception as e:
        print(f"{'  ' * depth}[열기 실패] {url}: {type(e).__name__}")
        return []
    print(f"{'  ' * depth}== {url} -> {page.url} | {page.title()[:60]}")
    links = page.eval_on_selector_all("a[href]", "els => els.map(a => [a.innerText.trim().replace(/\\s+/g,' ').slice(0,40), a.href])")
    menu = [(t, h) for t, h in links if t and MENU.search(t) and h.startswith("http")]
    seen = set()
    for t, h in menu[:40]:
        if h in seen:
            continue
        seen.add(h)
        print(f"{'  ' * depth}  [메뉴] {t} -> {h}")
    prods = [(t, h) for t, h in links if PROD.search(urlparse(h).path + urlparse(h).query) and t]
    print(f"{'  ' * depth}  [상품 링크 후보] {len(prods)}개")
    for t, h in prods[:8]:
        print(f"{'  ' * depth}    · {t} | {h[:140]}")
    price = page.eval_on_selector_all("*", "els => els.filter(e => e.children.length===0 && /[0-9],?[0-9]{3}\\s*원/.test(e.innerText||'')).slice(0,6).map(e => (e.className||e.tagName)+' :: '+e.innerText.trim().slice(0,30))")
    print(f"{'  ' * depth}  [가격 요소 예] {price}")
    return [h for t, h in menu]


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36")
        for s in STARTS:
            robots(s)
            menu = inspect(page, s)
            mall = [h for h in menu if re.search(r"shop|mall|몰", h, re.I)][:2]
            for h in mall + [h for h in menu if re.search(r"best|new|rank|set|goods", h, re.I)][:3]:
                inspect(page, h, 1)
        b.close()


if __name__ == "__main__":
    main()
