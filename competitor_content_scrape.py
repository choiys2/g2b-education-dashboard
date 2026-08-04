#!/usr/bin/env python3
"""
경쟁사(티처빌/아이스크림/비바샘) 홈페이지 공개 이벤트 목록을 매일 스크레이핑한다.
로그인 없이 보이는 화면만 본다(비로그인 공개 정보). 세 사이트 모두 robots.txt를
확인했다(2026-08-04): teacherville.co.kr "Allow: /", teacher.i-scream.co.kr
"Allow:/", t.vivasam.com은 자사 사이트라 별도 확인 불필요.

세 사이트가 서로 다른 프레임워크(구형 JSP, Next.js SPA 등)라 사이트별로
파싱 방식이 다르다 - DOM 셀렉터가 안정적인 곳은 셀렉터로, 구조가 불명확한
곳은 페이지 텍스트에서 "제목 다음 줄에 날짜범위"라는 반복 패턴을 정규식으로
잡는다(회사마다 캡처 정확도가 다를 수 있음 - 이 스크립트가 원본
content_snapshot.json에 명시된 것과 같은 한계다).
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT_PATH = Path("live/competitor_content_export.json")


def scrape_vivasam(page):
    page.goto("https://t.vivasam.com/events/ongoing?menuId=MENU0626", wait_until="networkidle", timeout=30000)
    items = page.eval_on_selector_all(
        'a[href^="/events/ongoing/"]',
        """els => els.map(el => {
            const h3 = el.querySelector('h3');
            const spans = [...el.querySelectorAll('span')].map(s => s.textContent.trim());
            const periodIdx = spans.indexOf('이벤트 기간');
            return {
                title: h3 ? h3.textContent.trim() : '',
                period: periodIdx >= 0 ? spans[periodIdx + 1] : '',
            };
        })""",
    )
    return [i for i in items if i["title"]]


def scrape_teacherville(page):
    page.goto("https://www.teacherville.co.kr/cs/eventpromotion/eventList.edu", wait_until="networkidle", timeout=30000)
    items = page.eval_on_selector_all(
        "li",
        """els => els.map(el => {
            const tit = el.querySelector('.tit');
            const day = el.querySelector('.day');
            if (!tit) return null;
            return { title: tit.textContent.trim(), period: day ? day.textContent.replace('기간','').trim() : '' };
        }).filter(Boolean)""",
    )
    return items


_DATE_RANGE_RE = re.compile(r"(\d{4}[.\-]\d{2}[.\-]\d{2})\s*~\s*(\d{4}[.\-]\d{2}[.\-]\d{2})")


def scrape_iscream(page):
    page.goto("https://teacher.i-scream.co.kr/event/all/list.do", wait_until="networkidle", timeout=30000)
    text = page.inner_text("body")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    items = []
    for i, line in enumerate(lines):
        m = _DATE_RANGE_RE.match(line)
        if m and i > 0:
            title = lines[i - 1]
            # 페이지네이션/메뉴 텍스트 등 제목이 아닌 줄 제외
            if len(title) < 3 or title in ("이벤트", "EVENT"):
                continue
            items.append({"title": title, "period": f"{m.group(1)} ~ {m.group(2)}"})
    return items


SCRAPERS = {
    "티처빌": ("https://www.teacherville.co.kr", scrape_teacherville),
    "아이스크림": ("https://teacher.i-scream.co.kr", scrape_iscream),
    "비바샘": ("https://t.vivasam.com", scrape_vivasam),
}


def main():
    result = {"captured_date": date.today().isoformat(), "companies": {}}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, (url, fn) in SCRAPERS.items():
            page = browser.new_page()
            try:
                events = fn(page)
                result["companies"][name] = {"url": url, "events": events, "event_count": len(events)}
                print(f"  {name}: {len(events)}건")
            except Exception as e:
                print(f"  [경고] {name} 스크레이핑 실패: {e}", file=sys.stderr)
                result["companies"][name] = {"url": url, "events": [], "event_count": 0, "error": str(e)}
            finally:
                page.close()
        browser.close()

    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {OUT_PATH}")


if __name__ == "__main__":
    main()
