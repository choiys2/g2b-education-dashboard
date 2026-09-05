#!/usr/bin/env python3
"""
경쟁사(티처빌/아이스크림/비바샘) 연수원 "직무연수 전체 목록"을 사이트당 최대
--max-items(기본 500)건까지 수집한다. 로그인 없이 보이는 공개 목록 페이지만 본다.

개발 환경 네트워크 정책상 세 도메인에 직접 접속할 수 없어, debug_dump_catalog_html.py로
GitHub Actions에서 실제 렌더링된 DOM을 한 번 받아본 뒤(2026-09-03) 사이트별 실제 강좌
카드 구조를 확인하고 맞춘 값이다(SITES 딕셔너리의 사이트별 주석 참고):

  - 아이스크림/비바샘: 강좌 상세로 연결되는 <a href="..."> 중 실측된 정규식에
    매칭하는 것만 "강좌 후보"로 모은다(extract mode "href").
  - 티처빌: <a href="...">가 아예 없이 onclick+data 속성으로 카드가 구성돼(data-seq
    등) 별도 추출 모드를 쓴다(extract mode "data_attr").
  - 페이지 넘기기는 사이트별로 "다음/더보기" 버튼 클릭(기본) 또는 URL 쿼리
    파라미터 직접 이동(아이스크림 - pagination mode "url_param") 중 확인된 방식을 쓴다.
  - 안전장치: 500건 도달, 더 이상 신규 건이 늘지 않음(연속 STALL_LIMIT회),
    또는 MAX_PAGES 도달 중 먼저 오는 조건에서 멈춘다.

그래도 실제 사이트 구조가 이후 바뀌면 실측치가 틀어질 수 있다 - --debug 옵션을 켜면
매 스텝마다 후보 건수·다음버튼 탐지 여부를 stderr로 자세히 찍는다.

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


def _extract_candidates(page, extract_cfg):
    """extract_cfg에 따라 강좌 후보를 모아 제목/링크(또는 참조 키)/주변 텍스트를 반환.

    mode "href" (기본): href_pattern에 매칭하는 <a>를 강좌 후보로 본다(아이스크림/비바샘).
    mode "data_attr": <a href>가 아예 없이 onclick+data 속성으로 카드가 구성되는
    사이트용(티처빌 실측: <div class="info-item" data-seq="O1006337"
    data-tv-label="...">) - id_attr로 카드를 찾고 title_attr(없으면 텍스트)을 제목으로 쓴다.
    """
    if extract_cfg.get("mode") == "data_attr":
        return page.eval_on_selector_all(
            f"[{extract_cfg['id_attr']}]",
            """(els, cfg) => {
                const seen = new Set();
                const out = [];
                for (const el of els) {
                    const seq = el.getAttribute(cfg.idAttr) || '';
                    if (!seq || seen.has(seq)) continue;
                    let title = cfg.titleAttr ? (el.getAttribute(cfg.titleAttr) || '') : '';
                    if (!title) title = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ');
                    if (!title || title.length < 2) continue;
                    seen.add(seq);
                    let ctx = (el.innerText || '').trim().replace(/\\s+/g, ' ');
                    if (ctx.length > 300) ctx = ctx.slice(0, 300);
                    out.push({ title: title.slice(0, 200), href: '#' + seq, context: ctx });
                }
                return out;
            }""",
            {"idAttr": extract_cfg["id_attr"], "titleAttr": extract_cfg.get("title_attr")},
        )

    href_pattern = extract_cfg["href_pattern"]
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
    # 번호형 페이지네이션(구형 JSP 사이트에 흔함)이 있으면 이쪽을 우선한다 -
    # 텍스트 기반 '더보기' 버튼이 페이지네이션과 무관한 엉뚱한 요소를 잘못
    # 매칭해 클릭만 되고 내용은 안 느는 경우(아이스크림에서 실측됨)를 피하려고.
    if _try_click_numbered_page(page, debug):
        return True
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


def _try_click_numbered_page(page, debug):
    """더보기/다음 버튼이 없거나 무의미할 때: 페이징 영역에서 현재 활성 페이지 번호를
    찾아 다음 숫자를 클릭한다(전형적인 '1 2 3 4 5 다음' 형태 JSP 페이지네이션 대응)."""
    try:
        clicked = page.evaluate("""() => {
            const activeSel = '.on, .active, .current, .selected, [aria-current="page"]';
            const containers = document.querySelectorAll('[class*="paging" i], [class*="pagination" i], [class*="page" i]');
            for (const c of containers) {
                const active = c.querySelector(activeSel);
                if (!active) continue;
                const cur = parseInt((active.innerText || '').trim(), 10);
                if (!cur) continue;
                const links = [...c.querySelectorAll('a, button')];
                for (const el of links) {
                    const n = parseInt((el.innerText || '').trim(), 10);
                    if (n === cur + 1) { el.click(); return n; }
                }
            }
            return 0;
        }""")
    except Exception:
        clicked = 0
    if clicked:
        if debug:
            print(f"    [다음] 번호형 페이지네이션 {clicked}페이지 클릭", file=sys.stderr)
        return True
    return False


def _scroll_more(page):
    prev_height = page.evaluate("document.body.scrollHeight")
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(1500)
    new_height = page.evaluate("document.body.scrollHeight")
    return new_height > prev_height


def scrape_site(page, name, url, extract_cfg, max_items, debug, pagination=None):
    pagination = pagination or {"mode": "click"}
    if check_robots_disallowed(url):
        print(f"  [중단] {name}: robots.txt가 이 경로를 금지함 - 크롤링하지 않음", file=sys.stderr)
        return [], "robots.txt disallow"

    # networkidle 대기는 티처빌에서 백그라운드 폴링으로 추정되는 이유로 30초
    # 타임아웃이 났다(진단 덤프에서 실측) - domcontentloaded + 고정 대기로 교체.
    page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
    page.wait_for_timeout(4000)
    collected = {}
    stall = 0
    note = ""

    if pagination["mode"] == "url_param":
        # 클릭 기반 대신 페이지 번호를 URL 쿼리 파라미터로 직접 요청한다(구형 JSP
        # 사이트가 hidden input으로 pageIndex를 쓰는 걸 실측으로 확인 - 아이스크림).
        param = pagination["param"]
        sep = "&" if "?" in url else "?"
        for page_no in range(1, MAX_PAGES + 1):
            if page_no > 1:
                page.goto(f"{url}{sep}{param}={page_no}", wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                page.wait_for_timeout(2500)
            before = len(collected)
            for it in _extract_candidates(page, extract_cfg):
                collected.setdefault(it["href"], it)
            gained = len(collected) - before
            if debug:
                print(f"  [{name}] {param}={page_no}: 누적 {len(collected)}건 (신규 {gained})", file=sys.stderr)
            if len(collected) >= max_items:
                note = f"목표({max_items}건) 도달"
                break
            stall = stall + 1 if gained == 0 else 0
            if stall >= STALL_LIMIT:
                note = f"연속 {STALL_LIMIT}페이지 신규 없음 - 마지막 페이지로 판단하고 중단"
                break
        else:
            note = f"MAX_PAGES({MAX_PAGES}) 도달"
    else:
        for step in range(MAX_PAGES):
            before = len(collected)
            for it in _extract_candidates(page, extract_cfg):
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
                    page.wait_for_load_state("networkidle", timeout=3000)
                except Exception:
                    pass
                page.wait_for_timeout(1000)
            else:
                moved = _scroll_more(page)
                if moved:
                    page.wait_for_timeout(1000)

            stall = stall + 1 if gained == 0 else 0

            if not moved:
                note = "더 이상 다음 페이지/스크롤 없음"
                break
            if stall >= STALL_LIMIT:
                note = f"클릭은 되지만 연속 {STALL_LIMIT}회 신규 없음 - 중단(실제 마지막 페이지이거나 버튼 오탐 가능)"
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
    # 티처빌 실측(2026-09-03, debug_html/티처빌.html): 강좌 카드는 <a href>가 아니라
    # <div class="info-item" data-seq="O1006337" data-tv-label="...">이고, 신청은
    # onclick="allCourseList.fn.link(('O1006337', 'T')"로 처리된다(href 자체가 없음).
    # "더보기" 버튼(id="more" 안, recordCountPerPage=20)은 실제 로드모어 버튼으로 확인됨
    # - 기존 클릭 기반 페이지네이션은 그대로 두고 추출 방식만 data_attr로 교체.
    "티처빌": {
        "url": "https://www.teacherville.co.kr/trainapply/allCourseList.edu",
        "extract": {"mode": "data_attr", "id_attr": "data-seq", "title_attr": "data-tv-label"},
    },
    # 아이스크림 실측(2026-09-03, debug_html/아이스크림.html): 강좌 카드는
    # /course/crs/creditView.do?crsCode=NNNN 로 연결되고(목록 메뉴 링크와 명확히
    # 구분됨), 페이지는 hidden input #pageIndex로 넘어간다(recordCountPerPage=30) -
    # 클릭 대신 URL에 pageIndex=N을 직접 붙여 GET으로 이동.
    "아이스크림": {
        "url": "https://teacher.i-scream.co.kr/course/crs/creditList.do?searchOrdinalTyCode=TY01&searchOrderField=NEW",
        "extract": {"mode": "href", "href_pattern": r"creditView\.do\?crsCode=\d+"},
        "pagination": {"mode": "url_param", "param": "pageIndex"},
    },
    # 비바샘 실측(2026-09-03, debug_html/비바샘.html): 강좌 카드는 /courses/job/t26-022
    # 같은 슬러그로 연결되고(카테고리 메뉴 /courses/job 자체와 구분됨), '더보기'
    # 버튼은 실제 클릭마다 신규 항목이 늘어나는 것으로 확인됨(기존 클릭 방식 유지).
    "비바샘": {
        "url": "https://t.vivasam.com/courses/job?menuId=MENU0610",
        "extract": {"mode": "href", "href_pattern": r"/courses/job/[a-zA-Z0-9-]+"},
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
                items, note = scrape_site(
                    page, name, cfg["url"], cfg["extract"], args.max_items, args.debug,
                    pagination=cfg.get("pagination"),
                )
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
