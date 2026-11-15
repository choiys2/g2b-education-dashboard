#!/usr/bin/env python3
"""연결 키 점검 - 값은 절대 출력하지 않고 '설정됨/미설정'·형식·조회 결과 건수만 남긴다(CLAUDE.md 보안 1)."""
import os
import re


def st(name, rx=None):
    v = os.environ.get(name, "").strip()
    if not v:
        return "미설정"
    if rx and not re.match(rx, v):
        return "설정됨(형식 확인 필요)"
    return "설정됨"


print("SENTRY_DSN:", st("SENTRY_DSN", r"^https://[0-9a-f]+@[\w.-]+/\d+$"))
print("POSTHOG_KEY:", st("POSTHOG_KEY", r"^phc_\w+$"))
print("POSTHOG_PERSONAL_API_KEY:", st("POSTHOG_PERSONAL_API_KEY", r"^phx_\w+$"))
print("POSTHOG_PROJECT_ID:", st("POSTHOG_PROJECT_ID", r"^\d+$"))
print("FIRECRAWL_API_KEY:", st("FIRECRAWL_API_KEY", r"^fc-\w+$"))
try:
    u = __import__("dashboard_usage").load()
    if u is None:
        print("사용 분석 조회: 키 없음")
    elif u.get("error"):
        print("사용 분석 조회: 실패", u["error"])
    else:
        print("사용 분석 조회: 성공, 탭", len(u["rows"]), "개")
except Exception as e:  # noqa: BLE001
    print("사용 분석 조회: 오류", type(e).__name__)
