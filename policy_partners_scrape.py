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
# 화면에 보이는 표만(지난 버전 접힘 표 제외), 병합 셀(rowspan/colspan)을 펼치고, 표 바로 앞 조항 제목을 붙인다.
JS_TABLES = """() => {
  const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length) && getComputedStyle(el).visibility !== 'hidden';
  const out = [];
  let ctx = '';
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
  for (let n = w.currentNode; n; n = w.nextNode()) {
    if (n.nodeType === 3) {
      const t = n.textContent.trim();
      if (t && t.length < 70 && /위탁|제\s?3\s?자|제공/.test(t) && !(n.parentElement && n.parentElement.closest('table'))) ctx = t;
      continue;
    }
    if (n.tagName !== 'TABLE' || !vis(n)) continue;
    const grid = [];
    [...n.querySelectorAll('tr')].forEach((tr, ri) => {
      grid[ri] = grid[ri] || [];
      let ci = 0;
      [...tr.querySelectorAll('th,td')].forEach(c => {
        while (grid[ri][ci] !== undefined) ci++;
        const txt = c.innerText.trim().replace(/[ \\t\\u00a0]+/g, ' ').replace(/\\s*\\n\\s*/g, ' | ');
        for (let r = 0; r < (c.rowSpan || 1); r++)
          for (let k = 0; k < (c.colSpan || 1); k++) {
            grid[ri + r] = grid[ri + r] || [];
            grid[ri + r][ci + k] = txt;
          }
        ci += c.colSpan || 1;
      });
    });
    out.push({ctx, rows: grid.map(r => [...r].map(x => x || ''))});
  }
  return out;
}"""


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
    # 공지 제목('… 처리방침 개정 안내')보다 하단 고정 링크(짧은 글자)를 먼저
    links = sorted((l for l in page.evaluate(JS_LINKS) if LINK_RE.search(l["t"])), key=lambda l: len(l["t"]))
    print(f"  처리방침 링크 후보: {[(l['t'][:20], l['h'][:80]) for l in links[:5]]}")
    page._pp_notices = notices(page, [l for l in links if re.search(r"개정|변경|안내", l["t"])], rules)
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


def classify_tables(tables):
    """머리글로 처리위탁(수탁…)·제3자 제공(…받는 자) 표만 고른다. 책임자·연락처 표는 저장하지 않는다."""
    consign, third, seen = [], [], set()
    for t in tables:
        rows = t["rows"]
        if len(rows) < 2:
            continue
        head, ctx = [c.replace(" | ", " ") for c in rows[0]], t.get("ctx", "")
        hs = " ".join(head)
        if re.search(r"책임자|담당자|담당부서|연락처|전화", hs):
            continue
        sig = json.dumps(rows, ensure_ascii=False)
        if sig in seen:
            continue
        seen.add(sig)
        body = [[scrub(c) for c in r] for r in rows[1:] if any(r)]
        if re.search(r"수탁", hs) or (head[:2] == ["구분", "목적"] and "위탁" in ctx):
            consign.append({"head": head, "rows": body, "ctx": ctx})
        elif re.search(r"받는\s?자|제공처", hs):
            third.append({"head": head, "rows": body, "ctx": ctx})
    return consign, third


NOTICE_RE = re.compile(r"시행\s?일?\s*[:：]?\s*(20\d{2})\s?[.년-]\s?(\d{1,2})\s?[.월-]\s?(\d{1,2})")


def notices(page, links, rules):
    """첫 화면 공지 중 처리방침 개정 안내 -> [{t, eff}] (최대 2건, 제목과 시행일만)"""
    out = []
    for l in links[:2]:
        url = urljoin(page.url, l["h"]) if l["h"] and not l["h"].startswith(("javascript", "#")) else ""
        eff = ""
        if url and allowed(rules, url):
            try:
                np = page.context.new_page()
                np.goto(url, wait_until="domcontentloaded", timeout=30000)
                np.wait_for_timeout(1500)
                m = NOTICE_RE.search(np.evaluate("() => document.body.innerText"))
                eff = "-".join([m.group(1), m.group(2).zfill(2), m.group(3).zfill(2)]) if m else ""
                np.close()
            except Exception:
                pass
        out.append({"t": scrub(l["t"])[:80], "eff": eff})
    return out


JS_EXPAND = """() => [...document.querySelectorAll('table a, table button, table [onclick]')]
  .filter(a => /전체\\s?보기|상세\\s?목록/.test(a.innerText || ''))
  .map((a, i) => { a.setAttribute('data-pp-x', i); const td = a.closest('td'); return {i, near: td ? td.innerText.trim().slice(0, 30) : '', h: a.getAttribute('href') || ''}; })"""


def expand(pg, rules):
    """표 안 '전체 보기'·'[상세목록]' -> 펼친 명단 글자(새 창·레이어 모두). 회사명만 뷰에서 추린다."""
    out = []
    try:
        cands = pg.evaluate(JS_EXPAND)[:4]
    except Exception:
        return out
    for c in cands:
        before = set(pg.evaluate("() => document.body.innerText").splitlines())
        text = ""
        try:
            h = c["h"]
            if h and not h.startswith(("javascript", "#")):
                url = urljoin(pg.url, h)
                if allowed(rules, url):
                    np = pg.context.new_page()
                    np.goto(url, wait_until="domcontentloaded", timeout=30000)
                    np.wait_for_timeout(1500)
                    text = np.evaluate("() => document.body.innerText")
                    np.close()
            else:
                try:
                    with pg.context.expect_page(timeout=4000) as pop:
                        pg.click(f'[data-pp-x="{c["i"]}"]', timeout=5000)
                    np = pop.value
                    np.wait_for_load_state("domcontentloaded", timeout=30000)
                    np.wait_for_timeout(1500)
                    text = np.evaluate("() => document.body.innerText")
                    np.close()
                except Exception:
                    pg.wait_for_timeout(1500)
                    after = pg.evaluate("() => document.body.innerText").splitlines()
                    text = "\n".join(x for x in after if x not in before)
                    pg.keyboard.press("Escape")
        except Exception as e:
            print(f"  [펼치기 실패] {c['near'][:20]}: {str(e).splitlines()[0][:120]}")
        if text:
            out.append({"near": scrub(c["near"]), "text": scrub(text)[:4000]})
            print(f"  펼침 [{c['near'][:20]}] {len(text)}자: {text[:200]!r}")
    return out


def scrape(page, key, site):
    print(f"[{site['name']}] {site['home']}")
    rules = robots_rules(site["home"])
    if not allowed(rules, site["home"] + "/"):
        return {"status": "robots 비허용"}
    url, pg = find_policy(page, site["home"], rules)
    if not pg:
        return {"status": "접속 실패"}
    text = pg.evaluate("() => document.body.innerText")
    tables = pg.evaluate(JS_TABLES)
    for fr in pg.frames[1:]:  # 처리방침이 iframe 안에 있는 경우
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
    ver = re.search(r"현행\s*(Ver\.?\s*[\d.]+)", text)
    out = {"status": "ok", "url": url, "effective": "-".join([eff.group(1), eff.group(2).zfill(2), eff.group(3).zfill(2)]) if eff else "",
           "version": ver.group(1) if ver else "", "notices": getattr(page, "_pp_notices", []),
           "consign_tables": consign, "third_tables": third, "expand": expand(pg, rules),
           "hash": hashlib.sha1(text.encode()).hexdigest()[:12]}
    print(f"  {url} · 시행 {out['effective'] or '?'} {out['version']} · 위탁표 {len(consign)} · 제공표 {len(third)} · 개정공지 {out['notices']}")
    for t in consign + third:
        print(f"  표[{t['ctx'][:30]}] {t['head']}: {len(t['rows'])}행")
        for r in t["rows"]:
            print("     ", [c[:50] for c in r[:3]])
    return out


def track(prev_snap, sites, today):
    """협력사 이름 집합을 지난주와 비교 -> 변경 이력(신규·제외)"""
    from policy_partners_view import extract, norm
    snap, changes = {}, []
    for k, s in sites.items():
        if s.get("status") != "ok":
            if k in prev_snap:
                snap[k] = prev_snap[k]
            continue
        cur = {}
        for e in extract(s):
            cur.setdefault(norm(e["name"]), {"n": e["name"], "kind": e["kind"], "cat": e["cat"]})
        snap[k] = cur
        old = prev_snap.get(k)
        if old is None:
            continue
        add = [v for n, v in cur.items() if n not in old]
        rem = [v for n, v in old.items() if n not in cur]
        if add or rem:
            changes.append({"date": today, "site": s.get("name"), "added": add, "removed": rem})
    return snap, changes


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
    snap, changes = track(prev.get("snap", {}), sites, today)
    OUT_PATH.write_text(json.dumps({"updated": today, "sites": sites, "changes": (prev.get("changes", []) + changes)[-100:],
                                    "snap": snap}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("저장:", {k: v.get("status") for k, v in sites.items()}, "· 변경", len(changes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
