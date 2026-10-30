#!/usr/bin/env python3
"""(일회성) 티처몰 협력사 안내 페이지와 상품 상세의 판매자·브랜드 표기 구조 확인. 저장하지 않음."""
import re
from playwright.sync_api import sync_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_context(user_agent=UA, locale="ko-KR").new_page()
    pg.goto("https://shop.teacherville.co.kr/service/provider", wait_until="domcontentloaded", timeout=40000)
    pg.wait_for_timeout(3000)
    print("== provider", pg.url, pg.title())
    body = re.sub(r"\s+", " ", pg.inner_text("body"))
    print(body[:3000])
    links = pg.eval_on_selector_all("a[href]", "els => els.map(a => [a.innerText.trim().replace(/\\s+/g,' ').slice(0,40), a.href])")
    print("[provider links]", [l for l in links if re.search(r"provider|brand|seller|minishop|partner", l[1], re.I)][:40])
    imgs = pg.eval_on_selector_all("img", "els => els.slice(0,80).map(i => (i.alt||'')+' | '+(i.src||'').slice(-60))")
    print("[imgs]", imgs[:60])
    for no in ["983882", "1199418", "936698", "1081381"]:
        pg.goto(f"https://shop.teacherville.co.kr/goods/view?no={no}", wait_until="domcontentloaded", timeout=40000)
        pg.wait_for_timeout(2500)
        t = re.sub(r"\s+", " ", pg.inner_text("body"))
        print(f"\n== goods {no}: {pg.title()[:50]}")
        for kw in ("판매자", "브랜드", "제조사", "공급", "원산지", "입점", "provider", "상호"):
            for m in re.finditer(kw, t):
                print(f"  {kw}: ...{t[max(0, m.start()-40):m.start()+80]}...")
                break
        ln = pg.eval_on_selector_all("a[href]", "els => els.map(a => [a.innerText.trim().slice(0,30), a.href]).filter(x => /provider|brand|seller|minishop/i.test(x[1]))")
        print("  [links]", ln[:8])
    b.close()
