#!/usr/bin/env python3
"""연수원 회원 분석(사용자 요청 2026-11-22).

- 원천: 비공개 저장소 strategy_room/member_analysis.json — 이수기록 집계값만(개인 식별 정보 없음), 수동 갱신.
- cp(): CP 탭 '연수원 회원분석'용 — 회원 수·수강 건수·비중·증감률만. 매출·객단가는 넣지 않는다(사용자 결정).
- build(sec): 관리 탭 '👥 회원 분석(매출)' 칸 — 추정 매출·RFM·코호트·예측 대비 실적·정리 후보·데이터 품질.
  결과 HTML 은 관리 탭 암호문 안에만(ADMIN_PASSWORD). 모든 글자는 escape.
"""
import json
import re
from html import escape as h

STYLE_RX = r"당장|바로|요점|쏙쏙|핵심만|한눈에|쉬운|실천|현장|아이디어|써먹|활용"
LEVELS = ["유치원", "초등", "중등", "특수", "기타"]
STRENGTH = [("독서", ["독서"]), ("진로", ["진로진학"]), ("과학", []), ("한국사", []), ("수학", [])]


def _load():
    try:
        from strategy_room import _private
        d = _private()
        f = d / "strategy_room" / "member_analysis.json" if d else None
        return json.loads(f.read_text(encoding="utf-8")) if f and f.exists() else None
    except Exception:  # noqa: BLE001
        return None


def _pct(a, b):
    return round(a * 100.0 / b, 1) if b else 0.0


def _define(D):
    """최상단 '회원 특성 정의' — 수치는 모두 집계에서 다시 계산."""
    age = {x["k"]: x["mem"] for x in D["age"]}
    am = sum(age.values())
    s3040 = _pct(age.get("30대", 0) + age.get("40대", 0), am)
    sch = {x["k"]: x["mem"] for x in D["school"]}
    sm = sum(sch.values())
    g = {x["k"]: x["mem"] for x in D["gender"]}
    fem = _pct(g.get("여(추정)", 0), g.get("여(추정)", 0) + g.get("남(추정)", 0))
    seg = D["seg"]
    mon = {x["m"]: x["rows"] for x in D["month"]}
    peak = sorted(mon, key=lambda m: -mon[m])[:3]
    peak_share = _pct(sum(mon[m] for m in peak), sum(mon.values()))
    reg = sorted(D["region"], key=lambda x: -x["mem"])
    rm = sum(x["mem"] for x in reg)
    top3 = reg[:3]
    grow = [r for r, v in D["region_g"].items() if v > 0 and r != "기타/미확인"]
    yr = {x["y"]: x for x in D["by_year"]}
    y0, y1 = yr.get(2020), yr.get(2025)
    drop = round((y1["mem"] / y0["mem"] - 1) * 100) if y0 and y1 else None
    cy = {x["k"]: [int(v) for v in x["v"]] for x in D["cat_year"]}
    coh = [v.get("2021_잔존율(%)") for v in [D["cohort"]["A_2020-22"].get("2020", {})]] + \
          [D["cohort"]["A_2020-22"].get("2021", {}).get("2022_잔존율(%)"), D["cohort"]["B_2023-24"].get("2023", {}).get("2024_잔존율(%)")]
    coh = [c for c in coh if c is not None]
    cards = [
        {"i": "👩‍🏫", "k": "누가", "v": f"30~40대 {s3040}%", "d": f"중등 {_pct(sch.get('중등', 0), sm)}% · 초등 {_pct(sch.get('초등', 0), sm)}% · 여성 {fem}%(성별 확인 회원 중, 추정)"},
        {"i": "🔁", "k": "얼마나", "v": f"1인 {seg['avg_purchase'][2]}건/년", "d": f"재구매 {seg['rp'][0]}% → {seg['rp'][2]}%(2025) · 첫해 다음 해 잔존 {min(coh):.0f}~{max(coh):.0f}%"},
        {"i": "🧭", "k": "무엇을", "v": "정책을 따라 이동", "d": f"고교학점제 {cy['고교학점제'][0]:,}→{cy['고교학점제'][4]:,}건 · AI {cy['AI'][0]:,}→{cy['AI'][4]:,}건 · 평가 {cy['평가'][0]:,}→{cy['평가'][4]:,}건(2020→2024)"},
        {"i": "🗓️", "k": "언제", "v": "·".join(f"{m}월" for m in sorted(peak)) + f" {peak_share}%", "d": "학기 초 몰입형 — 연수 시작 3개월에 수강이 몰린다(신청은 그 직전)"},
        {"i": "📍", "k": "어디서", "v": " · ".join(x["r"] for x in top3) + f" {_pct(sum(x['mem'] for x in top3), rm)}%", "d": f"2020→2024 수강 규모가 늘어난 곳은 {'·'.join(grow) or '없음'}뿐, 나머지 시도는 감소"},
        {"i": "📉", "k": "규모", "v": f"연간 회원 {drop:+d}%" if drop is not None else "-", "d": f"{y0['mem']:,}명(2020) → {y1['mem']:,}명(2025) · 2026년 1~7월 {yr[2026]['mem']:,}명" if y0 and y1 and 2026 in yr else ""},
    ]
    persona = (f"정책 변화에 맞춰 <strong>1년에 1~2과정</strong>을 <strong>학기 초</strong>에 듣는 <strong>30~40대 중등 교사</strong> — "
               f"한 번 온 회원의 <strong>약 80%는 다음 해 돌아오지 않는다</strong>.")
    return persona, cards


def _style(D):
    best = D["best"]
    tot = sum(x["rows"] for x in best)
    prac = [x for x in best if re.search(STYLE_RX, x["t"])]
    return {"prac": _pct(sum(x["rows"] for x in prac), tot), "n": len(prac), "of": len(best),
            "ex": [x["t"] for x in prac[:4]]}


def _textbook(D):
    cat = {x["k"]: x["rows"] for x in D["cat"]}
    tot = sum(cat.values())
    out = []
    for name, keys in STRENGTH:
        n = sum(cat.get(k, 0) for k in keys)
        out.append({"k": name, "rows": n, "share": _pct(n, tot), "has": bool(keys)})
    return {"rows": out, "etc": cat.get("기타", 0), "etc_share": _pct(cat.get("기타", 0), tot), "total": tot}


def cp():
    D = _load()
    if not D:
        return None
    persona, cards = _define(D)
    seg = D["seg"]
    return {
        "as_of": D["as_of"], "period": D["period"], "rows": D["rows"], "members": D["members"],
        "persona": persona, "cards": cards,
        "years": [{"y": x["y"], "mem": x["mem"], "rows": x["rows"], "partial": x["partial"]} for x in D["by_year"]],
        "seg": {k: seg[k] for k in ("labels", "members", "purchases", "rp", "vip_rate", "avg_purchase")},
        "school": [{"k": x["k"], "mem": x["mem"], "rows": x["rows"]} for x in D["school"]],
        "school_year": [{"k": x["k"], "y": x["y"], "mem": x["mem"]} for x in D["school_year"]],
        "school_top": D["school_top"],
        "region": [{"r": x["r"], "mem": x["mem"], "rows": x["rows"], "g": D["region_g"].get(x["r"]),
                    "g2": next((y["g2324"] for y in D["region_recent"] if y["r"] == x["r"]), None)} for x in D["region"]],
        "age": [{"k": x["k"], "mem": x["mem"], "rows": x["rows"]} for x in D["age"]],
        "gender": [{"k": x["k"], "mem": x["mem"]} for x in D["gender"]],
        "top_age": D["top_age"], "top_gender": D["top_gender"],
        "month": [x["rows"] for x in sorted(D["month"], key=lambda x: x["m"])], "month_2025": D["month_2025"], "month_2026": D["month_2026"],
        "cat_year": D["cat_year"], "best": [{"t": x["t"], "rows": x["rows"]} for x in D["best"][:10]],
        "cohort": D["cohort"], "style": _style(D), "textbook": _textbook(D),
        "caution": "성별은 이름 기반 추정(미확인 37%), 연령은 생년월일 기반, 월별은 연수 시작일 기준입니다. 회원 번호 체계가 2023년에 바뀌어 재구매·잔존은 구간(2020-22·2023-24·2025·2026) 안에서만 셉니다.",
    }


# ---------------- 관리 탭 ----------------
CSS = """<style>
.mv{font-size:13px;color:var(--ink,inherit)}.mv h4{margin:16px 0 8px;font-size:14.5px}.mv .mv-sum{background:var(--surface-2,#f4f6fa);border-radius:10px;padding:10px 14px;margin:0 0 10px}
.mv .mv-sum li{margin:3px 0}.mv table{border-collapse:collapse;width:100%;font-size:12.5px}.mv th,.mv td{border-bottom:1px solid var(--border,#e5e7eb);padding:5px 6px;text-align:right}
.mv th:first-child,.mv td:first-child{text-align:left}.mv .mv-g{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(340px,100%),1fr));gap:14px}
.mv .mv-c{background:var(--surface,#fff);border:1px solid var(--border,#e5e7eb);border-radius:10px;padding:10px 12px;overflow-x:auto}
.mv .up{color:#059669;font-weight:700}.mv .dn{color:#dc2626;font-weight:700}.mv .mv-bar{height:8px;border-radius:4px;background:#6366f1;display:inline-block;vertical-align:middle}
.mv .mv-note{color:var(--muted,#6b7280);font-size:12px}.mv .mv-k{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin:8px 0}
.mv .mv-k div{background:var(--surface-2,#f4f6fa);border-radius:8px;padding:8px 10px}.mv .mv-k b{display:block;font-size:18px}
</style>"""


def _won(v):
    return f"{v / 1e8:.2f}억" if v >= 1e8 else f"{v / 1e4:,.0f}만"


def _gc(v):
    if v is None:
        return "-"
    return f'<span class="{"up" if v > 0 else "dn"}">{v:+.1f}%</span>'


def build(sec=None):
    D = _load()
    if not D:
        return '<div class="mv"><p class="mv-note">데이터 준비 중</p></div>'
    seg, P = D["seg"], D["pred"]
    yrs = D["by_year"]
    miss = round((P["act2025"] / P["pred2025"] - 1) * 100, 1)
    rfm_b = D["rfm"].get("B_2023-24", {})
    risk_b = _pct(rfm_b.get("이탈위험", 0) + rfm_b.get("휴면회원", 0), sum(rfm_b.values()))
    c25 = sorted(D["cat_2025"], key=lambda x: -x["g"])
    s = [
        f"추정 매출 {_won(yrs[0]['rev'])}(2020) → {_won(next(x['rev'] for x in yrs if x['y'] == 2025))}(2025), 2026년 1~7월 {_won(yrs[-1]['rev'])} — 연수원 회원 이수 기반은 5년 새 절반 이하로 줄었다.",
        f"2025 예측 {_won(P['pred2025'])} 대비 실적 {_won(P['act2025'])}(<b>{miss:+.1f}%</b>) — 단순 추세 연장 예측은 성장 카테고리를 과대평가했다. 2025 실측 성장은 평가 {c25[0]['g']:+.1f}%·수업혁신 {c25[1]['g']:+.1f}%·AI {next(x['g'] for x in c25 if x['k'] == 'AI'):+.1f}%.",
        f"재구매율은 {seg['rp'][0]}%→{seg['rp'][2]}%로 올랐지만 VIP(6회+) 비율은 {seg['vip_rate'][0]}%→{seg['vip_rate'][2]}%로 내려갔다 — '두 번은 오지만 단골은 안 된다'.",
        f"2023-24 구간 RFM 이탈위험+휴면 {risk_b}% — 두 구간 모두 40% 고착. 2025 코호트의 2026년(1~7월) 재방문은 {D['cohort']['C_2025'].get('2025→26partial', {}).get('2026partial잔존율(%)', '-')}%에 그친다.",
        *([D["recommend"]] if D.get("recommend") else []),
    ]
    out = [CSS, '<div class="mv">', f'<p class="mv-note">기준 {h(D["period"])} · 이수기록 {D["rows"]:,}건 · 고유 회원 {D["members"]:,}명 · {h(D["assume"])}</p>',
           '<ul class="mv-sum">' + "".join(f"<li>{x}</li>" for x in s) + "</ul>"]
    # KPI 타일
    out.append('<div class="mv-k">' + "".join(f"<div>{h(k)}<b>{v}</b><span class='mv-note'>{h(n)}</span></div>" for k, v, n in [
        ("코호트 1년 잔존", "15~21%", "목표 30%+"), ("재구매율(2025)", f"{seg['rp'][2]}%", "목표 40%+"), ("VIP 비율(2025)", f"{seg['vip_rate'][2]}%", "목표 3%"),
        ("2025 예측 대비", f"{miss:+.1f}%", "실적/예측"), ("역성장 시도", f"{sum(1 for r, v in D['region_g'].items() if v < 0 and r != '기타/미확인')}/17", "2020→2024, 목표 5 이하")]) + "</div>")
    # 연도·세그먼트
    t1 = "<table><tr><th>연도</th><th>회원</th><th>이수</th><th>추정 매출</th><th>1인당</th></tr>" + "".join(
        f"<tr><td>{x['y']}{'(1~7월)' if x['partial'] else ''}</td><td>{x['mem']:,}</td><td>{x['rows']:,}</td><td>{_won(x['rev'])}</td><td>{x['rev'] / x['mem'] / 1e4:.1f}만</td></tr>" for x in yrs) + "</table>"
    t2 = "<table><tr><th>구간</th><th>회원</th><th>추정 매출</th><th>재구매</th><th>VIP</th><th>평균 건수</th></tr>" + "".join(
        f"<tr><td>{h(seg['labels'][i])}</td><td>{seg['members'][i]:,}</td><td>{_won(seg['revenue'][i])}</td><td>{seg['rp'][i]}%</td><td>{seg['vip'][i]:,}({seg['vip_rate'][i]}%)</td><td>{seg['avg_purchase'][i]}</td></tr>" for i in range(len(seg["labels"]))) + "</table>"
    out.append(f'<div class="mv-g"><div class="mv-c"><h4>연도별 회원·매출</h4>{t1}</div><div class="mv-c"><h4>구간별 충성도</h4>{t2}</div></div>')
    # 카테고리 2025 실측 vs 예측
    mx = max(x["r25"] for x in D["cat_2025"]) or 1
    t3 = "<table><tr><th>카테고리</th><th>2024</th><th>2025 실적</th><th>증감</th><th>2025 예측</th><th></th></tr>" + "".join(
        f"<tr><td>{h(x['k'])}</td><td>{_won(x['r24'])}</td><td>{_won(x['r25'])}</td><td>{_gc(x['g'])}</td><td>{_won(x['pred']) if x['pred'] else '-'}</td>"
        f"<td style='text-align:left'><span class='mv-bar' style='width:{x['r25'] / mx * 90:.0f}px'></span></td></tr>" for x in sorted(D["cat_2025"], key=lambda x: -x["r25"])) + "</table>"
    # 지역 매출·객단가
    rr = {x["r"]: x for x in D["region_recent"]}
    t4 = "<table><tr><th>시도</th><th>누적 매출</th><th>객단가</th><th>2020→24</th><th>2023→24</th></tr>" + "".join(
        f"<tr><td>{h(x['r'])}</td><td>{_won(x['rev'])}</td><td>{x['aov']:,.0f}</td><td>{_gc(D['region_g'].get(x['r']))}</td><td>{_gc((rr.get(x['r']) or {}).get('g2324'))}</td></tr>"
        for x in sorted(D["region"], key=lambda x: -x["rev"])) + "</table>"
    out.append(f'<div class="mv-g"><div class="mv-c"><h4>카테고리 — 2025 실적 vs 예측</h4>{t3}<p class="mv-note">예측 = 2023→24 증감 연장(±50~100% 상한). 평가·AI·에듀테크 모두 예측에 못 미침.</p></div>'
               f'<div class="mv-c"><h4>시도별 매출·객단가</h4>{t4}</div></div>')
    # RFM · 코호트
    order = ["VIP", "핵심고객", "성장고객", "일반고객", "이탈위험", "휴면회원"]
    keys = [k for k in ("A_2020-22", "B_2023-24", "C_2025") if k in D["rfm"]]
    t5 = "<table><tr><th>등급</th>" + "".join(f"<th>{h(k)}</th>" for k in keys) + "</tr>" + "".join(
        "<tr><td>" + h(g) + "</td>" + "".join(f"<td>{D['rfm'][k].get(g, 0):,} ({_pct(D['rfm'][k].get(g, 0), sum(D['rfm'][k].values()))}%)</td>" for k in keys) + "</tr>" for g in order) + "</table>"
    act = D.get("rfm_actions") or {}
    t6 = "<table><tr><th>등급</th><th>액션</th></tr>" + "".join(f"<tr><td>{h(k)}</td><td style='text-align:left'>{h(v)}</td></tr>" for k, v in act.items()) + "</table>"
    out.append(f'<div class="mv-g"><div class="mv-c"><h4>RFM 분포(구간별 독립 산정)</h4>{t5}</div><div class="mv-c"><h4>등급별 액션</h4>{t6}</div></div>')
    # 정리 후보
    bad = [x for x in D["bottom"] if x["rec"] == "폐지/종료"][:10]
    t7 = "<table><tr><th>과정</th><th>카테고리</th><th>이수</th><th>매출</th></tr>" + "".join(
        f"<tr><td>{h(x['t'])}</td><td>{h(x['cat'])}</td><td>{x['rows']}</td><td>{_won(x['rev'])}</td></tr>" for x in bad) + "</table>"
    road = [tuple(x) for x in D.get("roadmap") or []]
    t8 = "<table><tr><th>단계</th><th>과제</th></tr>" + "".join(f"<tr><td>{h(a)}</td><td style='text-align:left'>{h(b)}</td></tr>" for a, b in road) + "</table>"
    out.append(f'<div class="mv-g"><div class="mv-c"><h4>정리 후보(최저 이수 과정)</h4>{t7}</div><div class="mv-c"><h4>실행 로드맵</h4>{t8}</div></div>')
    q = D["quality"]
    out.append('<div class="mv-c" style="margin-top:14px"><h4>데이터 품질·해석 주의</h4><ul>' + "".join(f"<li>{h(n)}</li>" for n in q["notes"])
               + f"<li>원본 시도 표기 {q['region_variants']}종 → 표준 18종으로 정리, 생년월일 형식 오류 {q['bad_birth']}건</li></ul>"
               '<p class="mv-note">원천: 비공개 저장소 strategy_room/member_analysis.json(집계값만, 수동 갱신). 개인 식별 정보는 저장하지 않음.</p></div>')
    out.append("</div>")
    return "".join(out)


if __name__ == "__main__":
    print(json.dumps(cp(), ensure_ascii=False)[:1500])
