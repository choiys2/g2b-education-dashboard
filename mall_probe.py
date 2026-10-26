#!/usr/bin/env python3
"""
(일회성 점검 2차) 티처몰 상품 카드 DOM·카테고리 코드, 아이스크림몰 접속 가능 여부 확인. 저장하지 않음.
"""
import re

from playwright.sync_api import sync_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
TM = "https://shop.teacherville.co.kr"
IS = ["https://i-screammall.co.kr/", "http://i-screammall.co.kr/", "https://www.i-screammall.co.kr/", "https://i-screammall.co.kr/robots.txt"]


def fresh(b):
    return b.new_context(user_agent=UA, locale="ko-KR", ignore_https_errors=True).new_page()


def go(b, url, wait=3000):
    pg = fresh(b)
    try:
        r = pg.goto(url, wait_until="domcontentloaded", timeout=40000)
        pg.wait_for_timeout(wait)
        print(f"\n== {url} -> {pg.url} | status {r.status if r else '-'} | {pg.title()[:60]}")
        return pg
    except Exception as e:
        print(f"\n[열기 실패] {url}: {str(e).splitlines()[0][:200]}")
        return None


def cards(pg, n=2):
    js = """() => { const a=[...document.querySelectorAll('a[href*="goods/view"]')];
      const out=[]; const seen=new Set();
      for (const x of a) { let p=x; for (let i=0;i<4 && p.parentElement;i++){ p=p.parentElement; if(/[0-9],?[0-9]{3}\\s*원/.test(p.innerText)) break; }
        const k=p.className; if(seen.has(k)) continue; seen.add(k); out.push([k, p.tagName, p.outerHTML.slice(0,1500)]); if(out.length>=3) break; }
      return out; }"""
    for k, t, h in pg.evaluate(js)[:n]:
        print(f"  [카드] {t}.{k}")
        print(re.sub(r"\s+", " ", h))
    print("  [goods/view 링크 수]", pg.eval_on_selector_all('a[href*="goods/view"]', "e=>new Set(e.map(a=>a.href.match(/no=(\\d+)/)?.[1])).size"))


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = go(b, TM + "/")
        if pg:
            links = pg.eval_on_selector_all("a[href]", "els => els.map(a => [a.innerText.trim().replace(/\\s+/g,' ').slice(0,30), decodeURIComponent(a.href)])")
            cat = sorted({(t, re.search(r"code=(\d+)", h).group(1)) for t, h in links if "catalog?code=" in h and t})
            print("  [카테고리 코드]", len(cat))
            for t, c in sorted(cat, key=lambda x: x[1])[:120]:
                print(f"    {c} {t}")
            for t, h in links:
                if re.search(r"신상|NEW|new|신규|랭킹|인기|급상승|추천", t) or re.search(r"goods/(new|best|rank|teachermade)|area=.*(keyword|search|hot)", h):
                    print(f"  [후보] {t} -> {h[:160]}")
        for u in [TM + "/goods/best", TM + "/goods/catalog?code=0001", TM + "/goods/new", TM + "/goods/teachermade", TM + "/promotion/event"]:
            pg = go(b, u)
            if pg:
                cards(pg)
                print("  [정렬/필터 후보]", pg.eval_on_selector_all("a[href*='sort'],option,[data-sort]", "e=>e.slice(0,15).map(x=>(x.innerText||'').trim()+' '+(x.getAttribute('href')||x.value||''))"))
                print("  [페이지 텍스트 일부]", re.sub(r"\s+", " ", pg.inner_text("body"))[:600])
        for u in IS:
            pg = go(b, u, 5000)
            if pg:
                print("  [본문 일부]", re.sub(r"\s+", " ", pg.inner_text("body"))[:800])
                links = pg.eval_on_selector_all("a[href]", "els => els.map(a => [a.innerText.trim().replace(/\\s+/g,' ').slice(0,30), a.href])")
                for t, h in links:
                    if t and re.search(r"베스트|BEST|신상|NEW|카테고리|세트|기획전|랭킹", t):
                        print(f"  [메뉴] {t} -> {h[:160]}")
                print("  [상품링크 예]", [h for t, h in links if re.search(r"goods|product|item", h, re.I)][:8])
        b.close()


if __name__ == "__main__":
    main()
