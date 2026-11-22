#!/usr/bin/env python3
"""
관리 탭 '📊 사용 KPI' 칸(사용자 승인 2026-11-22 "5번 진행") — 대시보드가 실제로 쓰이는지 KPI 로 본다.
- 데이터: PostHog 의 'tab_view'(탭·관리 칸 이름) · 'feature_use'(기능 이름) 이벤트. 이메일·이름·입력값·화면 녹화 없음, 임시 세션 번호만.
- 조회 키: POSTHOG_PERSONAL_API_KEY(읽기 전용) + POSTHOG_PROJECT_ID (시크릿, 로그에는 설정 여부만). 무료 요금제 안(조회 4번/배포).
- 결과 HTML 은 관리 탭 암호문 안에만(ADMIN_PASSWORD). 외부 텍스트는 모두 escape.
판단 규칙: 28일 조회 0 = 정리 후보, 상위 5 = 키울 후보(첫 화면 배치), 직전 28일 대비 증감.
"""
import json
import os
import re
import urllib.request
from html import escape as h
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
ADM_TRACK_START = date(2026, 11, 22)  # 관리 칸·기능 측정 시작일 — 28일이 지나기 전엔 0회를 정리 후보로 판정하지 않는다
API = "https://us.posthog.com/api/projects/{}/query/"
FEAT_NAME = {"export_png": "그림 저장(PNG)", "export_excel": "표 저장(엑셀)", "watch_add": "관심 기관 추가", "listen_morning": "조간 듣기",
             "treemap_zoom": "트리맵 확대", "race_play": "막대 레이스 재생", "territory_play": "영토 지도 재생", "table_view": "표로 보기",
             "summary_more": "한눈에 보기 → 자세히", "bid_compare_open": "공고 비교 창 열기", "region_filter": "지역 필터", "map_drill": "지도 드릴다운",
             "farm_dex": "텃밭 도감", "time_travel": "시간 여행", "revenue_sim": "매출 시뮬레이터", "cpx_filter": "연동 필터(지역·기간·비교)"}


def _q(sql):
    key, pid = os.environ.get("POSTHOG_PERSONAL_API_KEY", "").strip(), os.environ.get("POSTHOG_PROJECT_ID", "").strip()
    if not (key and pid.isdigit()):
        return None
    body = json.dumps({"query": {"kind": "HogQLQuery", "query": sql}}).encode()
    req = urllib.request.Request(API.format(pid), data=body, method="POST", headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode()).get("results") or []


def load():
    """None = 조회 키 없음. 실패 시 {'error': 종류}."""
    try:
        tabs = _q("SELECT properties.tab AS tab, countIf(timestamp > now() - INTERVAL 28 DAY) AS v, "
                  "countIf(timestamp <= now() - INTERVAL 28 DAY) AS pv, count(DISTINCT if(timestamp > now() - INTERVAL 28 DAY, properties.sid, NULL)) AS s "
                  "FROM events WHERE event = 'tab_view' AND timestamp > now() - INTERVAL 56 DAY GROUP BY tab ORDER BY v DESC LIMIT 120")
        if tabs is None:
            return None
        weeks = _q("SELECT toStartOfWeek(timestamp, 1) AS w, count(DISTINCT properties.sid) AS s, count() AS v FROM events "
                   "WHERE event = 'tab_view' AND timestamp > now() - INTERVAL 63 DAY GROUP BY w ORDER BY w")
        feats = _q("SELECT properties.f AS f, count() AS n FROM events WHERE event = 'feature_use' AND timestamp > now() - INTERVAL 28 DAY GROUP BY f ORDER BY n DESC LIMIT 40")
        return {"tabs": [{"tab": str(a or "-"), "v": int(b), "pv": int(c), "s": int(d)} for a, b, c, d in tabs],
                "weeks": [{"w": str(a)[:10], "s": int(b), "v": int(c)} for a, b, c in weeks or []],
                "feats": [{"f": str(a or "-"), "n": int(b)} for a, b in feats or []]}
    except Exception as e:  # noqa: BLE001 — 값·키는 출력하지 않는다
        print("사용 KPI 조회 실패:", type(e).__name__)
        return {"error": type(e).__name__}


def catalog():
    """화면에 실제로 있는 탭·관리 칸 목록(이름) — 0회 조회 판정용."""
    cp, adm = {}, {}
    try:
        t = (HERE / "dashboard_template.html").read_text(encoding="utf-8")
        for k, lab in re.findall(r'class="tabbtn"[^>]*data-tab="([a-z0-9_]+)"[^>]*>([^<]{1,40})<', t):
            cp[k] = lab.strip()
    except OSError:
        pass
    try:
        s = (HERE / "admin_structure.py").read_text(encoding="utf-8")
        m = re.search(r"panes = \[(.*?)\]\n", s)
        for k, lab in re.findall(r'\("([a-z0-9_]+)", "([^"]+)"\)', m.group(1) if m else ""):
            adm[k] = lab
    except OSError:
        pass
    return cp, adm


def build(sec=None, data="__load__"):
    U = load() if data == "__load__" else data
    if U is None:
        return '<div class="cpv-wrap"><p class="cpv-note">데이터 준비 중 — 사용 분석 조회 키가 등록되면 표시됩니다.</p></div>'
    if U.get("error"):
        return f'<div class="cpv-wrap"><p class="cpv-note">사용 KPI 조회 오류({h(U["error"])}) — 다음 배포 때 다시 시도합니다.</p></div>'
    cp, adm = catalog()
    rows = U.get("tabs") or []
    seen = {r["tab"]: r for r in rows}
    tot = sum(r["v"] for r in rows) or 1
    weeks = U.get("weeks") or []
    last_w = weeks[-1]["s"] if weeks else 0
    prev_w = weeks[-2]["s"] if len(weeks) > 1 else 0
    sess28 = max((r["s"] for r in rows), default=0)
    per = round(tot / max(sum(w["s"] for w in weeks[-4:]) or 1, 1), 1)
    adm_v = sum(r["v"] for r in rows if r["tab"].startswith("adm:"))
    name = lambda k: (adm.get(k[4:], k[4:]) if k.startswith("adm:") else cp.get(k, k))

    def kpi(lab, val, sub, good=None):
        c = "" if good is None else (' style="color:var(--own)"' if good else ' style="color:var(--rival)"')
        return f'<div class="uk-k"><small>{h(lab)}</small><b{c}>{h(val)}</b><span>{h(sub)}</span></div>'
    k = (kpi("주간 활성 세션", f"{last_w:,}", f"전주 {prev_w:,}", last_w >= prev_w)
         + kpi("28일 조회", f"{tot:,}", f"직전 28일 {sum(r['pv'] for r in rows):,}", tot >= sum(r['pv'] for r in rows))
         + kpi("세션당 화면 수", f"{per}", "4주 평균")
         + kpi("관리 칸 조회", f"{adm_v:,}", f"전체의 {adm_v * 100 // tot}%"))
    mx = max((w["s"] for w in weeks), default=1) or 1
    trend = "".join(f'<div class="uk-w"><i style="height:{max(3, w["s"] / mx * 70):.0f}px"></i><small>{h(w["w"][5:])}</small><b>{w["s"]}</b></div>' for w in weeks[-9:])
    top = sorted(rows, key=lambda r: -r["v"])[:8]
    top_html = "".join(f'<tr><td>{h(name(r["tab"]))}</td><td class="num">{r["v"]:,}</td><td class="num">{r["v"] * 100 // tot}%</td>'
                       f'<td class="num">{("+" if r["v"] >= r["pv"] else "")}{r["v"] - r["pv"]:,}</td><td class="num">{r["s"]:,}</td></tr>' for r in top)
    warm = date.today() >= ADM_TRACK_START + timedelta(days=28)
    dead = [f"{lab}" for key, lab in cp.items() if seen.get(key, {}).get("v", 0) == 0] + ([f"관리 · {lab}" for key, lab in adm.items() if key != "home" and seen.get("adm:" + key, {}).get("v", 0) == 0] if warm else [])
    drop = [name(r["tab"]) for r in rows if r["pv"] >= 10 and r["v"] < r["pv"] * .5]
    feats = U.get("feats") or []
    fx = max((f["n"] for f in feats), default=1) or 1
    feat_html = "".join(f'<div class="uk-f"><span>{h(FEAT_NAME.get(f["f"], f["f"]))}</span><i><b style="width:{f["n"] / fx * 100:.0f}%"></b></i><em>{f["n"]:,}</em></div>' for f in feats[:14]) \
        or '<p class="cpv-note">아직 기능 사용 기록이 없습니다(기능 측정은 2026-11-22 시작).</p>'
    unused_f = [v for kf, v in FEAT_NAME.items() if kf not in {f["f"] for f in feats}]
    rec = []
    if top:
        rec.append(f"키울 후보(첫 화면 배치): {', '.join(name(r['tab']) for r in top[:3])}")
    if dead:
        rec.append(f"정리 후보(28일 조회 0): {', '.join(dead[:8])}{' 외 ' + str(len(dead) - 8) + '개' if len(dead) > 8 else ''} — 합치거나 다른 칸 안으로 옮기기")
    if drop:
        rec.append(f"관심 급감(직전 대비 절반 이하): {', '.join(drop[:5])} — 내용이 낡았는지 점검")
    if not warm:
        rec.append(f"관리 칸·기능 사용은 {ADM_TRACK_START.month}월 {ADM_TRACK_START.day}일부터 측정 — {(ADM_TRACK_START + timedelta(days=28)).isoformat()} 이후 정리 후보 판정에 포함")
    if unused_f and warm:
        rec.append(f"안 쓰이는 기능: {', '.join(unused_f[:6])} — 회의·온보딩에서 한 번 시연")
    rec_html = "".join(f"<li>{h(x)}</li>" for x in rec)
    return (f'<div class="cpv-wrap"><div class="cpv-grid">'
            f'<section class="cpv-card"><header><span class="cpv-ic">📊</span><div><b>대시보드 사용 KPI</b><small>최근 28일 · 개인정보 없이 화면·기능 이름만</small></div></header>'
            f'<div class="uk-ks">{k}</div><div class="uk-ws" aria-label="주별 활성 세션">{trend}</div>'
            f'<div class="br-out"><p><strong>이번 달 정리·강화 제안</strong></p><ul class="qa-h">{rec_html}</ul></div></section>'
            f'<section class="cpv-card"><header><span class="cpv-ic">🏆</span><div><b>많이 본 화면 TOP 8</b><small>조회 · 비중 · 직전 28일 대비 · 세션</small></div></header>'
            f'<div class="tbl-wrap"><table class="data"><thead><tr><th>화면</th><th class="num">조회</th><th class="num">비중</th><th class="num">증감</th><th class="num">세션</th></tr></thead><tbody>{top_html}</tbody></table></div></section>'
            f'<section class="cpv-card"><header><span class="cpv-ic">🧰</span><div><b>기능 사용</b><small>세션당 1회로 센 기능별 사용 수</small></div></header>{feat_html}</section>'
            f'</div></div>')


if __name__ == "__main__":
    demo = {"tabs": [{"tab": "g2bfull", "v": 120, "pv": 90, "s": 40}, {"tab": "market", "v": 60, "pv": 70, "s": 25}, {"tab": "adm:salesx", "v": 15, "pv": 0, "s": 5},
                     {"tab": "competitor", "v": 4, "pv": 20, "s": 3}],
            "weeks": [{"w": "2026-10-05", "s": 10, "v": 40}, {"w": "2026-10-12", "s": 14, "v": 55}, {"w": "2026-11-16", "s": 18, "v": 70}],
            "feats": [{"f": "export_png", "n": 6}, {"f": "listen_morning", "n": 3}]}
    print(len(build(data=demo)))
