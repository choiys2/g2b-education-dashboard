#!/usr/bin/env python3
"""
관리 탭 '27 전략실' + 결정 보드 '결정 후보' (관리 비밀번호 암호문 안에만 실린다 - admin_structure.build_html 에서 호출)

  흐름: ① 시장 판도(시각화) → ② 핵심 인사이트 → ③ 2027 방향 → ④ 셀별 실행(1셀 콘텐츠·개발 / 2셀 영업·운영) → ⑤ 월별 점검
  - 데이터: 공개 수집 누적(history/) + 비공개 저장소 지시사항(strategy_room/directives.md) + 실적(MGMT_JSON, 있으면)
  - 셀 지시사항: 사업총괄이 채팅으로 말하면 비공개 저장소 표에 한 줄 추가(공개 저장소에 남기지 않음)
  - 결정 후보: 전략 브리핑(복호화)·수집 감시·시장 신호에서 '결정이 필요한 일'을 뽑아 결정 보드에 보여 준다. 채팅으로 승인하면 decisions/log.md 로 옮긴다.
외부 텍스트는 모두 html.escape, 링크는 http(s)만·새 창 noopener noreferrer. 개인 실명 없음(담당은 셀 단위).
"""
import html
import json
import os
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
E = html.escape
NOTE = "color:var(--muted);font-size:12.5px;"
REG = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
CO = {"비바샘연수원": "var(--accent)", "비바샘": "var(--accent)", "티처빌": "#f59e0b", "아이스크림": "#ec4899"}
CELL = {"1셀": ("콘텐츠·개발", "#8b5cf6"), "2셀": ("영업·운영", "#0ea5e9"), "총괄": ("사업총괄", "#64748b")}
DCOLS = ["날짜", "셀", "지시", "기한", "KPI", "상태", "결과"]
ST = {"진행": "open", "open": "open", "완료": "done", "done": "done", "보류": "hold", "취소": "drop"}


def today():
    return (datetime.now(timezone.utc) + timedelta(hours=9)).date()


def _j(p, d=None):
    try:
        return json.loads((HERE / p).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return d


def _jl(p):
    f = HERE / p
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()] if f.exists() else []


def _num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def eok(v, d=1):
    return f"{v / 1e8:,.{d}f}억"


def _link(u, t):
    return f'<a href="{E(u)}" target="_blank" rel="noopener noreferrer">{E(t)}</a>' if str(u).startswith(("https://", "http://")) else E(t)


def _topics():
    try:
        import training_topics as tt
        return tt, {tid: nm for tid, nm, *_ in tt.TOPICS}
    except Exception:  # noqa: BLE001
        return None, {}


def _region(s):
    s = str(s or "")
    if "전남광주" in s:
        return "광주"
    for r in REG:
        if s.startswith(r) or r in s[:6]:
            return r
    return "전국"


# ------------------------------------------------------------------ 그림(SVG, 외부 라이브러리 없음)
def hbars(rows, w=520, color="var(--accent)", fmt=lambda v: f"{v:,.0f}", colors=None):
    """rows=[(라벨, 값)] 가로 막대"""
    if not rows:
        return f"<p style='{NOTE}'>데이터 없음</p>"
    mx = max(v for _, v in rows) or 1
    bh, lw, h = 22, 90, len(rows) * 22 + 6
    out = [f"<svg viewBox='0 0 {w} {h}' style='width:100%;max-width:{w}px;height:auto;' role='img'>"]
    for i, (lab, v) in enumerate(rows):
        y = i * bh + 3
        bw = (w - lw - 90) * v / mx
        c = (colors or {}).get(lab, color)
        out.append(f"<text x='{lw - 6}' y='{y + 14}' text-anchor='end' font-size='12' fill='var(--ink)'>{E(str(lab))}</text>"
                   f"<rect x='{lw}' y='{y + 3}' width='{max(bw, 1):.1f}' height='14' rx='3' fill='{c}'/>"
                   f"<text x='{lw + bw + 6:.1f}' y='{y + 14}' font-size='11.5' fill='var(--muted)'>{E(fmt(v))}</text>")
    return "".join(out) + "</svg>"


def lines(series, labels, w=620, h=200, fmt=lambda v: f"{v:,.0f}"):
    """series=[(이름, 색, [값...])] 꺾은선(월별)"""
    vals = [v for _, _, s in series for v in s if v is not None]
    if not vals:
        return f"<p style='{NOTE}'>데이터 없음</p>"
    mx, n, pl, pb = max(vals) or 1, len(labels), 40, 26
    x = lambda i: pl + (w - pl - 10) * i / max(n - 1, 1)
    y = lambda v: 10 + (h - pb - 10) * (1 - v / mx)
    out = [f"<svg viewBox='0 0 {w} {h}' style='width:100%;max-width:{w}px;height:auto;' role='img'>"]
    for k in range(3):
        gv = mx * k / 2
        out.append(f"<line x1='{pl}' x2='{w - 10}' y1='{y(gv):.1f}' y2='{y(gv):.1f}' stroke='var(--border)'/><text x='{pl - 4}' y='{y(gv) + 4:.1f}' text-anchor='end' font-size='10' fill='var(--muted)'>{E(fmt(gv))}</text>")
    for i, lb in enumerate(labels):
        out.append(f"<text x='{x(i):.1f}' y='{h - 8}' text-anchor='middle' font-size='10.5' fill='var(--muted)'>{E(lb)}</text>")
    for name, col, s in series:
        pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(s) if v is not None)
        out.append(f"<polyline points='{pts}' fill='none' stroke='{col}' stroke-width='2.2'/>")
        out += [f"<circle cx='{x(i):.1f}' cy='{y(v):.1f}' r='3' fill='{col}'><title>{E(name)} {E(labels[i])}: {E(fmt(v))}</title></circle>" for i, v in enumerate(s) if v is not None]
    return "".join(out) + "</svg>"


def legend(items):
    return "<div style='display:flex;gap:12px;flex-wrap:wrap;font-size:12px;margin:4px 0 8px;'>" + "".join(
        f"<span><i style='display:inline-block;width:10px;height:10px;border-radius:2px;background:{c};margin-right:4px;'></i>{E(n)}</span>" for n, c in items) + "</div>"


def gauge(cur, target, label, w=520):
    """현재 vs 목표 막대(%, 0~100)"""
    cur = max(0, min(100, cur or 0))
    return (f"<div style='margin:6px 0 10px;'><div style='font-size:12.5px;margin-bottom:4px;'>{E(label)}</div>"
            f"<svg viewBox='0 0 {w} 30' style='width:100%;max-width:{w}px;height:auto;'>"
            f"<rect x='0' y='6' width='{w}' height='14' rx='7' fill='var(--surface-2)' stroke='var(--border)'/>"
            f"<rect x='0' y='6' width='{w * cur / 100:.1f}' height='14' rx='7' fill='#f59e0b'/>"
            f"<line x1='{w * target / 100:.1f}' x2='{w * target / 100:.1f}' y1='0' y2='26' stroke='#10b981' stroke-width='3'/>"
            f"<text x='{min(w * cur / 100 + 6, w - 70):.1f}' y='18' font-size='11' fill='var(--ink)'>현재 {cur:.0f}%</text></svg>"
            f"<div style='{NOTE}'>초록 선 = 2027 목표 {target}%</div></div>")


def tiles(ts):
    return ("<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:6px 0 12px;'>"
            + "".join(f"<div style='padding:10px 12px;border:1px solid var(--border);border-radius:10px;background:var(--surface-2);'>"
                      f"<div style='font-size:12px;color:var(--muted);'>{E(k)}</div><div style='font-size:21px;font-weight:800;color:{c};'>{E(str(v))}</div>"
                      f"<div style='font-size:11.5px;color:var(--muted);'>{E(s)}</div></div>" for k, v, s, c in ts) + "</div>")


def grid2(a, b):
    return f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px;'><div>{a}</div><div>{b}</div></div>"


# ------------------------------------------------------------------ 데이터
def market():
    tt, names = _topics()
    T = _jl("history/training_bids.jsonl")
    seen, rows = set(), []
    for r in T:  # 차수(-000/-001) 중복 제거: 공고번호 앞부분 기준
        k = str(r.get("k", "")).rsplit("-", 1)[0]
        if k in seen:
            continue
        seen.add(k)
        rows.append({"d": r.get("d", ""), "t": r.get("t", ""), "r": _region(r.get("r")), "a": _num(r.get("a")),
                     "tp": tt.classify_topics(r.get("t", "")) if tt else []})
    y26 = [r for r in rows if r["d"].startswith("2026")]
    month = [0] * 12
    amt = [0.0] * 12
    for r in y26:
        m = int(r["d"][5:7])
        month[m - 1] += 1
        amt[m - 1] += r["a"]
    reg = Counter()
    for r in y26:
        reg[r["r"]] += r["a"]
    h1 = Counter(tp for r in y26 if r["d"][5:7] <= "06" for tp in r["tp"])
    h2 = Counter(tp for r in y26 if r["d"][5:7] > "06" for tp in r["tp"])
    mom = sorted(((names.get(k, k), h1[k], h2[k]) for k in set(h1) | set(h2)), key=lambda x: -(x[2] - x[1]))
    # 경쟁 판도: 나라장터 낙찰(경쟁사) + 교육청 수의계약(K-에듀파인)
    W = _jl("history/competitor_wins.jsonl")
    win = Counter()
    for w in W:
        if str(w.get("date", "")).startswith("2026"):
            win[w.get("competitor", "")] += _num(w.get("amount"))
    ec = _jl("history/edu_contracts.jsonl")
    sui = Counter(r.get("vendor") for r in ec if r.get("vendor") in ("비바샘연수원", "티처빌", "아이스크림"))
    sui_amt = Counter()
    for r in ec:
        if r.get("vendor") in ("비바샘연수원", "티처빌", "아이스크림"):
            sui_amt[r["vendor"]] += _num(r.get("amount"))
    comp_reg = defaultdict(Counter)
    for w in W:
        comp_reg[_region(w.get("region"))][w.get("competitor", "")] += 1
    plans = [p for p in _jl("history/order_plans.jsonl") if re.search(r"연수|역량|교원|직무", p.get("t", ""))]
    return {"rows": rows, "y26": y26, "month": month, "amt": amt, "reg": reg, "mom": mom, "win": win,
            "sui": sui, "sui_amt": sui_amt, "comp_reg": comp_reg, "plans": plans, "names": names}


def catalog():
    c = (_j("history/competitor_course_catalog.json", {}) or {}).get("companies", {})
    tt, names = _topics()
    n = {k: len(v.get("courses", [])) for k, v in c.items()}
    cov = {}
    for k, v in c.items():
        cov[k] = Counter(tp for x in v.get("courses", []) for tp in (tt.classify_topics(x.get("title", "")) if tt else []))
    own = cov.get("비바샘연수원", Counter())
    gaps = sorted(((names.get(t, t), max(cov.get("티처빌", {}).get(t, 0), cov.get("아이스크림", {}).get(t, 0)), own.get(t, 0))
                   for t in set().union(*[set(x) for x in cov.values()]) if t != "subject" and own.get(t, 0) * 3 < max(cov.get("티처빌", {}).get(t, 0), cov.get("아이스크림", {}).get(t, 0))),
                  key=lambda x: -(x[1] - x[2]))
    newc = [r for r in _jl("history/competitor_new_courses.jsonl") if r.get("first_seen", "") >= (today() - timedelta(days=30)).isoformat() and r.get("title") not in ("상세보기", "")]
    return {"n": n, "gaps": gaps, "new30": newc}


def _private():
    env = os.environ.get("PRIVATE_DATA_DIR", "").strip()
    for d in ([Path(env)] if env else []) + [HERE / "_private", HERE / "private.local"]:
        if d.is_dir():
            return d
    return None


def _date(s, ref):
    s = (s or "").strip()
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return date(*map(int, m.groups()))
    m = re.match(r"(\d{1,2})[./](\d{1,2})", s)
    if m:
        mo, dd = int(m.group(1)), int(m.group(2))
        y = ref.year + (1 if mo < ref.month - 6 else 0)
        try:
            return date(y, mo, dd)
        except ValueError:
            return None
    return None


def directives():
    """비공개 저장소 strategy_room/directives.md 표 -> [{셀, 지시, 기한(date), KPI, 상태, 결과, 날짜}]"""
    d = _private()
    f = d / "strategy_room" / "directives.md" if d else None
    if not f or not f.is_file():
        return None
    ref, out, head = today(), [], None
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if head is None:
            head = cells
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        r = dict(zip(head, cells + [""] * (len(head) - len(cells))))
        if "(예시)" in "".join(cells) or not r.get("지시"):
            continue
        out.append({"made": _date(r.get("날짜"), ref), "cell": r.get("셀", "총괄") or "총괄", "t": r.get("지시", ""), "due": _date(r.get("기한"), ref),
                    "kpi": r.get("KPI", ""), "st": ST.get((r.get("상태") or "진행").strip(), "open"), "res": r.get("결과", "")})
    return out


def decisions():
    try:
        import owner_decisions as od
        return od.load(today()) or []
    except Exception:  # noqa: BLE001
        return []


def latest_briefing():
    """가장 최근 전략 브리핑(암호문) 복호화 - STRATEGY_KEY 가 있을 때만. 로컬 시험: STRATEGY_PLAIN_DIR(평문 json 폴더)"""
    pdir = os.environ.get("STRATEGY_PLAIN_DIR", "").strip()
    if pdir and Path(pdir).is_dir():
        fs = sorted(Path(pdir).glob("sb_*.json"))
        if fs:
            return json.loads(fs[-1].read_text(encoding="utf-8"))
    key = os.environ.get("STRATEGY_KEY", "")
    fs = sorted((HERE / "strategy_briefings").glob("20*.enc.json"))
    if not key or not fs:
        return None
    try:
        import strategy_crypto
        return strategy_crypto.decrypt(json.loads(fs[-1].read_text(encoding="utf-8")), key)
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------------ 인사이트·방향·후보(규칙 기반, 수치 근거 포함)
def insights(M, C):
    out = []
    reg = [(r, v) for r, v in M["reg"].most_common() if r != "전국"]
    tot = sum(M["reg"].values()) or 1
    if reg:
        top3 = reg[:3]
        out.append(("시장 집중", f"2026 연수 발주 금액의 {sum(v for _, v in top3) / tot * 100:.0f}%가 {', '.join(r for r, _ in top3)}에 몰려 있습니다(총 {eok(tot)}).",
                    "상위 3개 시도는 2셀 상시 영업 대상, 나머지는 주제형 제안으로 접근"))
    up = [m for m in M["mom"] if m[2] > m[1]][:3]
    if up:
        out.append(("뜨는 주제", "하반기 발주가 늘어난 주제: " + ", ".join(f"{n}({a}→{b}건)" for n, a, b in up) + ".", "1셀 2027 과정 개발 우선순위에 반영"))
    w = M["win"]
    if w:
        t = sum(w.values()) or 1
        lead = w.most_common(1)[0]
        out.append(("경쟁 판도", f"2026 나라장터 연수 낙찰(경쟁사 확인분) {eok(t)} 중 {lead[0]}이 {lead[1] / t * 100:.0f}%를 가져갔습니다.",
                    "경쟁사 낙찰 상위 지역부터 2027 사전 접촉(공고 2~3개월 전)"))
    s = M["sui"]
    if s:
        out.append(("수의계약(학교·교육청)", "K-에듀파인 공개 수의계약 건수: " + ", ".join(f"{k} {v}건" for k, v in s.most_common()) + ".",
                    "수의계약에서 앞서는 강점을 학교 단위 B2S 패키지로 확장"))
    if C["gaps"]:
        g = C["gaps"][:3]
        out.append(("과정 공백", "경쟁사 대비 우리 과정이 크게 적은 주제: " + ", ".join(f"{n}(경쟁 {a}·자사 {b})" for n, a, b in g) + ".", "1셀이 공백 주제 신규 과정 기획"))
    if C["new30"]:
        out.append(("경쟁사 신규 과정", f"최근 30일 경쟁사 신규 과정 {len(C['new30'])}개가 확인됐습니다.", "1셀 월간 대응표에 반영"))
    return out


def directions(M, C, mg):
    share = None
    try:
        if mg and mg.get("years"):
            y = sorted(mg["years"], key=lambda r: r.get("y", 0))[-1]
            share = (y["b2s"] + y["b2g"]) / y["tot"] * 100 if y.get("tot") else None
    except Exception:  # noqa: BLE001
        share = None
    reg = [r for r, _ in M["reg"].most_common(8) if r != "전국"][:5]
    up = [n for n, a, b in M["mom"] if b > a][:3]
    gaps = [n for n, _, _ in C["gaps"][:3]]
    return share, [
        ("① 매출 구조 전환", "B2G 40 : B2C+B2S 60", "B2G 의존 축소와 B2C·B2S 성장. 학교 단위 패키지·샘몰(2026 H2)·개인 재수강을 묶어 키운다.", "총괄"),
        ("② 주제 포트폴리오", " · ".join(dict.fromkeys(up + gaps)) or "-", "하반기 발주가 늘어난 주제와 경쟁사 대비 과정 공백 주제를 2027 신규 과정으로 먼저 만든다.", "1셀"),
        ("③ 지역 공략", " · ".join(reg) or "-", "발주 금액 상위 시도는 상시 관리, 경쟁사 낙찰 지역은 공고 2~3개월 전 사전 제안.", "2셀"),
        ("④ AI·플랫폼 전환", "AI 활용 연수·샘몰", "AI 연수 체계 개편 기조(교육부)에 맞춘 과정과 플랫폼(샘몰·교사 크리에이터) 결합.", "1셀·2셀"),
    ]


def suggested(M, C):
    """셀별 '제안 지시'(데이터 기반, 채택은 채팅으로)"""
    s = {"1셀": [], "2셀": []}
    for n, a, b in C["gaps"][:3]:
        s["1셀"].append(f"'{n}' 신규 과정 기획안(경쟁 {a}개 · 자사 {b}개) — 2027 1분기 오픈 목표")
    up = [m for m in M["mom"] if m[2] > m[1]][:2]
    for n, a, b in up:
        s["1셀"].append(f"'{n}' 교육청 위탁형 과정 패키지 준비(하반기 발주 {a}→{b}건)")
    for r, v in [x for x in M["reg"].most_common(5) if x[0] != "전국"][:3]:
        cr = M["comp_reg"].get(r)
        s["2셀"].append(f"{r} 교육청 2027 연수 수요 사전 접촉(2026 발주 {eok(v)}" + (f", 경쟁사 낙찰 {sum(cr.values())}건" if cr else "") + ")")
    if M["plans"]:
        s["2셀"].append(f"발주계획 공개분 중 연수 관련 {len(M['plans'])}건 담당 배정·제안 일정 수립")
    return s


def candidates(M, C):
    """결정 후보: (결정안, 근거, 담당, 기한일수, KPI)"""
    out = []
    w = _jl("history/pipeline_watch.jsonl")
    full = [r for r in w if not r.get("quick")]
    if full and full[-1].get("status") != "ok":
        out.append(("수집 장애 복구 담당·기한 지정", f"최근 수집 감시 실패: {', '.join(full[-1].get('fail') or [])}", "총괄", 2, "다음 수집 정상"))
    b = latest_briefing()
    for o in (b or {}).get("opportunities", [])[:4]:
        out.append((str(o.get("idea", ""))[:60], f"전략 브리핑 {b.get('date', '')}: {str(o.get('action', ''))[:90]}", "2셀" if re.search(r"교육청|영업|제안|B2G", str(o)) else "1셀",
                    14, str(o.get("timing", ""))[:20] or "실행 여부"))
    sig = Counter(r["s"] for r in _jl("history/edu_office_signals.jsonl") if r.get("plan") and r.get("d", "") >= (today() - timedelta(days=30)).isoformat())
    for s, n in sig.most_common(2):
        out.append((f"{s}교육청 2027 사업 대응 제안서 착수", f"최근 30일 '계획 신호' 기사 {n}건(시행계획·예산·정책연구)", "2셀", 21, "제안 미팅 1회"))
    for n, a, b in C["gaps"][:2]:
        out.append((f"'{n}' 신규 과정 개발 착수 여부", f"경쟁사 {a}개 대비 자사 {b}개", "1셀", 30, "기획안 승인"))
    return out


# ------------------------------------------------------------------ 화면
def build_candidates(sec):
    try:
        M, C = market(), catalog()
        cs = candidates(M, C)
    except Exception as e:  # noqa: BLE001
        print(f"[경고] 결정 후보 실패: {type(e).__name__}")
        cs = []
    if not cs:
        return sec("결정 후보 (자동)", "데이터에서 결정이 필요한 일을 뽑습니다.", f"<p style='{NOTE}'>지금 올라온 후보가 없습니다.</p>")
    t = today()
    cs = [tuple(str(x).replace("|", "/") if isinstance(x, str) else x for x in c) for c in cs]
    rows = "".join(f"<tr><td class='num'>{i}</td><td><b>{E(a)}</b><div style='{NOTE}'>{E(b)}</div></td><td>{E(c)}</td><td style='white-space:nowrap;'>{(t + timedelta(days=d)):%m/%d}</td><td>{E(k)}</td>"
                   f"<td><code style='font-size:11px;user-select:all;'>| {t:%Y-%m-%d} | {E(a)} | {E(b[:40])} | {E(c)} | {(t + timedelta(days=d)):%m/%d} | {E(k)} | 진행 | |</code></td></tr>"
                   for i, (a, b, c, d, k) in enumerate(cs, 1))
    return sec("결정 후보 (자동 · 승인 대기)",
               "전략 브리핑·수집 감시·교육청 계획 신호·과정 공백에서 '결정이 필요한 일'을 뽑았습니다. 채팅으로 \"결정 후보 1·3 승인\"처럼 말하면 결정 기록(decisions/log.md)으로 옮깁니다. 오른쪽 칸은 기록 줄 형식입니다.",
               f"<div class='tbl-wrap'><table><thead><tr><th class='num'>#</th><th>결정안 · 근거</th><th>담당</th><th>제안 기한</th><th>KPI</th><th>기록 줄</th></tr></thead><tbody>{rows}</tbody></table></div>")


def build_strategy(sec):
    M, C = market(), catalog()
    try:
        mg = __import__("mgmt_owner").load()
    except Exception:  # noqa: BLE001
        mg = None
    t = today()
    tot26 = sum(M["reg"].values())
    # ① 시장 판도
    s1_tiles = tiles([("2026 연수 발주(누적)", f"{len(M['y26'])}건", eok(tot26), "var(--ink)"),
                      ("경쟁사 낙찰 확인분", eok(sum(M["win"].values())), " · ".join(f"{k} {v / 1e8:.1f}억" for k, v in M["win"].most_common()), "#ec4899"),
                      ("수의계약(자사)", f"{M['sui'].get('비바샘연수원', 0)}건", f"티처빌 {M['sui'].get('티처빌', 0)} · 아이스크림 {M['sui'].get('아이스크림', 0)}", "var(--accent)"),
                      ("과정 수(자사/티처빌/아이스크림)", f"{C['n'].get('비바샘연수원', 0)}", f"{C['n'].get('티처빌', 0)} / {C['n'].get('아이스크림', 0)}", "var(--ink)")])
    mon = lines([("발주 건수", "var(--accent)", M["month"][:t.month] if t.year == 2026 else M["month"])], [f"{i + 1}월" for i in range(t.month if t.year == 2026 else 12)])
    regb = hbars([(r, v / 1e8) for r, v in M["reg"].most_common(10)], fmt=lambda v: f"{v:,.1f}억", colors={"전국": "#94a3b8"})
    comp = hbars([(k, v / 1e8) for k, v in M["win"].most_common()], fmt=lambda v: f"{v:,.1f}억", colors=CO)
    sui = hbars([(k, v) for k, v in M["sui"].most_common()], fmt=lambda v: f"{v:,.0f}건", colors=CO)
    mom_rows = "".join(f"<tr><td>{E(n)}</td><td class='num'>{a}</td><td class='num'>{b}</td><td class='num' style='color:{'#10b981' if b > a else '#dc2626' if b < a else 'var(--muted)'};'>{b - a:+d}</td></tr>" for n, a, b in M["mom"][:10])
    s1 = sec("① 시장 판도 — 2026 연수 발주·경쟁·과정",
             "나라장터 연수 입찰(차수 중복 제거)·경쟁사 낙찰·교육청 수의계약(K-에듀파인)·경쟁사 과정 카탈로그 누적 기준. 금액은 공고 예산 기준.",
             s1_tiles
             + grid2("<h4>월별 연수 발주 건수(2026)</h4>" + mon, "<h4>시도별 발주 금액 상위 10</h4>" + regb + f"<p style='{NOTE}'>'전국' = 중앙부처·전국 단위 발주(시도 구분 불가)</p>")
             + grid2("<h4>경쟁사 나라장터 낙찰(2026, 확인분)</h4>" + comp, "<h4>교육청·학교 수의계약 건수(공개분)</h4>" + sui)
             + "<h4>주제별 발주 흐름(상반기 → 하반기 건수)</h4><div class='tbl-wrap'><table><thead><tr><th>주제</th><th class='num'>상반기</th><th class='num'>하반기</th><th class='num'>증감</th></tr></thead><tbody>"
             + mom_rows + "</tbody></table></div>")
    # ② 인사이트
    ins = insights(M, C)
    s2 = sec("② 핵심 인사이트 — 데이터가 말하는 것",
             "규칙 기반 자동 해석(수치는 위 ①과 같은 원천). 오른쪽 '그래서'가 실행 방향입니다.",
             "<div class='tbl-wrap'><table><thead><tr><th>구분</th><th>사실(수치)</th><th>그래서</th></tr></thead><tbody>"
             + "".join(f"<tr><td style='white-space:nowrap;'><b>{E(a)}</b></td><td>{E(b)}</td><td>{E(c)}</td></tr>" for a, b, c in ins) + "</tbody></table></div>")
    # ③ 2027 방향
    share, dirs = directions(M, C, mg)
    g = gauge(share, 40, "B2G 매출 비중 (MGMT_JSON 최근 연도)") if share is not None else f"<p style='{NOTE}'>B2G 비중: 실적(MGMT_JSON) 등록 시 표시 · 목표 2027 B2G 40%</p>"
    cards = "".join(f"<div style='border:1px solid var(--border);border-left:4px solid {CELL.get(o.split('·')[0], ('', '#64748b'))[1]};border-radius:8px;padding:10px 12px;'>"
                    f"<b>{E(a)}</b> <span style='{NOTE}'>담당 {E(o)}</span><div style='font-size:13px;margin:4px 0;'>{E(b)}</div><div style='{NOTE}'>{E(c)}</div></div>" for a, b, c, o in dirs)
    s3 = sec("③ 2027 방향 — 4대 축", "핵심 과제(B2G 의존 축소 · Core 재설계 · AI/플랫폼 · 샘몰)를 데이터로 구체화했습니다. 주제·지역은 ①의 수치에서 자동으로 고릅니다.",
             g + f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px;'>{cards}</div>")
    # ④ 셀별 실행
    D = directives()
    sug = suggested(M, C)
    cell_html = ""
    for cell in ("1셀", "2셀"):
        role, col = CELL[cell]
        mine = [d for d in (D or []) if d["cell"].startswith(cell)]
        op = [d for d in mine if d["st"] == "open"]
        late = [d for d in op if d["due"] and d["due"] < t]
        done = [d for d in mine if d["st"] == "done"]
        if cell == "1셀":
            kp = [("자사 과정", f"{C['n'].get('비바샘연수원', 0)}", "경쟁 최대 " + str(max(C['n'].get('티처빌', 0), C['n'].get('아이스크림', 0))), col),
                  ("공백 주제", f"{len(C['gaps'])}개", "경쟁 대비 1/3 미만", "#dc2626" if C["gaps"] else col),
                  ("경쟁 신규(30일)", f"{len(C['new30'])}개", "대응 검토", col)]
        else:
            kp = [("2026 발주", f"{len(M['y26'])}건", eok(tot26), col),
                  ("경쟁사 낙찰", f"{sum(M['comp_reg'].get(r, Counter()).total() for r in M['comp_reg'])}건", "2026 확인분", "#ec4899"),
                  ("연수 발주계획", f"{len(M['plans'])}건", "공개분", col)]
        kp.append(("지시 진행/지연/완료", f"{len(op)}/{len(late)}/{len(done)}", "기한 지남 빨강", "#dc2626" if late else col))
        lst = "".join(f"<li style='margin:3px 0;'>{'🔴' if d in late else ('✅' if d['st'] == 'done' else '⏳')} {E(d['t'])} <span style='{NOTE}'>{('기한 ' + d['due'].strftime('%m/%d')) if d['due'] else ''} {E(d['kpi'])}</span></li>"
                      for d in sorted(mine, key=lambda d: (d["st"] != "open", d["due"] or date(2100, 1, 1)))[:10]) or f"<li style='{NOTE}'>등록된 지시가 없습니다.</li>"
        sg = "".join(f"<li style='margin:3px 0;'>{E(x)}</li>" for x in sug.get(cell, [])[:5])
        cell_html += (f"<div style='border:1px solid var(--border);border-top:4px solid {col};border-radius:10px;padding:12px;'>"
                      f"<p style='font-weight:800;margin:0 0 4px;'>연수 {cell} · {E(role)}</p>" + tiles(kp)
                      + f"<h4 style='margin:8px 0 4px;'>지시사항</h4><ul style='margin:0 0 0 16px;padding:0;font-size:13px;'>{lst}</ul>"
                      + f"<h4 style='margin:10px 0 4px;'>데이터 기반 제안 지시</h4><ul style='margin:0 0 0 16px;padding:0;font-size:12.5px;color:var(--muted);'>{sg or '<li>없음</li>'}</ul></div>")
    s4 = sec("④ 셀별 실행 — 연수 1셀(콘텐츠·개발) · 2셀(영업·운영)",
             "지시사항은 비공개 저장소 strategy_room/directives.md 표가 원본입니다. 채팅으로 \"1셀에 ○○ 지시, 기한 12/20\"처럼 말하면 한 줄 추가합니다. '제안 지시'는 데이터로 고른 후보이며, 채택하면 지시로 옮깁니다."
             + ("" if D is not None else " (지시 표 파일이 아직 없습니다)"),
             f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:12px;'>{cell_html}</div>")
    # ⑤ 월별 점검
    months = []
    y, m = t.year, t.month
    for _ in range(14):
        months.append((y, m))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    DEC = decisions()

    def cellv(items, ym):
        due = [d for d in items if d.get("due") and (d["due"].year, d["due"].month) == ym]
        if not due:
            return "<td class='num' style='color:var(--muted);'>·</td>"
        dn = sum(1 for d in due if d["st"] == "done")
        late = sum(1 for d in due if d["st"] == "open" and d["due"] < t)
        c = "#10b981" if dn == len(due) else ("#dc2626" if late else "#f59e0b")
        return f"<td class='num' style='background:color-mix(in srgb, {c} 28%, transparent);' title='완료 {dn} / 전체 {len(due)}'>{dn}/{len(due)}</td>"

    season = [M["month"][mm - 1] for _, mm in months]
    smx = max(season) or 1
    head = "".join(f"<th class='num'>{('’' + str(yy)[2:] + '.') if mm == 1 or i == 0 else ''}{mm}월</th>" for i, (yy, mm) in enumerate(months))
    rows = ""
    for cell in ("1셀", "2셀", "총괄"):
        rows += f"<tr><td><b>{E(cell)}</b> 지시</td>" + "".join(cellv([d for d in (D or []) if d["cell"].startswith(cell)], ym) for ym in months) + "</tr>"
    rows += "<tr><td><b>결정</b> 기한</td>" + "".join(cellv([{"due": d.get("due"), "st": d.get("st")} for d in DEC], ym) for ym in months) + "</tr>"
    rows += ("<tr><td>시장 발주 성수기<div style='" + NOTE + "'>2026 월별 연수 공고 건수</div></td>"
             + "".join(f"<td class='num' style='background:color-mix(in srgb, var(--accent) {10 + 55 * v // smx}%, transparent);'>{v or '·'}</td>" for v in season) + "</tr>")
    s5 = sec("⑤ 월별 점검 — 지시·결정 이행 × 시장 성수기",
             "칸 = 그 달 기한인 항목의 완료/전체. 초록 전부 완료 · 주황 진행 중 · 빨강 기한 지남. 맨 아래 줄은 2026년 같은 달 연수 공고 건수(성수기 대비 준비 시점 판단용).",
             f"<div class='tbl-wrap'><table><thead><tr><th>구분</th>{head}</tr></thead><tbody>{rows}</tbody></table></div>")
    return s1 + s2 + s3 + s4 + s5


if __name__ == "__main__":
    sec = lambda a, b, c: f"<section><h3>{a}</h3><p>{b}</p>{c}</section>"
    h = build_strategy(sec) + build_candidates(sec)
    print(len(h))
    print(re.sub(r"<[^>]+>", " ", h)[:3000])
