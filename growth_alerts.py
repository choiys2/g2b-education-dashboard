#!/usr/bin/env python3
"""
고도화 4종 (2026-11-15 사용자 결정: 관리 중심, 경쟁사 가격·SET 원자료만 CP '경쟁사' 탭)

  1. hot_alert(sec)      🔒 관리 'B2C 매출 전략' — 핫토픽 선점 경보: 경쟁사 신규 과정에 나온 도구·주제 중 자사 과정이 없거나 열세인 것
  2. price_raw()          CP '경쟁사' 탭 원자료 — 3사 과정 수·15차시 환산 가격·할인·무료·연수+상품 SET 비중(해석 없음)
     price_position(sec) 🔒 관리 'B2C 매출 전략' — 주제별 자사 가격 위치(비쌈/쌈)·SET 미대응 주제
  3. delay_alert(sec)    🔒 관리 '27 전략실' — 셀 지시 기한 ↔ 주간보고 언급 대조 + 프로젝트 정체·기한 위험
  4. order_forecast(sec) 🔒 관리 '교육청 인사이트' — 시도별 2027 발주 가능성 점수 + 이번 달 찾아갈 기관
입력은 이미 쌓인 파일만(외부 호출 없음, 비용 0). 외부 텍스트는 모두 html.escape, 링크는 https 만.
"""
import html
import json
import re
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import training_topics

HERE = Path(__file__).parent
E = html.escape
NOTE = "color:var(--muted);font-size:12.5px;"
OWN, RIVALS = "비바샘연수원", ("티처빌", "아이스크림")
COS = (OWN,) + RIVALS
TOPIC_NAME = {t[0]: t[1] for t in training_topics.TOPICS}
HOT_TERMS = [
    ("클로드(Claude)", r"클로드|Claude"), ("코워크·AI 업무 자동화", r"코워크|Cowork|업무\s?자동화"), ("AI 에이전트", r"에이전트|Agent"),
    ("챗GPT", r"챗\s?GPT|ChatGPT|챗지피티"), ("제미나이(Gemini)", r"제미나이|Gemini"), ("노트북LM", r"노트북\s?LM|NotebookLM"),
    ("바이브 코딩", r"바이브\s?코딩|vibe\s?coding"), ("커서·코딩 도구", r"커서|Cursor|Stitch|Figma"), ("캔바·미리캔버스", r"캔바|Canva|미리캔버스"),
    ("퍼플렉시티·젠스파크", r"퍼플렉시티|Perplexity|젠스파크|Genspark"), ("프롬프트", r"프롬프트"), ("숏폼·영상 제작", r"숏폼|쇼츠|영상\s?제작|브이로그"),
    ("AI 디지털교과서", r"AIDT|AI\s?디지털\s?교과서"), ("생기부·학생부", r"생기부|학생부|세특"), ("서·논술형 평가", r"서[·.]?\s?논술형"),
    ("고교학점제", r"고교\s?학점제"), ("늘봄", r"늘봄"), ("문해력", r"문해력|리터러시"), ("사회정서학습(SEL)", r"사회\s?정서|SEL"),
    ("경제·금융 교육", r"경제\s?교육|금융"), ("기후·생태", r"기후|생태"), ("교권·민원", r"교권|민원"), ("마음챙김·회복", r"마음\s?챙김|회복|번아웃"),
    ("딥페이크·디지털 윤리", r"딥페이크|디지털\s?(윤리|시민)|저작권"), ("노션·스프레드시트", r"노션|Notion|스프레드시트|엑셀|구글\s?시트"),
]
_HOT = [(n, re.compile(r, re.I)) for n, r in HOT_TERMS]


def _j(p, d=None):
    try:
        return json.loads((HERE / p).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return d


def _jsonl(p):
    f = HERE / p
    if not f.exists():
        return []
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]


def _link(u, t):
    return f'<a href="{E(u)}" target="_blank" rel="noopener noreferrer">{E(t)}</a>' if (u or "").startswith("https://") else E(t)


def _tbl(head, rows, num=()):
    cls = lambda i: ' class="num"' if i in num else ""
    return ("<div class='tbl-wrap'><table><thead><tr>" + "".join(f"<th{cls(i)}>{E(h)}</th>" for i, h in enumerate(head))
            + "</tr></thead><tbody>" + "".join("<tr>" + "".join(f"<td{cls(i)}>{c}</td>" for i, c in enumerate(r)) + "</tr>" for r in rows)
            + "</tbody></table></div>")


def _box(txt):
    return f"<div style='margin-top:10px;padding:10px 12px;border-left:3px solid var(--accent);background:var(--surface-2);border-radius:6px;font-size:13px;'>{txt}</div>"


def _pill(t, color):
    return f"<span style='display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;white-space:nowrap;background:color-mix(in srgb, {color} 22%, var(--surface-2));'>{E(t)}</span>"


def _catalog():
    comp = (_j("history/competitor_course_catalog.json") or {}).get("companies") or {}
    out = {}
    for co, v in comp.items():
        rows = []
        for c in v.get("courses") or []:
            t = (c.get("title") or "").strip()
            if not t or t == "상세보기":
                continue
            m = re.search(r"(\d+)\s*차시", (c.get("credit") or "") + " " + (c.get("context") or ""))
            ch = int(m.group(1)) if m else None
            p, o = c.get("price"), c.get("orig_price")
            ctx = c.get("context") or ""
            rows.append({"t": t, "url": c.get("url") or "", "ch": ch, "p": p if isinstance(p, (int, float)) else None,
                         "o": o if isinstance(o, (int, float)) else None,
                         "set": bool(re.search(r"\(연수\s?\+|연수.\S*SET|SET\b", t + " " + ctx)),
                         "tp": [x for x in training_topics.classify_topics(t) if x != "subject"]})
        out[co] = rows
    return out


# ---------------------------------------------------------------- 1. 핫토픽 선점 경보
def hot_terms(days=60):
    cut = (date.today() - timedelta(days=days)).isoformat()
    new = [r for r in _jsonl("history/competitor_new_courses.jsonl") if (r.get("first_seen") or "") >= cut and r.get("company") in RIVALS]
    cat = _catalog()
    own_titles = [c["t"] for c in cat.get(OWN, [])]
    riv_titles = [c["t"] for co in RIVALS for c in cat.get(co, [])]
    rows = []
    for name, rx in _HOT:
        hits = [r for r in new if rx.search(r.get("title") or "")]
        if not hits:
            continue
        own_n = sum(1 for t in own_titles if rx.search(t))
        riv_n = sum(1 for t in riv_titles if rx.search(t))
        first = min(r["first_seen"] for r in hits)
        state = "선점 당함" if own_n == 0 else ("열세" if own_n * 3 < riv_n else "대응 중")
        rows.append({"name": name, "new": len(hits), "first": first, "cos": sorted({r["company"] for r in hits}),
                     "own": own_n, "riv": riv_n, "state": state, "ex": hits[0].get("title", ""), "url": hits[0].get("url", "")})
    order = {"선점 당함": 0, "열세": 1, "대응 중": 2}
    rows.sort(key=lambda r: (order[r["state"]], -r["new"], r["first"]))
    return rows, len(new)


def hot_alert(sec):
    rows, n_new = hot_terms()
    if not rows:
        return sec("핫토픽 선점 경보", "경쟁사 신규 과정이 쌓이면 채워집니다.", "")
    col = {"선점 당함": "#ef4444", "열세": "#f59e0b", "대응 중": "#10b981"}
    today = date.today()
    body = _tbl(["주제·도구", "상태", "경쟁사 신규(60일)", "처음 발견", "경과", "자사 과정", "경쟁사 과정", "경쟁사 예시"],
                [[f"<b>{E(r['name'])}</b>", _pill(r["state"], col[r["state"]]), f"{r['new']} ({E('·'.join(r['cos']))})", E(r["first"]),
                  f"{(today - date.fromisoformat(r['first'])).days}일", str(r["own"]), str(r["riv"]),
                  f"<span style='font-size:12px;'>{_link(r['url'], r['ex'][:48])}</span>"] for r in rows], num=(5, 6))
    hot = [r["name"] for r in rows if r["state"] == "선점 당함"][:4]
    return sec("핫토픽 선점 경보", f"최근 60일 경쟁사 신규 과정 {n_new}개에서 나온 도구·주제를 자사 카탈로그와 대조합니다. '선점 당함' = 경쟁사만 있음.",
               body + _box(f"<b>이번 주 라이브 후보</b> — {E(' · '.join(hot) or '없음')}. 선점 당함 주제는 학점 과정을 새로 만들기보다 "
                           "<b>2주 안에 60~90분 라이브 특강</b>으로 먼저 열고, 반응이 확인되면 심화 코호트·학점 과정으로 확장합니다(경과일이 30일을 넘기면 후발 차별화 — L1 입문·L3 제작 같은 단계로 각도 변경)."))


# ---------------------------------------------------------------- 2. 가격·할인·SET
def _p15(c):
    return c["p"] * 15 / c["ch"] if c["p"] and c["ch"] else None


def price_raw():
    """CP '경쟁사' 탭 원자료(해석 없음)."""
    cat = _catalog()
    rows = []
    for co in COS:
        cs = cat.get(co) or []
        if not cs:
            continue
        v = [x for x in (_p15(c) for c in cs) if x]
        rows.append({"co": co, "n": len(cs), "p15": int(statistics.median(v)) if v else None,
                     "disc": sum(1 for c in cs if c["o"] and c["p"] is not None and c["o"] > c["p"]),
                     "free": sum(1 for c in cs if c["p"] == 0), "set": sum(1 for c in cs if c["set"]),
                     "ch": dict(Counter(c["ch"] for c in cs if c["ch"]).most_common(4))})
    cap = (_j("history/competitor_course_catalog.json") or {}).get("captured_date") or ""
    return {"available": bool(rows), "captured": cap, "rows": rows}


def price_position(sec):
    cat = _catalog()
    if not cat.get(OWN):
        return ""
    by = defaultdict(lambda: defaultdict(list))
    setc = defaultdict(lambda: defaultdict(int))
    for co in COS:
        for c in cat.get(co) or []:
            for t in c["tp"]:
                if _p15(c):
                    by[t][co].append(_p15(c))
                if c["set"]:
                    setc[t][co] += 1
    rows = []
    for t, d in by.items():
        own = statistics.median(d[OWN]) if d.get(OWN) else None
        riv = [x for co in RIVALS for x in d.get(co, [])]
        if not own or len(riv) < 5:
            continue
        rm = statistics.median(riv)
        gap = own / rm - 1
        rs = sum(setc[t][co] for co in RIVALS)
        rows.append((t, own, rm, gap, len(d[OWN]), len(riv), rs, setc[t][OWN]))
    rows.sort(key=lambda r: -r[3])
    pos = lambda g: _pill("비쌈", "#f59e0b") if g >= 0.15 else (_pill("쌈", "#3b82f6") if g <= -0.15 else _pill("비슷", "#10b981"))
    body = _tbl(["주제", "자사 중앙값", "경쟁 2사 중앙값", "차이", "위치", "과정 수(자사/경쟁)", "연수+상품 SET(경쟁/자사)"],
                [[E(TOPIC_NAME.get(t, t)), f"{own:,.0f}원", f"{rm:,.0f}원", f"{gap * 100:+.0f}%", pos(gap), f"{on}/{rn}",
                  f"{rs}/{os_}" + (" " + _pill("SET 미대응", "#ef4444") if rs >= 5 and os_ == 0 else "")] for t, own, rm, gap, on, rn, rs, os_ in rows],
                num=(1, 2, 3))
    hi = [TOPIC_NAME.get(r[0], r[0]) for r in rows if r[3] >= 0.15][:3]
    sm = [TOPIC_NAME.get(r[0], r[0]) for r in rows if r[6] >= 5 and r[7] == 0][:4]
    R = {r["co"]: r for r in price_raw()["rows"]}
    disc = R.get("아이스크림", {}).get("disc", 0)
    return sec("가격·할인·SET 포지셔닝", "15차시 환산 가격(가격 × 15 ÷ 차시) 기준으로 주제별 자사 위치와 연수+상품 SET 대응 여부를 봅니다.",
               body + _box(f"<b>해석</b> — ① 자사가 15% 이상 비싼 주제: <b>{E(' · '.join(hi) or '없음')}</b> → 가격을 내리기보다 라이브 Q&A·자료·SET 같은 '추가 가치'를 붙여 정당화. "
                           f"② 경쟁사는 SET가 있는데 자사는 0인 주제: <b>{E(' · '.join(sm) or '없음')}</b> → 샘몰 SET 후보 칸과 연결해 1순위로 묶기. "
                           f"③ 아이스크림은 할인 과정 {disc}개를 상시 운영 — 자사는 할인보다 멤버십(라이브 묶음) 가격으로 대응하는 편이 마진을 지킵니다."))


# ---------------------------------------------------------------- 3. 지연 경보
def delay_alert(sec):
    try:
        ow = __import__("owner_weekly")
        weeks = ow.load_weeks()
    except Exception:  # noqa: BLE001
        weeks = []
    try:
        dirs = __import__("strategy_room").directives() or []
    except Exception:  # noqa: BLE001
        dirs = []
    today = date.today()
    parts = []
    if dirs:
        latest = json.dumps(weeks[-1][1], ensure_ascii=False) if weeks else ""
        rows = []
        for d in dirs:
            if d["st"] in ("done", "cancel"):
                continue
            toks = [w for w in re.findall(r"[가-힣A-Za-z0-9]{2,}", d["t"]) if w not in ("신규", "과정", "기획", "작성", "추진", "검토")]
            hit = sum(1 for w in toks if w in latest)
            days = (d["due"] - today).days if d.get("due") else None
            f = []
            if days is not None and days < 0:
                f.append(_pill("기한 경과", "#ef4444"))
            elif days is not None and days <= 7:
                f.append(_pill(f"D-{days}", "#f59e0b"))
            if toks and hit == 0:
                f.append(_pill("주간보고 언급 없음", "#8b5cf6"))
            if f:
                rows.append([E(d["cell"]), E(d["t"]), E(d["due"].isoformat() if d.get("due") else "-"), E(d.get("kpi") or "-"), " ".join(f)])
        parts.append("<h4>셀 지시 ↔ 주간보고</h4>" + (_tbl(["셀", "지시", "기한", "KPI", "경보"], rows) if rows
                                                      else f"<p style='{NOTE}'>경보 없음 — 진행 중 지시가 모두 기한 여유가 있고 주간보고에 언급됩니다.</p>"))
    else:
        parts.append(f"<p style='{NOTE}'>셀 지시가 아직 없습니다. 채팅으로 \"1셀에 ○○ 지시, 기한 12/20\"처럼 등록하면 기한·주간보고 언급을 자동 대조합니다.</p>")
    if weeks:
        tr, _ = ow.project_trend(weeks)
        fl = ow.flags(tr, weeks)
        last = weeks[-1][0]
        rows = []
        for k, f in fl.items():
            if not f or last not in tr[k]:
                continue
            pg, _, nm, nd = tr[k][last]
            rows.append([f"<b>{E(k)}</b>", f"{pg}%" if pg is not None else "-", E(nd or "-"), E((nm or "")[:60]), " ".join(_pill(t, c) for c, t in f)])
        ms = [(d, m) for d, m in ow.upcoming(weeks, days=14) if m.get("urgency") in ("critical", "high")]
        parts.append("<h4>프로젝트 정체·기한 위험</h4>" + (_tbl(["프로젝트", "공정률", "다음 기한", "다음 마일스톤", "경보"], rows) if rows
                                                    else f"<p style='{NOTE}'>경보 없음.</p>"))
        if ms:
            parts.append("<h4>14일 안 핵심 마감</h4>" + _tbl(["날짜", "D-", "내용", "셀"], [[E(d.isoformat()), str((d - today).days), E(m.get("label", "")), E(m.get("cell", ""))] for d, m in ms]))
    else:
        parts.append(f"<p style='{NOTE}'>주간보고가 올라오면 정체·기한 위험을 함께 봅니다.</p>")
    return sec("지연 경보 (셀 지시 · 주간보고)", "기한 임박·경과, 주간보고에 언급이 없는 지시, 2주 이상 공정률 정체·일정 위험을 한곳에 모읍니다. 매 배포 갱신.", "".join(parts))


# ---------------------------------------------------------------- 4. 교육청 2027 발주 예측
TRAIN_RX = re.compile(r"연수|역량\s?강화|직무|워크숍|컨설팅|교원\s?(성장|전문성)")
NOT_RX = re.compile(r"수학여행|수련|체험학습|현장학습|공사|급식|청소|경비|시설|차량|임차|NEIS|상담센터|해외|국외|건설|감리|사업관리|설계")
EDU_ORG = re.compile(r"교육청|교육지원청|교육연수원|교육원|교육연구|교육정보원|학교")
SIDO = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]


def _sido(s):
    s = s or ""
    if s == "전남광주":
        return "광주"
    return next((x for x in SIDO if x in s), s)


def order_forecast(sec):
    today = date.today()
    ok = lambda r: TRAIN_RX.search(r.get("t", "")) and not NOT_RX.search(r.get("t", "")) and EDU_ORG.search(r.get("o", ""))
    plans = [r for r in _jsonl("history/order_plans.jsonl") if ok(r)]
    bids = [r for r in _jsonl("history/training_bids.jsonl") if ok(r)]
    sig = [r for r in _jsonl("history/edu_office_signals.jsonl") if (r.get("d") or "") >= (today - timedelta(days=60)).isoformat()]
    nxt = [((today.replace(day=1) + timedelta(days=32 * i)).month) for i in range(0, 3)]
    season = [b for b in bids if (b.get("d") or "")[:4] == str(today.year - 1) or (b.get("d") or "")[:4] == str(today.year)]
    season = [b for b in season if int((b.get("d") or "0000-00")[5:7] or 0) in nxt and (b.get("d") or "") < (today - timedelta(days=200)).isoformat()]
    S = defaultdict(lambda: {"plan": 0, "plan_a": 0, "season": 0, "sig": 0, "y1": 0, "y0": 0})
    for r in plans:
        S[_sido(r.get("r"))]["plan"] += 1
        S[_sido(r.get("r"))]["plan_a"] += r.get("a") or 0
    for b in season:
        S[_sido(b.get("r"))]["season"] += 1
    for r in sig:
        if r.get("plan"):
            S[_sido(r.get("s"))]["sig"] += 1
    y = (today - timedelta(days=365)).isoformat()
    for b in bids:
        S[_sido(b.get("r"))]["y1" if (b.get("d") or "") >= y else "y0"] += 1
    S = {k: v for k, v in S.items() if k in SIDO}
    if not S:
        return ""
    mx = {f: max(1, max(v[f] for v in S.values())) for f in ("plan", "season", "sig", "y1")}
    for v in S.values():
        v["score"] = round(40 * v["plan"] / mx["plan"] + 30 * v["season"] / mx["season"] + 20 * v["sig"] / mx["sig"] + 10 * v["y1"] / mx["y1"], 1)
    rank = sorted(S.items(), key=lambda kv: -kv[1]["score"])
    body = _tbl(["시도", "점수", "연수 발주계획", "계획 금액", "지난해 같은 시기 공고", "정책 신호(60일)", "최근 1년 공고"],
                [[f"<b>{E(k)}</b>", f"<b>{v['score']}</b>", str(v["plan"]), f"{v['plan_a'] / 1e8:.1f}억" if v["plan_a"] else "-", str(v["season"]), str(v["sig"]), str(v["y1"])]
                 for k, v in rank[:12]], num=(1, 2, 4, 5, 6))
    # 이번 달 찾아갈 기관: 발주계획(연수) + 작년 같은 시기 공고 기관
    orgs = {}
    for r in plans:
        orgs.setdefault(r.get("o", ""), {"why": [], "a": 0, "s": _sido(r.get("r"))})
        orgs[r["o"]]["why"].append(f"발주계획: {r.get('t', '')[:40]}")
        orgs[r["o"]]["a"] += r.get("a") or 0
    for b in season:
        orgs.setdefault(b.get("o", ""), {"why": [], "a": 0, "s": _sido(b.get("r"))})
        orgs[b["o"]]["why"].append(f"지난 {b.get('d', '')[:7]} 공고: {b.get('t', '')[:40]}")
        orgs[b["o"]]["a"] += b.get("a") or 0
    top = sorted(((o, v) for o, v in orgs.items() if o), key=lambda kv: -kv[1]["a"])[:15]
    body2 = _tbl(["기관", "시도", "규모", "근거"], [[E(o), E(v["s"]), f"{v['a'] / 1e8:.1f}억" if v["a"] else "-", "<br>".join(E(w) for w in v["why"][:2])] for o, v in top], num=(2,))
    lead = " · ".join(k for k, _ in rank[:3])
    return sec("교육청 2027 발주 예측", "점수 = 연수 발주계획 40 + 지난해 같은 시기(앞으로 3개월) 공고 30 + 정책 신호 20 + 최근 1년 공고 10. 발주계획은 연수 관련(수학여행·공사 등 제외)만.",
               body + "<h4>이번 달 찾아갈 기관 (규모순 15)</h4>" + body2
               + _box(f"<b>영업 우선순위</b> — 점수 상위 <b>{E(lead)}</b>부터 12월 중 발주 전 제안 방문을 잡으세요. 발주계획에 올라온 기관은 공고 전 제안요청서 반영 기회가 있고, "
                      "지난해 같은 시기 공고 기관은 재발주 가능성이 높아 전년 수행사·금액 확인 후 차별 제안을 준비합니다(정책 신호가 높은 시도는 주제 맞춤 제안)."))


if __name__ == "__main__":
    sec = lambda t, d, b: f"<section><h3>{t}</h3><p>{d}</p>{b}</section>"
    r, n = hot_terms()
    print("hot", n, [(x["name"], x["state"], x["new"], x["own"]) for x in r][:12])
    print("price", price_raw())
    print(len(price_position(sec)), len(delay_alert(sec)), len(order_forecast(sec)))
