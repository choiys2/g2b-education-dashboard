#!/usr/bin/env python3
"""
교사단체 분석 탭(사용자 요청 2026-11-22) — 교원단체·노조 / 출판사 연수원 / 교과·수업 연구회 / 정책 협의체의
최근 180일 소식을 모아 주간 활동량·이슈 유형·리더십(회장·임원) 동향을 만든다 -> history/teacher_org_watch.json

- 소스(모두 무료·키 불필요 우선): 구글 뉴스 RSS(키 없음), NAVER_CLIENT_ID/SECRET 이 있으면 네이버 뉴스 검색(무료 한도),
  매일 모이는 에듀테크 레이더 묶음(history/edutech_radar.json), 교사단체 소식(history/teacher_group_news.json).
- 개인 실명은 저장하지 않는다: 직함 옆 이름을 '○○○'로 가리고, 같은 이름은 다른 제목에서도 가린다. 원문 링크로 확인.
- 이전 결과와 합쳐 180일을 누적한다(한 번 수집이 실패해도 이력은 남음).
"""
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

OUT = Path("history/teacher_org_watch.json")
DAYS = 180
WEEKS = 26

# (카테고리, 이름, 검색어, 제목 매칭 정규식)
ORGS = [
    ("union", "한국교총", "교총", r"교총|교원단체총연합회"),
    ("union", "전교조", "전교조", r"전교조|전국교직원노동조합"),
    ("union", "교사노조연맹", "교사노조", r"교사노조|교사노동조합"),
    ("union", "실천교육교사모임", "실천교육교사모임", r"실천교육교사"),
    ("union", "좋은교사운동", "좋은교사운동", r"좋은교사"),
    ("union", "새로운학교네트워크", "새로운학교네트워크", r"새로운학교네트워크"),
    ("pub", "아이스크림 연수원", "아이스크림연수원", r"아이스크림\s?(원격)?(교육)?연수원|아이스크림에듀|아이스크림미디어"),
    ("pub", "티처빌 연수원", "티처빌", r"티처빌|테크빌교육"),
    ("pub", "천재 T셀파", "T셀파", r"T셀파|티셀파|천재교육|천재교과서"),
    ("pub", "미래엔 엠티처", "엠티처", r"엠티처|미래엔"),
    ("pub", "지학사", "지학사", r"지학사"),
    ("pub", "동아출판", "동아출판", r"동아출판"),
    ("pub", "비바샘 연수원", "비바샘", r"비바샘|비상교육"),
    ("study", "한국교사크리에이터협회", "교사크리에이터협회", r"교사크리에이터|교크협"),
    ("study", "대한교사협회", "대한교사협회", r"대한교사협회"),
    ("study", "전국진로진학상담교사협의회", "진로진학상담교사협의회", r"진로진학상담교사"),
    ("study", "참쌤스쿨", "참쌤스쿨", r"참쌤"),
    ("study", "교육과정평가연구회", "수업평가 연구회", r"수업.?평가.?연구회|교육과정.?연구회"),
    ("policy", "시도교육감협의회", "시도교육감협의회", r"교육감협의회"),
    ("policy", "교원단체 교섭·협의", "교원단체 교섭", r"교원단체.{0,6}(교섭|협의|간담회)|단체교섭"),
]
CATS = {"union": "교원단체·노조", "pub": "출판사·연수원", "study": "교과·수업 연구회", "policy": "정책 협의체"}
TAGS = [
    ("리더십", r"(?<!장관 )(?:회장|위원장|이사장|연수원장|대표|취임|당선|선거|연임|선출|집행부|임원|사무총장)(?!.{0,4}인선)"),
    ("성명·입장", r"성명|논평|기자회견|촉구|반대|요구|비판|규탄|입장|우려|철회|환영|해야|하라|반발"),
    ("연수·행사", r"연수|세미나|포럼|대회|캠프|박람회|컨퍼런스|콘퍼런스|워크숍|축제|시상"),
    ("협약·제휴", r"협약|MOU|제휴|맞손|협력|파트너"),
    ("AI·디지털", r"AI|인공지능|디지털|에듀테크|코딩|AIDT|챗GPT"),
    ("교권·처우", r"교권|처우|수당|임금|민원|정원|업무|소송|아동학대"),
    ("평가·입시", r"수능|평가|입시|고교학점제|내신|시험"),
]
TITLE_WORDS = r"(?:장관|회장|부회장|위원장|부위원장|수석부위원장|이사장|원장|대표|교육감|총장|사무총장|대변인|의원|교수|교장|교감)"
SURN = set("김이박최정강조윤장임한오서신권황안송류유전홍고문양손배백허남심노하곽성차주우구민진나지엄채원천방공현함변염여추도소석선설마길연위표명기반왕금옥육인맹제모남궁탁국어은편용예봉경봉")
NOT_NAME = re.compile(r"(부|청|원|회|조|단|국|처|관|교|당|실|과|군|시|도|구|측|들|와|과|은|는|이|가|의|에)$")


def _names(title):
    """직함 앞뒤의 2~3글자 한글 이름 후보."""
    out = set()
    for m in re.finditer(r"([가-힣]{2,3})\s?" + TITLE_WORDS, title):
        w = m.group(1)
        if w[0] in SURN and not NOT_NAME.search(w):
            out.add(w)
    for m in re.finditer(r"([가-힣]{3})\s(?:[가-힣]{2,8}\s)?" + TITLE_WORDS, title):  # 이름 + 소속 + 직함
        w = m.group(1)
        if w[0] in SURN and not NOT_NAME.search(w):
            out.add(w)
    for m in re.finditer(r"([가-힣]{3})\s?(?=사퇴|사임|취임|당선|경질|선출|연임|내정)", title):
        w = m.group(1)
        if w[0] in SURN and not NOT_NAME.search(w):
            out.add(w)
    for m in re.finditer(TITLE_WORDS + r"\s([가-힣]{2,3})(?=[\s,·\"'”’…]|$)", title):
        w = m.group(1)
        if w[0] in SURN and not NOT_NAME.search(w):
            out.add(w)
    return out


def mask(title, names):
    for n in sorted(names, key=len, reverse=True):
        title = re.sub(r"(?<![가-힣])" + re.escape(n), "○" * len(n), title)
    return title


def tags(t):
    return [k for k, rx in TAGS if re.search(rx, t)]


def _wk(d):
    dt = date.fromisoformat(d)
    return (dt - timedelta(dt.weekday())).isoformat()


def _fetch(q):
    try:
        from teacher_group_news import google, naver
    except Exception:  # noqa: BLE001
        return []
    items = naver(q)
    if items is None:
        items = google(q)
    return items or []


def collect(net=True):
    since = (date.today() - timedelta(DAYS)).isoformat()
    raw = []  # (org name, item)
    ok = 0
    if net:
        for cat, nm, q, rx in ORGS:
            got = _fetch(q)
            ok += bool(got)
            for it in got:
                if re.search(rx, it.get("t", "")):
                    raw.append((nm, it))
            time.sleep(0.3)
    # 매일 모이는 레이더 묶음 · 교사단체 소식
    try:
        R = json.loads(Path("history/edutech_radar.json").read_text(encoding="utf-8"))
        for it in R.get("items") or []:
            t = it.get("title") or ""
            for cat, nm, q, rx in ORGS:
                if re.search(rx, t):
                    raw.append((nm, {"t": t, "d": (it.get("orig_date") or it.get("date") or "")[:10], "src": it.get("source") or "",
                                     "u": it.get("orig") or it.get("url") or ""}))
    except (OSError, ValueError):
        pass
    try:
        G = json.loads(Path("history/teacher_group_news.json").read_text(encoding="utf-8"))
        for org, v in (G.get("orgs") or {}).items():
            for it in v.get("items") or []:
                for cat, nm, q, rx in ORGS:
                    if re.search(rx, it.get("t", "")) or re.search(rx, org):
                        raw.append((nm, it))
                        break
    except (OSError, ValueError):
        pass
    return raw, since, ok


def build(raw, since, prev=None):
    names = set()
    for _, it in raw:
        names |= _names(it.get("t", ""))
    by = defaultdict(dict)
    # 이전 누적(이미 가려진 제목) + 새 수집
    for o in (prev or {}).get("orgs") or []:
        for it in o.get("all") or []:
            if it["d"] >= since:
                by[o["name"]][re.sub(r"\W", "", it["t"])[:24]] = it
    for nm, it in raw:
        d = (it.get("d") or "")[:10]
        if not re.match(r"\d{4}-\d{2}-\d{2}$", d) or d < since:
            continue
        u = it.get("u") or ""
        if not u.startswith("https://"):
            u = ""
        t = mask(re.sub(r"\s+", " ", it.get("t") or "").strip(), names)
        key = re.sub(r"\W", "", t)[:24]
        if key and key not in by[nm]:
            by[nm][key] = {"t": t[:160], "d": d, "src": (it.get("src") or "")[:30], "u": u, "tg": tags(t)}
    today = date.today()
    wks = [(today - timedelta(today.weekday()) - timedelta(weeks=i)).isoformat() for i in range(WEEKS - 1, -1, -1)]
    orgs = []
    for cat, nm, q, rx in ORGS:
        al = sorted(by.get(nm, {}).values(), key=lambda x: x["d"], reverse=True)
        wc = Counter(_wk(x["d"]) for x in al)
        tc = Counter(t for x in al for t in x["tg"])
        r4 = sum(wc.get(w, 0) for w in wks[-4:])
        p8 = sum(wc.get(w, 0) for w in wks[-12:-4]) / 2.0
        orgs.append({"name": nm, "cat": cat, "n": len(al), "weekly": [wc.get(w, 0) for w in wks], "tags": dict(tc),
                     "r4": r4, "p4avg": round(p8, 1), "last": al[0]["d"] if al else None, "all": al[:60]})
    lead = sorted([dict(x, org=o["name"], cat=o["cat"]) for o in orgs for x in o["all"] if "리더십" in x["tg"]], key=lambda x: x["d"], reverse=True)[:20]
    stance = sorted([dict(x, org=o["name"], cat=o["cat"]) for o in orgs for x in o["all"] if "성명·입장" in x["tg"]], key=lambda x: x["d"], reverse=True)[:15]
    return {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "since": since, "weeks": wks, "cats": CATS,
            "tags": [k for k, _ in TAGS], "orgs": orgs, "leadership": lead, "stance": stance}


def main():
    net = "--offline" not in sys.argv
    prev = None
    try:
        prev = json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    raw, since, ok = collect(net)
    out = build(raw, since, prev)
    total = sum(o["n"] for o in out["orgs"])
    if not total:
        print("모인 소식 없음 - 기존 파일 유지")
        return 0
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"저장: {OUT} · 기관 {sum(1 for o in out['orgs'] if o['n'])}/{len(ORGS)}곳 · 소식 {total}건 · 온라인 조회 성공 {ok}곳")
    return 0


if __name__ == "__main__":
    sys.exit(main())
