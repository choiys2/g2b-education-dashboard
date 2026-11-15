#!/usr/bin/env python3
"""
수행기관 모니터링 (2026-11-15 사용자 결정: 원자료 CP '기업·대학 트렌드 2027' 탭 + 해석 🔒 관리 '교육청 인사이트', CP 에도 그룹 표시)

  대상(그룹): 비상 컨소 파트너(한국능률협회·알파코·KTcs·엘리스) · 교과서사(천재교육·창비교육) · 평생교육(SLI 평생교육원)
              · 연수원 경쟁사(티처빌·아이스크림) · 기업(네패스·팀모노리스)
  데이터(추가 조회 없음, 비용 0):
    - 나라장터 낙찰·계약: competitor_g2b_export / competitor_contract_export 가 이미 받는 조회 결과에서 낙찰·계약 업체명이
      아래 별칭과 맞는 건만 history/org_watch.jsonl 에 누적(기존 4개사 경쟁 매트릭스와 섞지 않음)
    - KERIS 입찰 참가·낙찰: history/keris_procurement.json(참가 업체 전체가 이미 있음)
    - 뉴스: history/partner_news.json(industry_trend_2027.json scrap_targets.company 에 검색어 추가 → 주 1회)
    - 교육청 정책 신호: history/edu_office_signals.jsonl 기사 제목에 기관명이 나오는 건
  지역·대학 연계: 발주기관(시도교육청·교육지원청·대학 산학협력단)과 기사 제목 속 시도·대학명으로 판정.
"""
import html
import json
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
E = html.escape
OUT = HERE / "history" / "org_watch.jsonl"
NOTE = "color:var(--muted);font-size:12.5px;"

GROUPS = ["비상 컨소 파트너", "교과서사", "평생교육", "연수원 경쟁사", "기업"]
GROUP_COLOR = {"비상 컨소 파트너": "#8b5cf6", "교과서사": "#f59e0b", "평생교육": "#10b981", "연수원 경쟁사": "#ef4444", "기업": "#3b82f6"}
# 이름: (그룹, 나라장터 법인명 별칭, 뉴스 검색어)
WATCH = {
    "한국능률협회": ("비상 컨소 파트너", ["한국능률협회"], "한국능률협회"),
    "알파코": ("비상 컨소 파트너", ["알파코"], "알파코"),
    "KTcs": ("비상 컨소 파트너", ["케이티씨에스", "KTcs", "케이티 씨에스"], "KTcs"),
    "엘리스": ("비상 컨소 파트너", ["엘리스그룹", "엘리스 그룹"], "엘리스그룹"),
    "천재교육": ("교과서사", ["천재교육", "천재교과서"], "천재교육"),
    "창비교육": ("교과서사", ["창비교육"], "창비교육"),
    "SLI 평생교육원": ("평생교육", ["SLI평생교육원", "SLI 평생교육원", "에스엘아이"], "에스엘아이평생교육원"),
    "티처빌": ("연수원 경쟁사", ["테크빌교육"], "티처빌"),
    "아이스크림": ("연수원 경쟁사", ["아이스크림미디어", "아이스크림에듀"], "아이스크림미디어"),
    "네패스": ("기업", ["네패스"], "네패스"),
    "팀모노리스": ("기업", ["팀모노리스"], "팀모노리스"),
}
SIDO = [("서울", r"서울"), ("부산", r"부산"), ("대구", r"대구"), ("인천", r"인천"), ("광주", r"광주"), ("대전", r"대전"), ("울산", r"울산"),
        ("세종", r"세종"), ("경기", r"경기"), ("강원", r"강원"), ("충북", r"충북|충청북"), ("충남", r"충남|충청남"), ("전북", r"전북|전라북"),
        ("전남", r"전남|전라남"), ("경북", r"경북|경상북"), ("경남", r"경남|경상남"), ("제주", r"제주")]
UNIV_RE = re.compile(r"([가-힣]{2,14}(?:대학교|교육대|교대|대학))")
EDU_RE = re.compile(r"교육청|교육지원청|교육연수원|교육원")
_BUF = {}


def match(name):
    s = name or ""
    for k, (_, aliases, _) in WATCH.items():
        if any(a in s for a in aliases):
            return k
    return None


def sido_of(text):
    for n, rx in SIDO:
        if re.search(rx, text or ""):
            return n
    return ""


def collect(rec):
    """수집기에서 호출: rec = {k, org(감시 기관), kind('win'|'contract'), t, buyer, region, amount, date}"""
    if rec.get("org") and rec.get("k"):
        _BUF[rec["kind"] + ":" + rec["k"]] = rec


def save():
    """수집기 끝에서 호출: 누적 파일에 새 건만 추가(키 기준)."""
    if not _BUF:
        return 0
    old = {}
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                old[r["kind"] + ":" + r["k"]] = r
    n = sum(1 for k in _BUF if k not in old)
    old.update(_BUF)
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in sorted(old.values(), key=lambda r: r.get("date") or "")), encoding="utf-8")
    print(f"수행기관 모니터링: 신규 {n}건 · 누적 {len(old)}건")
    _BUF.clear()
    return n


def _jsonl(p):
    f = HERE / p
    if not f.exists():
        return []
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]


def _j(p, d=None):
    try:
        return json.loads((HERE / p).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return d


def gather():
    """기관별 낙찰·계약(나라장터) + KERIS 참가·낙찰 + 뉴스 + 정책 신호."""
    rec = defaultdict(lambda: {"g2b": [], "keris": [], "news": [], "signals": []})
    for r in _jsonl("history/org_watch.jsonl"):
        rec[r["org"]]["g2b"].append(r)
    K = _j("history/keris_procurement.json", {}) or {}
    bids, awards = K.get("bids") or {}, K.get("awards") or {}
    for key, ps in (K.get("participants") or {}).items():
        b = bids.get(key) or awards.get(key) or {}
        univ_in = sorted({UNIV_RE.search(p.get("corp") or "").group(1) for p in ps if UNIV_RE.search(p.get("corp") or "")})
        for p in ps:
            o = match(p.get("corp"))
            if o:
                rec[o]["keris"].append({"d": b.get("d") or "", "t": b.get("t") or "", "rank": p.get("rank"), "amt": p.get("amt"),
                                        "win": p.get("rank") == 1, "univ": [u for u in univ_in if u not in (p.get("corp") or "")]})
    PN = (_j("history/partner_news.json", {}) or {}).get("items") or {}
    for o, (_, _, q) in WATCH.items():
        for it in (PN.get(q) or PN.get(o) or {}).get("items", []):  # 검색어를 바꿔도 이전 수집분은 이름으로 찾는다
            t = it.get("t") or ""
            rec[o]["news"].append({"d": it.get("d") or "", "t": t, "u": it.get("u") or "", "src": it.get("src") or "",
                                   "sido": sido_of(t),
                                   "univ": (UNIV_RE.search(t).group(1) if UNIV_RE.search(t) else ""),
                                   "mou": bool(re.search(r"협약|MOU|업무협약|맞손|손잡|협력", t))})
    for r in _jsonl("history/edu_office_signals.jsonl"):
        for o, (_, aliases, q) in WATCH.items():
            if any(a in (r.get("t") or "") for a in aliases + [o, q]):
                rec[o]["signals"].append({"d": r.get("d"), "s": r.get("s"), "t": r.get("t"), "u": r.get("u")})
    return rec


def build_cp():
    """CP 원자료(그룹 표시 포함, 해석 없음)."""
    rec = gather()
    orgs = []
    for o, (g, _, _) in WATCH.items():
        r = rec.get(o) or {"g2b": [], "keris": [], "news": [], "signals": []}
        yr = (date.today() - timedelta(days=365)).isoformat()
        g2 = [x for x in r["g2b"] if (x.get("date") or "") >= yr]
        regions = Counter(x.get("region") or "전국" for x in r["g2b"])
        univ = sorted({u for k in r["keris"] for u in k["univ"]} | {n["univ"] for n in r["news"] if n["univ"]})
        orgs.append({"name": o, "group": g, "g2b_n": len(g2), "g2b_amt": sum(int(float(x.get("amount") or 0)) for x in g2),
                     "keris_n": len(r["keris"]), "keris_win": sum(1 for k in r["keris"] if k["win"]),
                     "news_n": len(r["news"]), "mou_n": sum(1 for n in r["news"] if n["mou"]),
                     "regions": dict(regions), "news_regions": dict(Counter(n["sido"] for n in r["news"] if n["sido"])),
                     "univ": univ[:8],
                     "recent": sorted(([{"d": x.get("date"), "t": x.get("t"), "w": x.get("buyer"), "k": "낙찰" if x["kind"] == "win" else "계약", "a": x.get("amount")} for x in r["g2b"]]
                                       + [{"d": k["d"], "t": k["t"], "w": "KERIS", "k": "KERIS 낙찰" if k["win"] else "KERIS 참가", "a": k.get("amt")} for k in r["keris"]]),
                                      key=lambda x: x["d"] or "", reverse=True)[:5],
                     "news": sorted(r["news"], key=lambda n: n["d"], reverse=True)[:4],
                     "signals": r["signals"][-3:]})
    sidos = [n for n, _ in SIDO]
    return {"available": True, "groups": GROUPS, "colors": GROUP_COLOR, "sidos": sidos, "orgs": orgs,
            "news_updated": (_j("history/partner_news.json", {}) or {}).get("generated")}


def build_admin(sec):
    D = build_cp()
    O = D["orgs"]
    if not any(o["g2b_n"] or o["keris_n"] or o["news_n"] for o in O):
        return sec("수행기관 × 지역·대학 연계 분석", "낙찰·KERIS·뉴스 데이터가 쌓이면 채워집니다.", "")
    # 시도별 우세 기관
    by_sido = defaultdict(Counter)
    for o in O:
        for s, n in o["regions"].items():
            by_sido[s][o["name"]] += n
        for s, n in o["news_regions"].items():
            by_sido[s][o["name"]] += n * 0.5
    rows = []
    for s in D["sidos"]:
        c = by_sido.get(s)
        if not c:
            continue
        top = c.most_common(3)
        rows.append([f"<b>{E(s)}</b>", " · ".join(f"{E(k)} {v:g}" for k, v in top),
                     E(", ".join(sorted({WATCH[k][0] for k, _ in top})))])
    t1 = ("<div class='tbl-wrap'><table><thead><tr><th>시도</th><th>활동 상위 기관(낙찰 1 · 기사 0.5)</th><th>그룹</th></tr></thead><tbody>"
          + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) + "</tbody></table></div>") if rows else f"<p style='{NOTE}'>지역 데이터 없음</p>"
    part = [o for o in O if o["group"] == "비상 컨소 파트너"]
    solo = [o["name"] for o in part if o["g2b_n"] or o["keris_win"]]
    univ_links = [(o["name"], u) for o in O for u in o["univ"]]
    mou = [o["name"] for o in O if o["mou_n"]]
    rival = [o for o in O if o["group"] == "연수원 경쟁사"]
    body = (t1 + "<h4>대학 연계</h4>"
            + ("<ul style='font-size:13px;margin:4px 0 0 16px;'>" + "".join(f"<li><b>{E(a)}</b> ↔ {E(b)}</li>" for a, b in univ_links[:14]) + "</ul>"
               if univ_links else f"<p style='{NOTE}'>대학과 함께 참가·보도된 건이 아직 없습니다.</p>")
            + (f"<p style='{NOTE}margin-top:6px;'>컨소 파트너·교과서사·기업의 나라장터 낙찰·계약은 이번 주부터 쌓입니다(과거분 채우기 전이라 지역 표가 연수원 경쟁사 중심으로 보일 수 있음).</p>"
               if not any(o["g2b_n"] for o in O if o["group"] != "연수원 경쟁사") else "")
            + "<div style='margin-top:10px;padding:10px 12px;border-left:3px solid var(--accent);background:var(--surface-2);border-radius:6px;font-size:13px;'>"
            f"<b>해석</b> — ① 비상 컨소 파트너 중 <b>{E(' · '.join(solo) or '없음')}</b>은(는) 자체 수주·낙찰 이력이 있어, 다음 컨소에서는 역할 분담(콘텐츠 vs 운영·플랫폼)을 먼저 정하고 경쟁 구도가 되는 지역을 피해 묶는 것이 유리합니다. "
            f"② 협약·MOU 보도가 있는 기관: <b>{E(' · '.join(mou) or '없음')}</b> — 해당 시도·대학은 이미 선점된 관계이므로, 우리는 교원양성대학(교대) 자원이나 교과서 채택 학교 네트워크처럼 다른 연결고리로 접근합니다. "
            f"③ 연수원 경쟁사의 최근 1년 낙찰·계약 {sum(o['g2b_n'] for o in rival)}건은 시도교육청 원격연수 중심 — 지역 표에서 경쟁사만 있는 시도는 컨소 파트너와 공동 제안 후보입니다.</div>")
    return sec("수행기관 × 지역·대학 연계 분석", "컨소 파트너·교과서사·평생교육·연수원 경쟁사·기업이 어느 시도·대학과 연결되는지(낙찰·KERIS·기사)와 대응 방향. 매 배포 갱신.", body)


if __name__ == "__main__":
    d = build_cp()
    for o in d["orgs"]:
        print(o["group"], o["name"], "g2b", o["g2b_n"], "keris", o["keris_n"], o["keris_win"], "news", o["news_n"], "univ", o["univ"][:3])
