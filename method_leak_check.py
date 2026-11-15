#!/usr/bin/env python3
"""
방법론 비노출 점검(CLAUDE.md '노출 위치' 5) - 일반 사용자(CP) 화면 문구에 제작·수집 방식이 드러나는지 찾는다.
  대상: dashboard_template.html 의 화면 글자(주석 제외 - 주석은 combine_dashboard.strip_dev_comments 가 배포본에서 지움).
  찾는 것: API·Gemini·Firecrawl·robots·크롤·스크레이핑·자동 수집·수집 대기·시크릿·GitHub·개방포털·공공데이터포털·배포 때·.py 등.
  관리 탭(관리 비밀번호 암호화) 문구는 admin_*.py·strategy_room.py 에서 만들므로 대상이 아니다.
  결과는 경고(::warning)만 - 푸시를 막지 않는다. 허용 예외는 ALLOW 에 추가.
"""
import re
import sys
from pathlib import Path

KW = re.compile(r"(\bAPI\b|Gemini|Firecrawl|Playwright|PostHog|Sentry|GitHub|Cloudflare|robots|스크레이핑|크롤|\.py\b|자동 수집|자동으로 열람|수집 대기|첫 수집|서비스계정|공공데이터포털|개방포털|시크릿|Secret|배포 때|다음 배포|odcloud|data\.go\.kr|API 키|해외 서버|Windsor|Supabase|Vercel)")
ALLOW = ("xAPI",)


def scan(path):
    out = []
    src = Path(path).read_text(encoding="utf-8")
    try:  # 배포본과 같은 기준: 개발 주석을 걷어낸 뒤 검사
        from combine_dashboard import strip_dev_comments
        src = strip_dev_comments(src)
    except Exception:  # noqa: BLE001
        pass
    for i, ln in enumerate(src.split("\n"), 1):
        t = re.sub(r"<!--.*?-->", "", ln)
        t = re.sub(r"/\*.*?\*/", "", t)
        t = re.sub(r"(^|[^:'\"`])//.*$", r"\1", t)
        t = re.sub(r"^\s*\*.*$", "", t)  # 여러 줄 주석 안쪽 줄
        if not re.search(r"[가-힣]", t) or any(a in t for a in ALLOW):
            continue
        m = KW.search(t)
        if m:
            a = max(0, m.start() - 40)
            out.append((i, m.group(0), t[a:m.end() + 40].strip()))
    return out


if __name__ == "__main__":
    hits = scan(sys.argv[1] if len(sys.argv) > 1 else "dashboard_template.html")
    for i, k, ctx in hits:
        print(f"::warning file=dashboard_template.html,line={i}::공개 화면에 제작·수집 방식 노출 의심 [{k}] …{ctx}…")
    print(f"방법론 비노출 점검: 의심 {len(hits)}건")
