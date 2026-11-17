#!/usr/bin/env python3
"""
🔒 관리 탭 'AI 업무 도구' 칸 — 업무플로우 빈 단계·단계 사이·관리 기능 13종 (2026-11-18 사용자 지시: "모두 처리해줘")

  A. 빈 단계: ① 제작 방식 추천기 ② 등록 서류 초안기 ③ 수강 후기 분석기 ④ 문의 답변 초안·FAQ ⑤ 이수 후 다음 연수 추천
  B. 단계 사이: ⑥ 제안서 자동 조립 ⑦ 결과보고 초안·정산 체크리스트 ⑧ 후속 제안 자동 생성 ⑨ 라이브 반응 → 기획안 ⑩ 셀 주간보고 취합
  C. 관리: ⑪ 단계별 병목 지도 ⑫ AI 자동화 진척판 ⑬ 업무 인수인계 카드

  초안 도구(①~⑨)는 브라우저 안에서 규칙·서식으로 초안을 만든다(외부 AI 호출·비용 없음, 입력 내용은 저장하지 않음).
  ⑩~⑬과 할 일은 배포 때 서버에서 계산한다. 기준값·종료 건은 비공개 저장소 strategy_room/ai_ops.json.
"""
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import training_plan as tp

HERE = Path(__file__).parent
E = tp.E
NOTE = tp.NOTE

# 업무플로우 단계 → AI 도구(번호, 이름). workflows.render() 가 단계 칩으로 붙인다.
TOOLS = {1: "제작 방식 추천기", 2: "등록 서류 초안기", 3: "수강 후기 분석기", 4: "문의 답변 초안·FAQ", 5: "이수 후 다음 연수 추천",
         6: "제안서 자동 조립", 7: "결과보고 초안·정산 체크리스트", 8: "후속 제안 자동 생성", 9: "라이브 반응 → 기획안", 10: "셀 주간보고 취합",
         11: "단계별 병목 지도", 12: "AI 자동화 진척판", 13: "업무 인수인계 카드"}
PHASE_TOOLS = {
    ("dev", "콘텐츠 기획"): [9, 1], ("dev", "제작 방식 판단"): [1], ("dev", "계약 및 등록"): [2], ("dev", "운영 및 성과 분석"): [3],
    ("b2g", "사업 발굴 협의"): [8], ("b2g", "연수 제안"): [6], ("b2g", "결과보고"): [7], ("b2g", "정산 및 매출관리"): [7],
    ("b2c", "기획 및 설계"): [9], ("b2c", "연수 운영·평가"): [3], ("b2c", "문의 대응"): [4], ("b2c", "운영 지원"): [4], ("b2c", "이수 및 환류"): [5],
    ("off", "사후 관리 및 정산"): [7, 8],
}


def tools_for(wid, phase):
    return PHASE_TOOLS.get((wid, phase), [])


def _priv(name):
    try:
        d = __import__("strategy_room")._private()
    except Exception:  # noqa: BLE001
        d = None
    for base in ([d] if d else []) + [HERE / "_private", HERE / "private.local"]:
        f = base / name
        if f.is_file():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                return None
    return None


def _today():
    return datetime.now(timezone(timedelta(hours=9))).date()


def _anchor(n):
    return f"ait-{n}"


def _sec(sec, n, desc, body):
    return f"<div id='{_anchor(n)}'></div>" + sec(f"{chr(0x2460 + n - 1)} {TOOLS[n]}", desc, body)


# ---------------------------------------------------------------- 브라우저 도구에 넘길 자료
def _payload(A):
    try:
        import training_topics as tt
        topics = [[t[0], t[1], t[2]] for t in tt.TOPICS]
    except Exception:  # noqa: BLE001
        topics = []
    cat = []
    try:
        c = json.loads((HERE / "history/competitor_course_catalog.json").read_text(encoding="utf-8"))
        for r in ((c.get("companies") or {}).get("비바샘연수원") or {}).get("courses") or []:
            t = (r.get("title") or "").strip()
            u = r.get("url") or ""
            if t and t != "상세보기" and u.startswith("https://"):
                cat.append({"t": t[:90], "c": r.get("credit") or "", "u": u})
    except Exception:  # noqa: BLE001
        pass
    sig = {}
    since = (_today() - timedelta(days=60)).isoformat()
    f = HERE / "history/edu_office_signals.jsonl"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if r.get("d", "") >= since and r.get("s"):
                sig.setdefault(r["s"], []).append([r.get("d", ""), (r.get("t") or "")[:80]])
    sig = {k: sorted(v, reverse=True)[:4] for k, v in sig.items()}
    TP = tp.load() or {}
    OB = __import__("ops_boards").load() or {}
    today = _today().isoformat()
    lives = [{"d": x.get("date"), "t": x.get("title")} for x in OB.get("lives") or [] if (x.get("date") or "") >= today]
    return {"topics": topics, "cat": cat[:400], "sig": sig, "quote": (TP.get("quote") or {}).get("items") or [],
            "refs": (A or {}).get("refs") or {}, "settle": (A or {}).get("settle_days") or {}, "lives": lives}


# ---------------------------------------------------------------- ⑩ 셀 주간보고 취합 (비공개 weekly_data 최신 1주)
def _weekly():
    try:
        d = __import__("strategy_room")._private()
    except Exception:  # noqa: BLE001
        d = None
    files = []
    for base in ([d] if d else []) + [HERE / "_private", HERE / "private.local"]:
        p = base / "weekly_data"
        if p.is_dir():
            files = sorted(p.glob("*.json"))
            break
    if not files:
        return f"<p style='{NOTE}'>데이터 준비 중</p>"
    W = json.loads(files[-1].read_text(encoding="utf-8"))
    wk = files[-1].stem
    rows, issues = [], []
    for cell, v in (W.get("cells") or {}).items():
        acts = v.get("key_activities") or []
        kpi = [a for a in acts if re.search(r"\d", a)][:2]
        rows.append([f"<b>{cell}</b>", " · ".join(a[:60] for a in acts[:3]), " / ".join(a[:50] for a in kpi) or "-", " / ".join(v.get("issues") or []) or "-"])
        issues += [f"{cell}: {i}" for i in v.get("issues") or []]
    top = W.get("top_issues") or []
    dec = W.get("decisions") or []
    risk = W.get("risks") or []
    def _txt(x):
        if not isinstance(x, dict):
            return str(x)
        body = x.get("content") or x.get("title") or x.get("t") or x.get("text") or ""
        lv = {"critical": "긴급", "high": "높음", "medium": "보통", "low": "낮음"}.get(x.get("level", ""), "")
        return f"[{lv}] {body}" if lv and body else (body or "")
    lst = lambda xs: "".join(f"<li>{E(_txt(x)[:140])}</li>" for x in xs[:6] if _txt(x))
    return (tp._table({"h": f"{wk} 셀별 요약", "head": ["셀", "핵심 활동", "숫자가 있는 활동(KPI 후보)", "이슈"], "rows": rows})
            + "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(min(260px,100%),1fr));gap:12px;margin-top:8px;font-size:13px;'>"
            + f"<div><b>이번 주 핵심</b><ul style='margin:4px 0 0 18px;'>{lst(top)}</ul></div>"
            + f"<div><b>결정 필요</b><ul style='margin:4px 0 0 18px;'>{lst(dec) or '<li>없음</li>'}</ul></div>"
            + f"<div><b>리스크·이슈</b><ul style='margin:4px 0 0 18px;'>{lst(risk + issues) or '<li>없음</li>'}</ul></div></div>"
            + f"<p style='{NOTE}'>주간 자료가 들어올 때마다 다시 취합합니다. '결정 필요' 항목은 결정 보드에서 처리하세요.</p>")


# ---------------------------------------------------------------- ⑪ 병목 지도 · ⑫ 진척판 · ⑬ 인수인계 카드
def _wf():
    return __import__("workflows")


def _bottleneck(today=None):
    today = today or _today()
    W = _wf()
    OB = __import__("ops_boards")
    D = OB.load() or {}
    late = {}
    P = D.get("pipeline") or {}
    sla = P.get("sla") or {}
    n_ax = sum(1 for c in P.get("courses") or [] if c.get("stage") in sla and (today - (OB._d(c.get("since")) or today)).days > sla[c["stage"]])
    late[("dev", "콘텐츠 개발 및 심사")] = (n_ax, "AX 파이프라인 기준 초과")
    lt = [t for t in OB.live_todos(D, today) if t[3] == "지남"]
    late[("b2c", "준비 및 홍보")] = (len(lt), "라이브 후속 할 일 지남")
    A = _priv("strategy_room/ai_ops.json") or {}
    ct = [t for t in closure_todos(A, today) if t[3] == "지남"]
    late[("b2g", "정산 및 매출관리")] = (sum(1 for t in ct if t[4] == "정산"), "정산 단계 기한 지남")
    late[("b2g", "결과보고")] = (sum(1 for t in ct if t[4] == "결과보고"), "결과보고 기한 지남")
    rows = []
    for w in W.WORKFLOWS:
        cells = ""
        for p in w["phases"]:
            n_link, n_tool = len(p["links"]), len(tools_for(w["id"], p["name"]))
            lt_n, why = late.get((w["id"], p["name"]), (None, ""))
            if lt_n:
                col, st = "#ef4444", f"지연 {lt_n}건 · {why}"
            elif n_link + n_tool == 0:
                col, st = "#94a3b8", "연결 없음"
            elif lt_n == 0:
                col, st = "#10b981", "지연 없음(측정 중)"
            else:
                col, st = "#3b82f6", f"화면 {n_link} · AI 도구 {n_tool} · 지연 측정 전"
            cells += (f"<div title='{E(st)}' style='flex:1;min-width:110px;padding:6px 8px;border-radius:6px;border-left:4px solid {col};background:var(--surface-2);font-size:12px;'>"
                      f"<b>{E(p['name'])}</b><div style='{NOTE}font-size:11.5px;'>{E(st)}</div></div>")
        rows.append(f"<div style='margin:8px 0;'><b style='font-size:13px;'>{E(w['name'])}</b><div style='display:flex;flex-wrap:wrap;gap:6px;margin-top:4px;'>{cells}</div></div>")
    return ("".join(rows) + f"<p style='{NOTE}'>빨강 = 기한을 넘긴 일이 있음 · 초록 = 측정 중이며 지연 없음 · 파랑 = 연결은 있으나 지연을 아직 재지 않음 · 회색 = 연결 없음. "
                            "지연은 AX 파이프라인·라이브 후속·교육청 종료 건(결과보고·정산)에서 셉니다.</p>")


def _progress():
    W = _wf()
    rows, tot = [], [0, 0, 0, 0]
    for w in W.WORKFLOWS:
        n = len(w["phases"])
        link = sum(1 for p in w["phases"] if p["links"])
        tool = sum(1 for p in w["phases"] if tools_for(w["id"], p["name"]))
        none = sum(1 for p in w["phases"] if not p["links"] and not tools_for(w["id"], p["name"]))
        tot = [tot[0] + n, tot[1] + link, tot[2] + tool, tot[3] + none]
        rows.append([f"<b>{w['name']}</b>", n, link, tool, none, f"{(n - none) / n * 100:.0f}%"])
    ai = W.ai_summary()
    ai_rows = [[r["name"], r["n"], r["auto"], r["assist"], f"{(r['auto'] + r['assist']) / max(1, r['n']) * 100:.0f}%"] for r in ai]
    return (tp._tiles({"items": [["업무 단계", f"{tot[0]}개", "4개 업무 흐름"], ["화면 연결", f"{tot[1]}단계", "판단에 쓰는 화면"], ["AI 도구 연결", f"{tot[2]}단계", "이번에 추가된 초안·추천 도구"],
                                 ["연결 없음", f"{tot[3]}단계", "다음 고도화 대상"]]})
            + tp._table({"h": "업무 흐름별 연결 현황", "head": ["업무 흐름", "단계", "화면 연결", "AI 도구", "연결 없음", "연결률"], "rows": rows})
            + tp._table({"h": "세부 업무별 AI 적용 가능성", "head": ["업무 흐름", "세부 업무", "자동화", "AI 보조", "AI 적용률"], "rows": ai_rows})
            + f"<p style='{NOTE}'>아낀 시간은 도구 사용 기록이 쌓이면 계산합니다(지금은 연결 범위만).</p>")


def _handover():
    W = _wf()
    out = []
    for w in W.WORKFLOWS:
        ph = w["phases"]
        cards = ""
        for i, p in enumerate(ph):
            toks = [t.strip() for ln in p["lanes"] for t in ln.split(" > ")]
            roles = sorted({t.split(":", 1)[0] for t in toks if ":" in t and not t.startswith("?") and len(t.split(":", 1)[0]) <= 4})
            last = [ln.split(" > ")[-1] for ln in p["lanes"]]
            outp = " / ".join(re.sub(r"^[^:?]{1,4}:", "", x).split("|")[0].lstrip("?") for x in last)[:120]
            inp = ", ".join(W.F[k][2] for k, _ in p["links"]) or "-"
            tl = ", ".join(TOOLS[n] for n in tools_for(w["id"], p["name"])) or "-"
            nxt = ph[i + 1]["name"] if i + 1 < len(ph) else "완료"
            cards += (f"<div style='padding:10px 12px;border:1px solid var(--border);border-radius:8px;font-size:12.5px;line-height:1.6;'>"
                      f"<b>{i + 1}. {E(p['name'])}</b><div><span style='{NOTE}'>업무 유형</span> {E(' · '.join(roles) or '-')}</div>"
                      f"<div><span style='{NOTE}'>참고 화면</span> {E(inp)}</div><div><span style='{NOTE}'>AI 도구</span> {E(tl)}</div>"
                      f"<div><span style='{NOTE}'>산출물</span> {E(outp)}</div><div><span style='{NOTE}'>다음 단계</span> {E(nxt)}</div></div>")
        out.append(f"<details style='margin:6px 0;'><summary style='cursor:pointer;font-weight:700;font-size:13.5px;'>{E(w['name'])} — 주관 {E(w['owner'])} · {len(ph)}단계</summary>"
                   f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(min(240px,100%),1fr));gap:8px;margin-top:8px;'>{cards}</div></details>")
    return "".join(out) + f"<p style='{NOTE}'>업무플로우에서 자동으로 만듭니다. 담당은 역할명만 씁니다(실명 미저장). 휴직·전환배치 때 인수인계서 초안으로 쓰세요.</p>"


# ---------------------------------------------------------------- ⑦⑧ 종료 건 → 결과보고·정산·후속 영업 할 일
def closure_todos(A, today=None):
    today = today or _today()
    days = A.get("settle_days") or {}
    out = []
    for c in A.get("closures") or []:
        try:
            d0 = date.fromisoformat(c.get("end", "")[:10])
        except Exception:  # noqa: BLE001
            continue
        if (today - d0).days > 60:
            continue
        name = f"{c.get('org', '')} · {c.get('title', '')}"
        steps = [(d0 + timedelta(days=7), "결과·만족도 분석(후속 영업 1단계)", "후속"), (d0 + timedelta(days=14), "영업 담당 공유", "후속"),
                 (d0 + timedelta(days=30), "후속 제안서 발송(⑧ 후속 제안 초안 사용)", "후속")]
        for k, n in days.items():
            if not (c.get("done") or {}).get(k):
                steps.append((d0 + timedelta(days=int(n)), k, "결과보고" if k == "결과보고" else "정산"))
        for due, what, kind in steps:
            gap = (due - today).days
            out.append((due, name, what, "지남" if gap < 0 else ("이번 주" if gap <= 7 else "예정"), kind))
    return sorted(out)


# ---------------------------------------------------------------- 칸 조립
def build(sec):
    A = _priv("strategy_room/ai_ops.json") or {}
    P = _payload(A)
    holder = f"<div id='aiOpsData' hidden data-p='{E(json.dumps(P, ensure_ascii=False))}'></div>"
    nav = ("<div style='display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px;'>"
           + "".join(f"<a href='#{_anchor(n)}' class='wf-lk' style='text-decoration:none;color:inherit;'>{chr(0x2460 + n - 1)} {E(t)}</a>" for n, t in TOOLS.items()) + "</div>")
    intro = sec("AI 업무 도구", "업무플로우의 빈 단계와 단계 사이를 잇는 도구 13종. ①~⑨는 입력하면 바로 초안·추천이 나오고(브라우저 안에서만 처리, 저장 안 함), ⑩~⑬은 배포 때마다 자동으로 다시 계산됩니다.", nav)
    slot = lambda n: f"<div class='aiops-tool' data-tool='{n}'><p style='{NOTE}'>도구를 불러오는 중입니다.</p></div>"
    A_ = (_sec(sec, 1, "연수 개발 › 제작 방식 판단 — 주제·일정·예산·강사 조건으로 자체 / 샘크 A~D형 / 하이브리드 / CP 중 추천", slot(1))
          + _sec(sec, 2, "연수 개발 › 계약 및 등록 — 상세페이지·분류 태그·강사 계약 점검표 초안", slot(2))
          + _sec(sec, 3, "운영 및 성과 분석 · 연수 운영·평가 — 후기를 붙여 넣으면 개선 과제로 묶음", slot(3))
          + _sec(sec, 4, "문의 대응 · 운영 지원 — 문의 유형 분류, 답변 초안, 자주 묻는 질문 후보", slot(4))
          + _sec(sec, 5, "이수 및 환류 — 이수한 과정에서 다음 연수·라이브 추천", slot(5)))
    B_ = (_sec(sec, 6, "공고 → 제안 → 계약 — 교육청 정책 신호·견적·운영 실적을 묶어 제안서 1차본", slot(6))
          + _sec(sec, 7, "연수 운영 → 결과보고 → 정산 — 결과보고 본문 초안과 정산 단계 기한", slot(7))
          + _sec(sec, 8, "결과보고 → 후속 영업 — 7·14·30일 후속 단계와 후속 제안 초안", slot(8))
          + _sec(sec, 9, "라이브 → 개발 — 라이브 질문·채팅을 묶어 1셀 기획안 초안", slot(9))
          + _sec(sec, 10, "주간 업무 → 경영 보고 — 최신 셀 주간보고를 KPI·리스크·결정 필요로 취합", _weekly()))
    C_ = (_sec(sec, 11, "업무 흐름 단계마다 연결 상태와 기한을 넘긴 일", _bottleneck())
          + _sec(sec, 12, "업무 흐름별 화면·AI 도구 연결률", _progress())
          + _sec(sec, 13, "단계마다 업무 유형·참고 화면·AI 도구·산출물·다음 단계", _handover()))
    return holder + intro + A_ + B_ + C_


def build_actions(sec):
    A = _priv("strategy_room/ai_ops.json") or {}
    T = closure_todos(A)
    if not T:
        body = f"<p style='{NOTE}'>{E(A.get('closures_note') or '종료된 교육청 연수가 등록되면 결과보고·정산·후속 제안 할 일이 자동으로 생깁니다.')}</p>"
    else:
        body = tp._table({"h": "", "head": ["기한", "연수", "할 일", "상태"], "rows": [[d.isoformat(), n, w, f"<b>{s}</b>"] for d, n, w, s, _ in T]})
    return sec("교육청 연수 종료 후속 할 일", "결과보고·정산 단계 기한과 7·14·30일 후속 영업 — AI 업무 도구 ⑦⑧과 연결", body)
