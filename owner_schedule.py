#!/usr/bin/env python3
"""
관리 탭 '내 일정' 화면(대표 전용) - 내 일정 × 나라장터 입찰 마감 × 콘텐츠Company 주간보고 일정을 날짜별로 겹쳐 보고,
겹침(이중 예약·부재일 마감)을 자동으로 찾는다. 금요일 '내 주간업무보고' 초안 보관함도 함께 보여 준다.

- 내 일정: 비공개 저장소 my_schedule/latest.json — 루틴 허브의 '일정 금고 저장' 예약 작업이 매일 05:37 에
  Google Calendar 앞으로 14일(+지난 1일) 일정을 전부(제목·시간·장소·참석자·설명) 저장한다.
  {"generated": "...", "range": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
   "events": [{"start": "2026-11-04T10:00:00+09:00" | "2026-11-04", "end": ..., "all_day": bool,
               "title": "", "location": "", "attendees": [""], "description": "", "calendar": ""}]}
- 내 주간보고: 비공개 저장소 my_weekly/YYYY-MM-WN.md — '주간업무보고 초안' 예약 작업이 금요일에 저장.
- 입찰 마감: live/_ai_rows_count.json(공개 데이터, ics_feed 와 같은 원천).
- 결과 HTML 은 admin_structure.build_html 에 붙어 ADMIN_PASSWORD 로 암호화된다(공개 화면·history 미기록).
"""
import html
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
E = html.escape
AWAY = re.compile(r"휴가|연차|반차|출장|외근|여행|부재|교육\s*참석|워크숍")
WK = "월화수목금토일"


def _today():
    return (datetime.now(timezone.utc) + timedelta(hours=9)).date()


def _dirs(name):
    env = os.environ.get("PRIVATE_DATA_DIR", "").strip()
    out = [Path(env) / name] if env else []
    return out + [HERE / "_private" / name, HERE / f"{name}.local"]


def _parse(v):
    """'2026-11-04' 또는 ISO 시각 → (date, datetime|None)"""
    v = str(v or "").strip()
    if not v:
        return None, None
    try:
        if len(v) == 10:
            return date.fromisoformat(v), None
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        if dt.tzinfo:
            dt = dt.astimezone(timezone(timedelta(hours=9)))
        return dt.date(), dt
    except ValueError:
        return None, None


def load_schedule():
    for d in _dirs("my_schedule"):
        f = d / "latest.json"
        if f.is_file():
            try:
                s = json.loads(f.read_text(encoding="utf-8"))
            except ValueError as e:
                print(f"[경고] my_schedule 읽기 실패: {str(e)[:80]}")
                return None
            return s if isinstance(s, dict) else None
    return None


def events(sched):
    out = []
    for e in (sched or {}).get("events") or []:
        d, st = _parse(e.get("start"))
        if not d:
            continue
        ed, en = _parse(e.get("end"))
        title = re.sub(r"^\s*(전달|FW|Fwd)\s*:\s*", "", e.get("title") or "", flags=re.I).strip()
        all_day = bool(e.get("all_day")) or st is None
        if all_day and ed and ed > d:
            ed = ed - timedelta(days=1)  # Google 종일 일정의 end 는 다음 날(배타적)
        out.append({"date": d, "end_date": ed or d, "st": st, "en": en, "all_day": all_day,
                    "title": title or "(제목 없음)", "location": e.get("location") or "", "attendees": e.get("attendees") or [],
                    "description": e.get("description") or "", "away": bool(AWAY.search(title))})
    return sorted(out, key=lambda x: (x["date"], x["st"] or datetime.min.replace(tzinfo=timezone.utc)))


def bid_deadlines(today, days=14):
    try:
        rows = json.loads((HERE / "live/_ai_rows_count.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out, seen = [], set()
    for r in rows if isinstance(rows, list) else []:
        if r.get("status") == "낙찰정보":
            continue
        try:
            d = date.fromisoformat(str(r.get("date") or "")[:10])
        except ValueError:
            continue
        k = (d, r.get("title"), r.get("org"))
        if k in seen or not (today <= d <= today + timedelta(days=days)):
            continue
        seen.add(k)
        out.append({"date": d, "title": r.get("title") or "", "org": r.get("org") or "", "amount": r.get("amount"), "status": r.get("status") or ""})
    return out


def weekly_milestones():
    try:
        ow = __import__("owner_weekly")
        weeks = ow.load_weeks()
        return ow.upcoming(weeks, days=14) if weeks else []
    except Exception:
        return []


def conflicts(evs, bids, mss):
    """[(date, 설명)] — 이중 예약(시간 겹침), 부재일(휴가·출장 등)에 걸린 마감·핵심 일정, 하루 일정 6건 이상."""
    out = []
    by_day = {}
    for e in evs:
        d = e["date"]
        while d <= e["end_date"]:
            by_day.setdefault(d, []).append(e)
            d += timedelta(days=1)
    timed = [e for e in evs if e["st"] and e["en"]]
    for i, a in enumerate(timed):
        for b in timed[i + 1:]:
            if a["date"] == b["date"] and a["st"] < b["en"] and b["st"] < a["en"]:
                out.append((a["date"], f"이중 예약: {a['st']:%H:%M} {a['title']} ↔ {b['st']:%H:%M} {b['title']}"))
    for d, lst in by_day.items():
        away = [e["title"] for e in lst if e["away"]]
        if away:
            n_b = sum(1 for b in bids if b["date"] == d)
            crit = [m.get("label") for md, m in mss if md == d and m.get("urgency") in ("critical", "high")]
            if n_b or crit:
                what = ", ".join(([f"입찰 마감 {n_b}건"] if n_b else []) + crit[:2])
                out.append((d, f"부재({away[0]}) 중 {what}"))
        if len(lst) >= 6:
            out.append((d, f"일정 과밀: {len(lst)}건"))
    return sorted(set(out))


def my_weekly():
    items = {}
    for d in _dirs("my_weekly"):
        if d.is_dir():
            for f in d.glob("*.md"):
                if re.fullmatch(r"\d{4}-\d{2}-W\d", f.stem):  # README 등 안내 파일 제외
                    items.setdefault(f.stem, f)
    return [(k, items[k].read_text(encoding="utf-8")) for k in sorted(items, reverse=True)]


def _ev_line(e):
    t = "종일" if e["all_day"] else f"{e['st']:%H:%M}–{e['en']:%H:%M}" if e["en"] else f"{e['st']:%H:%M}"
    extra = " · ".join(x for x in [e["location"], f"참석 {len(e['attendees'])}명" if e["attendees"] else ""] if x)
    tip = E((e["description"] or "")[:400] + ("\n참석: " + ", ".join(map(str, e["attendees"][:20])) if e["attendees"] else ""))
    away = " <span style='color:#8b5cf6;font-weight:700;'>[부재]</span>" if e["away"] else ""
    ex = f" <span style='color:var(--muted);font-size:12px;'>({E(extra)})</span>" if extra else ""
    return f"<div style='font-size:13px;padding:2px 0;' title='{tip}'>📅 <b>{E(t)}</b> {E(e['title'])}{away}{ex}</div>"


def build(sec):
    today = _today()
    sched = load_schedule()
    evs = [e for e in events(sched) if today - timedelta(days=1) <= e["date"] <= today + timedelta(days=14)]
    bids = bid_deadlines(today)
    mss = weekly_milestones()
    cf = conflicts(evs, bids, mss)
    parts = []

    if not sched:
        parts.append(sec("내 일정 (대표 전용)", "내 일정 × 입찰 마감 × 주간보고 일정",
                         '<p class="tt-note">아직 내 일정이 없습니다. 루틴 허브의 <b>일정 금고 저장</b> 예약 작업이 비공개 저장소 '
                         '<code>my_schedule/latest.json</code> 을 만들면 다음 배포부터 채워집니다. 아래 입찰 마감·주간보고 일정은 먼저 보여 드립니다.</p>'))
    cf_html = "".join(f"<div style='padding:5px 0;border-bottom:1px dashed var(--border);font-size:13px;'>"
                      f"<b>{d.month}.{d.day}({WK[d.weekday()]})</b> {E(t)}</div>" for d, t in cf)
    parts.append(sec("겹침·주의 (14일)", "이중 예약 · 휴가/출장/외근 중 마감이나 핵심 일정 · 하루 6건 이상",
                     cf_html or "<p style='color:var(--muted);font-size:13px;'>겹치는 일정 없음</p>"))

    rows = []
    for i in range(-1, 15):
        d = today + timedelta(days=i)
        mine = [e for e in evs if e["date"] <= d <= e["end_date"]]
        b = [x for x in bids if x["date"] == d]
        m = [x for md, x in mss if md == d]
        if not (mine or b or m):
            continue
        cell = "".join(_ev_line(e) for e in mine)
        cell += "".join(f"<div style='font-size:12.5px;padding:2px 0;color:#dc2626;'>⏰ 입찰 마감 · {E(x['org'])} · {E(x['title'][:60])}"
                        f"{' · ' + format(int(x['amount']), ',') + '원' if isinstance(x.get('amount'), (int, float)) and x['amount'] else ''}</div>" for x in b[:6])
        if len(b) > 6:
            cell += f"<div style='font-size:12px;color:var(--muted);'>외 입찰 마감 {len(b) - 6}건</div>"
        cell += "".join(f"<div style='font-size:12.5px;padding:2px 0;color:#2563eb;'>🏢 {E(x.get('label', ''))} <span style='color:var(--muted);'>({E(x.get('cell', ''))})</span></div>" for x in m)
        hl = " style='background:color-mix(in srgb, var(--accent) 8%, transparent);'" if d == today else ""
        tag = "오늘" if d == today else "어제" if i < 0 else f"D-{i}"
        rows.append(f"<tr{hl}><td style='white-space:nowrap;vertical-align:top;'><b>{d.month}.{d.day} ({WK[d.weekday()]})</b>"
                    f"<div style='font-size:11.5px;color:var(--muted);'>{tag}</div></td><td>{cell}</td></tr>")
    gen = E(str((sched or {}).get("generated") or "-"))
    parts.append(sec("날짜별 통합 일정", f"📅 내 일정(Google Calendar, 저장 {gen}) · ⏰ 나라장터 입찰 마감 · 🏢 콘텐츠Company 주간보고 마일스톤. 일정에 마우스를 올리면 설명·참석자",
                     f"<div class='tbl-wrap'><table><tbody>{''.join(rows)}</tbody></table></div>" if rows
                     else "<p style='color:var(--muted);font-size:13px;'>14일 안 일정 없음</p>"))

    mw = my_weekly()
    if mw:
        latest = mw[0]
        arch = "".join(f"<details style='margin:6px 0;'><summary style='cursor:pointer;'><b>{E(k)}</b></summary>"
                       f"<pre style='white-space:pre-wrap;font-size:12.5px;line-height:1.6;'>{E(t)}</pre></details>" for k, t in mw[1:12])
        parts.append(sec(f"내 주간업무보고 — {E(latest[0])}", "금요일 '주간업무보고 초안' 예약 작업이 비공개 저장소에 저장한 초안(발송본이 아니라 초안 그대로)",
                         f"<pre style='white-space:pre-wrap;font-size:12.5px;line-height:1.6;background:var(--surface-2);padding:12px;border-radius:8px;border:1px solid var(--border);margin:0;'>{E(latest[1])}</pre>"
                         + (f"<h4>지난 주차</h4>{arch}" if arch else "")))
    return "".join(parts)


def pack_md(days=14):
    """경영 브리프 팩용 Markdown 조각."""
    today = _today()
    sched = load_schedule()
    evs = [e for e in events(sched) if today <= e["date"] <= today + timedelta(days=days)]
    bids, mss = bid_deadlines(today, days), weekly_milestones()
    out = []
    if sched:
        out += [f"## 내 일정 (앞으로 {days}일, 저장 {sched.get('generated', '-')})", "", "| 날짜 | 시간 | 제목 | 장소 | 참석자 |", "|---|---|---|---|---|"]
        for e in evs:
            t = "종일" if e["all_day"] else f"{e['st']:%H:%M}" + (f"–{e['en']:%H:%M}" if e["en"] else "")
            att = ", ".join(map(str, e["attendees"][:8])) + (f" 외 {len(e['attendees']) - 8}" if len(e["attendees"]) > 8 else "")
            out.append(f"| {e['date']:%m/%d}({WK[e['date'].weekday()]}) | {t} | {e['title'].replace('|', '/')} | {e['location'].replace('|', '/')} | {att.replace('|', '/')} |")
        out.append("")
    cf = conflicts(evs, bids, mss)
    if cf:
        out += ["## 일정 겹침·주의", ""] + [f"- {d:%m/%d}({WK[d.weekday()]}) {t}" for d, t in cf] + [""]
    if bids:
        out += [f"## 입찰 마감 (앞으로 {days}일, {len(bids)}건)", ""]
        out += [f"- {b['date']:%m/%d} {b['org']} · {b['title'][:70]}" for b in sorted(bids, key=lambda x: x["date"])[:20]] + [""]
    mw = my_weekly()
    if mw:
        out += [f"## 내 주간업무보고 (최근 {mw[0][0]})", "", "```", mw[0][1].strip(), "```", ""]
    return out


if __name__ == "__main__":
    import sys
    sec = lambda t, d, body: f'<section class="panel"><h3>{t}</h3><p>{d}</p>{body}</section>'
    out = build(sec)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text("<meta charset='utf-8'><style>:root{--border:#ddd;--muted:#777;--accent:#4f8cff;--surface-2:#f6f7f9}"
                                     "table{border-collapse:collapse;width:100%}td,th{padding:6px;border-bottom:1px solid #ddd;text-align:left}</style>" + out, encoding="utf-8")
    print(f"내 일정 HTML {len(out):,}자")
