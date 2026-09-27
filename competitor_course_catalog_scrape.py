#!/usr/bin/env python3
"""
경쟁사(티처빌/아이스크림/비바샘연수원) 연수원 "직무연수 전체 목록"을 사이트당 최대
--max-items(기본 500)건까지 수집한다. 로그인 없이 보이는 공개 목록 페이지만 본다.

개발 환경 네트워크 정책상 세 도메인에 직접 접속할 수 없어, debug_dump_catalog_html.py로
GitHub Actions에서 실제 렌더링된 DOM을 한 번 받아본 뒤(2026-09-03) 사이트별 실제 강좌
카드 구조를 확인하고 맞춘 값이다(SITES 딕셔너리의 사이트별 주석 참고):

  - 아이스크림/비바샘연수원: 강좌 상세로 연결되는 <a href="..."> 중 실측된 정규식에
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

from catalog_field_parser import parse_fields

OUT_PATH = Path("history/competitor_course_catalog.json")
# 스냅샷의 diff는 "직전 수집 대비"만 남아 다음 주에 덮어써진다. 대시보드의
# "신규 콘텐츠" 패널이 몇 달치를 보여줄 수 있게 신규 강좌만 따로 누적한다.
NEW_LOG_PATH = Path("history/competitor_new_courses.jsonl")
NEW_LOG_FIELDS = ("title", "category", "credit", "price", "orig_price", "url")
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

    mode "href" (기본): href_pattern에 매칭하는 <a>를 강좌 후보로 본다(아이스크림/비바샘연수원).
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



# 아이스크림 실측(2026-09-27 로그): pageIndex=2~4를 GET으로 붙여도 1페이지와 같은 45건만
# 돌아왔다 - 서버가 쿼리 파라미터를 무시하고 폼 POST/JS 함수로만 페이지를 넘기는 구조로
# 추정. 개발 환경에선 사이트에 접속할 수 없어 DOM을 직접 못 보므로, 흔한 전자정부/JSP
# 페이징 방식들을 순서대로 시도하고, 실패하면 진단 정보를 로그에 남긴다.
PAGE_SIZE_PARAMS = ("recordCountPerPage", "pageUnit", "pageSize", "listSize", "rows")
PAGE_JS_FUNCS = ("fn_egov_link_page", "fn_link_page", "linkPage", "goPage", "fnGoPage",
                 "fn_goPage", "movePage", "fnMovePage", "fn_movePage", "pageMove", "goList")


def _goto_page_in_dom(page, page_no, param="pageIndex"):
    """URL 파라미터가 먹지 않을 때 페이지 안에서 page_no 페이지로 이동. 성공한 방법명 반환."""
    how = page.evaluate("""([n, param, funcs]) => {
        // 1) 페이지 번호 링크를 직접 클릭(텍스트가 정확히 n인 a/button, 페이징 영역 우선)
        const areas = document.querySelectorAll('[class*="pag" i], [id*="pag" i]');
        for (const a of areas) {
            for (const el of a.querySelectorAll('a, button')) {
                if ((el.innerText || '').trim() === String(n)) { el.click(); return 'link'; }
            }
        }
        // 2) 전자정부 프레임워크류 전역 페이징 함수
        for (const f of funcs) {
            if (typeof window[f] === 'function') { try { window[f](n); return 'fn:' + f; } catch (e) {} }
        }
        // 3) hidden input에 번호를 넣고 그 폼을 제출
        const inp = document.querySelector(`input[name="${param}"], #${param}`);
        if (inp && inp.form) { inp.value = String(n); inp.form.submit(); return 'form'; }
        return '';
    }""", [page_no, param, list(PAGE_JS_FUNCS)])
    if how:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=NAV_TIMEOUT_MS)
        except Exception:
            pass
        page.wait_for_timeout(2500)
    return how


def _dump_paging_diagnostics(page, name):
    """페이징이 막혔을 때 다음 수정에 쓸 단서를 로그에 남긴다(사이트 DOM을 직접 볼 수 없어서)."""
    try:
        info = page.evaluate("""() => {
            const pick = sel => [...document.querySelectorAll(sel)].slice(0, 4)
                .map(e => e.outerHTML.replace(/\\s+/g, ' ').slice(0, 700));
            return {
                url: location.href,
                paging: pick('[class*="pag" i], [id*="pag" i]'),
                more: pick('[id*="more" i], [class*="more" i]'),
                inputs: [...document.querySelectorAll('input[type=hidden]')].map(i => `${i.name||i.id}=${i.value}`).slice(0, 30),
                pageFuncs: Object.keys(window).filter(k => { try { return typeof window[k] === 'function' && /page|more|list/i.test(k); } catch (e) { return false; } }).slice(0, 40),
            };
        }""")
        print(f"  [{name}] 페이징 진단: {json.dumps(info, ensure_ascii=False)[:4000]}", file=sys.stderr)
    except Exception as e:
        print(f"  [{name}] 페이징 진단 실패: {e}", file=sys.stderr)


def _wait_for_growth(page, extract_cfg, before_count, timeout_ms=20000):
    """'더보기' 클릭 후 목록이 실제로 늘 때까지 최대 timeout_ms 기다린다(고정 1초 대기로는
    티처빌 응답이 늦을 때 '신규 0'으로 오판했다 - 2026-09-27 20/500건 사고)."""
    waited = 0
    while waited < timeout_ms:
        page.wait_for_timeout(500)
        waited += 500
        try:
            if len(_extract_candidates(page, extract_cfg)) > before_count:
                return True
        except Exception:
            pass
    return False



def _click_more_selector(page, selector, debug):
    """지정한 '더보기' 요소가 보이면 클릭. 없거나 비어 있으면(마지막 페이지) False."""
    try:
        loc = page.locator(selector).first
        # 티처빌은 응답이 10초 넘게 늦을 때 로딩 중 버튼을 잠깐 숨긴다(2026-09-27: 460건에서
        # '끝'으로 오판). 사라졌다고 바로 끝내지 않고 다시 나타나길 최대 20초 기다린다.
        try:
            loc.wait_for(state="visible", timeout=20000)
        except Exception:
            return False
        loc.scroll_into_view_if_needed(timeout=3000)
        loc.click(timeout=5000)
        if debug:
            print(f"    [다음] '{selector}' 클릭", file=sys.stderr)
        return True
    except Exception:
        return False


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
        # 먼저 한 페이지 크기를 크게 요청해 본다 - 서버가 받아주면 1페이지로 끝난다.
        big = "&".join(f"{k}={max_items}" for k in PAGE_SIZE_PARAMS)
        first = len(_extract_candidates(page, extract_cfg))
        page.goto(f"{url}{sep}{big}", wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        page.wait_for_timeout(3000)
        if len(_extract_candidates(page, extract_cfg)) <= first:
            page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            page.wait_for_timeout(3000)
        elif debug:
            print(f"  [{name}] 페이지 크기 확대 파라미터 적용됨", file=sys.stderr)
        dom_mode = False  # URL 파라미터가 무시되는 게 확인되면 페이지 안 이동으로 전환
        for page_no in range(1, MAX_PAGES + 1):
            if page_no > 1 and not dom_mode:
                page.goto(f"{url}{sep}{param}={page_no}", wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                page.wait_for_timeout(2500)
                if page_no == 2 and not any(it["href"] not in collected for it in _extract_candidates(page, extract_cfg)):
                    dom_mode = True
                    if debug:
                        print(f"  [{name}] {param} URL 파라미터 무시됨 - 페이지 안 이동으로 전환", file=sys.stderr)
                    page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                    page.wait_for_timeout(2500)
            if page_no > 1 and dom_mode:
                how = _goto_page_in_dom(page, page_no, param)
                if debug:
                    print(f"  [{name}] {page_no}페이지 이동 방법: {how or '없음'}", file=sys.stderr)
                if not how:
                    _dump_paging_diagnostics(page, name)
                    note = "페이지 이동 수단을 찾지 못함(로그의 페이징 진단 참고)"
                    break
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
                if len(collected) < 100:
                    _dump_paging_diagnostics(page, name)
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

            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(500)
            count_before_click = len(_extract_candidates(page, extract_cfg))
            if pagination.get("more_selector"):
                # 사이트별로 실측한 '목록 더보기' 버튼만 누른다. 범용 텍스트 매칭은 헤더/추천
                # 영역의 다른 '더보기'를 잘못 눌렀다(티처빌 AI추천, 아이스크림 상단 메뉴).
                moved = _click_more_selector(page, pagination["more_selector"], debug)
            else:
                moved = _try_click_next(page, debug)
            if moved:
                try:
                    page.wait_for_load_state("networkidle", timeout=3000)
                except Exception:
                    pass
                if not _wait_for_growth(page, extract_cfg, count_before_click) and debug:
                    print(f"  [{name}] 클릭 후 20초 내 목록 증가 없음", file=sys.stderr)
            elif not pagination.get("more_selector"):
                moved = _scroll_more(page)
                if moved:
                    page.wait_for_timeout(1000)

            stall = stall + 1 if gained == 0 else 0

            if not moved:
                note = "더 이상 다음 페이지/스크롤 없음"
                if len(collected) < 100:
                    _dump_paging_diagnostics(page, name)
                break
            if stall >= STALL_LIMIT:
                note = f"클릭은 되지만 연속 {STALL_LIMIT}회 신규 없음 - 중단(실제 마지막 페이지이거나 버튼 오탐 가능)"
                _dump_paging_diagnostics(page, name)
                break
        else:
            note = f"MAX_PAGES({MAX_PAGES}) 도달"

    items = []
    for i, (href, it) in enumerate(list(collected.items())[:max_items]):
        fields = parse_fields(name, it["title"], it["context"])
        items.append({
            "index": i + 1,
            "title": fields["title"],
            "category": fields["category"],
            "credit": fields["credit"],
            "price": fields["price"],
            "orig_price": fields["orig_price"],
            "url": urljoin(url, href),
            "context": it["context"],
        })
    if not note:
        note = "정상 종료"
    return items, note


def _diff_courses(prev_items, curr_items):
    """url 기준으로 신규/종료 강좌만 뽑는다(competitor_content_scrape.py의
    diff_events와 동일한 패턴 - 제목이 아니라 url을 키로 쓰는 이유는 이쪽은
    가격 표기 등으로 title이 실행마다 미세하게 흔들릴 수 있어서)."""
    prev_urls = {it.get("url") for it in prev_items}
    curr_urls = {it.get("url") for it in curr_items}
    new_urls = curr_urls - prev_urls
    removed_urls = prev_urls - curr_urls
    return {
        "new": [it for it in curr_items if it.get("url") in new_urls],
        "removed": [it for it in prev_items if it.get("url") in removed_urls],
    }


SITES = {
    # 티처빌 실측(2026-09-03, debug_html/티처빌.html): 강좌 카드는 <a href>가 아니라
    # <div class="info-item" data-seq="O1006337" data-tv-label="...">이고, 신청은
    # onclick="allCourseList.fn.link(('O1006337', 'T')"로 처리된다(href 자체가 없음).
    # "더보기" 버튼(id="more" 안, recordCountPerPage=20)은 실제 로드모어 버튼으로 확인됨
    # - 기존 클릭 기반 페이지네이션은 그대로 두고 추출 방식만 data_attr로 교체.
    "티처빌": {
        "url": "https://www.teacherville.co.kr/trainapply/allCourseList.edu",
        "extract": {"mode": "data_attr", "id_attr": "data-seq", "title_attr": "data-tv-label"},
        # 2026-09-27 진단: 목록 더보기는 <div id="more"> 안의 버튼이고 끝에 가면 비워진다.
        # 그 뒤엔 범용 매칭이 AI추천 영역의 '더 보기'를 눌러 헛돌았다.
        "pagination": {"mode": "click", "more_selector": "#more button, #more a"},
    },
    # 아이스크림 실측(2026-09-03, debug_html/아이스크림.html): 강좌 카드는
    # /course/crs/creditView.do?crsCode=NNNN 로 연결되고(목록 메뉴 링크와 명확히
    # 구분됨), 페이지는 hidden input #pageIndex로 넘어간다(recordCountPerPage=30) -
    # 클릭 대신 URL에 pageIndex=N을 직접 붙여 GET으로 이동.
    "아이스크림": {
        "url": "https://teacher.i-scream.co.kr/course/crs/creditList.do?searchOrdinalTyCode=TY01&searchOrderField=NEW",
        "extract": {"mode": "href", "href_pattern": r"creditView\.do\?crsCode=\d+"},
        # 2026-09-27 진단: pageIndex는 GET/폼 제출 모두 무시되고, 목록은
        # <div id="divMore" onclick="getCrsList(null, true)">더보기</div>로 AJAX 추가된다.
        "pagination": {"mode": "click", "more_selector": "#divMore"},
    },
    # 비바샘연수원 실측(2026-09-03, debug_html/비바샘.html): 강좌 카드는 /courses/job/t26-022
    # 같은 슬러그로 연결되고(카테고리 메뉴 /courses/job 자체와 구분됨), '더보기'
    # 버튼은 실제 클릭마다 신규 항목이 늘어나는 것으로 확인됨(기존 클릭 방식 유지).
    "비바샘연수원": {
        "url": "https://t.vivasam.com/courses/job?menuId=MENU0610",
        "extract": {"mode": "href", "href_pattern": r"/courses/job/[a-zA-Z0-9-]+"},
    },
}


def append_new_courses(company, new_items, first_seen, log_path=NEW_LOG_PATH):
    """신규 강좌를 url 기준으로 한 번만 기록한다(재등장해도 최초 확인일 유지)."""
    seen = set()
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    r = json.loads(line)
                    seen.add((r.get("company"), r.get("url")))
                except json.JSONDecodeError:
                    continue
    rows = [
        {"first_seen": first_seen, "company": company, **{k: it.get(k) for k in NEW_LOG_FIELDS}}
        for it in new_items if it.get("url") and (company, it.get("url")) not in seen
    ]
    if rows:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-items", type=int, default=MAX_ITEMS_DEFAULT)
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--sites", default="", help="쉼표구분, 비우면 전체 (예: 티처빌,비바샘연수원)")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    targets = [s.strip() for s in args.sites.split(",") if s.strip()] or list(SITES.keys())

    out_path = Path(args.out)
    try:
        prev = json.loads(out_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        prev = {"captured_date": None, "companies": {}}
    prev_companies = prev.get("companies", {})

    # --sites로 일부만 재크롤링해도 나머지 회사의 이전 결과는 그대로 보존한다
    # (부분 실행이 전체 파일을 덮어써 지우지 않도록).
    result = {
        "captured_date": date.today().isoformat(),
        "target_per_site": args.max_items,
        "companies": dict(prev_companies),
    }
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
                prev_items = prev_companies.get(name, {}).get("courses", [])
                diff = _diff_courses(prev_items, items)
                # 2026-09-27 실측: 티처빌 '더보기'가 한 번도 안 눌려 500건 -> 20건만 수집됐고,
                # 그대로 저장하면 "종료 481건"이 되고 다음 주엔 480건이 "신규"로 쏟아진다.
                # 직전의 절반도 못 모았으면 부분 수집으로 보고, 새로 보인 강좌만 반영한 채
                # 이전 목록을 유지한다(종료 판정은 하지 않음).
                # 기준을 절반에서 80%로 강화(2026-09-27 티처빌 700->460건 중단이 "종료 240건"으로 기록됨)
                if prev_items and len(prev_items) >= 20 and len(items) < len(prev_items) * 0.8:
                    kept = {it.get("url") for it in items}
                    merged = items + [it for it in prev_items if it.get("url") not in kept]
                    note = f"부분 수집({len(items)}/{len(prev_items)}건) - 이전 목록 유지, 종료 판정 생략"
                    diff = {"new": diff["new"], "removed": []}
                    items = merged
                result["companies"][name] = {
                    "url": cfg["url"], "count": len(items), "note": note, "courses": items,
                    "diff": diff, "diff_since": prev.get("captured_date"),
                }
                new_n, removed_n = len(diff["new"]), len(diff["removed"])
                # 첫 수집(비교 대상 없음)이나 직전 수집 0건이면 전부 "신규"로 잡히므로 기록하지 않는다.
                # 수집 범위 자체가 크게 늘어난 경우(상한 상향·크롤러 개선)도 새로 보인 강좌가
                # 신규 출시가 아니라 이전에 못 모았던 것이므로 기록하지 않는다(2026-09-27
                # 티처빌 500->700건 확장 때 199건이 NEW로 잘못 기록된 사고).
                if prev_items and len(items) <= len(prev_items) * 1.2:
                    append_new_courses(name, diff["new"], result["captured_date"])
                elif prev_items:
                    print(f"  {name}: 수집 범위 확장({len(prev_items)}->{len(items)}건) - 신규 기록 생략", file=sys.stderr)
                    diff = {"new": [], "removed": diff["removed"]}
                    result["companies"][name]["diff"] = diff
                print(f"  수집 {len(items)}건 / 목표 {args.max_items}건 - {note} (신규 {new_n}·종료 {removed_n})")
            except Exception as e:
                print(f"  [오류] {name} 수집 실패: {e}", file=sys.stderr)
                result["companies"][name] = {
                    "url": cfg["url"], "count": 0, "note": f"오류: {e}", "courses": [],
                    "diff": {"new": [], "removed": []}, "diff_since": prev.get("captured_date"),
                }
            finally:
                page.close()
        browser.close()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {out_path}")


if __name__ == "__main__":
    main()
