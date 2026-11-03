#!/usr/bin/env python3
"""
주간보고 JSON 품질 검사기 — 표준 라이브러리만 사용(비공개 저장소 tools/ 에 같은 파일을 두고 업로드 때 자동 실행).

검사: 파일명·주차 일치 / 필수 칸 / 날짜 형식 / 글 속 'M.D(요일)'·'M/D(요일)' 요일 오류 / 공정률 0~100 숫자 /
      status·urgency·level 값 / 직전 주 대비 공정률 하락(사유 없으면 경고) / 지난주에 있던 프로젝트가 사라짐 /
      이름이 조금 바뀐 프로젝트(같은 프로젝트로 보이는데 표기만 다름)
결과: [(등급, 메시지)] — 등급 'error'(반영 전 고쳐야 함) · 'warn'(확인 권장)

  python weekly_check.py weekly_data/2026-11-W2.json [weekly_data/]   # 폴더를 주면 직전 주와 비교
  종료 코드: error 가 있으면 1
"""
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

WEEK_RE = re.compile(r"^(\d{4})-(\d{2})-W(\d)$")
WK = "월화수목금토일"
REQ = ["meta", "summary", "projects", "milestones"]
STATUS = {"on_track", "at_risk", "delayed", "completed"}
URG = {"critical", "high", "medium", "low", "done"}
DAY_RE = re.compile(r"(?<!\d)(1[0-2]|0?[1-9])\s*[./]\s*([12]\d|3[01]|0?[1-9])\s*\(\s*([월화수목금토일])\s*\)")
REASON = re.compile(r"재산정|재설정|범위|기준\s*변경|일정\s*변경|조정|추가\s*개발|리베이스|scope", re.I)


def _canon(name):
    try:
        return __import__("owner_weekly").canon(name)
    except Exception:
        return re.sub(r"\s+", "", name or "")


def monday_of(wid):
    """'2026-11-W1' → 그 달 첫 월요일 + (N-1)주 (콘텐츠Company 주차 표기)"""
    m = WEEK_RE.match(wid)
    y, mo, n = int(m.group(1)), int(m.group(2)), int(m.group(3))
    d = date(y, mo, 1)
    d += timedelta(days=(7 - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from _strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from _strings(v)


def check(w, wid, prev=None):
    out = []
    E = lambda m: out.append(("error", m))
    W = lambda m: out.append(("warn", m))
    if not isinstance(w, dict):
        return [("error", "JSON 최상위가 객체({})가 아닙니다")]
    if not WEEK_RE.match(wid or ""):
        E(f"파일명 '{wid}.json' 이 YYYY-MM-WN 형식이 아닙니다(예: 2026-11-W2.json)")
        return out
    for k in REQ:
        if k not in w:
            E(f"필수 칸 '{k}' 없음")
    meta = w.get("meta") or {}
    if meta.get("week_id") and meta["week_id"] != wid:
        E(f"meta.week_id '{meta['week_id']}' 와 파일명 '{wid}' 가 다릅니다")
    mon = monday_of(wid)
    try:
        ds = date.fromisoformat(str(meta.get("date_start", ""))[:10])
        if abs((ds - mon).days) > 3:
            W(f"meta.date_start {ds} 가 {wid} 의 월요일({mon})과 {abs((ds - mon).days)}일 차이 — 주차 번호 확인")
    except ValueError:
        W("meta.date_start 가 없거나 YYYY-MM-DD 형식이 아닙니다")

    # 글 속 요일 오류 (예: '11.7 (금)' 인데 실제 토요일)
    seen = set()
    for s in _strings(w):
        for mo, d, wd in DAY_RE.findall(s):
            y = mon.year + 1 if int(mo) < mon.month - 6 else mon.year - 1 if int(mo) > mon.month + 6 else mon.year
            try:
                real = WK[date(y, int(mo), int(d)).weekday()]
            except ValueError:
                real = None
            if real and real != wd and (mo, d, wd) not in seen:
                seen.add((mo, d, wd))
                W(f"요일 오류: '{int(mo)}.{int(d)}({wd})' → 실제 {real}요일 — \"{s[:40]}\"")

    names = {}
    for i, p in enumerate(w.get("projects") or []):
        nm = p.get("name") or f"#{i + 1}"
        pg = p.get("progress")
        if not isinstance(pg, (int, float)) or isinstance(pg, bool):
            E(f"[{nm}] progress 가 숫자가 아닙니다: {pg!r} (예: 85)")
        elif not 0 <= pg <= 100:
            E(f"[{nm}] progress {pg} 가 0~100 밖입니다")
        if p.get("status") and p["status"] not in STATUS:
            W(f"[{nm}] status '{p['status']}' → {', '.join(sorted(STATUS))} 중 하나")
        if p.get("next_date"):
            try:
                date.fromisoformat(str(p["next_date"])[:10])
            except ValueError:
                E(f"[{nm}] next_date '{p['next_date']}' 가 YYYY-MM-DD 가 아닙니다")
        names[_canon(nm)] = (nm, pg if isinstance(pg, (int, float)) else None)
    for m in w.get("milestones") or []:
        try:
            date.fromisoformat(str(m.get("date", ""))[:10])
        except ValueError:
            E(f"마일스톤 '{(m.get('label') or '')[:30]}' 날짜 '{m.get('date')}' 가 YYYY-MM-DD 가 아닙니다")
        if m.get("urgency") and m["urgency"] not in URG:
            W(f"마일스톤 urgency '{m['urgency']}' → {', '.join(sorted(URG))} 중 하나")
        if re.search(r"D-\d+", m.get("label") or ""):
            W(f"마일스톤 라벨에 D-day 표기: '{m['label'][:30]}' (화면이 오늘 기준으로 다시 셉니다 — 빼 주세요)")
    for r in w.get("risks") or []:
        if r.get("level") and r["level"] not in URG:
            W(f"리스크 level '{r['level']}' → critical/high/medium/low 중 하나")

    if prev:
        alltext = " ".join(_strings(w))
        pnames = {}
        for p in prev.get("projects") or []:
            pnames[_canon(p.get("name"))] = (p.get("name"), p.get("progress"))
        for k, (nm, pg) in names.items():
            if k in pnames:
                pn, ppg = pnames[k]
                if pn != nm:
                    W(f"프로젝트 이름 표기 변경: 지난주 '{pn}' → 이번 주 '{nm}' (같은 이름으로 맞추면 추이가 정확해집니다)")
                if isinstance(pg, (int, float)) and isinstance(ppg, (int, float)) and pg < ppg:
                    has_reason = bool(REASON.search(alltext)) and nm.split()[0] in alltext
                    W(f"[{nm}] 공정률 하락 {ppg}% → {pg}%" + ("" if has_reason else " — 사유(범위 재산정·일정 변경 등)를 next_milestone 이나 risks 에 적어 주세요"))
        for k, (pn, ppg) in pnames.items():
            if k not in names and not (isinstance(ppg, (int, float)) and ppg >= 100):
                W(f"지난주 프로젝트 '{pn}'({ppg}%) 가 이번 주에 없습니다 — 완료(100%)·보류 여부 표기 권장")
    return out


def prev_of(folder, wid):
    files = sorted(f for f in Path(folder).glob("*.json") if WEEK_RE.match(f.stem) and f.stem < wid)
    key = lambda f: tuple(int(x) for x in WEEK_RE.match(f.stem).groups())
    files = sorted(files, key=key)
    files = [f for f in files if key(f) < tuple(int(x) for x in WEEK_RE.match(wid).groups())]
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except ValueError:
        return None


def check_file(path, folder=None):
    p = Path(path)
    try:
        w = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        return [("error", f"JSON 문법 오류: {e}")]
    folder = folder or p.parent
    return check(w, p.stem, prev_of(folder, p.stem) if WEEK_RE.match(p.stem) else None)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    bad = 0
    for f in sys.argv[1:]:
        if Path(f).is_dir() or not f.endswith(".json") or Path(f).name == "index.json":
            continue
        res = check_file(f)
        print(f"■ {Path(f).name}: 오류 {sum(1 for l, _ in res if l == 'error')} · 확인 {sum(1 for l, _ in res if l == 'warn')}")
        for lv, msg in res:
            print(f"  {'❌' if lv == 'error' else '⚠️'} {msg}")
        bad += any(l == "error" for l, _ in res)
    sys.exit(1 if bad else 0)
