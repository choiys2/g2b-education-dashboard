#!/usr/bin/env python3
"""
샘몰 SET 상품 스코어 (2026-11-15 결정: 원자료는 CP, 해석은 관리)

  - theme_map(): CP 'B2S·샘몰 기획' 탭 '테마별 교사몰 상품 지도' 원자료.
        연수 주제 18개 × 티처몰·아이스크림몰 상품 수 · 티처몰 베스트 진입 수 · 교사 관심 추세(↑↓). 점수·추천 없음.
  - build_admin(sec): 🔒 관리 탭 '샘몰 SET 후보' 칸(관리 비밀번호 암호화).
        주제별 SET 점수 = 교사 관심 30 + 연수 수요 30 + 상품 연계 가능성 20 + 자사 과정 보유 20
        → SET 후보 Top 10(자사 과정 + 상품 묶음안) · 유형(즉시 SET / 과정 개발 후 SET / 자체 상품 기획) · 경쟁 몰·연수원 대비 공백.
입력은 이미 쌓인 파일만 쓴다(외부 호출 없음, 비용 0):
  history/competitor_mall_catalog.json · history/teacher_interest_trends.json ·
  history/training_bids.jsonl · history/competitor_course_catalog.json
"""
import html
import json
from datetime import date, timedelta
from pathlib import Path

import training_topics
from mall_trends import NEULBOM_STRICT, topics_of

HERE = Path(__file__).parent
E = html.escape
TOPIC_NAME = {t[0]: t[1] for t in training_topics.TOPICS}
TOPICS = [t[0] for t in training_topics.TOPICS]
OWN = "비바샘연수원"
RIVALS = ("티처빌", "아이스크림")
NOTE = "color:var(--muted);font-size:12.5px;"


def _j(p, d=None):
    try:
        return json.loads((HERE / p).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return d


def _products():
    """티처몰(베스트·카테고리 상위·세트) + 아이스크림몰(노출 상품) → [{mall, no, n, p, rk, topics}] (상품번호 기준 중복 제거)"""
    cat = _j("history/competitor_mall_catalog.json") or {}
    malls = cat.get("malls") or {}
    tm, isc = malls.get("teachermall") or {}, malls.get("iscream") or {}
    seen, out = set(), []

    def add(mall, r, cat_name="", rk=None):
        key = (mall, str(r.get("no")))
        if key in seen or not r.get("name"):
            return
        seen.add(key)
        out.append({"mall": mall, "no": str(r.get("no")), "n": r["name"], "p": r.get("price"), "rk": rk,
                    "topics": topics_of(r["name"] + " " + cat_name, product=True)})
    for r in tm.get("best") or []:
        add("tm", r, "", r.get("rank"))
    for c in tm.get("categories") or []:
        for r in c.get("top") or []:
            add("tm", r, c.get("name", ""))
    for r in tm.get("sets") or []:
        add("tm", r, "세트")
    for r in isc.get("goods") or []:
        add("isc", r, "")
    return out, cat.get("captured_date") or ""


def _interest():
    """주제별 교사 관심 추세: 최근 4주 평균 ÷ 직전 8주 평균 - 1, 최근 수준(최근 4주 평균)"""
    d = (_j("history/teacher_interest_trends.json") or {}).get("datalab") or {}
    res = {}
    for t, ser in (d.get("topics") or {}).items():
        v = [x[1] for x in ser if isinstance(x, list) and len(x) == 2 and x[1] is not None]
        if len(v) < 12:
            continue
        rec, prev = sum(v[-4:]) / 4, sum(v[-12:-4]) / 8
        res[t] = {"mom": (rec / prev - 1) if prev else 0.0, "lvl": rec}
    return res, d.get("captured_date") or ""


def _arrow(m):
    return "↑" if m >= 0.10 else ("↓" if m <= -0.10 else "→")


def _bids(days=365):
    cut = (date.today() - timedelta(days=days)).isoformat()
    cnt = {}
    p = HERE / "history" / "training_bids.jsonl"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if (r.get("d") or "") < cut:
                continue
            for t in training_topics.classify_topics(r.get("t", "")):
                cnt[t] = cnt.get(t, 0) + 1
    return cnt


def _courses():
    comp = (_j("history/competitor_course_catalog.json") or {}).get("companies") or {}
    by = {}
    for co, v in comp.items():
        for c in v.get("courses") or []:
            title = c.get("title") or ""
            for t in training_topics.classify_topics(title):
                if t == "neulbom" and not NEULBOM_STRICT.search(title):
                    continue
                by.setdefault(co, {}).setdefault(t, []).append({"t": title, "url": c.get("url") or ""})
    return by


def theme_map():
    """CP 원자료: 점수·추천·판단 없이 수치만."""
    prods, cap = _products()
    if not prods:
        return {"available": False}
    intr, icap = _interest()
    rows = []
    for t in TOPICS:
        tm = [p for p in prods if p["mall"] == "tm" and t in p["topics"]]
        isc = [p for p in prods if p["mall"] == "isc" and t in p["topics"]]
        i = intr.get(t)
        if not (tm or isc or i):
            continue
        rows.append({"t": t, "name": TOPIC_NAME.get(t, t), "tm": len(tm), "best": sum(1 for p in tm if p["rk"]),
                     "isc": len(isc), "trend": _arrow(i["mom"]) if i else "", "pct": round(i["mom"] * 100) if i else None,
                     "ex": [p["n"] for p in sorted(tm + isc, key=lambda p: (p["rk"] is None, p["rk"] or 0))[:2]]})
    rows.sort(key=lambda r: -(r["tm"] + r["isc"]))
    other = {"tm": sum(1 for p in prods if p["mall"] == "tm" and not p["topics"]),
             "isc": sum(1 for p in prods if p["mall"] == "isc" and not p["topics"])}
    return {"available": True, "captured": cap, "interest_date": icap, "rows": rows, "other": other,
            "total": {"tm": sum(1 for p in prods if p["mall"] == "tm"), "isc": sum(1 for p in prods if p["mall"] == "isc")}}


def scores():
    prods, cap = _products()
    intr, _ = _interest()
    bids = _bids()
    crs = _courses()
    own = crs.get(OWN, {})
    rival = {t: sum(len(crs.get(co, {}).get(t, [])) for co in RIVALS) for t in TOPICS}

    def norm(d):
        mx = max(d.values()) if d and max(d.values()) > 0 else 1
        return {k: v / mx for k, v in d.items()}
    prod_n = {t: sum(1 for p in prods if t in p["topics"]) for t in TOPICS}
    mom = {t: max(-0.5, min(0.5, intr[t]["mom"])) + 0.5 for t in intr}
    lvl = norm({t: intr[t]["lvl"] for t in intr})
    I = {t: 0.6 * mom.get(t, 0.5) + 0.4 * lvl.get(t, 0) for t in TOPICS}
    nb, nr = norm({t: bids.get(t, 0) for t in TOPICS}), norm(rival)
    D = {t: 0.5 * nb[t] + 0.5 * nr[t] for t in TOPICS}
    P = norm(prod_n)
    rows = []
    for t in TOPICS:
        oc = own.get(t, [])
        s = 30 * I[t] + 30 * D[t] + 20 * P[t] + 20 * (1.0 if oc else 0.4)
        if oc and P[t] >= 0.2:
            kind = "즉시 SET"
        elif not oc and (D[t] >= 0.4 or (P[t] >= 0.6 and I[t] >= 0.5)):
            kind = "과정 개발 후 SET"
        elif P[t] < 0.2 and (I[t] >= 0.55 or D[t] >= 0.4):
            kind = "자체 상품 기획"
        else:
            kind = "관찰"
        tp = sorted([p for p in prods if t in p["topics"]], key=lambda p: (p["rk"] is None, p["rk"] or 0))
        rows.append({"t": t, "name": TOPIC_NAME.get(t, t), "score": round(s, 1), "kind": kind,
                     "I": round(I[t], 2), "D": round(D[t], 2), "P": round(P[t], 2), "mom": intr.get(t, {}).get("mom"),
                     "bids": bids.get(t, 0), "rival": rival[t], "own_n": len(oc), "own": oc[:2], "prod_n": prod_n[t],
                     "tm_n": sum(1 for p in tp if p["mall"] == "tm"), "isc_n": sum(1 for p in tp if p["mall"] == "isc"),
                     "prods": tp[:3]})
    rows = [r for r in rows if r["t"] != "subject"]  # '교과 전문성(기타)'는 분류 안 된 과정이 모이는 칸이라 순위에서 뺀다
    rows.sort(key=lambda r: -r["score"])
    return rows, cap


def _bar(v, w=None):
    return (f"<span style='display:inline-block;width:100%;max-width:110px;height:8px;background:var(--surface-2);border-radius:4px;vertical-align:middle;'>"
            f"<span style='display:block;height:100%;width:{max(0, min(100, v * 100)):.0f}%;background:var(--accent);border-radius:4px;'></span></span>")


def _plink(p):
    if p["mall"] == "tm" and p["no"].isdigit():
        u = "https://shop.teacherville.co.kr/goods/view?no=" + p["no"]
    elif p["mall"] == "isc" and p["no"].isdigit():
        u = "https://i-screammall.co.kr/goods/detail/" + p["no"]
    else:
        return E(p["n"])
    return f'<a href="{E(u)}" target="_blank" rel="noopener noreferrer">{E(p["n"])}</a>'


def _clink(c):
    u = c.get("url") or ""
    return f'<a href="{E(u)}" target="_blank" rel="noopener noreferrer">{E(c["t"])}</a>' if u.startswith("https://") else E(c["t"])


KIND_BG = {"즉시 SET": "color-mix(in srgb, #10b981 22%, var(--surface-2))", "과정 개발 후 SET": "color-mix(in srgb, var(--warning) 25%, var(--surface-2))",
           "자체 상품 기획": "color-mix(in srgb, var(--accent) 20%, var(--surface-2))", "관찰": "var(--surface-2)"}


def _chip(k):
    return f"<span style='display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;white-space:nowrap;background:{KIND_BG.get(k, 'var(--surface-2)')};'>{E(k)}</span>"


def build_admin(sec):
    rows, cap = scores()
    if not rows or not any(r["prod_n"] for r in rows):
        return sec("샘몰 SET 후보", "교사몰 상품 데이터가 쌓이면 채워집니다.", "")
    top = rows[:10]
    kinds = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    tiles = "".join(f"<div style='padding:8px 10px;border:1px solid var(--border);border-radius:10px;min-width:0;'>"
                    f"<div style='{NOTE}white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{E(k)}</div><div style='font-size:20px;font-weight:800;line-height:1.3;'>{kinds.get(k, 0)}<span style='font-size:13px;font-weight:600;'> 주제</span></div></div>"
                    for k in ("즉시 SET", "과정 개발 후 SET", "자체 상품 기획", "관찰"))
    body1 = (f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;margin-bottom:12px;'>{tiles}</div>"
             "<div class='tbl-wrap'><table class='sset' style='table-layout:fixed;min-width:920px;font-size:12.5px;'>"
             "<colgroup><col style='width:36px'><col style='width:170px'><col style='width:118px'><col style='width:56px'>"
             "<col style='width:86px'><col style='width:86px'><col style='width:86px'><col></colgroup>"
             "<thead><tr><th class='num'>#</th><th>연수 주제</th><th>유형</th><th class='num'>점수</th>"
             "<th>교사 관심</th><th>연수 수요</th><th>상품 연계</th><th>SET 묶음안 (자사 과정 + 상품)</th></tr></thead><tbody>"
             + "".join(
                 f"<tr><td class='num'>{i}</td><td><b>{E(r['name'])}</b>"
                 f"<div style='{NOTE}'>관심 {('+' if (r['mom'] or 0) >= 0 else '')}{round((r['mom'] or 0) * 100)}% · 공고 {r['bids']} · 경쟁 과정 {r['rival']}</div></td>"
                 f"<td>{_chip(r['kind'])}</td><td class='num'><b>{r['score']}</b></td>"
                 f"<td>{_bar(r['I'])}</td><td>{_bar(r['D'])}</td><td>{_bar(r['P'])}</td>"
                 f"<td class='sset-b'>"
                 + ("".join(f"<div class='l1'>📘 {_clink(c)}</div>" for c in r["own"]) if r["own"] else f"<div style='{NOTE}'>📘 자사 과정 없음 → 과정 개발 필요</div>")
                 + ("".join(f"<div class='l1'>🎁 {_plink(p)}</div>" for p in r["prods"]) if r["prods"] else f"<div style='{NOTE}'>🎁 연계 상품 없음 → 자체 상품 기획</div>")
                 + "</td></tr>" for i, r in enumerate(top, 1))
             + "</tbody></table></div>"
             f"<p style='{NOTE}margin-top:6px;'>점수 = 교사 관심 30(최근 4주 추세 60%·수준 40%) + 연수 수요 30(최근 1년 연수 공고 50%·경쟁 연수원 과정 수 50%) + 상품 연계 20(교사몰 해당 주제 상품 수) + 자사 과정 보유 20(없으면 8). "
             "유형: 즉시 SET = 자사 과정 있음·상품 있음 / 과정 개발 후 SET = 수요(또는 상품·관심)가 큰데 자사 과정 없음 / 자체 상품 기획 = 관심·수요는 있는데 교사몰 상품이 적음.</p>")
    imm = [r["name"] for r in top if r["kind"] == "즉시 SET"][:3]
    dev = [r["name"] for r in rows if r["kind"] == "과정 개발 후 SET"][:3]
    own_p = [r["name"] for r in rows if r["kind"] == "자체 상품 기획"][:3]
    so = ("<div style='margin-top:10px;padding:10px 12px;border-left:3px solid var(--accent);background:var(--surface-2);border-radius:6px;font-size:13px;'>"
          f"<b>해석</b> — ① 샘몰 출시(2026 H2) 첫 묶음은 <b>{E(' · '.join(imm) or '-')}</b>: 이미 자사 과정과 팔리는 상품이 있어 기획만으로 출시 가능합니다. "
          f"② <b>{E(' · '.join(dev) or '-')}</b>은 시장 수요가 확인됐지만 자사 과정이 없어 1·2셀 과정 개발과 함께 묶어야 합니다. "
          f"③ <b>{E(' · '.join(own_p) or '-')}</b>은 교사몰 상품이 부족한 공백이라 샘몰 자체(협력사) 상품 기획 기회입니다.</div>")
    gap_rows = sorted(rows, key=lambda r: -(r["rival"] - r["own_n"] * 3))
    body2 = ("<div class='tbl-wrap'><table style='table-layout:fixed;min-width:640px;font-size:12.5px;'><colgroup><col style='width:150px'><col style='width:84px'><col style='width:96px'><col style='width:72px'><col style='width:110px'><col></colgroup><thead><tr><th>연수 주제</th><th class='num'>티처몰 상품</th><th class='num'>아이스크림몰 상품</th>"
             "<th class='num'>자사 과정</th><th class='num'>경쟁 연수원 과정(2사)</th><th>공백</th></tr></thead><tbody>"
             + "".join(
                 f"<tr><td>{E(r['name'])}</td><td class='num'>{r['tm_n']}</td><td class='num'>{r['isc_n']}</td>"
                 f"<td class='num'>{r['own_n']}</td><td class='num'>{r['rival']}</td><td style='font-size:12.5px;'>"
                 + E(" · ".join(x for x in [
                     "자사 과정 열세" if r["rival"] >= 10 and r["own_n"] * 3 < r["rival"] else "",
                     "아이스크림몰 미진출" if r["tm_n"] and not r["isc_n"] else "",
                     "티처몰 미진출" if r["isc_n"] and not r["tm_n"] else "",
                     "몰 상품 없음" if not r["prod_n"] else ""] if x) or "-")
                 + "</td></tr>" for r in gap_rows if r["prod_n"] or r["rival"] or r["own_n"])
             + "</tbody></table></div>"
             f"<p style='{NOTE}margin-top:6px;'>아이스크림몰은 첫 화면 노출 상품만 반영해 실제 상품 수보다 적습니다. 자사 과정은 공개 목록 일부만 확인된 경우가 있어 '자사 과정 0'은 확인 필요입니다.</p>")
    css = ("<style>.sset td,.sset th{vertical-align:middle;padding:7px 8px;} .sset td{word-break:keep-all;overflow-wrap:anywhere;}"
           " .sset-b .l1{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:1.55;font-size:12.5px;}"
           " .sset-b .l1 a{color:inherit;text-decoration:underline;text-decoration-color:var(--border);}</style>")
    return (css + sec("샘몰 SET 후보 Top 10", f"연수+상품 SET을 어느 주제부터 묶을지 점수로 정렬했습니다. 상품 {E(cap)} 기준 · 관리 탭 전용.", body1 + so)
            + sec("경쟁 몰·연수원 대비 공백", "주제별로 교사몰 상품과 연수 과정이 어디에 몰려 있고 어디가 비었는지.", body2))


if __name__ == "__main__":
    rows, cap = scores()
    for r in rows:
        print(f"{r['score']:5} {r['kind']:10} {r['name']:12} I{r['I']} D{r['D']} P{r['P']} own{r['own_n']} prod{r['prod_n']} bids{r['bids']} rival{r['rival']}")
    print(json.dumps(theme_map(), ensure_ascii=False)[:600])
