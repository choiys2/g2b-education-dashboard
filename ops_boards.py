#!/usr/bin/env python3
"""
🔒 관리 탭 운영 보드 8종 (2026-11-17 사용자 지시: "개발해줘 모두")

  경영 종합(1셀 운영·시스템·마케팅 칸 아래): ① 라이브 운영 보드 ② 라이브 주제 추천기 ⑤ 샘크 성장 사다리
                                            ⑥ AX 제작 파이프라인 ⑦ 중등 SET 처방
  마케팅 보드(새 칸): ③ 출시 후 90일 노출 캘린더 ④ 채널별 성과판
  결정 보드: ⑧ 셀 간 공 넘기기   ·   이번 주 할 일: 라이브 후속 할 일

  입력값: 비공개 저장소 strategy_room/ops_boards.json(채팅으로 받은 값을 쌓음, 실명 금지).
  추천기·처방은 이미 모은 공개 수집 데이터(교육청 신호·입찰·경쟁사 신규 과정·조간 지면·연수 목록)만 읽는다.
"""
import json
import re
import statistics
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import training_plan as tp

HERE = Path(__file__).parent
E = tp.E
NOTE = tp.NOTE


def load():
    try:
        d = __import__("strategy_room")._private()
    except Exception:  # noqa: BLE001
        d = None
    for base in ([d] if d else []) + [HERE / "_private", HERE / "private.local"]:
        f = base / "strategy_room" / "ops_boards.json"
        if f.is_file():
            return json.loads(f.read_text(encoding="utf-8"))
    return None


def _today():
    return datetime.now(timezone(timedelta(hours=9))).date()


def _d(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except Exception:  # noqa: BLE001
        return None


def _pct(a, b):
    return round(a / b * 100) if a is not None and b else None


def _t(h, head, rows):
    return tp._table({"h": h, "head": head, "rows": rows})


def _tiles(items):
    return tp._tiles({"items": items})


def _box(text):
    return tp._box({"text": text})


def _empty(msg="데이터 준비 중"):
    return f"<p style='{NOTE}'>{E(msg)}</p>"


# ---------------------------------------------------------------- ① 라이브 운영 보드
def _live_board(D):
    L = sorted(D.get("lives") or [], key=lambda x: x.get("date", ""))
    B = D.get("live_baseline") or {}
    if not L:
        return _empty()
    rows, ar, sr = [], [], []
    for x in L:
        a, s = _pct(x.get("attend"), x.get("apply")), _pct(x.get("self_apply"), x.get("attend"))
        if a is not None:
            ar.append(a)
        if s is not None:
            sr.append(s)
        flag = lambda v, base: "-" if v is None else (f"{v}%" + (" ▼기준 미달" if base and v < base else ""))
        rows.append([x.get("date", ""), f"<b>{x.get('title', '')}</b> · {x.get('kind', '')}",
                     "-" if x.get("apply") is None else f"{x['apply']:,}", "-" if x.get("attend") is None else f"{x['attend']:,}",
                     flag(a, B.get("attend_rate")), "공개" if x.get("recorded") else "미공개",
                     "-" if x.get("self_apply") is None else f"{x['self_apply']:,}", flag(s, B.get("self_rate")),
                     "측정 전" if x.get("paid30") is None else f"{x['paid30']:,}명", x.get("next", "")])
    paid = sum(1 for x in L if x.get("paid30") is not None)
    tiles = _tiles([["기록된 라이브", f"{len(L)}회", "회차마다 한 줄씩 쌓임"],
                    ["평균 참여율", f"{round(statistics.mean(ar))}%" if ar else "-", f"목표 {B.get('attend_target', '-')}%"],
                    ["평균 자율연수 전환", f"{round(statistics.mean(sr))}%" if sr else "-", f"목표 {B.get('self_target', '-')}%"],
                    ["30일 유료 전환 측정", f"{paid}/{len(L)}회", "쿠폰 코드로 측정 시작 필요"]])
    tbl = _t("", ["날짜", "라이브", "신청", "참여", "참여율", "녹화본", "자율연수 신청", "전환율", "30일 유료", "다음 단계"], rows)
    return tiles + tbl + _box("<b>입력 방법</b> — 라이브가 끝나면 '날짜·제목·신청·참여·녹화본 공개 여부·자율연수 신청·30일 뒤 유료 수강 수'를 채팅으로 주세요. 기준선(참여 58%·전환 27%)보다 낮으면 ▼로 표시하고, 후속 할 일은 '이번 주 할 일'에 자동으로 올라갑니다.")


def live_todos(D, today=None):
    """라이브 후속 할 일: 녹화본 공개(D+3)·참여자 쿠폰(D+1~7)·후속 라이브 초대·유료 전환 집계(D+30)"""
    today = today or _today()
    out = []
    for x in D.get("lives") or []:
        d0 = _d(x.get("date"))
        if not d0 or (today - d0).days > 40 or (d0 - today).days > 14:
            continue
        steps = []
        if not x.get("recorded"):
            steps.append((d0 + timedelta(days=3), "녹화본 무료 자율연수 공개 + 끝 화면에 다음 연수·SET 안내"))
        steps.append((d0 + timedelta(days=1), "참여자 7일 쿠폰 발송(채널 추적 코드)"))
        steps.append((d0 + timedelta(days=30), "후속 라이브 초대 + 30일 유료 수강 집계 입력"))
        for due, what in steps:
            if what.startswith("후속") and x.get("paid30") is not None:
                continue
            gap = (due - today).days
            st = "지남" if gap < 0 else ("이번 주" if gap <= 7 else "예정")
            out.append((due, x.get("title", ""), what, st))
    return sorted(out)


# ---------------------------------------------------------------- ② 라이브 주제 추천기
def _jsonl(path, key, since):
    f = HERE / path
    if not f.exists():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if str(r.get(key, ""))[:10] >= since:
            out.append(r)
    return out


def _topic_reco(D, today=None):
    try:
        import training_topics as tt
    except Exception:  # noqa: BLE001
        return _empty()
    today = today or _today()
    s30, s60, s7 = (today - timedelta(days=30)).isoformat(), (today - timedelta(days=60)).isoformat(), (today - timedelta(days=7)).isoformat()
    name = {t[0]: t[1] for t in tt.TOPICS}
    score, ev, ex = Counter(), {}, {}

    def add(tid, src, w, title):
        score[tid] += w
        ev.setdefault(tid, Counter())[src] += 1
        ex.setdefault(tid, [])
        if len(ex[tid]) < 2 and title and title not in ex[tid]:
            ex[tid].append(title)

    for r in _jsonl("history/edu_office_signals.jsonl", "d", s30):
        for tid in (r.get("tp") or tt.classify_topics(r.get("t", ""))):
            add(tid, "교육청 신호", 2, r.get("t", ""))
    for r in _jsonl("history/training_bids.jsonl", "d", s60):
        for tid in tt.classify_topics(r.get("t", "")):
            add(tid, "연수 입찰", 3, r.get("t", ""))
    for r in _jsonl("history/competitor_new_courses.jsonl", "first_seen", s30):
        if r.get("company") == "비바샘연수원":
            continue
        for tid in tt.classify_topics(r.get("title", "")):
            add(tid, "경쟁사 신규", 2, f"[{r.get('company')}] {r.get('title', '')}")
    for f in sorted((HERE / "briefings").glob("*.json"))[-7:]:
        if f.stem < s7:
            continue
        try:
            b = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for s in b.get("sections", []):
            for it in s.get("items", []):
                for tid in tt.classify_topics(it.get("title", "")):
                    add(tid, "조간 지면", 1, it.get("title", ""))
    if not score:
        return _empty()
    P = D.get("topic_partners") or {}
    nxt = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
    rows = []
    for tid, sc in score.most_common(3):
        e = ev[tid]
        rows.append([f"<b>{name.get(tid, tid)}</b>", f"{sc}점", " · ".join(f"{k} {v}" for k, v in e.most_common()),
                     " / ".join(t[:48] for t in ex.get(tid, [])), ", ".join(P.get(tid, ["(후보 발굴 필요)"])), f"{nxt.month}월 정기 라이브"])
    return (_t("", ["주제", "점수", "근거(최근 30~60일)", "근거 예시", "교사단체 후보", "추천 시점"], rows)
            + f"<p style='{NOTE}'>점수 = 연수 입찰×3 + 교육청 신호×2 + 경쟁사 신규 과정×2 + 조간 지면×1. 매 배포 때 다시 계산합니다. 교사단체 후보는 단체명만 둡니다.</p>")


# ---------------------------------------------------------------- ③ 출시 후 90일 노출 캘린더
def _launch_calendar(D, today=None):
    today = today or _today()
    L = D.get("launches") or []
    if not L:
        return _empty()
    med = statistics.median([x["sales"] for x in L if x.get("sales") is not None] or [0])
    top = max((x.get("sales") or 0) for x in L)
    tot = sum((x.get("sales") or 0) for x in L)
    rows, alert = [], 0
    for x in sorted(L, key=lambda x: x.get("launch", "")):
        d0 = _d(x.get("launch", "") + "-01") if len(x.get("launch", "")) == 7 else _d(x.get("launch"))
        if not d0:
            continue
        marks = [("D-7 숏폼", d0 - timedelta(days=7)), ("D-day 라이브", d0), ("D+30 후기", d0 + timedelta(days=30)), ("D+90 판단", d0 + timedelta(days=90))]
        nxt = next(((k, v) for k, v in marks if v >= today), None)
        s = x.get("sales")
        if today >= d0 + timedelta(days=90):
            judge = "유지·확장" if s is not None and s >= med else "노출 부족 — 재노출·리뉴얼 검토"
            alert += judge.startswith("노출")
        else:
            judge = "진행 중"
        rows.append([x.get("launch", ""), f"<b>{x.get('title', '')}</b>", x.get("how", ""), "-" if s is None else f"{s:,}만",
                     f"{nxt[0]} {nxt[1].isoformat()}" if nxt else "90일 경과", judge])
    tiles = _tiles([["기록된 출시 과정", f"{len(rows)}개", "2026 신규 매출 TOP 10부터"],
                    ["상위 1개 의존도", f"{top / tot * 100:.0f}%" if tot else "-", "TOP 10 매출 기준 · 목표 30% 이하"],
                    ["노출 부족 판정", f"{alert}개", f"90일 경과 · 매출 중앙값({med:,.0f}만) 미만"]])
    return (tiles + _t("", ["출시", "과정", "개발", "매출", "다음 노출 일정", "90일 판정"], rows)
            + _box("<b>운영 규칙</b> — 출시 D-7 숏폼 → D-day 실시간 라이브 → D+30 수강 후기·쿠폰 → D+90 매출이 중앙값 미만이면 재노출(라이브 재방송·SET 묶기) 또는 리뉴얼을 결정합니다. 2027 출시 과정은 출시 월을 채팅으로 주시면 일정이 자동으로 생깁니다."))


# ---------------------------------------------------------------- ④ 채널별 성과판
def _channels(D):
    C = D.get("channels") or {}
    M = C.get("months") or []
    known = _t("현재 확인된 마케팅 활동", ["활동", "실적", "비고"], C.get("known") or [])
    if not M:
        return (known + _box("<b>데이터 준비 중</b> — 월별로 '채널(비바샘 / 숏폼·SNS / 교사단체 / 인플루언서 강사 / 이벤트) · 쿠폰 코드 · 신규 수강자 · 재구매 · 매출'을 주시면 "
                             "채널별 유입·전환과 이벤트의 신규 고객 비율을 자동으로 그립니다. 비바샘마케팅과 매월 같은 화면으로 점검하는 용도입니다."))
    by = {}
    for m in M:
        r = by.setdefault(m.get("ch", "기타"), [0, 0, 0])
        r[0] += m.get("new", 0)
        r[1] += m.get("repeat", 0)
        r[2] += m.get("rev", 0)
    rows = [[k, f"{a:,}", f"{b:,}", f"{a / (a + b) * 100:.0f}%" if a + b else "-", f"{c:,}만"] for k, (a, b, c) in sorted(by.items(), key=lambda x: -x[1][2])]
    return known + _t("채널별 누적", ["채널", "신규", "재구매", "신규 비율", "매출"], rows)


# ---------------------------------------------------------------- ⑤ 샘크 성장 사다리
def _samcre(D):
    S = D.get("samcre") or {}
    if not S:
        return _empty()
    T = S.get("types") or []
    rows = [[f"<b>{a}</b>", f"{b}과정", "-" if c is None else f"{c}과정", "-" if c is None else (f"+{c - b}" if c > b else "달성")] for a, b, c in T]
    top = {x["title"] for x in (D.get("launches") or []) if x.get("how") == "샘크"}
    cand = []
    for c in S.get("a_courses") or []:
        tok = c.split()[0]
        hit = len(tok) >= 3 and tok != "AI" and any(tok in t for t in top)
        cand.append(f"{c}{' (매출 TOP 10)' if hit else ''}")
    cand.sort(key=lambda s: "TOP" not in s)
    fun = tp._bars({"h": "강사·교사 공급 경로(명)", "unit": "명", "rows": S.get("funnel") or []})
    return (_tiles([["참여 교사", f"{S.get('teachers', '-')}명", "2026 샘크리에이티브"], ["샘크 과정", f"{S.get('courses', '-')}과정", "A 11 · B 4 · D 1"],
                    ["B형 목표", "4 → 8과정", "A형에서 정기활동 전환"], ["C형 1호", "문해력", "2027 도입 · 추진 중"]])
            + _t("유형별 현황과 2027 목표", ["유형", "2026", "2027 목표(제안)", "남은 차이"], rows)
            + _t("B형 제안 대상 — A형 과정", ["순서", "과정", "제안"], [[i + 1, c, "연 4회 업데이트 계획안 + 인센티브 제안"] for i, c in enumerate(cand)])
            + fun + f"<p style='{NOTE}'>B형 과정: {E(' · '.join(S.get('b_courses') or []))} / C형 추진: {E(' · '.join(S.get('c_pipeline') or []))}. 교사 실명은 저장하지 않습니다.</p>")


# ---------------------------------------------------------------- ⑥ AX 제작 파이프라인
def _pipeline(D, today=None):
    today = today or _today()
    P = D.get("pipeline") or {}
    st, sla, cs = P.get("stages") or [], P.get("sla") or {}, P.get("courses") or []
    if not st:
        return _empty()
    cols, late = [], 0
    for s in st:
        cards = ""
        for c in [c for c in cs if c.get("stage") == s]:
            since = _d(c.get("since"))
            days = (today - since).days if since else 0
            over = s in sla and days > sla[s]
            late += over
            cards += (f"<div style='margin:4px 0;padding:6px 8px;border-radius:6px;background:var(--surface);border:1px solid {'#ef4444' if over else 'var(--border)'};font-size:12px;line-height:1.45;'>"
                      f"{E(c.get('t', ''))}<div style='{NOTE}'>{E(c.get('g', ''))} · {days}일째{' · 기준 초과' if over else ''}</div></div>")
        lim = f" · 기준 {sla[s]}일" if s in sla else ""
        cols.append(f"<div style='min-width:150px;flex:1;padding:8px;border-radius:8px;background:var(--surface-2);'><b style='font-size:12.5px;'>{E(s)}</b>"
                    f"<span style='{NOTE}'>{E(lim)}</span>{cards or f'<div style={chr(39)}{NOTE}{chr(39)}>—</div>'}</div>")
    return (_tiles([["2027 개발 계획", "37과정", "자체 30 · 제휴·CP 7"], ["기준 일수 초과", f"{late}건", "빨간 테두리로 표시"]])
            + "<div style='display:flex;gap:8px;overflow-x:auto;padding-bottom:4px;margin-top:8px;'>" + "".join(cols) + "</div>"
            + f"<p style='{NOTE}'>{E(P.get('note', ''))}</p>")


# ---------------------------------------------------------------- ⑦ 중등 SET 처방
def _set_rx(D):
    R = (D.get("set_compare") or {}).get("rows") or []
    if len(R) < 2:
        return _empty()
    rows = [[f"<b>{a}</b>", f"{n}건", f"{won:,}원", f"{won // n:,}원" if n else "-", m, desc] for a, n, won, m, desc in R]
    comp = Counter()
    sets = Counter()
    try:
        import training_topics as tt
        cat = json.loads((HERE / "history/competitor_course_catalog.json").read_text(encoding="utf-8"))
        for co, v in (cat.get("companies") or {}).items():
            if co == "비바샘연수원":
                continue
            for r in v.get("courses") or []:
                ttl = r.get("title") or ""
                if re.search(r"중등|중학", ttl):
                    for tid in tt.classify_topics(ttl):
                        comp[tid] += 1
                        if re.search(r"SET|세트|상품", (r.get("context") or "") + ttl):
                            sets[tid] += 1
        name = {t[0]: t[1] for t in tt.TOPICS}
    except Exception:  # noqa: BLE001
        name = {}
    crow = [[name.get(k, k), f"{v}개", f"{sets.get(k, 0)}개"] for k, v in comp.most_common(5)]
    rx = [["출시 시점", "중등이 초등보다 3개월 늦게(7월) 출시 — 1학기 수요를 놓침", "2027은 초·중등 동시 출시, 학기 시작 전(2월) 노출"],
          ["주제", "학급운영·사회정서 중심 구성 — 중등은 교과·평가 수요가 큼(경쟁사 중등 과정 주제 참고)", "교과 수업·평가 주제 SET 1종 추가(예: 서·논술형 평가 + 도구 이용권)"],
          ["가격·구성", "건당 매출이 초등의 약 1/8 — 저가 구성 위주로 팔림", "연수+자료(즉시 쓰는 활동지)·연수+연수 묶음 등 2027 신규 유형으로 객단가 회복"]]
    return (_t("초등 vs 중등 SET", ["학교급", "판매", "매출", "건당", "출시", "구성"], rows)
            + (_t("경쟁사 중등 과정 주제 TOP 5", ["주제", "과정 수", "SET·상품 결합"], crow) if crow else "")
            + _t("처방 카드", ["진단", "근거", "처방"], rx))


# ---------------------------------------------------------------- ⑧ 셀 간 공 넘기기
def _handoffs(D):
    H = sorted(D.get("handoffs") or [], key=lambda x: x.get("date", ""), reverse=True)
    if not H:
        return _empty()
    st = Counter(x.get("status", "") for x in H)
    route = Counter(f"{x.get('from', '')} → {x.get('to', '')}" for x in H)
    done = st.get("완료", 0)
    rows = [[x.get("date", ""), f"{x.get('from', '')} → {x.get('to', '')}", x.get("item", ""), f"<b>{x.get('status', '')}</b>", x.get("result", "")] for x in H]
    return (_tiles([["넘긴 일", f"{len(H)}건", " · ".join(f"{k} {v}" for k, v in st.most_common())], ["완료율", f"{done / len(H) * 100:.0f}%", "'연결이 반복 가능한가'의 숫자"],
                    ["가장 많은 경로", route.most_common(1)[0][0], f"{route.most_common(1)[0][1]}건"]])
            + _t("", ["날짜", "경로", "넘긴 일", "상태", "결과"], rows)
            + f"<p style='{NOTE}'>상태: 제안 → 계획 → 진행 → 완료(또는 보류). 셀 사이에 넘긴 일과 결과를 채팅으로 주시면 쌓입니다.</p>")


# ---------------------------------------------------------------- 칸 조립
def build_exec(sec):
    D = load()
    if not D:
        return ""
    return (sec("① 라이브 운영 보드", "회차별 신청 → 참여 → 녹화본 → 자율연수 → 30일 유료 수강. 2026 기준선과 자동 비교.", _live_board(D))
            + sec("② 라이브 주제 추천기", "교육청 신호·연수 입찰·경쟁사 신규 과정·조간 지면에서 다음 달 라이브 주제 3개", _topic_reco(D))
            + sec("⑤ 샘크리에이티브 성장 사다리", "A형 → B·C형 전환 후보와 2027 목표", _samcre(D))
            + sec("⑥ AX 제작 파이프라인", "37과정이 5단계 중 어디에 있는지, 기준 일수를 넘긴 과정", _pipeline(D))
            + sec("⑦ 중등 SET 처방", "초등 40건 vs 중등 22건 — 원인과 재구성안", _set_rx(D)))


def build_mkt(sec):
    D = load()
    if not D:
        return sec("마케팅 보드", "", _empty())
    return (sec("③ 출시 후 90일 노출 캘린더", "D-7 숏폼 → D-day 라이브 → D+30 후기 → D+90 판단 · 매출 쏠림 경보", _launch_calendar(D))
            + sec("④ 채널별 성과판", "채널·쿠폰 코드별 신규/재구매와 전환 — 비바샘마케팅과 월간 점검용", _channels(D)))


def build_handoff(sec):
    D = load()
    if not D:
        return ""
    return sec("⑧ 셀 간 공 넘기기", "1셀 ↔ 2셀 ↔ 샘브릿지 사이에 넘긴 일과 결과", _handoffs(D))


def build_actions(sec):
    D = load()
    if not D:
        return ""
    T = live_todos(D)
    body = (_t("", ["기한", "라이브", "할 일", "상태"], [[d.isoformat(), t, w, f"<b>{s}</b>"] for d, t, w, s in T]) if T
            else _empty("최근 40일 안에 끝났거나 2주 안에 열릴 라이브가 없습니다. 라이브 일정을 채팅으로 주시면 후속 할 일이 자동으로 생깁니다."))
    return sec("라이브 후속 할 일", "라이브 운영 보드에서 자동 생성 — 녹화본 공개·쿠폰·후속 초대·30일 유료 집계", body)
