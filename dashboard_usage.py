#!/usr/bin/env python3
"""
B4 대시보드 사용 분석 - PostHog 에 쌓인 'tab_view' 이벤트(탭 이름만, 개인정보 없음)를 최근 28일 집계.

  - 수집: 화면(dashboard_template.html)이 탭을 열 때 PostHog 로 {탭 이름, 임시 세션 번호}만 보낸다.
    이메일·이름·입력값·화면 녹화·IP 기반 개인 식별은 쓰지 않는다. 키(POSTHOG_KEY, 공개 쓰기 전용)는 시크릿에서 배포 때만 넣는다.
  - 조회: POSTHOG_PERSONAL_API_KEY(읽기 전용) + POSTHOG_PROJECT_ID 가 있으면 관리 탭 표를 만든다. 없으면 None.
  - 무료 요금제(월 100만 이벤트) 안에서 사용 - 하루 수백 건 수준.
"""
import json
import os
import urllib.request

API = "https://us.posthog.com/api/projects/{}/query/"


def load(days=28):
    key, pid = os.environ.get("POSTHOG_PERSONAL_API_KEY", "").strip(), os.environ.get("POSTHOG_PROJECT_ID", "").strip()
    if not (key and pid.isdigit()):
        return None
    q = ("SELECT properties.tab AS tab, count() AS views, count(DISTINCT properties.sid) AS sessions, "
         "max(timestamp) AS last FROM events WHERE event = 'tab_view' "
         f"AND timestamp > now() - INTERVAL {int(days)} DAY GROUP BY tab ORDER BY views DESC LIMIT 80")
    body = json.dumps({"query": {"kind": "HogQLQuery", "query": q}}).encode()
    req = urllib.request.Request(API.format(pid), data=body, method="POST",
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read().decode())
        rows = [{"tab": t or "-", "views": int(v), "sessions": int(s), "last": str(l)[:16]} for t, v, s, l in (d.get("results") or [])]
        return {"days": days, "rows": rows}
    except Exception as e:  # noqa: BLE001
        print("사용 분석 조회 실패:", type(e).__name__)
        return {"days": days, "rows": [], "error": type(e).__name__}


if __name__ == "__main__":
    print(json.dumps(load(), ensure_ascii=False, indent=1))
