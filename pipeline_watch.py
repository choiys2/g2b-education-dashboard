#!/usr/bin/env python3
"""
B1 수집 장애 감시 - 매일 배포 끝에 실행(deploy.yml, if: always()).

  - 핵심 점검: 나라장터 건전성, 입찰공고·낙찰 0건, 대시보드 조합 성공, Cloudflare 배포 성공
  - 결과를 history/pipeline_watch.jsonl 에 1줄 누적(최근 120일) - 관리 탭 '시스템 구조'에서 표로 본다
  - SENTRY_DSN 이 있으면 Sentry 크론 감시(daily-deploy)에 ok/error 체크인 → 실패·미실행 시 Sentry 가 메일 알림
    (무료 요금제 크론 감시 1개 안에서 사용. DSN 은 시크릿에만, 로그에는 '설정됨/미설정'만)
  - 빠른 배포(수집 생략)는 체크인하지 않는다(수집이 실제로 돈 날만 감시 대상)
env: QUICK, HEALTHY, COMBINE, CFDEPLOY, EVENT
"""
import json
import os
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "history" / "pipeline_watch.jsonl"
SLUG = "daily-deploy"
KST = timezone(timedelta(hours=9))


def _j(p, d=None):
    try:
        return json.loads((HERE / p).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return d


def checks():
    env = os.environ.get
    out = []
    full = _j("live/full_live.json", {}) or {}
    a = full.get("analytics") or {}
    nb, nw, ns = len(a.get("입찰공고") or []), len(a.get("낙찰정보") or []), len(a.get("사전규격") or [])
    out.append(("나라장터 건전성", env("HEALTHY") == "true", f"입찰 {nb} · 낙찰 {nw} · 사전규격 {ns}", True))
    out.append(("입찰공고·낙찰 수집", nb > 0 and nw > 0, "0건이면 조회 조건 변경 의심(g2b_probe_api.yml)", True))
    out.append(("대시보드 조합", env("COMBINE") == "success", env("COMBINE") or "-", True))
    out.append(("Cloudflare 배포", env("CFDEPLOY") == "success", env("CFDEPLOY") or "-", True))
    ec = _j("history/edu_contracts_status.json", {}) or {}
    out.append(("교육청 수의계약", bool(ec.get("total")), f"{ec.get('total', 0)}건", False))
    ai = _j("history/ai_insights_status.json", {}) or {}
    out.append(("AI 해석(Gemini)", bool(ai.get("ok")), "실패 시 이전 해석본 사용", False))
    return out


def checkin(status):
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    m = re.match(r"https://([0-9a-f]+)@([^/]+)/(\d+)$", dsn)
    if not m:
        print("Sentry:", "미설정" if not dsn else "형식 오류")
        return "미설정" if not dsn else "형식 오류"
    key, host, pid = m.groups()
    url = f"https://{host}/api/{pid}/cron/{SLUG}/{key}/?status={status}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=15) as r:
            print("Sentry 체크인:", status, r.status)
            return f"{status} 전송"
    except Exception as e:  # noqa: BLE001
        print("Sentry 체크인 실패:", type(e).__name__)
        return "전송 실패"


def main():
    quick = os.environ.get("QUICK") == "true"
    cs = checks()
    critical_fail = [n for n, ok, _, crit in cs if crit and not ok]
    status = "error" if critical_fail else "ok"
    for n, ok, memo, crit in cs:
        print(f"  {'✅' if ok else ('❌' if crit else '⚠️')} {n} - {memo}")
    sent = "빠른 배포 - 체크인 생략" if quick else checkin(status)
    row = {"at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "event": os.environ.get("EVENT", ""), "quick": quick,
           "status": status, "fail": critical_fail, "sentry": sent,
           "checks": [{"n": n, "ok": ok, "m": memo, "c": crit} for n, ok, memo, crit in cs]}
    lines = OUT.read_text(encoding="utf-8").splitlines() if OUT.exists() else []
    lines = (lines + [json.dumps(row, ensure_ascii=False)])[-120:]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"감시 결과: {status}" + (f" ({', '.join(critical_fail)})" if critical_fail else ""))
    if critical_fail:
        print(f"::warning::수집 장애 감시: {', '.join(critical_fail)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
