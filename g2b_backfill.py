#!/usr/bin/env python3
"""
나라장터 낙찰 과거분 나눠 채우기(사용자 지시 2026-11-16: 과부하면 나눠서) - g2b_backfill.yml 이 하루 1구간씩 실행.
  구간: 60~240일 · 240~420일 · 420~600일 · 600~730일 전(최근 60일은 매일 배포가 이미 조회)
  진행 상태: history/g2b_backfill_state.json {"done": [...구간], "last": 날짜}. 4구간이 끝나면 아무것도 하지 않는다.
  결과는 history/competitor_wins.jsonl(기존 4개사)·history/org_watch.jsonl(수행기관 11곳)에 누적.
"""
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

STATE = Path("history/g2b_backfill_state.json")
WINDOWS = [(240, 60), (420, 240), (600, 420), (730, 600)]


def main():
    st = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"done": []}
    todo = [w for w in WINDOWS if f"{w[0]}-{w[1]}" not in st["done"]]
    if not todo:
        print("과거분 채우기 완료 - 할 일 없음")
        return 0
    days, until = todo[0]
    print(f"이번 구간: {days}~{until}일 전 (남은 구간 {len(todo)}개)")
    r = subprocess.run([sys.executable, "competitor_g2b_export.py", "--days", str(days), "--until-days", str(until),
                        "--out", "live/competitor_g2b_export.json"])
    if r.returncode == 0:
        st["done"].append(f"{days}-{until}")
        st["last"] = date.today().isoformat()
        STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
