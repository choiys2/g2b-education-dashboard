#!/usr/bin/env python3
"""
관리 탭 '결정 보드'(대표 전용) — 데이터로 내린 결정을 기록하고 기한·실행을 추적한다(결정 루프).

- 원본: 비공개 저장소 decisions/log.md 의 표 한 개(GitHub 웹에서 연필 아이콘으로 한 줄 추가·수정).
  | 날짜 | 결정 | 근거 | 담당 | 기한 | KPI | 상태 | 결과 |
  상태: 진행 · 완료 · 보류 · 취소 (영문 open/done/hold/drop 도 인식). 날짜·기한은 YYYY-MM-DD 또는 M/D.
- 로컬 시험: decisions.local/log.md (gitignore)
- 결과 HTML 은 관리 탭 암호문(ADMIN_PASSWORD) 안에만. 경영 브리프 팩에는 '기한 지남·이번 주 마감'만 요약.
"""
import html
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
E = html.escape
COLS = ["날짜", "결정", "근거", "담당", "기한", "KPI", "상태", "결과"]
ST = {"진행": "open", "열림": "open", "open": "open", "완료": "done", "done": "done", "보류": "hold", "hold": "hold",
      "취소": "drop", "drop": "drop", "철회": "drop"}
STL = {"open": ("#2563eb", "진행"), "done": ("#10b981", "완료"), "hold": ("#94a3b8", "보류"), "drop": ("#94a3b8", "취소")}


def _today():
    return (datetime.now(timezone.utc) + timedelta(hours=9)).date()


def _date(s, ref):
    s = (s or "").strip()
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return date(*map(int, m.groups()))
    m = re.match(r"(\d{1,2})[./](\d{1,2})", s)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        y = ref.year + (1 if mo < ref.month - 6 else -1 if mo > ref.month + 6 else 0)
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    return None


def _files():
    env = os.environ.get("PRIVATE_DATA_DIR", "").strip()
    for d in ([Path(env) / "decisions"] if env else []) + [HERE / "_private" / "decisions", HERE / "decisions.local"]:
        if (d / "log.md").is_file():
            return d / "log.md"
    return None


def load(today=None):
    today = today or _today()
    f = _files()
    if not f:
        return None
    rows, head = [], None
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue
        if head is None:
            head = cells
            continue
        r = dict(zip(head, cells + [""] * (len(head) - len(cells))))
        if not (r.get("결정") or "").strip() or r.get("결정", "").startswith("("):
            continue  # 빈 줄·예시 줄
        d = _date(r.get("날짜"), today) or today
        due = _date(r.get("기한"), d)
        st = ST.get((r.get("상태") or "진행").strip().lower(), ST.get((r.get("상태") or "").strip(), "open"))
        rows.append({**r, "d": d, "due": due, "st": st})
    return rows


def summary(rows, today=None):
    today = today or _today()
    opn = [r for r in rows if r["st"] == "open"]
    over = [r for r in opn if r["due"] and r["due"] < today]
    week = [r for r in opn if r["due"] and today <= r["due"] <= today + timedelta(days=7)]
    since = today - timedelta(days=30)
    done30 = [r for r in rows if r["st"] == "done" and r["d"] >= since - timedelta(days=60)]
    due30 = [r for r in rows if r["due"] and since <= r["due"] <= today and r["st"] in ("open", "done")]
    rate = (sum(1 for r in due30 if r["st"] == "done") / len(due30) * 100) if due30 else None
    made7 = [r for r in rows if r["d"] >= today - timedelta(days=7)]
    return {"open": opn, "over": over, "week": week, "rate": rate, "made7": made7, "done": done30}


def _pill(c, t):
    return (f'<span style="display:inline-block;padding:1px 8px;border-radius:999px;font-size:11.5px;font-weight:700;'
            f'background:color-mix(in srgb, {c} 18%, transparent);color:{c};">{E(t)}</span>')


def build(sec):
    today = _today()
    rows = load(today)
    if rows is None:
        return sec("결정 보드 (대표 전용)", "데이터로 내린 결정 → 담당·기한 → 실행 추적",
                   '<p class="tt-note">아직 결정 기록이 없습니다. 비공개 저장소 <code>decisions/log.md</code> 표에 한 줄을 추가하면 다음 배포부터 채워집니다.</p>')
    S = summary(rows, today)
    tile = lambda k, v, s="", c="var(--ink)": (f"<div style='padding:10px 12px;border:1px solid var(--border);border-radius:10px;background:var(--surface-2);'>"
                                               f"<div style='font-size:12px;color:var(--muted);'>{k}</div><div style='font-size:22px;font-weight:800;color:{c};'>{v}</div>"
                                               f"<div style='font-size:11.5px;color:var(--muted);'>{s}</div></div>")
    tiles = ("<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:12px;'>"
             + tile("진행 중", len(S["open"])) + tile("기한 지남", len(S["over"]), "", "#dc2626" if S["over"] else "var(--ink)")
             + tile("7일 안 마감", len(S["week"]), "", "#f59e0b" if S["week"] else "var(--ink)")
             + tile("최근 7일 새 결정", len(S["made7"]), "목표 주 3건 이상", "#10b981" if len(S["made7"]) >= 3 else "#f59e0b")
             + tile("30일 실행률", f"{S['rate']:.0f}%" if S["rate"] is not None else "-", "기한 도래 결정 중 완료 · 목표 70%",
                    "#10b981" if (S["rate"] or 0) >= 70 else "#f59e0b") + "</div>")

    def line(r):
        late = r["st"] == "open" and r["due"] and r["due"] < today
        dd = (f"D+{(today - r['due']).days}" if late else f"D-{(r['due'] - today).days}") if r["due"] and r["st"] == "open" else ""
        bg = " style='background:color-mix(in srgb, #dc2626 7%, transparent);'" if late else ""
        return (f"<tr{bg}><td style='white-space:nowrap;'>{r['d']:%m/%d}</td><td><b>{E(r.get('결정', ''))}</b>"
                f"<div style='font-size:12px;color:var(--muted);'>{E(r.get('근거', ''))}</div></td><td>{E(r.get('담당', ''))}</td>"
                f"<td style='white-space:nowrap;'>{r['due']:%m/%d}" + (f" <b style='color:{'#dc2626' if late else 'var(--muted)'};'>{dd}</b>" if dd else "") + "</td>"
                f"<td style='font-size:12px;'>{E(r.get('KPI', ''))}</td><td>{_pill(*STL[r['st']])}</td><td style='font-size:12px;'>{E(r.get('결과', ''))}</td></tr>"
                if r["due"] else
                f"<tr><td>{r['d']:%m/%d}</td><td><b>{E(r.get('결정', ''))}</b><div style='font-size:12px;color:var(--muted);'>{E(r.get('근거', ''))}</div></td>"
                f"<td>{E(r.get('담당', ''))}</td><td style='color:#f59e0b;'>기한 없음</td><td style='font-size:12px;'>{E(r.get('KPI', ''))}</td>"
                f"<td>{_pill(*STL[r['st']])}</td><td style='font-size:12px;'>{E(r.get('결과', ''))}</td></tr>")
    th = "<thead><tr><th>날짜</th><th>결정 · 근거</th><th>담당</th><th>기한</th><th>KPI</th><th>상태</th><th>결과</th></tr></thead>"
    opn = sorted(S["open"], key=lambda r: (r["due"] or date.max))
    rest = sorted([r for r in rows if r["st"] != "open"], key=lambda r: r["d"], reverse=True)[:30]
    body = (tiles + f"<div class='tbl-wrap'><table>{th}<tbody>{''.join(line(r) for r in opn) or '<tr><td colspan=7>진행 중인 결정 없음</td></tr>'}</tbody></table></div>"
            + (f"<details style='margin-top:10px;'><summary style='cursor:pointer;font-weight:700;'>완료·보류·취소 {len(rest)}건</summary>"
               f"<div class='tbl-wrap'><table>{th}<tbody>{''.join(line(r) for r in rest)}</tbody></table></div></details>" if rest else "")
            + "<p class='tt-note'>원본: 비공개 저장소 <code>decisions/log.md</code>. 경영 브리프 채팅에서 \"결정 기록 줄 만들어줘\" → 나온 한 줄을 GitHub 연필(✏️)로 붙여 넣고 저장하면 다음 배포에 반영됩니다.</p>")
    return sec("결정 보드 (대표 전용)", f"결정 {len(rows)}건 · 기한 지난 결정은 경영 브리프 팩 맨 위에도 올라갑니다", body)


def pack_md():
    today = _today()
    rows = load(today)
    if not rows:
        return []
    S = summary(rows, today)
    rate = "-" if S["rate"] is None else f"{S['rate']:.0f}%"
    out = ["## 결정 보드", "",
           f"- 진행 {len(S['open'])} · **기한 지남 {len(S['over'])}** · 7일 안 마감 {len(S['week'])} · 최근 7일 새 결정 {len(S['made7'])} · 30일 실행률 {rate}"]
    for tag, lst in (("기한 지남", S["over"]), ("7일 안 마감", S["week"])):
        for r in sorted(lst, key=lambda r: r["due"]):
            out.append(f"- [{tag}] {r['due']:%m/%d} · {r.get('결정', '')} · 담당 {r.get('담당', '-')} · KPI {r.get('KPI', '-')}")
    return out + [""]
