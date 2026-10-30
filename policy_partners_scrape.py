#!/usr/bin/env python3
"""
연수원 3사(티처빌·아이스크림·비바샘) 개인정보처리방침의 '처리위탁 수탁사'와 '제3자 제공처' 수집 - 주 1회(mall_catalog.yml).

  - 각 연수원 첫 화면 하단의 '개인정보처리방침' 링크를 따라가 본문 표·문단을 읽는다(robots.txt 허용 경로만).
  - 표 머리글에 '수탁'·'위탁' 이 있으면 처리위탁, '제공받는' 이 있으면 제3자 제공으로 본다.
    표가 없으면 해당 조항 문단을 그대로 남겨 뷰(policy_partners_view.py)가 회사명을 뽑는다.
  - 회사·기관명과 업무·목적만 저장한다(담당자 이름·연락처는 저장하지 않음).
  - 지난주와 비교해 새로 생기거나 빠진 협력사를 history 에 누적한다.
"""
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright

from competitor_mall_scrape import UA, allowed, robots_rules

OUT_PATH = Path("history/policy_partners.json")
SITES = {
    "teacherville": {"name": "티처빌", "home": "https://www.teacherville.co.kr"},
    "iscream": {"name": "아이스크림", "home": "https://teacher.i-scream.co.kr"},
    "vivasam": {"name": "비바샘", "home": "https://t.vivasam.com"},
}
LINK_RE = re.compile(r"개인\s?정보\s?(처리|취급)\s?방침")
# 연락처·이메일은 저장 전에 지운다
SCRUB_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|\(?0\d{1,2}\)?[-.\s]?\d{3,4}[-.\s]?\d{4}|1[5-9]\d{2}-\d{4}")

JS_LINKS = """() => [...document.querySelectorAll('a')].map(a => ({t: (a.innerText || a.title || '').trim(), h: a.getAttribute('href') || '', on: a.getAttribute('onclick') || ''}))"""
JS_TABLES = """() => [...document.querySelectorAll('table')].map(t => [...t.querySelectorAll('tr')].map(r => [...r.querySelectorAll('th,td')].map(c => c.innerText.trim().replace(/\\s+/g, ' '))))"""


def scrub(s):
    return SCRUB_RE.sub("", s or "").strip()


def find_policy(page, home, rules):
    """첫 화면에서 처리방침 링크 -> (URL, 열린 page). 새 창·자바스크립트 링크도 클릭으로 따라간다."""
    try:
        page.goto(home, wait_until="domcontentloaded", timeout=40000)
        page.wait_for_timeout(2500)
    except Exception as e:
        print(f"  [열기 실패] {home}: {str(e).splitlines()[0][:160]}")
        return None, None
    links = [l for l in page.evaluate(JS_LINKS) if LINK_RE.search(l["t"])]
    print(f"  처리방침 링크 후보: {[(l['t'][:20], l['h'][:80]) for l in links[:5]]}")
    for l in links:
        h = l["h"]
        if h and not h.startswith(("javascript", "#")):
            url = urljoin(page.url, h)
            if not allowed(rules, url) and urlparse(url).netloc == urlparse(home).netloc:
                print(f"  [건너뜀] robots 비허용: {url}")
                continue
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(2500)
                return page.url, page
            except Exception as e:
                print(f"  [열기 실패] {url}: {str(e).splitlines()[0][:160]}")
    # 자바스크립트 링크: 클릭해서 새 창 또는 같은 창 이동
    loc = page.get_by_text(LINK_RE).first
    try:
        with page.context.expect_page(timeout=8000) as pop:
            loc.click(timeout=8000)
        np = pop.value
        np.wait_for_load_state("domcontentloaded", timeout=40000)
        np.wait_for_timeout(2500)
        return np.url, np
    except Exception:
        page.wait_for_timeout(2500)
        return page.url, page


def sections(text):
    """'위탁'·'제3자 제공' 조항 문단(다음 조항 머리 전까지, 최대 4000자)."""
    out = {}
    heads = [m.start() for m in re.finditer(r"(?m)^\s*(제\s?\d+\s?조|\d{1,2}\s?[.)]|[①-⑳]|[가-하]\.)\s*\S", text)]
    for key, pat in (("consign", r"위탁"), ("third", r"제\s?3\s?자\s?(에게\s?)?제공|제공받는")):
        for m in re.finditer(r"(?m)^.*(" + pat + r").*$", text):
            if len(m.group(0)) > 80:  # 조항 제목 줄만(본문 문장 제외)
                continue
            st = m.start()
            nxt = next((h for h in heads if h > st + len(m.group(0)) + 20 and re.match(r"\s*제\s?\d+\s?조", text[h:h + 12])), None)
            out[key] = scrub(text[st:(nxt or st + 4000)][:4000])
            break
    return out


def classify_tables(tables):
    consign, third = [], []
    for t in tables:
        if len(t) < 2:
            continue
        head = " ".join(t[0])
        rows = [[scrub(c) for c in r] for r in t[1:] if any(r)]
        if re.search(r"수탁|위탁", head):
            consign.append({"head": t[0], "rows": rows})
        elif re.search(r"제공\s?받는|제공처|제3자", head):
            third.append({"head": t[0], "rows": rows})
    return consign, third


def scrape(page, key, site):
    print(f"[{site['name']}] {site['home']}")
    rules = robots_rules(site["home"])
    if not allowed(rules, site["home"] + "/"):
        return {"status": "robots 비허용"}
    url, pg = find_policy(page, site["home"], rules)
    if not pg:
        return {"status": "접속 실패"}
    text = pg.evaluate("() => document.body.innerText")
    # 처리방침이 iframe 안에 있는 경우
    tables = pg.evaluate(JS_TABLES)
    for fr in pg.frames[1:]:
        try:
            text += "\n" + fr.evaluate("() => document.body.innerText")
            tables += fr.evaluate(JS_TABLES)
        except Exception:
            pass
    if not re.search(r"위탁|제3자", text):
        print(f"  처리방침 본문을 찾지 못함: {url} ({len(text)}자)")
        return {"status": "본문 없음", "url": url}
    consign, third = classify_tables(tables)
    eff = re.search(r"(20\d{2})\s?[.년-]\s?(\d{1,2})\s?[.월-]\s?(\d{1,2})\s?일?\s*(부터|시행|적용)", text)
    out = {"status": "ok", "url": url, "effective": "-".join([eff.group(1), eff.group(2).zfill(2), eff.group(3).zfill(2)]) if eff else "",
           "consign_tables": consign, "third_tables": third, "sections": sections(text),
           "hash": hashlib.sha1(text.encode()).hexdigest()[:12]}
    print(f"  {url} · 시행 {out['effective'] or '?'} · 위탁표 {len(consign)} · 제공표 {len(third)} · 조항 {list(out['sections'])}")
    for k, v in out["sections"].items():
        print(f"  --- {k} ---\n{v[:1500]}")
    for t in consign + third:
        print(f"  표 {t['head']}: {len(t['rows'])}행 예) {t['rows'][:3]}")
    return out


def main():
    today = date.today().isoformat()
    prev = json.loads(OUT_PATH.read_text(encoding="utf-8")) if OUT_PATH.exists() else {}
    sites = dict(prev.get("sites", {}))
    with sync_playwright() as p:
        b = p.chromium.launch()
        for key, site in SITES.items():
            page = b.new_context(user_agent=UA, locale="ko-KR").new_page()
            try:
                r = scrape(page, key, site)
            except Exception as e:
                print(f"  [오류] {e}", file=sys.stderr)
                r = {"status": "오류"}
            if r.get("status") == "ok" or key not in sites:
                sites[key] = {**r, "name": site["name"], "home": site["home"], "captured": today}
            else:  # 실패하면 지난 결과 유지
                sites[key]["last_error"] = r.get("status")
            page.context.close()
        b.close()
    OUT_PATH.write_text(json.dumps({"updated": today, "sites": sites, "changes": prev.get("changes", []),
                                    "snap": prev.get("snap", {})}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("저장:", {k: v.get("status") for k, v in sites.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
