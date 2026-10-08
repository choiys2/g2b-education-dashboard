#!/usr/bin/env python3
"""
구글시트 업무 탭 4종 -> 실행 추적 데이터(live/sheets_ops.json, 암호화된 대시보드에만 게시).

  26입찰DT            : 공고·입찰참여·수주여부·사업규모·수주금액·수주업체 -> 입찰 결과 깔때기·낙찰률·패찰 상대
  26 콘텐츠DT         : 인증·서비스·심사접수·분야·학점·주제·월별 매출 -> 인증 파이프라인·과정 매출(파레토·월×분야)
  정산관리            : 청구월·총예산·청구금액·계산서발행·매출전표 -> 미수·미발행 경보
  26운영(블렌디드연수) : 집합 사업의 장소·강사섭외·홍보문자·운영준비·목표·신청 -> 집합연수 준비 현황판

*** 개인정보 ***
담당자·연락처·메일·강사·담당·장학사·주무관 열과 이슈사항·비고 같은 자유 서술 열은 읽지 않는다
(강사 열은 '분야별 강사 수' 집계에만 메모리에서 쓰고 이름은 저장·게시하지 않는다).
history/sheets_ops_status.json 에는 머리글 매칭 결과와 건수, 상태값 어휘(짧은 범주값)만 남긴다.
"""
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import own_pipeline_export as ope

HERE = Path(__file__).parent
STATUS = HERE / "history" / "sheets_ops_status.json"
PRIVATE = re.compile(r"담당|연락|전화|메일|e-?mail|장학사|주무관|이슈|비고|메모|강사명|소통", re.I)


def tab(title_rx):
    gid = ope.find_gid(title_rx)
    if not gid:
        return None, []
    return gid, ope.fetch_via_service_account(gid)


def header_index(matrix, want):
    """want: {역할: 정규식}. 처음 6줄 중 매칭이 가장 많은 줄을 머리글로."""
    best, bi = {}, 0
    for i, row in enumerate(matrix[:6]):
        m = {}
        for role, rx in want.items():
            for j, h in enumerate(row):
                h = (h or "").replace("\n", " ").strip()
                if role not in m and h and re.search(rx, h) and not (PRIVATE.search(h) and not role.startswith("_")):
                    m[role] = j
        if len(m) > len(best):
            best, bi = m, i
    return bi, best


def num(s):
    s = re.sub(r"[^\d.\-]", "", str(s or ""))
    try:
        return float(s) if s not in ("", "-", ".") else None
    except ValueError:
        return None


def pdate(s, year=2026):
    s = str(s or "").strip()
    m = re.search(r"(20\d{2})\D{1,3}(\d{1,2})\D{1,3}(\d{1,2})", s) or re.search(r"(?<!\d)(2\d)[./-](\d{1,2})[./-](\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
        y = y + 2000 if y < 100 else y
    else:
        m = re.search(r"(?<!\d)(\d{1,2})\s?[./월]\s?(\d{1,2})", s)
        if not m:
            return None
        y, (mo, d) = year, map(int, m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def vocab(vals, n=12):
    """짧은 범주값만(사람 이름 형태 2~3자 한글 단독은 제외) 상위 n개"""
    c = Counter(v.strip() for v in vals if v and len(v.strip()) <= 8 and not re.fullmatch(r"[가-힣]{2,3}", v.strip()))
    return dict(c.most_common(n))


YES = re.compile(r"^(o|y|yes|v|✓|✔|●|○|참여|수주|완료|낙찰|발행|확정|true)$", re.I)


# ---------------------------------------------------------------- 26입찰DT
def bids(status):
    gid, m = tab(r"^\s*'?2[6-9]\s*입찰\s*DT")
    if not m:
        status["bids"] = {"error": "탭 없음"}
        return None
    hi, ix = header_index(m, {"region": r"공고지역|지역", "org": r"공고기관|발주", "posted": r"공고게시|공고일", "field": r"^분야",
                               "title": r"공고명|사업명", "budget": r"사업규모|추정|예산", "join": r"입찰참여|참여", "open": r"개찰",
                               "won": r"수주여부", "won_amt": r"수주금액|낙찰금액", "winner": r"수주업체|낙찰업체"})
    rows = []
    for r in m[hi + 1:]:
        g = lambda k: (r[ix[k]] if k in ix and ix[k] < len(r) else "") or ""
        if not g("title").strip():
            continue
        wv = g("won").strip()
        # 실제 입력(2026-10-08 진단): 수주성공 / 수주실패 / 티처빌수주 / 한교원수주 / 비바샘 과정수주 / 개발이라 아웃 / 공고 미확인 …
        won = bool(re.search(r"수주\s?성공|비바샘|자사|^o$|^y$", wv, re.I))
        comp_won = re.search(r"(티처빌|아이스크림|한교원|테크빌|[가-힣A-Za-z]+)\s?수주$", wv) if not won else None
        lost = bool(re.search(r"실패|탈락|낙찰\s?실패", wv)) or bool(comp_won)
        jv = g("join").strip()
        joined = won or lost or (bool(jv) and not re.search(r"^(x|n|no|미참여|불참|포기|-)$", jv, re.I))
        rows.append({"region": g("region").strip()[:4], "org": g("org").strip()[:30], "title": g("title").strip()[:80],
                     "field": g("field").strip()[:12], "posted": (pdate(g("posted")) or pdate(g("open")) or "") and (pdate(g("posted")) or pdate(g("open"))).isoformat(),
                     "budget": num(g("budget")), "joined": joined, "won": won, "result": wv[:8],
                     "won_amt": num(g("won_amt")), "winner": (g("winner").strip() or (comp_won.group(1) if comp_won else ""))[:20]})
    status["bids"] = {"tab_gid": gid, "header_row": hi + 1, "roles": sorted(ix), "rows": len(rows),
                      "vocab_join": vocab([(r[ix["join"]] if "join" in ix and ix["join"] < len(r) else "") for r in m[hi + 1:]]),
                      "vocab_won": vocab([(r[ix["won"]] if "won" in ix and ix["won"] < len(r) else "") for r in m[hi + 1:]])}
    joined = [r for r in rows if r["joined"]]
    won = [r for r in joined if r["won"]]
    lost_to = Counter(r["winner"] for r in joined if not r["won"] and r["winner"])
    rate = [{"budget": r["budget"], "amt": r["won_amt"], "rate": round(r["won_amt"] / r["budget"] * 100, 1), "won": r["won"], "winner": r["winner"]}
            for r in joined if r["budget"] and r["won_amt"] and 0.3 < r["won_amt"] / r["budget"] < 1.2]
    by_field = defaultdict(lambda: {"n": 0, "join": 0, "won": 0})
    for r in rows:
        f = by_field[r["field"] or "미분류"]
        f["n"] += 1
        f["join"] += r["joined"]
        f["won"] += r["won"]
    return {"n": len(rows), "joined": len(joined), "won": len(won), "won_amt": sum(r["won_amt"] or 0 for r in won),
            "results": dict(Counter(r["result"] or "미기재" for r in joined).most_common(8)),
            "lost_to": dict(lost_to.most_common(10)), "rate": rate, "by_field": dict(by_field),
            "recent": sorted(rows, key=lambda r: r["posted"] or "", reverse=True)[:60]}


# ---------------------------------------------------------------- 26 콘텐츠DT
def contents(status):
    gid, m = tab(r"^\s*'?2[6-9]\s*콘텐츠\s*DT")
    if not m:
        status["contents"] = {"error": "탭 없음"}
        return None
    hi, ix = header_index(m, {"cert": r"^인증", "service": r"^서비스", "submit": r"심사\s?접수", "field": r"^분야", "credit": r"^학점",
                               "topic": r"^주제|과정명|연수명", "kind": r"^분류", "_inst": r"^강사$", "total": r"누적\s?매출|매출\(누적"})
    head = m[hi]
    months = [(j, int(re.search(r"(\d{1,2})\s?월", h).group(1))) for j, h in enumerate(head) if h and re.search(r"매출.*\d{1,2}\s?월", h)]
    rows, inst = [], defaultdict(set)
    for r in m[hi + 1:]:
        g = lambda k: (r[ix[k]] if k in ix and ix[k] < len(r) else "") or ""
        if not g("topic").strip():
            continue
        sales = {mo: (num(r[j]) if j < len(r) else None) or 0 for j, mo in months}
        if g("_inst").strip():
            inst[g("field").strip() or "미분류"].add(g("_inst").strip())  # 이름은 집계에만 쓰고 저장하지 않음
        rows.append({"title": g("topic").strip()[:60], "field": g("field").strip()[:12], "kind": g("kind").strip()[:10],
                     "credit": g("credit").strip()[:6], "cert": g("cert").strip()[:10],
                     "submit": (pdate(g("submit")) or "") and pdate(g("submit")).isoformat(),
                     "service": (pdate(g("service")) or "") and pdate(g("service")).isoformat(),
                     "service_year": (re.search(r"20\d{2}", g("service")) or [None])[0] if g("service") else None,
                     "total": num(g("total")) or sum(sales.values()), "sales": sales})
    status["contents"] = {"tab_gid": gid, "header_row": hi + 1, "roles": sorted(k for k in ix if not k.startswith("_")), "rows": len(rows),
                          "months": [mo for _, mo in months], "vocab_cert": vocab([(r[ix["cert"]] if "cert" in ix and ix["cert"] < len(r) else "") for r in m[hi + 1:]]),
                          "vocab_service": vocab([(r[ix["service"]] if "service" in ix and ix["service"] < len(r) else "") for r in m[hi + 1:]])}
    today = date.today()

    def stage(r):
        # '서비스' 열은 서비스 시작 연도(2022~2026)로 입력돼 있다
        if (r["service"] and r["service"] <= today.isoformat()) or (r["service_year"] and int(r["service_year"]) <= today.year):
            return "서비스 중"
        if r["service"] or r["service_year"]:
            return "오픈 예정"
        if re.search(r"완료|합격|인증|o|y", r["cert"], re.I) and not re.search(r"미|불|x", r["cert"], re.I):
            return "인증 완료"
        if r["submit"]:
            return "심사 중"
        return "제작·준비"
    for r in rows:
        r["stage"] = stage(r)
    mfield = defaultdict(lambda: defaultdict(float))
    for r in rows:
        for mo, v in r["sales"].items():
            mfield[r["field"] or "미분류"][mo] += v
    years = Counter(r["service_year"] for r in rows if r["service_year"])
    return {"n": len(rows), "stages": dict(Counter(r["stage"] for r in rows)), "rows": rows, "by_year": dict(sorted(years.items())),
            "months": [mo for _, mo in months], "by_field_month": {k: dict(v) for k, v in mfield.items()},
            "total": sum(r["total"] or 0 for r in rows), "inst_by_field": {k: len(v) for k, v in inst.items()}}


# ---------------------------------------------------------------- 정산관리
def settle(status):
    gid, m = tab(r"^\s*정산\s*관리")
    if not m:
        status["settle"] = {"error": "탭 없음"}
        return None
    hi, ix = header_index(m, {"state": r"^상태", "month": r"청구\s?월", "region": r"^지역", "org": r"기관명", "course": r"연수명",
                               "end": r"연수\s?종료", "budget": r"총\s?예산", "claim": r"청구\s?금액|실매출", "invoice": r"계산서",
                               "slip": r"매출\s?전표", "contract": r"계약\s?진행", "rate": r"모집률"})
    rows = []
    today = date.today()
    for r in m[hi + 1:]:
        g = lambda k: (r[ix[k]] if k in ix and ix[k] < len(r) else "") or ""
        if not (g("course").strip() or g("org").strip()):
            continue
        end = pdate(g("end"))
        inv = g("invoice").strip()
        inv_done = bool(inv) and not re.search(r"^(x|n|미|-)$|미발행|예정", inv, re.I)
        slip_done = bool(g("slip").strip()) and not re.search(r"^(x|n|미|-)$", g("slip").strip(), re.I)
        claim = num(g("claim"))
        days = (today - end).days if end else None
        flag = ("계산서 미발행" if claim and not inv_done and days is not None and days > 14 else
                "전표 미처리" if inv_done and not slip_done else "청구 전" if not claim and days is not None and days > 30 else "")
        rows.append({"state": g("state").strip()[:8], "month": g("month").strip()[:8], "region": g("region").strip()[:4],
                     "org": g("org").strip()[:30], "course": g("course").strip()[:60], "end": end.isoformat() if end else "",
                     "budget": num(g("budget")), "claim": claim, "invoice": inv_done, "slip": slip_done, "days": days, "flag": flag})
    status["settle"] = {"tab_gid": gid, "header_row": hi + 1, "roles": sorted(ix), "rows": len(rows),
                        "vocab_invoice": vocab([(r[ix["invoice"]] if "invoice" in ix and ix["invoice"] < len(r) else "") for r in m[hi + 1:]])}
    return {"n": len(rows), "rows": rows, "claim": sum(r["claim"] or 0 for r in rows),
            "flags": dict(Counter(r["flag"] for r in rows if r["flag"]))}


# ---------------------------------------------------------------- 26운영(블렌디드연수)
def blended(status):
    gid, m = tab(r"^\s*'?2[6-9]\s*운영\s*\(\s*블렌")
    if not m:
        status["blended"] = {"error": "탭 없음"}
        return None
    hi, ix = header_index(m, {"kind": r"^구분", "contract": r"^계약", "field": r"^분야", "course": r"연수명", "region": r"^지역",
                               "org": r"기관명", "venue_name": r"연수\s?장소|대관\s?장소", "schedule": r"연수\s?일정", "target": r"^목표",
                               "applied": r"신청\s?인원", "people": r"연수\s?인원", "venue": r"장소\s?섭외", "lecturer": r"강사\s?섭외",
                               "sms": r"홍보\s?문자|안내\s?문자", "prep": r"운영\s?준비", "meal": r"^식사", "snack": r"^다과",
                               "budget": r"^예산", "recruit": r"모집\s?현황"})
    checks = [("venue", "장소"), ("lecturer", "강사"), ("sms", "홍보문자"), ("prep", "운영준비"), ("meal", "식사"), ("snack", "다과")]
    rows = []
    for r in m[hi + 1:]:
        g = lambda k: (r[ix[k]] if k in ix and ix[k] < len(r) else "") or ""
        if not g("course").strip():
            continue
        st = {}
        for k, lab in checks:
            if k in ix:
                v = g(k).strip()
                # 실제 입력은 날짜·장소·이름을 적는 방식 → 값이 있으면 완료, '미정·예정·검토·요청·중'이면 진행(값 자체는 저장 안 함)
                st[lab] = "미착수" if not v or v in ("-", "x", "X") else ("진행" if re.search(r"미정|예정|검토|요청|진행|중$|\?", v) else "완료")
        tgt, app = num(g("target")), num(g("applied")) or num(g("people"))
        rows.append({"course": g("course").strip()[:60], "org": g("org").strip()[:30], "region": g("region").strip()[:4],
                     "field": g("field").strip()[:12], "venue_name": g("venue_name").strip()[:30], "schedule": g("schedule").strip()[:30],
                     "first_date": (pdate(g("schedule")) or "") and pdate(g("schedule")).isoformat(),
                     "target": tgt, "applied": app, "budget": num(g("budget")), "checks": st,
                     "ready": round(sum(1 for v in st.values() if v == "완료") / len(st) * 100) if st else None})
    status["blended"] = {"tab_gid": gid, "header_row": hi + 1, "roles": sorted(ix), "rows": len(rows),
                         "vocab_checks": {lab: vocab([(r[ix[k]] if k in ix and ix[k] < len(r) else "") for r in m[hi + 1:]], 6) for k, lab in checks if k in ix}}
    return {"n": len(rows), "rows": rows, "checks": [lab for k, lab in checks if k in ix]}


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "live/sheets_ops.json")
    status = {"date": date.today().isoformat()}
    res = {"available": False}
    if not ope.SA_JSON:
        status["error"] = "GOOGLE_SHEETS_SA_JSON 없음"
    else:
        for k, fn in (("bids", bids), ("contents", contents), ("settle", settle), ("blended", blended)):
            try:
                res[k] = fn(status)
            except Exception as e:
                status[k] = {"error": str(e)[:200]}
                res[k] = None
        res["available"] = any(res.get(k) for k in ("bids", "contents", "settle", "blended"))
        res["fetched"] = (datetime.utcnow() + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M")
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    print("sheets_ops:", {k: (v or {}).get("rows") if isinstance(v, dict) else v for k, v in status.items() if k != "date"})


if __name__ == "__main__":
    main()
