#!/usr/bin/env python3
"""
경쟁사(티처빌/아이스크림/비바샘) 연수원 "직무연수 전체 목록"을 사이트당 최대
--max-items(기본 500)건까지 수집한다. 로그인 없이 보이는 공개 목록 페이지만 본다.

⚠️ 작성 시점 한계: 이 스크립트는 세 사이트의 실제 목록 페이지 DOM을 직접 눈으로
확인하지 못한 상태로 작성됐다(개발 환경 네트워크 정책상 세 도메인 접속이 막혀
있었음 - competitor_content_scrape.py를 작성했던 예전 세션과는 다른 제약).
그래서 "정확한 CSS 셀렉터"가 아니라 href 패턴 기반의 느슨한 추출 전략을 쓴다:

  1) 목록 페이지에서 상세 페이지로 연결되는 <a href="..."> 중, 사이트별로 지정한
     정규식(COURSE_HREF_PATTERN)에 매칭하는 것만 "강좌 후보"로 모은다.
  2) 페이지 넘기기는 "다음/더보기" 류 버튼을 우선 클릭 시도하고, 안 되면
     아래로 스크롤해 무한스크롤 로딩을 유도한다.
  3) 안전장치: 500건 도달, 더 이상 신규 건이 늘지 않음(연속 STALL_LIMIT회),
     또는 MAX_PAGES 도달 중 먼저 오는 조건에서 멈춘다.

최초 실행 결과가 목표(500건)에 크게 못 미치면 COURSE_HREF_PATTERN이나
NEXT_SELECTORS를 실제 페이지에 맞게 보정해야 한다 - --debug 옵션을 켜면 매
스텝마다 후보 건수·다음버튼 탐지 여부를 stderr로 자세히 찍는다.

robots.txt: teacherville.co.kr / teacher.i-scream.co.kr 루트 도메인은
2026-08-04 확인 당시 "Allow: /"였다(competitor_content_scrape.py 주석 참고).
이 스크립트는 실행 시점에 대상 경로가 그 이후 별도로 금지되지 않았는지
다시 한번 자동으로 확인한다(check_robots_disallowed).
"""
import argparse
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright

OUT_PATH = Path("history/competitor_course_catalog.json")
MAX_ITEMS_DEFAULT = 500
MAX_PAGES = 80          # 안전장치: 무한루프 방지
STALL_LIMIT = 3          # 연속 N회 신규 후보가 0건이면 그만둔다
NAV_TIMEOUT_MS = 30000
STEP_WAIT_MS = 15000

# 페이지 넘기기 시도 순서: 번호형 페이지네이션 -> 다음/더보기 버튼
NEXT_SELECTORS = [
    "a:has-text('다음')",
    "button:has-text('다음')",
    "a[title='다음']",
    "a.next", ".pagination .next a", ".paging a.next", ".paging .next a",
    "button:has-text('더보기')", "a:has-text('더보기')",
    "button:has-text('더 보기')", "a:has-text('더 보기')",
    "button:has-text('More')",
]


def check_robots_disallowed(url):
    """대상 경로가 robots.txt에서 명시적으로 금지돼 있으면 True(=크롤링하면 안 됨)."""
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        with urllib.request.urlopen(robots_url, timeout=10) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  [경고] robots.txt 조회 실패({robots_url}): {e} - 판단 보류하고 진행", file=sys.stderr)
        return False
    star_block = False
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("user-agent:"):
            star_block = line.split(":", 1)[1].strip() == "*"
        elif star_block and line.lower().startswith("disallow:"):
            path = line.split(":", 1)[1].strip()
            if path and parsed.path.startswith(path):
                return True
    return False


def _extract_candidates(page, href_pattern):
    """href_pattern에 매칭하는 <a>를 강좌 후보로 모아 제목/링크/주변 텍스트를 반환."""
    return page.eval_on_selector_all(
        "a[href]",
        """(els, pattern) => {
            const re = new RegExp(pattern);
            const out = [];
            for (const el of els) {
                const href = el.getAttribute('href') || '';
                if (!re.test(href)) continue;
                const text = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ');
                if (!text || text.length < 2) continue;
                let ctxEl = el.closest('li') || el.closest('[class*="item" i]')
                    || el.closest('[class*="card" i]') || el.parentElement;
                let ctx = ctxEl ? (ctxEl.innerText || '').trim().replace(/\\s+/g, ' ') : '';
                if (ctx.length > 300) ctx = ctx.slice(0, 300);
                out.push({ title: text.slice(0, 200), href, context: ctx });
            }
            return out;
        }""",
        href_pattern,
    )


def _try_click_next(page, debug):
    for sel in NEXT_SELECTORS:
        try:
            loc = page.locator(sel).first
            if loc.count() == 0 or not loc.is_visible():
                continue
            loc.click(timeout=5000)
            if debug:
                print(f"    [다음] '{sel}' 클릭", file=sys.stderr)
            return True
        except Exception:
            continue
    return False


def _scroll_more(page):
    prev_height = page.evaluate("document.body.scrollHeight")
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(1500)
    new_height = page.evaluate("document.body.scrollHeight")
    return new_height > prev_height


def scrape_site(page, name, url, href_pattern, max_items, debug):
    if check_robots_disallowed(url):
        print(f"  [중단] {name}: robots.txt가 이 경로를 금지함 - 크롤링하지 않음", file=sys.stderr)
        return [], "robots.txt disallow"

    page.goto(url, wait_until="networkidle", timeout=NAV_TIMEOUT_MS)
    collected = {}
    stall = 0
    note = ""

    for step in range(MAX_PAGES):
        before = len(collected)
        for it in _extract_candidates(page, href_pattern):
            collected.setdefault(it["href"], it)
        gained = len(collected) - before
        if debug:
            print(f"  [{name}] step {step}: 누적 {len(collected)}건 (신규 {gained})", file=sys.stderr)

        if len(collected) >= max_items:
            note = f"목표({max_items}건) 도달"
            break

        moved = _try_click_next(page, debug)
        if moved:
            try:
                page.wait_for_load_state("networkidle", timeout=STEP_WAIT_MS)
            except Exception:
                page.wait_for_timeout(2000)
        else:
            moved = _scroll_more(page)
            if moved:
                page.wait_for_timeout(1000)

        if not moved and gained == 0:
            stall += 1
        elif gained > 0:
            stall = 0

        if not moved:
            note = "더 이상 다음 페이지/스크롤 없음"
            break
        if stall >= STALL_LIMIT:
            note = f"연속 {STALL_LIMIT}회 신규 없음 - 중단"
            break
    else:
        note = f"MAX_PAGES({MAX_PAGES}) 도달"

    items = []
    for i, (href, it) in enumerate(list(collected.items())[:max_items]):
        items.append({
            "index": i + 1,
            "title": it["title"],
            "url": urljoin(url, href),
            "context": it["context"],
        })
    if not note:
        note = "정상 종료"
    return items, note


SITES = {
    "티처빌": {
        "url": "https://www.teacherville.co.kr/trainapply/allCourseList.edu",
        "href_pattern": r"(course|Course|crs|lecture)",
    },
    "아이스크림": {
        "url": "https://teacher.i-scream.co.kr/course/crs/creditList.do?searchOrdinalTyCode=TY01&searchOrderField=NEW",
        "href_pattern": r"(crs|course|credit|Credit)",
    },
    "비바샘": {
        "url": "https://t.vivasam.com/courses/job?menuId=MENU0610",
        "href_pattern": r"/courses?/(job|view)?/?[a-zA-Z0-9]+",
    },
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-items", type=int, default=MAX_ITEMS_DEFAULT)
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--sites", default="", help="쉼표구분, 비우면 전체 (예: 티처빌,비바샘)")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    targets = [s.strip() for s in args.sites.split(",") if s.strip()] or list(SITES.keys())

    result = {"captured_date": date.today().isoformat(), "target_per_site": args.max_items, "companies": {}}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name in targets:
            cfg = SITES[name]
            page = browser.new_page()
            print(f"== {name} ==")
            try:
                items, note = scrape_site(page, name, cfg["url"], cfg["href_pattern"], args.max_items, args.debug)
                result["companies"][name] = {
                    "url": cfg["url"], "count": len(items), "note": note, "courses": items,
                }
                print(f"  수집 {len(items)}건 / 목표 {args.max_items}건 - {note}")
            except Exception as e:
                print(f"  [오류] {name} 수집 실패: {e}", file=sys.stderr)
                result["companies"][name] = {
                    "url": cfg["url"], "count": 0, "note": f"오류: {e}", "courses": [],
                }
            finally:
                page.close()
        browser.close()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {out_path}")


if __name__ == "__main__":
    main()
