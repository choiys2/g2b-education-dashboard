#!/usr/bin/env python3
"""
live/_ai_rows_count.json(combine_dashboard.py가 남기는 AI_ROWS 전체) -> live/g2b_deadlines.ics

입찰 마감일을 구글/애플 캘린더에 "자동으로" 등록하려면 원래 OAuth(Calendar API,
사용자 동의 필요)가 있어야 하지만, 정적 GitHub Pages 파이프라인에서 사용자별
OAuth 토큰을 안전하게 보관할 방법이 없다. 대신 .ics "구독형 피드"로 우회한다:
이 파일을 고정 URL로 매일 새로 만들어 배포하면, 사용자가 캘린더 앱에 그 URL을
"URL로 캘린더 추가"로 한 번만 등록해두면 이후 캘린더 앱이 주기적으로(보통 몇
시간~하루 간격) 알아서 다시 읽어가 자동 갱신된다 - 매일 새로 등록할 필요 없음.
"""
import json
import re
import sys
from datetime import datetime, timezone

CALENDAR_NAME = "비바샘 나라장터 AI공고 마감일"


def esc(s):
    return re.sub(r"([,;\\])", r"\\\1", str(s or "")).replace("\n", "\\n")


def build_ics(ai_rows, calendar_name=CALENDAR_NAME):
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//vivasam//g2b-ai-deadlines//KO",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        f"X-WR-CALNAME:{esc(calendar_name)}",
        "X-WR-TIMEZONE:Asia/Seoul",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
        "X-PUBLISHED-TTL:PT6H",
    ]
    seen = set()
    for r in ai_rows:
        if r.get("status") == "낙찰정보":
            continue  # 이미 낙찰 완료된 과거 건 - 마감일 알림 대상 아님(입찰공고/사전규격만)
        date = r.get("date")
        if not date:
            continue
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(date))
        if not m:
            continue
        dt = f"{m.group(1)}{m.group(2)}{m.group(3)}"
        uid_src = f'{r.get("title")}|{r.get("org")}|{dt}'
        uid = re.sub(r"[^0-9A-Za-z]", "", uid_src)[:80] + "@vivasam-g2b-dashboard"
        if uid in seen:
            continue
        seen.add(uid)

        title = (r.get("title") or "")[:80]
        summary = f'[마감] {title} - {r.get("org","")}'
        desc_parts = [f'상태: {r.get("status","")}', f'지역: {r.get("region","")}']
        if r.get("amount"):
            desc_parts.append(f'예산: {r.get("amount"):,}원')
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now}",
            f"DTSTART;VALUE=DATE:{dt}",
            f"SUMMARY:{esc(summary)}",
            f"DESCRIPTION:{esc(chr(10).join(desc_parts))}",
        ]
        if r.get("url"):
            lines.append(f'URL:{r.get("url")}')
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def main():
    in_path = sys.argv[1] if len(sys.argv) > 1 else "live/_ai_rows_count.json"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "live/g2b_deadlines.ics"
    with open(in_path, encoding="utf-8") as f:
        ai_rows = json.load(f)
    ics = build_ics(ai_rows)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        f.write(ics)
    print(f"saved {out_path}: {ics.count('BEGIN:VEVENT')}건 일정")


if __name__ == "__main__":
    main()
