#!/usr/bin/env python3
"""
NEIS 학사일정(SchoolSchedule) 표본 수집 -> history/neis_schedule.json (주 1회, neis_schedule.yml)

B2S 학사일정 패널용. 전국 전수는 호출량이 커서 시도 x 학교급(초·중·고)마다 표본 학교 SAMPLE 개교의
앞으로 DAYS 일 일정을 받아, 시도·학교급별 대표 날짜(중앙값)만 저장한다(학교명은 저장하지 않음).

  - 행사 분류: 시험(고사·평가) / 방학식 / 겨울·여름방학 시작 / 개학 / 졸업식 / 종업식 / 재량휴업
  - 주별 '방학 중인 표본 학교 비율' = 교사가 연수를 들을 여유가 큰 주(연수 모집·B2C 기획전 시점)
환경변수: NEIS_KEY (나이스 개방포털 인증키 - 기존 neis_full_export.py 와 같은 키)
"""
import json
import os
import re
import statistics
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

KEY = os.environ.get("NEIS_KEY", "")
BASE = "https://open.neis.go.kr/hub"
OUT = Path("history/neis_schedule.json")
SAMPLE = 8
DAYS = 150
REGIONS = [("B10", "서울"), ("C10", "부산"), ("D10", "대구"), ("E10", "인천"), ("F10", "광주"), ("G10", "대전"),
           ("H10", "울산"), ("I10", "세종"), ("J10", "경기"), ("K10", "강원"), ("M10", "충북"), ("N10", "충남"),
           ("P10", "전북"), ("Q10", "전남"), ("R10", "경북"), ("S10", "경남"), ("T10", "제주")]
KINDS = {"초": "초등학교", "중": "중학교", "고": "고등학교"}
EVENTS = [  # (키, 정규식) - 위에서부터 먼저 맞는 것
    ("방학식", r"방학식"),
    ("졸업식", r"졸업"),
    ("종업식", r"종업|수료식"),
    ("개학", r"개학|시업식|입학식"),
    ("겨울방학", r"겨울\s?방학|동계\s?방학"),
    ("여름방학", r"여름\s?방학|하계\s?방학"),
    ("봄방학", r"봄\s?방학|학년말\s?방학"),
    ("시험", r"고사|시험|평가"),
    ("재량휴업", r"재량\s?휴업|재량\s?휴일"),
]
EV_RE = [(k, re.compile(p)) for k, p in EVENTS]


def call(op, params, retries=3):
    url = f"{BASE}/{op}?" + urllib.parse.urlencode({"KEY": KEY, "Type": "json", **params})
    for i in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if i == retries - 1:
                print(f"  [경고] {op} 실패: {str(e)[:120]}", file=sys.stderr)
                return None
            time.sleep(1.5)


def rows_of(data, op):
    try:
        return data[op][1]["row"]
    except (TypeError, KeyError, IndexError):
        return []


def sample_schools(code, kind):
    rows = rows_of(call("schoolInfo", {"pIndex": 1, "pSize": 300, "ATPT_OFCDC_SC_CODE": code, "SCHUL_KND_SC_NM": kind}), "schoolInfo")
    rows = [r for r in rows if r.get("SD_SCHUL_CODE")]
    if len(rows) <= SAMPLE:
        return [r["SD_SCHUL_CODE"] for r in rows]
    step = len(rows) / SAMPLE  # 고르게 띄워 뽑는다(매주 같은 표본 -> 추이 비교 가능)
    return [rows[int(i * step)]["SD_SCHUL_CODE"] for i in range(SAMPLE)]


def school_events(code, sc, d0, d1):
    out = []
    for page in (1, 2, 3):
        rows = rows_of(call("SchoolSchedule", {"pIndex": page, "pSize": 1000, "ATPT_OFCDC_SC_CODE": code, "SD_SCHUL_CODE": sc,
                                               "AA_FROM_YMD": d0.strftime("%Y%m%d"), "AA_TO_YMD": d1.strftime("%Y%m%d")}), "SchoolSchedule")
        out += rows
        if len(rows) < 1000:
            break
        time.sleep(0.12)
    return out


def summarize(rows):
    """학교 1곳 -> {행사: 날짜}, 방학 날짜 집합.
    방학 표기는 학교마다 다르다(시작일 하루만 / 매일 / 겨울·학년말 방학 분리). 방학 표기 날짜들을 4일 이내 간격으로 이어
    가장 긴 연속 구간을 '겨울방학'으로 보고, 그 시작·끝과 직후 개학(개학·시업식)을 잡는다."""
    days = {}
    for r in rows:
        nm, ymd = (r.get("EVENT_NM") or "").strip(), r.get("AA_YMD") or ""
        if len(ymd) != 8 or not nm:
            continue
        d = date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:]))
        for k, rx in EV_RE:
            if rx.search(nm):
                days.setdefault(k, set()).add(d)
                break
    vdays = sorted(days.get("겨울방학", set()) | days.get("봄방학", set()))
    runs, cur = [], []
    for d in vdays:
        if cur and (d - cur[-1]).days > 4:
            runs.append(cur); cur = []
        cur.append(d)
    if cur:
        runs.append(cur)
    first, vac = {}, set()
    for run in runs:
        vac |= {run[0] + timedelta(n) for n in range((run[-1] - run[0]).days + 1)}
    if runs:
        main = max(runs, key=lambda r: ((r[-1] - r[0]).days, len(r)))
        end = main[-1]
        nxt = [x for x in days.get("개학", ()) if x > main[0]]
        if (end - main[0]).days < 3 and nxt:  # 시작일만 적는 학교: 개학 전날까지를 방학으로
            end = min(nxt) - timedelta(1)
            vac |= {main[0] + timedelta(n) for n in range((end - main[0]).days + 1)}
        main = [main[0], end]
        first["겨울방학"], first["방학 종료"] = main[0], main[-1]
        bs = [x for x in days.get("방학식", ()) if timedelta(0) <= main[0] - x <= timedelta(14)]
        if bs:
            first["방학식"] = max(bs)
        back = [x for x in days.get("개학", ()) if x > main[-1]]
        if back:
            first["개학"] = min(back)
    for k in ("시험", "졸업식", "종업식", "재량휴업"):
        if k in days:
            first[k] = min(days[k])
    return first, vac


def med(ds):
    if not ds:
        return None
    o = sorted(x.toordinal() for x in ds)
    return date.fromordinal(int(statistics.median(o))).isoformat()


def main():
    if not KEY:
        print("NEIS_KEY 없음 - 건너뜀")
        return 0
    today = date.today()
    d1 = today + timedelta(DAYS)
    weeks = [today - timedelta(today.weekday()) + timedelta(7 * i) for i in range(DAYS // 7)]
    regions, nat_vac, n_total, calls = [], {w: [0, 0] for w in weeks}, 0, 0
    for code, reg in REGIONS:
        row = {"region": reg, "levels": {}}
        for lv, kind in KINDS.items():
            firsts, n = {}, 0
            for sc in sample_schools(code, kind):
                rows = school_events(code, sc, today, d1)
                calls += 1
                time.sleep(0.12)
                if not rows:
                    continue
                n += 1
                f, vac = summarize(rows)
                for k, d in f.items():
                    firsts.setdefault(k, []).append(d)
                for w in weeks:
                    nat_vac[w][1] += 1
                    if any(w + timedelta(i) in vac for i in range(5)):  # 그 주 평일 중 하루라도 방학
                        nat_vac[w][0] += 1
            row["levels"][lv] = {"n": n, **{k: med(v) for k, v in firsts.items()},
                                 "cover": {k: len(v) for k, v in firsts.items()}}
            n_total += n
        regions.append(row)
        print(f"{reg}: " + " · ".join(f"{lv} {row['levels'][lv]['n']}교 겨울방학 {row['levels'][lv].get('겨울방학') or '-'}" for lv in KINDS))
    out = {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "from": today.isoformat(), "to": d1.isoformat(),
           "sample_per_cell": SAMPLE, "n_schools": n_total, "calls": calls, "regions": regions,
           "weeks": [{"week": w.isoformat(), "vac_share": round(a / b * 100) if b else None} for w, (a, b) in nat_vac.items()]}
    if n_total == 0:
        print("수집된 학사일정 없음 - 기존 파일 유지")
        return 0
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"저장: {OUT} · 표본 {n_total}교 · 호출 {calls}회")
    return 0


if __name__ == "__main__":
    sys.exit(main())
