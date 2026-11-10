#!/usr/bin/env python3
"""
참고 사이트 디자인·기능 분석(수동 실행 전용, ref_capture.yml) - 대시보드 개선 참고용.
각 URL을 데스크톱·모바일로 열어 화면을 캡처(실행 결과물 artifact)하고, 디자인 요소(색·글꼴·모서리·그림자·간격)와
기능 요소(내비게이션·버튼·입력·탭·카드·차트 등)를 추출해 로그에 JSON 으로 남긴다. 저장소에는 아무것도 커밋하지 않는다.
  python ref_capture.py <출력폴더> <url> [<url> ...]
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

JS = r"""() => {
  const all = [...document.querySelectorAll('body *')].filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
  const cnt = (arr) => { const m = {}; arr.forEach(v => { if (v) m[v] = (m[v] || 0) + 1; }); return Object.entries(m).sort((a, b) => b[1] - a[1]); };
  const cs = all.slice(0, 3000).map(e => getComputedStyle(e));
  const isClr = c => c && c !== 'rgba(0, 0, 0, 0)' && c !== 'transparent';
  const head = [...document.querySelectorAll('h1,h2,h3')].slice(0, 30).map(h => `${h.tagName}:${h.innerText.trim().slice(0, 60)}`);
  const ctrls = [...document.querySelectorAll('button,a,[role=button],[role=tab],input,select,textarea')].filter(e => e.getBoundingClientRect().width > 0)
    .slice(0, 80).map(e => `${e.tagName.toLowerCase()}${e.type ? '[' + e.type + ']' : ''}:${(e.innerText || e.placeholder || e.getAttribute('aria-label') || e.value || '').trim().replace(/\s+/g, ' ').slice(0, 40)}`);
  const comp = {
    nav: document.querySelectorAll('nav,header').length, tabs: document.querySelectorAll('[role=tab],[role=tablist]').length,
    cards: all.filter(e => { const s = getComputedStyle(e); return (s.boxShadow !== 'none' || s.borderStyle !== 'none') && parseFloat(s.borderRadius) >= 8 && e.getBoundingClientRect().width > 150 && e.getBoundingClientRect().height > 80; }).length,
    svg: document.querySelectorAll('svg').length, canvas: document.querySelectorAll('canvas').length, img: document.querySelectorAll('img').length,
    inputs: document.querySelectorAll('input,textarea,select').length, dialogs: document.querySelectorAll('dialog,[role=dialog]').length,
    progress: document.querySelectorAll('progress,[role=progressbar]').length, lists: document.querySelectorAll('ul,ol').length, tables: document.querySelectorAll('table').length,
    sticky: all.filter(e => ['fixed', 'sticky'].includes(getComputedStyle(e).position)).map(e => e.tagName.toLowerCase() + (e.className && typeof e.className === 'string' ? '.' + e.className.split(' ')[0] : '')).slice(0, 8),
  };
  const ls = (() => { try { return Object.keys(localStorage).slice(0, 15); } catch (e) { return []; } })();
  return {
    title: document.title, lang: document.documentElement.lang, desc: (document.querySelector('meta[name=description]') || {}).content || '',
    height: document.body.scrollHeight, bodyBg: getComputedStyle(document.body).backgroundColor,
    textColors: cnt(cs.map(s => s.color)).slice(0, 8), bgColors: cnt(cs.map(s => s.backgroundColor).filter(isClr)).slice(0, 10),
    borderColors: cnt(cs.filter(s => s.borderStyle !== 'none').map(s => s.borderColor)).slice(0, 5),
    gradients: cnt(cs.map(s => s.backgroundImage).filter(v => v && v.includes('gradient'))).slice(0, 4).map(x => [x[0].slice(0, 140), x[1]]),
    fonts: cnt(cs.map(s => s.fontFamily.split(',')[0].replace(/["']/g, ''))).slice(0, 5),
    fontSizes: cnt(cs.map(s => s.fontSize)).slice(0, 8), weights: cnt(cs.map(s => s.fontWeight)).slice(0, 5),
    radius: cnt(cs.map(s => s.borderRadius).filter(v => v !== '0px')).slice(0, 6), shadows: cnt(cs.map(s => s.boxShadow).filter(v => v !== 'none')).slice(0, 4).map(x => [x[0].slice(0, 120), x[1]]),
    gaps: cnt(cs.map(s => s.gap).filter(v => v && v !== 'normal')).slice(0, 5), maxWidths: cnt(cs.map(s => s.maxWidth).filter(v => v !== 'none')).slice(0, 4),
    anim: cnt(cs.map(s => s.transitionProperty).filter(v => v && v !== 'all' && v !== 'none')).slice(0, 4).concat(cnt(cs.map(s => s.animationName).filter(v => v && v !== 'none')).slice(0, 4)),
    headings: head, controls: ctrls, comp, localStorage: ls,
    text: document.body.innerText.replace(/\n{2,}/g, '\n').slice(0, 2200),
  };
}"""


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        for i, url in enumerate(sys.argv[2:]):
            res = {"url": url}
            for mode, vp in (("desktop", {"width": 1366, "height": 900}), ("mobile", {"width": 390, "height": 844})):
                ctx = b.new_context(viewport=vp, locale="ko-KR", is_mobile=(mode == "mobile"))
                page = ctx.new_page()
                try:
                    try:
                        r = page.goto(url, wait_until="networkidle", timeout=30000)
                    except Exception:  # 영상·추적 스크립트로 networkidle 이 끝나지 않는 사이트(예: visang.com) - 화면이 뜨면 진행
                        r = None
                        if page.url in ("about:blank", ""):
                            r = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(6000)
                    page.screenshot(path=str(out / f"{i}_{mode}_top.png"))
                    page.screenshot(path=str(out / f"{i}_{mode}_full.png"), full_page=True)
                    if mode == "desktop":
                        res.update({"status": r.status if r else None, **page.evaluate(JS)})
                        # 첫 번째 탭·버튼을 눌러 화면 전환이 있는지(앱형 기능) 확인
                        clicks = []
                        for sel in ("[role=tab]", "nav a", "button"):
                            els = page.query_selector_all(sel)[:3]
                            for e in els:
                                try:
                                    t = (e.inner_text() or "").strip()[:30]
                                    e.click(timeout=2000)
                                    page.wait_for_timeout(1200)
                                    clicks.append({"sel": sel, "text": t, "url": page.url, "h1": (page.query_selector("h1,h2") or page).inner_text()[:60] if page.query_selector("h1,h2") else ""})
                                except Exception:
                                    pass
                            if clicks:
                                break
                        res["clicks"] = clicks
                        page.screenshot(path=str(out / f"{i}_{mode}_after_click.png"))
                    else:
                        res["mobile_height"] = page.evaluate("document.body.scrollHeight")
                        res["mobile_overflow"] = page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 2")
                except Exception as e:
                    res[f"{mode}_error"] = f"{type(e).__name__}: {str(e)[:160]}"
                ctx.close()
            print(f"===REF {i} START===")
            print(json.dumps(res, ensure_ascii=False))
            print(f"===REF {i} END===", flush=True)
        b.close()


if __name__ == "__main__":
    main()
