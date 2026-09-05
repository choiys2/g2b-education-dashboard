#!/usr/bin/env python3
"""1회성 진단 도구. competitor_course_catalog_scrape.py의 href 패턴 기반 추출이
실제 강좌 카드가 아니라 상단 메뉴 링크('나의강의실', '연수신청' 등)를 잡고 있는
것으로 확인돼, 실제 강좌 카드의 URL/클래스 패턴을 직접 보기 위해 만들었다.
렌더링된 DOM에서 script/style/svg 태그와 공백만 제거해 git에 부담 없이 커밋될
크기로 줄인다. 확인이 끝나면 이 스크립트와 debug_html/은 지워도 된다.
"""
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SITES = {
    "티처빌": "https://www.teacherville.co.kr/trainapply/allCourseList.edu",
    "아이스크림": "https://teacher.i-scream.co.kr/course/crs/creditList.do?searchOrdinalTyCode=TY01&searchOrderField=NEW",
    "비바샘": "https://t.vivasam.com/courses/job?menuId=MENU0610",
}
OUT_DIR = Path("debug_html")
MAX_CHARS = 700_000


def trim(html):
    html = re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.S | re.I)
    html = re.sub(r"<style\b[^>]*>.*?</style>", "", html, flags=re.S | re.I)
    html = re.sub(r"<svg\b[^>]*>.*?</svg>", "", html, flags=re.S | re.I)
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    html = re.sub(r">\s+<", "><", html)
    return html


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, url in SITES.items():
            page = browser.new_page()
            try:
                # networkidle 대기는 티처빌에서 30초 타임아웃으로 실패했다(백그라운드
                # 폴링/애널리틱스가 계속 도는 것으로 추정) - domcontentloaded + 고정
                # 대기로 교체.
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(4000)
                html = trim(page.evaluate("document.documentElement.outerHTML"))
                out = OUT_DIR / f"{name}.html"
                out.write_text(html[:MAX_CHARS], encoding="utf-8")
                print(f"{name}: 원본 {len(html)}자 -> 저장 {min(len(html), MAX_CHARS)}자 ({out})")
            except Exception as e:
                print(f"[오류] {name}: {e}", file=sys.stderr)
            finally:
                page.close()
        browser.close()


if __name__ == "__main__":
    main()
