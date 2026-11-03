#!/usr/bin/env python3
"""
관리 탭 '주간보고' 화면(대표 전용) - 콘텐츠Company 주간 업무보고를 주차별로 쌓아 추이로 보여 준다.

- 데이터: 비공개 저장소(PRIVATE_DATA_REPO, 기본 choiys2/vs-insight-private)의 weekly_data/*.json.
  배포 때 deploy.yml 이 PRIVATE_DATA_TOKEN 으로 _private/ 에 내려받는다(이 공개 저장소에는 원본을 두지 않음).
  로컬 시험은 weekly_data.local/ 에 JSON 을 두면 된다(_private/·weekly_data.local/ 모두 gitignore).
- 결과 HTML 은 admin_structure.build_html 에 붙어 ADMIN_PASSWORD 로 암호화된다.
  history/·live/·브리핑·직원 화면(대시보드 비밀번호)에는 쓰지 않는다.
- 매주 할 일: 비공개 저장소 weekly_data/ 에 'YYYY-MM-WN.json' 한 개를 올리면 끝(index.json 불필요, 파일명으로 정렬).
"""
import html
import json
import os
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
E = html.escape
WEEK_RE = re.compile(r"^(\d{4})-(\d{2})-W(\d)\.json$")

# 주차마다 이름이 조금씩 다른 프로젝트를 한 줄로 묶는다(추이 계산용)
ALIAS = [
    (r"연수원몰", "연수원몰"),
    (r"AI\s*챗봇", "비바샘 AI 챗봇"),
    (r"AI\s*생기부|AI\s*성장\s*리포트", "AI 생기부"),
    (r"태블로", "태블로 대시보드"),
    (r"샘포트", "샘포트"),
    (r"그라운드\s*넥스트", "그라운드넥스트"),
    (r"초등\s*비바샘\s*UX|UX\s*개선", "초등 비바샘 UX 개선"),
    (r"해커톤", "교원단체 해커톤"),
    (r"연구대회", "현장 수업 연구대회"),
    (r"271", "271 교과서 제작"),
    (r"AI\s*디지털\s*교육자료|AIDT", "AI 디지털교육자료"),
    (r"경영\s*계획", "2027 경영계획"),
]
LV = {"critical": ("#dc2626", "긴급"), "high": ("#f59e0b", "높음"), "medium": ("#3b82f6", "보통"),
      "low": ("#94a3b8", "낮음"), "done": ("#10b981", "완료")}
ST = {"on_track": ("#10b981", "정상"), "at_risk": ("#f59e0b", "주의"), "delayed": ("#dc2626", "지연"),
      "completed": ("#64748b", "완료")}


def canon(name):
    for pat, out in ALIAS:
        if re.search(pat, name or ""):
            return out
    return (name or "").strip()


def data_dirs():
    env = os.environ.get("WEEKLY_DATA_DIR", "").strip()
    out = [Path(env)] if env else []
    return out + [HERE / "_private" / "weekly_data", HERE / "weekly_data.local"]


def load_weeks():
    """[(week_id, dict)] 오래된 주차 → 최근 주차. 같은 주차가 여러 폴더에 있으면 앞 폴더 우선."""
    seen = {}
    for d in data_dirs():
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.json")):
            if not WEEK_RE.match(f.name) or f.stem in seen:
                continue
            try:
                w = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                print(f"[경고] 주간보고 {f.name} 읽기 실패: {str(e)[:80]}")
                continue
            if isinstance(w, dict):
                seen[f.stem] = w
    return sorted(seen.items(), key=lambda kv: tuple(int(x) for x in WEEK_RE.match(kv[0] + ".json").groups()))


def _label(wid, w):
    m = WEEK_RE.match(wid + ".json")
    return (w.get("meta") or {}).get("week_label") or f"{int(m.group(2))}월 {m.group(3)}주차"


def _short(wid):
    m = WEEK_RE.match(wid + ".json")
    return f"{int(m.group(2))}-{m.group(3)}주"


def _pill(color, text):
    return (f'<span style="display:inline-block;padding:1px 8px;border-radius:999px;font-size:11.5px;font-weight:700;'
            f'background:color-mix(in srgb, {color} 18%, transparent);color:{color};">{E(text)}</span>')


def _ul(items, empty="—"):
    items = [i for i in (items or []) if i]
    if not items:
        return f'<p style="color:var(--muted);font-size:13px;">{empty}</p>'
    return '<ul style="margin:0;padding-left:18px;line-height:1.7;font-size:13px;">' + "".join(f"<li>{E(str(i))}</li>" for i in items) + "</ul>"


def _spark(vals, w=90, h=22):
    pts = [(i, v) for i, v in enumerate(vals) if v is not None]
    if len(pts) < 2:
        return ""
    n = max(len(vals) - 1, 1)
    xy = " ".join(f"{i / n * (w - 4) + 2:.1f},{h - 2 - v / 100 * (h - 4):.1f}" for i, v in pts)
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" aria-hidden="true">'
            f'<polyline points="{xy}" fill="none" stroke="var(--accent)" stroke-width="1.8"/></svg>')


def _today():
    return (datetime.now(timezone.utc) + timedelta(hours=9)).date()


def project_trend(weeks):
    """{프로젝트: {week_id: (progress, status, next_milestone, next_date)}} 와 최신 주차 순서."""
    tr, order = {}, []
    for wid, w in weeks:
        for p in w.get("projects") or []:
            k = canon(p.get("name"))
            if not k:
                continue
            if k not in tr:
                tr[k] = {}
            try:
                pg = int(round(float(str(p.get("progress")).rstrip("%"))))
            except (TypeError, ValueError):
                pg = None
            tr[k][wid] = (pg, p.get("status"), p.get("next_milestone") or "", p.get("next_date") or "")
    last = weeks[-1][0]
    order = sorted(tr, key=lambda k: (last not in tr[k], -(tr[k].get(last, (0,))[0] or 0)))
    return tr, order


def flags(tr, weeks, today=None):
    """정체(최근 2주 +3%p 미만)·일정 위험(남은 일수 대비 남은 진척이 큼) 판정."""
    today = today or _today()
    ids = [wid for wid, _ in weeks]
    out = {}
    for k, row in tr.items():
        f = []
        cur = row.get(ids[-1])
        if not cur or cur[0] is None:
            out[k] = f
            continue
        prog, status, _, nd = cur
        pv = row.get(ids[-2]) if len(ids) >= 2 else None
        if pv and pv[0] is not None and prog < pv[0]:
            f.append(("#8b5cf6", "공정률 하락"))  # 범위 재설정·산정 기준 변경 가능성 - 담당 확인
        elif prog < 100 and len(ids) >= 3 and all(row.get(i) and row[i][0] is not None for i in ids[-3:]):
            if prog - row[ids[-3]][0] < 3:
                f.append(("#f59e0b", "정체"))
        try:
            days = (date.fromisoformat(nd) - today).days
        except ValueError:
            days = None
        if days is not None and prog < 100:
            if days < 0:
                f.append(("#dc2626", "기한 경과"))
            elif len(ids) >= 2 and row.get(ids[-2]) and row[ids[-2]][0] is not None:
                pace = max(prog - row[ids[-2]][0], 0)  # 주당 진척
                need_weeks = (100 - prog) / pace if pace else 99
                if need_weeks > days / 7 + 0.5 and days <= 21:
                    f.append(("#dc2626", "일정 위험"))
        if status in ("at_risk", "delayed"):
            f.append(ST[status])
        out[k] = f
    return out


def upcoming(weeks, today=None, days=35):
    """최신 주차 보고의 마일스톤만(이전 주차 일정은 바뀌었을 수 있어 섞지 않음), 오늘부터 N일 이내.
    라벨 속 '(D-11)' 같은 표기는 보고 시점 기준이라 지우고 화면에서 오늘 기준으로 다시 센다."""
    today = today or _today()
    seen, rows = set(), []
    for m in weeks[-1][1].get("milestones") or []:
        try:
            d = date.fromisoformat(m.get("date", ""))
        except ValueError:
            continue
        label = re.sub(r"\s*\(?D-\d+\)?", "", m.get("label") or "").strip()
        key = (d, label[:20])
        if key in seen or not (today - timedelta(days=1) <= d <= today + timedelta(days=days)):
            continue
        seen.add(key)
        rows.append((d, dict(m, label=label)))
    return sorted(rows, key=lambda r: r[0])


def keyword_signal(weeks, top=18):
    c = Counter()
    for _, w in weeks:
        for k in set(w.get("keywords") or []):
            c[k] += 1
    return c.most_common(top)


def brief_text(weeks, tr, fl):
    """보고·발표용 복사 문안(사실만, 숫자 그대로)."""
    wid, w = weeks[-1]
    lines = [f"[콘텐츠Company 주간 동향 — {_label(wid, w)}]", "", f"■ 요약: {w.get('summary', '')}", ""]
    lines.append("■ 핵심 프로젝트 진척")
    prev = weeks[-2][0] if len(weeks) > 1 else None
    for k, row in tr.items():
        cur = row.get(wid)
        if not cur or cur[0] is None:
            continue
        d = ""
        if prev and row.get(prev) and row[prev][0] is not None:
            d = f" ({cur[0] - row[prev][0]:+d}%p)"
        fx = " · ".join(t for _, t in fl.get(k, []))
        lines.append(f"- {k}: {cur[0]}%{d}{' · ' + cur[2] if cur[2] else ''}{' [' + fx + ']' if fx else ''}")
    if w.get("risks"):
        lines += ["", "■ 리스크"] + [f"- [{LV.get(r.get('level'), ('', r.get('level')))[1]}] {r.get('content', '')}" for r in w["risks"]]
    if w.get("vivasam_connects"):
        lines += ["", "■ 연수원 연계 기회"] + [f"- {x}" for x in w["vivasam_connects"]]
    return "\n".join(lines)


def build(sec):
    weeks = load_weeks()
    if not weeks:
        return sec("주간보고 (대표 전용)", "콘텐츠Company 주간 업무보고 누적",
                   '<p class="tt-note">아직 주간 데이터가 없습니다. 비공개 저장소 <code>weekly_data/</code> 에 '
                   '<code>YYYY-MM-WN.json</code> 을 올리고 GitHub Secret <code>PRIVATE_DATA_TOKEN</code> 을 등록하면 다음 배포부터 채워집니다.</p>')
    today = _today()
    wid, w = weeks[-1]
    ids = [i for i, _ in weeks]
    tr, order = project_trend(weeks)
    fl = flags(tr, weeks, today)
    prev = ids[-2] if len(ids) > 1 else None

    # 1) 이번 주 한눈에
    focus = " ".join(_pill("var(--accent)", f) for f in w.get("focus_areas") or [])
    risks = "".join(f'<div style="padding:6px 0;border-bottom:1px dashed var(--border);font-size:13px;">'
                    f'{_pill(*LV.get(r.get("level"), ("#94a3b8", r.get("level") or "-")))} {E(r.get("content", ""))}</div>'
                    for r in w.get("risks") or []) or '<p style="color:var(--muted);font-size:13px;">—</p>'
    grid = "display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px;"
    head = (f'<p style="font-size:14px;line-height:1.7;margin:0 0 10px;"><b>{E(w.get("summary", ""))}</b></p>'
            f'<div style="margin-bottom:14px;line-height:2;">{focus}</div>'
            f'<div style="{grid}">'
            f'<div><h4>이번 주 핵심 이슈</h4>{_ul(w.get("top_issues"))}</div>'
            f'<div><h4>리스크</h4>{risks}</div>'
            f'<div><h4>의사결정·착수</h4>{_ul(w.get("decisions"))}</div>'
            f'<div><h4>직전 주 완료</h4>{_ul(w.get("completed"))}</div></div>')
    meta = w.get("meta") or {}
    s1 = sec(f"주간보고 — {E(_label(wid, w))}",
             f"{E(meta.get('date_start', ''))} ~ {E(meta.get('date_end', ''))} · 출처 {E(meta.get('source', '-'))} · 누적 {len(weeks)}주 ({E(_short(ids[0]))} ~ {E(_short(wid))})",
             head)

    # 2) 연수원 연계 기회(사업총괄 관점에서 가장 쓸모 있는 칸이라 따로 크게)
    s2 = sec("비바샘원격교육연수원 연계 기회", "이번 주 콘텐츠Company 업무 중 연수원 매출·과정으로 이어질 수 있는 지점",
             _ul(w.get("vivasam_connects"), "이번 주 등록된 연계 기회 없음"))

    # 3) 프로젝트 진척 추이
    th = "".join(f"<th class='num'>{E(_short(i))}</th>" for i in ids)
    rows = []
    for k in order:
        row = tr[k]
        vals = [row.get(i, (None,))[0] for i in ids]
        cells = "".join(f"<td class='num'>{'' if v is None else v}</td>" for v in vals)
        cur = row.get(wid)
        delta = ""
        if cur and prev and row.get(prev) and cur[0] is not None and row[prev][0] is not None:
            dv = cur[0] - row[prev][0]
            delta = f"<span style='color:{'#10b981' if dv > 0 else 'var(--muted)'};font-weight:700;'>{dv:+d}</span>"
        nxt = f"{E(cur[2])}" if cur else "<span style='color:var(--muted);'>이번 주 보고 없음</span>"
        fx = " ".join(_pill(c, t) for c, t in fl.get(k, []))
        rows.append(f"<tr><td><b>{E(k)}</b></td>{cells}<td class='num'>{delta}</td><td>{_spark(vals)}</td><td style='font-size:12px;'>{nxt}</td><td>{fx}</td></tr>")
    s3 = sec("프로젝트 진척 추이 (%)",
             "주차별 공정률. Δ = 직전 주 대비. 정체 = 최근 2주 +3%p 미만, 공정률 하락 = 범위 재설정 등 확인 필요, 일정 위험 = 3주 안 마감인데 지금 속도로는 100% 도달이 늦음(추정).",
             f"<div class='tbl-wrap'><table><thead><tr><th>프로젝트</th>{th}<th class='num'>Δ</th><th>추이</th><th>다음 이정표</th><th>판정</th></tr></thead>"
             f"<tbody>{''.join(rows)}</tbody></table></div>")

    # 4) 다가오는 일정(월간 일정표 대체)
    wk = "월화수목금토일"
    hot = ' style="background:color-mix(in srgb, #dc2626 7%, transparent);"'
    up = "".join(
        f"<tr{hot if m.get('urgency') == 'critical' else ''}>"
        f"<td style='white-space:nowrap;'><b>{d.month}.{d.day} ({wk[d.weekday()]})</b>"
        f"<div style='font-size:11.5px;color:var(--muted);'>{'오늘' if d == today else f'D-{(d - today).days}' if d > today else '어제'}</div></td>"
        f"<td>{_pill(*LV.get(m.get('urgency'), ('#94a3b8', m.get('urgency') or '-')))}</td>"
        f"<td>{E(m.get('label', ''))}</td><td style='font-size:12px;color:var(--muted);'>{E(m.get('cell', ''))}</td></tr>"
        for d, m in upcoming(weeks, today))
    s4 = sec("다가오는 일정 (35일)", f"최신 주차({E(_label(wid, w))}) 보고의 마일스톤, 오늘({today.month}.{today.day}) 기준 D-day",
             f"<div class='tbl-wrap'><table><thead><tr><th>날짜</th><th>구분</th><th>내용</th><th>담당</th></tr></thead><tbody>{up}</tbody></table></div>"
             if up else '<p style="color:var(--muted);font-size:13px;">35일 안에 등록된 일정 없음</p>')

    # 5) 키워드 지속성(몇 주째 나오는가 = 조직이 실제로 붙잡고 있는 주제)
    kw = keyword_signal(weeks)
    kw_html = " ".join(
        f'<span style="display:inline-block;margin:3px;padding:3px 10px;border-radius:999px;border:1px solid var(--border);'
        f'background:color-mix(in srgb, var(--accent) {min(8 + n * 12, 60)}%, transparent);font-size:12.5px;font-weight:700;">{E(k)} <small>{n}주</small></span>'
        for k, n in kw)
    s5 = sec("키워드 지속성", f"최근 {len(weeks)}주 중 몇 주에 등장했는지. 오래 이어지는 주제일수록 진함", kw_html or "—")

    # 6) 셀별 활동(이번 주) · 지난 주차 보관함
    cells = w.get("cells") or {}
    cell_html = f'<div style="{grid}">' + "".join(
        f'<div><h4>{E(c)}</h4>{_ul((v or {}).get("key_activities"))}'
        + (f'<div style="margin-top:6px;">{_ul([("⚠ " + i) for i in (v or {}).get("issues") or []], "")}</div>' if (v or {}).get("issues") else "")
        + "</div>" for c, v in cells.items()) + "</div>"
    s6 = sec("셀별 주요 활동 (이번 주)", "주간보고 원문 기준", f"<details><summary style='cursor:pointer;font-weight:700;'>펼쳐 보기 ({len(cells)}개 셀)</summary><div style='margin-top:10px;'>{cell_html}</div></details>")
    arch = "".join(
        f"<details style='margin:6px 0;'><summary style='cursor:pointer;'><b>{E(_label(i, x))}</b> — {E((x.get('summary') or '')[:90])}</summary>"
        f"<div style='{grid};margin:10px 0 4px;'><div><h4>핵심 이슈</h4>{_ul(x.get('top_issues'))}</div>"
        f"<div><h4>리스크</h4>{_ul([r.get('content') for r in x.get('risks') or []])}</div>"
        f"<div><h4>연수원 연계</h4>{_ul(x.get('vivasam_connects'))}</div></div></details>"
        for i, x in reversed(weeks[:-1]))
    s7 = sec("지난 주차 보관함", "이전 주간보고 요약", arch or "—")

    # 7) 보고·발표용 복사 문안
    txt = E(brief_text(weeks, tr, fl))
    s8 = sec("보고·발표용 요약 문안", "숫자를 그대로 옮긴 텍스트입니다. 선택해 복사하면 메일·보고서·슬라이드 초안에 바로 쓸 수 있습니다.",
             f"<pre style='white-space:pre-wrap;font-size:12.5px;line-height:1.6;background:var(--surface-2);padding:12px;border-radius:8px;border:1px solid var(--border);margin:0;'>{txt}</pre>")
    return s1 + s2 + s3 + s4 + s5 + s6 + s7 + s8


if __name__ == "__main__":
    import sys
    sec = lambda t, d, body: f'<section class="panel"><h3>{t}</h3><p>{d}</p>{body}</section>'
    out = build(sec)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text("<meta charset='utf-8'><style>:root{--border:#ddd;--muted:#777;--accent:#4f8cff;--surface-2:#f6f7f9}"
                                     "table{border-collapse:collapse;width:100%}td,th{padding:6px;border-bottom:1px solid #ddd;text-align:left}.num{text-align:right}</style>" + out,
                                     encoding="utf-8")
    print(f"주간보고 {len(load_weeks())}주, HTML {len(out):,}자")
